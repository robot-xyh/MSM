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
from .consistency import (
    TerminalConsistencyConfig,
    TerminalConsistencyTracker,
    candidate_cost_margin,
    summarize_terminal_consistency,
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
    TerminalConsistencySummary,
    TerminalObservation,
)
from .observation_bus import TerminalObservationBus
from .visual_handoff import (
    BBoxStability,
    VisualPngHandoffConfig,
    annotate_visual_png_handoff,
    bbox_area_stability,
    expected_bbox_area_ratio,
    range_band_for_handoff,
)

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
    "TerminalConsistencyConfig",
    "TerminalConsistencySummary",
    "TerminalConsistencyTracker",
    "TerminalAssociator",
    "TerminalEvidenceSummary",
    "TerminalObservation",
    "TerminalObservationBus",
    "TerminalStressMetrics",
    "BBoxStability",
    "VisualPngHandoffConfig",
    "annotate_visual_png_handoff",
    "bbox_area_stability",
    "compute_terminal_stress_metrics",
    "candidate_cost_margin",
    "expected_bbox_area_ratio",
    "local_visual_tracks_from_sim_detections",
    "publish_sim_detections_as_local_observations",
    "range_band_for_handoff",
    "summarize_degradation_case",
    "summarize_terminal_consistency",
]
