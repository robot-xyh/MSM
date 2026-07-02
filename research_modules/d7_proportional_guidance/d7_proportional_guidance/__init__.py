"""D7 offline proportional guidance research module."""

from .airsim_dry_run import (
    AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
    guidance_records_from_airsim_dry_run_fixture,
    guidance_records_from_airsim_phase1_dry_run,
    guidance_records_from_assignment_dry_run,
    make_minimal_airsim_dry_run_fixture,
)
from .models import (
    GuidanceCommand,
    GuidanceConfig,
    GuidanceMode,
    GuidanceRecord,
    GuidanceState,
)
from .pn import compute_pn_command, compute_proportional_navigation_command
from .simulator import simulate_guidance_episode, summarize_guidance_records

__all__ = [
    "AIRSIM_PHASE1_DRY_RUN_BOUNDARY",
    "GuidanceCommand",
    "GuidanceConfig",
    "GuidanceMode",
    "GuidanceRecord",
    "GuidanceState",
    "compute_pn_command",
    "compute_proportional_navigation_command",
    "guidance_records_from_airsim_dry_run_fixture",
    "guidance_records_from_airsim_phase1_dry_run",
    "guidance_records_from_assignment_dry_run",
    "make_minimal_airsim_dry_run_fixture",
    "simulate_guidance_episode",
    "summarize_guidance_records",
]
