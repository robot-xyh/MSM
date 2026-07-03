"""Offline multi-sensor fusion research module.

The package is intentionally limited to simulation and offline evaluation. It
does not provide real vehicle control, fire-control, or automatic action APIs.
"""

from .airsim_dry_run import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)
from .fusion import FusionAdapter
from .observations import RadarCovarianceConfig
from .replay import (
    read_blocks_sensor_observations_jsonl,
    replay_blocks_sensor_observations_jsonl,
    sensor_observation_from_jsonl_record,
)
from .types import GlobalTrack, SensorObservation, TrackLevel, TrackUncertaintySummary

__all__ = [
    "FusionAdapter",
    "GlobalTrack",
    "RadarCovarianceConfig",
    "SensorObservation",
    "TrackLevel",
    "TrackUncertaintySummary",
    "make_minimal_airsim_dry_run_fixture",
    "observations_from_airsim_dry_run_fixture",
    "read_blocks_sensor_observations_jsonl",
    "replay_blocks_sensor_observations_jsonl",
    "sensor_observation_from_jsonl_record",
]
