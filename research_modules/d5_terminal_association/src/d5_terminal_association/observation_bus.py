"""Passive terminal observation bus for cross-view summaries.

The bus is intentionally not a planner. It aggregates terminal visual evidence
from interceptors, secondary reconnaissance nodes, and peer links, then reports
cross-view consistency and duplicate-lock risk for D3/D4/D6 consumers.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from .models import (
    CrossViewAssociation,
    IdentityClaim,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociation,
    TerminalObservation,
)
from .coalition_visual import CoalitionVisualSummary, summarize_coalition_visual_completion


_AUTHORIZED_STATES = {
    "authorized",
    "approved",
    "human_approved",
    "operator_approved",
    "recorded",
}
_ACTIVE_MEMBER_STATES = {"active", "activated", "authorized", "committed", "executing"}


@dataclass(frozen=True)
class _CoalitionLockAssessment:
    conflict: bool
    conflict_state: str
    planned_cooperative_lock: bool
    coalition_id: str | None
    coalition_version: int | None
    required_resource_count: int
    coordination_mode: str
    excess_lock_resource_ids: tuple[str, ...]
    lock_contracts: tuple[dict[str, Any], ...]


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

    def coalition_visual_summary(
        self,
        coalition_bindings: Iterable[Any],
        *,
        historical_associations: Iterable[TerminalAssociation | TerminalObservation] = (),
        required_stable_frames: int = 2,
    ) -> CoalitionVisualSummary:
        """Summarize the bus snapshot against one read-only D3 coalition contract."""

        return summarize_coalition_visual_completion(
            coalition_bindings,
            (
                observation
                for observation in self._observations
                if observation.terminal_association is not None
            ),
            historical_associations,
            required_stable_frames=required_stable_frames,
        )

    def cross_view_associations(
        self,
        *,
        as_of_timestamp: float | None = None,
        max_age_s: float | None = None,
        plan_id: str | None = None,
        plan_version: int | None = None,
    ) -> list[CrossViewAssociation]:
        """Group terminal associations by existing global track ID.

        The grouping uses only global IDs supplied by upstream D2/D3/D4 data.
        Local track IDs are namespaced as `resource_id:local_track_id` because
        local MOT IDs are not unique across interceptors or cameras.

        With no scope arguments, the method retains its legacy all-history
        behavior. Any scope argument enables snapshot mode: observations are
        filtered by time and plan identity, then only each resource's latest
        timestamp is retained. Duplicate locks therefore represent concurrent
        evidence in one current snapshot rather than accumulated history.
        """

        observations, snapshot_metadata = _snapshot_observations(
            self._observations,
            as_of_timestamp=as_of_timestamp,
            max_age_s=max_age_s,
            plan_id=plan_id,
            plan_version=plan_version,
        )
        grouped: dict[str, list[TerminalObservation]] = defaultdict(list)
        locked_local_to_global: dict[str, list[str]] = defaultdict(list)
        locked_global_to_resources: dict[str, list[str]] = defaultdict(list)
        observed_global_ids_by_resource: dict[str, list[str]] = defaultdict(list)

        for observation in observations:
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
            locked_observations = [
                observation
                for observation in observations
                if observation.terminal_association is not None
                and observation.terminal_association.decision_state == "locked"
                and observation.terminal_association.local_track_id is not None
            ]
            coalition = _assess_coalition_locks(locked_observations)
            locked_resource_ids = _unique(locked_global_to_resources[global_track_id])
            duplicate_local_track_ids = _unique(duplicate_local_ids_by_global[global_track_id])
            per_resource_multi_local_ids = _per_resource_multi_local_ids(locked_observations)
            duplicate_local_track_ids = _unique(
                (*duplicate_local_track_ids, *per_resource_multi_local_ids)
            )
            duplicate_risk = bool(coalition.conflict or duplicate_local_track_ids)
            duplicate_lock_resource_ids = locked_resource_ids if duplicate_risk else ()
            reason = "multi_view_support" if len(supporting_resource_ids) > 1 else "single_view_support"
            planned_cooperative_lock = bool(
                coalition.planned_cooperative_lock and not duplicate_risk
            )
            if planned_cooperative_lock:
                reason = "planned_cooperative_lock"
            elif coalition.conflict_state == "member_count_exceeds_demand":
                reason = "coalition_member_over_demand"
            elif coalition.conflict:
                reason = "coalition_contract_conflict"
            elif duplicate_risk:
                reason = "duplicate_terminal_lock_risk"
            recon_cue_evidence = tuple(
                _recon_cue_evidence(cue)
                for observation in observations
                for cue in observation.recon_image_cues
            )
            coverage_modes = _unique(
                value
                for value in (
                    *(
                        cue.get("coverage_mode")
                        for cue in recon_cue_evidence
                    ),
                    *(
                        observation.metadata.get("coverage_mode")
                        for observation in observations
                    ),
                )
            )
            capability_classes = _unique(
                value
                for value in (
                    *(
                        cue.get("capability_class")
                        for cue in recon_cue_evidence
                    ),
                    *(
                        observation.metadata.get("capability_class")
                        for observation in observations
                    ),
                )
            )
            cue_sources = _unique(
                value
                for value in (
                    *(
                        cue.get("cue_source")
                        for cue in recon_cue_evidence
                    ),
                    *(
                        observation.metadata.get("cue_source")
                        for observation in observations
                    ),
                )
            )

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
                    planned_cooperative_lock=planned_cooperative_lock,
                    coalition_id=coalition.coalition_id,
                    coalition_version=coalition.coalition_version,
                    required_resource_count=coalition.required_resource_count,
                    coordination_mode=coalition.coordination_mode,
                    excess_lock_resource_ids=coalition.excess_lock_resource_ids,
                    coalition_conflict_state=coalition.conflict_state,
                    metadata={
                        "observed_global_track_ids_by_resource": {
                            resource_id: _unique(global_ids)
                            for resource_id, global_ids in observed_global_ids_by_resource.items()
                        },
                        "coverage_modes": coverage_modes,
                        "capability_classes": capability_classes,
                        "cue_sources": cue_sources,
                        "recon_cue_evidence": recon_cue_evidence,
                        "mobile_recon_gimbal_support_count": sum(
                            1
                            for cue in recon_cue_evidence
                            if cue.get("coverage_mode") == "mobile_recon_gimbal"
                            or cue.get("capability_class") == "mobile_high_recon"
                        ),
                        "fixed_downlook_secondary_support_count": sum(
                            1
                            for cue in recon_cue_evidence
                            if cue.get("coverage_mode") == "fixed_downlook_secondary"
                        ),
                        "planned_cooperative_lock": planned_cooperative_lock,
                        "coalition_id": coalition.coalition_id,
                        "coalition_version": coalition.coalition_version,
                        "required_resource_count": coalition.required_resource_count,
                        "coordination_mode": coalition.coordination_mode,
                        "coalition_conflict_state": coalition.conflict_state,
                        "excess_lock_resource_ids": coalition.excess_lock_resource_ids,
                        "lock_contracts": coalition.lock_contracts,
                        **snapshot_metadata,
                    },
                )
            )

        return sorted(associations, key=lambda item: item.global_track_id)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value is not None and str(value)))


def _snapshot_observations(
    observations: Iterable[TerminalObservation],
    *,
    as_of_timestamp: float | None,
    max_age_s: float | None,
    plan_id: str | None,
    plan_version: int | None,
) -> tuple[tuple[TerminalObservation, ...], dict[str, Any]]:
    all_observations = tuple(observations)
    scope_enabled = any(
        value is not None
        for value in (as_of_timestamp, max_age_s, plan_id, plan_version)
    )
    if not scope_enabled:
        return all_observations, {
            "snapshot_scope_enabled": False,
            "snapshot_input_observation_count": len(all_observations),
            "snapshot_selected_observation_count": len(all_observations),
        }
    if max_age_s is not None and as_of_timestamp is None:
        raise ValueError("max_age_s requires as_of_timestamp")
    if as_of_timestamp is not None:
        as_of_timestamp = float(as_of_timestamp)
        if not np.isfinite(as_of_timestamp):
            raise ValueError("as_of_timestamp must be finite")
    if max_age_s is not None:
        max_age_s = float(max_age_s)
        if not np.isfinite(max_age_s) or max_age_s < 0.0:
            raise ValueError("max_age_s must be finite and non-negative")
    if plan_version is not None:
        plan_version = int(plan_version)

    candidates: list[TerminalObservation] = []
    for observation in all_observations:
        association = observation.terminal_association
        if association is None:
            continue
        timestamp = float(observation.timestamp)
        if as_of_timestamp is not None:
            age_s = as_of_timestamp - timestamp
            if age_s < -1e-9:
                continue
            if max_age_s is not None and age_s > max_age_s + 1e-9:
                continue
        if plan_id is not None and association.plan_id != plan_id:
            continue
        if plan_version is not None and association.plan_version != plan_version:
            continue
        candidates.append(observation)

    latest_timestamp_by_resource: dict[str, float] = {}
    for observation in candidates:
        latest_timestamp_by_resource[observation.resource_id] = max(
            float(observation.timestamp),
            latest_timestamp_by_resource.get(observation.resource_id, float("-inf")),
        )
    selected = tuple(
        observation
        for observation in candidates
        if abs(
            float(observation.timestamp)
            - latest_timestamp_by_resource[observation.resource_id]
        )
        <= 1e-9
    )
    return selected, {
        "snapshot_scope_enabled": True,
        "snapshot_as_of_timestamp": as_of_timestamp,
        "snapshot_max_age_s": max_age_s,
        "snapshot_plan_id": plan_id,
        "snapshot_plan_version": plan_version,
        "snapshot_input_observation_count": len(all_observations),
        "snapshot_candidate_observation_count": len(candidates),
        "snapshot_selected_observation_count": len(selected),
        "snapshot_latest_timestamp_by_resource": dict(latest_timestamp_by_resource),
    }


def _assess_coalition_locks(
    observations: list[TerminalObservation],
) -> _CoalitionLockAssessment:
    associations = [
        observation.terminal_association
        for observation in observations
        if observation.terminal_association is not None
    ]
    resource_ids = _unique(observation.resource_id for observation in observations)
    contracts = tuple(
        {
            "resource_id": observation.resource_id,
            "plan_id": association.plan_id,
            "plan_version": association.plan_version,
            "coalition_id": association.coalition_id,
            "coalition_version": association.coalition_version,
            "member_role": association.member_role,
            "wave_id": association.wave_id,
            "required_resource_count": association.required_resource_count,
            "coordination_mode": association.coordination_mode,
            "arrival_window_start_s": association.arrival_window_start_s,
            "arrival_window_end_s": association.arrival_window_end_s,
            "activation_state": association.activation_state,
            "authorization_state": association.authorization_state,
            "execution_gate_pass": association.metadata.get("execution_gate_pass", True),
        }
        for observation, association in zip(observations, associations)
    )
    if len(resource_ids) <= 1:
        association = associations[0] if associations else None
        return _CoalitionLockAssessment(
            conflict=False,
            conflict_state="none",
            planned_cooperative_lock=False,
            coalition_id=association.coalition_id if association is not None else None,
            coalition_version=association.coalition_version if association is not None else None,
            required_resource_count=(
                association.required_resource_count if association is not None else 1
            ),
            coordination_mode=(
                association.coordination_mode if association is not None else "independent"
            ),
            excess_lock_resource_ids=(),
            lock_contracts=contracts,
        )

    signatures = {
        (
            association.plan_id,
            association.plan_version,
            association.coalition_id,
            association.coalition_version,
            association.required_resource_count,
            association.coordination_mode,
        )
        for association in associations
    }
    first = associations[0]
    contract_complete = all(
        association.plan_id is not None
        and association.plan_version is not None
        and association.coalition_id is not None
        and association.coalition_version is not None
        and association.required_resource_count > 1
        for association in associations
    )
    resource_scope_matches = all(
        association.resource_id in {None, observation.resource_id}
        for observation, association in zip(observations, associations)
    )
    execution_authorized = all(
        association.authorization_state.lower() in _AUTHORIZED_STATES
        and association.activation_state in _ACTIVE_MEMBER_STATES
        and bool(association.metadata.get("execution_gate_pass", True))
        for association in associations
    )
    if not contract_complete:
        conflict_state = "missing_coalition_contract"
    elif len(signatures) != 1:
        conflict_state = "coalition_or_plan_version_mismatch"
    elif not resource_scope_matches:
        conflict_state = "resource_outside_assignment_scope"
    elif not execution_authorized:
        conflict_state = "coalition_member_not_execution_authorized"
    elif len(resource_ids) > first.required_resource_count:
        conflict_state = "member_count_exceeds_demand"
    else:
        conflict_state = "none"
    excess_ids = (
        resource_ids[first.required_resource_count :]
        if first.required_resource_count < len(resource_ids)
        else ()
    )
    conflict = conflict_state != "none"
    return _CoalitionLockAssessment(
        conflict=conflict,
        conflict_state=conflict_state,
        planned_cooperative_lock=not conflict,
        coalition_id=first.coalition_id if len(signatures) == 1 else None,
        coalition_version=first.coalition_version if len(signatures) == 1 else None,
        required_resource_count=first.required_resource_count,
        coordination_mode=first.coordination_mode,
        excess_lock_resource_ids=excess_ids,
        lock_contracts=contracts,
    )


def _per_resource_multi_local_ids(observations: list[TerminalObservation]) -> tuple[str, ...]:
    by_resource: dict[str, list[str]] = defaultdict(list)
    for observation in observations:
        by_resource[observation.resource_id].append(_namespaced_local_id(observation))
    return _unique(
        local_id
        for local_ids in by_resource.values()
        if len(_unique(local_ids)) > 1
        for local_id in _unique(local_ids)
    )


def _namespaced_local_id(observation: TerminalObservation) -> str:
    association = observation.terminal_association
    if association is None or association.local_track_id is None:
        raise ValueError("observation has no terminal local_track_id")
    if observation.camera_id:
        return f"{observation.resource_id}/{observation.camera_id}:{association.local_track_id}"
    return f"{observation.resource_id}:{association.local_track_id}"


def _recon_cue_evidence(cue: ReconImageCue) -> dict[str, Any]:
    return {
        "cue_id": cue.cue_id,
        "producer_node_id": cue.producer_node_id,
        "image_frame_id": cue.image_frame_id,
        "global_track_id": cue.global_track_id,
        "source_type": cue.source_type,
        "cue_source": cue.cue_source,
        "capability_class": cue.capability_class,
        "coverage_mode": cue.coverage_mode,
        "cue_position_ned": _vector_to_list(cue.cue_position_ned),
        "look_at_ned": _vector_to_list(cue.look_at_ned),
        "gimbal_pointing_metadata": dict(cue.gimbal_pointing_metadata),
        "cue_pointing_error_m": cue.cue_pointing_error_m,
        "cue_pointing_error_rad": cue.cue_pointing_error_rad,
        "gimbal_track_error_px": cue.gimbal_track_error_px,
        "confidence": cue.confidence,
        "scoped_resource_ids": cue.scoped_resource_ids,
    }


def _vector_to_list(value: np.ndarray | None) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value.tolist()]
