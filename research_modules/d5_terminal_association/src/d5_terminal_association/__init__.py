"""Terminal visual association research module.

The package only performs offline/simulation association decisions. It never
rewrites center-owned global track identifiers.
"""

from .associator import AssociationConfig, TerminalAssociator
from .identity import IdentityChecker
from .models import (
    Assignment,
    CameraModel,
    CostBreakdown,
    CostMatrixResult,
    GlobalTrack,
    IdentityClaim,
    LocalVisualTrack,
    ProjectionResult,
    ReconImageCue,
    TerminalAssociation,
)

__all__ = [
    "AssociationConfig",
    "Assignment",
    "CameraModel",
    "CostBreakdown",
    "CostMatrixResult",
    "GlobalTrack",
    "IdentityChecker",
    "IdentityClaim",
    "LocalVisualTrack",
    "ProjectionResult",
    "ReconImageCue",
    "TerminalAssociation",
    "TerminalAssociator",
]
