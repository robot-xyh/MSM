"""Deterministic P1 replay for D4 secondary and distributed failover safety.

The replay exercises the online D4 commit contracts without constructing a
system AssignmentPlan.  It is intentionally deterministic so main and D6 can
use the versioned result as a regression fixture before AirSim fault injection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .active_degradation import (
    ActiveDegradationArbiter,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    DegradationAction,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
)
from .coalition_safety import (
    CoalitionCommitCoordinator,
    CoalitionCommitState,
    CoalitionMemberAck,
)
from .models import C2Health, to_jsonable


P1_FAILOVER_MATRIX_VERSION = "d4-p1-fallback-matrix-v1"
P1_FAILOVER_SCENARIOS = (
    "normal_center_no_false_degradation",
    "secondary_takeover_full_ack",
    "missing_ack_fail_closed",
    "member_loss_replacement",
    "network_partition_recovery",
    "stale_epoch_rejected",
    "expired_lease_fail_closed",
    "digest_conflict_fail_closed",
    "center_recovery_dual_track_audit",
)

_TRACK_ID = "G-P1-COALITION-1"
_COALITION_ID = "coalition-p1-1"
_PLAN_ID = "plan-p1-1"
_MEMBERS = ("INT-1", "INT-2", "INT-3")


@dataclass(frozen=True)
class P1FailoverCaseResult:
    """One normalized row in the P1 failover disturbance matrix."""

    scenario_id: str
    expected_outcome: str
    passed: bool
    final_state: str
    final_reason: str
    execution_allowed: bool
    fail_closed: bool
    state_trace: tuple[dict[str, Any], ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class P1FailoverReplayReport:
    """Versioned D4-only replay report for main and D6 ingestion."""

    scenario_ids: tuple[str, ...]
    cases: tuple[P1FailoverCaseResult, ...]
    summary: dict[str, Any]
    matrix_version: str = P1_FAILOVER_MATRIX_VERSION
    schema: str = "d4_p1_failover_disturbance_replay_v1"
    assignment_plan_generated_by_d4: bool = False
    lowers_external_execution_gates: bool = False

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class P1FailoverDisturbanceReplay:
    """Run the D4 P1 failover and recovery disturbance matrix."""

    def run(self) -> tuple[P1FailoverCaseResult, ...]:
        return (
            self._normal_center(),
            self._secondary_takeover(),
            self._missing_ack(),
            self._member_loss_replacement(),
            self._partition_recovery(),
            self._stale_epoch(),
            self._expired_lease(),
            self._digest_conflict(),
            self._center_recovery(),
        )

    def _normal_center(self) -> P1FailoverCaseResult:
        decision = ActiveDegradationArbiter().evaluate(
            TrackUncertaintySummary(
                track_id=_TRACK_ID,
                coverage_cell="cell-p1",
                position_sigma_m=2.0,
                covariance_trace=12.0,
                measurement_age_s=0.1,
            ),
            AssociationRiskSummary(track_id=_TRACK_ID),
            AssignmentValiditySummary(
                global_track_id=_TRACK_ID,
                assigned_resource_id="INT-1",
                plan_version=1,
            ),
            TerminalAssociationSummary(
                resource_id="INT-1",
                assigned_global_track_id=_TRACK_ID,
                observed_global_track_id=_TRACK_ID,
                decision_state=TerminalDecisionState.LOCKED,
                association_confidence=0.95,
                ambiguity_score=0.02,
                coverage_cell="cell-p1",
            ),
            C2Health.NORMAL,
            secondary_nodes=[],
            current_time_s=1.0,
        )
        passed = decision.action == DegradationAction.CONTINUE_CENTER
        return P1FailoverCaseResult(
            scenario_id="normal_center_no_false_degradation",
            expected_outcome="continue_center_without_false_degradation",
            passed=passed,
            final_state="center_active",
            final_reason=decision.reason,
            execution_allowed=False,
            fail_closed=False,
            state_trace=(
                {
                    "phase": "center_healthy",
                    "timestamp": 1.0,
                    "d4_action": decision.action.value,
                    "degradation_mode": decision.mode.value,
                },
            ),
            metadata={
                "false_degradation": decision.action
                != DegradationAction.CONTINUE_CENTER,
                "coalition_commit_required": False,
            },
        )

    def _secondary_takeover(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._propose(
            coordinator,
            coordinator_id="RECON-1",
            coordinator_role="mobile_high_recon",
            metadata={"takeover_ready": True},
        )
        trace = [self._snapshot("secondary_proposed", state, 10.0)]
        state = self._ack_all(coordinator, state, start_time=10.1, trace=trace)
        state = coordinator.mark_executing(state, timestamp=10.5)
        trace.append(self._snapshot("secondary_executing", state, 10.5))
        allowed = self._execution_allowed(state, 10.5)
        return self._case(
            "secondary_takeover_full_ack",
            "secondary_executes_only_after_all_required_acks",
            state,
            trace,
            passed=allowed and state.coordinator_id == "RECON-1",
            timestamp=10.5,
            metadata={"fallback_mode": "secondary", "ack_required": True},
        )

    def _missing_ack(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._propose(coordinator)
        trace = [self._snapshot("proposed", state, 10.0)]
        for offset, member_id in enumerate(_MEMBERS[:-1], start=1):
            timestamp = 10.0 + 0.1 * offset
            state = coordinator.record_ack(
                state,
                self._ack(state, member_id, timestamp=timestamp),
                timestamp=timestamp,
            )
            trace.append(self._snapshot("ack_received", state, timestamp))
        state = coordinator.evaluate(state, timestamp=10.4, finalize=True)
        trace.append(self._snapshot("ack_deadline", state, 10.4))
        return self._case(
            "missing_ack_fail_closed",
            "missing_required_ack_blocks_execution",
            state,
            trace,
            passed=(
                state.state == "aborted"
                and state.reason == "missing_required_acks"
                and state.missing_member_ids == ("INT-3",)
            ),
            timestamp=10.4,
        )

    def _member_loss_replacement(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._ack_all(coordinator, self._propose(coordinator), start_time=10.1)
        state = coordinator.mark_executing(state, timestamp=10.5)
        trace = [self._snapshot("initial_executing", state, 10.5)]
        state = coordinator.record_ack(
            state,
            self._ack(state, "INT-3", timestamp=11.0, can_execute=False),
            timestamp=11.0,
        )
        trace.append(self._snapshot("member_lost", state, 11.0))

        replacement_members = ("INT-1", "INT-2", "INT-4")
        replacement = self._propose(
            coordinator,
            epoch=2,
            plan_version=2,
            coalition_version=2,
            members=replacement_members,
            timestamp=12.0,
            lease_expires_at=22.0,
            metadata={"replaced_member_id": "INT-3", "replacement_member_id": "INT-4"},
        )
        trace.append(self._snapshot("replacement_proposed", replacement, 12.0))
        replacement = self._ack_all(
            coordinator,
            replacement,
            start_time=12.1,
            trace=trace,
        )
        replacement = coordinator.mark_executing(replacement, timestamp=12.5)
        trace.append(self._snapshot("replacement_executing", replacement, 12.5))
        passed = bool(
            state.state == "reconfiguring"
            and replacement.state == "executing"
            and replacement.epoch == 2
            and replacement.required_member_ids == replacement.acked_member_ids
            and replacement.required_member_ids == replacement_members
        )
        return self._case(
            "member_loss_replacement",
            "member_loss_requires_new_generation_and_full_reack",
            replacement,
            trace,
            passed=passed,
            timestamp=12.5,
            metadata={
                "lost_member_id": "INT-3",
                "replacement_member_id": "INT-4",
                "replacement_required_full_reack": True,
            },
        )

    def _partition_recovery(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._ack_all(coordinator, self._propose(coordinator), start_time=10.1)
        state = coordinator.mark_executing(state, timestamp=10.5)
        trace = [self._snapshot("initial_executing", state, 10.5)]
        state = coordinator.evaluate(state, timestamp=11.0, partitioned=True)
        trace.append(self._snapshot("partition_detected", state, 11.0))

        recovered = self._propose(
            coordinator,
            epoch=2,
            plan_version=2,
            coalition_version=2,
            timestamp=12.0,
            lease_expires_at=22.0,
            metadata={"recovery_reason": "network_partition_recovered"},
        )
        trace.append(self._snapshot("recovery_proposed", recovered, 12.0))
        recovered = self._ack_all(
            coordinator,
            recovered,
            start_time=12.1,
            trace=trace,
        )
        recovered = coordinator.mark_executing(recovered, timestamp=12.5)
        trace.append(self._snapshot("recovery_executing", recovered, 12.5))
        passed = bool(
            state.state == "reconfiguring"
            and state.reason == "network_partition"
            and recovered.state == "executing"
            and recovered.epoch == 2
            and not recovered.missing_member_ids
        )
        return self._case(
            "network_partition_recovery",
            "partition_revokes_execution_until_new_generation_full_reack",
            recovered,
            trace,
            passed=passed,
            timestamp=12.5,
            metadata={"partition_fail_closed": True, "full_reack_after_recovery": True},
        )

    def _stale_epoch(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        current = self._propose(
            coordinator,
            epoch=2,
            plan_version=2,
            coalition_version=2,
        )
        stale = self._propose(
            coordinator,
            epoch=1,
            plan_version=2,
            coalition_version=2,
            timestamp=10.1,
        )
        retained = coordinator.record_ack(
            current,
            self._ack(current, "INT-1", timestamp=10.2),
            timestamp=10.2,
        )
        trace = (
            self._snapshot("current_generation", current, 10.0),
            self._snapshot("stale_proposal_rejected", stale, 10.1),
            self._snapshot("current_generation_retained", retained, 10.2),
        )
        passed = bool(
            stale.state == "aborted"
            and stale.reason == "coalition_epoch_stale"
            and retained.epoch == 2
            and retained.acked_member_ids == ("INT-1",)
        )
        return self._case(
            "stale_epoch_rejected",
            "stale_epoch_does_not_replace_current_generation",
            stale,
            trace,
            passed=passed,
            timestamp=10.1,
            metadata={"retained_epoch": retained.epoch},
        )

    def _expired_lease(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._ack_all(
            coordinator,
            self._propose(coordinator, lease_expires_at=10.8),
            start_time=10.1,
        )
        state = coordinator.mark_executing(state, timestamp=10.5)
        trace = [self._snapshot("executing", state, 10.5)]
        state = coordinator.evaluate(state, timestamp=10.8)
        trace.append(self._snapshot("lease_expired", state, 10.8))
        return self._case(
            "expired_lease_fail_closed",
            "expired_lease_revokes_execution",
            state,
            trace,
            passed=state.state == "reconfiguring"
            and state.reason == "coalition_lease_expired",
            timestamp=10.8,
        )

    def _digest_conflict(self) -> P1FailoverCaseResult:
        coordinator = CoalitionCommitCoordinator()
        current = self._propose(coordinator)
        conflict = self._propose(
            coordinator,
            members=("INT-1", "INT-2", "INT-4"),
            timestamp=10.1,
        )
        trace = (
            self._snapshot("current_digest", current, 10.0),
            self._snapshot("conflicting_digest", conflict, 10.1),
        )
        return self._case(
            "digest_conflict_fail_closed",
            "same_generation_digest_conflict_is_rejected",
            conflict,
            trace,
            passed=conflict.state == "aborted"
            and conflict.reason == "coalition_digest_conflict",
            timestamp=10.1,
            metadata={
                "current_commit_digest": conflict.metadata.get("current_commit_digest"),
            },
        )

    def _center_recovery(self) -> P1FailoverCaseResult:
        local_coordinator = CoalitionCommitCoordinator()
        local = self._ack_all(
            local_coordinator,
            self._propose(
                local_coordinator,
                epoch=3,
                plan_version=3,
                coalition_version=3,
            ),
            start_time=10.1,
        )
        local = local_coordinator.mark_executing(local, timestamp=10.5)

        center_coordinator = CoalitionCommitCoordinator()
        recovered = self._propose(
            center_coordinator,
            epoch=4,
            plan_version=4,
            coalition_version=4,
            coordinator_id="CENTER-1",
            coordinator_role="ground_backup",
            timestamp=12.0,
            lease_expires_at=22.0,
            metadata={"recovered_center": True},
        )
        audit = local_coordinator.audit_recovery(local, recovered, timestamp=12.1)
        passed = bool(
            audit["decision"] == "dual_track_review_required"
            and audit["recovered_newer"] is True
            and audit["immediate_takeover_allowed"] is False
        )
        return P1FailoverCaseResult(
            scenario_id="center_recovery_dual_track_audit",
            expected_outcome="center_recovery_requires_dual_track_review_before_authority_change",
            passed=passed,
            final_state=str(audit["decision"]),
            final_reason="center_recovery_audit",
            execution_allowed=False,
            fail_closed=True,
            state_trace=(
                self._snapshot("local_distributed_executing", local, 10.5),
                self._snapshot("recovered_center_candidate", recovered, 12.0),
                {
                    "phase": "dual_track_audit",
                    "timestamp": 12.1,
                    **audit,
                },
            ),
            metadata={"recovery_audit": audit, "immediate_authority_change": False},
        )

    def _propose(
        self,
        coordinator: CoalitionCommitCoordinator,
        *,
        epoch: int = 1,
        plan_version: int = 1,
        coalition_version: int = 1,
        coordinator_id: str = "INT-1",
        coordinator_role: str = "cluster_representative",
        members: Sequence[str] = _MEMBERS,
        timestamp: float = 10.0,
        lease_expires_at: float = 20.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> CoalitionCommitState:
        return coordinator.propose(
            global_track_id=_TRACK_ID,
            coalition_id=_COALITION_ID,
            coalition_version=coalition_version,
            plan_id=_PLAN_ID,
            plan_version=plan_version,
            epoch=epoch,
            coordinator_id=coordinator_id,
            coordinator_role=coordinator_role,
            required_member_ids=members,
            lease_expires_at=lease_expires_at,
            timestamp=timestamp,
            metadata=metadata,
        )

    def _ack_all(
        self,
        coordinator: CoalitionCommitCoordinator,
        state: CoalitionCommitState,
        *,
        start_time: float,
        trace: list[dict[str, Any]] | None = None,
    ) -> CoalitionCommitState:
        for offset, member_id in enumerate(state.required_member_ids):
            timestamp = start_time + 0.1 * offset
            state = coordinator.record_ack(
                state,
                self._ack(state, member_id, timestamp=timestamp),
                timestamp=timestamp,
            )
            if trace is not None:
                trace.append(self._snapshot("ack_received", state, timestamp))
        return state

    @staticmethod
    def _ack(
        state: CoalitionCommitState,
        resource_id: str,
        *,
        timestamp: float,
        can_execute: bool = True,
    ) -> CoalitionMemberAck:
        return CoalitionMemberAck(
            resource_id=resource_id,
            global_track_id=state.global_track_id,
            coalition_id=state.coalition_id,
            coalition_version=state.coalition_version,
            plan_id=state.plan_id,
            plan_version=state.plan_version,
            epoch=state.epoch,
            can_execute=can_execute,
            evidence_timestamp=timestamp,
            valid_until=timestamp + 2.0,
            reason="ready" if can_execute else "member_unavailable",
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
            "epoch": state.epoch,
            "plan_version": state.plan_version,
            "coalition_version": state.coalition_version,
            "coordinator_id": state.coordinator_id,
            "required_member_ids": list(state.required_member_ids),
            "acked_member_ids": list(state.acked_member_ids),
            "missing_member_ids": list(state.missing_member_ids),
            "lease_expires_at": state.lease_expires_at,
            "execution_allowed": cls._execution_allowed(state, timestamp),
        }

    @staticmethod
    def _execution_allowed(state: CoalitionCommitState, timestamp: float) -> bool:
        return bool(
            state.state == "executing"
            and not state.missing_member_ids
            and float(timestamp) < state.lease_expires_at
        )

    @classmethod
    def _case(
        cls,
        scenario_id: str,
        expected_outcome: str,
        state: CoalitionCommitState,
        trace: Sequence[dict[str, Any]],
        *,
        passed: bool,
        timestamp: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> P1FailoverCaseResult:
        execution_allowed = cls._execution_allowed(state, timestamp)
        return P1FailoverCaseResult(
            scenario_id=scenario_id,
            expected_outcome=expected_outcome,
            passed=bool(passed),
            final_state=state.state,
            final_reason=state.reason,
            execution_allowed=execution_allowed,
            fail_closed=not execution_allowed,
            state_trace=tuple(trace),
            metadata=dict(metadata or {}),
        )


def run_p1_failover_disturbance_replay() -> P1FailoverReplayReport:
    """Run and summarize the deterministic D4 P1 disturbance matrix."""

    cases = P1FailoverDisturbanceReplay().run()
    false_degradation_count = sum(
        bool(case.metadata.get("false_degradation")) for case in cases
    )
    summary = {
        "matrix_version": P1_FAILOVER_MATRIX_VERSION,
        "scenario_count": len(cases),
        "passed_count": sum(case.passed for case in cases),
        "failed_count": sum(not case.passed for case in cases),
        "execution_allowed_count": sum(case.execution_allowed for case in cases),
        "fail_closed_count": sum(case.fail_closed for case in cases),
        "false_degradation_count": false_degradation_count,
        "all_expected_outcomes_met": all(case.passed for case in cases),
    }
    return P1FailoverReplayReport(
        scenario_ids=P1_FAILOVER_SCENARIOS,
        cases=cases,
        summary=summary,
    )
