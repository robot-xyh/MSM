"""Failover coordinator for offline degraded continuity experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .cbba import CBBANegotiator
from .models import (
    Assignment,
    AvailabilityBand,
    C2Health,
    CBBAResult,
    CommBand,
    HealthTransition,
    MergeResult,
    NodeRole,
    ResourceSummary,
    SECONDARY_NODE_ROLES,
    TrackSummary,
    is_secondary_node_resource,
    node_role_value,
    secondary_capability_class,
)
from .network import SimulatedNetwork


AVAILABILITY_RANK = {
    AvailabilityBand.NONE: 0,
    AvailabilityBand.LOW: 1,
    AvailabilityBand.MEDIUM: 2,
    AvailabilityBand.HIGH: 3,
}
COMM_RANK = {
    CommBand.POOR: 0,
    CommBand.LIMITED: 1,
    CommBand.GOOD: 2,
}
CAPABILITY_RANK = {
    "secondary_c2": 5,
    "mobile_high_recon": 5,
    "mobile_secondary_recon": 5,
    "fixed_tethered_secondary": 4,
    "tethered_recon": 4,
    "relay": 3,
    "observe": 2,
    "hold": 1,
}
ROLE_RANK = {
    NodeRole.GROUND_BACKUP: 0,
    NodeRole.MOBILE_HIGH_RECON: 1,
    NodeRole.MOBILE_SECONDARY_RECON: 1,
    NodeRole.FIXED_TETHERED_SECONDARY: 2,
    NodeRole.SECONDARY_RECON: 2,
    NodeRole.CLUSTER_REPRESENTATIVE: 3,
    NodeRole.INTERCEPTOR: 4,
}
ROLE_RANK_BY_VALUE = {role.value: rank for role, rank in ROLE_RANK.items()}


@dataclass
class FailoverCoordinator:
    node_id: str
    peer_ids: list[str]
    epoch: int = 1
    heartbeat_warning_s: float = 1.0
    heartbeat_stale_s: float = 2.0
    heartbeat_failure_s: float = 4.0
    stable_recovery_s: float = 2.0
    health: C2Health = C2Health.NORMAL
    last_heartbeat_s: float = 0.0
    last_good_digest_s: float = 0.0
    transition_log: list[HealthTransition] = field(default_factory=list)
    leader_id: str | None = None
    last_plan: CBBAResult | None = None

    @property
    def node_ids(self) -> list[str]:
        return [self.node_id, *self.peer_ids]

    def observe_center(
        self,
        now_s: float,
        heartbeat_ok: bool,
        digest_ok: bool = True,
        center_epoch: int | None = None,
    ) -> C2Health:
        if center_epoch is not None and center_epoch < self.epoch:
            return self._transition(C2Health.SUSPECT, now_s, "center_epoch_stale")
        if heartbeat_ok:
            self.last_heartbeat_s = now_s
        if heartbeat_ok and digest_ok:
            self.last_good_digest_s = now_s
            if self.health in {C2Health.DEGRADED, C2Health.SUSPECT, C2Health.FAILED}:
                return self._transition(
                    C2Health.SUSPECT,
                    now_s,
                    "center_digest_recovered_pending_merge",
                )
            if self.health == C2Health.NORMAL:
                return self.health
        if not digest_ok:
            return self._transition(C2Health.SUSPECT, now_s, "center_digest_conflict")
        return self.update_health(now_s)

    def update_health(
        self,
        now_s: float,
        peer_fail_votes: int = 0,
        quorum_size: int | None = None,
    ) -> C2Health:
        quorum = quorum_size if quorum_size is not None else (len(self.node_ids) // 2 + 1)
        if peer_fail_votes >= quorum:
            return self._transition(C2Health.FAILED, now_s, "peer_quorum_failed")
        heartbeat_age = now_s - self.last_heartbeat_s
        if heartbeat_age > self.heartbeat_failure_s:
            return self._transition(C2Health.FAILED, now_s, "heartbeat_failure_timeout")
        if heartbeat_age > self.heartbeat_stale_s:
            return self._transition(C2Health.SUSPECT, now_s, "heartbeat_stale")
        if heartbeat_age > self.heartbeat_warning_s:
            return self._transition(C2Health.DEGRADED, now_s, "heartbeat_jitter")
        if self.health != C2Health.NORMAL:
            return self._transition(
                C2Health.SUSPECT,
                now_s,
                "heartbeat_recovered_pending_merge",
            )
        return self.health

    def elect_leader(
        self,
        resources: Iterable[ResourceSummary],
        tasks: Iterable[TrackSummary] | None = None,
    ) -> str | None:
        leader = self.elect_leader_resource(resources, tasks=tasks)
        self.leader_id = None if leader is None else leader.node_id
        return self.leader_id

    def elect_leader_resource(
        self,
        resources: Iterable[ResourceSummary],
        tasks: Iterable[TrackSummary] | None = None,
    ) -> ResourceSummary | None:
        task_cells = {
            task.coarse_cell
            for task in tasks or ()
            if task.coarse_cell not in {None, ""}
        }
        candidates = [
            resource
            for resource in resources
            if not resource.operator_hold and resource.availability_band != AvailabilityBand.NONE
            and self._resource_covers_task_cells(resource, task_cells)
        ]
        if not candidates:
            self.leader_id = None
            return None
        candidates.sort(
            key=lambda resource: (
                int(resource.takeover_priority),
                ROLE_RANK_BY_VALUE.get(node_role_value(resource.node_role), 99),
                -int(resource.lease_epoch),
                -AVAILABILITY_RANK[resource.availability_band],
                -COMM_RANK[resource.comm_band],
                -CAPABILITY_RANK.get(resource.capability_class, 0),
                resource.node_id,
            )
        )
        self.leader_id = candidates[0].node_id
        return candidates[0]

    def plan_degraded(
        self,
        tasks: list[TrackSummary],
        resources: list[ResourceSummary],
        network: SimulatedNetwork,
        now_s: float,
        bundle_limit: int = 1,
        max_rounds: int = 20,
        round_period_s: float = 0.5,
    ) -> CBBAResult:
        if self.health != C2Health.FAILED:
            self.update_health(now_s)
        if self.health != C2Health.FAILED:
            return self._safe_hold_result(now_s, "center_not_failed")
        leader_resource = self.elect_leader_resource(resources, tasks=tasks)
        if leader_resource is None:
            self._transition(C2Health.SUSPECT, now_s, "no_eligible_fallback_leader")
            return self._safe_hold_result(now_s, "no_eligible_fallback_leader")
        coordination_mode = self._coordination_mode(leader_resource)
        self._transition(
            C2Health.DEGRADED,
            now_s,
            "secondary_node_takeover"
            if coordination_mode == "secondary_node"
            else "distributed_fallback_elected",
        )
        executor_resources = [
            resource
            for resource in resources
            if not resource.coordinator_only and not is_secondary_node_resource(resource)
        ]
        negotiator = CBBANegotiator(
            node_ids=[resource.node_id for resource in executor_resources],
            epoch=self.epoch,
            bundle_limit=bundle_limit,
            max_rounds=max_rounds,
            round_period_s=round_period_s,
        )
        self.last_plan = negotiator.run(tasks, executor_resources, network, start_time_s=now_s)
        self.last_plan.final_views["coordination_mode"] = {
            "state": coordination_mode,
            "leader_id": leader_resource.node_id,
            "leader_role": node_role_value(leader_resource.node_role),
            "leader_capability_class": leader_resource.capability_class,
            "secondary_capability_class": secondary_capability_class(leader_resource),
            "coverage_cell": leader_resource.coverage_cell or "",
        }
        if not self.last_plan.converged:
            self._transition(C2Health.SUSPECT, now_s, "fallback_consensus_not_converged")
        return self.last_plan

    def merge_recovery(
        self,
        center_assignments: Iterable[Assignment],
        fallback_assignments: Iterable[Assignment],
        human_accept: bool,
        now_s: float,
    ) -> MergeResult:
        center_by_task = self._group_assignments(center_assignments)
        fallback_by_task = self._group_assignments(fallback_assignments)
        accepted: list[str] = []
        review: list[str] = []
        conflicts: list[str] = []
        merged: dict[str, Assignment] = {}

        for task_id in sorted(set(center_by_task) | set(fallback_by_task)):
            center_items = center_by_task.get(task_id, [])
            fallback_items = fallback_by_task.get(task_id, [])
            if len(center_items) > 1 or len(fallback_items) > 1:
                conflicts.append(task_id)
                continue
            center = center_items[0] if center_items else None
            fallback = fallback_items[0] if fallback_items else None
            if center and fallback:
                if center.owner == fallback.owner and center.epoch >= fallback.epoch:
                    accepted.append(task_id)
                    merged[task_id] = center
                elif center.epoch < fallback.epoch:
                    conflicts.append(task_id)
                    merged[task_id] = fallback
                else:
                    conflicts.append(task_id)
                    merged[task_id] = center
            elif center:
                review.append(task_id)
                merged[task_id] = center
            elif fallback:
                review.append(task_id)
                merged[task_id] = fallback

        restored = human_accept and not conflicts and not review
        self._transition(
            C2Health.NORMAL if restored else C2Health.DEGRADED,
            now_s,
            "dual_track_merge_accepted" if restored else "dual_track_merge_review",
        )
        return MergeResult(
            accepted=accepted,
            review=review,
            conflicts=conflicts,
            merged_assignments=merged,
            restored_normal=restored,
        )

    def _transition(self, new_state: C2Health, now_s: float, reason: str) -> C2Health:
        if new_state == self.health:
            return self.health
        old_state = self.health
        self.health = new_state
        self.transition_log.append(
            HealthTransition(
                from_state=old_state,
                to_state=new_state,
                time_s=now_s,
                reason=reason,
                epoch=self.epoch,
            )
        )
        return self.health

    @staticmethod
    def _group_assignments(assignments: Iterable[Assignment]) -> dict[str, list[Assignment]]:
        grouped: dict[str, list[Assignment]] = {}
        for assignment in assignments:
            grouped.setdefault(assignment.task_id, []).append(assignment)
        return grouped

    def _safe_hold_result(self, now_s: float, reason: str) -> CBBAResult:
        del now_s
        result = CBBAResult(
            assignments={},
            consensus_rounds=0,
            converged=False,
            conflict_count=0,
            completion_rate=0.0,
            messages_sent=0,
            messages_delivered=0,
            messages_dropped=0,
            estimated_bytes=0,
            duration_s=0.0,
            final_views={"reason": {"state": reason}},
        )
        self.last_plan = result
        return result

    @staticmethod
    def _coordination_mode(leader: ResourceSummary) -> str:
        if is_secondary_node_resource(leader):
            return "secondary_node"
        return "distributed_cbba"

    @staticmethod
    def _resource_covers_task_cells(resource: ResourceSummary, task_cells: set[str]) -> bool:
        if not task_cells or not is_secondary_node_resource(resource):
            return True
        return (
            resource.coverage_cell is None
            or resource.coverage_cell == ""
            or resource.coverage_cell in task_cells
            or (
                resource.secondary_coverage_ratio is not None
                and resource.secondary_coverage_ratio > 0.0
            )
        )
