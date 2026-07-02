"""Offline multi-sensor fusion research module.

The package is intentionally limited to simulation and offline evaluation. It
does not provide real vehicle control, fire-control, or automatic action APIs.
"""

from .airsim_dry_run import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)
from .fusion import FusionAdapter
from .types import GlobalTrack, SensorObservation, TrackLevel

__all__ = [
    "FusionAdapter",
    "GlobalTrack",
    "SensorObservation",
    "TrackLevel",
    "make_minimal_airsim_dry_run_fixture",
    "observations_from_airsim_dry_run_fixture",
]
