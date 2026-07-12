"""Optional external-framework adapters kept outside D2's default path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
from typing import Any

import numpy as np

from .models import Detection, GlobalTrack


class OptionalIntegrationUnavailable(RuntimeError):
    """Raised when a requested optional framework cannot be imported."""


@dataclass(frozen=True, slots=True)
class OptionalDependencyStatus:
    name: str
    available: bool
    purpose: str
    version: str | None = None
    reason: str | None = None
    integration_level: str = "adapter_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "reason": self.reason,
            "purpose": self.purpose,
            "integration_level": self.integration_level,
        }


_DEPENDENCIES = {
    "filterpy": {
        "purpose": "Optional CV Kalman object adapter and update smoke benchmark.",
        "distribution": "filterpy",
    },
    "stonesoup": {
        "purpose": "Optional Detection object adapter smoke benchmark.",
        "distribution": "stonesoup",
    },
}


def optional_dependency_status() -> list[OptionalDependencyStatus]:
    return [probe_optional_dependency(name) for name in _DEPENDENCIES]


def probe_optional_dependency(name: str) -> OptionalDependencyStatus:
    normalized = str(name).lower()
    if normalized not in _DEPENDENCIES:
        raise ValueError(f"unsupported optional dependency: {name!r}")
    definition = _DEPENDENCIES[normalized]
    spec = _find_spec(normalized)
    if spec is None:
        return OptionalDependencyStatus(
            name=normalized,
            available=False,
            purpose=definition["purpose"],
            reason=(
                f"{normalized} is not installed in the active Python environment; "
                "install it only in an isolated research environment"
            ),
        )
    try:
        version = importlib.metadata.version(definition["distribution"])
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return OptionalDependencyStatus(
        name=normalized,
        available=True,
        purpose=definition["purpose"],
        version=version,
        reason=None,
    )


def to_stonesoup_detection(detection: Detection) -> object:
    """Map one online-safe D2 detection to a Stone Soup Detection object."""

    status = probe_optional_dependency("stonesoup")
    if not status.available:
        raise OptionalIntegrationUnavailable(status.reason or "stonesoup unavailable")
    try:
        from stonesoup.types.detection import Detection as StoneSoupDetection
        from stonesoup.types.state import StateVector
    except (ImportError, AttributeError) as exc:
        raise OptionalIntegrationUnavailable(
            f"Stone Soup adapter API is unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    timestamp = datetime.fromtimestamp(float(detection.timestamp), tz=timezone.utc)
    return StoneSoupDetection(
        StateVector(np.asarray(detection.position, dtype=float).reshape(-1, 1)),
        timestamp=timestamp,
        metadata=_online_safe_metadata(detection.metadata),
    )


def to_filterpy_state(
    track: GlobalTrack,
    *,
    dt: float = 1.0,
    measurement_variance: float = 1.0,
) -> object:
    """Map one D2 CV track to a FilterPy KalmanFilter object."""

    status = probe_optional_dependency("filterpy")
    if not status.available:
        raise OptionalIntegrationUnavailable(status.reason or "filterpy unavailable")
    return _build_filterpy_filter(
        state=np.asarray(track.state, dtype=float),
        covariance=np.asarray(track.covariance, dtype=float),
        dt=dt,
        measurement_variance=measurement_variance,
    )


def filterpy_filter_from_detection(
    detection: Detection,
    *,
    dt: float = 1.0,
) -> object:
    """Create a FilterPy CV filter initialized from one D2 detection."""

    status = probe_optional_dependency("filterpy")
    if not status.available:
        raise OptionalIntegrationUnavailable(status.reason or "filterpy unavailable")
    position = np.asarray(detection.position, dtype=float).reshape(2)
    state = np.array([position[0], position[1], 0.0, 0.0], dtype=float)
    covariance = np.zeros((4, 4), dtype=float)
    covariance[:2, :2] = np.asarray(detection.covariance, dtype=float)
    covariance[2:, 2:] = np.eye(2, dtype=float) * 25.0
    measurement_variance = float(np.mean(np.diag(detection.covariance)))
    return _build_filterpy_filter(
        state=state,
        covariance=covariance,
        dt=dt,
        measurement_variance=max(measurement_variance, np.finfo(float).eps),
    )


def _build_filterpy_filter(
    *,
    state: np.ndarray,
    covariance: np.ndarray,
    dt: float,
    measurement_variance: float,
) -> object:
    try:
        from filterpy.kalman import KalmanFilter
    except (ImportError, AttributeError) as exc:
        raise OptionalIntegrationUnavailable(
            f"FilterPy adapter API is unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    delta_t = float(dt)
    if not np.isfinite(delta_t) or delta_t <= 0.0:
        raise ValueError("dt must be positive and finite")
    filter_object = KalmanFilter(dim_x=4, dim_z=2)
    filter_object.x = np.asarray(state, dtype=float).reshape(4, 1)
    filter_object.P = np.asarray(covariance, dtype=float).reshape(4, 4).copy()
    filter_object.F = np.array(
        [
            [1.0, 0.0, delta_t, 0.0],
            [0.0, 1.0, 0.0, delta_t],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    filter_object.H = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
        dtype=float,
    )
    filter_object.Q = np.eye(4, dtype=float) * 0.01
    filter_object.R = np.eye(2, dtype=float) * float(measurement_variance)
    return filter_object


def _online_safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    forbidden = ("truth", "ground_truth", "actor_name", "sim_truth")
    return {
        str(key): _online_safe_value(value)
        for key, value in metadata.items()
        if not any(token in str(key).lower() for token in forbidden)
    }


def _online_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _online_safe_metadata(value)
    if isinstance(value, list):
        return [_online_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_online_safe_value(item) for item in value)
    return value


def _find_spec(name: str) -> object | None:
    return importlib.util.find_spec(name)
