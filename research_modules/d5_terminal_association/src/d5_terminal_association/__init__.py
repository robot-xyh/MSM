"""Terminal visual association research module.

The package only performs offline/simulation association decisions. It never
rewrites center-owned global track identifiers.
"""

from .associator import AssociationConfig, TerminalAssociator
from .airsim_cv_adapter import (
    AirSimCVScenarioSpec,
    TerminalEvidenceSummary,
    TerminalStressMetrics,
    compute_terminal_stress_metrics,
    local_visual_tracks_from_sim_detections,
    publish_sim_detections_as_local_observations,
    summarize_degradation_case,
)
from .identity import IdentityChecker
from .models import (
    Assignment,
    CameraModel,
    CostBreakdown,
    CostMatrixResult,
    CrossViewAssociation,
    GlobalTrack,
    IdentityClaim,
    LocalVisualTrack,
    ProjectionResult,
    ReconImageCue,
    TerminalAssociation,
    TerminalObservation,
)
from .observation_bus import TerminalObservationBus

__all__ = [
    "AssociationConfig",
    "AirSimCVScenarioSpec",
    "Assignment",
    "CameraModel",
    "CostBreakdown",
    "CostMatrixResult",
    "CrossViewAssociation",
    "GlobalTrack",
    "IdentityChecker",
    "IdentityClaim",
    "LocalVisualTrack",
    "ProjectionResult",
    "ReconImageCue",
    "TerminalAssociation",
    "TerminalAssociator",
    "TerminalEvidenceSummary",
    "TerminalObservation",
    "TerminalObservationBus",
    "TerminalStressMetrics",
    "compute_terminal_stress_metrics",
    "local_visual_tracks_from_sim_detections",
    "publish_sim_detections_as_local_observations",
    "summarize_degradation_case",
]
