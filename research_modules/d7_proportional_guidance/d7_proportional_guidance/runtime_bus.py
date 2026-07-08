"""D7-owned runtime-bus helpers for N-pair guidance state injection.

The helpers in this module are passive adapters: callers inject the current
D3/D4/D5 state for each assignment pair and D7 returns gate/log fields.  The
module keeps one visual PNG filter per resource-target context and never calls
AirSim, SimpleFlight, or any vehicle-control API.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .models import GuidanceMode
from .terminal_gate import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    TerminalPngContractDecision,
    coerce_assignment_guidance_binding,
    evaluate_terminal_png_contract,
    guidance_mode_from_terminal_contract,
)
from .vision_png import (
    PngGuidanceCommand,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
)


D7_RUNTIME_BUS_BOUNDARY = "d7_runtime_bus_state_injection_only_no_vehicle_control"


@dataclass(frozen=True)
class D7RuntimePairInput:
    """Injected D7 state for one assignment pair at one runtime sample."""

    binding: AssignmentGuidanceBinding | Mapping[str, Any] | Any
    d4_permission: D4GuidancePermission | Mapping[str, Any] | Any | None = None
    terminal_association: Mapping[str, Any] | Any | None = None
    observation: VisionGuidanceObservation | Mapping[str, Any] | Any | None = None
    timestamp_s: float | None = None
    resource_id: str | None = None
    handover_pending: bool = True
    terminal_locked: bool = False
    current_heading_rad: float = 0.0
    current_speed_mps: float = 0.0
    intercept_speed_mps: float = 0.0
    relative_position_ned: tuple[float, float, float] | None = None
    relative_velocity_ned: tuple[float, float, float] | None = None
    command_z_ned_m: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class D7RuntimePairOutput:
    """D7 gate and log fields for one injected assignment-pair sample."""

    timestamp_s: float
    resource_id: str
    assigned_global_track_id: str
    control_context_id: str
    mode: GuidanceMode
    guidance_law: str
    visual_png_enabled: bool
    terminal_contract_allowed: bool
    terminal_contract_reject_reason: str
    terminal_switch_allowed: bool
    terminal_switch_reject_reason: str
    plan_id: str
    plan_version: int
    track_version: int
    d4_action: str
    d5_decision_state: str
    assignment_id: str | None = None
    owner_node_id: str | None = None
    d4_target_node_id: str | None = None
    local_track_id: str | None = None
    stable_frame_count: int = 0
    ttc_s: float | None = None
    los_rate_radps: float = 0.0
    png_guidance_law_candidate: str | None = None
    selected_velocity_ned: tuple[float, float, float] | None = None
    png_command: PngGuidanceCommand | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_log_record(self) -> dict[str, Any]:
        """Return JSON/CSV-friendly D7 runtime bus fields."""

        return {
            "timestamp_s": self.timestamp_s,
            "resource_id": self.resource_id,
            "target_id": self.assigned_global_track_id,
            "assigned_global_track_id": self.assigned_global_track_id,
            "control_context_id": self.control_context_id,
            "assignment_id": self.assignment_id,
            "mode": self.mode.value,
            "guidance_law": self.guidance_law,
            "visual_png_enabled": self.visual_png_enabled,
            "terminal_contract_allowed": self.terminal_contract_allowed,
            "terminal_contract_reject_reason": self.terminal_contract_reject_reason,
            "terminal_switch_allowed": self.terminal_switch_allowed,
            "terminal_switch_reject_reason": self.terminal_switch_reject_reason,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "owner_node_id": self.owner_node_id,
            "d4_target_node_id": self.d4_target_node_id,
            "track_version": self.track_version,
            "d4_action": self.d4_action,
            "d5_decision_state": self.d5_decision_state,
            "local_track_id": self.local_track_id,
            "stable_frame_count": self.stable_frame_count,
            "ttc_s": self.ttc_s,
            "los_rate_radps": self.los_rate_radps,
            "png_guidance_law_candidate": self.png_guidance_law_candidate,
            "selected_velocity_ned": self.selected_velocity_ned,
            **self.metadata,
        }


class D7RuntimeBus:
    """Stateful per-pair visual filter registry for D7 runtime injection."""

    def __init__(self, config: PngGuidanceConfig | None = None) -> None:
        self.config = config or PngGuidanceConfig()
        self._filters: dict[str, SimpleFlightPngGuidanceFilter] = {}
        self._binding_signatures: dict[str, tuple[str, int, str | None, int, str | None]] = {}

    @property
    def control_context_ids(self) -> tuple[str, ...]:
        return tuple(self._filters)

    def reset(self) -> None:
        self._filters.clear()
        self._binding_signatures.clear()

    def reset_pair(self, control_context_id: str) -> None:
        self._filters.pop(control_context_id, None)
        self._binding_signatures.pop(control_context_id, None)

    def inject_state(
        self,
        pair_inputs: Iterable[D7RuntimePairInput | Mapping[str, Any] | Any],
    ) -> list[D7RuntimePairOutput]:
        """Evaluate one runtime bus sample for every injected assignment pair."""

        return [self.evaluate_pair(_coerce_pair_input(item)) for item in pair_inputs]

    def evaluate_pair(self, pair_input: D7RuntimePairInput) -> D7RuntimePairOutput:
        """Evaluate D3/D4/D5 contract and optional visual PNG gate for one pair."""

        binding = coerce_assignment_guidance_binding(pair_input.binding)
        control_context_id = _control_context_id(binding)
        signature = _binding_signature(binding)
        if self._binding_signatures.get(control_context_id) != signature:
            self._filters[control_context_id] = SimpleFlightPngGuidanceFilter(self.config)
            self._binding_signatures[control_context_id] = signature

        observation = (
            coerce_vision_guidance_observation(pair_input.observation)
            if pair_input.observation is not None
            else None
        )
        timestamp_s = _resolve_timestamp_s(pair_input, observation, binding)
        decision = evaluate_terminal_png_contract(
            binding=binding,
            d4_permission=pair_input.d4_permission,
            terminal_association=pair_input.terminal_association,
            observation=observation,
            timestamp_s=timestamp_s,
            resource_id=pair_input.resource_id or binding.resource_id,
        )

        common = _common_output_kwargs(
            timestamp_s=timestamp_s,
            binding=binding,
            control_context_id=control_context_id,
            decision=decision,
            metadata={
                "boundary": D7_RUNTIME_BUS_BOUNDARY,
                **pair_input.metadata,
            },
        )

        if not decision.allowed:
            return D7RuntimePairOutput(
                **common,
                mode=guidance_mode_from_terminal_contract(
                    decision,
                    handover_pending=pair_input.handover_pending,
                    terminal_locked=pair_input.terminal_locked,
                ),
                guidance_law="radar_pn",
                visual_png_enabled=False,
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="",
            )

        if observation is None:
            return D7RuntimePairOutput(
                **common,
                mode=GuidanceMode.HANDOVER_PENDING,
                guidance_law="radar_pn",
                visual_png_enabled=False,
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="vision_observation_missing",
            )

        command = self._filters[control_context_id].evaluate(
            observation,
            current_heading_rad=pair_input.current_heading_rad,
            current_speed_mps=pair_input.current_speed_mps,
            intercept_speed_mps=pair_input.intercept_speed_mps,
            relative_position_ned=pair_input.relative_position_ned,
            relative_velocity_ned=pair_input.relative_velocity_ned,
            command_z_ned_m=pair_input.command_z_ned_m,
        )
        visual_png_enabled = bool(command.quality.terminal_switch_allowed)
        return D7RuntimePairOutput(
            **common,
            mode=GuidanceMode.VISION_TERMINAL if visual_png_enabled else GuidanceMode.HANDOVER_PENDING,
            guidance_law=command.guidance_law if visual_png_enabled else "radar_pn",
            visual_png_enabled=visual_png_enabled,
            terminal_switch_allowed=visual_png_enabled,
            terminal_switch_reject_reason=command.quality.reject_reason,
            stable_frame_count=command.quality.stable_frame_count,
            ttc_s=command.quality.ttc_s,
            los_rate_radps=command.quality.los_rate_radps,
            png_guidance_law_candidate=command.guidance_law,
            selected_velocity_ned=command.velocity_ned if visual_png_enabled else None,
            png_command=command,
        )


def coerce_vision_guidance_observation(
    value: VisionGuidanceObservation | Mapping[str, Any] | Any,
) -> VisionGuidanceObservation:
    """Coerce D5/AirSim/replay-style bbox records into D7 observations."""

    if isinstance(value, VisionGuidanceObservation):
        return value
    metadata = dict(_value(value, ("metadata",), default={}) or {})
    latency_s = _optional_float_value(
        value,
        ("visual_latency_s", "measurement_age_s", "latency_s"),
    )
    if latency_s is not None:
        metadata["visual_latency_s"] = latency_s
    source = _optional_string_value(value, ("source", "detector_source", "replay_source"))
    if source is not None:
        metadata.setdefault("source", source)
    frame_index = _value(value, ("frame_index",), default=None)
    if frame_index is not None:
        metadata.setdefault("frame_index", frame_index)
    return VisionGuidanceObservation(
        timestamp_s=_required_float(value, ("timestamp_s", "timestamp", "t")),
        frame_timestamp_s=_optional_float_value(value, ("frame_timestamp_s", "frame_time_s")),
        bbox_xyxy=_bbox_xyxy(value),
        detection_confidence=_float_value(
            value,
            ("detection_confidence", "confidence", "score"),
            default=1.0,
        ),
        local_track_id=_optional_string_value(value, ("local_track_id", "track_id", "bytetrack_id")),
        assigned_global_track_id=_optional_string_value(
            value,
            ("assigned_global_track_id", "global_track_id", "target_id"),
        ),
        camera_id=_optional_string_value(value, ("camera_id", "camera_name")),
        metadata=metadata,
    )


def summarize_runtime_bus_outputs(outputs: Iterable[D7RuntimePairOutput]) -> dict[str, Any]:
    """Summarize D7 runtime bus fields without rerunning guidance or control."""

    rows = list(outputs)
    contract_rejects: Counter[str] = Counter()
    switch_rejects: Counter[str] = Counter()
    guidance_laws: Counter[str] = Counter()
    for row in rows:
        guidance_laws[row.guidance_law] += 1
        if row.terminal_contract_reject_reason:
            contract_rejects[row.terminal_contract_reject_reason] += 1
        if row.terminal_switch_reject_reason:
            switch_rejects[row.terminal_switch_reject_reason] += 1

    visual_png_switch_count = sum(1 for row in rows if row.visual_png_enabled)
    return {
        "boundary": D7_RUNTIME_BUS_BOUNDARY,
        "sample_count": len(rows),
        "control_context_count": len({row.control_context_id for row in rows}),
        "control_context_ids": sorted({row.control_context_id for row in rows}),
        "visual_png_switch_count": visual_png_switch_count,
        "terminal_contract_reject_count": sum(contract_rejects.values()),
        "terminal_contract_reject_reasons": dict(contract_rejects),
        "terminal_switch_reject_count": sum(switch_rejects.values()),
        "terminal_switch_reject_reasons": dict(switch_rejects),
        "terminal_switch_allowed_rate": visual_png_switch_count / len(rows) if rows else 0.0,
        "guidance_law_counts": dict(guidance_laws),
    }


def _common_output_kwargs(
    *,
    timestamp_s: float,
    binding: AssignmentGuidanceBinding,
    control_context_id: str,
    decision: TerminalPngContractDecision,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp_s": timestamp_s,
        "resource_id": binding.resource_id,
        "assigned_global_track_id": binding.assigned_global_track_id,
        "control_context_id": control_context_id,
        "terminal_contract_allowed": decision.allowed,
        "terminal_contract_reject_reason": decision.reject_reason,
        "plan_id": binding.plan_id,
        "plan_version": binding.plan_version,
        "track_version": binding.track_version,
        "assignment_id": binding.assignment_id,
        "owner_node_id": binding.owner_node_id,
        "d4_target_node_id": decision.d4_target_node_id,
        "d4_action": decision.d4_action,
        "d5_decision_state": decision.d5_decision_state,
        "local_track_id": decision.local_track_id,
        "metadata": metadata,
    }


def _coerce_pair_input(value: D7RuntimePairInput | Mapping[str, Any] | Any) -> D7RuntimePairInput:
    if isinstance(value, D7RuntimePairInput):
        return value
    return D7RuntimePairInput(
        binding=_value(value, ("binding", "assignment", "guidance_binding"), default=None),
        d4_permission=_value(value, ("d4_permission", "d4", "permission"), default=None),
        terminal_association=_value(value, ("terminal_association", "d5_terminal_association", "d5"), default=None),
        observation=_value(value, ("observation", "vision_observation", "bbox_observation"), default=None),
        timestamp_s=_optional_float_value(value, ("timestamp_s", "timestamp", "t")),
        resource_id=_optional_string_value(value, ("resource_id",)),
        handover_pending=bool(_value(value, ("handover_pending",), default=True)),
        terminal_locked=bool(_value(value, ("terminal_locked",), default=False)),
        current_heading_rad=_float_value(value, ("current_heading_rad",), default=0.0),
        current_speed_mps=_float_value(value, ("current_speed_mps",), default=0.0),
        intercept_speed_mps=_float_value(value, ("intercept_speed_mps",), default=0.0),
        relative_position_ned=_optional_tuple3(value, ("relative_position_ned",)),
        relative_velocity_ned=_optional_tuple3(value, ("relative_velocity_ned",)),
        command_z_ned_m=_float_value(value, ("command_z_ned_m",), default=0.0),
        metadata=dict(_value(value, ("metadata",), default={}) or {}),
    )


def _control_context_id(binding: AssignmentGuidanceBinding) -> str:
    return f"{binding.resource_id}->{binding.assigned_global_track_id}"


def _binding_signature(
    binding: AssignmentGuidanceBinding,
) -> tuple[str, int, str | None, int, str | None]:
    return (
        binding.plan_id,
        binding.plan_version,
        binding.owner_node_id,
        binding.track_version,
        binding.assignment_id,
    )


def _resolve_timestamp_s(
    pair_input: D7RuntimePairInput,
    observation: VisionGuidanceObservation | None,
    binding: AssignmentGuidanceBinding,
) -> float:
    if pair_input.timestamp_s is not None:
        return float(pair_input.timestamp_s)
    if observation is not None:
        return float(observation.timestamp_s)
    return float(binding.created_at_s)


def _bbox_xyxy(value: Any) -> tuple[float, float, float, float]:
    bbox = _value(value, ("bbox_xyxy", "xyxy", "bbox"), default=None)
    if bbox is not None:
        return _tuple4(bbox, "bbox_xyxy")
    xywh = _value(value, ("bbox_xywh", "xywh"), default=None)
    if xywh is None:
        raise ValueError("observation requires bbox_xyxy/xyxy/bbox or bbox_xywh/xywh")
    x, y, width, height = _tuple4(xywh, "bbox_xywh")
    return (x, y, x + width, y + height)


def _tuple4(value: Any, name: str) -> tuple[float, float, float, float]:
    try:
        items = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence") from exc
    if len(items) != 4:
        raise ValueError(f"{name} must contain exactly four values")
    return (float(items[0]), float(items[1]), float(items[2]), float(items[3]))


def _optional_tuple3(value: Any, names: tuple[str, ...]) -> tuple[float, float, float] | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    try:
        items = tuple(raw)
    except TypeError as exc:
        raise ValueError(f"{names[0]} must be a sequence") from exc
    if len(items) != 3:
        raise ValueError(f"{names[0]} must contain exactly three values")
    return (float(items[0]), float(items[1]), float(items[2]))


def _required_float(value: Any, names: tuple[str, ...]) -> float:
    raw = _value(value, names, default=None)
    if raw is None:
        raise ValueError(f"{names[0]} is required")
    return float(raw)


def _float_value(value: Any, names: tuple[str, ...], *, default: float) -> float:
    return float(_value(value, names, default=default))


def _optional_float_value(value: Any, names: tuple[str, ...]) -> float | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    return float(raw)


def _optional_string_value(value: Any, names: tuple[str, ...]) -> str | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    if hasattr(raw, "value"):
        raw = raw.value
    text = str(raw)
    return text if text else None


def _value(record: Any, names: tuple[str, ...], *, default: Any) -> Any:
    if record is None:
        return default
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if not isinstance(record, Mapping) and hasattr(record, name):
            return getattr(record, name)
    return default
