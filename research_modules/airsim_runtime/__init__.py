"""Real AirSim Blocks smoke runtime.

This package is limited to simulator smoke checks, offline replay, and explicit
AirSim-only SimpleFlight control episodes. 2v2 target motion is represented by
non-vehicle actor pose scripting.
"""

from .blocks import BlocksProcessManager
from .episode_bus import MainAirSimEpisodeBus, MainEpisodeBusResult, run_main_episode_bus
from .intercept import InterceptRunResult, run_controlled_intercept_episode
from .long_range_3d_reporting import (
    TrajectorySeries,
    build_trajectory_summary,
    load_actor_trajectories,
    load_association_event_positions,
    load_interceptor_trajectory,
    write_long_range_3d_trajectory_figures,
)
from .long_range_cv_scan import (
    LongRangeCVScenario,
    LongRangeCampaignResult,
    SUPPORTED_GEOMETRY_PROFILES,
    VelocityAwareAnonymousTracker,
    build_serpentine_scan_grid,
    derive_pitch_search_plan,
    crossing_geometry_preflight,
    evaluate_mot_continuity,
    pixel_to_world_unit_ray,
    world_ray_velocity_to_pixel_rate,
    run_long_range_cv_campaign,
    snapshot_frame_indices,
    write_long_range_cv_settings,
)
from .long_range_mot_reaudit import (
    camera_info_from_gimbal_record,
    reaudit_long_range_campaign,
    reaudit_long_range_profile_rows,
)
from .models import (
    BlocksActorTargetSpec,
    BlocksSmokeConfig,
    default_2v2_actor_target_specs,
    default_actor_target_specs,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_d4d5_stress_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
    default_cv_camera_vehicle_names,
    default_cv_secondary_vehicle_names,
    default_interceptor_vehicle_names,
    write_dynamic_computer_vision_settings,
    write_dynamic_multirotor_settings,
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
    "LongRangeCVScenario",
    "LongRangeCampaignResult",
    "TrajectorySeries",
    "SUPPORTED_GEOMETRY_PROFILES",
    "MainAirSimEpisodeBus",
    "MainEpisodeBusResult",
    "RealAirSimRuntimeClient",
    "VelocityAwareAnonymousTracker",
    "build_serpentine_scan_grid",
    "build_trajectory_summary",
    "camera_info_from_gimbal_record",
    "derive_pitch_search_plan",
    "crossing_geometry_preflight",
    "evaluate_mot_continuity",
    "load_actor_trajectories",
    "load_association_event_positions",
    "load_interceptor_trajectory",
    "pixel_to_world_unit_ray",
    "world_ray_velocity_to_pixel_rate",
    "reaudit_long_range_campaign",
    "reaudit_long_range_profile_rows",
    "default_2v2_actor_target_specs",
    "default_actor_target_specs",
    "default_cv_5v5_actor_target_specs",
    "default_cv_5v5_d4d5_stress_actor_target_specs",
    "default_cv_5v5_camera_vehicle_names",
    "default_cv_5v5_secondary_vehicle_names",
    "default_cv_camera_vehicle_names",
    "default_cv_secondary_vehicle_names",
    "default_interceptor_vehicle_names",
    "write_dynamic_computer_vision_settings",
    "write_dynamic_multirotor_settings",
    "run_controlled_intercept_episode",
    "run_long_range_cv_campaign",
    "run_main_episode_bus",
    "run_blocks_sequence",
    "run_blocks_smoke",
    "snapshot_frame_indices",
    "write_long_range_cv_settings",
    "write_long_range_3d_trajectory_figures",
]
