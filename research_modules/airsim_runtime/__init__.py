"""Real AirSim Blocks smoke runtime.

This package is limited to simulator smoke checks, offline replay, and explicit
AirSim-only SimpleFlight control episodes. 2v2 target motion is represented by
non-vehicle actor pose scripting.
"""

from .blocks import BlocksProcessManager
from .intercept import InterceptRunResult, run_controlled_intercept_episode
from .models import (
    BlocksActorTargetSpec,
    BlocksSmokeConfig,
    default_2v2_actor_target_specs,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_d4d5_stress_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
)
from .orchestrator import AirSimBlocksSmokeOrchestrator, run_blocks_smoke
from .real_runtime import RealAirSimRuntimeClient
from .sequence import AirSimBlocksSequenceOrchestrator, run_blocks_sequence

__all__ = [
    "AirSimBlocksSmokeOrchestrator",
    "AirSimBlocksSequenceOrchestrator",
    "BlocksActorTargetSpec",
    "BlocksProcessManager",
    "BlocksSmokeConfig",
    "InterceptRunResult",
    "RealAirSimRuntimeClient",
    "default_2v2_actor_target_specs",
    "default_cv_5v5_actor_target_specs",
    "default_cv_5v5_d4d5_stress_actor_target_specs",
    "default_cv_5v5_camera_vehicle_names",
    "default_cv_5v5_secondary_vehicle_names",
    "run_controlled_intercept_episode",
    "run_blocks_sequence",
    "run_blocks_smoke",
]
