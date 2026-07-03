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
    CommunicationSummary,
    ConfidenceBand,
    LinkType,
    NodeRole,
    PayloadKind,
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
    "CommunicationSummary",
    "ConfidenceBand",
    "DegradationAction",
    "DegradationMode",
    "FailoverCoordinator",
    "LinkType",
    "NodeRole",
    "PayloadKind",
    "ResourceSummary",
    "TerminalAssociationSummary",
    "TerminalDecisionState",
    "TrackSummary",
    "TrackUncertaintySummary",
]
