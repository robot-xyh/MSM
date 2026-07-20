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
    topic: str
    source: str
    schema_version: str
    payload: Any


@dataclass(frozen=True)
class RuntimeStepInput:
    timestamp: float
    arrived_sensor_batches: tuple[OnlineSensorBatch, ...]
    interceptors: PlatformNavigationBatch
    recon: PlatformNavigationBatch


@dataclass(frozen=True)
class RuntimeStepOutput:
    interceptor_acceleration_ned: np.ndarray
    recon_acceleration_ned: np.ndarray
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
        return self


class ScalableModuleStack(Protocol):
    """Interface implemented by the main-owned D1-D7 composition adapter."""

    def reset(self, config: ScenarioConfig) -> None:
        ...

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        ...
