"""Safety-bounded active-vision interfaces for D5 research policies.

These interfaces produce camera observation intents only.  They do not expose
vehicle motion, weapons, assignment, or global-track mutation actions.  The
default policy is a deterministic rule scanner used when observations time out
or association confidence is low; no learned policy is claimed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence, runtime_checkable

import numpy as np


class ActiveVisionActionType(str, Enum):
    OBSERVE_TARGET = "observe_target"
    SEARCH_SECTOR = "search_sector"
    GIMBAL_INCREMENT = "gimbal_increment"
    SET_FOV_ZOOM = "set_fov_zoom"


@dataclass(frozen=True)
class ActiveVisionAction:
    """One bounded camera-only action intent."""

    action_type: ActiveVisionActionType
    camera_id: str
    issued_timestamp: float
    target_global_track_id: str | None = None
    search_sector_deg: tuple[float, float, float, float] | None = None
    gimbal_increment_deg: tuple[float, float] | None = None
    horizontal_fov_deg: float | None = None
    zoom_ratio: float | None = None
    reason: str = "policy"

    def __post_init__(self) -> None:
        if not str(self.camera_id).strip():
            raise ValueError("camera_id must be non-empty")
        if not np.isfinite(self.issued_timestamp) or self.issued_timestamp < 0.0:
            raise ValueError("issued_timestamp must be finite and non-negative")
        action_type = ActiveVisionActionType(self.action_type)
        object.__setattr__(self, "action_type", action_type)
        target_id = str(self.target_global_track_id).strip() if self.target_global_track_id else None
        object.__setattr__(self, "target_global_track_id", target_id)
        if action_type is ActiveVisionActionType.OBSERVE_TARGET:
            if target_id is None:
                raise ValueError("observe_target requires a center-owned target reference")
            _require_absent(self.search_sector_deg, self.gimbal_increment_deg, self.horizontal_fov_deg, self.zoom_ratio)
        elif action_type is ActiveVisionActionType.SEARCH_SECTOR:
            sector = _search_sector(self.search_sector_deg)
            object.__setattr__(self, "search_sector_deg", sector)
            _require_absent(target_id, self.gimbal_increment_deg, self.horizontal_fov_deg, self.zoom_ratio)
        elif action_type is ActiveVisionActionType.GIMBAL_INCREMENT:
            increment = _finite_pair(self.gimbal_increment_deg, "gimbal_increment_deg")
            object.__setattr__(self, "gimbal_increment_deg", increment)
            _require_absent(target_id, self.search_sector_deg, self.horizontal_fov_deg, self.zoom_ratio)
        elif action_type is ActiveVisionActionType.SET_FOV_ZOOM:
            if self.horizontal_fov_deg is None and self.zoom_ratio is None:
                raise ValueError("set_fov_zoom requires horizontal_fov_deg or zoom_ratio")
            if self.horizontal_fov_deg is not None and (
                not np.isfinite(self.horizontal_fov_deg) or self.horizontal_fov_deg <= 0.0
            ):
                raise ValueError("horizontal_fov_deg must be finite and positive")
            if self.zoom_ratio is not None and (
                not np.isfinite(self.zoom_ratio) or self.zoom_ratio <= 0.0
            ):
                raise ValueError("zoom_ratio must be finite and positive")
            _require_absent(target_id, self.search_sector_deg, self.gimbal_increment_deg)


@dataclass(frozen=True)
class ActiveVisionObservation:
    """Truth-free policy observation for one camera."""

    camera_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    association_confidence: float
    last_detection_timestamp: float | None = None
    center_owned_global_track_id: str | None = None
    current_gimbal_deg: tuple[float, float] = (0.0, 0.0)
    current_horizontal_fov_deg: float = 60.0

    def __post_init__(self) -> None:
        if not str(self.camera_id).strip():
            raise ValueError("camera_id must be non-empty")
        if not np.isfinite(self.measurement_timestamp) or not np.isfinite(self.arrival_timestamp):
            raise ValueError("timestamps must be finite")
        if self.arrival_timestamp + 1.0e-12 < self.measurement_timestamp:
            raise ValueError("arrival_timestamp must not precede measurement_timestamp")
        if not 0.0 <= self.association_confidence <= 1.0:
            raise ValueError("association_confidence must be in [0, 1]")
        if self.last_detection_timestamp is not None and not np.isfinite(self.last_detection_timestamp):
            raise ValueError("last_detection_timestamp must be finite when present")
        object.__setattr__(self, "current_gimbal_deg", _finite_pair(self.current_gimbal_deg, "current_gimbal_deg"))
        if not np.isfinite(self.current_horizontal_fov_deg) or self.current_horizontal_fov_deg <= 0.0:
            raise ValueError("current_horizontal_fov_deg must be finite and positive")
        center_id = (
            str(self.center_owned_global_track_id).strip()
            if self.center_owned_global_track_id
            else None
        )
        object.__setattr__(self, "center_owned_global_track_id", center_id)


@dataclass(frozen=True)
class ActiveVisionSafetyConfig:
    """Timeout, confidence, and actuator-envelope limits."""

    observation_timeout_s: float = 0.75
    minimum_association_confidence: float = 0.6
    max_gimbal_increment_deg: float = 8.0
    minimum_horizontal_fov_deg: float = 10.0
    maximum_horizontal_fov_deg: float = 120.0
    minimum_zoom_ratio: float = 1.0
    maximum_zoom_ratio: float = 12.0
    scan_sectors_deg: tuple[tuple[float, float, float, float], ...] = (
        (-60.0, -20.0, -20.0, 20.0),
        (-20.0, 20.0, -20.0, 20.0),
        (20.0, 60.0, -20.0, 20.0),
    )

    def __post_init__(self) -> None:
        if self.observation_timeout_s <= 0.0 or not np.isfinite(self.observation_timeout_s):
            raise ValueError("observation_timeout_s must be finite and positive")
        if not 0.0 <= self.minimum_association_confidence <= 1.0:
            raise ValueError("minimum_association_confidence must be in [0, 1]")
        if self.max_gimbal_increment_deg <= 0.0 or not np.isfinite(self.max_gimbal_increment_deg):
            raise ValueError("max_gimbal_increment_deg must be finite and positive")
        if not 0.0 < self.minimum_horizontal_fov_deg <= self.maximum_horizontal_fov_deg < 180.0:
            raise ValueError("horizontal FOV bounds are invalid")
        if not 0.0 < self.minimum_zoom_ratio <= self.maximum_zoom_ratio:
            raise ValueError("zoom bounds are invalid")
        sectors = tuple(_search_sector(sector) for sector in self.scan_sectors_deg)
        if not sectors:
            raise ValueError("at least one rule scan sector is required")
        object.__setattr__(self, "scan_sectors_deg", sectors)


@runtime_checkable
class ActiveVisionEnvironment(Protocol):
    """Environment surface accepted by camera-only active-vision policies."""

    def observe(self, camera_id: str) -> ActiveVisionObservation:
        ...

    def apply_camera_action(self, action: ActiveVisionAction) -> ActiveVisionObservation:
        ...


@runtime_checkable
class ActiveVisionPolicy(Protocol):
    def select_action(
        self,
        observation: ActiveVisionObservation,
        *,
        current_timestamp: float,
        center_owned_global_track_ids: Sequence[str],
    ) -> ActiveVisionAction:
        ...


class SafeRuleScanPolicy:
    """Observe a valid center cue; otherwise rotate deterministic scan sectors."""

    def __init__(self, config: ActiveVisionSafetyConfig | None = None) -> None:
        self.config = config or ActiveVisionSafetyConfig()
        self._next_sector_by_camera: dict[str, int] = {}

    def select_action(
        self,
        observation: ActiveVisionObservation,
        *,
        current_timestamp: float,
        center_owned_global_track_ids: Sequence[str],
    ) -> ActiveVisionAction:
        if not np.isfinite(current_timestamp) or current_timestamp < observation.arrival_timestamp - 1.0e-12:
            raise ValueError("current_timestamp must be finite and not precede observation arrival")
        allowed_ids = {str(value) for value in center_owned_global_track_ids if str(value)}
        target_id = observation.center_owned_global_track_id
        detection_age = (
            float("inf")
            if observation.last_detection_timestamp is None
            else max(0.0, current_timestamp - observation.last_detection_timestamp)
        )
        timed_out = detection_age > self.config.observation_timeout_s
        low_confidence = observation.association_confidence < self.config.minimum_association_confidence
        invalid_binding = target_id is None or target_id not in allowed_ids
        if timed_out or low_confidence or invalid_binding:
            reasons = []
            if timed_out:
                reasons.append("observation_timeout")
            if low_confidence:
                reasons.append("low_association_confidence")
            if invalid_binding:
                reasons.append("center_binding_unavailable")
            return self._next_scan_action(
                observation.camera_id,
                current_timestamp,
                reason="rule_scan_fallback:" + "+".join(reasons),
            )
        return ActiveVisionAction(
            action_type=ActiveVisionActionType.OBSERVE_TARGET,
            camera_id=observation.camera_id,
            issued_timestamp=current_timestamp,
            target_global_track_id=target_id,
            reason="fresh_confident_center_binding",
        )

    def bounded_gimbal_increment(
        self,
        *,
        camera_id: str,
        current_timestamp: float,
        yaw_delta_deg: float,
        pitch_delta_deg: float,
        reason: str = "bounded_gimbal_correction",
    ) -> ActiveVisionAction:
        limit = self.config.max_gimbal_increment_deg
        increment = (
            float(np.clip(yaw_delta_deg, -limit, limit)),
            float(np.clip(pitch_delta_deg, -limit, limit)),
        )
        return ActiveVisionAction(
            action_type=ActiveVisionActionType.GIMBAL_INCREMENT,
            camera_id=camera_id,
            issued_timestamp=current_timestamp,
            gimbal_increment_deg=increment,
            reason=reason,
        )

    def bounded_fov_zoom(
        self,
        *,
        camera_id: str,
        current_timestamp: float,
        horizontal_fov_deg: float | None = None,
        zoom_ratio: float | None = None,
        reason: str = "bounded_fov_zoom",
    ) -> ActiveVisionAction:
        fov = (
            None
            if horizontal_fov_deg is None
            else float(
                np.clip(
                    horizontal_fov_deg,
                    self.config.minimum_horizontal_fov_deg,
                    self.config.maximum_horizontal_fov_deg,
                )
            )
        )
        zoom = (
            None
            if zoom_ratio is None
            else float(
                np.clip(
                    zoom_ratio,
                    self.config.minimum_zoom_ratio,
                    self.config.maximum_zoom_ratio,
                )
            )
        )
        return ActiveVisionAction(
            action_type=ActiveVisionActionType.SET_FOV_ZOOM,
            camera_id=camera_id,
            issued_timestamp=current_timestamp,
            horizontal_fov_deg=fov,
            zoom_ratio=zoom,
            reason=reason,
        )

    def _next_scan_action(
        self,
        camera_id: str,
        timestamp: float,
        *,
        reason: str,
    ) -> ActiveVisionAction:
        index = self._next_sector_by_camera.get(camera_id, 0)
        sector = self.config.scan_sectors_deg[index % len(self.config.scan_sectors_deg)]
        self._next_sector_by_camera[camera_id] = index + 1
        return ActiveVisionAction(
            action_type=ActiveVisionActionType.SEARCH_SECTOR,
            camera_id=camera_id,
            issued_timestamp=timestamp,
            search_sector_deg=sector,
            reason=reason,
        )


def run_active_vision_step(
    environment: ActiveVisionEnvironment,
    policy: ActiveVisionPolicy,
    *,
    camera_id: str,
    current_timestamp: float,
    center_owned_global_track_ids: Sequence[str],
    safety_config: ActiveVisionSafetyConfig | None = None,
) -> tuple[ActiveVisionAction, ActiveVisionObservation]:
    """Execute one camera-only environment/policy interaction."""

    observation = environment.observe(camera_id)
    action = policy.select_action(
        observation,
        current_timestamp=current_timestamp,
        center_owned_global_track_ids=center_owned_global_track_ids,
    )
    validate_active_vision_action(
        action,
        center_owned_global_track_ids=center_owned_global_track_ids,
        safety_config=safety_config,
    )
    next_observation = environment.apply_camera_action(action)
    return action, next_observation


def validate_active_vision_action(
    action: ActiveVisionAction,
    *,
    center_owned_global_track_ids: Sequence[str],
    safety_config: ActiveVisionSafetyConfig | None = None,
) -> None:
    """Fail closed on custom-policy output before an environment executes it."""

    config = safety_config or ActiveVisionSafetyConfig()
    if action.action_type not in set(ActiveVisionActionType):
        raise ValueError("policy emitted an unsupported active-vision action")
    allowed_ids = {str(value) for value in center_owned_global_track_ids if str(value)}
    if (
        action.action_type is ActiveVisionActionType.OBSERVE_TARGET
        and action.target_global_track_id not in allowed_ids
    ):
        raise ValueError("observe_target does not reference a current center-owned track")
    if action.action_type is ActiveVisionActionType.GIMBAL_INCREMENT:
        assert action.gimbal_increment_deg is not None
        if max(abs(value) for value in action.gimbal_increment_deg) > config.max_gimbal_increment_deg:
            raise ValueError("gimbal increment exceeds the active-vision safety envelope")
    if action.action_type is ActiveVisionActionType.SET_FOV_ZOOM:
        if action.horizontal_fov_deg is not None and not (
            config.minimum_horizontal_fov_deg
            <= action.horizontal_fov_deg
            <= config.maximum_horizontal_fov_deg
        ):
            raise ValueError("horizontal FOV exceeds the active-vision safety envelope")
        if action.zoom_ratio is not None and not (
            config.minimum_zoom_ratio <= action.zoom_ratio <= config.maximum_zoom_ratio
        ):
            raise ValueError("zoom ratio exceeds the active-vision safety envelope")


def _search_sector(values: Sequence[float] | None) -> tuple[float, float, float, float]:
    if values is None:
        raise ValueError("search_sector_deg is required")
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (4,) or not np.all(np.isfinite(array)):
        raise ValueError("search sector must contain four finite values")
    yaw_min, yaw_max, pitch_min, pitch_max = array.tolist()
    if yaw_min >= yaw_max or pitch_min >= pitch_max:
        raise ValueError("search sector bounds must be increasing")
    if yaw_min < -180.0 or yaw_max > 180.0 or pitch_min < -90.0 or pitch_max > 90.0:
        raise ValueError("search sector exceeds physical angular bounds")
    return (float(yaw_min), float(yaw_max), float(pitch_min), float(pitch_max))


def _finite_pair(values: Sequence[float] | None, name: str) -> tuple[float, float]:
    if values is None:
        raise ValueError(f"{name} is required")
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (2,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain two finite values")
    return (float(array[0]), float(array[1]))


def _require_absent(*values: object | None) -> None:
    if any(value is not None for value in values):
        raise ValueError("active-vision action contains fields outside its action type")


__all__ = [
    "ActiveVisionAction",
    "ActiveVisionActionType",
    "ActiveVisionEnvironment",
    "ActiveVisionObservation",
    "ActiveVisionPolicy",
    "ActiveVisionSafetyConfig",
    "SafeRuleScanPolicy",
    "run_active_vision_step",
    "validate_active_vision_action",
]
