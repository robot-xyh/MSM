from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    RecommendationSource,
    RegionResourceProjectionConfig,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
    AdvisorMode,
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
)
from d4_distributed_fallback.region_resource_runtime_ack import (
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckParser,
    RegionResourceRuntimeAdoptionKind,
    canonical_runtime_payload_sha256,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


class _FiniteAssistPolicy:
    def __init__(self, projection: RegionResourceProjectionConfig) -> None:
        self._rule = RuleRegionResourcePolicy(
            RuleRegionResourcePolicyConfig(projection=projection)
        )

    def is_ood(self, snapshot: Any, *, margin: float) -> bool:
        del snapshot, margin
        return False

    def recommend_raw(self, snapshot: Any) -> Any:
        recommendation = self._rule.recommend(snapshot)
        return replace(
            recommendation,
            policy_name="d4-runtime-ack-integration-policy",
            policy_version="v1",
            source=RecommendationSource.LEARNED,
            projected=False,
            model_sha256="a" * 64,
            fallback_reason=None,
        )


def _assist_advisor() -> RegionResourceAdvisor:
    projection = RegionResourceProjectionConfig(advisory_ttl_s=1.5)
    return RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.ASSIST,
            minimum_unseen_seeds=1,
            projection=projection,
        ),
        learned_policy=_FiniteAssistPolicy(projection),
    )


def _envelope_dict(message: Any) -> dict[str, Any]:
    return {
        "sequence": int(message.sequence),
        "topic": str(message.topic),
        "source": str(message.source),
        "timestamp": float(message.timestamp),
        "schema_version": str(message.schema_version),
        "payload": deepcopy(message.payload),
    }


@pytest.fixture(scope="module")
def real_refresh_chain() -> dict[str, dict[str, Any]]:
    config = ScenarioConfig(
        scenario_name="d4_d3_next_cycle_bridge",
        scenario_version="d4-d3-next-cycle-bridge-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=41,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    result = run_episode(
        config,
        module_stack=IntegratedScalableModuleStack(
            d4_region_advisor=_assist_advisor(),
            d4_unseen_seed_count=1,
        ),
    )
    messages = tuple(result.online_messages)
    sequence_index = {int(item.sequence): item for item in messages}
    applied_ack = next(
        item
        for item in messages
        if item.topic == "runtime.assignment_plan_ack"
        and item.payload["d4_regional_hint_evidence"]["applied"] is True
    )
    advisory_id = applied_ack.payload["d4_regional_hint_evidence"]["advisory_id"]
    advice = next(
        item
        for item in messages
        if item.topic == "modules.d4.region_resource_advice"
        and item.payload["advisory_contract"] is not None
        and item.payload["advisory_contract"]["advisory_id"] == advisory_id
    )
    consumption = next(
        item
        for item in messages
        if item.topic == "modules.d4.region_resource_consumption"
        and item.payload["advisory"]["advisory_id"] == advisory_id
    )
    current_plan = sequence_index[
        int(applied_ack.payload["source_plan_bus_sequence"])
    ]
    current_guidance = sequence_index[
        int(applied_ack.payload["source_guidance_bus_sequence"])
    ]
    source_plan_id, source_plan_version = advice.payload[
        "advisory_contract"
    ]["source_plan_versions"][0]
    source_plan = min(
        (
            item
            for item in messages
            if item.topic == "modules.d3.assignment_plan"
            and item.sequence < current_plan.sequence
            and item.payload["plan_id"] == source_plan_id
            and item.payload["plan_version"] == source_plan_version
        ),
        key=lambda item: item.sequence,
    )
    return {
        "advisory": _envelope_dict(advice),
        "consumption": _envelope_dict(consumption),
        "ack": _envelope_dict(applied_ack),
        "current_plan": _envelope_dict(current_plan),
        "current_guidance": _envelope_dict(current_guidance),
        "source_plan": _envelope_dict(source_plan),
    }


def _consume(chain: dict[str, dict[str, Any]]):
    return RegionResourceRuntimeAckParser().consume(
        advisory_source=chain["advisory"],
        consumption_source=chain["consumption"],
        assignment_plan_ack_source=chain["ack"],
        d3_plan_source_envelope=chain["current_plan"],
        d7_guidance_source_envelope=chain["current_guidance"],
        advisory_source_plan_envelope=chain["source_plan"],
    )


def test_real_main_5v5_evaluation_refresh_is_adoption_ack(
    real_refresh_chain: dict[str, dict[str, Any]],
) -> None:
    sequences = {
        name: int(real_refresh_chain[name]["sequence"])
        for name in (
            "source_plan",
            "advisory",
            "current_plan",
            "consumption",
            "current_guidance",
            "ack",
        )
    }
    assert list(sequences.values()) == sorted(sequences.values())
    assert real_refresh_chain["ack"]["payload"]["source_plan_bus_sequence"] == (
        sequences["current_plan"]
    )
    assert real_refresh_chain["ack"]["payload"]["source_guidance_bus_sequence"] == (
        sequences["current_guidance"]
    )
    source_payload = real_refresh_chain["source_plan"]["payload"]
    current_payload = real_refresh_chain["current_plan"]["payload"]
    assert current_payload["plan_id"] == source_payload["plan_id"]
    assert current_payload["plan_version"] == source_payload["plan_version"] == 1

    evidence = _consume(deepcopy(real_refresh_chain))

    assert evidence.runtime_advisory_applied_ack_available is True
    assert evidence.adoption_kind == (
        RegionResourceRuntimeAdoptionKind.EVALUATION_REFRESH_APPLIED.value
    )
    assert evidence.applied_plan_id == evidence.source_plan_id
    assert evidence.applied_plan_version == evidence.source_plan_version
    assert evidence.coalition_member_ack_available is False
    assert evidence.physical_outcome_available is False
    assert evidence.attributable_reward_available is False
    assert evidence.paired_shadow_available is False
    assert evidence.ppo_admission_allowed is False
    assert evidence.assist_admission_allowed is False
    assert evidence.authority_admission_allowed is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("refresh_flags", RegionResourceRuntimeAckCode.PLAN_REFRESH_FLAGS_INVALID),
        (
            "binding_changed",
            RegionResourceRuntimeAckCode.PLAN_REFRESH_BINDINGS_CHANGED,
        ),
        ("execution_changed", RegionResourceRuntimeAckCode.PLAN_NOT_NEW),
        (
            "source_plan_missing",
            RegionResourceRuntimeAckCode.PLAN_REFRESH_SOURCE_MISSING,
        ),
    ),
)
def test_real_main_refresh_tampering_fails_closed(
    real_refresh_chain: dict[str, dict[str, Any]],
    mutation: str,
    expected_code: RegionResourceRuntimeAckCode,
) -> None:
    chain = deepcopy(real_refresh_chain)
    current_payload = chain["current_plan"]["payload"]
    metadata = current_payload["metadata"]
    if mutation == "refresh_flags":
        metadata["evaluation_refresh_only"] = False
    elif mutation == "binding_changed":
        current_payload["assignments"][0]["coalition_version"] += 1
    elif mutation == "execution_changed":
        metadata["execution_signature_changed"] = True
    elif mutation == "source_plan_missing":
        chain["source_plan"] = None  # type: ignore[assignment]
    else:  # pragma: no cover
        raise AssertionError(mutation)
    if mutation != "source_plan_missing":
        chain["ack"]["payload"]["source_plan_payload_sha256"] = (
            canonical_runtime_payload_sha256(current_payload)
        )

    evidence = RegionResourceRuntimeAckParser().consume(
        advisory_source=chain["advisory"],
        consumption_source=chain["consumption"],
        assignment_plan_ack_source=chain["ack"],
        d3_plan_source_envelope=chain["current_plan"],
        d7_guidance_source_envelope=chain["current_guidance"],
        advisory_source_plan_envelope=chain["source_plan"],
    )

    assert evidence.runtime_advisory_applied_ack_available is False
    assert evidence.adoption_kind is None
    assert evidence.code == expected_code.value
