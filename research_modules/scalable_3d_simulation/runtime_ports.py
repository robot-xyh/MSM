"""Truth-free runtime ports used by main to connect D1-D7 module adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from .models import OnlineSensorBatch, ScenarioConfig


@dataclass(frozen=True)
class PlatformNavigationBatch:
    """Own-platform navigation state that may be provided to online control modules."""

    platform_kind: str
    platform_ids: tuple[str, ...]
    timestamp: float
    state_ned: np.ndarray
    covariance: np.ndarray
    active: np.ndarray

    def __post_init__(self) -> None:
        count = len(self.platform_ids)
        state = np.asarray(self.state_ned, dtype=float)
        covariance = np.asarray(self.covariance, dtype=float)
        active = np.asarray(self.active, dtype=bool).reshape(-1)
        if state.shape != (count, 6):
            raise ValueError("state_ned must have shape (platform_count, 6)")
        if covariance.shape != (count, 6, 6):
            raise ValueError("covariance must have shape (platform_count, 6, 6)")
        if active.shape != (count,):
            raise ValueError("active must have shape (platform_count,)")
        if not np.all(np.isfinite(state)) or not np.all(np.isfinite(covariance)):
            raise ValueError("platform navigation state and covariance must be finite")
        state = state.copy()
        covariance = covariance.copy()
        active = active.copy()
        state.setflags(write=False)
        covariance.setflags(write=False)
        active.setflags(write=False)
        object.__setattr__(self, "state_ned", state)
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "active", active)


@dataclass(frozen=True)
class RuntimePublication:
    """One online publication; zero-copy requires producer ownership transfer."""

    topic: str
    source: str
    schema_version: str
    payload: Any
    copy_payload: bool = True


@dataclass(frozen=True)
class CameraRuntimeState:
    """Applied camera state returned by main to the active-vision scheduler."""

    camera_id: str
    resource_id: str
    platform_kind: str
    timestamp: float
    yaw_deg: float
    pitch_deg: float
    horizontal_fov_deg: float
    fov_mode: str = "wide"
    last_plan_version: int = 0
    last_coalition_version: int = 0
    last_communication_version: int = 0

    def __post_init__(self) -> None:
        for name in ("camera_id", "resource_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        platform_kind = str(self.platform_kind).strip().lower()
        if platform_kind not in {"interceptor", "recon"}:
            raise ValueError("camera platform_kind must be interceptor or recon")
        object.__setattr__(self, "platform_kind", platform_kind)
        for name in ("timestamp", "yaw_deg", "pitch_deg", "horizontal_fov_deg"):
            value = float(getattr(self, name))
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if not -180.0 <= self.yaw_deg <= 180.0:
            raise ValueError("camera yaw must be within [-180, 180] degrees")
        if not -89.9 <= self.pitch_deg <= 89.9:
            raise ValueError("camera pitch must be within [-89.9, 89.9] degrees")
        if not 1.0 < self.horizontal_fov_deg < 179.0:
            raise ValueError("camera horizontal FOV must be within (1, 179) degrees")
        fov_mode = str(self.fov_mode).strip().lower()
        if fov_mode not in {"wide", "zoom"}:
            raise ValueError("camera fov_mode must be wide or zoom")
        object.__setattr__(self, "fov_mode", fov_mode)
        for name in (
            "last_plan_version",
            "last_coalition_version",
            "last_communication_version",
        ):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class CameraObservationCommand:
    """Versioned camera-only command emitted by D5 through main glue.

    The command carries an absolute NED look point and FOV.  It cannot assign a
    resource or create a global identity; ``target_global_track_id`` is only a
    read-only reference to a D2-owned candidate.
    """

    camera_id: str
    resource_id: str
    issued_timestamp: float
    expires_timestamp: float
    plan_version: int
    coalition_version: int
    communication_version: int
    intent: str
    aim_point_ned: np.ndarray
    horizontal_fov_deg: float
    fov_mode: str
    target_global_track_id: str | None = None
    requested_mode: str = "disabled"
    effective_mode: str = "disabled"
    reason: str = "rule"

    def __post_init__(self) -> None:
        for name in ("camera_id", "resource_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        issued = float(self.issued_timestamp)
        expires = float(self.expires_timestamp)
        if not np.isfinite(issued) or not np.isfinite(expires) or expires <= issued:
            raise ValueError("camera command timestamps must be finite with positive lifetime")
        object.__setattr__(self, "issued_timestamp", issued)
        object.__setattr__(self, "expires_timestamp", expires)
        for name in ("plan_version", "coalition_version", "communication_version"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        intent = str(self.intent).strip().lower()
        if intent not in {"observe_target", "search_sector", "hold", "reacquire"}:
            raise ValueError("camera command intent is invalid")
        object.__setattr__(self, "intent", intent)
        point = np.asarray(self.aim_point_ned, dtype=float).reshape(-1)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            raise ValueError("camera command aim_point_ned must be a finite 3-vector")
        point = point.copy()
        point.setflags(write=False)
        object.__setattr__(self, "aim_point_ned", point)
        fov = float(self.horizontal_fov_deg)
        if not np.isfinite(fov) or not 1.0 < fov < 179.0:
            raise ValueError("camera command horizontal FOV must be within (1, 179) degrees")
        object.__setattr__(self, "horizontal_fov_deg", fov)
        fov_mode = str(self.fov_mode).strip().lower()
        if fov_mode not in {"wide", "zoom"}:
            raise ValueError("camera command fov_mode must be wide or zoom")
        object.__setattr__(self, "fov_mode", fov_mode)
        target_id = (
            None
            if self.target_global_track_id is None
            else str(self.target_global_track_id).strip()
        )
        if self.target_global_track_id is not None and not target_id:
            raise ValueError("target_global_track_id must be non-empty when present")
        if intent in {"observe_target", "reacquire"} and target_id is None:
            raise ValueError("target camera command requires a center-owned track reference")
        if intent in {"search_sector", "hold"} and target_id is not None:
            raise ValueError("search/hold camera command cannot carry a target reference")
        object.__setattr__(self, "target_global_track_id", target_id)
        for name in ("requested_mode", "effective_mode"):
            value = str(getattr(self, name)).strip().lower()
            if value not in {"disabled", "shadow", "assist"}:
                raise ValueError(f"{name} must be disabled, shadow, or assist")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "reason", str(self.reason or "rule"))


@dataclass(frozen=True)
class RuntimeStepInput:
    timestamp: float
    arrived_sensor_batches: tuple[OnlineSensorBatch, ...]
    interceptors: PlatformNavigationBatch
    recon: PlatformNavigationBatch
    cameras: tuple[CameraRuntimeState, ...] = ()


@dataclass(frozen=True)
class RuntimeStepOutput:
    interceptor_acceleration_ned: np.ndarray
    recon_acceleration_ned: np.ndarray
    camera_commands: tuple[CameraObservationCommand, ...] = ()
    publications: tuple[RuntimePublication, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def validated(
        self,
        *,
        resource_count: int,
        recon_count: int,
    ) -> "RuntimeStepOutput":
        interceptor = np.asarray(self.interceptor_acceleration_ned, dtype=float)
        recon = np.asarray(self.recon_acceleration_ned, dtype=float)
        if interceptor.shape != (resource_count, 3):
            raise ValueError(
                f"interceptor acceleration must have shape ({resource_count}, 3)"
            )
        if recon.shape != (recon_count, 3):
            raise ValueError(f"recon acceleration must have shape ({recon_count}, 3)")
        if not np.all(np.isfinite(interceptor)) or not np.all(np.isfinite(recon)):
            raise ValueError("runtime acceleration commands must be finite")
        commands = tuple(self.camera_commands)
        if len(commands) > resource_count + recon_count:
            raise ValueError("camera command count exceeds configured camera count")
        camera_ids = tuple(command.camera_id for command in commands)
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError("runtime output contains duplicate camera commands")
        return self


class ScalableModuleStack(Protocol):
    """Interface implemented by the main-owned D1-D7 composition adapter."""

    def reset(self, config: ScenarioConfig) -> None:
        ...

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        ...
