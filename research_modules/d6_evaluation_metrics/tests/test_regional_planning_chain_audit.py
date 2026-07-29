from __future__ import annotations

import copy

from d6_evaluation_metrics.regional_planning_chain_audit import (
    REGIONAL_PLANNING_CHAIN_AUDIT_SCHEMA_VERSION,
    REGIONAL_PLANNING_SAME_KEY_R0_SCHEMA_VERSION,
    audit_regional_planning_chain,
)


def _record(
    sequence: int,
    topic: str,
    payload: dict[str, object],
    *,
    source: str | None = None,
    schema_version: str | None = None,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": topic,
        "source": source or ("main" if "consumption" in topic else topic.split(".")[1].upper()),
        "schema_version": schema_version or "fixture-v1",
        "payload": payload,
    }


def _plan(
    plan_id: str,
    version: int,
    bindings: tuple[tuple[str, str], ...],
    unassigned: tuple[str, ...],
    *,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "plan_id": plan_id,
        "plan_version": version,
        "assignment_count": len(bindings),
        "assignments": [
            {
                "resource_id": resource_id,
                "global_track_id": target_id,
                "member_role": "primary",
            }
            for resource_id, target_id in bindings
        ],
        "unassigned_global_track_ids": list(unassigned),
        "metadata": dict(metadata or {}),
    }


def _authority(
    region_id: str,
    *,
    planning: bool,
    fault_generation_fenced: bool = False,
) -> dict[str, object]:
    return {
        "region_id": region_id,
        "planning_replan_eligible": planning,
        "assignment_execution_authorized": False,
        "coalition_execution_authorized": False,
        "takeover_execution_authorized": False,
        "control_execution_authorized": False,
        "fault_generation_fenced": fault_generation_fenced,
    }


def _planning_advisory(
    *,
    advisory_id: str = "d4-advisory-test",
    source_plan_id: str = "source-plan",
    source_plan_version: int = 1,
    source: str = "rule",
) -> dict[str, object]:
    return {
        "advisory_id": advisory_id,
        "schema": "d4-region-resource-advisory-v2",
        "source": source,
        "source_plan_versions": [[source_plan_id, source_plan_version]],
        "planning_only_region_ids": ["region-b"],
        "regions": [
            {
                "source_version": {
                    "region_id": "region-a",
                    "authority_capabilities": _authority(
                        "region-a",
                        planning=False,
                    ),
                }
            },
            {
                "source_version": {
                    "region_id": "region-b",
                    "authority_capabilities": _authority(
                        "region-b",
                        planning=True,
                    ),
                }
            },
        ],
        "transfers": [
            {
                "source_region_id": "region-a",
                "target_region_id": "region-b",
                "resource_count": 1,
            }
        ],
    }


def _successor_metadata(
    *,
    advisory_id: str = "d4-advisory-test",
    source_plan_id: str = "source-plan",
    source_plan_version: int = 1,
    successor_plan_id: str = "successor-plan",
    successor_plan_version: int = 2,
) -> dict[str, object]:
    return {
        "plan_published": True,
        "regional_hint_applied": True,
        "regional_hint_advisory_id": advisory_id,
        "regional_hint_source_plan_id": source_plan_id,
        "regional_hint_source_plan_version": source_plan_version,
        "regional_hint_successor_advisory_id": advisory_id,
        "regional_hint_successor_source_plan_id": source_plan_id,
        "regional_hint_successor_source_plan_version": source_plan_version,
        "regional_hint_successor_plan_available": True,
        "regional_hint_successor_state": "successor_published",
        "regional_hint_successor_plan_id": successor_plan_id,
        "regional_hint_successor_plan_version": successor_plan_version,
    }


def _consumption(
    advisory: dict[str, object],
    *,
    successor_plan_id: str = "successor-plan",
    successor_plan_version: int = 2,
) -> dict[str, object]:
    return {
        "schema": "d4-region-resource-consumption-v1",
        "advisory": copy.deepcopy(advisory),
        "consumable": True,
        "rejection_reasons": [],
        "planning_replan_eligible": True,
        "execution_authorized": False,
        "assignment_execution_authorized": False,
        "coalition_execution_authorized": False,
        "takeover_execution_authorized": False,
        "control_execution_authorized": False,
        "bridge_rejection_reason": None,
        "d3_hint_applied": True,
        "d3_successor_plan_available": True,
        "d3_successor_state": "successor_published",
        "d3_successor_plan_id": successor_plan_id,
        "d3_successor_plan_version": successor_plan_version,
    }


def _positive_records() -> list[dict[str, object]]:
    source_bindings = (
        ("R-1", "T-1"),
        ("R-2", "T-2"),
        ("R-3", "T-3"),
    )
    successor_bindings = (*source_bindings, ("R-4", "T-4"))
    advisory = _planning_advisory()
    return [
        _record(
            1,
            "modules.d3.assignment_plan",
            _plan("source-plan", 1, source_bindings, ("T-4",)),
            source="D3",
        ),
        _record(
            2,
            "modules.d4.region_resource_advice",
            {"advisory_contract": advisory},
            source="D4",
            schema_version="d4-region-resource-advisory-runtime-v1",
        ),
        _record(
            3,
            "modules.d3.assignment_plan",
            _plan(
                "successor-plan",
                2,
                successor_bindings,
                (),
                metadata=_successor_metadata(),
            ),
            source="D3",
        ),
        _record(
            4,
            "modules.d4.region_resource_consumption",
            _consumption(advisory),
            source="main",
            schema_version="d4-region-resource-consumption-v1",
        ),
    ]


def test_rule_advisory_proves_chain_binding_and_descriptive_non_degradation() -> None:
    result = audit_regional_planning_chain(_positive_records())

    assert result.schema_version == REGIONAL_PLANNING_CHAIN_AUDIT_SCHEMA_VERSION
    assert result.status == "contract_chain_verified"
    assert result.contract_chain_available is True
    assert result.planning_only_authority_safe is True
    assert result.real_binding_intervention_available is True
    assert result.added_bindings == (("R-4", "T-4"),)
    assert result.newly_covered_target_ids == ("T-4",)
    assert result.source_assignment_count == 3
    assert result.successor_assignment_count == 4
    assert result.assignment_count_delta == 1
    assert result.source_unassigned_count == 1
    assert result.successor_unassigned_count == 0
    assert result.unassigned_count_delta == -1
    assert result.same_key_r0_available is False
    assert result.non_degradation_available is True
    assert result.non_degraded is True
    assert result.non_degradation_scope == "descriptive_source_successor"
    assert result.model_benefit_available is False
    assert "advisory_source_not_learned" in result.blocker_codes
    assert (
        "independent_same_key_r0_paired_episode_missing"
        in result.blocker_codes
    )
    assert result.safety_violation_codes == ()


def test_independent_same_key_r0_is_separate_from_model_benefit() -> None:
    r0_plan = _plan(
        "r0-plan",
        2,
        (("R-1", "T-1"), ("R-2", "T-2"), ("R-3", "T-3")),
        ("T-4",),
        metadata={"plan_published": False},
    )
    r0_evidence = {
        "schema": REGIONAL_PLANNING_SAME_KEY_R0_SCHEMA_VERSION,
        "comparison_key": "scenario-v1:seed-7:source-plan-v1",
        "independent_episode": True,
        "source_plan_id": "source-plan",
        "source_plan_version": 1,
        "plan": r0_plan,
    }

    result = audit_regional_planning_chain(
        _positive_records(),
        same_key_r0_evidence=r0_evidence,
    )

    assert result.same_key_r0_available is True
    assert result.non_degradation_scope == "independent_same_key_r0_pair"
    assert result.non_degraded is True
    assert result.model_benefit_available is False
    assert (
        "strict_learning_adoption_model_benefit_evidence_missing"
        in result.blocker_codes
    )


def test_version_or_metadata_refresh_is_not_a_real_intervention() -> None:
    records = _positive_records()
    source_plan = records[0]["payload"]
    successor_plan = records[2]["payload"]
    successor_plan["assignments"] = copy.deepcopy(source_plan["assignments"])
    successor_plan["assignment_count"] = source_plan["assignment_count"]
    successor_plan["unassigned_global_track_ids"] = copy.deepcopy(
        source_plan["unassigned_global_track_ids"]
    )

    result = audit_regional_planning_chain(records)

    assert result.contract_chain_available is True
    assert result.real_binding_intervention_available is False
    assert result.status == "contract_chain_without_real_intervention"
    assert "real_binding_intervention_missing" in result.blocker_codes


def test_planning_only_consumption_cannot_grant_control_authority() -> None:
    records = _positive_records()
    consumption = records[-1]["payload"]
    consumption["control_execution_authorized"] = True

    result = audit_regional_planning_chain(records)

    assert result.contract_chain_available is False
    assert result.planning_only_authority_safe is False
    assert result.real_binding_intervention_available is False
    assert (
        "planning_only_control_execution_authorized_not_false"
        in result.safety_violation_codes
    )


def test_fault_generation_fence_is_a_safety_pass_not_model_failure() -> None:
    contract = {
        "advisory_id": "fault-fenced-advisory",
        "schema": "d4-region-resource-advisory-v1",
        "source": "rule",
        "source_plan_versions": [["source-plan", 1]],
        "regions": [
            {
                "source_version": {
                    "region_id": "region-a",
                    "authority_capabilities": _authority(
                        "region-a",
                        planning=False,
                        fault_generation_fenced=True,
                    ),
                }
            }
        ],
        "transfers": [],
        "planning_only_region_ids": [],
    }
    records = [
        _record(
            1,
            "modules.d3.assignment_plan",
            _plan("source-plan", 1, (("R-1", "T-1"),), ()),
            source="D3",
        ),
        _record(
            2,
            "modules.d4.region_resource_advice",
            {"advisory_contract": contract},
            source="D4",
            schema_version="d4-region-resource-advisory-runtime-v1",
        ),
    ]

    result = audit_regional_planning_chain(records)

    assert result.status == "fault_generation_fence_verified"
    assert result.fault_generation_fence_evidence_available is True
    assert result.fault_generation_fence_passed is True
    assert result.contract_chain_available is False
    assert result.real_binding_intervention_available is False
    assert result.model_benefit_available is False
    assert result.safety_violation_codes == ()
    assert "fault_generation_fenced_before_consumption" in result.blocker_codes


def test_later_fault_fence_supersedes_an_earlier_unapplied_attempt() -> None:
    planning = _planning_advisory(advisory_id="old-planning-advisory")
    old_consumption = _consumption(planning)
    old_consumption.update(
        {
            "bridge_rejection_reason": (
                "d3_regional_hint_rejected:"
                "regional_hint_no_executable_successor"
            ),
            "d3_hint_applied": False,
            "d3_successor_plan_available": False,
            "d3_successor_state": "no_successor",
            "d3_successor_plan_id": None,
            "d3_successor_plan_version": None,
        }
    )
    fenced = {
        "advisory_id": "fault-fenced-advisory",
        "schema": "d4-region-resource-advisory-v1",
        "source": "rule",
        "source_plan_versions": [["source-plan", 1]],
        "regions": [],
        "transfers": [],
        "projection_rejections": [
            "region:region-a:fault_fence_active",
            "region:region-a:formal_d4_execution_fenced",
        ],
    }
    records = [
        _record(
            1,
            "modules.d3.assignment_plan",
            _plan("source-plan", 1, (("R-1", "T-1"),), ()),
            source="D3",
        ),
        _record(
            2,
            "modules.d4.region_resource_advice",
            {"advisory_contract": planning},
            source="D4",
            schema_version="d4-region-resource-advisory-runtime-v1",
        ),
        _record(
            3,
            "modules.d4.region_resource_consumption",
            old_consumption,
            source="main",
            schema_version="d4-region-resource-consumption-v1",
        ),
        _record(
            4,
            "modules.d4.region_resource_advice",
            {"advisory_contract": fenced},
            source="D4",
            schema_version="d4-region-resource-advisory-runtime-v1",
        ),
    ]

    result = audit_regional_planning_chain(records)

    assert result.status == "fault_generation_fence_verified"
    assert result.advisory_id == "fault-fenced-advisory"
    assert result.fault_generation_fence_passed is True
    assert result.safety_violation_codes == ()
