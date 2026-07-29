"""Truth-free audit of D4 planning advice consumed by a strict D3 successor."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping, Sequence

from .runtime_plan_outcome_join import (
    RuntimePlanOutcomeJoinError,
    canonical_assignment_binding_set,
)


REGIONAL_PLANNING_CHAIN_AUDIT_SCHEMA_VERSION = (
    "d6-regional-planning-chain-audit-v1"
)
REGIONAL_PLANNING_SAME_KEY_R0_SCHEMA_VERSION = (
    "d6-regional-planning-same-key-r0-v1"
)

_D3_PLAN_TOPIC = "modules.d3.assignment_plan"
_D4_ADVICE_TOPIC = "modules.d4.region_resource_advice"
_D4_ADVICE_ENVELOPE_SCHEMA = "d4-region-resource-advisory-runtime-v1"
_D4_PLANNING_ADVISORY_SCHEMA = "d4-region-resource-advisory-v2"
_D4_CONSUMPTION_TOPIC = "modules.d4.region_resource_consumption"
_D4_CONSUMPTION_SCHEMA = "d4-region-resource-consumption-v1"
_EXECUTION_AUTHORITY_FIELDS = (
    "execution_authorized",
    "assignment_execution_authorized",
    "coalition_execution_authorized",
    "takeover_execution_authorized",
    "control_execution_authorized",
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "actor_id",
        "ground_truth",
        "ground_truth_id",
        "ground_truth_target_id",
        "sim_object_id",
        "truth_id",
        "truth_target_id",
    }
)


@dataclass(frozen=True, slots=True)
class RegionalPlanningChainAuditResult:
    """One fail-closed, episode-local planning-chain conclusion."""

    status: str
    advisory_id: str | None
    advisory_source: str | None
    source_plan_id: str | None
    source_plan_version: int | None
    successor_plan_id: str | None
    successor_plan_version: int | None
    contract_chain_available: bool
    planning_only_authority_safe: bool
    real_binding_intervention_available: bool
    same_key_r0_available: bool
    non_degradation_available: bool
    non_degraded: bool | None
    non_degradation_scope: str | None
    model_benefit_available: bool
    fault_generation_fence_evidence_available: bool
    fault_generation_fence_passed: bool | None
    source_assignment_count: int | None
    successor_assignment_count: int | None
    assignment_count_delta: int | None
    source_unassigned_count: int | None
    successor_unassigned_count: int | None
    unassigned_count_delta: int | None
    added_bindings: tuple[tuple[str, str], ...] = ()
    removed_bindings: tuple[tuple[str, str], ...] = ()
    newly_covered_target_ids: tuple[str, ...] = ()
    lost_target_ids: tuple[str, ...] = ()
    blocker_codes: tuple[str, ...] = ()
    safety_violation_codes: tuple[str, ...] = ()
    schema_version: str = REGIONAL_PLANNING_CHAIN_AUDIT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "advisory_id": self.advisory_id,
            "advisory_source": self.advisory_source,
            "source_plan_id": self.source_plan_id,
            "source_plan_version": self.source_plan_version,
            "successor_plan_id": self.successor_plan_id,
            "successor_plan_version": self.successor_plan_version,
            "contract_chain_available": self.contract_chain_available,
            "planning_only_authority_safe": self.planning_only_authority_safe,
            "real_binding_intervention_available": (
                self.real_binding_intervention_available
            ),
            "same_key_r0_available": self.same_key_r0_available,
            "non_degradation_available": self.non_degradation_available,
            "non_degraded": self.non_degraded,
            "non_degradation_scope": self.non_degradation_scope,
            "model_benefit_available": self.model_benefit_available,
            "fault_generation_fence_evidence_available": (
                self.fault_generation_fence_evidence_available
            ),
            "fault_generation_fence_passed": (
                self.fault_generation_fence_passed
            ),
            "source_assignment_count": self.source_assignment_count,
            "successor_assignment_count": self.successor_assignment_count,
            "assignment_count_delta": self.assignment_count_delta,
            "source_unassigned_count": self.source_unassigned_count,
            "successor_unassigned_count": self.successor_unassigned_count,
            "unassigned_count_delta": self.unassigned_count_delta,
            "added_bindings": [list(item) for item in self.added_bindings],
            "removed_bindings": [list(item) for item in self.removed_bindings],
            "newly_covered_target_ids": list(self.newly_covered_target_ids),
            "lost_target_ids": list(self.lost_target_ids),
            "blocker_codes": list(self.blocker_codes),
            "safety_violation_codes": list(self.safety_violation_codes),
        }

    def to_scalable_3d_metrics(self) -> dict[str, Any]:
        """Project the audit into stable scalable-offline row fields."""

        prefix = "d4_planning_chain_"
        return {
            f"{prefix}audit_schema_version": self.schema_version,
            f"{prefix}status": self.status,
            f"{prefix}advisory_id": self.advisory_id,
            f"{prefix}advisory_source": self.advisory_source,
            f"{prefix}source_plan_id": self.source_plan_id,
            f"{prefix}source_plan_version": self.source_plan_version,
            f"{prefix}successor_plan_id": self.successor_plan_id,
            f"{prefix}successor_plan_version": self.successor_plan_version,
            f"{prefix}contract_chain_available": (
                self.contract_chain_available
            ),
            f"{prefix}planning_only_authority_safe": (
                self.planning_only_authority_safe
            ),
            f"{prefix}real_binding_intervention_available": (
                self.real_binding_intervention_available
            ),
            f"{prefix}same_key_r0_available": self.same_key_r0_available,
            f"{prefix}non_degradation_available": (
                self.non_degradation_available
            ),
            f"{prefix}non_degraded": self.non_degraded,
            f"{prefix}non_degradation_scope": self.non_degradation_scope,
            f"{prefix}model_benefit_available": (
                self.model_benefit_available
            ),
            f"{prefix}fault_generation_fence_evidence_available": (
                self.fault_generation_fence_evidence_available
            ),
            f"{prefix}fault_generation_fence_passed": (
                self.fault_generation_fence_passed
            ),
            f"{prefix}source_assignment_count": self.source_assignment_count,
            f"{prefix}successor_assignment_count": (
                self.successor_assignment_count
            ),
            f"{prefix}assignment_count_delta": self.assignment_count_delta,
            f"{prefix}source_unassigned_count": self.source_unassigned_count,
            f"{prefix}successor_unassigned_count": (
                self.successor_unassigned_count
            ),
            f"{prefix}unassigned_count_delta": self.unassigned_count_delta,
            f"{prefix}added_binding_count": len(self.added_bindings),
            f"{prefix}removed_binding_count": len(self.removed_bindings),
            f"{prefix}newly_covered_target_count": len(
                self.newly_covered_target_ids
            ),
            f"{prefix}lost_target_count": len(self.lost_target_ids),
            f"{prefix}blocker_codes_json": list(self.blocker_codes),
            f"{prefix}safety_violation_codes_json": list(
                self.safety_violation_codes
            ),
        }


def audit_regional_planning_chain(
    online_records: Sequence[Any],
    *,
    same_key_r0_evidence: Mapping[str, Any] | None = None,
) -> RegionalPlanningChainAuditResult:
    """Audit advice -> consumption -> strict successor without online truth.

    A same-key R0 is optional. It must be an independently persisted evidence
    envelope; a locally recomputed or unpublished mapping is not inferred from
    the treatment episode.
    """

    records, normalization_violations = _normalize_online_records(online_records)
    plans = _index_plans(records)
    advisories = _index_advisories(records)
    consumptions = [
        record for record in records if record["topic"] == _D4_CONSUMPTION_TOPIC
    ]
    selected_consumption = _select_consumption(consumptions)
    fault_advisory = _latest_fault_fenced_advisory(advisories)

    if (
        selected_consumption is not None
        and selected_consumption["payload"].get("d3_hint_applied") is True
    ):
        return _audit_consumed_chain(
            selected_consumption,
            plans=plans,
            advisories=advisories,
            same_key_r0_evidence=same_key_r0_evidence,
            inherited_violations=normalization_violations,
        )

    if (
        fault_advisory is not None
        and (
            selected_consumption is None
            or fault_advisory["sequence"] > selected_consumption["sequence"]
        )
    ):
        return _audit_fault_generation_fence(
            fault_advisory,
            plans=plans,
            consumptions=consumptions,
            inherited_violations=normalization_violations,
        )

    if selected_consumption is not None:
        return _audit_consumed_chain(
            selected_consumption,
            plans=plans,
            advisories=advisories,
            same_key_r0_evidence=same_key_r0_evidence,
            inherited_violations=normalization_violations,
        )

    blockers = _dedupe(
        (
            "regional_planning_consumption_missing",
            "independent_same_key_r0_paired_episode_missing",
            "strict_learning_adoption_model_benefit_evidence_missing",
        )
    )
    return RegionalPlanningChainAuditResult(
        status="unavailable",
        advisory_id=None,
        advisory_source=None,
        source_plan_id=None,
        source_plan_version=None,
        successor_plan_id=None,
        successor_plan_version=None,
        contract_chain_available=False,
        planning_only_authority_safe=False,
        real_binding_intervention_available=False,
        same_key_r0_available=False,
        non_degradation_available=False,
        non_degraded=None,
        non_degradation_scope=None,
        model_benefit_available=False,
        fault_generation_fence_evidence_available=False,
        fault_generation_fence_passed=None,
        source_assignment_count=None,
        successor_assignment_count=None,
        assignment_count_delta=None,
        source_unassigned_count=None,
        successor_unassigned_count=None,
        unassigned_count_delta=None,
        blocker_codes=blockers,
        safety_violation_codes=normalization_violations,
    )


def _audit_consumed_chain(
    consumption_record: Mapping[str, Any],
    *,
    plans: Mapping[tuple[str, int], tuple[Mapping[str, Any], ...]],
    advisories: Mapping[str, tuple[Mapping[str, Any], ...]],
    same_key_r0_evidence: Mapping[str, Any] | None,
    inherited_violations: tuple[str, ...],
) -> RegionalPlanningChainAuditResult:
    payload = consumption_record["payload"]
    violations = list(inherited_violations)
    blockers: list[str] = []
    if consumption_record["schema_version"] != _D4_CONSUMPTION_SCHEMA:
        violations.append("consumption_envelope_schema_mismatch")
    if consumption_record["source"] != "main":
        violations.append("consumption_source_not_main")
    if payload.get("schema") != _D4_CONSUMPTION_SCHEMA:
        violations.append("consumption_payload_schema_mismatch")

    advisory = payload.get("advisory")
    if not isinstance(advisory, Mapping):
        advisory = {}
        violations.append("consumption_advisory_missing")
    advisory_id = _text(advisory.get("advisory_id"))
    advisory_source = _text(advisory.get("source"))
    if advisory.get("schema") != _D4_PLANNING_ADVISORY_SCHEMA:
        violations.append("planning_advisory_schema_mismatch")
    if advisory_id is None:
        violations.append("advisory_id_missing")

    published = advisories.get(advisory_id or "", ())
    if not published:
        violations.append("published_advisory_missing")
    elif not any(
        _canonical_json(item["payload"].get("advisory_contract"))
        == _canonical_json(advisory)
        for item in published
    ):
        violations.append("published_and_consumed_advisory_mismatch")
    if any(item["schema_version"] != _D4_ADVICE_ENVELOPE_SCHEMA for item in published):
        violations.append("advisory_envelope_schema_mismatch")
    if any(item["source"] != "D4" for item in published):
        violations.append("advisory_source_not_d4")

    source_key = _single_source_plan_key(advisory, violations)
    successor_key = _successor_plan_key(payload, violations)
    source_plan = _select_plan(plans, source_key, "source", violations)
    successor_plan = _select_plan(plans, successor_key, "successor", violations)

    authority_safe = _audit_planning_only_authority(
        advisory,
        payload,
        violations,
    )
    _audit_consumption_decision(payload, violations)
    if (
        source_plan is not None
        and successor_plan is not None
        and source_key is not None
        and successor_key is not None
    ):
        _audit_successor_linkage(
            advisory_id=advisory_id,
            source_key=source_key,
            successor_key=successor_key,
            successor_plan=successor_plan,
            violations=violations,
        )

    source_bindings = _bindings(source_plan, "source", violations)
    successor_bindings = _bindings(successor_plan, "successor", violations)
    source_unassigned = _unassigned_targets(
        source_plan, "source", violations
    )
    successor_unassigned = _unassigned_targets(
        successor_plan, "successor", violations
    )

    added = tuple(sorted(successor_bindings - source_bindings))
    removed = tuple(sorted(source_bindings - successor_bindings))
    source_targets = {target_id for _, target_id in source_bindings}
    successor_targets = {target_id for _, target_id in successor_bindings}
    newly_covered = tuple(sorted(successor_targets - source_targets))
    lost_targets = tuple(sorted(source_targets - successor_targets))
    real_intervention = bool(added or removed or newly_covered or lost_targets)
    if not real_intervention:
        blockers.append("real_binding_intervention_missing")

    source_count = len(source_bindings) if source_plan is not None else None
    successor_count = (
        len(successor_bindings) if successor_plan is not None else None
    )
    assignment_delta = (
        successor_count - source_count
        if source_count is not None and successor_count is not None
        else None
    )
    source_unassigned_count = (
        len(source_unassigned) if source_unassigned is not None else None
    )
    successor_unassigned_count = (
        len(successor_unassigned)
        if successor_unassigned is not None
        else None
    )
    unassigned_delta = (
        successor_unassigned_count - source_unassigned_count
        if source_unassigned_count is not None
        and successor_unassigned_count is not None
        else None
    )

    same_key_r0_available, r0_plan, r0_blockers = _audit_same_key_r0(
        same_key_r0_evidence,
        source_key=source_key,
    )
    blockers.extend(r0_blockers)
    comparison_plan = r0_plan if same_key_r0_available else source_plan
    comparison_scope = (
        "independent_same_key_r0_pair"
        if same_key_r0_available
        else "descriptive_source_successor"
    )
    comparison_bindings = _bindings(
        comparison_plan,
        "same_key_r0" if same_key_r0_available else "source",
        violations,
    )
    comparison_unassigned = _unassigned_targets(
        comparison_plan,
        "same_key_r0" if same_key_r0_available else "source",
        violations,
    )
    non_degradation_available = bool(
        successor_plan is not None
        and comparison_plan is not None
        and comparison_unassigned is not None
    )
    non_degraded: bool | None = None
    if non_degradation_available:
        comparison_targets = {target_id for _, target_id in comparison_bindings}
        non_degraded = bool(
            len(successor_bindings) >= len(comparison_bindings)
            and len(successor_unassigned or ()) <= len(comparison_unassigned)
            and not (comparison_targets - successor_targets)
        )
    else:
        comparison_scope = None
        blockers.append("assignment_unassigned_non_degradation_unavailable")

    if advisory_source != "learned":
        blockers.append("advisory_source_not_learned")
    blockers.append("strict_learning_adoption_model_benefit_evidence_missing")
    if not same_key_r0_available:
        blockers.append("independent_same_key_r0_paired_episode_missing")

    violations = list(_dedupe(violations))
    contract_available = not violations
    real_available = bool(contract_available and real_intervention)
    status = (
        "contract_chain_verified"
        if contract_available and real_intervention
        else (
            "contract_chain_without_real_intervention"
            if contract_available
            else "invalid_contract_chain"
        )
    )
    return RegionalPlanningChainAuditResult(
        status=status,
        advisory_id=advisory_id,
        advisory_source=advisory_source,
        source_plan_id=None if source_key is None else source_key[0],
        source_plan_version=None if source_key is None else source_key[1],
        successor_plan_id=None if successor_key is None else successor_key[0],
        successor_plan_version=(
            None if successor_key is None else successor_key[1]
        ),
        contract_chain_available=contract_available,
        planning_only_authority_safe=bool(contract_available and authority_safe),
        real_binding_intervention_available=real_available,
        same_key_r0_available=same_key_r0_available,
        non_degradation_available=non_degradation_available,
        non_degraded=non_degraded,
        non_degradation_scope=comparison_scope,
        model_benefit_available=False,
        fault_generation_fence_evidence_available=False,
        fault_generation_fence_passed=None,
        source_assignment_count=source_count,
        successor_assignment_count=successor_count,
        assignment_count_delta=assignment_delta,
        source_unassigned_count=source_unassigned_count,
        successor_unassigned_count=successor_unassigned_count,
        unassigned_count_delta=unassigned_delta,
        added_bindings=added,
        removed_bindings=removed,
        newly_covered_target_ids=newly_covered,
        lost_target_ids=lost_targets,
        blocker_codes=_dedupe(blockers),
        safety_violation_codes=tuple(violations),
    )


def _audit_fault_generation_fence(
    advisory_record: Mapping[str, Any],
    *,
    plans: Mapping[tuple[str, int], tuple[Mapping[str, Any], ...]],
    consumptions: Sequence[Mapping[str, Any]],
    inherited_violations: tuple[str, ...],
) -> RegionalPlanningChainAuditResult:
    contract = advisory_record["payload"]["advisory_contract"]
    advisory_id = _text(contract.get("advisory_id"))
    violations = list(inherited_violations)
    if advisory_record["schema_version"] != _D4_ADVICE_ENVELOPE_SCHEMA:
        violations.append("advisory_envelope_schema_mismatch")
    if advisory_record["source"] != "D4":
        violations.append("advisory_source_not_d4")
    if contract.get("transfers") not in ([], ()):
        violations.append("fault_generation_fenced_advisory_has_transfer")
    if contract.get("planning_only_region_ids") not in (None, [], ()):
        violations.append(
            "fault_generation_fenced_advisory_has_planning_only_regions"
        )
    for capabilities in _authority_capabilities(contract):
        if capabilities.get("fault_generation_fenced") is True:
            if capabilities.get("planning_replan_eligible") is not False:
                violations.append(
                    "fault_generation_fenced_region_planning_eligible"
                )
            for field in (
                "assignment_execution_authorized",
                "coalition_execution_authorized",
                "takeover_execution_authorized",
                "control_execution_authorized",
            ):
                if capabilities.get(field) is True:
                    violations.append(
                        f"fault_generation_fenced_region_{field}"
                    )
    for record in consumptions:
        nested = record["payload"].get("advisory")
        if (
            isinstance(nested, Mapping)
            and _text(nested.get("advisory_id")) == advisory_id
        ):
            violations.append("fault_generation_fenced_advisory_consumed")

    for plan_records in plans.values():
        for record in plan_records:
            metadata = record["payload"].get("metadata")
            if not isinstance(metadata, Mapping):
                continue
            linked_id = (
                metadata.get("regional_hint_successor_advisory_id")
                or metadata.get("regional_hint_advisory_id")
            )
            if (
                linked_id == advisory_id
                and (
                    metadata.get("regional_hint_applied") is True
                    or metadata.get("regional_hint_successor_plan_available")
                    is True
                )
            ):
                violations.append(
                    "fault_generation_fenced_advisory_formed_successor"
                )

    violations = list(_dedupe(violations))
    passed = not violations
    blockers = (
        "fault_generation_fenced_before_consumption",
        "independent_same_key_r0_paired_episode_missing",
        "strict_learning_adoption_model_benefit_evidence_missing",
    )
    return RegionalPlanningChainAuditResult(
        status=(
            "fault_generation_fence_verified"
            if passed
            else "fault_generation_fence_violation"
        ),
        advisory_id=advisory_id,
        advisory_source=_text(contract.get("source")),
        source_plan_id=None,
        source_plan_version=None,
        successor_plan_id=None,
        successor_plan_version=None,
        contract_chain_available=False,
        planning_only_authority_safe=False,
        real_binding_intervention_available=False,
        same_key_r0_available=False,
        non_degradation_available=False,
        non_degraded=None,
        non_degradation_scope=None,
        model_benefit_available=False,
        fault_generation_fence_evidence_available=True,
        fault_generation_fence_passed=passed,
        source_assignment_count=None,
        successor_assignment_count=None,
        assignment_count_delta=None,
        source_unassigned_count=None,
        successor_unassigned_count=None,
        unassigned_count_delta=None,
        blocker_codes=blockers,
        safety_violation_codes=tuple(violations),
    )


def _audit_planning_only_authority(
    advisory: Mapping[str, Any],
    consumption: Mapping[str, Any],
    violations: list[str],
) -> bool:
    safe = True
    if consumption.get("consumable") is not True:
        violations.append("consumption_not_consumable")
        safe = False
    if consumption.get("planning_replan_eligible") is not True:
        violations.append("planning_replan_not_eligible")
        safe = False
    for field in _EXECUTION_AUTHORITY_FIELDS:
        if consumption.get(field) is not False:
            violations.append(f"planning_only_{field}_not_false")
            safe = False

    planning_ids = advisory.get("planning_only_region_ids")
    if not isinstance(planning_ids, Sequence) or isinstance(
        planning_ids, (str, bytes)
    ):
        violations.append("planning_only_region_ids_missing")
        return False
    expected_ids = {_text(value) for value in planning_ids}
    expected_ids.discard(None)
    if not expected_ids:
        violations.append("planning_only_region_ids_empty")
        return False
    capabilities_by_region = {
        _text(capabilities.get("region_id")): capabilities
        for capabilities in _authority_capabilities(advisory)
    }
    for region_id in sorted(expected_ids):
        capabilities = capabilities_by_region.get(region_id)
        if capabilities is None:
            violations.append(
                f"planning_only_authority_capabilities_missing:{region_id}"
            )
            safe = False
            continue
        if capabilities.get("planning_replan_eligible") is not True:
            violations.append(
                f"planning_only_region_not_replan_eligible:{region_id}"
            )
            safe = False
        if capabilities.get("fault_generation_fenced") is not False:
            violations.append(
                f"planning_only_region_fault_generation_fenced:{region_id}"
            )
            safe = False
        for field in (
            "assignment_execution_authorized",
            "coalition_execution_authorized",
            "takeover_execution_authorized",
            "control_execution_authorized",
        ):
            if capabilities.get(field) is not False:
                violations.append(
                    f"planning_only_region_{field}:{region_id}"
                )
                safe = False
    return safe


def _audit_consumption_decision(
    payload: Mapping[str, Any],
    violations: list[str],
) -> None:
    if payload.get("rejection_reasons") not in ([], ()):
        violations.append("consumable_advisory_has_rejection_reasons")
    if payload.get("bridge_rejection_reason") is not None:
        violations.append("consumption_bridge_rejected")
    expected = {
        "d3_hint_applied": True,
        "d3_successor_plan_available": True,
        "d3_successor_state": "successor_published",
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            violations.append(f"consumption_{field}_mismatch")


def _audit_successor_linkage(
    *,
    advisory_id: str | None,
    source_key: tuple[str, int],
    successor_key: tuple[str, int],
    successor_plan: Mapping[str, Any],
    violations: list[str],
) -> None:
    if successor_key[0] == source_key[0]:
        violations.append("successor_plan_id_not_new")
    if successor_key[1] <= source_key[1]:
        violations.append("successor_plan_version_not_strictly_new")
    metadata = successor_plan.get("metadata")
    if not isinstance(metadata, Mapping):
        violations.append("successor_metadata_missing")
        return
    expected = {
        "regional_hint_applied": True,
        "regional_hint_source_plan_id": source_key[0],
        "regional_hint_source_plan_version": source_key[1],
        "regional_hint_successor_source_plan_id": source_key[0],
        "regional_hint_successor_source_plan_version": source_key[1],
        "regional_hint_successor_advisory_id": advisory_id,
        "regional_hint_successor_plan_available": True,
        "regional_hint_successor_state": "successor_published",
        "regional_hint_successor_plan_id": successor_key[0],
        "regional_hint_successor_plan_version": successor_key[1],
        "plan_published": True,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            violations.append(f"successor_metadata_mismatch:{field}")
    hint_id = metadata.get("regional_hint_advisory_id")
    if hint_id is not None and hint_id != advisory_id:
        violations.append("successor_metadata_mismatch:regional_hint_advisory_id")


def _audit_same_key_r0(
    evidence: Mapping[str, Any] | None,
    *,
    source_key: tuple[str, int] | None,
) -> tuple[bool, Mapping[str, Any] | None, tuple[str, ...]]:
    if evidence is None:
        return (
            False,
            None,
            ("independent_same_key_r0_paired_episode_missing",),
        )
    blockers: list[str] = []
    if evidence.get("schema") != REGIONAL_PLANNING_SAME_KEY_R0_SCHEMA_VERSION:
        blockers.append("same_key_r0_schema_mismatch")
    if evidence.get("independent_episode") is not True:
        blockers.append("same_key_r0_not_independent")
    if _text(evidence.get("comparison_key")) is None:
        blockers.append("same_key_r0_comparison_key_missing")
    if source_key is None or (
        evidence.get("source_plan_id"),
        evidence.get("source_plan_version"),
    ) != source_key:
        blockers.append("same_key_r0_source_plan_mismatch")
    plan = evidence.get("plan")
    if not isinstance(plan, Mapping):
        blockers.append("same_key_r0_plan_missing")
        plan = None
    if isinstance(plan, Mapping):
        metadata = plan.get("metadata")
        if (
            not isinstance(metadata, Mapping)
            or metadata.get("plan_published") is not False
        ):
            blockers.append("same_key_r0_must_be_unpublished")
        try:
            canonical_assignment_binding_set(plan)
        except RuntimePlanOutcomeJoinError:
            blockers.append("same_key_r0_binding_contract_invalid")
    return not blockers, plan if not blockers else None, _dedupe(blockers)


def _single_source_plan_key(
    advisory: Mapping[str, Any],
    violations: list[str],
) -> tuple[str, int] | None:
    raw = advisory.get("source_plan_versions")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        violations.append("advisory_source_plan_versions_missing")
        return None
    values = tuple(_plan_key(item) for item in raw)
    if len(values) != 1 or values[0] is None:
        violations.append("advisory_source_plan_identity_not_unique")
        return None
    return values[0]


def _successor_plan_key(
    payload: Mapping[str, Any],
    violations: list[str],
) -> tuple[str, int] | None:
    key = _plan_key(
        (
            payload.get("d3_successor_plan_id"),
            payload.get("d3_successor_plan_version"),
        )
    )
    if key is None:
        violations.append("consumption_successor_plan_identity_invalid")
    return key


def _select_plan(
    plans: Mapping[tuple[str, int], tuple[Mapping[str, Any], ...]],
    key: tuple[str, int] | None,
    role: str,
    violations: list[str],
) -> Mapping[str, Any] | None:
    if key is None:
        return None
    records = plans.get(key, ())
    if not records:
        violations.append(f"{role}_plan_publication_missing")
        return None
    binding_sets: set[frozenset[tuple[str, str]]] = set()
    for record in records:
        try:
            binding_sets.add(canonical_assignment_binding_set(record["payload"]))
        except RuntimePlanOutcomeJoinError as exc:
            violations.append(f"{role}_plan_{exc.code}")
    if len(binding_sets) > 1:
        violations.append(f"{role}_plan_identity_reused_with_new_bindings")
    return records[0]["payload"] if role == "source" else records[-1]["payload"]


def _bindings(
    plan: Mapping[str, Any] | None,
    role: str,
    violations: list[str],
) -> frozenset[tuple[str, str]]:
    if plan is None:
        return frozenset()
    try:
        return canonical_assignment_binding_set(plan)
    except RuntimePlanOutcomeJoinError as exc:
        violations.append(f"{role}_plan_{exc.code}")
        return frozenset()


def _unassigned_targets(
    plan: Mapping[str, Any] | None,
    role: str,
    violations: list[str],
) -> frozenset[str] | None:
    if plan is None:
        return None
    raw = plan.get("unassigned_global_track_ids")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        violations.append(f"{role}_unassigned_target_ids_missing")
        return None
    values = tuple(_text(value) for value in raw)
    if any(value is None for value in values):
        violations.append(f"{role}_unassigned_target_ids_invalid")
        return None
    result = frozenset(value for value in values if value is not None)
    if len(result) != len(values):
        violations.append(f"{role}_unassigned_target_ids_duplicate")
    return result


def _index_plans(
    records: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, int], tuple[Mapping[str, Any], ...]]:
    mutable: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for record in records:
        if record["topic"] != _D3_PLAN_TOPIC:
            continue
        payload = record["payload"]
        key = _plan_key((payload.get("plan_id"), payload.get("plan_version")))
        if key is not None:
            mutable.setdefault(key, []).append(record)
    return {key: tuple(value) for key, value in mutable.items()}


def _index_advisories(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    mutable: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        if record["topic"] != _D4_ADVICE_TOPIC:
            continue
        contract = record["payload"].get("advisory_contract")
        if not isinstance(contract, Mapping):
            continue
        advisory_id = _text(contract.get("advisory_id"))
        if advisory_id is not None:
            mutable.setdefault(advisory_id, []).append(record)
    return {key: tuple(value) for key, value in mutable.items()}


def _select_consumption(
    records: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    planning_records = []
    for record in records:
        payload = record["payload"]
        advisory = payload.get("advisory")
        if (
            isinstance(advisory, Mapping)
            and advisory.get("schema") == _D4_PLANNING_ADVISORY_SCHEMA
        ):
            planning_records.append(record)
    records = planning_records
    applied = [
        record
        for record in records
        if record["payload"].get("d3_hint_applied") is True
    ]
    if applied:
        return applied[-1]
    return records[-1] if records else None


def _latest_fault_fenced_advisory(
    advisories: Mapping[str, tuple[Mapping[str, Any], ...]],
) -> Mapping[str, Any] | None:
    records = [
        record
        for values in advisories.values()
        for record in values
        if _advisory_is_fault_generation_fenced(
            record["payload"]["advisory_contract"]
        )
    ]
    return max(records, key=lambda item: item["sequence"]) if records else None


def _advisory_is_fault_generation_fenced(
    advisory: Mapping[str, Any],
) -> bool:
    if any(
        item.get("fault_generation_fenced") is True
        for item in _authority_capabilities(advisory)
    ):
        return True
    rejections = advisory.get("projection_rejections")
    if not isinstance(rejections, Sequence) or isinstance(
        rejections, (str, bytes)
    ):
        return False
    return any(
        "fault_fence_active" in str(reason)
        or "formal_d4_execution_fenced" in str(reason)
        for reason in rejections
    )


def _authority_capabilities(
    advisory: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    regions = advisory.get("regions")
    if not isinstance(regions, Sequence) or isinstance(regions, (str, bytes)):
        return ()
    for region in regions:
        if not isinstance(region, Mapping):
            continue
        source_version = region.get("source_version")
        if not isinstance(source_version, Mapping):
            continue
        capabilities = source_version.get("authority_capabilities")
        if isinstance(capabilities, Mapping):
            result.append(capabilities)
    return tuple(result)


def _normalize_online_records(
    records: Sequence[Any],
) -> tuple[tuple[Mapping[str, Any], ...], tuple[str, ...]]:
    normalized: list[dict[str, Any]] = []
    violations: list[str] = []
    relevant_topics = {_D3_PLAN_TOPIC, _D4_ADVICE_TOPIC, _D4_CONSUMPTION_TOPIC}
    for index, value in enumerate(records):
        topic = _record_field(value, "topic")
        if topic not in relevant_topics:
            continue
        payload = _record_field(value, "payload")
        if not isinstance(payload, Mapping):
            violations.append(f"online_record_payload_invalid:{index}")
            continue
        if _contains_forbidden_online_key(payload):
            violations.append(f"online_truth_field_present:{index}")
            continue
        sequence = _record_field(value, "sequence")
        normalized.append(
            {
                "sequence": (
                    int(sequence)
                    if isinstance(sequence, int) and not isinstance(sequence, bool)
                    else index
                ),
                "topic": str(topic),
                "source": _text(_record_field(value, "source")) or "",
                "schema_version": (
                    _text(_record_field(value, "schema_version")) or ""
                ),
                "payload": payload,
            }
        )
    normalized.sort(key=lambda item: item["sequence"])
    return tuple(normalized), _dedupe(violations)


def _record_field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _plan_key(value: Any) -> tuple[str, int] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) != 2:
        return None
    plan_id = _text(value[0])
    version = value[1]
    if (
        plan_id is None
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 0
    ):
        return None
    return plan_id, int(version)


def _contains_forbidden_online_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized in _FORBIDDEN_ONLINE_KEYS
                or normalized.startswith("ground_truth")
            ):
                return True
            if _contains_forbidden_online_key(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_online_key(item) for item in value)
    return False


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


__all__ = [
    "REGIONAL_PLANNING_CHAIN_AUDIT_SCHEMA_VERSION",
    "REGIONAL_PLANNING_SAME_KEY_R0_SCHEMA_VERSION",
    "RegionalPlanningChainAuditResult",
    "audit_regional_planning_chain",
]
