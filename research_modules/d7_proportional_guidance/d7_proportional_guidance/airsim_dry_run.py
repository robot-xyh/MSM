"""D7 AirSim phase-1 dry-run adapter.

The adapter accepts plain Python assignment/resource/target-estimate records and
returns D7 proportional-guidance log records. It intentionally does not import
AirSim, connect to a simulator, or call vehicle-control APIs. Outputs are
offline research records for interface and logging checks only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .models import GuidanceConfig, GuidanceMode, GuidanceRecord, GuidanceState
from .pn import compute_proportional_navigation_command
from .simulator import summarize_guidance_records


AIRSIM_PHASE1_DRY_RUN_BOUNDARY = (
    "offline_airsim_phase1_dry_run_only_no_vehicle_control"
)
DEFAULT_DRY_RUN_RESOURCE_SPEED_MPS = 48.0
_MISSING = object()


def make_minimal_airsim_dry_run_fixture() -> dict[str, Any]:
    """Return a deterministic fake AirSim-like fixture for D7 adapter tests."""

    return {
        "fixture_id": "d7_minimal_airsim_phase1_dry_run",
        "frame_id": "ned",
        "assignment": {
            "assignment_id": "dry_assignment_001",
            "plan_id": "dry_plan_001",
            "plan_version": 1,
            "resource_id": "R01",
            "target_id": "T01",
            "authorization_state": "recorded",
            "timestamp_s": 0.0,
        },
        "resource": {
            "resource_id": "R01",
            "position_ned": [0.0, 0.0, -10.0],
            "velocity_ned": [48.0, 0.0, 0.0],
        },
        "target_estimate": {
            "global_track_id": "T01",
            "valid_at": 0.0,
            "position_ned": [620.0, 120.0, -15.0],
            "velocity_ned": [-22.0, -3.0, 0.0],
            "covariance_trace": 18.0,
            "source": "global_track_estimate",
            "metadata": {
                "fixture_id": "d7_minimal_airsim_phase1_dry_run",
                "frame_id": "ned",
            },
        },
    }


def guidance_records_from_airsim_dry_run_fixture(
    fixture: Mapping[str, Any],
    config: GuidanceConfig | None = None,
    *,
    default_resource_speed_mps: float = DEFAULT_DRY_RUN_RESOURCE_SPEED_MPS,
) -> tuple[list[GuidanceRecord], dict[str, Any]]:
    """Convert a fake AirSim phase-1 fixture into D7 guidance records."""

    frame_id = str(fixture.get("frame_id", "ned")).lower()
    if frame_id != "ned":
        raise ValueError("D7 AirSim dry-run fixture must use frame_id='ned'")
    return guidance_records_from_assignment_dry_run(
        assignment=fixture["assignment"],
        resource=fixture["resource"],
        target_estimate=fixture["target_estimate"],
        config=config,
        default_resource_speed_mps=default_resource_speed_mps,
    )


def guidance_records_from_assignment_dry_run(
    assignment: Mapping[str, Any] | Any,
    resource: Mapping[str, Any] | Any,
    target_estimate: Mapping[str, Any] | Any,
    config: GuidanceConfig | None = None,
    *,
    default_resource_speed_mps: float = DEFAULT_DRY_RUN_RESOURCE_SPEED_MPS,
) -> tuple[list[GuidanceRecord], dict[str, Any]]:
    """Produce radar-midcourse and vision-terminal records for one handoff.

    Inputs are passive data objects: an assignment, a resource state, and a
    target estimate. The returned records are not actuator commands and are not
    suitable for real vehicle control.
    """

    if default_resource_speed_mps <= 0.0:
        raise ValueError("default_resource_speed_mps must be positive")

    cfg = config or GuidanceConfig()
    resource_id = _resolve_resource_id(assignment, resource)
    target_id = _resolve_target_id(assignment, target_estimate)
    timestamp_s = _float_value(
        target_estimate,
        ("timestamp_s", "timestamp", "valid_at", "published_at"),
        default=_float_value(
            assignment,
            ("timestamp_s", "timestamp", "created_at"),
            default=0.0,
        ),
    )
    resource_position = _position_xy(resource, "resource")
    target_position = _position_xy(target_estimate, "target_estimate")
    resource_velocity = _resource_velocity_xy(
        resource=resource,
        resource_position=resource_position,
        target_position=target_position,
        default_speed_mps=default_resource_speed_mps,
    )
    target_velocity = _velocity_xy(
        target_estimate,
        "target_estimate",
        default=(0.0, 0.0),
    )

    pursuer = GuidanceState(
        entity_id=resource_id,
        timestamp_s=timestamp_s,
        position_m=resource_position,
        velocity_mps=resource_velocity,
        source=str(_value(resource, ("source",), default="assignment_resource_state")),
        metadata={
            "dry_run": True,
            "boundary": AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
            "input_frame_id": _frame_id(resource),
        },
    )
    target = GuidanceState(
        entity_id=target_id,
        timestamp_s=timestamp_s,
        position_m=target_position,
        velocity_mps=target_velocity,
        source=str(_value(target_estimate, ("source",), default="global_track_estimate")),
        covariance_trace=_optional_float(
            _value(target_estimate, ("covariance_trace",), default=None)
        ),
        metadata={
            **_metadata(target_estimate),
            "dry_run": True,
            "boundary": AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
            "input_frame_id": _frame_id(target_estimate),
        },
    )

    assignment_metadata = _assignment_metadata(assignment)
    radar_record = _record_for_mode(
        mode=GuidanceMode.RADAR_MIDCOURSE,
        timestamp_s=timestamp_s,
        pursuer=pursuer,
        target=target,
        cfg=cfg,
        resource_id=resource_id,
        target_id=target_id,
        assignment_metadata=assignment_metadata,
        mode_switch=False,
    )
    vision_record = _record_for_mode(
        mode=GuidanceMode.VISION_TERMINAL,
        timestamp_s=timestamp_s + cfg.dt_s,
        pursuer=pursuer,
        target=target,
        cfg=cfg,
        resource_id=resource_id,
        target_id=target_id,
        assignment_metadata=assignment_metadata,
        mode_switch=True,
    )
    records = [radar_record, vision_record]
    summary = summarize_guidance_records(records, cfg)
    summary.update(
        {
            "dry_run": True,
            "phase": "airsim_phase1",
            "boundary": AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
            "record_count": len(records),
            "resource_id": resource_id,
            "target_id": target_id,
            **assignment_metadata,
        }
    )
    return records, summary


guidance_records_from_airsim_phase1_dry_run = guidance_records_from_assignment_dry_run


def _record_for_mode(
    *,
    mode: GuidanceMode,
    timestamp_s: float,
    pursuer: GuidanceState,
    target: GuidanceState,
    cfg: GuidanceConfig,
    resource_id: str,
    target_id: str,
    assignment_metadata: dict[str, Any],
    mode_switch: bool,
) -> GuidanceRecord:
    command = compute_proportional_navigation_command(
        pursuer=pursuer,
        target=target,
        dt_s=cfg.dt_s,
        navigation_constant=cfg.navigation_constant,
        mode=mode,
        max_lateral_accel_mps2=cfg.max_lateral_accel_mps2,
        max_turn_rate_radps=cfg.max_turn_rate_radps,
        min_speed_mps=cfg.min_speed_mps,
    )
    observation = _observation_for_mode(
        mode=mode,
        command_los_angle_rad=command.los_angle_rad,
        range_m=command.range_m,
        pursuer=pursuer,
        target=target,
        cfg=cfg,
        assignment_metadata=assignment_metadata,
    )
    return GuidanceRecord(
        timestamp_s=timestamp_s,
        resource_id=resource_id,
        target_id=target_id,
        mode=mode,
        range_m=command.range_m,
        los_angle_rad=command.los_angle_rad,
        los_rate_radps=command.los_rate_radps,
        closing_speed_mps=command.closing_speed_mps,
        commanded_lateral_accel_mps2=command.commanded_lateral_accel_mps2,
        limited_lateral_accel_mps2=command.limited_lateral_accel_mps2,
        limited_turn_rate_radps=command.limited_turn_rate_radps,
        pursuer_position_m=pursuer.position_m,
        pursuer_velocity_mps=pursuer.velocity_mps,
        target_position_m=target.position_m,
        target_velocity_mps=target.velocity_mps,
        target_estimated_position_m=target.position_m,
        target_estimated_velocity_mps=target.velocity_mps,
        observation=observation,
        mode_switch=mode_switch,
    )


def _observation_for_mode(
    *,
    mode: GuidanceMode,
    command_los_angle_rad: float,
    range_m: float,
    pursuer: GuidanceState,
    target: GuidanceState,
    cfg: GuidanceConfig,
    assignment_metadata: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "dry_run": True,
        "phase": "airsim_phase1",
        "boundary": AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
        "truth_state_available": False,
        "target_source": target.source,
        **assignment_metadata,
    }
    if mode == GuidanceMode.RADAR_MIDCOURSE:
        return {
            **base,
            "source": "global_track_estimate",
            "range_estimate_m": range_m,
            "los_angle_rad": command_los_angle_rad,
            "covariance_trace": target.covariance_trace,
        }

    heading_rad = _heading_from_velocity(pursuer.velocity_mps, command_los_angle_rad)
    relative_bearing_rad = _wrap_pi(command_los_angle_rad - heading_rad)
    pixel_x = cfg.vision_image_center_x_px + cfg.vision_focal_length_px * math.tan(
        relative_bearing_rad
    )
    return {
        **base,
        "source": "vision_los_dry_run",
        "range_estimate_m": range_m,
        "los_angle_rad": command_los_angle_rad,
        "relative_bearing_rad": relative_bearing_rad,
        "pixel_x": float(pixel_x),
        "focal_length_px": cfg.vision_focal_length_px,
        "relative_velocity_source": "target_estimate",
    }


def _resolve_resource_id(assignment: Any, resource: Any) -> str:
    assignment_resource_id = _string_value(
        assignment,
        ("resource_id", "owner", "assigned_resource_id"),
        default=None,
    )
    resource_id = _string_value(
        resource,
        ("resource_id", "entity_id", "id"),
        default=assignment_resource_id,
    )
    if not resource_id:
        raise ValueError("resource_id must be present on assignment or resource")
    if assignment_resource_id and assignment_resource_id != resource_id:
        raise ValueError("assignment.resource_id does not match resource.resource_id")
    return resource_id


def _resolve_target_id(assignment: Any, target_estimate: Any) -> str:
    assignment_target_id = _string_value(
        assignment,
        ("target_id", "assigned_global_track_id", "global_track_id"),
        default=None,
    )
    target_id = _string_value(
        target_estimate,
        ("target_id", "global_track_id", "track_id", "entity_id", "id"),
        default=assignment_target_id,
    )
    if not target_id:
        raise ValueError("target_id must be present on assignment or target_estimate")
    if assignment_target_id and assignment_target_id != target_id:
        raise ValueError("assignment target_id does not match target_estimate target_id")
    return target_id


def _position_xy(record: Any, label: str) -> tuple[float, float]:
    value = _value(
        record,
        ("position_m", "position_xy_m", "position_ned", "position", "state_ned", "state"),
        default=_MISSING,
    )
    if value is _MISSING:
        raise ValueError(f"{label} requires position_m, position_ned, or state_ned")
    return _xy_from_sequence(value, f"{label}.position", offset=0)


def _velocity_xy(
    record: Any,
    label: str,
    *,
    default: tuple[float, float] | None = None,
) -> tuple[float, float]:
    value = _value(
        record,
        ("velocity_mps", "velocity_xy_mps", "velocity_ned", "velocity"),
        default=_MISSING,
    )
    if value is not _MISSING:
        return _xy_from_sequence(value, f"{label}.velocity", offset=0)
    state = _value(record, ("state_ned", "state"), default=_MISSING)
    if state is not _MISSING:
        return _xy_from_sequence(state, f"{label}.state velocity", offset=3)
    if default is not None:
        return default
    raise ValueError(f"{label} requires velocity_mps, velocity_ned, or state_ned")


def _resource_velocity_xy(
    *,
    resource: Any,
    resource_position: tuple[float, float],
    target_position: tuple[float, float],
    default_speed_mps: float,
) -> tuple[float, float]:
    velocity = _velocity_xy(resource, "resource", default=(0.0, 0.0))
    if _speed(velocity) > 0.0:
        return velocity
    line_x = target_position[0] - resource_position[0]
    line_y = target_position[1] - resource_position[1]
    distance = math.hypot(line_x, line_y)
    if distance <= 1e-12:
        return (default_speed_mps, 0.0)
    return (
        default_speed_mps * line_x / distance,
        default_speed_mps * line_y / distance,
    )


def _xy_from_sequence(value: Any, name: str, *, offset: int) -> tuple[float, float]:
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence") from exc
    if len(values) < offset + 2:
        raise ValueError(f"{name} must contain at least {offset + 2} values")
    return (float(values[offset]), float(values[offset + 1]))


def _assignment_metadata(assignment: Any) -> dict[str, Any]:
    metadata = {
        "assignment_id": _string_value(assignment, ("assignment_id", "id"), default=None),
        "plan_id": _string_value(assignment, ("plan_id",), default=None),
        "plan_version": _optional_int(
            _value(assignment, ("plan_version", "version"), default=None)
        ),
        "authorization_state": _string_value(
            assignment,
            ("authorization_state", "human_authorization_state"),
            default=None,
        ),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _metadata(record: Any) -> dict[str, Any]:
    value = _value(record, ("metadata",), default={})
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _frame_id(record: Any) -> str:
    value = _value(record, ("frame_id",), default=None)
    if value is None:
        metadata = _metadata(record)
        value = metadata.get("frame_id", "ned")
    return str(value)


def _string_value(
    record: Any,
    names: tuple[str, ...],
    *,
    default: str | None,
) -> str | None:
    value = _value(record, names, default=default)
    if value is None:
        return None
    text = str(value)
    return text if text else default


def _float_value(record: Any, names: tuple[str, ...], *, default: float) -> float:
    value = _value(record, names, default=default)
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _value(record: Any, names: tuple[str, ...], *, default: Any) -> Any:
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if not isinstance(record, Mapping) and hasattr(record, name):
            return getattr(record, name)
    return default


def _speed(velocity: tuple[float, float]) -> float:
    return math.hypot(velocity[0], velocity[1])


def _heading_from_velocity(
    velocity_mps: tuple[float, float],
    fallback_rad: float,
) -> float:
    speed = _speed(velocity_mps)
    if speed <= 1e-12:
        return fallback_rad
    return math.atan2(velocity_mps[1], velocity_mps[0])


def _wrap_pi(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
