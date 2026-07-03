"""Passive terminal observation bus for cross-view summaries.

The bus is intentionally not a planner. It aggregates terminal visual evidence
from interceptors, secondary reconnaissance nodes, and peer links, then reports
cross-view consistency and duplicate-lock risk for D3/D4/D6 consumers.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np

from .models import (
    CrossViewAssociation,
    IdentityClaim,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociation,
    TerminalObservation,
)


class TerminalObservationBus:
    """Collect local terminal evidence and derive cross-view associations.

    The bus preserves submitted `TerminalAssociation.assigned_global_track_id`
    values exactly. Duplicate terminal locks are surfaced as risk signals only;
    no reassignment, deconfliction, or ID rewriting is performed here.
    """

    def __init__(self) -> None:
        self._observations: list[TerminalObservation] = []

    def publish(self, observation: TerminalObservation) -> TerminalObservation:
        """Append an already built observation and return it unchanged."""

        self._observations.append(observation)
        return observation

    def publish_terminal_association(
        self,
        *,
        resource_id: str,
        source_node_id: str,
        link_type: str,
        timestamp: float,
        terminal_association: TerminalAssociation,
        local_track: LocalVisualTrack | None = None,
        identity_claims: Iterable[IdentityClaim] = (),
        recon_image_cues: Iterable[ReconImageCue] = (),
        camera_id: str | None = None,
        frame_id: str | None = None,
        arrival_timestamp: float | None = None,
        metadata: dict | None = None,
    ) -> TerminalObservation:
        """Publish a terminal association summary from one resource."""

        return self.publish(
            TerminalObservation(
                resource_id=resource_id,
                source_node_id=source_node_id,
                link_type=link_type,
                timestamp=timestamp,
                local_track=local_track,
                terminal_association=terminal_association,
                identity_claims=tuple(identity_claims),
                recon_image_cues=tuple(recon_image_cues),
                camera_id=camera_id,
                frame_id=frame_id,
                arrival_timestamp=arrival_timestamp,
                metadata=metadata or {},
            )
        )

    def publish_local_track(
        self,
        *,
        resource_id: str,
        source_node_id: str,
        link_type: str,
        timestamp: float,
        local_track: LocalVisualTrack,
        identity_claims: Iterable[IdentityClaim] = (),
        recon_image_cues: Iterable[ReconImageCue] = (),
        camera_id: str | None = None,
        frame_id: str | None = None,
        arrival_timestamp: float | None = None,
        metadata: dict | None = None,
    ) -> TerminalObservation:
        """Publish local visual evidence before or without terminal locking."""

        return self.publish(
            TerminalObservation(
                resource_id=resource_id,
                source_node_id=source_node_id,
                link_type=link_type,
                timestamp=timestamp,
                local_track=local_track,
                identity_claims=tuple(identity_claims),
                recon_image_cues=tuple(recon_image_cues),
                camera_id=camera_id,
                frame_id=frame_id,
                arrival_timestamp=arrival_timestamp,
                metadata=metadata or {},
            )
        )

    def observations(self) -> tuple[TerminalObservation, ...]:
        """Return an immutable snapshot of bus contents."""

        return tuple(self._observations)

    def clear(self) -> None:
        """Remove all stored observations."""

        self._observations.clear()

    def cross_view_associations(self) -> list[CrossViewAssociation]:
        """Group terminal associations by existing global track ID.

        The grouping uses only global IDs supplied by upstream D2/D3/D4 data.
        Local track IDs are namespaced as `resource_id:local_track_id` because
        local MOT IDs are not unique across interceptors or cameras.
        """

        grouped: dict[str, list[TerminalObservation]] = defaultdict(list)
        locked_local_to_global: dict[str, list[str]] = defaultdict(list)
        locked_global_to_resources: dict[str, list[str]] = defaultdict(list)
        observed_global_ids_by_resource: dict[str, list[str]] = defaultdict(list)

        for observation in self._observations:
            association = observation.terminal_association
            if association is None:
                continue
            if association.local_track_id is None and association.decision_state == "reacquire":
                continue
            grouped[association.assigned_global_track_id].append(observation)
            observed_global_ids_by_resource[observation.resource_id].append(
                association.assigned_global_track_id
            )
            if association.decision_state == "locked" and association.local_track_id is not None:
                local_key = _namespaced_local_id(observation)
                locked_local_to_global[local_key].append(association.assigned_global_track_id)
                locked_global_to_resources[association.assigned_global_track_id].append(
                    observation.resource_id
                )

        duplicate_local_ids_by_global: dict[str, list[str]] = defaultdict(list)
        for local_id, global_ids in locked_local_to_global.items():
            unique_global_ids = _unique(global_ids)
            if len(unique_global_ids) <= 1:
                continue
            for global_id in unique_global_ids:
                duplicate_local_ids_by_global[global_id].append(local_id)

        associations: list[CrossViewAssociation] = []
        for global_track_id, observations in grouped.items():
            supporting_resource_ids = _unique(observation.resource_id for observation in observations)
            local_track_ids = _unique(
                _namespaced_local_id(observation)
                for observation in observations
                if observation.terminal_association is not None
                and observation.terminal_association.local_track_id is not None
            )
            terminal_associations = [
                observation.terminal_association
                for observation in observations
                if observation.terminal_association is not None
            ]
            locked_resources = _unique(
                observation.resource_id
                for observation in observations
                if observation.terminal_association is not None
                and observation.terminal_association.decision_state == "locked"
            )
            source_node_ids = _unique(observation.source_node_id for observation in observations)
            link_types = _unique(observation.link_type for observation in observations)
            decision_states = tuple(association.decision_state for association in terminal_associations)
            confidences = tuple(
                float(np.clip(association.association_confidence, 0.0, 1.0))
                for association in terminal_associations
            )
            ambiguity = max(
                (float(np.clip(association.ambiguity_score, 0.0, 1.0)) for association in terminal_associations),
                default=1.0,
            )
            duplicate_lock_resource_ids = _unique(locked_global_to_resources[global_track_id])
            duplicate_local_track_ids = _unique(duplicate_local_ids_by_global[global_track_id])
            duplicate_risk = len(duplicate_lock_resource_ids) > 1 or bool(duplicate_local_track_ids)
            reason = "multi_view_support" if len(supporting_resource_ids) > 1 else "single_view_support"
            if duplicate_risk:
                reason = "duplicate_terminal_lock_risk"

            associations.append(
                CrossViewAssociation(
                    global_track_id=global_track_id,
                    supporting_resource_ids=supporting_resource_ids,
                    local_track_ids=local_track_ids,
                    ambiguity_score=ambiguity,
                    duplicate_terminal_lock_risk=duplicate_risk,
                    source_node_id="terminal_observation_bus",
                    link_type="cross_view_summary",
                    source_node_ids=source_node_ids,
                    link_types=link_types,
                    decision_states=decision_states,
                    association_confidences=confidences,
                    friend_conflict_states=tuple(
                        association.friend_conflict_state for association in terminal_associations
                    ),
                    recon_cue_used_count=sum(
                        1 for association in terminal_associations if association.recon_cue_used
                    ),
                    support_count=len(supporting_resource_ids),
                    duplicate_lock_resource_ids=duplicate_lock_resource_ids,
                    duplicate_local_track_ids=duplicate_local_track_ids,
                    reason=reason,
                    metadata={
                        "observed_global_track_ids_by_resource": {
                            resource_id: _unique(global_ids)
                            for resource_id, global_ids in observed_global_ids_by_resource.items()
                        }
                    },
                )
            )

        return sorted(associations, key=lambda item: item.global_track_id)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value is not None and str(value)))


def _namespaced_local_id(observation: TerminalObservation) -> str:
    association = observation.terminal_association
    if association is None or association.local_track_id is None:
        raise ValueError("observation has no terminal local_track_id")
    if observation.camera_id:
        return f"{observation.resource_id}/{observation.camera_id}:{association.local_track_id}"
    return f"{observation.resource_id}:{association.local_track_id}"
