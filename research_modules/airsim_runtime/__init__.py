"""Real AirSim Blocks smoke runtime.

This package is limited to simulator smoke checks and offline replay into the
existing research modules. It does not arm, take off, move, or command vehicles;
2v2 target motion is represented by non-vehicle actor pose scripting.
"""

from .blocks import BlocksProcessManager
from .models import BlocksActorTargetSpec, BlocksSmokeConfig, default_2v2_actor_target_specs
from .orchestrator import AirSimBlocksSmokeOrchestrator, run_blocks_smoke
from .real_runtime import RealAirSimRuntimeClient
from .sequence import AirSimBlocksSequenceOrchestrator, run_blocks_sequence

__all__ = [
    "AirSimBlocksSmokeOrchestrator",
    "AirSimBlocksSequenceOrchestrator",
    "BlocksActorTargetSpec",
    "BlocksProcessManager",
    "BlocksSmokeConfig",
    "RealAirSimRuntimeClient",
    "default_2v2_actor_target_specs",
    "run_blocks_sequence",
    "run_blocks_smoke",
]
