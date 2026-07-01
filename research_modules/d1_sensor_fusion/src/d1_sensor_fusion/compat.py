from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from .types import GlobalTrack, SensorObservation


@dataclass
class StoneSoupAdapterPlaceholder:
    """Non-importing placeholder for a future Stone Soup bridge.

    Stone Soup is not required for the current fallback implementation. This
    class keeps the boundary explicit so tests do not fail on hosts where the
    optional package is absent.
    """

    available: bool = importlib.util.find_spec("stonesoup") is not None

    def to_detection_dict(self, observation: SensorObservation) -> dict:
        return {
            "id": observation.observation_id,
            "timestamp": observation.measurement_timestamp,
            "modality": observation.modality,
            "measurement": observation.measurement.copy(),
            "covariance": None
            if observation.covariance is None
            else observation.covariance.copy(),
            "metadata": dict(observation.metadata),
        }

    def from_track_dict(self, payload: dict) -> GlobalTrack:
        raise NotImplementedError(
            "Stone Soup conversion is a future integration point; the current "
            "module uses the NumPy/SciPy fallback and does not import stonesoup."
        )


@dataclass
class FilterPyBackendPlaceholder:
    """Optional-backend marker without importing FilterPy."""

    available: bool = importlib.util.find_spec("filterpy") is not None

    def describe(self) -> str:
        if self.available:
            return "FilterPy is installed and can be evaluated as an optional EKF backend."
        return "FilterPy is not installed; NumPy EKF fallback is active."
