"""Offline multi-sensor fusion research module.

The package is intentionally limited to simulation and offline evaluation. It
does not provide real vehicle control, fire-control, or automatic action APIs.
"""

from .fusion import FusionAdapter
from .types import GlobalTrack, SensorObservation, TrackLevel

__all__ = ["FusionAdapter", "GlobalTrack", "SensorObservation", "TrackLevel"]
