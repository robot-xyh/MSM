from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from d4_distributed_fallback.region_resource import (
    DeterministicResourceProjector,
    RegionResourceNode,
    RegionResourceProjectionConfig,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from d4_distributed_fallback.region_resource_reward_evidence import (
    REGION_RESOURCE_OUTCOME_PROVENANCE_SCHEMA,
    REGION_RESOURCE_OUTCOME_WINDOW_SCHEMA,
    REGION_RESOURCE_REWARD_COMPONENT_SCHEMA,
    REGION_RESOURCE_REWARD_WEIGHTS,
    RegionResourceRewardEvidenceAdapter,
    RegionResourceRewardEvidenceCode,
    canonical_region_resource_outcome_window_sha256,
    region_resource_advisory_fingerprint_sha256,
)
from d4_distributed_fallback.region_resource_runtime_ack import (
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckEvidence,
    RegionResourceRuntimeAdoptionKind,
    canonical_runtime_payload_sha256,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


def _snapshot(
    *,
    snapshot_id: str,
    timestamp_s: float,
    plan_id: str,
    plan_version: int,
    epoch: int = 4,
    lease_expires_at_s: float = 10.0,
    fault_generation: int | None = None,
    high_threat_backlog: float = 1.0,
) -> RegionResourceSnapshot:
    return RegionResourceSnapshot(
        snapshot_id=snapshot_id,
        scenario_id="regional-reward-test",
        scenario_version="v1",
        seed=17,
        timestamp_s=timestamp_s,
        regions=(
            RegionResourceNode(
                region_id="region-000",
                target_demand=2.0,
                high_threat_backlog=high_threat_backlog,
                d1_uncertainty=0.2,
                d2_uncertainty=0.1,
                d5_visibility=0.8,
                d5_consistency=0.9,
                available_resources=3,
                reserve_resources=1,
                secondary_coverage=0.9,
                secondary_readiness=0.9,
                communication_capacity=100.0,
                communication_latency_s=0.02,
                packet_loss_rate=0.0,
                current_owner_id="C2",
                current_owner_layer=RegionalAuthorityLayer.CENTER,
                plan_id=plan_id,
                plan_version=plan_version,
                epoch=epoch,
                lease_expires_at_s=lease_expires_at_s,
                coalition_ack_complete=True,
                owner_active=True,
                fault_fenced=False,
                fault_fence_epoch=fault_generation,
            ),
        ),
        edges=(),
    )


def _fixture(
    *,
    adoption_kind: str = (
        RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
    ),
) -> dict[str, object]:
    source = _snapshot(
        snapshot_id="SNAP-SOURCE",
        timestamp_s=1.0,
        plan_id="PLAN-OLD",
        plan_version=2,
    )
    projector = DeterministicResourceProjector(
        RegionResourceProjectionConfig(advisory_ttl_s=5.0)
    )
    policy = RuleRegionResourcePolicy(
        RuleRegionResourcePolicyConfig(projection=projector.config),
        projector=projector,
    )
    advisory = projector.build_advisory_contract(source, policy.recommend(source))
    if adoption_kind == RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value:
        applied_plan_id = "PLAN-NEW"
        applied_plan_version = 3
    else:
        applied_plan_id = "PLAN-OLD"
        applied_plan_version = 2
    applied_plan_payload = {
        "plan_id": applied_plan_id,
        "plan_version": applied_plan_version,
        "assignments": [],
        "metadata": {"authority_epoch": 4, "owner_node_id": "C2"},
    }
    applied_plan_hash = canonical_runtime_payload_sha256(applied_plan_payload)
    ack = RegionResourceRuntimeAckEvidence(
        code=RegionResourceRuntimeAckCode.APPLIED.value,
        reason="validated runtime ACK fixture",
        runtime_advisory_applied_ack_available=True,
        adoption_kind=adoption_kind,
        advisory_id=advisory.advisory_id,
        advisory_version=7,
        source_plan_id="PLAN-OLD",
        source_plan_version=2,
        applied_plan_id=applied_plan_id,
        applied_plan_version=applied_plan_version,
        consumed_at_s=2.0,
        acknowledged_at_s=2.0,
        owner_layer="center",
        owner_node_id="C2",
        authority_epoch=4,
        lease_expires_at_s=10.0,
        source_plan_bus_sequence=21,
        advisory_source_plan_bus_sequence=(10 if applied_plan_id == "PLAN-OLD" else None),
        source_guidance_bus_sequence=24,
        ack_bus_sequence=25,
        advisory_payload_sha256=canonical_runtime_payload_sha256(advisory.to_dict()),
        source_plan_payload_sha256=applied_plan_hash,
        source_guidance_payload_sha256="a" * 64,
    )
    outcome = _snapshot(
        snapshot_id="SNAP-OUTCOME",
        timestamp_s=3.0,
        plan_id=applied_plan_id,
        plan_version=applied_plan_version,
        high_threat_backlog=0.5,
    )
    artifact_hash = "b" * 64
    components = []
    for name in REGION_RESOURCE_REWARD_WEIGHTS:
        components.append(
            {
                "schema": REGION_RESOURCE_REWARD_COMPONENT_SCHEMA,
                "name": name,
                "availability": "available",
                "raw_value": 0.1,
                "unit": "normalized_window_cost",
                "normalization_denominator": 1.0,
                "normalized_cost": 0.1,
                "source_artifact": "online_region_metrics",
                "source_artifact_sha256": artifact_hash,
                "reason": None,
            }
        )
    window: dict[str, object] = {
        "schema": REGION_RESOURCE_OUTCOME_WINDOW_SCHEMA,
        "window_id": "WINDOW-001",
        "window_version": 1,
        "episode_id": "EPISODE-017",
        "scenario_id": source.scenario_id,
        "scenario_version": source.scenario_version,
        "seed": source.seed,
        "advisory_id": advisory.advisory_id,
        "advisory_version": 7,
        "advisory_fingerprint_sha256": region_resource_advisory_fingerprint_sha256(
            advisory
        ),
        "model_sha256": advisory.model_sha256,
        "source_plan_id": "PLAN-OLD",
        "source_plan_version": 2,
        "applied_plan_id": applied_plan_id,
        "applied_plan_version": applied_plan_version,
        "adoption_kind": adoption_kind,
        "ack_bus_sequence": 25,
        "ack_timestamp_s": 2.0,
        "owner_layer": "center",
        "owner_node_id": "C2",
        "authority_epoch": 4,
        "lease_expires_at_s": 10.0,
        "window_start_s": 2.0,
        "window_end_s": 3.0,
        "window_interval": "left_closed_right_open",
        "source_snapshot_id": source.snapshot_id,
        "source_snapshot_version": source.snapshot_version,
        "source_snapshot_timestamp_s": source.timestamp_s,
        "source_snapshot_payload_sha256": canonical_runtime_payload_sha256(
            source.to_dict()
        ),
        "outcome_snapshot_id": outcome.snapshot_id,
        "outcome_snapshot_version": outcome.snapshot_version,
        "outcome_snapshot_timestamp_s": outcome.timestamp_s,
        "outcome_snapshot_payload_sha256": canonical_runtime_payload_sha256(
            outcome.to_dict()
        ),
        "execution_binding_sha256_start": applied_plan_hash,
        "execution_binding_sha256_end": applied_plan_hash,
        "coalition_binding_sha256_start": "c" * 64,
        "coalition_binding_sha256_end": "c" * 64,
        "region_generations": [
            {
                "region_id": "region-000",
                "owner_layer": "center",
                "owner_node_id": "C2",
                "epoch": 4,
                "lease_expires_at_s": 10.0,
                "fault_generation": None,
            }
        ],
        "provenance": {
            "schema": REGION_RESOURCE_OUTCOME_PROVENANCE_SCHEMA,
            "producer_name": "d6-regional-outcome-observer",
            "producer_version": "v1",
            "episode_id": "EPISODE-017",
            "clock": "episode_clock",
            "online_truth_use_count": 0,
            "source_artifacts": [
                {
                    "name": "online_region_metrics",
                    "schema": "scalable3d-online-region-metrics-v1",
                    "sha256": artifact_hash,
                }
            ],
        },
        "components": components,
        "window_payload_sha256": "",
    }
    _seal(window)
    return {
        "source": source,
        "advisory": advisory,
        "ack": ack,
        "outcome": outcome,
        "window": window,
    }


def _seal(window: dict[str, object]) -> None:
    window["window_payload_sha256"] = canonical_region_resource_outcome_window_sha256(
        window
    )


def _evaluate(
    fixture: dict[str, object],
    *,
    adapter: RegionResourceRewardEvidenceAdapter | None = None,
):
    return (adapter or RegionResourceRewardEvidenceAdapter()).evaluate(
        runtime_ack=fixture["ack"],  # type: ignore[arg-type]
        advisory_source=fixture["advisory"],  # type: ignore[arg-type]
        source_snapshot_source=fixture["source"],  # type: ignore[arg-type]
        outcome_snapshot_source=fixture["outcome"],  # type: ignore[arg-type]
        outcome_window_source=fixture["window"],  # type: ignore[arg-type]
    )


def test_new_execution_plan_produces_noncausal_window_reward() -> None:
    evidence = _evaluate(_fixture())

    assert evidence.code == RegionResourceRewardEvidenceCode.AVAILABLE.value
    assert evidence.outcome_window_available is True
    assert evidence.observational_cost == pytest.approx(0.1)
    assert evidence.window_attributed_reward == pytest.approx(-0.1)
    assert evidence.attribution_scope.endswith("noncausal")
    assert evidence.ack_bus_sequence == 25
    assert evidence.coalition_member_ack_available is False
    assert evidence.physical_execution_outcome_available is False
    assert evidence.causal_attribution_available is False
    assert evidence.paired_shadow_available is False
    assert evidence.on_policy_evidence_available is False
    assert evidence.ppo_admission_allowed is False
    assert evidence.assist_admission_allowed is False
    assert evidence.authority_admission_allowed is False
    assert evidence.rule_fallback_required is True


def test_evaluation_refresh_is_observation_only() -> None:
    fixture = _fixture(
        adoption_kind=(
            RegionResourceRuntimeAdoptionKind.EVALUATION_REFRESH_APPLIED.value
        )
    )

    evidence = _evaluate(fixture)

    assert evidence.code == RegionResourceRewardEvidenceCode.REFRESH_ONLY.value
    assert evidence.outcome_window_available is True
    assert evidence.observational_cost_available is True
    assert evidence.observational_cost == pytest.approx(0.1)
    assert evidence.window_attributed_reward_available is False
    assert evidence.window_attributed_reward is None


def test_unavailable_component_is_not_zero_filled() -> None:
    fixture = _fixture()
    component = fixture["window"]["components"][0]  # type: ignore[index]
    component.update(  # type: ignore[union-attr]
        {
            "availability": "unavailable",
            "raw_value": None,
            "unit": None,
            "normalization_denominator": None,
            "normalized_cost": None,
            "reason": "regional_backlog_series_missing",
        }
    )
    _seal(fixture["window"])  # type: ignore[arg-type]

    evidence = _evaluate(fixture)

    assert evidence.code == RegionResourceRewardEvidenceCode.COMPONENTS_UNAVAILABLE.value
    assert evidence.outcome_window_available is True
    assert evidence.observational_cost_available is False
    assert evidence.observational_cost is None
    assert evidence.window_attributed_reward_available is False
    unavailable = next(
        item for item in evidence.components if item.availability == "unavailable"
    )
    assert unavailable.raw_value is None
    assert unavailable.reason == "regional_backlog_series_missing"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("missing_ack", RegionResourceRewardEvidenceCode.RUNTIME_ACK_MISSING),
        ("ack_unavailable", RegionResourceRewardEvidenceCode.RUNTIME_ACK_UNAVAILABLE),
        ("missing_component", RegionResourceRewardEvidenceCode.REQUIRED_FIELD_MISSING),
        ("ack_sequence", RegionResourceRewardEvidenceCode.ACK_BINDING_MISMATCH),
        ("advisory_fingerprint", RegionResourceRewardEvidenceCode.MODEL_FINGERPRINT_MISMATCH),
        ("source_plan", RegionResourceRewardEvidenceCode.PLAN_BINDING_MISMATCH),
        ("expired_lease", RegionResourceRewardEvidenceCode.LEASE_EXPIRED),
        ("execution_changed", RegionResourceRewardEvidenceCode.EXECUTION_BINDING_CHANGED),
        ("coalition_changed", RegionResourceRewardEvidenceCode.COALITION_BINDING_CHANGED),
        ("source_snapshot_hash", RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH),
        ("provenance_hash", RegionResourceRewardEvidenceCode.PROVENANCE_INVALID),
        ("truth_leakage", RegionResourceRewardEvidenceCode.TRUTH_LEAKAGE),
        ("window_hash", RegionResourceRewardEvidenceCode.PAYLOAD_HASH_MISMATCH),
    ),
)
def test_reward_evidence_fails_closed_matrix(
    mutation: str,
    expected_code: RegionResourceRewardEvidenceCode,
) -> None:
    fixture = _fixture()
    window = fixture["window"]
    ack = fixture["ack"]
    assert isinstance(window, dict)
    if mutation == "missing_ack":
        fixture["ack"] = None
    elif mutation == "ack_unavailable":
        fixture["ack"] = replace(
            ack,  # type: ignore[arg-type]
            runtime_advisory_applied_ack_available=False,
            adoption_kind=None,
            rejection_reasons=("rejected",),
        )
    elif mutation == "missing_component":
        window["components"] = window["components"][:-1]  # type: ignore[index]
        _seal(window)
    elif mutation == "ack_sequence":
        window["ack_bus_sequence"] = 26
        _seal(window)
    elif mutation == "advisory_fingerprint":
        window["advisory_fingerprint_sha256"] = "0" * 64
        _seal(window)
    elif mutation == "source_plan":
        window["source_plan_version"] = 1
        _seal(window)
    elif mutation == "expired_lease":
        window["window_end_s"] = 10.0
        window["outcome_snapshot_timestamp_s"] = 10.0
        _seal(window)
    elif mutation == "execution_changed":
        window["execution_binding_sha256_end"] = "0" * 64
        _seal(window)
    elif mutation == "coalition_changed":
        window["coalition_binding_sha256_end"] = "0" * 64
        _seal(window)
    elif mutation == "source_snapshot_hash":
        window["source_snapshot_payload_sha256"] = "0" * 64
        _seal(window)
    elif mutation == "provenance_hash":
        window["components"][0]["source_artifact_sha256"] = "0" * 64  # type: ignore[index]
        _seal(window)
    elif mutation == "truth_leakage":
        window["provenance"]["source_artifacts"][0]["truth_id"] = "T001"  # type: ignore[index]
        _seal(window)
    elif mutation == "window_hash":
        window["window_payload_sha256"] = "0" * 64
    else:  # pragma: no cover
        raise AssertionError(mutation)

    evidence = _evaluate(fixture)

    assert evidence.outcome_window_available is False
    assert evidence.code == expected_code.value
    assert evidence.window_attributed_reward_available is False
    assert evidence.ppo_admission_allowed is False
    assert evidence.assist_admission_allowed is False
    assert evidence.authority_admission_allowed is False


def test_overlapping_window_is_rejected_without_mutating_first_evidence() -> None:
    adapter = RegionResourceRewardEvidenceAdapter()
    first_fixture = _fixture()
    first = _evaluate(first_fixture, adapter=adapter)
    second_fixture = deepcopy(first_fixture)
    second_fixture["window"]["window_id"] = "WINDOW-002"  # type: ignore[index]
    _seal(second_fixture["window"])  # type: ignore[arg-type]

    second = _evaluate(second_fixture, adapter=adapter)

    assert first.outcome_window_available is True
    assert second.code == RegionResourceRewardEvidenceCode.WINDOW_OVERLAP.value
    assert adapter.accepted_window_ids == ("WINDOW-001",)


def test_changed_or_stale_region_generation_fails_closed() -> None:
    fixture = _fixture()
    outcome = fixture["outcome"]
    assert isinstance(outcome, RegionResourceSnapshot)
    fixture["outcome"] = _snapshot(
        snapshot_id=outcome.snapshot_id,
        timestamp_s=outcome.timestamp_s,
        plan_id="PLAN-NEW",
        plan_version=3,
        epoch=3,
        high_threat_backlog=0.5,
    )
    window = fixture["window"]
    window["outcome_snapshot_payload_sha256"] = canonical_runtime_payload_sha256(  # type: ignore[index]
        fixture["outcome"].to_dict()  # type: ignore[union-attr]
    )
    _seal(window)  # type: ignore[arg-type]

    evidence = _evaluate(fixture)

    assert evidence.code == RegionResourceRewardEvidenceCode.STALE_GENERATION.value
    assert evidence.outcome_window_available is False


def test_d6_pair_progress_diagnostic_cannot_be_promoted_to_d4_reward() -> None:
    fixture = _fixture()
    fixture["window"] = {
        "schema_version": "d6.runtime-plan-outcome-join.v1",
        "binding_windows": [
            {
                "bounded_pair_progress_diagnostic": {
                    "available": True,
                    "value": 0.5,
                },
                "formal_d3_ppo_reward_available": False,
                "truth_target_id": "offline-only",
            }
        ],
    }

    evidence = _evaluate(fixture)

    assert evidence.code == RegionResourceRewardEvidenceCode.TRUTH_LEAKAGE.value
    assert evidence.outcome_window_available is False
    assert evidence.window_attributed_reward_available is False
