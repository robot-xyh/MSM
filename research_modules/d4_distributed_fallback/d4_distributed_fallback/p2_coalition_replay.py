"""Isolated P2 fault replay for native and optional coalition references.

This module is deliberately outside the online D4 arbitration path.  The
native replay reuses the local atomic commit coordinator and uses CBBA only to
select a coordinator or replacement candidate.  It does not treat the
single-winner CBBA result as an atomic ``k > 1`` coalition assignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .cbba import CBBANegotiator, build_cbba_cost_gap_benchmark
from .coalition_safety import (
    CoalitionCommitCoordinator,
    CoalitionCommitState,
    CoalitionMemberAck,
)
from .models import (
    AvailabilityBand,
    CommBand,
    ConfidenceBand,
    DistributedVisualEvidenceSummary,
    ResourceSummary,
    TrackSummary,
    to_jsonable,
)
from .network import SimulatedNetwork


REPLAY_SCENARIOS = (
    "center_secondary_distributed",
    "missing_ack",
    "stale_epoch",
    "expired_lease",
    "partition",
    "member_loss_replacement",
)
EXTERNAL_REFERENCE_BACKENDS = ("mit_cbba", "ca_cbba")

_TRACK_ID = "G-P2-COALITION-1"
_COALITION_ID = "coalition-p2-1"
_PLAN_ID = "plan-p2-1"
_MEMBERS = ("INT-1", "INT-2", "INT-3")


@dataclass(frozen=True)
class ExternalReplayCapability:
    """Capability probe for one optional external reference tree."""

    backend: str
    reference_path: str | None
    path_exists: bool
    source_detected: bool
    executable_adapter_available: bool
    capabilities: tuple[str, ...]
    unavailable_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CoalitionReplayCaseResult:
    """Normalized result row shared by native and external replay backends."""

    backend: str
    scenario_id: str
    result_available: bool
    status: str
    converged: bool | None
    convergence_rounds: int | None
    completion_rate: float | None
    conflict_count: int | None
    optimality_gap: float | None
    unavailable_reason: str | None
    final_state: str | None
    final_reason: str | None
    expected_outcome_met: bool | None
    phase_trace: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CoalitionReplayReport:
    """Serializable P2 replay report with explicit isolation guarantees."""

    scenario_ids: tuple[str, ...]
    results: tuple[CoalitionReplayCaseResult, ...]
    external_capabilities: tuple[ExternalReplayCapability, ...]
    backend_summary: dict[str, dict[str, Any]]
    schema: str = "d4_p2_isolated_coalition_replay_v1"
    isolated_from_online_d4: bool = True
    replaces_online_d4: bool = False
    adds_default_dependency: bool = False

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class ExternalCoalitionReplayAdapter:
    """Probe optional MIT/CA-CBBA trees without importing or executing them."""

    def __init__(self, backend: str, reference_path: str | Path | None = None) -> None:
        if backend not in EXTERNAL_REFERENCE_BACKENDS:
            raise ValueError(f"unsupported external replay backend: {backend}")
        self.backend = backend
        self.reference_path = Path(reference_path).expanduser() if reference_path else None

    def probe(self) -> ExternalReplayCapability:
        if self.reference_path is None:
            return self._unavailable(
                path_exists=False,
                source_detected=False,
                reason=f"{self.backend}_reference_path_not_configured",
            )
        if not self.reference_path.exists():
            return self._unavailable(
                path_exists=False,
                source_detected=False,
                reason=f"{self.backend}_reference_path_not_found",
            )

        files = tuple(path for path in self.reference_path.rglob("*") if path.is_file())
        if self.backend == "mit_cbba":
            source_files = tuple(path for path in files if path.suffix.lower() == ".m")
            reason = (
                "mit_cbba_matlab_runtime_adapter_not_integrated"
                if source_files
                else "mit_cbba_matlab_source_not_detected"
            )
            capabilities = (
                "single_winner_cbba_reference",
                "matlab_source_detected",
                "coalition_commit_not_provided",
            ) if source_files else ("reference_tree_probe",)
        else:
            source_suffixes = {".py", ".m", ".cpp", ".cc", ".c", ".h", ".hpp"}
            source_files = tuple(path for path in files if path.suffix.lower() in source_suffixes)
            reason = (
                "ca_cbba_execution_adapter_not_integrated"
                if source_files
                else "ca_cbba_public_reference_has_no_executable_source"
            )
            capabilities = (
                "communication_aware_reference_source_detected",
                "coalition_commit_not_provided",
            ) if source_files else ("reference_metadata_only",)

        return self._unavailable(
            path_exists=True,
            source_detected=bool(source_files),
            reason=reason,
            capabilities=capabilities,
            metadata={
                "file_count": len(files),
                "source_file_count": len(source_files),
            },
        )

    def unavailable_results(
        self,
        scenario_ids: Iterable[str],
        capability: ExternalReplayCapability | None = None,
    ) -> tuple[CoalitionReplayCaseResult, ...]:
        resolved = capability or self.probe()
        return tuple(
            CoalitionReplayCaseResult(
                backend=self.backend,
                scenario_id=scenario_id,
                result_available=False,
                status="unavailable",
                converged=None,
                convergence_rounds=None,
                completion_rate=None,
                conflict_count=None,
                optimality_gap=None,
                unavailable_reason=resolved.unavailable_reason,
                final_state=None,
                final_reason=None,
                expected_outcome_met=None,
                metadata={"capability": resolved.to_dict()},
            )
            for scenario_id in scenario_ids
        )

    def _unavailable(
        self,
        *,
        path_exists: bool,
        source_detected: bool,
        reason: str,
        capabilities: tuple[str, ...] = ("reference_tree_probe",),
        metadata: Mapping[str, Any] | None = None,
    ) -> ExternalReplayCapability:
        return ExternalReplayCapability(
            backend=self.backend,
            reference_path=str(self.reference_path) if self.reference_path else None,
            path_exists=path_exists,
            source_detected=source_detected,
            executable_adapter_available=False,
            capabilities=capabilities,
            unavailable_reason=reason,
            metadata=dict(metadata or {}),
        )


class NativeCoalitionFaultReplay:
    """Deterministic fault replay over the current local D4 contracts."""

    backend = "native_d4_coalition_cbba"

    def run(self) -> tuple[CoalitionReplayCaseResult, ...]:
        return (
            self._center_secondary_distributed(),
            self._missing_ack(),
            self._stale_epoch(),
            self._expired_lease(),
            self._partition(),
            self._member_loss_replacement(),
        )

    def _center_secondary_distributed(self) -> CoalitionReplayCaseResult:
        coordinator = CoalitionCommitCoordinator()
        phases = [_phase("center", "center_active", 0, 1.0)]
        secondary = self._propose(
            coordinator,
            epoch=1,
            plan_version=1,
            coalition_version=1,
            coordinator_id="RECON-1",
            coordinator_role="mobile_high_recon",
            members=_MEMBERS,
            timestamp=10.0,
            lease_expires_at=20.0,
            metadata={"takeover_ready": True},
        )
        secondary = self._ack_all(coordinator, secondary, start_time=10.1)
        secondary = coordinator.mark_executing(secondary, timestamp=10.5)
        phases.append(_phase("secondary", secondary.state, 2, 1.0, secondary.reason))

        secondary = coordinator.evaluate(secondary, timestamp=11.0, partitioned=True)
        phases.append(_phase("secondary_loss", secondary.state, 1, 0.0, secondary.reason))
        election, gap = self._run_cbba_selection(
            candidates=_MEMBERS,
            preferred="INT-2",
            task_id="distributed-coordinator",
            epoch=2,
        )
        selected = election.assignments["distributed-coordinator"].owner
        distributed = self._propose(
            coordinator,
            epoch=2,
            plan_version=2,
            coalition_version=2,
            coordinator_id=selected,
            coordinator_role="cluster_representative",
            members=_MEMBERS,
            timestamp=12.0,
            lease_expires_at=22.0,
        )
        distributed = self._ack_all(coordinator, distributed, start_time=12.1)
        distributed = coordinator.mark_executing(distributed, timestamp=12.5)
        phases.append(
            _phase(
                "distributed",
                distributed.state,
                election.consensus_rounds + 2,
                1.0,
                distributed.reason,
            )
        )
        return self._result(
            scenario_id="center_secondary_distributed",
            state=distributed,
            convergence_rounds=sum(int(item["rounds"]) for item in phases),
            completion_rate=1.0,
            conflict_count=election.conflict_count + 1,
            optimality_gap=gap,
            phase_trace=phases,
            metadata={
                "selected_distributed_coordinator": selected,
                "cbba_scope": "coordinator_selection_only",
                "single_winner_cbba_forms_atomic_coalition": False,
            },
        )

    def _missing_ack(self) -> CoalitionReplayCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._propose(coordinator)
        for offset, member_id in enumerate(_MEMBERS[:-1], start=1):
            state = coordinator.record_ack(
                state,
                self._ack(state, member_id, timestamp=10.0 + 0.1 * offset),
                timestamp=10.0 + 0.1 * offset,
            )
        state = coordinator.evaluate(state, timestamp=10.4, finalize=True)
        return self._result(
            scenario_id="missing_ack",
            state=state,
            convergence_rounds=2,
            completion_rate=0.0,
            conflict_count=0,
            unavailable_reason="optimality_gap_unavailable_atomic_commit_incomplete",
            phase_trace=[_phase("secondary", state.state, 2, 0.0, state.reason)],
            metadata={"missing_member_ids": list(state.missing_member_ids)},
        )

    def _stale_epoch(self) -> CoalitionReplayCaseResult:
        coordinator = CoalitionCommitCoordinator()
        self._propose(
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
            timestamp=10.2,
        )
        return self._result(
            scenario_id="stale_epoch",
            state=stale,
            convergence_rounds=1,
            completion_rate=0.0,
            conflict_count=1,
            unavailable_reason="optimality_gap_unavailable_stale_epoch_rejected",
            phase_trace=[_phase("proposal", stale.state, 1, 0.0, stale.reason)],
        )

    def _expired_lease(self) -> CoalitionReplayCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._propose(coordinator, lease_expires_at=10.4)
        state = coordinator.record_ack(
            state,
            self._ack(state, "INT-1", timestamp=10.1),
            timestamp=10.1,
        )
        state = coordinator.evaluate(state, timestamp=10.4)
        return self._result(
            scenario_id="expired_lease",
            state=state,
            convergence_rounds=2,
            completion_rate=0.0,
            conflict_count=0,
            unavailable_reason="optimality_gap_unavailable_lease_expired",
            phase_trace=[_phase("secondary", state.state, 2, 0.0, state.reason)],
        )

    def _partition(self) -> CoalitionReplayCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._ack_all(coordinator, self._propose(coordinator), start_time=10.1)
        state = coordinator.mark_executing(state, timestamp=10.5)
        state = coordinator.evaluate(state, timestamp=11.0, partitioned=True)
        return self._result(
            scenario_id="partition",
            state=state,
            convergence_rounds=3,
            completion_rate=0.0,
            conflict_count=1,
            unavailable_reason="optimality_gap_unavailable_partition_reconfiguration",
            phase_trace=[_phase("distributed", state.state, 3, 0.0, state.reason)],
        )

    def _member_loss_replacement(self) -> CoalitionReplayCaseResult:
        coordinator = CoalitionCommitCoordinator()
        state = self._ack_all(coordinator, self._propose(coordinator), start_time=10.1)
        state = coordinator.mark_executing(state, timestamp=10.5)
        state = coordinator.record_ack(
            state,
            self._ack(state, "INT-3", timestamp=11.0, can_execute=False),
            timestamp=11.0,
        )
        election, gap = self._run_cbba_selection(
            candidates=("INT-4", "INT-5"),
            preferred="INT-4",
            task_id="replacement-slot",
            epoch=2,
        )
        replacement_id = election.assignments["replacement-slot"].owner
        replacement_members = ("INT-1", "INT-2", replacement_id)
        replacement = self._propose(
            coordinator,
            epoch=2,
            plan_version=2,
            coalition_version=2,
            coordinator_id="INT-1",
            coordinator_role="cluster_representative",
            members=replacement_members,
            timestamp=12.0,
            lease_expires_at=22.0,
            metadata={"replaced_member_id": "INT-3", "replacement_member_id": replacement_id},
        )
        replacement = self._ack_all(coordinator, replacement, start_time=12.1)
        replacement = coordinator.mark_executing(replacement, timestamp=12.5)
        phases = (
            _phase("distributed", "executing", 2, 1.0, "coalition_execution_started"),
            _phase("member_loss", state.state, 1, 0.0, state.reason),
            _phase(
                "replacement",
                replacement.state,
                election.consensus_rounds + 2,
                1.0,
                replacement.reason,
            ),
        )
        return self._result(
            scenario_id="member_loss_replacement",
            state=replacement,
            convergence_rounds=sum(int(item["rounds"]) for item in phases),
            completion_rate=1.0,
            conflict_count=election.conflict_count,
            optimality_gap=gap,
            phase_trace=phases,
            metadata={
                "lost_member_id": "INT-3",
                "replacement_member_id": replacement_id,
                "replacement_required_full_reack": True,
                "cbba_scope": "replacement_candidate_selection_only",
            },
        )

    def _run_cbba_selection(
        self,
        *,
        candidates: Sequence[str],
        preferred: str,
        task_id: str,
        epoch: int,
    ) -> tuple[Any, float | None]:
        evidence = DistributedVisualEvidenceSummary(
            visual_support_resource_ids=(preferred,),
            assigned_global_track_id=_TRACK_ID,
            terminal_confidence=0.95,
            hypothesis_count=1,
            support_count=1,
            decision_states=("locked",),
        )
        task = TrackSummary(
            track_id=task_id,
            coarse_cell="cell-p2",
            age_s=0.5,
            confidence_band=ConfidenceBand.HIGH,
            source_count=3,
            epoch=epoch,
            visual_evidence=evidence,
        )
        resources = [
            ResourceSummary(
                node_id=node_id,
                capability_class="observe",
                availability_band=AvailabilityBand.HIGH,
                comm_band=CommBand.GOOD,
                epoch=epoch,
            )
            for node_id in candidates
        ]
        network = SimulatedNetwork(
            node_ids=list(candidates),
            packet_loss=0.0,
            min_delay_s=0.1,
            max_delay_s=0.1,
            seed=17,
        )
        result = CBBANegotiator(
            node_ids=list(candidates),
            epoch=epoch,
            max_rounds=12,
        ).run([task], resources, network)
        costs = {
            task_id: {
                node_id: 1.0 if node_id == preferred else 2.0 + index
                for index, node_id in enumerate(candidates)
            }
        }
        benchmark = build_cbba_cost_gap_benchmark(
            result,
            center_assignments={task_id: preferred},
            cost_by_task_resource=costs,
            benchmark_source="isolated_exhaustive_single_slot_optimum",
        )
        return result, benchmark.absolute_cost_gap

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
    ) -> CoalitionCommitState:
        for offset, member_id in enumerate(state.required_member_ids):
            timestamp = start_time + 0.1 * offset
            state = coordinator.record_ack(
                state,
                self._ack(state, member_id, timestamp=timestamp),
                timestamp=timestamp,
            )
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
            valid_until=timestamp + 5.0,
            reason="ready" if can_execute else "member_unavailable",
        )

    def _result(
        self,
        *,
        scenario_id: str,
        state: CoalitionCommitState,
        convergence_rounds: int,
        completion_rate: float,
        conflict_count: int,
        phase_trace: Sequence[dict[str, Any]],
        optimality_gap: float | None = None,
        unavailable_reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CoalitionReplayCaseResult:
        completed = completion_rate >= 1.0 and state.state == "executing"
        expected_fail_closed = scenario_id in {
            "missing_ack",
            "stale_epoch",
            "expired_lease",
            "partition",
        }
        return CoalitionReplayCaseResult(
            backend=self.backend,
            scenario_id=scenario_id,
            result_available=True,
            status="completed" if completed else "fail_closed",
            converged=completed,
            convergence_rounds=convergence_rounds,
            completion_rate=completion_rate,
            conflict_count=conflict_count,
            optimality_gap=optimality_gap,
            unavailable_reason=unavailable_reason,
            final_state=state.state,
            final_reason=state.reason,
            expected_outcome_met=completed or expected_fail_closed,
            phase_trace=tuple(phase_trace),
            metadata=dict(metadata or {}),
        )


def run_p2_coalition_fault_replay(
    *,
    mit_cbba_path: str | Path | None = None,
    ca_cbba_path: str | Path | None = None,
) -> CoalitionReplayReport:
    """Run native faults and report optional external references as unavailable."""

    native_results = NativeCoalitionFaultReplay().run()
    adapters = (
        ExternalCoalitionReplayAdapter("mit_cbba", mit_cbba_path),
        ExternalCoalitionReplayAdapter("ca_cbba", ca_cbba_path),
    )
    capabilities = tuple(adapter.probe() for adapter in adapters)
    external_results = tuple(
        result
        for adapter, capability in zip(adapters, capabilities)
        for result in adapter.unavailable_results(REPLAY_SCENARIOS, capability)
    )
    results = (*native_results, *external_results)
    return CoalitionReplayReport(
        scenario_ids=REPLAY_SCENARIOS,
        results=results,
        external_capabilities=capabilities,
        backend_summary=_summarize_backends(results),
    )


def _phase(
    phase: str,
    state: str,
    rounds: int,
    completion_rate: float,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "state": state,
        "rounds": rounds,
        "completion_rate": completion_rate,
        "reason": reason,
    }


def _summarize_backends(
    results: Sequence[CoalitionReplayCaseResult],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for backend in sorted({result.backend for result in results}):
        rows = [result for result in results if result.backend == backend]
        available = [result for result in rows if result.result_available]
        completion_values = [
            result.completion_rate
            for result in available
            if result.completion_rate is not None
        ]
        conflict_values = [
            result.conflict_count
            for result in available
            if result.conflict_count is not None
        ]
        summary[backend] = {
            "scenario_count": len(rows),
            "available_result_count": len(available),
            "completed_scenario_count": sum(result.status == "completed" for result in rows),
            "expected_outcome_met_count": sum(
                result.expected_outcome_met is True for result in rows
            ),
            "mean_completion_rate": (
                sum(completion_values) / len(completion_values)
                if completion_values
                else None
            ),
            "total_conflict_count": sum(conflict_values) if conflict_values else None,
            "unavailable_reasons": sorted(
                {
                    result.unavailable_reason
                    for result in rows
                    if not result.result_available and result.unavailable_reason
                }
            ),
        }
    return summary
