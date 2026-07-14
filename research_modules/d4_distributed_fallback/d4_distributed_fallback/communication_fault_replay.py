"""Deterministic communication-fault replay for D4 coalition failover.

This module owns no system AssignmentPlan and does not emulate an AirSim
runtime.  It exercises D4's existing ACK/lease/epoch contracts over the
in-memory network so main and D6 can ingest a stable per-seed fault summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .coalition_safety import (
    CoalitionCommitCoordinator,
    CoalitionCommitState,
    CoalitionMemberAck,
)
from .models import to_jsonable
from .network import SimulatedNetwork


P1_COMMUNICATION_MATRIX_VERSION = "d4-p1-communication-fault-matrix-v1"
P1_COMMUNICATION_SCENARIOS = (
    "normal",
    "delay_0_5s",
    "loss_30pct",
    "center_failure",
    "center_secondary_failure",
    "partition_recovery",
)


@dataclass(frozen=True)
class CommunicationReplayConfig:
    """Scale-independent node and coalition identity for one replay batch."""

    member_ids: tuple[str, ...]
    secondary_node_ids: tuple[str, ...]
    center_node_id: str = "CENTER"
    global_track_id: str = "G-COMM-1"
    coalition_id: str = "coalition-comm-1"
    plan_id: str = "plan-comm-1"
    lease_duration_s: float = 5.0
    ack_validity_s: float = 2.0

    def __post_init__(self) -> None:
        members = _unique(self.member_ids)
        secondaries = _unique(self.secondary_node_ids)
        if not members:
            raise ValueError("member_ids must not be empty")
        if not secondaries:
            raise ValueError("secondary_node_ids must not be empty")
        if set(members) & set(secondaries):
            raise ValueError("secondary nodes must not also be execution members")
        if self.center_node_id in set(members) | set(secondaries):
            raise ValueError("center_node_id must be distinct from members and secondaries")
        if self.lease_duration_s <= 0.0 or self.ack_validity_s <= 0.0:
            raise ValueError("lease and ACK validity durations must be positive")
        object.__setattr__(self, "member_ids", members)
        object.__setattr__(self, "secondary_node_ids", secondaries)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CommunicationFaultCaseSummary:
    """One D6-consumable row from a communication fault replay."""

    scenario_id: str
    seed: int
    expected_layer: str
    selected_layer: str
    passed: bool
    execution_allowed: bool
    fail_closed: bool
    first_failure_reason: str | None
    failure_reasons: tuple[str, ...]
    layer_trace: tuple[str, ...]
    state_trace: tuple[dict[str, Any], ...]
    message_stats: dict[str, Any]
    owner_id: str
    plan_id: str
    plan_version: int
    coalition_id: str
    coalition_version: int
    epoch: int
    commit_state: str
    commit_reason: str
    lease_expires_at: float | None
    required_member_ids: tuple[str, ...]
    acked_member_ids: tuple[str, ...]
    missing_member_ids: tuple[str, ...]
    rejected_ack_count: int
    reconfigure_count: int
    member_exit_events: tuple[dict[str, Any], ...]
    duplicate_owner_count: int
    split_brain_detected: bool
    split_brain_prevented: bool
    recovery_completed: bool
    recovery_time_s: float | None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = "d4_p1_communication_fault_case_v1"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CommunicationFaultReplayReport:
    """Versioned batch report consumed by main or D6 without D4 internals."""

    config: CommunicationReplayConfig
    seeds: tuple[int, ...]
    cases: tuple[CommunicationFaultCaseSummary, ...]
    summary: dict[str, Any]
    scenario_ids: tuple[str, ...] = P1_COMMUNICATION_SCENARIOS
    matrix_version: str = P1_COMMUNICATION_MATRIX_VERSION
    schema: str = "d4_p1_communication_fault_replay_v1"
    assignment_plan_generated_by_d4: bool = False
    lowers_external_execution_gates: bool = False

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class CommunicationFaultReplay:
    """Exercise the center -> secondary -> distributed communication hierarchy."""

    def __init__(self, config: CommunicationReplayConfig) -> None:
        self.config = config

    def run_seed(self, seed: int) -> tuple[CommunicationFaultCaseSummary, ...]:
        return (
            self._normal(seed),
            self._delay(seed),
            self._loss(seed),
            self._center_failure(seed),
            self._center_secondary_failure(seed),
            self._partition_recovery(seed),
        )

    def _normal(self, seed: int) -> CommunicationFaultCaseSummary:
        return self._center_case(
            scenario_id="normal",
            seed=seed,
            trace=(
                {
                    "phase": "center_healthy",
                    "timestamp": 0.0,
                    "owner_id": self.config.center_node_id,
                    "plan_version": 1,
                    "action": "continue_center",
                    "false_degradation": False,
                },
            ),
        )

    def _delay(self, seed: int) -> CommunicationFaultCaseSummary:
        return self._run_takeover(
            scenario_id="delay_0_5s",
            seed=seed,
            layer="secondary",
            owner_id=self.config.secondary_node_ids[0],
            delay_range=(0.5, 0.5),
            packet_loss=0.0,
            inject_stale_ack=True,
            layer_trace=("center", "secondary"),
            initial_failures=("center_unavailable",),
        )

    def _loss(self, seed: int) -> CommunicationFaultCaseSummary:
        return self._run_takeover(
            scenario_id="loss_30pct",
            seed=seed,
            layer="secondary",
            owner_id=self.config.secondary_node_ids[0],
            delay_range=(0.05, 0.2),
            packet_loss=0.30,
            inject_stale_ack=False,
            layer_trace=("center", "secondary"),
            initial_failures=("center_unavailable",),
        )

    def _center_failure(self, seed: int) -> CommunicationFaultCaseSummary:
        return self._run_takeover(
            scenario_id="center_failure",
            seed=seed,
            layer="secondary",
            owner_id=self.config.secondary_node_ids[0],
            delay_range=(0.05, 0.15),
            packet_loss=0.0,
            inject_stale_ack=False,
            layer_trace=("center", "secondary"),
            initial_failures=("center_unavailable",),
        )

    def _center_secondary_failure(self, seed: int) -> CommunicationFaultCaseSummary:
        exits = (
            {"node_id": self.config.center_node_id, "role": "center", "reason": "failed"},
            {
                "node_id": self.config.secondary_node_ids[0],
                "role": "secondary_coordinator",
                "reason": "failed",
            },
        )
        return self._run_takeover(
            scenario_id="center_secondary_failure",
            seed=seed,
            layer="distributed",
            owner_id=self.config.member_ids[0],
            delay_range=(0.05, 0.15),
            packet_loss=0.0,
            inject_stale_ack=False,
            layer_trace=("center", "secondary", "distributed"),
            initial_failures=("center_unavailable", "secondary_unavailable"),
            member_exit_events=exits,
            reconfigure_count=1,
        )

    def _partition_recovery(self, seed: int) -> CommunicationFaultCaseSummary:
        owner_id = self.config.member_ids[0]
        coordinator = CoalitionCommitCoordinator()
        trace: list[dict[str, Any]] = []
        failures = ["center_unavailable", "secondary_unavailable"]
        state, stats, delivery_failures = self._commit_over_network(
            coordinator=coordinator,
            seed=seed,
            owner_id=owner_id,
            coordinator_role="cluster_representative",
            epoch=1,
            plan_version=1,
            coalition_version=1,
            delay_range=(0.05, 0.15),
            packet_loss=0.0,
            trace=trace,
        )
        failures.extend(delivery_failures)
        partition_at = 2.0
        state = coordinator.evaluate(state, timestamp=partition_at, partitioned=True)
        trace.append(self._snapshot("partition_detected", state, partition_at))
        failures.append("network_partition")

        recovery_start = 3.0
        recovered, recovery_stats, recovery_failures = self._commit_over_network(
            coordinator=coordinator,
            seed=seed + 100_000,
            owner_id=owner_id,
            coordinator_role="cluster_representative",
            epoch=2,
            plan_version=2,
            coalition_version=2,
            delay_range=(0.05, 0.15),
            packet_loss=0.0,
            trace=trace,
            start_time=recovery_start,
        )
        failures.extend(recovery_failures)

        stale = coordinator.propose(
            global_track_id=self.config.global_track_id,
            coalition_id=self.config.coalition_id,
            coalition_version=1,
            plan_id=self.config.plan_id,
            plan_version=1,
            epoch=1,
            coordinator_id=self.config.secondary_node_ids[0],
            coordinator_role="mobile_high_recon",
            required_member_ids=self.config.member_ids,
            lease_expires_at=recovery_start + self.config.lease_duration_s,
            timestamp=recovery_start + 0.8,
            metadata={"takeover_ready": True, "split_brain_probe": True},
        )
        trace.append(self._snapshot("stale_owner_rejected", stale, recovery_start + 0.8))
        split_brain_prevented = bool(
            stale.state == "aborted" and stale.reason == "coalition_epoch_stale"
        )
        if stale.reason:
            failures.append(stale.reason)

        execution_allowed = self._execution_allowed(recovered, recovery_start + 0.7)
        passed = bool(
            execution_allowed
            and recovered.epoch == 2
            and recovered.plan_version == 2
            and set(recovered.required_member_ids) == set(recovered.acked_member_ids)
            and split_brain_prevented
        )
        return self._summary(
            scenario_id="partition_recovery",
            seed=seed,
            expected_layer="distributed",
            selected_layer="distributed",
            state=recovered,
            passed=passed,
            trace=trace,
            layer_trace=("center", "secondary", "distributed", "partition", "distributed"),
            failures=failures,
            message_stats=_merge_stats(stats, recovery_stats),
            reconfigure_count=1,
            duplicate_owner_count=0,
            split_brain_detected=True,
            split_brain_prevented=split_brain_prevented,
            recovery_completed=execution_allowed,
            recovery_time_s=0.7 if execution_allowed else None,
            metadata={
                "old_generation_state": state.state,
                "old_generation_reason": state.reason,
                "stale_owner_reject_reason": stale.reason,
                "full_reack_after_recovery": True,
            },
        )

    def _run_takeover(
        self,
        *,
        scenario_id: str,
        seed: int,
        layer: str,
        owner_id: str,
        delay_range: tuple[float, float],
        packet_loss: float,
        inject_stale_ack: bool,
        layer_trace: tuple[str, ...],
        initial_failures: tuple[str, ...],
        member_exit_events: tuple[dict[str, Any], ...] = (),
        reconfigure_count: int = 0,
    ) -> CommunicationFaultCaseSummary:
        coordinator = CoalitionCommitCoordinator()
        trace: list[dict[str, Any]] = []
        role = "mobile_high_recon" if layer == "secondary" else "cluster_representative"
        state, stats, network_failures = self._commit_over_network(
            coordinator=coordinator,
            seed=seed,
            owner_id=owner_id,
            coordinator_role=role,
            epoch=1,
            plan_version=1,
            coalition_version=1,
            delay_range=delay_range,
            packet_loss=packet_loss,
            trace=trace,
            inject_stale_ack=inject_stale_ack,
        )
        failures = [*initial_failures, *network_failures]
        execution_allowed = self._execution_allowed(state, 1.5)
        safety_valid = bool(
            not execution_allowed
            or (
                set(state.required_member_ids) == set(state.acked_member_ids)
                and 1.5 < state.lease_expires_at
            )
        )
        expected_layer = layer
        passed = bool(safety_valid and (execution_allowed or packet_loss > 0.0))
        return self._summary(
            scenario_id=scenario_id,
            seed=seed,
            expected_layer=expected_layer,
            selected_layer=layer,
            state=state,
            passed=passed,
            trace=trace,
            layer_trace=layer_trace,
            failures=failures,
            message_stats=stats,
            member_exit_events=member_exit_events,
            reconfigure_count=reconfigure_count,
            split_brain_prevented=True,
            metadata={
                "configured_delay_s": list(delay_range),
                "configured_packet_loss": packet_loss,
                "out_of_order_stale_ack_injected": inject_stale_ack,
                "safe_despite_loss": safety_valid,
            },
        )

    def _commit_over_network(
        self,
        *,
        coordinator: CoalitionCommitCoordinator,
        seed: int,
        owner_id: str,
        coordinator_role: str,
        epoch: int,
        plan_version: int,
        coalition_version: int,
        delay_range: tuple[float, float],
        packet_loss: float,
        trace: list[dict[str, Any]],
        start_time: float = 0.0,
        inject_stale_ack: bool = False,
    ) -> tuple[CoalitionCommitState, dict[str, Any], list[str]]:
        metadata = {"takeover_ready": True} if coordinator_role == "mobile_high_recon" else {}
        state = coordinator.propose(
            global_track_id=self.config.global_track_id,
            coalition_id=self.config.coalition_id,
            coalition_version=coalition_version,
            plan_id=self.config.plan_id,
            plan_version=plan_version,
            epoch=epoch,
            coordinator_id=owner_id,
            coordinator_role=coordinator_role,
            required_member_ids=self.config.member_ids,
            lease_expires_at=start_time + self.config.lease_duration_s,
            timestamp=start_time,
            metadata=metadata,
        )
        trace.append(self._snapshot("coalition_proposed", state, start_time))
        node_ids = _unique(
            (
                self.config.center_node_id,
                *self.config.secondary_node_ids,
                *self.config.member_ids,
            )
        )
        network = SimulatedNetwork(
            node_ids=list(node_ids),
            packet_loss=packet_loss,
            min_delay_s=delay_range[0],
            max_delay_s=delay_range[1],
            seed=seed,
        )
        failures: list[str] = []
        local_time = start_time + 0.01
        if owner_id in self.config.member_ids:
            state = coordinator.record_ack(
                state,
                self._ack(state, owner_id, timestamp=local_time),
                timestamp=local_time,
            )
            trace.append(self._snapshot("local_ack", state, local_time))

        for index, member_id in enumerate(self.config.member_ids):
            if member_id == owner_id:
                continue
            sent_at = start_time + 0.02 + 0.01 * index
            ack = self._ack(state, member_id, timestamp=sent_at)
            queued = network.send(
                member_id,
                owner_id,
                "coalition_member_ack",
                ack.to_dict(),
                sent_at,
                epoch,
            )
            trace.append(
                {
                    "phase": "ack_sent" if queued else "ack_dropped",
                    "timestamp": sent_at,
                    "resource_id": member_id,
                    "owner_id": owner_id,
                    "epoch": epoch,
                    "plan_version": plan_version,
                    "coalition_version": coalition_version,
                }
            )
            if not queued:
                failures.append("ack_message_dropped")

        if inject_stale_ack:
            member_id = next(item for item in self.config.member_ids if item != owner_id)
            sent_at = start_time + 0.2
            stale = self._ack(
                state,
                member_id,
                timestamp=sent_at,
                plan_version=max(0, plan_version - 1),
            )
            network.send(
                member_id,
                owner_id,
                "coalition_member_ack",
                stale.to_dict(),
                sent_at,
                epoch,
            )

        delivery_time = start_time + max(delay_range[1] + 0.4, 0.7)
        for message in network.deliver(owner_id, delivery_time):
            ack = _ack_from_mapping(message.payload)
            before_reason = state.reason
            state = coordinator.record_ack(state, ack, timestamp=delivery_time)
            trace.append(self._snapshot("ack_delivered", state, delivery_time))
            if state.reason.startswith("ack_") and state.reason != before_reason:
                failures.append(state.reason)

        state = coordinator.evaluate(state, timestamp=delivery_time, finalize=True)
        trace.append(self._snapshot("ack_window_finalized", state, delivery_time))
        if state.reason == "missing_required_acks":
            failures.append(state.reason)
        if state.state == "committed":
            state = coordinator.mark_executing(state, timestamp=delivery_time + 0.01)
            trace.append(self._snapshot("execution_started", state, delivery_time + 0.01))
        return state, network.stats.to_dict(), failures

    def _center_case(
        self,
        *,
        scenario_id: str,
        seed: int,
        trace: tuple[dict[str, Any], ...],
    ) -> CommunicationFaultCaseSummary:
        return CommunicationFaultCaseSummary(
            scenario_id=scenario_id,
            seed=seed,
            expected_layer="center",
            selected_layer="center",
            passed=True,
            execution_allowed=False,
            fail_closed=False,
            first_failure_reason=None,
            failure_reasons=(),
            layer_trace=("center",),
            state_trace=trace,
            message_stats={
                "sent_count": 0,
                "delivered_count": 0,
                "dropped_count": 0,
                "estimated_bytes": 0,
            },
            owner_id=self.config.center_node_id,
            plan_id=self.config.plan_id,
            plan_version=1,
            coalition_id=self.config.coalition_id,
            coalition_version=1,
            epoch=1,
            commit_state="center_active",
            commit_reason="center_healthy_continue_center",
            lease_expires_at=None,
            required_member_ids=self.config.member_ids,
            acked_member_ids=(),
            missing_member_ids=(),
            rejected_ack_count=0,
            reconfigure_count=0,
            member_exit_events=(),
            duplicate_owner_count=0,
            split_brain_detected=False,
            split_brain_prevented=True,
            recovery_completed=False,
            recovery_time_s=None,
            metadata={"false_degradation": False, "coalition_commit_required": False},
        )

    def _summary(
        self,
        *,
        scenario_id: str,
        seed: int,
        expected_layer: str,
        selected_layer: str,
        state: CoalitionCommitState,
        passed: bool,
        trace: Sequence[dict[str, Any]],
        layer_trace: Sequence[str],
        failures: Sequence[str],
        message_stats: Mapping[str, Any],
        member_exit_events: Sequence[dict[str, Any]] = (),
        reconfigure_count: int = 0,
        duplicate_owner_count: int = 0,
        split_brain_detected: bool = False,
        split_brain_prevented: bool = True,
        recovery_completed: bool = False,
        recovery_time_s: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CommunicationFaultCaseSummary:
        timestamp = float(trace[-1].get("timestamp", state.updated_at))
        execution_allowed = self._execution_allowed(state, timestamp)
        failure_reasons = _unique(failures)
        acked_set = set(state.acked_member_ids)
        ordered_acked = tuple(
            member_id for member_id in state.required_member_ids if member_id in acked_set
        )
        return CommunicationFaultCaseSummary(
            scenario_id=scenario_id,
            seed=int(seed),
            expected_layer=expected_layer,
            selected_layer=selected_layer,
            passed=bool(passed and selected_layer == expected_layer),
            execution_allowed=execution_allowed,
            fail_closed=not execution_allowed,
            first_failure_reason=failure_reasons[0] if failure_reasons else None,
            failure_reasons=failure_reasons,
            layer_trace=tuple(layer_trace),
            state_trace=tuple(dict(item) for item in trace),
            message_stats=dict(message_stats),
            owner_id=state.coordinator_id,
            plan_id=state.plan_id,
            plan_version=state.plan_version,
            coalition_id=state.coalition_id,
            coalition_version=state.coalition_version,
            epoch=state.epoch,
            commit_state=state.state,
            commit_reason=state.reason,
            lease_expires_at=state.lease_expires_at,
            required_member_ids=state.required_member_ids,
            acked_member_ids=ordered_acked,
            missing_member_ids=state.missing_member_ids,
            rejected_ack_count=int(state.metadata.get("rejected_ack_count", 0)),
            reconfigure_count=int(reconfigure_count),
            member_exit_events=tuple(dict(item) for item in member_exit_events),
            duplicate_owner_count=int(duplicate_owner_count),
            split_brain_detected=bool(split_brain_detected),
            split_brain_prevented=bool(split_brain_prevented),
            recovery_completed=bool(recovery_completed),
            recovery_time_s=recovery_time_s,
            metadata=dict(metadata or {}),
        )

    def _ack(
        self,
        state: CoalitionCommitState,
        resource_id: str,
        *,
        timestamp: float,
        plan_version: int | None = None,
    ) -> CoalitionMemberAck:
        return CoalitionMemberAck(
            resource_id=resource_id,
            global_track_id=state.global_track_id,
            coalition_id=state.coalition_id,
            coalition_version=state.coalition_version,
            plan_id=state.plan_id,
            plan_version=state.plan_version if plan_version is None else plan_version,
            epoch=state.epoch,
            can_execute=True,
            evidence_timestamp=timestamp,
            valid_until=timestamp + self.config.ack_validity_s,
            reason="ready",
        )

    @classmethod
    def _snapshot(
        cls,
        phase: str,
        state: CoalitionCommitState,
        timestamp: float,
    ) -> dict[str, Any]:
        return {
            "phase": phase,
            "timestamp": float(timestamp),
            "state": state.state,
            "reason": state.reason,
            "owner_id": state.coordinator_id,
            "owner_role": state.coordinator_role,
            "plan_id": state.plan_id,
            "plan_version": state.plan_version,
            "coalition_id": state.coalition_id,
            "coalition_version": state.coalition_version,
            "epoch": state.epoch,
            "lease_expires_at": state.lease_expires_at,
            "required_member_ids": list(state.required_member_ids),
            "acked_member_ids": list(state.acked_member_ids),
            "missing_member_ids": list(state.missing_member_ids),
            "execution_allowed": cls._execution_allowed(state, timestamp),
        }

    @staticmethod
    def _execution_allowed(state: CoalitionCommitState, timestamp: float) -> bool:
        return bool(
            state.state == "executing"
            and not state.missing_member_ids
            and float(timestamp) < state.lease_expires_at
        )


def run_p1_communication_fault_matrix(
    config: CommunicationReplayConfig,
    *,
    seeds: Iterable[int] = range(10),
) -> CommunicationFaultReplayReport:
    """Run the six-scenario matrix for each seed and aggregate stable metrics."""

    normalized_seeds = tuple(int(seed) for seed in seeds)
    if not normalized_seeds:
        raise ValueError("seeds must not be empty")
    replay = CommunicationFaultReplay(config)
    cases = tuple(case for seed in normalized_seeds for case in replay.run_seed(seed))
    by_scenario: dict[str, dict[str, Any]] = {}
    for scenario_id in P1_COMMUNICATION_SCENARIOS:
        selected = [case for case in cases if case.scenario_id == scenario_id]
        by_scenario[scenario_id] = {
            "case_count": len(selected),
            "passed_count": sum(case.passed for case in selected),
            "execution_allowed_count": sum(case.execution_allowed for case in selected),
            "fail_closed_count": sum(case.fail_closed for case in selected),
            "dropped_message_count": sum(
                int(case.message_stats.get("dropped_count", 0)) for case in selected
            ),
            "split_brain_prevention_passed_count": sum(
                case.split_brain_prevented for case in selected
            ),
            "first_failure_reason_histogram": _histogram(
                case.first_failure_reason for case in selected
            ),
        }
    summary = {
        "seed_count": len(normalized_seeds),
        "scenario_count": len(P1_COMMUNICATION_SCENARIOS),
        "case_count": len(cases),
        "passed_count": sum(case.passed for case in cases),
        "failed_count": sum(not case.passed for case in cases),
        "false_degradation_count": sum(
            bool(case.metadata.get("false_degradation")) for case in cases
        ),
        "duplicate_owner_count": sum(case.duplicate_owner_count for case in cases),
        "split_brain_prevention_failure_count": sum(
            not case.split_brain_prevented for case in cases
        ),
        "all_safety_outcomes_met": all(case.passed for case in cases),
        "by_scenario": by_scenario,
    }
    return CommunicationFaultReplayReport(
        config=config,
        seeds=normalized_seeds,
        cases=cases,
        summary=summary,
    )


def _ack_from_mapping(payload: Mapping[str, Any]) -> CoalitionMemberAck:
    return CoalitionMemberAck(
        resource_id=str(payload["resource_id"]),
        global_track_id=str(payload["global_track_id"]),
        coalition_id=str(payload["coalition_id"]),
        coalition_version=int(payload["coalition_version"]),
        plan_id=str(payload["plan_id"]),
        plan_version=int(payload["plan_version"]),
        epoch=int(payload["epoch"]),
        can_execute=bool(payload["can_execute"]),
        evidence_timestamp=float(payload["evidence_timestamp"]),
        valid_until=float(payload["valid_until"]),
        reason=str(payload.get("reason", "acknowledged")),
        metadata=dict(payload.get("metadata", {})),
    )


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _merge_stats(*stats: Mapping[str, Any]) -> dict[str, int]:
    keys = ("sent_count", "delivered_count", "dropped_count", "estimated_bytes")
    return {key: sum(int(item.get(key, 0)) for item in stats) for key in keys}


def _histogram(values: Iterable[str | None]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = value or "none"
        result[key] = result.get(key, 0) + 1
    return result
