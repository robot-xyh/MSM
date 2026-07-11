"""Adapters between D1-D6 module-specific data models."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

import numpy as np

from d1_sensor_fusion import GlobalTrack as D1GlobalTrack
from d2_data_association import Detection, GlobalTrack as D2GlobalTrack
from d3_assignment_planner import AssignmentPlan, ResourceState, TargetTrack
from d4_distributed_fallback.active_degradation import (
    AssignmentValiditySummary,
    AssociationRiskSummary,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
)
from d4_distributed_fallback.models import (
    AvailabilityBand,
    CommBand,
    ConfidenceBand,
    NodeRole,
    ResourceSummary,
    TrackSummary,
)
from d5_terminal_association import Assignment as TerminalAssignment
from d5_terminal_association import GlobalTrack as TerminalGlobalTrack
from d6_evaluation_metrics import (
    AssignmentRecord,
    CoalitionRecord,
    TargetDemandRecord,
    TerminalRecord,
    TrackRecord,
)

from .models import ResourcePlatform, TruthState


def d1_tracks_to_d2_detections(
    d1_tracks: Iterable[D1GlobalTrack],
    timestamp: float,
) -> list[Detection]:
    """Convert fused 3D tracks to D2 2D detections."""

    detections: list[Detection] = []
    for track in _best_d1_track_per_truth(d1_tracks):
        truth_id = track.metadata.get("truth_id")
        covariance_2d = track.covariance[:2, :2] + np.eye(2) * 0.5
        detections.append(
            Detection(
                detection_id=f"{track.global_track_id}_{timestamp:.2f}",
                timestamp=timestamp,
                position=track.position[:2],
                covariance=covariance_2d,
                truth_id=None if truth_id is None else str(truth_id),
                confidence=0.95,
                metadata={
                    "source_global_track_id": track.global_track_id,
                    "source_support": dict(track.source_support),
                    "covariance_trace_3d": float(np.trace(track.covariance[:3, :3])),
                    "position_3d": track.position.tolist(),
                    "velocity_3d": track.velocity.tolist(),
                },
            )
        )
    return detections


def _best_d1_track_per_truth(tracks: Iterable[D1GlobalTrack]) -> list[D1GlobalTrack]:
    best: dict[str, D1GlobalTrack] = {}
    unlabeled: list[D1GlobalTrack] = []
    for track in tracks:
        truth_id = track.metadata.get("truth_id")
        if truth_id is None:
            unlabeled.append(track)
            continue
        current = best.get(str(truth_id))
        if current is None or _d1_track_quality_key(track) < _d1_track_quality_key(current):
            best[str(truth_id)] = track
    return [*best.values(), *unlabeled]


def _d1_track_quality_key(track: D1GlobalTrack) -> tuple[float, int, str]:
    return (
        float(np.trace(track.covariance[:3, :3])),
        -int(sum(track.source_support.values())),
        track.global_track_id,
    )


def d2_tracks_to_target_tracks(
    tracks: Iterable[D2GlobalTrack],
    truth_by_id: dict[str, TruthState],
    resources: list[ResourcePlatform],
) -> list[TargetTrack]:
    """Convert D2 tracks into D3 abstract target tracks."""

    target_tracks: list[TargetTrack] = []
    for track in _best_track_per_truth(tracks):
        if track.truth_id is None or track.truth_id not in truth_by_id:
            continue
        truth = truth_by_id[track.truth_id]
        covariance_norm = min(float(np.trace(track.covariance[:2, :2])) / 120.0, 1.0)
        fov_difficulty: dict[str, float] = {}
        conflict_risk: dict[str, float] = {}
        feasibility: dict[str, bool] = {}
        for resource in resources:
            distance = float(np.linalg.norm(resource.position[:2] - track.position[:2]))
            coverage_penalty = 0.25 if resource.coverage_cell != truth.coverage_cell else 0.0
            fov_difficulty[resource.resource_id] = min(distance / 360.0 + coverage_penalty, 1.0)
            conflict_risk[resource.resource_id] = 0.10 if resource.coverage_cell != truth.coverage_cell else 0.02
            feasibility[resource.resource_id] = True
        target_tracks.append(
            TargetTrack(
                track_id=track.global_track_id,
                threat_score=truth.threat_score,
                covariance=covariance_norm,
                window_cost=min(float(np.linalg.norm(track.position)) / 1000.0, 1.0),
                assignable=True,
                fov_difficulty_by_resource=fov_difficulty,
                conflict_risk_by_resource=conflict_risk,
                feasibility_by_resource=feasibility,
                metadata={
                    "truth_id": track.truth_id,
                    "coverage_cell": truth.coverage_cell,
                    "position": track.position.tolist(),
                },
            )
        )
    return target_tracks


def _best_track_per_truth(tracks: Iterable[D2GlobalTrack]) -> list[D2GlobalTrack]:
    """Keep one D3 candidate per truth label when D2 has temporary duplicates."""

    best: dict[str, D2GlobalTrack] = {}
    unlabeled: list[D2GlobalTrack] = []
    for track in tracks:
        if track.truth_id is None:
            unlabeled.append(track)
            continue
        current = best.get(track.truth_id)
        if current is None or _track_quality_key(track) < _track_quality_key(current):
            best[track.truth_id] = track
    return [*best.values(), *unlabeled]


def _track_quality_key(track: D2GlobalTrack) -> tuple[float, int, str]:
    return (
        float(np.trace(track.covariance)),
        -int(track.hits),
        track.global_track_id,
    )


def resources_to_d3(resources: Iterable[ResourcePlatform]) -> list[ResourceState]:
    return [
        ResourceState(
            resource_id=resource.resource_id,
            status=resource.status,
            health_score=resource.health_score,
            metadata={
                "position": resource.position.tolist(),
                "coverage_cell": resource.coverage_cell,
            },
        )
        for resource in resources
    ]


def resources_to_d4(
    resources: Iterable[ResourcePlatform],
    secondary_available: bool,
    epoch: int = 1,
) -> list[ResourceSummary]:
    """Build D4 secondary-node and executor summaries."""

    summaries = [
        ResourceSummary(
            node_id="SEC-NORTH",
            capability_class="tethered_recon",
            availability_band=AvailabilityBand.HIGH if secondary_available else AvailabilityBand.NONE,
            comm_band=CommBand.GOOD,
            takeover_priority=10,
            lease_epoch=5,
            epoch=epoch,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
            cue_freshness_s=0.0 if secondary_available else None,
            gimbal_pointing_ok=secondary_available,
            secondary_coverage_ratio=0.9 if secondary_available else 0.0,
            cross_view_support_count=5 if secondary_available else 0,
            secondary_network_full_view_rate=0.9 if secondary_available else 0.0,
            stable_cross_view_registration_count=5 if secondary_available else 0,
            not_registered_count=0 if secondary_available else None,
        ),
        ResourceSummary(
            node_id="SEC-SOUTH",
            capability_class="tethered_recon",
            availability_band=AvailabilityBand.HIGH if secondary_available else AvailabilityBand.NONE,
            comm_band=CommBand.GOOD,
            takeover_priority=11,
            lease_epoch=5,
            epoch=epoch,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-south",
            cue_freshness_s=0.0 if secondary_available else None,
            gimbal_pointing_ok=secondary_available,
            secondary_coverage_ratio=0.9 if secondary_available else 0.0,
            cross_view_support_count=5 if secondary_available else 0,
            secondary_network_full_view_rate=0.9 if secondary_available else 0.0,
            stable_cross_view_registration_count=5 if secondary_available else 0,
            not_registered_count=0 if secondary_available else None,
        ),
    ]
    for resource in resources:
        summaries.append(
            ResourceSummary(
                node_id=resource.resource_id,
                capability_class="observe",
                availability_band=AvailabilityBand.HIGH
                if resource.status == "available"
                else AvailabilityBand.LOW,
                comm_band=CommBand.GOOD,
                takeover_priority=50,
                lease_epoch=1,
                epoch=epoch,
                node_role=NodeRole.INTERCEPTOR,
                coordinator_only=False,
                coverage_cell=resource.coverage_cell,
            )
        )
    return summaries


def d2_tracks_to_d4_tasks(
    tracks: Iterable[D2GlobalTrack],
    truth_by_id: dict[str, TruthState],
    timestamp: float,
    epoch: int = 1,
) -> list[TrackSummary]:
    tasks: list[TrackSummary] = []
    for track in tracks:
        truth = truth_by_id.get(track.truth_id or "")
        if truth is None:
            continue
        covariance_trace = float(np.trace(track.covariance[:2, :2]))
        if covariance_trace < 20.0:
            confidence = ConfidenceBand.HIGH
        elif covariance_trace < 80.0:
            confidence = ConfidenceBand.MEDIUM
        else:
            confidence = ConfidenceBand.LOW
        tasks.append(
            TrackSummary(
                track_id=track.global_track_id,
                coarse_cell=truth.coverage_cell,
                age_s=max(0.0, timestamp - track.last_update_time),
                confidence_band=confidence,
                source_count=2,
                epoch=epoch,
            )
        )
    return tasks


def d2_tracks_to_terminal_tracks(
    tracks: Iterable[D2GlobalTrack],
    truth_by_id: dict[str, TruthState],
    plan_version: int,
    timestamp: float,
) -> list[TerminalGlobalTrack]:
    """Convert D2 tracks to D5 center-owned global tracks."""

    output: list[TerminalGlobalTrack] = []
    for track in tracks:
        truth = truth_by_id.get(track.truth_id or "")
        if truth is None:
            continue
        covariance_3d = np.diag(
            [
                max(float(track.covariance[0, 0]), 0.5),
                max(float(track.covariance[1, 1]), 0.5),
                4.0,
            ]
        )
        output.append(
            TerminalGlobalTrack(
                global_track_id=track.global_track_id,
                position=np.array([track.state[0], track.state[1], truth.position[2]], dtype=float),
                covariance=covariance_3d,
                velocity=np.array([track.state[2], track.state[3], truth.velocity[2]], dtype=float),
                category="uav",
                timestamp=timestamp,
                track_version=plan_version,
            )
        )
    return output


def plan_to_terminal_assignments(plan: AssignmentPlan) -> list[TerminalAssignment]:
    output: list[TerminalAssignment] = []
    coalition_by_id = {item.coalition_id: item for item in plan.coalitions}
    for assignment in plan.assignments:
        coalition = coalition_by_id.get(assignment.coalition_id)
        activation_state = str(
            assignment.metadata.get(
                "activation_state",
                "active"
                if assignment.member_role == "primary" and assignment.wave_id == 0
                else "standby",
            )
        )
        output.append(TerminalAssignment(
            assigned_global_track_id=assignment.target_id,
            assignment_version=plan.version,
            timestamp=plan.created_at,
            require_version_match=True,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            authorization_state=plan.human_authorization_state,
            resource_id=assignment.resource_id,
            coalition_id=assignment.coalition_id,
            coalition_version=assignment.coalition_version,
            member_role=assignment.member_role,
            wave_id=assignment.wave_id,
            required_resource_count=assignment.required_resource_count,
            coordination_mode="independent"
            if coalition is None
            else coalition.coordination_mode,
            arrival_window_start_s=assignment.arrival_window_start_s,
            arrival_window_end_s=assignment.arrival_window_end_s,
            activation_state=activation_state,
        ))
    return output


def plan_to_assignment_records(
    plan: AssignmentPlan,
    d2_by_id: dict[str, D2GlobalTrack],
) -> list[AssignmentRecord]:
    records: list[AssignmentRecord] = []
    coalition_by_target = {item.target_id: item for item in plan.coalitions}
    for assignment in plan.assignments:
        track = d2_by_id.get(assignment.target_id)
        coalition = coalition_by_target.get(assignment.target_id)
        records.append(
            AssignmentRecord(
                timestamp=plan.created_at,
                plan_id=plan.plan_id,
                version=plan.version,
                resource_id=assignment.resource_id,
                global_track_id=assignment.target_id,
                cost_breakdown=assignment.cost_breakdown,
                authorization_state=plan.human_authorization_state,
                active=True,
                truth_id=None if track is None else track.truth_id,
                coordination_mode=None if coalition is None else coalition.coordination_mode,
                coalition_id=assignment.coalition_id,
                coalition_version=assignment.coalition_version,
                coalition_state=None if coalition is None else coalition.state,
                member_role=assignment.member_role,
                wave_id=assignment.wave_id,
                required_resource_count=assignment.required_resource_count,
                demand_assigned=None if coalition is None else coalition.assigned_resource_count,
                demand_shortfall=None if coalition is None else coalition.shortfall,
                demand_complete=None if coalition is None else coalition.complete,
                arrival_window_start=assignment.arrival_window_start_s,
                arrival_window_end=assignment.arrival_window_end_s,
                minimum_member_separation=None
                if coalition is None
                else coalition.minimum_separation_s,
            )
        )
    return records


def plan_to_m_to_n_records(
    plan: AssignmentPlan,
) -> tuple[list[TargetDemandRecord], list[CoalitionRecord]]:
    """Convert a D3 plan snapshot into passive D6 demand/coalition evidence."""

    demand_records: list[TargetDemandRecord] = []
    coalition_records: list[CoalitionRecord] = []
    for coalition in plan.coalitions:
        demand_records.append(
            TargetDemandRecord(
                timestamp=plan.created_at,
                global_track_id=coalition.target_id,
                required_resource_count=coalition.required_resource_count,
                coordination_mode=coalition.coordination_mode,
                demand_assigned=coalition.assigned_resource_count,
                demand_shortfall=coalition.shortfall,
                demand_complete=coalition.complete,
                coalition_id=coalition.coalition_id,
                coalition_version=coalition.version,
                coalition_state=coalition.state,
                minimum_member_separation=coalition.minimum_separation_s,
                metadata={
                    "plan_id": plan.plan_id,
                    "plan_version": plan.version,
                    "plan_schema": plan.plan_schema,
                },
            )
        )
        coalition_records.append(
            CoalitionRecord(
                timestamp=plan.created_at,
                global_track_id=coalition.target_id,
                coalition_id=coalition.coalition_id,
                coalition_version=coalition.version,
                coalition_state=coalition.state,
                coordination_mode=coalition.coordination_mode,
                member_ids=tuple(member.resource_id for member in coalition.members),
                member_roles={
                    member.resource_id: member.member_role for member in coalition.members
                },
                required_resource_count=coalition.required_resource_count,
                demand_assigned=coalition.assigned_resource_count,
                demand_shortfall=coalition.shortfall,
                demand_complete=coalition.complete,
                minimum_member_separation=coalition.minimum_separation_s,
                trigger_timestamp=plan.created_at,
                metadata={
                    "plan_id": plan.plan_id,
                    "plan_version": plan.version,
                    "plan_schema": plan.plan_schema,
                    "complete": coalition.complete,
                },
            )
        )
    return demand_records, coalition_records


def track_records_from_d2(
    tracks: Iterable[D2GlobalTrack],
    truth_by_id: dict[str, TruthState],
    timestamp: float,
) -> list[TrackRecord]:
    records: list[TrackRecord] = []
    for track in tracks:
        truth = truth_by_id.get(track.truth_id or "")
        truth_position = None if truth is None else tuple(float(value) for value in truth.position)
        position = (
            float(track.state[0]),
            float(track.state[1]),
            float(truth.position[2] if truth is not None else 0.0),
        )
        records.append(
            TrackRecord(
                timestamp=timestamp,
                global_track_id=track.global_track_id,
                truth_id=track.truth_id,
                position=position,
                truth_position=truth_position,
                covariance_trace=float(np.trace(track.covariance)),
                track_state=track.lifecycle_state.value,
                association_source="integrated_d2",
            )
        )
    return records


def track_uncertainty_summary(
    track: D2GlobalTrack,
    truth: TruthState,
    timestamp: float,
) -> TrackUncertaintySummary:
    covariance_xy = track.covariance[:2, :2]
    max_eigenvalue = max(float(np.linalg.eigvalsh(covariance_xy)[-1]), 0.0)
    return TrackUncertaintySummary(
        track_id=track.global_track_id,
        coverage_cell=truth.coverage_cell,
        position_sigma_m=float(np.sqrt(max_eigenvalue)),
        covariance_trace=float(np.trace(track.covariance)),
        velocity_sigma_mps=float(np.sqrt(max(float(np.trace(track.covariance[2:, 2:])), 0.0))),
        measurement_age_s=max(0.0, timestamp - track.last_update_time),
    )


def association_risk_summary(
    track: D2GlobalTrack,
    ambiguity_score: float,
    id_switch_count: int,
    duplicate_assignment_count: int,
    track_continuity: float,
) -> AssociationRiskSummary:
    return AssociationRiskSummary(
        track_id=track.global_track_id,
        ambiguity_score=ambiguity_score,
        id_switch_count=id_switch_count,
        duplicate_track_count=duplicate_assignment_count,
        track_continuity=track_continuity,
    )


def assignment_validity_summary(
    plan: AssignmentPlan,
    assignment_resource_id: str,
    global_track_id: str,
    timestamp: float,
) -> AssignmentValiditySummary:
    costs = [assignment.cost for assignment in plan.assignments]
    ordered_costs = sorted(costs)
    if len(ordered_costs) >= 2:
        margin = max(0.0, ordered_costs[1] - ordered_costs[0])
    else:
        margin = 1.0
    return AssignmentValiditySummary(
        global_track_id=global_track_id,
        assigned_resource_id=assignment_resource_id,
        plan_version=plan.version,
        is_current=True,
        plan_age_s=max(0.0, timestamp - plan.created_at),
        cost_margin=float(min(margin, 1.0)),
    )


def terminal_summary_from_record(
    resource_id: str,
    assigned_global_track_id: str,
    decision_state: str,
    confidence: float,
    ambiguity_score: float,
    coverage_cell: str,
    observed_global_track_id: str | None,
    non_locked_count: int,
    mismatch_count: int,
    friend_conflict: bool,
) -> TerminalAssociationSummary:
    state = TerminalDecisionState(decision_state)
    return TerminalAssociationSummary(
        resource_id=resource_id,
        assigned_global_track_id=assigned_global_track_id,
        decision_state=state,
        association_confidence=confidence,
        ambiguity_score=ambiguity_score,
        coverage_cell=coverage_cell,
        observed_global_track_id=observed_global_track_id,
        consecutive_non_locked_frames=non_locked_count,
        consecutive_mismatch_frames=mismatch_count,
        friend_conflict=friend_conflict,
    )


def terminal_to_record(
    timestamp: float,
    resource_id: str,
    assigned_global_track_id: str,
    local_track_id: str | None,
    decision_state: str,
    ambiguity_score: float,
    friend_conflict_state: str,
    assignment_version: int,
    observed_global_track_id: str | None,
    authorization_state: str = "recorded",
    coordination_mode: str | None = None,
    coalition_id: str | None = None,
    coalition_version: int | None = None,
    coalition_state: str | None = None,
    member_role: str | None = None,
    wave_id: str | int | None = None,
    required_resource_count: int | None = None,
    demand_assigned: int | None = None,
    demand_shortfall: int | None = None,
    demand_complete: bool | None = None,
    arrival_window_start: float | None = None,
    arrival_window_end: float | None = None,
    minimum_member_separation: float | None = None,
) -> TerminalRecord:
    correct = None
    if observed_global_track_id is not None:
        correct = observed_global_track_id == assigned_global_track_id
    return TerminalRecord(
        timestamp=timestamp,
        resource_id=resource_id,
        assigned_global_track_id=assigned_global_track_id,
        local_track_id=local_track_id,
        decision_state=decision_state,
        ambiguity_score=ambiguity_score,
        friend_conflict_state=friend_conflict_state,
        assignment_version=assignment_version,
        expected_global_track_id=assigned_global_track_id,
        association_correct=correct,
        authorization_state=authorization_state,
        coordination_mode=coordination_mode,
        coalition_id=coalition_id,
        coalition_version=coalition_version,
        coalition_state=coalition_state,
        member_role=member_role,
        wave_id=wave_id,
        required_resource_count=required_resource_count,
        demand_assigned=demand_assigned,
        demand_shortfall=demand_shortfall,
        demand_complete=demand_complete,
        arrival_window_start=arrival_window_start,
        arrival_window_end=arrival_window_end,
        minimum_member_separation=minimum_member_separation,
    )


def jsonable_dataclass(value: Any) -> dict[str, Any]:
    """Dataclass-to-dict helper for records that may contain NumPy scalars."""

    def convert(item: Any) -> Any:
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.floating):
            return float(item)
        if isinstance(item, np.integer):
            return int(item)
        if isinstance(item, dict):
            return {str(key): convert(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(val) for val in item]
        return item

    return convert(asdict(value))
