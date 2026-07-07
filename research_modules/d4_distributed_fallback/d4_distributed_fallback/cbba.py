"""Simplified CBBA negotiator for continuity-only offline planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from .models import (
    Assignment,
    AvailabilityBand,
    BidState,
    CBBAResult,
    CommBand,
    ConfidenceBand,
    ResourceSummary,
    TrackSummary,
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
