"""Shared contracts and deterministic fixtures for the campaign."""

from .contracts import (
    AssociationRecord,
    LocalVisualTrackRecord,
    SearchHandoverRecord,
    SourceCueRecord,
    SourceCueTruthLabel,
)
from .recognition import bbox_longest_side_px, is_recognizable_bbox
from .scenario import CampaignScenario, TargetTruth, build_source_fixture, generate_targets

__all__ = [
    "AssociationRecord",
    "CampaignScenario",
    "LocalVisualTrackRecord",
    "SearchHandoverRecord",
    "SourceCueRecord",
    "SourceCueTruthLabel",
    "TargetTruth",
    "bbox_longest_side_px",
    "build_source_fixture",
    "generate_targets",
    "is_recognizable_bbox",
]
