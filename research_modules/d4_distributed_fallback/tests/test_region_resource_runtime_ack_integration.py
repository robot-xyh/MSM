from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    AdvisorMode,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceProjectionConfig,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
    formal_decision_digest,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
    RegionResourceAdvisoryResult,
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


class _IdentifiableHoldAssistPolicy:
    """Add one bounded D3-consumable action to the learned fixture."""

    def __init__(self, base: _FiniteAssistPolicy) -> None:
        self._base = base

    def is_ood(self, snapshot: Any, *, margin: float) -> bool:
        return self._base.is_ood(snapshot, margin=margin)

    def recommend_raw(self, snapshot: Any) -> Any:
        recommendation = self._base.recommend_raw(snapshot)
        selected_region_id = min(
            action.region_id for action in recommendation.actions
        )
        return replace(
            recommendation,
            actions=tuple(
                replace(
                    action,
                    hold=action.region_id == selected_region_id,
                    request_replan=(
                        action.region_id == selected_region_id
                    ),
                )
                for action in recommendation.actions
            ),
        )


class _RuntimeAckContractFixture:
    """Test-only source for an already-admitted advisory transport contract."""

    def __init__(self, *, identifiable_intervention: bool = False) -> None:
        projection = RegionResourceProjectionConfig(advisory_ttl_s=1.5)
        self.projector = DeterministicResourceProjector(projection)
        base_policy = _FiniteAssistPolicy(projection)
        self._policy = (
            _IdentifiableHoldAssistPolicy(base_policy)
            if identifiable_intervention
            else base_policy
        )

    def advise(
        self,
        snapshot: Any,
        *,
        formal_decision: Any = None,
        unseen_seed_count: int = 0,
    ) -> RegionResourceAdvisoryResult:
        raw = self._policy.recommend_raw(snapshot)
        recommendation = self.projector.project(
            snapshot,
            raw,
            formal_decision=formal_decision,
        )
        advisory_contract = self.projector.build_advisory_contract(
            snapshot,
            recommendation,
            formal_decision=formal_decision,
        )
        digest = formal_decision_digest(formal_decision)
        return RegionResourceAdvisoryResult(
            requested_mode=AdvisorMode.ASSIST,
            effective_mode=AdvisorMode.ASSIST,
            recommendation=recommendation,
            fallback_used=False,
            fallback_reason=None,
            assist_eligible=True,
            unseen_seed_count=int(unseen_seed_count),
            inference_latency_ms=0.0,
            formal_decision=formal_decision,
            formal_decision_digest_before=digest,
            formal_decision_digest_after=digest,
            formal_decision_unchanged=True,
            advisory_contract=advisory_contract,
        )


def _assist_advisor(
    *,
    identifiable_intervention: bool = False,
) -> _RuntimeAckContractFixture:
    return _RuntimeAckContractFixture(
        identifiable_intervention=identifiable_intervention
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


def _scenario_config(*, identifiable_intervention: bool) -> ScenarioConfig:
    return ScenarioConfig(
        scenario_name="d4_d3_next_cycle_bridge",
        scenario_version="d4-d3-next-cycle-bridge-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=3.0 if identifiable_intervention else 1.2,
        seed=1 if identifiable_intervention else 41,
        radar_detection_probability=(
            0.45 if identifiable_intervention else 1.0
        ),
        acoustic_enabled=False,
        visual_enabled=False,
        communication_drop_probability=0.0,
        communication_jitter_s=0.0,
        communication_latency_s=0.01,
    )


@pytest.fixture(scope="module")
def real_noop_chain() -> dict[str, Any]:
    stack = IntegratedScalableModuleStack(
        d4_region_advisor=_assist_advisor(),
        d4_unseen_seed_count=1,
    )
    result = run_episode(
        _scenario_config(identifiable_intervention=False),
        module_stack=stack,
    )
    messages = tuple(result.online_messages)
    advice = next(
        item
        for item in messages
        if item.topic == "modules.d4.region_resource_advice"
        and item.payload["advisory_contract"] is not None
    )
    advisory = advice.payload["advisory_contract"]
    advisory_id = advisory["advisory_id"]
    consumption = next(
        item
        for item in messages
        if item.topic == "modules.d4.region_resource_consumption"
        and item.payload["advisory"]["advisory_id"] == advisory_id
    )
    current_plan = next(
        item
        for item in messages
        if item.topic == "modules.d3.assignment_plan"
        and item.payload["metadata"].get("regional_hint_advisory_id")
        == advisory_id
    )
    source_plan_id, source_plan_version = advisory[
        "source_plan_versions"
    ][0]
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
    applied_acks = tuple(
        item
        for item in messages
        if item.topic == "runtime.assignment_plan_ack"
        and item.payload["d4_regional_hint_evidence"].get("advisory_id")
        == advisory_id
        and item.payload["d4_regional_hint_evidence"]["applied"] is True
    )
    return {
        "advisory": _envelope_dict(advice),
        "consumption": _envelope_dict(consumption),
        "current_plan": _envelope_dict(current_plan),
        "source_plan": _envelope_dict(source_plan),
        "applied_acks": applied_acks,
    }


@pytest.fixture(scope="module")
def real_successor_chain() -> dict[str, Any]:
    stack = IntegratedScalableModuleStack(
        d4_region_advisor=_assist_advisor(
            identifiable_intervention=True
        ),
        d4_unseen_seed_count=1,
    )
    result = run_episode(
        _scenario_config(identifiable_intervention=True),
        module_stack=stack,
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
        "latest_plan": stack.latest_plan,
    }


def _consume(chain: dict[str, Any]) -> Any:
    return RegionResourceRuntimeAckParser().consume(
        advisory_source=chain["advisory"],
        consumption_source=chain["consumption"],
        assignment_plan_ack_source=chain["ack"],
        d3_plan_source_envelope=chain["current_plan"],
        d7_guidance_source_envelope=chain["current_guidance"],
        advisory_source_plan_envelope=chain["source_plan"],
    )


def test_real_main_5v5_noop_has_no_successor_or_adoption_ack(
    real_noop_chain: dict[str, Any],
) -> None:
    advisory = real_noop_chain["advisory"]["payload"][
        "advisory_contract"
    ]
    assert advisory["total_quota_delta"] == 0
    assert advisory["transfers"] == []
    assert all(
        region["resources_before"] == region["resources_after"]
        and region["resource_quota_delta"] == 0
        and region["hold"] is False
        and region["request_replan"] is False
        for region in advisory["regions"]
    )

    consumption = real_noop_chain["consumption"]["payload"]
    assert consumption["consumable"] is True
    assert consumption["d3_hint_applied"] is False
    assert consumption["d3_successor_plan_available"] is False
    assert consumption["d3_successor_state"] == "no_successor"
    assert consumption["bridge_rejection_reason"] == (
        "d3_regional_hint_rejected:"
        "regional_hint_no_executable_successor"
    )

    source_payload = real_noop_chain["source_plan"]["payload"]
    current_payload = real_noop_chain["current_plan"]["payload"]
    metadata = current_payload["metadata"]
    assert current_payload["plan_id"] == source_payload["plan_id"]
    assert current_payload["plan_version"] == source_payload["plan_version"]
    assert metadata["regional_hint_applied"] is False
    assert metadata["regional_hint_rejected"] is True
    assert metadata["regional_hint_successor_state"] == "no_successor"
    assert metadata["regional_hint_successor_plan_available"] is False
    assert metadata["regional_hint_successor_plan_id"] is None
    assert metadata["regional_hint_successor_plan_version"] is None
    assert "authority_epoch" not in metadata
    assert "lease_expires_at_s" not in metadata
    assert real_noop_chain["applied_acks"] == ()


def test_real_main_5v5_successor_is_new_plan_adoption_ack(
    real_successor_chain: dict[str, Any],
) -> None:
    sequences = {
        name: int(real_successor_chain[name]["sequence"])
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
    assert (
        real_successor_chain["ack"]["payload"]["source_plan_bus_sequence"]
        == sequences["current_plan"]
    )
    assert real_successor_chain["ack"]["payload"][
        "source_guidance_bus_sequence"
    ] == (
        sequences["current_guidance"]
    )
    source_payload = real_successor_chain["source_plan"]["payload"]
    current_payload = real_successor_chain["current_plan"]["payload"]
    metadata = current_payload["metadata"]
    latest_plan = real_successor_chain["latest_plan"]
    assert current_payload["plan_id"] != source_payload["plan_id"]
    assert current_payload["plan_version"] > source_payload["plan_version"]
    assert latest_plan.plan_id == current_payload["plan_id"]
    assert latest_plan.version == current_payload["plan_version"]
    assert latest_plan.previous_plan_id == source_payload["plan_id"]
    assert metadata["regional_hint_source_plan_id"] == source_payload["plan_id"]
    assert metadata["regional_hint_source_plan_version"] == (
        source_payload["plan_version"]
    )
    assert metadata["execution_signature_changed"] is True
    assert metadata["plan_refresh_only"] is False
    assert metadata["evaluation_refresh_only"] is False
    assert metadata["regional_hint_applied"] is True
    assert metadata["regional_hint_rejected"] is False
    assert metadata["regional_hint_successor_state"] == "successor_published"
    assert metadata["regional_hint_successor_plan_available"] is True
    assert metadata["regional_hint_successor_plan_id"] == (
        current_payload["plan_id"]
    )
    assert metadata["regional_hint_successor_plan_version"] == (
        current_payload["plan_version"]
    )
    assert metadata["authority_epoch"] == 1
    assert metadata["lease_expires_at_s"] > current_payload["timestamp"]

    evidence = _consume(deepcopy(real_successor_chain))

    assert evidence.runtime_advisory_applied_ack_available is True
    assert evidence.adoption_kind == (
        RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
    )
    assert evidence.applied_plan_id != evidence.source_plan_id
    assert evidence.applied_plan_version > evidence.source_plan_version
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
        (
            "refresh_flags",
            RegionResourceRuntimeAckCode.PLAN_REFRESH_FLAGS_INVALID,
        ),
        (
            "execution_unchanged",
            RegionResourceRuntimeAckCode.PLAN_REFRESH_FLAGS_INVALID,
        ),
        ("plan_id_reused", RegionResourceRuntimeAckCode.PLAN_NOT_NEW),
        ("version_not_higher", RegionResourceRuntimeAckCode.PLAN_NOT_NEW),
    ),
)
def test_real_main_successor_tampering_fails_closed(
    real_successor_chain: dict[str, Any],
    mutation: str,
    expected_code: RegionResourceRuntimeAckCode,
) -> None:
    chain = deepcopy(real_successor_chain)
    current_payload = chain["current_plan"]["payload"]
    metadata = current_payload["metadata"]
    if mutation == "refresh_flags":
        metadata["evaluation_refresh_only"] = True
    elif mutation == "execution_unchanged":
        metadata["execution_signature_changed"] = False
    elif mutation == "plan_id_reused":
        source_plan_id = chain["source_plan"]["payload"]["plan_id"]
        current_payload["plan_id"] = source_plan_id
        metadata["current_plan_id"] = source_plan_id
        chain["ack"]["payload"]["plan_id"] = source_plan_id
        chain["ack"]["payload"]["decision_id"] = (
            f"{source_plan_id}:v{current_payload['plan_version']}"
        )
    elif mutation == "version_not_higher":
        source_version = chain["source_plan"]["payload"]["plan_version"]
        current_payload["plan_version"] = source_version
        metadata["current_plan_version"] = source_version
        chain["ack"]["payload"]["plan_version"] = source_version
        chain["ack"]["payload"]["decision_id"] = (
            f"{current_payload['plan_id']}:v{source_version}"
        )
    else:  # pragma: no cover
        raise AssertionError(mutation)
    chain["ack"]["payload"]["source_plan_payload_sha256"] = (
        canonical_runtime_payload_sha256(current_payload)
    )

    evidence = _consume(chain)

    assert evidence.runtime_advisory_applied_ack_available is False
    assert evidence.adoption_kind is None
    assert evidence.code == expected_code.value
