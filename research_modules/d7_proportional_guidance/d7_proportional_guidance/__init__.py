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
from .terminal_gate import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    TerminalPngContractDecision,
    coerce_assignment_guidance_binding,
    coerce_d4_guidance_permission,
    evaluate_terminal_png_contract,
)
from .vision_png import (
    PngGuidanceCommand,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    VisionGuidanceQuality,
)

__all__ = [
    "AIRSIM_PHASE1_DRY_RUN_BOUNDARY",
    "AssignmentGuidanceBinding",
    "D4GuidancePermission",
    "GuidanceCommand",
    "GuidanceConfig",
    "GuidanceMode",
    "GuidanceRecord",
    "GuidanceState",
    "PngGuidanceCommand",
    "PngGuidanceConfig",
    "SimpleFlightPngGuidanceFilter",
    "TerminalPngContractDecision",
    "VisionGuidanceObservation",
    "VisionGuidanceQuality",
    "coerce_assignment_guidance_binding",
    "coerce_d4_guidance_permission",
    "compute_pn_command",
    "compute_proportional_navigation_command",
    "evaluate_terminal_png_contract",
    "guidance_records_from_airsim_dry_run_fixture",
    "guidance_records_from_airsim_phase1_dry_run",
    "guidance_records_from_assignment_dry_run",
    "make_minimal_airsim_dry_run_fixture",
    "simulate_guidance_episode",
    "summarize_guidance_records",
]
