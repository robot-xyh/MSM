"""Simplified CBBA negotiator for continuity-only offline planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from .models import (
    Assignment,
    AvailabilityBand,
    BidState,
    CBBACostGapBenchmark,
    CBBAResult,
    CommBand,
    ConfidenceBand,
    ResourceSummary,
    TrackSummary,
    to_jsonable,
)
from .network import SimulatedNetwork


CONFIDENCE_SCORE = {
    ConfidenceBand.LOW: 1.0,
    ConfidenceBand.MEDIUM: 2.0,
    ConfidenceBand.HIGH: 3.0,
}
AVAILABILITY_SCORE = {
    AvailabilityBand.NONE: 0.0,
    AvailabilityBand.LOW: 1.0,
    AvailabilityBand.MEDIUM: 2.0,
    AvailabilityBand.HIGH: 3.0,
}
COMM_SCORE = {
    CommBand.POOR: 0.5,
    CommBand.LIMITED: 1.0,
    CommBand.GOOD: 1.5,
}


def _constraints_hash(node_id: str, task: TrackSummary, resource: ResourceSummary) -> str:
    raw = f"{node_id}|{task.coarse_cell}|{resource.capability_class}|{resource.epoch}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _is_better(candidate: BidState, incumbent: BidState | None) -> bool:
    if incumbent is None:
        return candidate.score > 0.0
    if candidate.epoch > incumbent.epoch:
        return True
    if candidate.epoch < incumbent.epoch:
        return False
    if candidate.score > incumbent.score + 1e-9:
        return True
    if candidate.score < incumbent.score - 1e-9:
        return False
    if candidate.bidder != incumbent.bidder:
        return candidate.bidder < incumbent.bidder
    return candidate.constraints_hash < incumbent.constraints_hash


@dataclass
class CBBAAgent:
    node_id: str
    resource: ResourceSummary
    epoch: int
    bundle_limit: int = 1
    bundle: list[str] = field(default_factory=list)
    winners: dict[str, BidState] = field(default_factory=dict)

    def merge_bid_states(self, bids: list[BidState]) -> None:
        for bid in bids:
            if bid.epoch < self.epoch:
                continue
            current = self.winners.get(bid.task_id)
            if _is_better(bid, current):
                self.winners[bid.task_id] = bid
                if current and current.bidder == self.node_id and bid.bidder != self.node_id:
                    self._release_from(bid.task_id)

    def rebuild_bundle(self, tasks: list[TrackSummary], round_id: int) -> None:
        self.bundle = [
            task_id
            for task_id in self.bundle
            if self.winners.get(task_id) and self.winners[task_id].bidder == self.node_id
        ]
        while len(self.bundle) < self.bundle_limit:
            candidate = self._best_insertable_task(tasks, round_id)
            if candidate is None:
                break
            self.winners[candidate.task_id] = candidate
            self.bundle.append(candidate.task_id)

    def winner_payload(self) -> dict[str, list[dict[str, object]]]:
        ordered = sorted(self.winners.values(), key=lambda bid: bid.task_id)
        return {"bids": [bid.to_dict() for bid in ordered]}

    def _best_insertable_task(self, tasks: list[TrackSummary], round_id: int) -> BidState | None:
        scored: list[BidState] = []
        for task in tasks:
            if task.epoch != self.epoch or task.track_id in self.bundle:
                continue
            score = self.score_task(task) - 0.15 * len(self.bundle)
            if score <= 0.0:
                continue
            bid = BidState(
                task_id=task.track_id,
                bidder=self.node_id,
                score=float(score),
                constraints_hash=_constraints_hash(self.node_id, task, self.resource),
                epoch=self.epoch,
                round_id=round_id,
            )
            incumbent = self.winners.get(task.track_id)
            if incumbent is None or _is_better(bid, incumbent):
                scored.append(bid)
        if not scored:
            return None
        scored.sort(key=lambda bid: (-bid.score, bid.task_id, bid.constraints_hash))
        return scored[0]

    def score_task(self, task: TrackSummary) -> float:
        if self.resource.operator_hold:
            return 0.0
        availability = AVAILABILITY_SCORE[self.resource.availability_band]
        if availability <= 0.0:
            return 0.0
        confidence = CONFIDENCE_SCORE[task.confidence_band]
        comm = COMM_SCORE[self.resource.comm_band]
        capability = self._capability_match(task)
        age_penalty = min(max(task.age_s, 0.0), 30.0) / 30.0
        source_bonus = min(task.source_count, 3) * 0.15
        vector = np.array([confidence, availability, comm, capability, source_bonus, age_penalty])
        weights = np.array([2.0, 1.4, 0.5, 1.2, 1.0, -0.8])
        base_score = float(np.dot(vector, weights))
        visual_adjustment = self._distributed_visual_adjustment(task)
        if visual_adjustment is None:
            return 0.0
        return max(0.0, base_score + visual_adjustment)

    def _distributed_visual_adjustment(self, task: TrackSummary) -> float | None:
        """Convert D5 peer-visual evidence into a conservative CBBA score term.

        D4 treats this evidence as advisory. It never creates a new global ID;
        missing, stale, or conflicting global IDs disable executable bids for
        the affected task because CBBA cannot safely anchor the visual tracklet
        to the center-owned tactical picture.
        """

        evidence = task.visual_evidence
        if not evidence.has_evidence:
            return 0.0

        if evidence.friend_conflict:
            return None
        if (
            evidence.stale_global_track_id
            or evidence.missing_global_track_id
            or evidence.global_track_id_conflict
        ):
            return None
        if self.node_id in evidence.hold_resource_ids:
            return None

        adjustment = 0.0
        support_set = set(evidence.visual_support_resource_ids)
        ambiguous_set = set(evidence.ambiguous_resource_ids)
        duplicate_set = set(evidence.duplicate_lock_resource_ids)

        if self.node_id in support_set:
            if evidence.hypothesis_only:
                adjustment += min(0.75, 0.25 + 0.4 * evidence.terminal_confidence)
            else:
                adjustment += min(
                    2.75,
                    0.6
                    + 1.4 * evidence.terminal_confidence
                    + 0.25 * min(evidence.support_count, 4),
                )
        elif support_set:
            adjustment -= 1.25

        if self.node_id in ambiguous_set:
            adjustment -= 1.25
        adjustment -= min(max(evidence.terminal_ambiguity, 0.0), 1.0) * 1.0

        if evidence.duplicate_terminal_lock_risk:
            if self.node_id in duplicate_set:
                adjustment -= 2.5
            else:
                adjustment -= 0.75

        if evidence.local_id_conflict:
            adjustment -= 1.0
        return adjustment

    def _capability_match(self, task: TrackSummary) -> float:
        if self.resource.capability_class == "observe":
            return 1.0
        if self.resource.capability_class == "relay":
            return 0.85 if task.source_count <= 2 else 0.65
        if self.resource.capability_class == "hold":
            return 0.2
        return 0.5

    def _release_from(self, task_id: str) -> None:
        if task_id not in self.bundle:
            return
        index = self.bundle.index(task_id)
        released = self.bundle[index:]
        self.bundle = self.bundle[:index]
        for released_task in released:
            current = self.winners.get(released_task)
            if current and current.bidder == self.node_id:
                del self.winners[released_task]


@dataclass
class CBBANegotiator:
    node_ids: list[str]
    epoch: int = 1
    bundle_limit: int = 1
    max_rounds: int = 20
    round_period_s: float = 0.5

    def run(
        self,
        tasks: list[TrackSummary],
        resources: list[ResourceSummary],
        network: SimulatedNetwork,
        start_time_s: float = 0.0,
    ) -> CBBAResult:
        resource_by_node = {resource.node_id: resource for resource in resources}
        agents = {
            node_id: CBBAAgent(
                node_id=node_id,
                resource=resource_by_node[node_id],
                epoch=self.epoch,
                bundle_limit=self.bundle_limit,
            )
            for node_id in self.node_ids
            if node_id in resource_by_node
        }
        task_ids = [task.track_id for task in tasks if task.epoch == self.epoch]
        now_s = start_time_s
        conflict_count = 0
        converged = False
        rounds_used = 0

        for round_id in range(self.max_rounds):
            rounds_used = round_id + 1
            delivered = network.drain_due(now_s)
            for node_id, messages in delivered.items():
                if node_id not in agents:
                    continue
                bids: list[BidState] = []
                for message in messages:
                    if message.kind != "cbba_state" or message.epoch != self.epoch:
                        continue
                    bids.extend(BidState.from_dict(item) for item in message.payload.get("bids", []))
                agents[node_id].merge_bid_states(bids)

            for agent in agents.values():
                agent.rebuild_bundle(tasks, round_id)

            conflict_count += self._round_conflicts(agents, task_ids)
            if self._views_converged(agents, task_ids):
                converged = True
                break

            for agent in agents.values():
                network.broadcast(
                    sender=agent.node_id,
                    kind="cbba_state",
                    payload=agent.winner_payload(),
                    now_s=now_s,
                    epoch=self.epoch,
                )
            now_s += self.round_period_s

        assignments = self._final_assignments(agents, task_ids) if converged else {}
        completion_rate = len(assignments) / len(task_ids) if task_ids and converged else 0.0
        if not task_ids:
            completion_rate = 1.0
        final_views = {
            node_id: {
                task_id: agent.winners[task_id].bidder
                for task_id in sorted(agent.winners)
                if task_id in task_ids
            }
            for node_id, agent in agents.items()
        }
        stats = network.stats
        return CBBAResult(
            assignments=assignments,
            consensus_rounds=rounds_used,
            converged=converged,
            conflict_count=conflict_count,
            completion_rate=completion_rate,
            messages_sent=stats.sent_count,
            messages_delivered=stats.delivered_count,
            messages_dropped=stats.dropped_count,
            estimated_bytes=stats.estimated_bytes,
            duration_s=max(0.0, now_s - start_time_s),
            final_views=final_views,
            assignment_audit=self._assignment_audit(tasks, assignments),
        )

    @staticmethod
    def _views_converged(agents: dict[str, CBBAAgent], task_ids: list[str]) -> bool:
        if not agents:
            return False
        signatures = []
        for agent in agents.values():
            signature = []
            for task_id in task_ids:
                bid = agent.winners.get(task_id)
                signature.append((task_id, bid.bidder if bid else None, round(bid.score, 9) if bid else None))
            signatures.append(tuple(signature))
        return len(set(signatures)) == 1

    @staticmethod
    def _round_conflicts(agents: dict[str, CBBAAgent], task_ids: list[str]) -> int:
        conflicts = 0
        for task_id in task_ids:
            bidders = {
                agent.winners[task_id].bidder
                for agent in agents.values()
                if task_id in agent.winners
            }
            if len(bidders) > 1:
                conflicts += 1
        return conflicts

    @staticmethod
    def _final_assignments(
        agents: dict[str, CBBAAgent],
        task_ids: list[str],
    ) -> dict[str, Assignment]:
        best_by_task: dict[str, BidState] = {}
        for agent in agents.values():
            for task_id in task_ids:
                bid = agent.winners.get(task_id)
                if bid and _is_better(bid, best_by_task.get(task_id)):
                    best_by_task[task_id] = bid
        return {
            task_id: Assignment(
                task_id=task_id,
                owner=bid.bidder,
                score=bid.score,
                epoch=bid.epoch,
            )
            for task_id, bid in sorted(best_by_task.items())
        }

    @staticmethod
    def _assignment_audit(
        tasks: list[TrackSummary],
        assignments: dict[str, Assignment],
    ) -> dict[str, dict[str, object]]:
        audit: dict[str, dict[str, object]] = {}
        for task in tasks:
            evidence = task.visual_evidence
            if not evidence.has_evidence:
                continue
            assignment = assignments.get(task.track_id)
            audit[task.track_id] = {
                "owner": assignment.owner if assignment else None,
                "visual_support_resource_ids": evidence.visual_support_resource_ids,
                "hold_resource_ids": evidence.hold_resource_ids,
                "ambiguous_resource_ids": evidence.ambiguous_resource_ids,
                "duplicate_lock_resource_ids": evidence.duplicate_lock_resource_ids,
                "terminal_confidence": evidence.terminal_confidence,
                "terminal_ambiguity": evidence.terminal_ambiguity,
                "hypothesis_count": evidence.hypothesis_count,
                "support_count": evidence.support_count,
                "hypothesis_only": evidence.hypothesis_only,
                "stale_global_track_id": evidence.stale_global_track_id,
                "missing_global_track_id": evidence.missing_global_track_id,
                "duplicate_terminal_lock_risk": evidence.duplicate_terminal_lock_risk,
                "friend_conflict": evidence.friend_conflict,
                "global_track_id_conflict": evidence.global_track_id_conflict,
                "local_id_conflict": evidence.local_id_conflict,
                "risk_reasons": evidence.risk_reasons,
            }
        return audit


def build_cbba_cost_gap_benchmark(
    cbba_result: CBBAResult,
    *,
    center_assignments: Mapping[str, str | Assignment],
    cost_by_task_resource: Mapping[str, Mapping[str, float]],
    benchmark_source: str = "d3_hungarian_cost_matrix",
    attach_to_result: bool = False,
) -> CBBACostGapBenchmark:
    """Compare a D4 CBBA result with a D3 centralized plan on the same costs.

    D4 does not run Hungarian or min-cost flow here. The centralized owner for
    each task must come from D3/main, together with the cost matrix used for
    that plan. This helper only computes the offline benchmark deltas.
    """

    center_owner_by_task = {
        str(task_id): _assignment_owner(owner)
        for task_id, owner in center_assignments.items()
    }
    cbba_owner_by_task = {
        str(task_id): assignment.owner
        for task_id, assignment in cbba_result.assignments.items()
    }
    task_ids = tuple(
        sorted(
            set(cost_by_task_resource)
            | set(center_owner_by_task)
            | set(cbba_owner_by_task)
        )
    )
    center_costs, missing_center_costs = _assignment_costs(
        center_owner_by_task,
        cost_by_task_resource,
    )
    cbba_costs, missing_cbba_costs = _assignment_costs(
        cbba_owner_by_task,
        cost_by_task_resource,
    )
    center_total = _total_cost_or_none(center_costs, missing_center_costs)
    cbba_total = _total_cost_or_none(cbba_costs, missing_cbba_costs)
    absolute_gap = None
    relative_gap = None
    if cbba_total is not None and center_total is not None:
        absolute_gap = cbba_total - center_total
        if abs(center_total) > 1e-12:
            relative_gap = absolute_gap / abs(center_total)

    per_task_gap: dict[str, float | None] = {}
    for task_id in task_ids:
        center_cost = center_costs.get(task_id)
        cbba_cost = cbba_costs.get(task_id)
        per_task_gap[task_id] = (
            cbba_cost - center_cost
            if center_cost is not None and cbba_cost is not None
            else None
        )

    center_completion = len(center_owner_by_task) / len(task_ids) if task_ids else 1.0
    benchmark = CBBACostGapBenchmark(
        benchmark_source=benchmark_source,
        cbba_total_cost=cbba_total,
        center_total_cost=center_total,
        absolute_cost_gap=absolute_gap,
        relative_cost_gap=relative_gap,
        cbba_assignment_count=len(cbba_owner_by_task),
        center_assignment_count=len(center_owner_by_task),
        common_assignment_count=len(set(cbba_owner_by_task) & set(center_owner_by_task)),
        cbba_completion_rate=cbba_result.completion_rate,
        center_completion_rate=center_completion,
        completion_rate_gap=cbba_result.completion_rate - center_completion,
        cbba_conflict_count=cbba_result.conflict_count,
        cbba_consensus_rounds=cbba_result.consensus_rounds,
        cbba_messages_sent=cbba_result.messages_sent,
        missing_cbba_task_ids=tuple(
            sorted(set(center_owner_by_task) - set(cbba_owner_by_task))
        ),
        extra_cbba_task_ids=tuple(
            sorted(set(cbba_owner_by_task) - set(center_owner_by_task))
        ),
        missing_cost_pairs=tuple(sorted(set(missing_center_costs) | set(missing_cbba_costs))),
        per_task_cost_gap=per_task_gap,
    )
    if attach_to_result:
        cbba_result.cost_gap_benchmark = benchmark
    return benchmark


def build_cbba_d6_metadata(
    cbba_result: CBBAResult,
    *,
    failover_time_s: float | None = None,
    degradation_mode: str = "passive",
    coordination_mode: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build stable D6/multi-seed metadata from a D4 CBBA fallback result.

    D4 does not publish a system-level AssignmentPlan here. The helper only
    normalizes already-computed CBBA metrics, coordination-mode metadata, audit
    details, and the optional D3/main-provided cost-gap benchmark.
    """

    coordination = _coordination_metadata(cbba_result, coordination_mode)
    mode = str(coordination.get("state") or "distributed_cbba")
    d4_action = (
        "degrade_to_secondary"
        if mode == "secondary_node"
        else "degrade_to_distributed"
    )
    metadata: dict[str, object] = {
        "d4_action": d4_action,
        "degradation_mode": degradation_mode,
        "selected_coordinator": mode,
        "coordination_mode": mode,
        "leader_id": coordination.get("leader_id"),
        "leader_role": coordination.get("leader_role"),
        "leader_capability_class": coordination.get("leader_capability_class"),
        "secondary_capability_class": coordination.get("secondary_capability_class"),
        "coverage_cell": coordination.get("coverage_cell"),
        "failover_time": failover_time_s,
        "consensus_rounds": cbba_result.consensus_rounds,
        "converged": cbba_result.converged,
        "degraded_completion_rate": cbba_result.completion_rate,
        "assignment_completion_rate": cbba_result.completion_rate,
        "assignment_count": len(cbba_result.assignments),
        "conflict_count": cbba_result.conflict_count,
        "messages_sent": cbba_result.messages_sent,
        "messages_delivered": cbba_result.messages_delivered,
        "messages_dropped": cbba_result.messages_dropped,
        "estimated_bytes": cbba_result.estimated_bytes,
        "duration_s": cbba_result.duration_s,
        "final_views": cbba_result.final_views,
        "assignment_audit": cbba_result.assignment_audit,
    }
    metadata.update(_cost_gap_metadata(cbba_result.cost_gap_benchmark))
    return to_jsonable(metadata)


def _assignment_owner(owner: str | Assignment) -> str:
    if isinstance(owner, Assignment):
        return owner.owner
    return str(owner)


def _assignment_costs(
    owner_by_task: Mapping[str, str],
    cost_by_task_resource: Mapping[str, Mapping[str, float]],
) -> tuple[dict[str, float], list[str]]:
    costs: dict[str, float] = {}
    missing: list[str] = []
    for task_id, owner in owner_by_task.items():
        task_costs = cost_by_task_resource.get(task_id)
        if task_costs is None or owner not in task_costs:
            missing.append(f"{task_id}:{owner}")
            continue
        costs[task_id] = float(task_costs[owner])
    return costs, missing


def _total_cost_or_none(costs: Mapping[str, float], missing_costs: list[str]) -> float | None:
    if missing_costs:
        return None
    return float(sum(costs.values()))


def _coordination_metadata(
    cbba_result: CBBAResult,
    coordination_mode: Mapping[str, object] | None,
) -> dict[str, object]:
    raw = coordination_mode
    if raw is None:
        raw = cbba_result.final_views.get("coordination_mode", {})
    try:
        metadata = dict(raw or {})
    except (TypeError, ValueError):
        metadata = {}
    return {
        "state": metadata.get("state") or "distributed_cbba",
        "leader_id": metadata.get("leader_id"),
        "leader_role": metadata.get("leader_role"),
        "leader_capability_class": metadata.get("leader_capability_class"),
        "secondary_capability_class": metadata.get("secondary_capability_class"),
        "coverage_cell": metadata.get("coverage_cell"),
    }


def _cost_gap_metadata(
    benchmark: CBBACostGapBenchmark | None,
) -> dict[str, object]:
    if benchmark is None:
        return {
            "cost_gap_available": False,
            "cost_gap_benchmark": None,
            "benchmark_source": None,
            "cbba_total_cost": None,
            "center_total_cost": None,
            "absolute_cost_gap": None,
            "relative_cost_gap": None,
            "cbba_assignment_count": None,
            "center_assignment_count": None,
            "common_assignment_count": None,
            "cbba_completion_rate": None,
            "center_completion_rate": None,
            "completion_rate_gap": None,
            "cbba_conflict_count": None,
            "cbba_consensus_rounds": None,
            "cbba_messages_sent": None,
            "missing_cbba_task_ids": (),
            "extra_cbba_task_ids": (),
            "missing_cost_pairs": (),
            "per_task_cost_gap": {},
        }
    return {
        "cost_gap_available": True,
        "cost_gap_benchmark": benchmark.to_dict(),
        "benchmark_source": benchmark.benchmark_source,
        "cbba_total_cost": benchmark.cbba_total_cost,
        "center_total_cost": benchmark.center_total_cost,
        "absolute_cost_gap": benchmark.absolute_cost_gap,
        "relative_cost_gap": benchmark.relative_cost_gap,
        "cbba_assignment_count": benchmark.cbba_assignment_count,
        "center_assignment_count": benchmark.center_assignment_count,
        "common_assignment_count": benchmark.common_assignment_count,
        "cbba_completion_rate": benchmark.cbba_completion_rate,
        "center_completion_rate": benchmark.center_completion_rate,
        "completion_rate_gap": benchmark.completion_rate_gap,
        "cbba_conflict_count": benchmark.cbba_conflict_count,
        "cbba_consensus_rounds": benchmark.cbba_consensus_rounds,
        "cbba_messages_sent": benchmark.cbba_messages_sent,
        "missing_cbba_task_ids": benchmark.missing_cbba_task_ids,
        "extra_cbba_task_ids": benchmark.extra_cbba_task_ids,
        "missing_cost_pairs": benchmark.missing_cost_pairs,
        "per_task_cost_gap": benchmark.per_task_cost_gap,
    }
