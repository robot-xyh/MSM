"""Optional compatibility helpers for external tracking frameworks.

The runnable module intentionally depends only on NumPy/SciPy. These helpers
report optional availability and provide explicit failure messages when a caller
tries to use an integration that is not installed.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from .models import Detection, GlobalTrack


class OptionalIntegrationUnavailable(RuntimeError):
    """Raised when an optional framework adapter is requested but unavailable."""


@dataclass(frozen=True, slots=True)
class OptionalDependencyStatus:
    name: str
    available: bool
    purpose: str


def optional_dependency_status() -> list[OptionalDependencyStatus]:
    return [
        OptionalDependencyStatus(
            name="filterpy",
            available=importlib.util.find_spec("filterpy") is not None,
            purpose="Future IMM/EKF/UKF prototype adapters.",
        ),
        OptionalDependencyStatus(
            name="stonesoup",
            available=importlib.util.find_spec("stonesoup") is not None,
            purpose="Future JPDA/MHT offline validation adapters.",
        ),
    ]


def to_stonesoup_detection(detection: Detection) -> object:
    if importlib.util.find_spec("stonesoup") is None:
        raise OptionalIntegrationUnavailable(
            "Stone Soup is not installed; use the NumPy/SciPy fallback or install "
            "Stone Soup in a separate research environment."
        )
    raise NotImplementedError(
        f"Stone Soup adapter placeholder for detection {detection.detection_id}"
    )


def to_filterpy_state(track: GlobalTrack) -> object:
    if importlib.util.find_spec("filterpy") is None:
        raise OptionalIntegrationUnavailable(
            "FilterPy is not installed; use Tracker's built-in constant-velocity "
            "Kalman fallback or install FilterPy in a separate research environment."
        )
    raise NotImplementedError(
        f"FilterPy adapter placeholder for track {track.global_track_id}"
    )
