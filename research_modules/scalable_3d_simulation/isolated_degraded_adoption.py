"""Post-application D4 evidence for isolated degraded physical continuations.

The main-owned producer uses D4's public verifier after a cloned world has
actually consumed every binding in a regional plan view.  The evidence remains
simulation-only and does not grant production authority or causal claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
    RegionResourceDegradedScenarioKind,
    RegionResourceIsolatedAdoptionVerifier,
    RegionResourceIsolatedCandidateGate,
    build_region_resource_degraded_scenario_lineage,
    build_region_resource_isolated_plan_consumption_ack,
)

from .episode_bus import jsonable
from .reserved_seed_interventions import ReservedSeedSourceEvidence


D4_ISOLATED_PHYSICAL_ADOPTION_SCHEMA = (
    "scalable3d-d4-isolated-physical-adoption-v1"
)


@dataclass(frozen=True, slots=True)
class D4IsolatedPhysicalAdoptionRecord:
    """Availability and D4-owned verdict for one arm/region."""

    arm_kind: str
    region_id: str
    intervention_kind: str
    available: bool
    reason: str | None
    source_plan: Mapping[str, Any] | None
    applied_plan: Mapping[str, Any] | None
    scenario_lineage: Mapping[str, Any] | None
    candidate_gate: Mapping[str, Any] | None
    plan_consumption_ack: Mapping[str, Any] | None
    adoption_evidence: Mapping[str, Any] | None
    schema_version: str = D4_ISOLATED_PHYSICAL_ADOPTION_SCHEMA

    def __post_init__(self) -> None:
        if self.arm_kind not in {"control", "treatment"}:
            raise ValueError("D4 adoption arm_kind is invalid")
        if not self.region_id:
            raise ValueError("D4 adoption region_id must be non-empty")
        if self.available:
            if self.reason is not None:
                raise ValueError("available D4 adoption cannot carry a reason")
            if any(
                item is None
                for item in (
                    self.source_plan,
                    self.applied_plan,
                    self.scenario_lineage,
                    self.candidate_gate,
                    self.plan_consumption_ack,
                    self.adoption_evidence,
                )
            ):
                raise ValueError("available D4 adoption lacks evidence")
        elif not self.reason:
            raise ValueError("unavailable D4 adoption requires a reason")

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


def evaluate_d4_isolated_physical_adoption(
    *,
    source: ReservedSeedSourceEvidence,
    arm_kind: str,
    applied_plan_payload: Mapping[str, Any],
    world_application_records: Sequence[Mapping[str, Any]],
    physical_duration_s: float,
) -> tuple[D4IsolatedPhysicalAdoptionRecord, ...]:
    """Evaluate every active degraded region after physical application."""

    if source.intervention_kind == "nominal":
        return ()
    scenario_kind = _scenario_kind(source.intervention_kind)
    task_by_region: dict[str, list[Any]] = {}
    for task in source.d4_formal_snapshot.tasks:
        task_by_region.setdefault(str(task.region_id), []).append(task)
    decision_by_region = {
        str(item.region_id): item
        for item in source.d4_formal_decision.region_decisions
        if item.task_ids
        and _decision_matches_intervention(item, source.intervention_kind)
    }
    records: list[D4IsolatedPhysicalAdoptionRecord] = []
    verifier = RegionResourceIsolatedAdoptionVerifier()
    for region_id in sorted(decision_by_region):
        decision = decision_by_region[region_id]
        tasks = tuple(task_by_region.get(region_id, ()))
        target_ids = {str(item.global_track_id) for item in tasks}
        if (
            not decision.execution_allowed
            or decision.fail_closed
            or not decision.ownership.active
            or not decision.ownership.owner_id
        ):
            records.append(
                _unavailable(
                    source,
                    arm_kind=arm_kind,
                    region_id=region_id,
                    reason="formal_region_not_executable",
                )
            )
            continue

        source_plan = _source_region_plan(source, decision, target_ids)
        gate = _deterministic_fallback_gate()
        lineage = build_region_resource_degraded_scenario_lineage(
            scenario_kind=scenario_kind,
            seed=source.seed,
            arm_id=f"{source.seed}-{arm_kind}",
            cycle_index=0,
            region_id=region_id,
            scenario_config_sha256=source.scenario_config_sha256,
            initial_state_sha256=source.initial_state_sha256,
            communication_schedule_sha256=source.communication_schedule_sha256,
            fault_schedule_sha256=source.fault_schedule_sha256,
            source_snapshot=source.d4_formal_snapshot,
            formal_decision=source.d4_formal_decision,
            source_plan_source=source_plan,
            candidate_gate=gate,
        )
        applied_plan = _applied_region_plan(
            applied_plan_payload,
            decision=decision,
            target_ids=target_ids,
            source_plan=source_plan,
            source_timestamp_s=source.intervention_timestamp_s,
            lineage_sha256=lineage.sha256,
        )
        expected_bindings = {
            (str(item["resource_id"]), str(item["global_track_id"]))
            for item in applied_plan["assignments"]
        }
        if {item[1] for item in expected_bindings} != target_ids:
            records.append(
                D4IsolatedPhysicalAdoptionRecord(
                    arm_kind=arm_kind,
                    region_id=region_id,
                    intervention_kind=source.intervention_kind,
                    available=False,
                    reason="applied_region_target_inventory_incomplete",
                    source_plan=source_plan,
                    applied_plan=applied_plan,
                    scenario_lineage=lineage.to_dict(),
                    candidate_gate=gate.to_dict(),
                    plan_consumption_ack=None,
                    adoption_evidence=None,
                )
            )
            continue
        applied_bindings = {
            (str(item.get("resource_id", "")), str(item.get("global_track_id", "")))
            for item in world_application_records
            if item.get("control_applied_to_world") is True
        }
        consumed_count = len(expected_bindings & applied_bindings)
        acknowledged_at_s = (
            float(source.intervention_timestamp_s) + float(physical_duration_s)
        )
        ack = build_region_resource_isolated_plan_consumption_ack(
            ack_id=f"d4-physical-{source.seed}-{arm_kind}-{region_id}",
            lineage=lineage,
            source_plan_source=source_plan,
            applied_plan_source=applied_plan,
            acknowledged_at_s=acknowledged_at_s,
            control_applied_binding_count=consumed_count,
            fully_consumed_by_isolated_world=(
                consumed_count == len(expected_bindings)
            ),
        )
        evidence = verifier.evaluate(
            scenario_lineage_source=lineage,
            source_snapshot=source.d4_formal_snapshot,
            formal_decision=source.d4_formal_decision,
            candidate_gate_source=gate,
            source_plan_source=source_plan,
            applied_plan_source=applied_plan,
            isolated_plan_ack_source=ack,
        )
        available = bool(
            evidence.isolated_plan_consumption_ack_available
            and (
                evidence.new_execution_plan_applied
                or evidence.evaluation_refresh_applied
            )
        )
        if not available:
            records.append(
                D4IsolatedPhysicalAdoptionRecord(
                    arm_kind=arm_kind,
                    region_id=region_id,
                    intervention_kind=source.intervention_kind,
                    available=False,
                    reason=str(evidence.code),
                    source_plan=source_plan,
                    applied_plan=applied_plan,
                    scenario_lineage=lineage.to_dict(),
                    candidate_gate=gate.to_dict(),
                    plan_consumption_ack=ack.to_dict(),
                    adoption_evidence=evidence.to_dict(),
                )
            )
            continue
        records.append(
            D4IsolatedPhysicalAdoptionRecord(
                arm_kind=arm_kind,
                region_id=region_id,
                intervention_kind=source.intervention_kind,
                available=True,
                reason=None,
                source_plan=source_plan,
                applied_plan=applied_plan,
                scenario_lineage=lineage.to_dict(),
                candidate_gate=gate.to_dict(),
                plan_consumption_ack=ack.to_dict(),
                adoption_evidence=evidence.to_dict(),
            )
        )
    return tuple(records)


def _scenario_kind(value: str) -> RegionResourceDegradedScenarioKind:
    mapping = {
        "center_failed": RegionResourceDegradedScenarioKind.CENTER_FAILED,
        "center_and_secondary_failed": (
            RegionResourceDegradedScenarioKind.CENTER_AND_SECONDARY_FAILED
        ),
        "active_risk": RegionResourceDegradedScenarioKind.ACTIVE_RISK,
    }
    try:
        return mapping[str(value)]
    except KeyError as exc:
        raise ValueError("unsupported degraded intervention kind") from exc


def _decision_matches_intervention(decision: Any, intervention_kind: str) -> bool:
    """Keep only regions that satisfy D4's scenario-eligibility predicate."""

    layer = str(decision.selected_layer.value)
    action = str(decision.action.value)
    if intervention_kind == "center_failed":
        return layer == "secondary" and bool(decision.selected_secondary_id)
    if intervention_kind == "center_and_secondary_failed":
        return layer == "distributed" and decision.selected_secondary_id is None
    if intervention_kind == "active_risk":
        return bool(
            layer == "center"
            and action in {"request_center_replan", "request_secondary_assist"}
            and decision.risk_factors
        )
    return False


def _deterministic_fallback_gate() -> RegionResourceIsolatedCandidateGate:
    return RegionResourceIsolatedCandidateGate(
        candidate_considered=False,
        candidate_id=None,
        candidate_payload_sha256=None,
        candidate_confidence=None,
        minimum_confidence=REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
        candidate_ood_passed=None,
        candidate_latency_ms=None,
        candidate_latency_limit_ms=REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
        candidate_finite=None,
        candidate_failure_gate_passed=None,
        candidate_safety_projection_passed=None,
        gate_pass=False,
        rule_fallback=True,
        rejection_reasons=("d4_development_candidate_not_admitted",),
    )


def _source_region_plan(
    source: ReservedSeedSourceEvidence,
    decision: Any,
    target_ids: set[str],
) -> dict[str, Any]:
    plan = source.d3_planning_frame.plan
    target_bridge = dict(source.planning_target_identity_bridge)
    resource_bridge = dict(source.planning_resource_identity_bridge)
    assignments = []
    for item in plan.assignments:
        track_id = target_bridge.get(str(item.target_id))
        resource_id = resource_bridge.get(str(item.resource_id))
        if track_id not in target_ids or resource_id is None:
            continue
        assignments.append(
            _binding_row(
                item,
                resource_id=resource_id,
                global_track_id=str(track_id),
                decision=decision,
            )
        )
    unassigned = tuple(
        sorted(
            track_id
            for token in getattr(plan, "unassigned_target_ids", ())
            for track_id in (target_bridge.get(str(token)),)
            if track_id in target_ids
        )
    )
    return _plan_view(
        plan_id=str(plan.plan_id),
        plan_version=int(plan.version),
        created_at=float(plan.created_at),
        timestamp=float(source.intervention_timestamp_s),
        assignments=assignments,
        unassigned=unassigned,
        decision=decision,
        execution_signature_changed=False,
        plan_refresh_only=False,
        evaluation_refresh_only=False,
        execution_source=None,
        lineage_sha256=None,
    )


def _applied_region_plan(
    payload: Mapping[str, Any],
    *,
    decision: Any,
    target_ids: set[str],
    source_plan: Mapping[str, Any],
    source_timestamp_s: float,
    lineage_sha256: str,
) -> dict[str, Any]:
    assignments = []
    for item in payload.get("assignments", ()):
        track_id = str(item.get("global_track_id", item.get("target_id", "")))
        if track_id not in target_ids:
            continue
        assignments.append(
            _binding_row(
                item,
                resource_id=str(item["resource_id"]),
                global_track_id=track_id,
                decision=decision,
            )
        )
    unassigned = tuple(
        sorted(
            str(item)
            for item in payload.get("unassigned_target_ids", ())
            if str(item) in target_ids
        )
    )
    same_identity = bool(
        str(payload["plan_id"]) == str(source_plan["plan_id"])
        and int(payload["plan_version"]) == int(source_plan["plan_version"])
    )
    created_at = float(payload.get("created_at", source_timestamp_s))
    if not same_identity:
        created_at = max(created_at, float(source_timestamp_s))
    return _plan_view(
        plan_id=str(payload["plan_id"]),
        plan_version=int(payload["plan_version"]),
        created_at=created_at,
        timestamp=float(source_timestamp_s),
        assignments=assignments,
        unassigned=unassigned,
        decision=decision,
        execution_signature_changed=not same_identity,
        plan_refresh_only=False,
        evaluation_refresh_only=same_identity,
        execution_source="deterministic_rule_fallback",
        lineage_sha256=lineage_sha256,
    )


def _binding_row(
    item: Any,
    *,
    resource_id: str,
    global_track_id: str,
    decision: Any,
) -> dict[str, Any]:
    def value(name: str, default: Any = None) -> Any:
        if isinstance(item, Mapping):
            return item.get(name, default)
        return getattr(item, name, default)

    return {
        "resource_id": str(resource_id),
        "global_track_id": str(global_track_id),
        "coalition_id": value("coalition_id"),
        "coalition_version": value("coalition_version"),
        "member_role": str(value("member_role", "primary")),
        "owner_node_id": str(decision.ownership.owner_id),
        "regional_owner_layer": str(decision.selected_layer.value),
        "regional_region_id": str(decision.region_id),
        "regional_epoch": int(decision.ownership.epoch),
        "regional_commit_mode": str(decision.action.value),
    }


def _plan_view(
    *,
    plan_id: str,
    plan_version: int,
    created_at: float,
    timestamp: float,
    assignments: Sequence[Mapping[str, Any]],
    unassigned: Sequence[str],
    decision: Any,
    execution_signature_changed: bool,
    plan_refresh_only: bool,
    evaluation_refresh_only: bool,
    execution_source: str | None,
    lineage_sha256: str | None,
) -> dict[str, Any]:
    metadata = {
        "active_plan_owner": str(decision.selected_layer.value),
        "owner_node_id": str(decision.ownership.owner_id),
        "authority_epoch": int(decision.ownership.epoch),
        "lease_expires_at_s": float(decision.ownership.lease_expires_at_s),
        "current_plan_id": str(plan_id),
        "current_plan_version": int(plan_version),
        "identity_created_at_s": float(created_at),
        "last_evaluated_at_s": float(timestamp),
        "execution_signature_changed": bool(execution_signature_changed),
        "plan_refresh_only": bool(plan_refresh_only),
        "evaluation_refresh_only": bool(evaluation_refresh_only),
        "plan_published": True,
    }
    if execution_source is not None:
        metadata["d4_isolated_execution_source"] = execution_source
        metadata["d4_candidate_payload_sha256"] = None
    if lineage_sha256 is not None:
        metadata["d4_source_lineage_sha256"] = lineage_sha256
    return {
        "timestamp": float(timestamp),
        "plan_id": str(plan_id),
        "plan_version": int(plan_version),
        "created_at": float(created_at),
        "assignment_count": len(assignments),
        "assignments": list(assignments),
        "unassigned_global_track_ids": list(unassigned),
        "metadata": metadata,
    }


def _unavailable(
    source: ReservedSeedSourceEvidence,
    *,
    arm_kind: str,
    region_id: str,
    reason: str,
) -> D4IsolatedPhysicalAdoptionRecord:
    return D4IsolatedPhysicalAdoptionRecord(
        arm_kind=arm_kind,
        region_id=region_id,
        intervention_kind=source.intervention_kind,
        available=False,
        reason=reason,
        source_plan=None,
        applied_plan=None,
        scenario_lineage=None,
        candidate_gate=None,
        plan_consumption_ack=None,
        adoption_evidence=None,
    )
