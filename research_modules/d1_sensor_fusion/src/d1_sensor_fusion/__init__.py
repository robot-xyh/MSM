"""Offline multi-sensor fusion research module.

The package is intentionally limited to simulation and offline evaluation. It
does not provide real vehicle control, fire-control, or automatic action APIs.
"""

from .airsim_dry_run import (
    AIRSIM_DRY_RUN_FIXTURE_SCHEMA_VERSION,
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)
from .fusion import FusionAdapter
from .observations import RadarCovarianceConfig
from .quality import annotate_covariance_growth_rates, summarize_region_quality_windows
from .recon_cue import summarize_recon_cue_from_tracks
from .replay import (
    REPLAY_SCHEMA_VERSION,
    read_blocks_sensor_observations_jsonl,
    read_sensor_observations_csv,
    read_sensor_observations_jsonl,
    replay_blocks_sensor_observations_jsonl,
    replay_sensor_observations_csv,
    replay_sensor_observations_jsonl,
    sensor_observation_from_csv_row,
    sensor_observation_from_jsonl_record,
    summarize_sensor_observation_latency_audit,
)
from .types import (
    FusionQualityRegionSummary,
    FusionQualityRegionWindowSummary,
    GlobalTrack,
    LatencyAuditSummary,
    ReconCueSummary,
    SensorHealthSummary,
    SensorObservation,
    TrackLevel,
    TrackUncertaintySummary,
)

__all__ = [
    "AIRSIM_DRY_RUN_FIXTURE_SCHEMA_VERSION",
    "FusionAdapter",
    "FusionQualityRegionSummary",
    "FusionQualityRegionWindowSummary",
    "GlobalTrack",
    "LatencyAuditSummary",
    "REPLAY_SCHEMA_VERSION",
    "RadarCovarianceConfig",
    "ReconCueSummary",
    "SensorHealthSummary",
    "SensorObservation",
    "TrackLevel",
    "TrackUncertaintySummary",
    "annotate_covariance_growth_rates",
    "make_minimal_airsim_dry_run_fixture",
    "observations_from_airsim_dry_run_fixture",
    "read_blocks_sensor_observations_jsonl",
    "read_sensor_observations_csv",
    "read_sensor_observations_jsonl",
    "replay_blocks_sensor_observations_jsonl",
    "replay_sensor_observations_csv",
    "replay_sensor_observations_jsonl",
    "sensor_observation_from_csv_row",
    "sensor_observation_from_jsonl_record",
    "summarize_region_quality_windows",
    "summarize_sensor_observation_latency_audit",
    "summarize_recon_cue_from_tracks",
]
