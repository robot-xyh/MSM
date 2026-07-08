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
    ASSIGNMENT_PLAN_SCHEMA_V1,
    Assignment,
    AssignmentFeedbackDecision,
    AssignmentGuidanceBinding,
    AssignmentPlan,
    AssignmentRecord,
    AssignmentValiditySummary,
    CostWeights,
    PlannerConfig,
    ResourceState,
    SECONDARY_PLAN_SCHEMA_V2,
    SolverResult,
    TargetTrack,
    TerminalFeedbackWriteback,
    apply_terminal_feedback_to_planner_inputs,
    assignment_records_from_plan,
    assignment_validity_summary_from_plan,
    evaluate_terminal_feedback,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)
from .planner import AssignmentPlanner, StalePlanError
from .solver import FallbackAssignmentSolver, HungarianAssignmentSolver

__all__ = [
    "Assignment",
    "ASSIGNMENT_PLAN_SCHEMA_V1",
    "AssignmentFeedbackDecision",
    "AssignmentGuidanceBinding",
    "AssignmentPlan",
    "AssignmentPlanner",
    "AssignmentRecord",
    "AssignmentValiditySummary",
    "AirSimDryRunAssignmentAdapter",
    "CostMatrixResult",
    "CostModel",
    "CostWeights",
    "FallbackAssignmentSolver",
    "HungarianAssignmentSolver",
    "PlannerConfig",
    "ResourceState",
    "SECONDARY_PLAN_SCHEMA_V2",
    "SolverResult",
    "StalePlanError",
    "TargetTrack",
    "TerminalFeedbackWriteback",
    "adapt_airsim_global_tracks",
    "adapt_airsim_resource_states",
    "apply_terminal_feedback_to_planner_inputs",
    "assignment_records_from_plan",
    "assignment_validity_summary_from_plan",
    "evaluate_terminal_feedback",
    "guidance_bindings_from_assignment_plan",
    "prepare_secondary_takeover_plan",
]
