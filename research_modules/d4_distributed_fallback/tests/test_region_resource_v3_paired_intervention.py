from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Callable

import pytest

from d4_distributed_fallback.region_resource import (
    RecommendationSource,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
)
from d4_distributed_fallback.region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION,
)
from d4_distributed_fallback.region_resource_paired_intervention import (
    REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
    RegionResourcePairedArm,
    RegionResourcePairedInputBinding,
    RegionResourcePairedThresholds,
)
from d4_distributed_fallback.region_resource_v3_paired_intervention import (
    REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256,
    REGION_RESOURCE_V3_CANDIDATE_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_V3_DEVELOPMENT_SEEDS,
    REGION_RESOURCE_V3_MODEL_STATE_SHA256,
    REGION_RESOURCE_V3_PAIRED_THRESHOLDS,
    REGION_RESOURCE_V3_REGISTRY_BINDING,
    REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256,
    RegionResourceV3CandidateEvaluation,
    RegionResourceV3DevelopmentPairedSpecification,
    RegionResourceV3IsolatedCandidateLoader,
    RegionResourceV3IsolatedPairedAdvisor,
    RegionResourceV3IsolatedPairedDecision,
    RegionResourceV3PairedInterventionError,
    RegionResourceV3RegistryBinding,
    build_region_resource_v3_development_paired_specification,
)
from d4_distributed_fallback.regional_failover import (
    RegionalAuthorityLayer,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
V3_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
    / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
)


def _sha(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _snapshot(
    seed: int,
    *,
    region_count: int = 8,
    timestamp_s: float = 1.0,
) -> RegionResourceSnapshot:
    common = {
        "high_threat_backlog": 0.0,
        "d1_uncertainty": 0.16,
        "d2_uncertainty": 0.11,
        "d5_visibility": 0.87,
        "d5_consistency": 0.89,
        "available_resources": 5,
        "committed_resources": 0,
        "reserve_resources": 1,
        "secondary_coverage": 0.9,
        "secondary_readiness": 0.9,
        "communication_capacity": 50.0,
        "communication_latency_s": 0.02,
        "packet_loss_rate": 0.01,
        "current_owner_id": "CENTER",
        "current_owner_layer": RegionalAuthorityLayer.CENTER,
        "plan_id": f"development-plan-{seed}",
        "plan_version": 7,
        "epoch": 2,
        "lease_expires_at_s": 120.0,
        "coalition_ack_complete": True,
    }
    regions = tuple(
        RegionResourceNode(
            region_id=f"region-{index:03d}",
            target_demand=3.0,
            **common,
        )
        for index in range(region_count)
    )
    edges = tuple(
        RegionResourceEdge(
            source_region_id=f"region-{index:03d}",
            target_region_id=f"region-{(index + 1) % region_count:03d}",
            transferable_resources=0,
            distance_m=500.0 + 25.0 * index,
            transfer_time_s=10.0 + index,
            bandwidth_mbps=20.0,
            edge_id=f"edge-{index:03d}",
            bidirectional=True,
        )
        for index in range(region_count)
    )
    return RegionResourceSnapshot(
        snapshot_id=f"v3-development-snapshot-{seed}",
        scenario_id=f"v3-development-{region_count}-region",
        scenario_version="v1",
        seed=seed,
        timestamp_s=timestamp_s,
        regions=regions,
        edges=edges,
    )


def _binding(snapshot: RegionResourceSnapshot) -> RegionResourcePairedInputBinding:
    return RegionResourcePairedInputBinding(
        seed=snapshot.seed,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        scenario_config_sha256=_sha(f"config-{snapshot.seed}"),
        initial_state_sha256=_sha(f"initial-{snapshot.seed}"),
        communication_schedule_sha256=_sha(
            f"communication-{snapshot.seed}"
        ),
        fault_schedule_sha256=_sha(f"fault-{snapshot.seed}"),
        region_snapshot_lineage_sha256=_sha(
            f"lineage-{snapshot.seed}"
        ),
    )


@pytest.fixture(scope="module")
def specification() -> RegionResourceV3DevelopmentPairedSpecification:
    snapshots = {
        seed: _snapshot(seed) for seed in REGION_RESOURCE_V3_DEVELOPMENT_SEEDS
    }
    return build_region_resource_v3_development_paired_specification(
        experiment_id="v3-development-paired-20v20",
        experiment_version="v1",
        input_bindings=tuple(
            _binding(snapshots[seed]) for seed in sorted(snapshots)
        ),
        candidate_root=V3_ROOT,
    )


def _matching_candidate(
    advisor: RegionResourceV3IsolatedPairedAdvisor,
    snapshot: RegionResourceSnapshot,
) -> RegionResourceRecommendation:
    rule = advisor.executor.rule_policy.recommend(snapshot)
    return replace(
        rule,
        policy_name=REGION_RESOURCE_V3_REGISTRY_BINDING.policy_name,
        policy_version=(
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
        ),
        source=RecommendationSource.LEARNED,
        confidence=0.90,
        projected=False,
        model_sha256=REGION_RESOURCE_V3_MODEL_STATE_SHA256,
        projection_rejections=(),
    )


def _passing_evaluation(
    advisor: RegionResourceV3IsolatedPairedAdvisor,
    snapshot: RegionResourceSnapshot,
) -> RegionResourceV3CandidateEvaluation:
    return RegionResourceV3CandidateEvaluation(
        raw_recommendation=_matching_candidate(advisor, snapshot),
        candidate_manifest_file_sha256=(
            REGION_RESOURCE_V3_CANDIDATE_MANIFEST_FILE_SHA256
        ),
        candidate_manifest_content_sha256=(
            REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256
        ),
        bundle_manifest_sha256=(
            REGION_RESOURCE_V3_REGISTRY_BINDING.bundle_manifest_sha256
        ),
        model_state_sha256=REGION_RESOURCE_V3_MODEL_STATE_SHA256,
        candidate_latency_ms=2.0,
        candidate_scope_match=True,
        candidate_ood_passed=True,
        raw_output_finite=True,
        runtime_gate_applied=True,
        runtime_gate_passed=True,
        runtime_action_consistent=True,
        raw_confidence=0.90,
        effective_confidence=0.90,
        runtime_gate_content_sha256=(
            REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256
        ),
    )


def _inject_evaluation(
    advisor: RegionResourceV3IsolatedPairedAdvisor,
    factory: Callable[
        [RegionResourceSnapshot], RegionResourceV3CandidateEvaluation
    ],
) -> None:
    assert advisor.candidate_loader is not None
    advisor.candidate_loader.evaluate = (  # type: ignore[method-assign]
        lambda snapshot, formal_decision=None: factory(snapshot)
    )


def test_old_formal_inventory_and_ttl_remain_unchanged() -> None:
    assert REGION_RESOURCE_RESERVED_EVALUATION_SEEDS == tuple(
        range(1000, 1020)
    )
    assert RegionResourcePairedThresholds().advisory_ttl_s == 1.0
    assert set(REGION_RESOURCE_RESERVED_EVALUATION_SEEDS).isdisjoint(
        REGION_RESOURCE_V3_DEVELOPMENT_SEEDS
    )


def test_v3_loader_freezes_registry_identity_and_runtime_contract() -> None:
    loader = RegionResourceV3IsolatedCandidateLoader(V3_ROOT)
    gate = loader.loaded_bundle.manifest.runtime_confidence_gate

    assert loader.binding == REGION_RESOURCE_V3_REGISTRY_BINDING
    assert loader.manifest.applicable_region_count == 8
    assert loader.manifest.content_sha256 == (
        REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256
    )
    assert loader.loaded_bundle.manifest.state_dict_sha256 == (
        REGION_RESOURCE_V3_MODEL_STATE_SHA256
    )
    assert gate is not None
    assert gate.content_sha256 == (
        REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256
    )
    assert gate.fixed_minimum_confidence == 0.60
    assert gate.fixed_ood_margin == 0.05
    assert gate.projection_config == {
        "minimum_reserve_ratio": 0.10,
        "minimum_reserve_resources": 1,
        "advisory_ttl_s": 1.5,
    }
    assert gate.rule_policy_config == {
        "projection": gate.projection_config,
        "high_threat_weight": 2.0,
        "uncertainty_weight": 0.5,
        "transfer_pressure_margin": 0.05,
    }


def test_v3_spec_uses_frozen_development_inventory_and_round_trips(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    assert specification.development_seeds == tuple(range(2003, 2013))
    assert specification.formal_reserved_seeds == tuple(range(1000, 1020))
    assert specification.thresholds == REGION_RESOURCE_V3_PAIRED_THRESHOLDS
    assert specification.thresholds.advisory_ttl_s == 1.5
    assert specification.thresholds.minimum_confidence == 0.60
    assert specification.thresholds.ood_margin == 0.05
    assert specification.thresholds.minimum_reserve_ratio == 0.10
    assert specification.thresholds.minimum_reserve_resources == 1
    assert specification.isolated_treatment_influence_allowed is True
    assert specification.assist_enabled is False
    assert specification.authority_enabled is False
    assert specification.formal_evaluation_authorized is False
    assert (
        RegionResourceV3DevelopmentPairedSpecification.from_dict(
            json.loads(json.dumps(specification.to_dict()))
        )
        == specification
    )


def test_v3_registry_manifest_and_model_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    manifest_copy = (
        tmp_path
        / "manifest"
        / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    )
    shutil.copytree(V3_ROOT, manifest_copy)
    manifest_path = (
        manifest_copy / "eight_region_shadow_candidate_manifest.json"
    )
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
    with pytest.raises(
        RegionResourceV3PairedInterventionError,
        match="candidate_manifest_file_sha256_mismatch",
    ):
        RegionResourceV3IsolatedCandidateLoader(manifest_copy)

    model_copy = (
        tmp_path
        / "model"
        / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    )
    shutil.copytree(V3_ROOT, model_copy)
    state_path = model_copy / "bundle/state_dict.pt"
    state_path.write_bytes(state_path.read_bytes() + b"tamper")
    with pytest.raises(
        RegionResourceV3PairedInterventionError,
        match="candidate_artifact_sha256_mismatch:bundle/state_dict.pt",
    ):
        RegionResourceV3IsolatedCandidateLoader(model_copy)


def test_v3_registry_identity_failure_returns_rule_treatment(
    specification: RegionResourceV3DevelopmentPairedSpecification,
    tmp_path: Path,
) -> None:
    copied = (
        tmp_path / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    )
    shutil.copytree(V3_ROOT, copied)
    manifest_path = copied / "eight_region_shadow_candidate_manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding

    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, copied)
    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert advisor.candidate_loader_ready is False
    assert result.treatment.raw_inference_completed is False
    assert result.treatment.deterministic_rule_selected is True
    assert result.treatment.next_cycle_isolated_adoption is False
    assert any(
        "candidate_manifest_file_sha256_mismatch" in reason
        for reason in result.load_or_inference_rejection_reasons
    )


def test_v3_binding_identity_cannot_be_reconfigured() -> None:
    with pytest.raises(ValueError, match="binding mismatch: policy_version"):
        replace(
            REGION_RESOURCE_V3_REGISTRY_BINDING,
            policy_version="forged-policy-version",
        )
    with pytest.raises(ValueError, match="binding mismatch: applicable_region_count"):
        RegionResourceV3RegistryBinding(applicable_region_count=2)


def test_v3_passing_gate_returns_explicit_isolated_adoption(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)
    _inject_evaluation(
        advisor, lambda observed: _passing_evaluation(advisor, observed)
    )

    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert result.control.deterministic_rule_selected is True
    assert result.control.raw_inference_completed is False
    assert result.treatment.raw_inference_completed is True
    assert result.treatment.runtime_gate_applied is True
    assert result.treatment.runtime_gate_passed is True
    assert result.treatment.projection_passed is True
    assert result.treatment.next_cycle_isolated_adoption is True
    assert result.treatment.isolated_treatment_influence_allowed is True
    assert result.treatment.isolated_treatment_influence_adopted is True
    assert result.treatment.deterministic_rule_selected is False
    assert result.treatment.advisory_contract.advisory_ttl_s == 1.5
    assert result.production_runtime_ack_emitted is False
    assert result.assist_authority_granted is False
    assert result.degradation_authority_granted is False
    assert (
        RegionResourceV3IsolatedPairedDecision.from_dict(
            json.loads(json.dumps(result.to_dict()))
        )
        == result
    )


def test_v3_projection_failure_returns_rule_treatment(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)
    _inject_evaluation(
        advisor, lambda observed: _passing_evaluation(advisor, observed)
    )
    original_project = advisor.executor.projector.project

    def reject_candidate_projection(
        observed_snapshot: RegionResourceSnapshot,
        recommendation: RegionResourceRecommendation,
        *,
        formal_decision: object = None,
    ) -> RegionResourceRecommendation:
        if recommendation.source == RecommendationSource.LEARNED:
            raise ValueError("synthetic_candidate_projection_rejected")
        return original_project(
            observed_snapshot,
            recommendation,
            formal_decision=formal_decision,
        )

    advisor.executor.projector.project = reject_candidate_projection  # type: ignore[method-assign]
    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert result.treatment.runtime_gate_passed is True
    assert result.treatment.projection_passed is False
    assert result.treatment.deterministic_rule_selected is True
    assert result.treatment.next_cycle_isolated_adoption is False
    assert any(
        reason.startswith("candidate_projection_failed:")
        for reason in result.treatment.arm_evidence.rejection_reasons
    )


def test_v3_registered_model_uses_embedded_runtime_gate_before_fallback(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)

    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert result.candidate_evaluation is not None
    assert result.treatment.raw_inference_completed is True
    assert result.treatment.runtime_gate_applied is True
    assert result.candidate_evaluation.runtime_gate_content_sha256 == (
        REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256
    )
    assert result.treatment.next_cycle_isolated_adoption == (
        result.candidate_evaluation.runtime_gate_passed
        and result.treatment.projection_passed
        and result.treatment.arm_evidence.next_cycle_consumption_passed
    )


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        (
            lambda evaluation: replace(
                evaluation,
                runtime_gate_passed=False,
                runtime_action_consistent=False,
                effective_confidence=0.59,
                runtime_gate_rejection_reasons=(
                    "candidate_runtime_action_inconsistent",
                    "candidate_runtime_effective_confidence_below_minimum",
                ),
            ),
            "candidate_runtime_action_inconsistent",
        ),
        (
            lambda evaluation: replace(
                evaluation,
                candidate_latency_ms=60.0,
                runtime_gate_passed=False,
                runtime_gate_rejection_reasons=(
                    "candidate_inference_timeout",
                ),
            ),
            "candidate_inference_timeout",
        ),
        (
            lambda evaluation: replace(
                evaluation,
                candidate_ood_passed=False,
                runtime_gate_passed=False,
                runtime_gate_rejection_reasons=(
                    "candidate_ood_rejected",
                ),
            ),
            "candidate_ood_rejected",
        ),
    ),
)
def test_v3_runtime_gate_failures_fall_back_to_rule(
    specification: RegionResourceV3DevelopmentPairedSpecification,
    mutation: Callable[
        [RegionResourceV3CandidateEvaluation],
        RegionResourceV3CandidateEvaluation,
    ],
    expected_reason: str,
) -> None:
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)
    _inject_evaluation(
        advisor,
        lambda observed: mutation(_passing_evaluation(advisor, observed)),
    )

    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert result.treatment.raw_inference_completed is True
    assert result.treatment.runtime_gate_passed is False
    assert result.treatment.next_cycle_isolated_adoption is False
    assert result.treatment.deterministic_rule_selected is True
    assert result.treatment.arm_evidence.rule_fallback_used is True
    assert expected_reason in result.load_or_inference_rejection_reasons


def test_v3_nonfinite_inference_failure_falls_back_to_rule(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)
    assert advisor.candidate_loader is not None

    def nonfinite_failure(
        _snapshot: RegionResourceSnapshot,
        *,
        formal_decision: object = None,
    ) -> RegionResourceV3CandidateEvaluation:
        del formal_decision
        raise ValueError("candidate_output_nonfinite")

    advisor.candidate_loader.evaluate = nonfinite_failure  # type: ignore[method-assign]
    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert result.candidate_evaluation is None
    assert result.treatment.raw_inference_completed is False
    assert result.treatment.runtime_gate_passed is False
    assert result.treatment.deterministic_rule_selected is True
    assert result.treatment.next_cycle_isolated_adoption is False
    assert any(
        "candidate_output_nonfinite" in reason
        for reason in result.load_or_inference_rejection_reasons
    )


def test_v3_scope_mismatch_fails_before_model_inference(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    snapshot = _snapshot(2003, region_count=2)
    binding = replace(
        specification.arm_for(
            2003, RegionResourcePairedArm.TREATMENT
        ).input_binding,
        scenario_id=snapshot.scenario_id,
    )
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)

    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.0,
    )

    assert result.treatment.candidate_scope_compatible is False
    assert result.treatment.raw_inference_completed is False
    assert result.treatment.deterministic_rule_selected is True
    assert result.treatment.next_cycle_isolated_adoption is False
    assert "v3_candidate_scope_region_count_mismatch" in (
        result.load_or_inference_rejection_reasons
    )


def test_v3_ttl_15_expires_fail_closed(
    specification: RegionResourceV3DevelopmentPairedSpecification,
) -> None:
    snapshot = _snapshot(2003)
    binding = specification.arm_for(
        2003, RegionResourcePairedArm.TREATMENT
    ).input_binding
    advisor = RegionResourceV3IsolatedPairedAdvisor(specification, V3_ROOT)
    _inject_evaluation(
        advisor, lambda observed: _passing_evaluation(advisor, observed)
    )

    result = advisor.advise_pair(
        seed=2003,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=2.51,
    )

    assert result.treatment.runtime_gate_passed is True
    assert result.treatment.projection_passed is False
    assert result.treatment.next_cycle_isolated_adoption is False
    assert result.treatment.deterministic_rule_selected is True
    assert "advisory_window_expired_before_next_cycle" in (
        result.treatment.arm_evidence.rejection_reasons
    )
