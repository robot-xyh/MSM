"""D3 centralized rolling assignment planner.

This package is for offline research simulation and human-review candidate
planning only. It intentionally excludes real fire-control parameters, damage
logic, hardware drivers, autonomous disposition, and authorization bypasses.
"""

from .costs import CostMatrixResult, CostModel
from .airsim_dry_run_adapter import (
    AirSimDryRunAssignmentAdapter,
    adapt_airsim_global_tracks,
    adapt_airsim_resource_states,
)
from .models import (
    Assignment,
    AssignmentPlan,
    CostWeights,
    PlannerConfig,
    ResourceState,
    SolverResult,
    TargetTrack,
)
from .planner import AssignmentPlanner, StalePlanError
from .solver import FallbackAssignmentSolver, HungarianAssignmentSolver

__all__ = [
    "Assignment",
    "AssignmentPlan",
    "AssignmentPlanner",
    "AirSimDryRunAssignmentAdapter",
    "CostMatrixResult",
    "CostModel",
    "CostWeights",
    "FallbackAssignmentSolver",
    "HungarianAssignmentSolver",
    "PlannerConfig",
    "ResourceState",
    "SolverResult",
    "StalePlanError",
    "TargetTrack",
    "adapt_airsim_global_tracks",
    "adapt_airsim_resource_states",
]
