"""D7 offline proportional guidance research module."""

from .airsim_dry_run import (
    AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
    guidance_records_from_airsim_dry_run_fixture,
    guidance_records_from_airsim_phase1_dry_run,
    guidance_records_from_assignment_dry_run,
    make_minimal_airsim_dry_run_fixture,
)
from .comparison import (
    DEFAULT_COMPARISON_STRATEGIES,
    GuidanceStrategyComparisonRow,
    run_guidance_strategy_comparison,
    summarize_guidance_strategy_comparison,
)
from .models import (
    GuidanceCommand,
    GuidanceConfig,
    GuidanceMode,
    GuidanceRecord,
    GuidanceState,
)
from .pn import (
    compute_pn_command,
    compute_proportional_navigation_command,
    compute_pure_pursuit_command,
)
from .replay import (
    BBOX_LOS_REPLAY_BOUNDARY,
    bbox_replay_detection_to_observation,
    evaluate_bbox_los_replay,
    vision_observations_from_bbox_replay,
)
from .runtime_bus import (
    D7_RUNTIME_BUS_BOUNDARY,
    D7RuntimeBus,
    D7RuntimePairInput,
    D7RuntimePairOutput,
    coerce_vision_guidance_observation,
    summarize_runtime_bus_outputs,
)
from .simulator import simulate_guidance_episode, summarize_guidance_records
from .terminal_gate import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    TerminalPngContractDecision,
    coerce_assignment_guidance_binding,
    coerce_d4_guidance_permission,
    evaluate_terminal_png_contract,
    guidance_mode_from_terminal_contract,
)
from .vision_png import (
    PngGuidanceCommand,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    VisionGuidanceQuality,
    summarize_terminal_switch_quality,
    terminal_switch_allowed_rate,
)

__all__ = [
    "AIRSIM_PHASE1_DRY_RUN_BOUNDARY",
    "AssignmentGuidanceBinding",
    "BBOX_LOS_REPLAY_BOUNDARY",
    "D7_RUNTIME_BUS_BOUNDARY",
    "D7RuntimeBus",
    "D7RuntimePairInput",
    "D7RuntimePairOutput",
    "D4GuidancePermission",
    "DEFAULT_COMPARISON_STRATEGIES",
    "GuidanceCommand",
    "GuidanceConfig",
    "GuidanceMode",
    "GuidanceRecord",
    "GuidanceState",
    "GuidanceStrategyComparisonRow",
    "PngGuidanceCommand",
    "PngGuidanceConfig",
    "SimpleFlightPngGuidanceFilter",
    "TerminalPngContractDecision",
    "VisionGuidanceObservation",
    "VisionGuidanceQuality",
    "bbox_replay_detection_to_observation",
    "coerce_assignment_guidance_binding",
    "coerce_d4_guidance_permission",
    "coerce_vision_guidance_observation",
    "compute_pn_command",
    "compute_proportional_navigation_command",
    "compute_pure_pursuit_command",
    "evaluate_terminal_png_contract",
    "evaluate_bbox_los_replay",
    "guidance_mode_from_terminal_contract",
    "guidance_records_from_airsim_dry_run_fixture",
    "guidance_records_from_airsim_phase1_dry_run",
    "guidance_records_from_assignment_dry_run",
    "make_minimal_airsim_dry_run_fixture",
    "run_guidance_strategy_comparison",
    "simulate_guidance_episode",
    "summarize_guidance_records",
    "summarize_guidance_strategy_comparison",
    "summarize_runtime_bus_outputs",
    "summarize_terminal_switch_quality",
    "terminal_switch_allowed_rate",
    "vision_observations_from_bbox_replay",
]
