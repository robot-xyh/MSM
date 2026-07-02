"""Offline distributed fallback simulation package for D4."""

from .active_degradation import (
    ActiveDegradationArbiter,
    ActiveDegradationConfig,
    ActiveDegradationDecision,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    DegradationAction,
    DegradationMode,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
)
from .cbba import CBBANegotiator
from .coordinator import FailoverCoordinator
from .models import (
    Assignment,
    AvailabilityBand,
    C2Health,
    CommBand,
    ConfidenceBand,
    NodeRole,
    ResourceSummary,
    TrackSummary,
)

__all__ = [
    "ActiveDegradationArbiter",
    "ActiveDegradationConfig",
    "ActiveDegradationDecision",
    "Assignment",
    "AssignmentValiditySummary",
    "AssociationRiskSummary",
    "AvailabilityBand",
    "C2Health",
    "CBBANegotiator",
    "CommBand",
    "ConfidenceBand",
    "DegradationAction",
    "DegradationMode",
    "FailoverCoordinator",
    "NodeRole",
    "ResourceSummary",
    "TerminalAssociationSummary",
    "TerminalDecisionState",
    "TrackSummary",
    "TrackUncertaintySummary",
]
