"""Dependency-free AirSim dry-run contracts for offline interface testing.

The package provides fake frames and orchestration glue only. It never imports
the AirSim Python client, starts a simulator, or issues vehicle-control calls.
"""

from .adapters import observations_from_airsim_frame
from .models import (
    AirSimAdapterResult,
    AirSimCameraInfo,
    AirSimDetectionBox,
    AirSimEpisodeConfig,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)
from .orchestrator import AirSimDryRunOrchestrator, run_airsim_dry_run
from .runtime import AirSimRuntimeClient, FakeAirSimRuntimeClient

__all__ = [
    "AirSimAdapterResult",
    "AirSimCameraInfo",
    "AirSimDetectionBox",
    "AirSimDryRunOrchestrator",
    "AirSimEpisodeConfig",
    "AirSimFrame",
    "AirSimResourceState",
    "AirSimRuntimeClient",
    "AirSimTruthObject",
    "FakeAirSimRuntimeClient",
    "observations_from_airsim_frame",
    "run_airsim_dry_run",
]
