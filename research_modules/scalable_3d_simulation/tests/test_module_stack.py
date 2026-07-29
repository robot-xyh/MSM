from __future__ import annotations

from collections import Counter
from dataclasses import replace
import csv
import importlib
import json
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
    ExperimentalCentroidEvidenceDisposition,
    GlobalTrack,
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
    SensorObservation,
    StructuralAmbiguityCandidateEdge,
    StructuralAmbiguityEvidence,
    StructuralAmbiguityMemberState,
    StructuralAmbiguityObservationEvidence,
    TrackLevel,
    structural_ambiguity_member_track_token,
    structural_ambiguity_source_key,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    RegionalPlanAuthorityError,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    AdvisorMode,
    ConstrainedDevelopmentRegionResourceAdapter,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAdvisoryResult,
    RegionResourceDevelopmentInterventionConfig,
    RegionResourceProjectionConfig,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
    formal_decision_digest,
)
from research_modules.d5_terminal_association.src.d5_terminal_association import (
    ActiveVisionPolicyProposal,
    DeterministicLookAtScanPolicy,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION,
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.reporting import (
    STAGE_TIMING_SCHEMA_VERSION,
    write_batch_outputs,
)
from research_modules.scalable_3d_simulation.scenarios import make_curriculum_scenario
from research_modules.scalable_3d_simulation.world import (
    REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION,
    VectorizedPointMassWorld,
)


class _FiniteLearnedRegionPolicy:
    """Deterministic learned-policy stand-in for main bridge tests."""

    def __init__(self, projection: RegionResourceProjectionConfig) -> None:
        self._rule = RuleRegionResourcePolicy(
            RuleRegionResourcePolicyConfig(projection=projection)
        )

    def is_ood(self, snapshot, *, margin: float) -> bool:
        del snapshot, margin
        return False

    def recommend_raw(self, snapshot):
        rule = self._rule.recommend(snapshot)
        return replace(
            rule,
            policy_name="test-finite-region-policy",
            policy_version="v1",
            source=RecommendationSource.LEARNED,
            projected=False,
            model_sha256="a" * 64,
            fallback_reason=None,
        )


def test_regional_resource_probe_limits_default_d3_resource_reachability() -> None:
    target_counts = (2, 4, 2, 3, 2, 3, 2, 2)
    resource_counts = (4, 1, 2, 3, 2, 3, 2, 3)
    config = ScenarioConfig(
        target_count=sum(target_counts),
        resource_count=sum(resource_counts),
        recon_count=2,
        region_count=8,
        duration_s=0.1,
        metadata={
            "regional_resource_locality_enforced": True,
            "regional_resource_probe": {
                "schema": REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION,
                "target_counts_by_region": target_counts,
                "resource_counts_by_region": resource_counts,
            },
        },
    )
    world = VectorizedPointMassWorld(config)
    snapshot = world.snapshot()
    stack = IntegratedScalableModuleStack()
    stack.reset(config)
    navigation = SimpleNamespace(
        platform_ids=world.interceptor_ids,
        active=snapshot.interceptors.active,
        state_ned=snapshot.interceptors.state,
        covariance=np.repeat(
            np.eye(6, dtype=float)[None, :, :],
            config.resource_count,
            axis=0,
        ),
    )

    resources = stack._d3_resources(navigation)

    assert resources
    assert all(
        resource.reachable_target_region_ids == (resource.region_id,)
        for resource in resources
    )


class _IdentifiableHoldRegionPolicy:
    """Force one bounded, D3-consumable intervention for audit tests."""

    def __init__(self, base: _FiniteLearnedRegionPolicy) -> None:
        self._base = base

    def is_ood(self, snapshot, *, margin: float) -> bool:
        return self._base.is_ood(snapshot, margin=margin)

    def recommend_raw(self, snapshot):
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


class _AdmittedRegionAdvisoryFixture:
    """Test-only source for an already-admitted D4 transport contract."""

    def __init__(
        self,
        *,
        ttl_s: float,
        identifiable_intervention: bool = False,
        constrained_development_intervention: bool = False,
    ) -> None:
        if identifiable_intervention and constrained_development_intervention:
            raise ValueError("select only one intervention fixture")
        projection = RegionResourceProjectionConfig(advisory_ttl_s=ttl_s)
        self.projection_config = projection
        self.projector = DeterministicResourceProjector(projection)
        self._base_policy = _FiniteLearnedRegionPolicy(projection)
        self._policy = (
            _IdentifiableHoldRegionPolicy(self._base_policy)
            if identifiable_intervention
            else self._base_policy
        )
        self._constrained_development_intervention = bool(
            constrained_development_intervention
        )

    def advise(
        self,
        snapshot,
        *,
        formal_decision=None,
        unseen_seed_count: int = 0,
    ) -> RegionResourceAdvisoryResult:
        if self._constrained_development_intervention:
            policy = ConstrainedDevelopmentRegionResourceAdapter(
                self._base_policy,
                config=RegionResourceDevelopmentInterventionConfig(
                    enabled=True,
                    run_label="main-a2-full-episode-development-probe",
                    allowed_scenario_ids=(snapshot.scenario_id,),
                    force_request_replan_on_projected_noop=True,
                    projection=self.projection_config,
                ),
            )
            raw = policy.recommend_raw(
                snapshot,
                formal_decision=formal_decision,
            )
        else:
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


def _assist_region_advisor(
    *,
    ttl_s: float = 1.5,
    identifiable_intervention: bool = False,
) -> _AdmittedRegionAdvisoryFixture:
    return _AdmittedRegionAdvisoryFixture(
        ttl_s=ttl_s,
        identifiable_intervention=identifiable_intervention,
    )


def _development_region_advisor(
    *,
    ttl_s: float = 1.5,
) -> _AdmittedRegionAdvisoryFixture:
    """Route D4's real development adapter without admitting it for benefit."""

    return _AdmittedRegionAdvisoryFixture(
        ttl_s=ttl_s,
        constrained_development_intervention=True,
    )


class _AdmittedActiveVisionPolicyFixture:
    """Admitted policy stand-in for the main A3 runtime evidence bridge."""

    available = True
    assist_admitted = True
    failure_reason = None
    model_fingerprint = f"sha256:{'a' * 64}"
    bundle_manifest_sha256 = "b" * 64
    bundle_weights_sha256 = "c" * 64
    manifest = {
        "model_semantic_version": "test-a3",
        "code_provenance": {
            "implementation_sha256": "d" * 64,
        },
    }

    def __init__(self) -> None:
        self._rule = DeterministicLookAtScanPolicy()

    def propose(
        self,
        snapshot,
        *,
        camera_id: str,
        current_timestamp: float,
    ) -> ActiveVisionPolicyProposal:
        action = self._rule.select_action(
            snapshot,
            camera_id=camera_id,
            current_timestamp=current_timestamp,
            expected_plan_version=snapshot.plan.plan_version,
            expected_coalition_version=snapshot.plan.coalition_version,
            expected_communication_version=(
                snapshot.communication.communication_version
            ),
        )
        return ActiveVisionPolicyProposal(
            action=action,
            confidence=1.0,
            inference_latency_ms=0.01,
            model_fingerprint=self.model_fingerprint,
        )


def test_recon_track_cues_are_fail_closed_by_default() -> None:
    assert IntegratedStackConfig().d5_recon_track_cues_enabled is False


def test_d1_scan_input_selection_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_scan_input_selection",
        scenario_version="d1-scan-input-selection-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.2,
        seed=17,
    )
    default = IntegratedStackConfig()
    assert default.d1_scan_input_implementation == "candidate_v2"

    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_scan_input_implementation="reference_v1",
        )
    )
    manifest_profile = stack.runtime_manifest_profile_for_scenario(config)
    assert manifest_profile["configuration"][
        "d1_scan_input_implementation"
    ] == "reference_v1"
    assert manifest_profile["d1_scan_input_implementation"] == "reference_v1"
    assert manifest_profile["d1_scan_input_execution_config"][
        "implementation"
    ] == "reference_v1"

    result = run_episode(config, module_stack=stack)
    governance = result.observation_governance_audit
    assert governance is not None
    assert governance["d1_scan_input_implementation"] == "reference_v1"
    assert governance["d1_scan_input_execution_config"][
        "implementation"
    ] == "reference_v1"
    assert governance["d1_scan_input_performance_diagnostics"][
        "implementation"
    ] == "reference_v1"
    assert result.summary["d1_scan_input_implementation"] == "reference_v1"
    assert result.summary["d1_scan_input_execution_config"] == governance[
        "d1_scan_input_execution_config"
    ]
    assert result.summary["d1_scan_input_performance_diagnostics"] == governance[
        "d1_scan_input_performance_diagnostics"
    ]
    assert result.manifest.runtime_profile[
        "d1_scan_input_execution_config"
    ]["implementation"] == "reference_v1"

    with pytest.raises(
        ValueError,
        match="d1_scan_input_implementation must be",
    ):
        IntegratedStackConfig(d1_scan_input_implementation="unknown")


def test_d1_online_batch_frame_selection_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_online_batch_frame_selection",
        scenario_version="d1-online-batch-frame-selection-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=1.0,
        seed=19,
    )
    default = IntegratedStackConfig()
    assert default.d1_online_batch_frame_implementation == (
        ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
    )
    assert ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION == (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )

    stack = IntegratedScalableModuleStack(default)
    manifest_profile = stack.runtime_manifest_profile_for_scenario(config)
    assert manifest_profile["configuration"][
        "d1_online_batch_frame_implementation"
    ] == ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    assert manifest_profile["d1_online_batch_frame_implementation"] == (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    assert manifest_profile["d1_online_batch_frame_execution_config"][
        "implementation"
    ] == ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    assert manifest_profile["d1_online_batch_frame_execution_config"][
        "candidate_default_enabled"
    ] is True

    result = run_episode(config, module_stack=stack)
    governance = result.observation_governance_audit
    assert governance is not None
    assert governance["d1_online_batch_frame_implementation"] == (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    assert governance["d1_online_batch_frame_execution_config"][
        "implementation"
    ] == ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    diagnostics = governance["d1_online_batch_frame_diagnostics"]
    counts = diagnostics["operation_counts"]
    assert counts["request_count"] > 0
    assert counts["request_count"] == counts["successful_build_count"]
    assert counts["candidate_closed_handoff_count"] == counts["request_count"]
    assert counts["candidate_reference_fallback_count"] == 0
    assert all(diagnostics["conservation"].values())
    assert result.summary["d1_online_batch_frame_implementation"] == (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    assert result.summary["d1_online_batch_frame_execution_config"] == (
        governance["d1_online_batch_frame_execution_config"]
    )
    assert result.summary["d1_online_batch_frame_diagnostics"] == diagnostics
    assert result.manifest.runtime_profile[
        "d1_online_batch_frame_execution_config"
    ]["implementation"] == ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION

    with pytest.raises(
        ValueError,
        match="d1_online_batch_frame_implementation must be",
    ):
        IntegratedStackConfig(
            d1_online_batch_frame_implementation="unknown"
        )


def test_episode_cli_exposes_d1_online_batch_frame_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert default_args.d1_online_batch_frame_implementation == (
        ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-online-batch-frame-implementation",
            ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
        ]
    )
    assert args.d1_online_batch_frame_implementation == (
        ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
    )


def test_d1_publication_metadata_selection_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_publication_metadata_selection",
        scenario_version="d1-publication-metadata-selection-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.6,
        seed=23,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_publication_metadata_implementation
        == "immutable_shared_v2"
    )
    reference = IntegratedStackConfig(
        d1_publication_metadata_implementation="per_track_copy_v1"
    )
    assert (
        reference.d1_publication_metadata_implementation
        == "per_track_copy_v1"
    )

    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publication_metadata_implementation="immutable_shared_v2",
        )
    )
    manifest_profile = stack.runtime_manifest_profile_for_scenario(config)
    assert manifest_profile["configuration"][
        "d1_publication_metadata_implementation"
    ] == "immutable_shared_v2"
    assert manifest_profile[
        "d1_publication_metadata_implementation"
    ] == "immutable_shared_v2"

    result = run_episode(config, module_stack=stack)
    governance = result.observation_governance_audit
    assert governance is not None
    assert governance[
        "d1_publication_metadata_implementation"
    ] == "immutable_shared_v2"
    diagnostics = governance["d1_publication_metadata_diagnostics"]
    assert diagnostics["immutable_shared_publication_metadata"] is True
    assert diagnostics["implementation_id"].endswith(
        "immutable_shared_audit.v2"
    )
    assert (
        diagnostics["publication_audit_contract_version"]
        == "d1.publication_audit_tree.v2"
    )
    assert result.summary[
        "d1_publication_metadata_implementation"
    ] == "immutable_shared_v2"
    assert result.summary[
        "d1_publication_metadata_diagnostics"
    ] == diagnostics
    d2_audit = result.summary["d2_publication_metadata_audit"]
    assert (
        d2_audit["schema_version"]
        == "scalable3d-d2-publication-metadata-audit-v1"
    )
    assert d2_audit["batch_count"] > 0
    totals = d2_audit["totals"]
    assert totals["immutable_v2_contract_validation_count"] > 0
    assert (
        totals["immutable_v2_contract_validation_count"]
        == totals["immutable_v2_full_content_audit_count"]
    )
    assert totals["immutable_v2_identity_reuse_count"] > 0
    assert totals["immutable_v2_contract_rejection_count"] == 0
    assert totals["shared_subtree_builtin_equivalent_reuse_count"] == 0
    assert (
        result.observation_governance_audit[
            "d2_publication_metadata_audit"
        ]
        == d2_audit
    )
    assert result.manifest.runtime_profile[
        "d1_publication_metadata_implementation"
    ] == "immutable_shared_v2"

    with pytest.raises(
        ValueError,
        match="d1_publication_metadata_implementation must be",
    ):
        IntegratedStackConfig(
            d1_publication_metadata_implementation="immutable_shared_v1"
        )

    with pytest.raises(
        ValueError,
        match="d1_publication_metadata_implementation must be",
    ):
        IntegratedStackConfig(
            d1_publication_metadata_implementation="unknown"
        )


def test_d1_cv_motion_model_cache_selection_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_cv_motion_model_cache_selection",
        scenario_version="d1-cv-motion-model-cache-selection-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.6,
        seed=29,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_cv_motion_model_implementation
        == "bounded_exact_lru_v1"
    )
    assert default.d1_cv_motion_model_cache_capacity == 128

    reference_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_cv_motion_model_implementation="per_prediction_build_v1",
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_cv_motion_model_implementation="bounded_exact_lru_v1",
            d1_cv_motion_model_cache_capacity=7,
        )
    )
    reference_profile = reference_stack.runtime_manifest_profile_for_scenario(
        config
    )
    candidate_profile = candidate_stack.runtime_manifest_profile_for_scenario(
        config
    )
    assert reference_profile["d1_cv_motion_model_implementation"] == (
        "per_prediction_build_v1"
    )
    assert candidate_profile["d1_cv_motion_model_implementation"] == (
        "bounded_exact_lru_v1"
    )
    assert candidate_profile["configuration"][
        "d1_cv_motion_model_cache_capacity"
    ] == 7
    initial_diagnostics = candidate_profile[
        "d1_cv_motion_model_cache_diagnostics"
    ]
    assert initial_diagnostics["candidate_enabled"] is True
    assert initial_diagnostics["cache_capacity"] == 7
    assert initial_diagnostics["cache_entry_count"] == 0
    assert initial_diagnostics["operation_counts"] == {}
    assert initial_diagnostics["implementation_id"].endswith(
        "bounded_exact_lru.v1"
    )

    reference_result = run_episode(config, module_stack=reference_stack)
    candidate_result = run_episode(config, module_stack=candidate_stack)
    assert (
        reference_result.manifest.runtime_profile_sha256
        != candidate_result.manifest.runtime_profile_sha256
    )
    governance = candidate_result.observation_governance_audit
    assert governance is not None
    assert governance["d1_cv_motion_model_implementation"] == (
        "bounded_exact_lru_v1"
    )
    diagnostics = governance["d1_cv_motion_model_cache_diagnostics"]
    assert diagnostics["candidate_enabled"] is True
    assert diagnostics["cache_capacity"] == 7
    assert diagnostics["implementation_id"].endswith(
        "bounded_exact_lru.v1"
    )
    assert diagnostics["operation_counts"]["prediction_request_count"] > 0
    assert candidate_result.summary[
        "d1_cv_motion_model_implementation"
    ] == "bounded_exact_lru_v1"
    assert candidate_result.summary[
        "d1_cv_motion_model_cache_diagnostics"
    ] == diagnostics
    assert candidate_result.summary["module_final_diagnostics"][
        "d1_cv_motion_model_cache_diagnostics"
    ] == diagnostics

    with pytest.raises(
        ValueError,
        match="d1_cv_motion_model_implementation must be",
    ):
        IntegratedStackConfig(d1_cv_motion_model_implementation="unknown")
    with pytest.raises(
        TypeError,
        match="d1_cv_motion_model_cache_capacity must be an integer",
    ):
        IntegratedStackConfig(d1_cv_motion_model_cache_capacity=True)
    with pytest.raises(
        ValueError,
        match="d1_cv_motion_model_cache_capacity must be between",
    ):
        IntegratedStackConfig(d1_cv_motion_model_cache_capacity=0)
    with pytest.raises(
        ValueError,
        match="d1_cv_motion_model_cache_capacity must be between",
    ):
        IntegratedStackConfig(d1_cv_motion_model_cache_capacity=4_097)


def test_episode_cli_exposes_d1_cv_motion_model_cache_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_cv_motion_model_implementation
        == "bounded_exact_lru_v1"
    )
    assert default_args.d1_cv_motion_model_cache_capacity == 128
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-cv-motion-model-implementation",
            "bounded_exact_lru_v1",
            "--d1-cv-motion-model-cache-capacity",
            "17",
        ]
    )
    assert (
        args.d1_cv_motion_model_implementation
        == "bounded_exact_lru_v1"
    )
    assert args.d1_cv_motion_model_cache_capacity == 17


def test_d1_opaque_source_identity_cache_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_opaque_source_identity_cache_selection",
        scenario_version="d1-opaque-source-identity-cache-selection-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.6,
        seed=30,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_opaque_source_identity_implementation
        == "per_publication_build_v1"
    )
    assert default.d1_opaque_source_identity_cache_capacity == 1_024

    reference_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publish_opaque_source_key=True,
            d1_opaque_source_identity_implementation=(
                "per_publication_build_v1"
            ),
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publish_opaque_source_key=True,
            d1_opaque_source_identity_implementation=(
                "bounded_generation_lru_v1"
            ),
            d1_opaque_source_identity_cache_capacity=7,
        )
    )
    reference_profile = reference_stack.runtime_manifest_profile_for_scenario(
        config
    )
    candidate_profile = candidate_stack.runtime_manifest_profile_for_scenario(
        config
    )
    assert reference_profile[
        "d1_opaque_source_identity_implementation"
    ] == "per_publication_build_v1"
    assert candidate_profile[
        "d1_opaque_source_identity_implementation"
    ] == "bounded_generation_lru_v1"
    assert candidate_profile["configuration"][
        "d1_opaque_source_identity_cache_capacity"
    ] == 7
    initial = candidate_profile[
        "d1_opaque_source_identity_cache_diagnostics"
    ]
    assert initial["candidate_enabled"] is True
    assert initial["cache_capacity"] == 7
    assert initial["cache_entry_count"] == 0
    assert initial["operation_counts"] == {}
    assert all(initial["conservation"].values())
    assert initial["implementation_id"].endswith(
        "bounded_generation_lru.v1"
    )

    reference_result = run_episode(config, module_stack=reference_stack)
    candidate_result = run_episode(config, module_stack=candidate_stack)
    assert (
        reference_result.manifest.runtime_profile_sha256
        != candidate_result.manifest.runtime_profile_sha256
    )
    for result, expected_selector, expected_candidate in (
        (reference_result, "per_publication_build_v1", False),
        (candidate_result, "bounded_generation_lru_v1", True),
    ):
        governance = result.observation_governance_audit
        assert governance is not None
        assert governance[
            "d1_opaque_source_identity_implementation"
        ] == expected_selector
        diagnostics = governance[
            "d1_opaque_source_identity_cache_diagnostics"
        ]
        assert diagnostics["candidate_enabled"] is expected_candidate
        assert diagnostics["cache_capacity"] == (
            7 if expected_candidate else 1_024
        )
        assert diagnostics["operation_counts"]["request_count"] > 0
        assert all(diagnostics["conservation"].values())
        assert result.summary[
            "d1_opaque_source_identity_implementation"
        ] == expected_selector
        assert result.summary[
            "d1_opaque_source_identity_cache_diagnostics"
        ] == diagnostics
        assert result.summary["module_final_diagnostics"][
            "d1_opaque_source_identity_cache_diagnostics"
        ] == diagnostics

    reference_counts = reference_result.summary[
        "d1_opaque_source_identity_cache_diagnostics"
    ]["operation_counts"]
    candidate_counts = candidate_result.summary[
        "d1_opaque_source_identity_cache_diagnostics"
    ]["operation_counts"]
    assert reference_counts["reference_bypass_count"] > 0
    assert reference_counts.get("cache_hit_count", 0) == 0
    assert candidate_counts["cache_hit_count"] > 0
    assert candidate_counts.get("reference_bypass_count", 0) == 0
    assert candidate_counts["identity_build_count"] < (
        reference_counts["identity_build_count"]
    )

    with pytest.raises(
        ValueError,
        match="d1_opaque_source_identity_implementation must be",
    ):
        IntegratedStackConfig(
            d1_opaque_source_identity_implementation="unknown"
        )
    with pytest.raises(
        TypeError,
        match="d1_opaque_source_identity_cache_capacity must be an integer",
    ):
        IntegratedStackConfig(
            d1_opaque_source_identity_cache_capacity=True
        )
    with pytest.raises(
        ValueError,
        match="d1_opaque_source_identity_cache_capacity must be between",
    ):
        IntegratedStackConfig(
            d1_opaque_source_identity_cache_capacity=0
        )
    with pytest.raises(
        ValueError,
        match="d1_opaque_source_identity_cache_capacity must be between",
    ):
        IntegratedStackConfig(
            d1_opaque_source_identity_cache_capacity=4_097
        )


def test_episode_cli_exposes_d1_opaque_source_identity_cache_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_opaque_source_identity_implementation
        == "per_publication_build_v1"
    )
    assert default_args.d1_opaque_source_identity_cache_capacity == 1_024
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-opaque-source-identity-implementation",
            "bounded_generation_lru_v1",
            "--d1-opaque-source-identity-cache-capacity",
            "17",
        ]
    )
    assert (
        args.d1_opaque_source_identity_implementation
        == "bounded_generation_lru_v1"
    )
    assert args.d1_opaque_source_identity_cache_capacity == 17


def test_d1_structured_jacobian_selection_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_structured_jacobian_selection",
        scenario_version="d1-structured-jacobian-selection-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.6,
        seed=31,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_structured_numerical_jacobian_implementation
        == "known_dimension_structural_columns_v1"
    )

    reference_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_structured_numerical_jacobian_implementation=(
                "dense_output_probe_v1"
            )
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_structured_numerical_jacobian_implementation=(
                "known_dimension_structural_columns_v1"
            )
        )
    )
    reference_profile = reference_stack.runtime_manifest_profile_for_scenario(
        config
    )
    candidate_profile = candidate_stack.runtime_manifest_profile_for_scenario(
        config
    )
    assert reference_profile[
        "d1_structured_numerical_jacobian_implementation"
    ] == "dense_output_probe_v1"
    assert candidate_profile[
        "d1_structured_numerical_jacobian_implementation"
    ] == "known_dimension_structural_columns_v1"
    initial = candidate_profile[
        "d1_structured_numerical_jacobian_diagnostics"
    ]
    assert initial["candidate_enabled"] is True
    assert initial["operation_counts"] == {}
    assert all(initial["conservation"].values())
    assert initial["implementation_id"].endswith(
        "known_dimension_structural_columns.v1"
    )

    reference_result = run_episode(config, module_stack=reference_stack)
    candidate_result = run_episode(config, module_stack=candidate_stack)
    assert (
        reference_result.manifest.runtime_profile_sha256
        != candidate_result.manifest.runtime_profile_sha256
    )
    for result, expected_selector, expected_candidate in (
        (reference_result, "dense_output_probe_v1", False),
        (
            candidate_result,
            "known_dimension_structural_columns_v1",
            True,
        ),
    ):
        governance = result.observation_governance_audit
        assert governance is not None
        assert governance[
            "d1_structured_numerical_jacobian_implementation"
        ] == expected_selector
        diagnostics = governance[
            "d1_structured_numerical_jacobian_diagnostics"
        ]
        assert diagnostics["candidate_enabled"] is expected_candidate
        assert diagnostics["operation_counts"]["jacobian_attempt_count"] > 0
        assert all(diagnostics["conservation"].values())
        assert result.summary[
            "d1_structured_numerical_jacobian_implementation"
        ] == expected_selector
        assert result.summary[
            "d1_structured_numerical_jacobian_diagnostics"
        ] == diagnostics
        assert result.summary["module_final_diagnostics"][
            "d1_structured_numerical_jacobian_diagnostics"
        ] == diagnostics

    reference_counts = reference_result.summary[
        "d1_structured_numerical_jacobian_diagnostics"
    ]["operation_counts"]
    candidate_counts = candidate_result.summary[
        "d1_structured_numerical_jacobian_diagnostics"
    ]["operation_counts"]
    assert reference_counts["reference_call_count"] > 0
    assert reference_counts.get("structured_candidate_call_count", 0) == 0
    assert candidate_counts["structured_candidate_call_count"] > 0
    assert candidate_counts.get("reference_call_count", 0) == 0
    assert (
        candidate_counts["measurement_function_evaluation_count"]
        < reference_counts["measurement_function_evaluation_count"]
    )

    with pytest.raises(
        ValueError,
        match="d1_structured_numerical_jacobian_implementation must be",
    ):
        IntegratedStackConfig(
            d1_structured_numerical_jacobian_implementation="unknown"
        )


def test_episode_cli_exposes_d1_structured_jacobian_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_structured_numerical_jacobian_implementation
        == "known_dimension_structural_columns_v1"
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-structured-numerical-jacobian-implementation",
            "dense_output_probe_v1",
        ]
    )
    assert (
        args.d1_structured_numerical_jacobian_implementation
        == "dense_output_probe_v1"
    )


def test_d1_association_sparse_prefilter_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_association_sparse_prefilter_selection",
        scenario_version="d1-association-sparse-prefilter-selection-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=1,
        duration_s=0.8,
        seed=32,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_association_sparse_prefilter_implementation
        == "disabled_v1"
    )

    reference_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_association_sparse_prefilter_implementation="disabled_v1"
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_association_sparse_prefilter_implementation=(
                "modality_conservative_quadratic_bound_v1"
            )
        )
    )
    reference_profile = reference_stack.runtime_manifest_profile_for_scenario(
        config
    )
    candidate_profile = candidate_stack.runtime_manifest_profile_for_scenario(
        config
    )
    assert (
        reference_profile["d1_association_sparse_prefilter_implementation"]
        == "disabled_v1"
    )
    assert candidate_profile[
        "d1_association_sparse_prefilter_implementation"
    ] == "modality_conservative_quadratic_bound_v1"
    assert (
        reference_profile
        != candidate_profile
    )
    initial = candidate_profile[
        "d1_association_sparse_prefilter_diagnostics"
    ]
    assert initial["candidate_enabled"] is True
    assert initial["execution_config"] == candidate_profile[
        "d1_association_sparse_prefilter_execution_config"
    ]
    assert initial["total_counts"]["candidate_pair_count"] == 0
    assert initial["conservation"]["all_counter_bounds_hold"] is True

    reference_result = run_episode(config, module_stack=reference_stack)
    candidate_result = run_episode(config, module_stack=candidate_stack)
    assert (
        reference_result.manifest.runtime_profile_sha256
        != candidate_result.manifest.runtime_profile_sha256
    )
    for result, expected_selector, expected_candidate in (
        (reference_result, "disabled_v1", False),
        (
            candidate_result,
            "modality_conservative_quadratic_bound_v1",
            True,
        ),
    ):
        governance = result.observation_governance_audit
        assert governance is not None
        assert governance[
            "d1_association_sparse_prefilter_implementation"
        ] == expected_selector
        diagnostics = governance[
            "d1_association_sparse_prefilter_diagnostics"
        ]
        assert diagnostics["candidate_enabled"] is expected_candidate
        assert diagnostics["total_counts"]["candidate_pair_count"] > 0
        assert diagnostics["conservation"]["all_counter_bounds_hold"] is True
        assert result.summary[
            "d1_association_sparse_prefilter_implementation"
        ] == expected_selector
        assert result.summary[
            "d1_association_sparse_prefilter_diagnostics"
        ] == diagnostics
        assert result.summary["module_final_diagnostics"][
            "d1_association_sparse_prefilter_diagnostics"
        ] == diagnostics

    with pytest.raises(
        ValueError,
        match="d1_association_sparse_prefilter_implementation must be",
    ):
        IntegratedStackConfig(
            d1_association_sparse_prefilter_implementation="heuristic"
        )


def test_episode_cli_exposes_d1_association_sparse_prefilter_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_association_sparse_prefilter_implementation
        == "disabled_v1"
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-association-sparse-prefilter-implementation",
            "modality_conservative_quadratic_bound_v1",
        ]
    )
    assert args.d1_association_sparse_prefilter_implementation == (
        "modality_conservative_quadratic_bound_v1"
    )


def test_d1_replay_prefix_summary_is_explicit_hashed_and_audited() -> None:
    config = ScenarioConfig(
        scenario_name="d1_replay_prefix_summary_selection",
        scenario_version="d1-replay-prefix-summary-selection-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=1,
        duration_s=1.4,
        seed=33,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_replay_prefix_summary_implementation
        == "per_checkpoint_prefix_rebuild_v1"
    )

    reference_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_replay_prefix_summary_implementation=(
                "per_checkpoint_prefix_rebuild_v1"
            )
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_replay_prefix_summary_implementation=(
                "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
            )
        )
    )
    reference_profile = reference_stack.runtime_manifest_profile_for_scenario(
        config
    )
    candidate_profile = candidate_stack.runtime_manifest_profile_for_scenario(
        config
    )
    assert reference_profile[
        "d1_replay_prefix_summary_implementation"
    ] == "per_checkpoint_prefix_rebuild_v1"
    assert candidate_profile[
        "d1_replay_prefix_summary_implementation"
    ] == "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
    assert reference_profile != candidate_profile
    initial = candidate_profile["d1_replay_prefix_summary_diagnostics"]
    assert initial["execution_config"] == candidate_profile[
        "d1_replay_prefix_summary_execution_config"
    ]
    assert initial["execution_config"]["candidate_enabled"] is True
    assert initial["pending_consistency_ledger_count"] == 0
    assert initial["conservation"]["attempt_partition"] is True

    reference_result = run_episode(config, module_stack=reference_stack)
    candidate_result = run_episode(config, module_stack=candidate_stack)
    assert (
        reference_result.manifest.runtime_profile_sha256
        != candidate_result.manifest.runtime_profile_sha256
    )
    for result, expected_selector, expected_candidate in (
        (
            reference_result,
            "per_checkpoint_prefix_rebuild_v1",
            False,
        ),
        (
            candidate_result,
            "fixed_lag_checkpoint_prefix_cumulative_summary_v1",
            True,
        ),
    ):
        governance = result.observation_governance_audit
        assert governance is not None
        assert governance[
            "d1_replay_prefix_summary_implementation"
        ] == expected_selector
        diagnostics = governance["d1_replay_prefix_summary_diagnostics"]
        assert diagnostics["execution_config"][
            "candidate_enabled"
        ] is expected_candidate
        assert diagnostics["pending_consistency_ledger_count"] == 0
        assert diagnostics["conservation"]["attempt_partition"] is True
        assert result.summary[
            "d1_replay_prefix_summary_implementation"
        ] == expected_selector
        assert result.summary[
            "d1_replay_prefix_summary_diagnostics"
        ] == diagnostics
        final_diagnostics = result.summary["module_final_diagnostics"][
            "d1_replay_prefix_summary_diagnostics"
        ]
        assert final_diagnostics["selector"] == expected_selector
        assert final_diagnostics["execution_config"][
            "candidate_enabled"
        ] is expected_candidate
        assert final_diagnostics["conservation"]["attempt_partition"] is True

    candidate_counts = candidate_result.summary[
        "d1_replay_prefix_summary_diagnostics"
    ]["operation_counts"]
    assert candidate_counts["summary_hit_count"] > 0
    assert candidate_counts["summary_reused_checkpoint_count"] > 0
    assert candidate_counts["public_snapshot_projection_count"] > 0
    assert (
        candidate_counts["lazy_consistency_refresh_logical_record_count"]
        >= candidate_counts["lazy_consistency_materialized_record_count"]
    )
    candidate_materialization_reasons = candidate_result.summary[
        "d1_replay_prefix_summary_diagnostics"
    ]["materialization_reasons"]
    assert (
        candidate_materialization_reasons.get(
            "checkpoint_suffix_appended",
            0,
        )
        == 0
    )

    with pytest.raises(
        ValueError,
        match="d1_replay_prefix_summary_implementation must be",
    ):
        IntegratedStackConfig(
            d1_replay_prefix_summary_implementation="unsafe"
        )


def test_episode_cli_exposes_d1_replay_prefix_summary_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_replay_prefix_summary_implementation
        == "per_checkpoint_prefix_rebuild_v1"
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-replay-prefix-summary-implementation",
            "fixed_lag_checkpoint_prefix_cumulative_summary_v1",
        ]
    )
    assert args.d1_replay_prefix_summary_implementation == (
        "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
    )


def test_d1_publication_evidence_snapshot_scope_is_explicit_and_exact() -> None:
    config = ScenarioConfig(
        scenario_name="d1_publication_evidence_snapshot_selection",
        scenario_version="d1-publication-evidence-snapshot-selection-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=1,
        duration_s=1.4,
        seed=34,
    )
    default = IntegratedStackConfig()
    assert (
        default.d1_publication_evidence_snapshot_implementation
        == D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION
    )
    reference_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publication_evidence_snapshot_implementation=(
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION
            )
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publication_evidence_snapshot_implementation=(
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION
            )
        )
    )
    reference_profile = reference_stack.runtime_manifest_profile_for_scenario(
        config
    )
    candidate_profile = candidate_stack.runtime_manifest_profile_for_scenario(
        config
    )
    assert reference_profile != candidate_profile
    for profile, selector, candidate_enabled in (
        (
            reference_profile,
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION,
            False,
        ),
        (
            candidate_profile,
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION,
            True,
        ),
    ):
        assert profile[
            "d1_publication_evidence_snapshot_implementation"
        ] == selector
        execution = profile[
            "d1_publication_evidence_snapshot_execution_config"
        ]
        assert execution["selector"] == selector
        assert execution["candidate_enabled"] is candidate_enabled
        assert execution["truth_dependent_inputs_allowed"] is False
        assert profile[
            "d1_publication_evidence_snapshot_diagnostics"
        ]["operation_counts"] == {}

    reference_result = run_episode(config, module_stack=reference_stack)
    candidate_result = run_episode(config, module_stack=candidate_stack)
    assert (
        reference_result.manifest.runtime_profile_sha256
        != candidate_result.manifest.runtime_profile_sha256
    )
    reference_publications = [
        message.payload
        for message in reference_result.online_messages
        if message.topic == "modules.d1.fused_tracks"
    ]
    candidate_publications = [
        message.payload
        for message in candidate_result.online_messages
        if message.topic == "modules.d1.fused_tracks"
    ]
    assert candidate_publications == reference_publications

    for result, selector, candidate_enabled in (
        (
            reference_result,
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION,
            False,
        ),
        (
            candidate_result,
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION,
            True,
        ),
    ):
        governance = result.observation_governance_audit
        assert governance is not None
        assert governance[
            "d1_publication_evidence_snapshot_implementation"
        ] == selector
        diagnostics = governance[
            "d1_publication_evidence_snapshot_diagnostics"
        ]
        assert diagnostics["execution_config"]["selector"] == selector
        assert diagnostics["execution_config"][
            "candidate_enabled"
        ] is candidate_enabled
        assert all(diagnostics["conservation"].values())
        assert result.summary[
            "d1_publication_evidence_snapshot_implementation"
        ] == selector
        assert result.summary[
            "d1_publication_evidence_snapshot_diagnostics"
        ] == diagnostics
        assert result.summary["module_final_diagnostics"][
            "d1_publication_evidence_snapshot_diagnostics"
        ] == diagnostics

    reference_counts = reference_result.summary[
        "d1_publication_evidence_snapshot_diagnostics"
    ]["operation_counts"]
    candidate_counts = candidate_result.summary[
        "d1_publication_evidence_snapshot_diagnostics"
    ]["operation_counts"]
    assert reference_counts["reference_selection_count"] > 0
    assert candidate_counts["candidate_subset_success_count"] > 0
    assert candidate_counts["candidate_fallback_count"] == 0
    assert candidate_counts["lookup_miss_count"] == 0
    assert candidate_counts["invalid_required_id_count"] == 0
    assert (
        candidate_counts["returned_record_count"]
        == candidate_counts["required_observation_id_count"]
    )
    assert (
        candidate_counts["returned_record_count"]
        < reference_counts["returned_record_count"]
    )

    with pytest.raises(
        ValueError,
        match="d1_publication_evidence_snapshot_implementation must be",
    ):
        IntegratedStackConfig(
            d1_publication_evidence_snapshot_implementation="unsafe"
        )


def test_d1_publication_evidence_snapshot_subset_falls_back_on_unknown_id() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publication_evidence_snapshot_implementation=(
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION
            )
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="d1_publication_evidence_unknown",
            scenario_version="d1-publication-evidence-unknown-v1",
            target_count=1,
            resource_count=1,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=35,
        )
    )
    result = SimpleNamespace(tracks_materialized=False, tracks=())
    batch = SimpleNamespace(
        observations=(
            SimpleNamespace(observation_id="unknown-observation"),
        )
    )
    evidence = stack._d1_publication_evidence_by_observation(
        ((result, batch, None, None, None),)
    )
    assert evidence == {}
    diagnostics = stack._d1_publication_evidence_snapshot_diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["candidate_selection_count"] == 1
    assert counts["candidate_fallback_count"] == 1
    assert counts["subset_snapshot_call_count"] == 1
    assert counts["full_snapshot_call_count"] == 1
    assert counts["adapter_snapshot_call_count"] == 2
    assert counts["lookup_miss_count"] == 1
    assert diagnostics["fallback_reason_counts"] == {
        "unknown_required_observation_id": 1
    }
    assert diagnostics["conservation"][
        "all_required_records_available"
    ] is False


def test_d1_publication_evidence_snapshot_subset_falls_back_on_empty_set() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_publication_evidence_snapshot_implementation=(
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION
            )
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="d1_publication_evidence_empty",
            scenario_version="d1-publication-evidence-empty-v1",
            target_count=1,
            resource_count=1,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=36,
        )
    )
    result = SimpleNamespace(tracks_materialized=False, tracks=())
    batch = SimpleNamespace(observations=())
    evidence = stack._d1_publication_evidence_by_observation(
        ((result, batch, None, None, None),)
    )
    assert evidence == {}
    diagnostics = stack._d1_publication_evidence_snapshot_diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["empty_required_id_selection_count"] == 1
    assert counts["candidate_fallback_count"] == 1
    assert counts["subset_snapshot_call_count"] == 0
    assert counts["full_snapshot_call_count"] == 1
    assert diagnostics["fallback_reason_counts"] == {
        "empty_required_observation_id_set": 1
    }


def test_d1_publication_evidence_required_ids_are_deduplicated() -> None:
    track = SimpleNamespace(
        metadata={"latest_observation_id": "obs-1"}
    )
    result = SimpleNamespace(tracks_materialized=True, tracks=(track,))
    batch = SimpleNamespace(
        observations=(
            SimpleNamespace(observation_id="obs-1"),
            SimpleNamespace(observation_id="obs-1"),
            SimpleNamespace(observation_id="obs-2"),
        )
    )
    required, source_count, track_count, invalid_count = (
        IntegratedScalableModuleStack
        ._required_d1_publication_evidence_ids(
            ((result, batch, None, None, None),)
        )
    )
    assert required == ("obs-1", "obs-2")
    assert source_count == 3
    assert track_count == 1
    assert invalid_count == 0


def test_episode_cli_exposes_d1_publication_evidence_snapshot_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_publication_evidence_snapshot_implementation
        == D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-publication-evidence-snapshot-implementation",
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION,
        ]
    )
    assert args.d1_publication_evidence_snapshot_implementation == (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION
    )


def test_d1_opaque_source_key_control_arm_is_explicit_and_hashed() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_publish_opaque_source_key=True)
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="d1_source_only_control_2v2",
            scenario_version="d1-source-only-control-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=19,
        )
    )

    assert stack.d1.radar_assignment_ambiguity_hold_evidence is False
    assert stack.d1.publish_opaque_source_key is True
    audit = stack.observation_governance_audit()
    assert audit["d1_publish_opaque_source_key"] is True
    assert audit["d1_d2_structural_ambiguity_hold_enabled"] is False
    assert audit["d1_fusion_association"][
        "opaque_source_key_publication_mode"
    ] == "source_only"
    assert stack.runtime_manifest_profile()["configuration"][
        "d1_publish_opaque_source_key"
    ] is True


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_d1_opaque_source_key_control_requires_bool(value: object) -> None:
    with pytest.raises(
        TypeError,
        match="d1_publish_opaque_source_key must be a bool",
    ):
        IntegratedStackConfig(
            d1_publish_opaque_source_key=value,  # type: ignore[arg-type]
        )


def test_d1_identity_neutral_centroid_candidate_is_explicit_and_hashed() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
            d1_identity_neutral_centroid_correction_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="d1_neutral_centroid_candidate_2v2",
            scenario_version="d1-neutral-centroid-candidate-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=23,
        )
    )

    assert (
        stack.d1.radar_assignment_ambiguity_neutral_centroid_correction
        is True
    )
    audit = stack.observation_governance_audit()
    assert audit["d1_d2_structural_ambiguity_hold_enabled"] is True
    assert (
        audit["d1_identity_neutral_centroid_correction_enabled"] is True
    )
    assert audit["d1_fusion_association"][
        "neutral_centroid_correction_status"
    ] == "experimental_identity_neutral_centroid_candidate_not_promoted"
    assert stack.runtime_manifest_profile()["configuration"][
        "d1_identity_neutral_centroid_correction_enabled"
    ] is True


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_d1_identity_neutral_centroid_candidate_requires_bool(
    value: object,
) -> None:
    with pytest.raises(
        TypeError,
        match=(
            "d1_identity_neutral_centroid_correction_enabled must be a bool"
        ),
    ):
        IntegratedStackConfig(
            d1_identity_neutral_centroid_correction_enabled=value,  # type: ignore[arg-type]
        )


def test_d1_identity_neutral_centroid_candidate_requires_hold() -> None:
    with pytest.raises(
        ValueError,
        match="centroid correction requires",
    ):
        IntegratedStackConfig(
            d1_identity_neutral_centroid_correction_enabled=True
        )


def test_d1_centroid_overlay_shadow_is_explicit_hashed_and_fail_closed() -> None:
    default = IntegratedStackConfig()
    assert default.d1_centroid_publication_overlay_shadow_enabled is False
    assert IntegratedScalableModuleStack(
        default
    ).runtime_manifest_profile()["configuration"][
        "d1_centroid_publication_overlay_shadow_enabled"
    ] is False

    with pytest.raises(
        ValueError,
        match="overlay shadow requires",
    ):
        IntegratedStackConfig(
            d1_centroid_publication_overlay_shadow_enabled=True
        )
    with pytest.raises(
        ValueError,
        match="cannot be combined",
    ):
        IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
            d1_identity_neutral_centroid_correction_enabled=True,
            d1_centroid_publication_overlay_shadow_enabled=True,
        )


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_d1_centroid_overlay_shadow_requires_bool(value: object) -> None:
    with pytest.raises(
        TypeError,
        match="d1_centroid_publication_overlay_shadow_enabled must be a bool",
    ):
        IntegratedStackConfig(
            d1_centroid_publication_overlay_shadow_enabled=value,  # type: ignore[arg-type]
        )


def test_d1_radar_assignment_ambiguity_governance_v2_is_explicit_and_audited() -> None:
    default = IntegratedScalableModuleStack()
    default.reset(
        ScenarioConfig(
            scenario_name="d1_ambiguity_default",
            scenario_version="d1-ambiguity-default-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=13,
        )
    )
    default_audit = default.observation_governance_audit()
    assert (
        default_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_enabled"
        ]
        is False
    )
    assert (
        default_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_status"
        ]
        == "disabled"
    )
    assert (
        default_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_selected_policy_version"
        ]
        is None
    )

    experimental = IntegratedScalableModuleStack(
        config=IntegratedStackConfig(
            d1_radar_assignment_ambiguity_governance_v2=True
        )
    )
    experimental.reset(
        ScenarioConfig(
            scenario_name="d1_ambiguity_experimental",
            scenario_version="d1-ambiguity-experimental-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=13,
        )
    )
    experimental_audit = experimental.observation_governance_audit()
    assert (
        experimental_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_enabled"
        ]
        is True
    )
    assert (
        experimental_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_status"
        ]
        == "experimental_v2_enabled_rejected_candidate"
    )
    assert (
        experimental_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_selected_policy_version"
        ]
        == "fail_closed_maximum_matching_allowed_edge_component_v2"
    )


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_d1_radar_assignment_ambiguity_governance_v2_requires_bool(
    value: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="d1_radar_assignment_ambiguity_governance_v2 must be a bool",
    ):
        IntegratedStackConfig(
            d1_radar_assignment_ambiguity_governance_v2=value,  # type: ignore[arg-type]
        )


def _d1_track_stub(
    local_track_id: str,
    timestamp: float,
    position_ned: tuple[float, float, float],
) -> SimpleNamespace:
    observation_id = f"OBS-{local_track_id}-{timestamp:.3f}"
    state = np.array([*position_ned, 0.0, 0.0, 0.0], dtype=float)
    return SimpleNamespace(
        global_track_id=local_track_id,
        state=state,
        covariance=np.eye(6, dtype=float) * 4.0,
        timestamp=float(timestamp),
        metadata={
            "frame_id": "ned",
            "measurement_timestamp": float(timestamp),
            "arrival_timestamp": float(timestamp),
            "published_at": float(timestamp),
            "confidence": 1.0,
            "latest_observation_id": observation_id,
            "latest_measurement_timestamp": float(timestamp),
            "latest_sensor_id": "RADAR-TEST",
        },
    )


def _seed_d1_lineage_for_tracks(
    stack: IntegratedScalableModuleStack,
    tracks: tuple[SimpleNamespace, ...],
) -> None:
    for track in tracks:
        observation_id = str(track.metadata["latest_observation_id"])
        record = {
            "observation_id": observation_id,
            "measurement_timestamp": float(
                track.metadata["latest_measurement_timestamp"]
            ),
            "source_lineage": [
                "opaque_online_lineage",
                "sensor:RADAR-TEST",
                observation_id,
            ],
            "replay_generation": 0,
        }
        stack._d1_latest_lineage_by_observation[observation_id] = dict(
            record
        )
        stack._d1_pending_lineage_by_track.setdefault(
            str(track.global_track_id),
            {},
        )[observation_id] = dict(record)


def _structural_ambiguity_fixture(
    *,
    publisher_epoch: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> StructuralAmbiguityEvidence:
    local_ids = ("D1-LOCAL-A", "D1-LOCAL-B")
    positions = (
        np.array([100.0, -20.0, -10.0]),
        np.array([100.0, 20.0, -10.0]),
    )
    tokens = tuple(
        structural_ambiguity_member_track_token(
            DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
            publisher_epoch,
            local_id,
        )
        for local_id in local_ids
    )
    members = tuple(
        StructuralAmbiguityMemberState(
            opaque_member_track_token=token,
            source_key=structural_ambiguity_source_key(
                DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
                publisher_epoch,
                token,
            ),
            state=np.concatenate((position, np.zeros(3, dtype=float))),
            covariance=np.eye(6, dtype=float) * 4.0,
        )
        for token, position in zip(tokens, positions, strict=True)
    )
    observation_keys = (
        f"d1-observation-sha256:{1:064x}",
        f"d1-observation-sha256:{2:064x}",
    )
    observations = tuple(
        StructuralAmbiguityObservationEvidence(
            observation_evidence_key=key,
            position_ned=position,
            covariance_ned=np.eye(3, dtype=float) * 4.0,
            radial_velocity_observed=False,
            birth_deferred=False,
        )
        for key, position in zip(observation_keys, positions, strict=True)
    )
    edges = tuple(
        StructuralAmbiguityCandidateEdge(
            opaque_member_track_token=token,
            observation_evidence_key=observation_key,
            nis=1.0 if member_index == observation_index else 2.0,
            gate_threshold=40.0,
            edge_roles=(
                ("matched_reference", "maximum_matching_allowed")
                if member_index == observation_index
                else ("alternating_cycle", "maximum_matching_allowed")
            ),
        )
        for member_index, token in enumerate(tokens)
        for observation_index, observation_key in enumerate(observation_keys)
    )
    return StructuralAmbiguityEvidence(
        evidence_id=f"d1-evidence-sha256:{3:064x}",
        component_id=f"d1-component-sha256:{4:064x}",
        component_generation=1,
        publisher_node_id=DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
        publisher_epoch=publisher_epoch,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        state_valid_timestamp=measurement_timestamp,
        published_at=arrival_timestamp,
        sensor_id="radar-main",
        scan_id=f"d1-scan-sha256:{5:064x}",
        member_states=members,
        observations=observations,
        candidate_edges=edges,
        component_kinds=("alternating_cycle",),
        member_count=2,
        observation_count=2,
        candidate_edge_count=4,
        free_row_count=0,
        free_column_count=0,
        maximum_matching_cardinality=2,
    )


def _centroid_shadow_tracks(
    evidence: StructuralAmbiguityEvidence,
) -> tuple[GlobalTrack, ...]:
    return tuple(
        GlobalTrack(
            global_track_id=f"CENTER-GT-{index:03d}",
            state=member.state.copy(),
            covariance=member.covariance.copy(),
            timestamp=evidence.published_at,
            track_level=TrackLevel.STABLE,
            source_support={"radar": 2},
            identity_likelihood={"unknown": 1.0},
            metadata={
                "frame_id": "ned",
                "measurement_timestamp": evidence.measurement_timestamp,
                "arrival_timestamp": evidence.arrival_timestamp,
                "published_at": evidence.published_at,
                "source_key": member.source_key,
                "opaque_member_track_token": (
                    member.opaque_member_track_token
                ),
            },
        )
        for index, member in enumerate(evidence.member_states)
    )


def test_d1_centroid_overlay_shadow_is_audit_only_and_bounded() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
            d1_centroid_publication_overlay_shadow_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="main_d1_centroid_overlay_shadow_2v2",
            scenario_version="main-d1-centroid-overlay-shadow-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=41,
        )
    )
    evidence = _structural_ambiguity_fixture(
        publisher_epoch=stack._d1_publisher_epoch,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    tracks = _centroid_shadow_tracks(evidence)
    stack.latest_d1_tracks = tracks
    before = json.dumps(
        [track.to_dict() for track in tracks],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    accepted = stack._d1_centroid_overlay_shadow_publication(
        canonical_tracks=tracks,
        evidence_items=(evidence,),
        disposition=ExperimentalCentroidEvidenceDisposition(),
        publication_timestamp=0.65,
        posterior_generation=1,
    )
    payload = accepted.payload
    assert accepted.topic == "audit.d1.centroid_publication_overlay_shadow"
    assert accepted.source == "main"
    assert payload["status"] == "offline_shadow_not_consumed"
    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 0
    assert payload["shadow_differs_from_canonical"] is True
    assert payload["measurement_timestamps"] == [0.4]
    assert payload["arrival_timestamps"] == [0.65]
    assert (
        payload["overlay_execution_mode"]
        == "atomic_experimental_offline_v1"
    )
    preparation = payload["canonical_preparation"]
    prepared_publication = preparation["prepared_publication"]
    assert prepared_publication["prototype_status"] == (
        "experimental_design_prototype_not_online_schema"
    )
    assert prepared_publication["usage_scope"] == (
        "experimental_offline_atomic_only"
    )
    assert prepared_publication["validation_error"] is None
    assert prepared_publication["track_count"] == 2
    assert prepared_publication["work"] == {
        "full_description_pass_count": 1,
        "track_count": 2,
        "validated_track_count": 2,
        "full_track_digest_count": 2,
        "state_digest_count": 2,
        "covariance_digest_count": 2,
        "publication_digest_count": 1,
    }
    assert preparation["canonical_publication_digest"] == (
        prepared_publication["base_publication_digest"]
    )
    assert preparation["post_integrity_check"] == {
        "matches": True,
        "mismatch_reason": None,
        "object_binding_pass_count": 1,
        "full_content_digest_pass_count": 1,
        "track_digest_count": 2,
    }
    assert preparation["work"] == {
        "canonical_full_description_pass_count": 1,
        "canonical_description_track_digest_count": 2,
        "canonical_post_integrity_pass_count": 1,
        "canonical_post_integrity_track_digest_count": 2,
        "shadow_track_copy_count": 2,
        "shadow_full_track_digest_count": 2,
        "shadow_publication_digest_count": 1,
    }
    assert preparation["atomic_failure_reason"] is None
    assert preparation["shadow_materialized"] is True
    assert isinstance(preparation["shadow_publication_digest"], str)
    assert preparation["shadow_publication_digest"].startswith("sha256:")
    assert len(preparation["shadow_publication_digest"]) == 71
    assert set(payload["phase_wall_time_ms"]) == {
        "atomic_overlay_operation",
        "audit_log_materialization",
        "forbidden_surface_after_digest",
        "forbidden_surface_before_digest",
        "shadow_payload_digest",
    }
    assert all(
        value >= 0.0 for value in payload["phase_wall_time_ms"].values()
    )
    assert payload["forbidden_mutation_audit"]["passed"] is True
    assert payload["forbidden_mutation_audit"]["d2_consumption_count"] == 0
    assert payload["forbidden_mutation_audit"]["d3_consumption_count"] == 0
    assert payload["bounded_memory_audit"][
        "generation_watermark_count"
    ] == 1
    assert payload["global_track_id_sequence_unchanged"] is True
    assert payload["canonical_global_track_ids_sha256"] == (
        payload["shadow_global_track_ids_sha256"]
    )
    assert "canonical_tracks" not in payload
    assert "shadow_tracks" not in payload
    assert json.dumps(
        [track.to_dict() for track in tracks],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == before
    assert stack.latest_d1_tracks is tracks
    assert stack.latest_d2_tracks == ()
    assert stack.latest_plan is None

    duplicate = stack._d1_centroid_overlay_shadow_publication(
        canonical_tracks=tracks,
        evidence_items=(evidence,),
        disposition=ExperimentalCentroidEvidenceDisposition(),
        publication_timestamp=0.65,
        posterior_generation=2,
    )
    duplicate_payload = duplicate.payload
    assert duplicate_payload["accepted_count"] == 0
    assert duplicate_payload["rejected_count"] == 1
    assert duplicate_payload["rejection_reason_counts"] == {
        "duplicate_evidence_generation": 1
    }
    duplicate_preparation = duplicate_payload["canonical_preparation"]
    assert duplicate_preparation["shadow_materialized"] is False
    assert duplicate_preparation["shadow_publication_digest"] is None
    assert duplicate_preparation["atomic_failure_reason"] is None
    assert duplicate_preparation["work"]["shadow_track_copy_count"] == 0
    assert duplicate_payload["shadow_tracks_sha256"] == (
        duplicate_payload["canonical_tracks_sha256"]
    )
    audit = stack.observation_governance_audit()
    assert audit["d1_centroid_overlay_shadow_evaluation_count"] == 2
    assert audit["d1_centroid_overlay_shadow_accepted_count"] == 1
    assert audit["d1_centroid_overlay_shadow_rejected_count"] == 1
    assert audit["d1_centroid_overlay_shadow_forbidden_mutation_count"] == 0
    assert audit["d1_centroid_overlay_shadow_d2_consumption_count"] == 0
    assert audit["d1_centroid_overlay_shadow_d3_consumption_count"] == 0
    assert audit["d1_centroid_overlay_shadow_max_watermark_count"] == 1
    assert audit["d1_centroid_overlay_shadow_max_payload_bytes"] > 0
    diagnostics = stack._diagnostics(
        0.65,
        include_timing_distribution=True,
    )
    stage_timings = diagnostics["stage_timings"]
    for phase_name in payload["phase_wall_time_ms"]:
        assert (
            "d1_centroid_publication_overlay_shadow."
            f"{phase_name}"
        ) in stage_timings


def test_d1_centroid_overlay_shadow_hook_publishes_only_after_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
            d1_centroid_publication_overlay_shadow_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="main_d1_centroid_overlay_hook_2v2",
            scenario_version="main-d1-centroid-overlay-hook-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=43,
        )
    )
    evidence = _structural_ambiguity_fixture(
        publisher_epoch=stack._d1_publisher_epoch,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    tracks = _centroid_shadow_tracks(evidence)
    result = SimpleNamespace(
        tracks=tracks,
        tracks_materialized=True,
        current_track_count=len(tracks),
        structural_ambiguity_evidence=(evidence,),
        summary=SimpleNamespace(
            to_dict=lambda: {
                "schema_version": "test-d1-summary-v1",
                "published_at": 0.65,
            }
        ),
    )
    observation = SensorObservation(
        observation_id="OBS-SHADOW-HOOK-001",
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
        frame_id="ned",
        measurement=np.array([100.0, -20.0, -10.0]),
        covariance=np.eye(3),
    )
    released_scan = SimpleNamespace(
        observations=(observation,),
        arrival_timestamp=0.65,
        sensor_id="radar-main",
        scan_id="SCAN-SHADOW-HOOK-001",
    )
    monkeypatch.setattr(
        stack.d1,
        "process_scan_batch",
        lambda observations, *, materialize_tracks: result,
    )
    publications = []

    assert stack._consume_d1_released_scans(
        (released_scan,),
        publications=publications,
        publication_timestamp=0.65,
    )

    assert [item.topic for item in publications] == [
        "modules.d1.fused_tracks",
        "audit.d1.centroid_publication_overlay_shadow",
    ]
    shadow_payload = publications[-1].payload
    assert shadow_payload["accepted_count"] == 1
    assert shadow_payload["evidence_count"] == 1
    assert stack.latest_d1_tracks is tracks
    assert stack.latest_d2_tracks == ()
    assert stack.latest_plan is None
    assert stack._d1_centroid_overlay_shadow_evaluation_count == 1


def test_d1_centroid_overlay_shadow_frozen_evidence_regression() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
            d1_centroid_publication_overlay_shadow_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="main_d1_centroid_overlay_frozen_2v2",
            scenario_version="main-d1-centroid-overlay-frozen-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=47,
        )
    )
    base_evidence = _structural_ambiguity_fixture(
        publisher_epoch=stack._d1_publisher_epoch,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    tracks = _centroid_shadow_tracks(base_evidence)
    stack.latest_d1_tracks = tracks
    canonical_bytes = json.dumps(
        [track.to_dict() for track in tracks],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    d1_audit_before = json.dumps(
        stack.d1.association_audit_summary(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    d1_time_before = float(stack.d1.current_time)
    d1_generation_before = int(stack._d1_posterior_generation)

    def generation(
        value: int,
        *,
        evidence: StructuralAmbiguityEvidence = base_evidence,
    ) -> StructuralAmbiguityEvidence:
        return replace(
            evidence,
            evidence_id=f"d1-evidence-sha256:{100 + value:064x}",
            component_generation=value,
        )

    accepted = stack._d1_centroid_overlay_shadow_publication(
        canonical_tracks=tracks,
        evidence_items=(generation(1),),
        disposition=ExperimentalCentroidEvidenceDisposition(),
        publication_timestamp=0.65,
        posterior_generation=1,
    ).payload
    assert accepted["accepted_count"] == 1
    assert accepted["rejected_count"] == 0
    assert accepted["shadow_differs_from_canonical"] is True

    oosm_evidence = generation(2)
    oosm = stack._d1_centroid_overlay_shadow_publication(
        canonical_tracks=tracks,
        evidence_items=(oosm_evidence,),
        disposition=ExperimentalCentroidEvidenceDisposition(
            oosm_evidence_ids=frozenset({oosm_evidence.evidence_id})
        ),
        publication_timestamp=0.65,
        posterior_generation=2,
    ).payload
    assert oosm["accepted_count"] == 0
    assert oosm["rejection_reason_counts"] == {"oosm_scan": 1}
    assert oosm["shadow_tracks_sha256"] == oosm["canonical_tracks_sha256"]

    retained_observation_keys = {
        base_evidence.observations[0].observation_evidence_key
    }
    unbalanced_edges = tuple(
        edge
        for edge in base_evidence.candidate_edges
        if edge.observation_evidence_key in retained_observation_keys
    )
    unbalanced_evidence = generation(
        3,
        evidence=replace(
            base_evidence,
            observations=base_evidence.observations[:1],
            candidate_edges=unbalanced_edges,
            observation_count=1,
            candidate_edge_count=len(unbalanced_edges),
            free_row_count=1,
            free_column_count=0,
            maximum_matching_cardinality=1,
        ),
    )
    unbalanced = stack._d1_centroid_overlay_shadow_publication(
        canonical_tracks=tracks,
        evidence_items=(unbalanced_evidence,),
        disposition=ExperimentalCentroidEvidenceDisposition(),
        publication_timestamp=0.65,
        posterior_generation=3,
    ).payload
    assert unbalanced["accepted_count"] == 0
    assert unbalanced["rejection_reason_counts"] == {
        "unbalanced_component": 1
    }
    assert unbalanced["shadow_tracks_sha256"] == (
        unbalanced["canonical_tracks_sha256"]
    )

    timing_ms = []
    for value in range(4, 36):
        payload = stack._d1_centroid_overlay_shadow_publication(
            canonical_tracks=tracks,
            evidence_items=(generation(value),),
            disposition=ExperimentalCentroidEvidenceDisposition(),
            publication_timestamp=0.65,
            posterior_generation=value,
        ).payload
        timing_ms.append(float(payload["evaluation_wall_time_ms"]))
        assert payload["accepted_count"] == 1
        assert payload["forbidden_mutation_audit"]["passed"] is True
        assert payload["global_track_id_sequence_unchanged"] is True

    audit = stack.observation_governance_audit()
    assert audit["d1_centroid_overlay_shadow_evaluation_count"] == 35
    assert audit["d1_centroid_overlay_shadow_accepted_count"] == 33
    assert audit["d1_centroid_overlay_shadow_rejected_count"] == 2
    assert audit["d1_centroid_overlay_shadow_rejection_reason_counts"] == {
        "oosm_scan": 1,
        "unbalanced_component": 1,
    }
    assert audit["d1_centroid_overlay_shadow_forbidden_mutation_count"] == 0
    assert audit["d1_centroid_overlay_shadow_max_watermark_count"] == 1
    assert audit["d1_centroid_overlay_shadow_watermark_count"] == 1
    assert (
        audit["d1_centroid_overlay_shadow_watermark_count"]
        <= audit["d1_centroid_overlay_shadow_watermark_capacity"]
    )
    assert np.isfinite(timing_ms).all()
    assert float(np.percentile(timing_ms, 95.0)) < 20.0

    assert stack.latest_d1_tracks is tracks
    assert stack.latest_d2_tracks == ()
    assert stack.latest_plan is None
    assert float(stack.d1.current_time) == d1_time_before
    assert int(stack._d1_posterior_generation) == d1_generation_before
    assert json.dumps(
        stack.d1.association_audit_summary(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == d1_audit_before
    assert json.dumps(
        [track.to_dict() for track in tracks],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == canonical_bytes


def test_d1_centroid_overlay_shadow_hashes_nested_read_only_metadata() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
            d1_centroid_publication_overlay_shadow_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="main_d1_centroid_overlay_mapping_proxy_2v2",
            scenario_version="main-d1-centroid-overlay-mapping-proxy-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=53,
        )
    )
    evidence = _structural_ambiguity_fixture(
        publisher_epoch=stack._d1_publisher_epoch,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    tracks = list(_centroid_shadow_tracks(evidence))
    tracks[0].metadata["runtime_read_only"] = MappingProxyType(
        {
            "nested": MappingProxyType({"value": np.float64(1.25)}),
            "modes": frozenset({"hold", "shadow"}),
        }
    )
    frozen_tracks = tuple(tracks)

    publication = stack._d1_centroid_overlay_shadow_publication(
        canonical_tracks=frozen_tracks,
        evidence_items=(evidence,),
        disposition=ExperimentalCentroidEvidenceDisposition(
            oosm_evidence_ids=frozenset({evidence.evidence_id})
        ),
        publication_timestamp=0.65,
        posterior_generation=1,
    )

    assert publication.payload["evaluation_error"] is None
    assert publication.payload["accepted_count"] == 0
    assert publication.payload["rejection_reason_counts"] == {
        "oosm_scan": 1
    }
    assert publication.payload["forbidden_mutation_audit"]["passed"] is True
    assert publication.payload["shadow_tracks_sha256"] == (
        publication.payload["canonical_tracks_sha256"]
    )


def test_atomic_d1_d2_ambiguity_hold_consumes_delayed_sidecar_once() -> None:
    stack = IntegratedScalableModuleStack(
        config=IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="main_ambiguity_hold_bridge_2v2",
            scenario_version="main-ambiguity-hold-bridge-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=1.0,
            radar_period_s=0.2,
            association_period_s=0.2,
            seed=31,
        )
    )
    assert (
        stack.d2.ambiguity_hold_config.max_component_age_seconds
        == pytest.approx(5.4)
    )
    assert (
        stack.d2.identity_commitment_recovery_config.config_version
        == "main-scalable3d-identity-recovery-publication-freshness-v1"
    )
    assert (
        stack.d2.identity_commitment_recovery_config
        .max_recovery_evidence_age_seconds
        == pytest.approx(
            stack.config.identity_lineage_freshness_budget_s
        )
    )
    publications = []
    positions = (
        (100.0, -20.0, -10.0),
        (100.0, 20.0, -10.0),
    )
    for generation, timestamp in enumerate((0.0, 0.2), start=1):
        tracks = tuple(
            _d1_track_stub(local_id, timestamp, position)
            for local_id, position in zip(
                ("D1-LOCAL-A", "D1-LOCAL-B"),
                positions,
                strict=True,
            )
        )
        stack.latest_d1_tracks = tracks
        _seed_d1_lineage_for_tracks(stack, tracks)
        if generation == 2:
            for track in tracks:
                stale_id = f"OBS-STALE-{track.global_track_id}"
                stack._d1_pending_lineage_by_track[
                    str(track.global_track_id)
                ][stale_id] = {
                    "observation_id": stale_id,
                    "measurement_timestamp": 0.1,
                    "source_lineage": [stale_id],
                    "replay_generation": 0,
                }
        stack._d1_posterior_generation = generation
        assert stack._associate_latest_d1_tracks(
            publications,
            publication_timestamp=timestamp,
            timing_stage="test_d2_seed",
            source_d1_posterior_generation=generation,
        )

    committed_lineage = publications[-1].payload["identity_lineage"]
    assert all(
        {
            item["measurement_timestamp"]
            for item in track_item["source_observations"]
        }
        == {0.1, 0.2}
        for track_item in committed_lineage
    )
    before = {
        track.global_track_id: (
            track.hits,
            track.misses,
            float(np.trace(track.covariance)),
        )
        for track in stack.d2.active_tracks()
    }
    committed_track_ids = tuple(sorted(before))
    stack.latest_plan = SimpleNamespace(
        plan_id="PLAN-COMMITTED-1",
        version=1,
        assignments=tuple(
            SimpleNamespace(
                target_id=track_id,
                resource_id=f"INT-{index:02d}",
                coalition_version=0,
            )
            for index, track_id in enumerate(committed_track_ids, start=1)
        ),
    )
    stack.latest_bindings = tuple(
        SimpleNamespace(
            resource_id=f"INT-{index:02d}",
            assigned_global_track_id=track_id,
        )
        for index, track_id in enumerate(committed_track_ids, start=1)
    )
    evidence = _structural_ambiguity_fixture(
        publisher_epoch=stack._d1_publisher_epoch,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    stack._latch_structural_ambiguity_evidence(
        SimpleNamespace(structural_ambiguity_evidence=(evidence,))
    )
    tracks = tuple(
        _d1_track_stub(local_id, 0.65, position)
        for local_id, position in zip(
            ("D1-LOCAL-A", "D1-LOCAL-B"),
            positions,
            strict=True,
        )
    )
    stack.latest_d1_tracks = tracks
    _seed_d1_lineage_for_tracks(stack, tracks)
    stack._d1_posterior_generation = 3

    assert stack._associate_latest_d1_tracks(
        publications,
        publication_timestamp=0.65,
        timing_stage="test_d2_hold",
        source_d1_posterior_generation=3,
    )

    hold = stack.latest_d2_result.metadata["ambiguity_hold"]
    assert hold["accepted_component_count"] == 1
    assert hold["active_component_count"] == 1
    assert len(hold["hold_track_ids"]) == 2
    assert stack._pending_structural_ambiguity_evidence == {}
    assert stack._structural_ambiguity_evidence_received_count == 1
    assert stack._structural_ambiguity_evidence_consumed_count == 1
    assert stack._structural_ambiguity_d2_consumption_count == 1
    lineage = stack._d2_identity_lineage_payload(
        stack.latest_d2_result
    )
    assert lineage
    assert {
        item["identity_commitment"]["identity_commitment_state"]
        for item in lineage
    } == {"identity_uncommitted_ambiguity_hold"}
    assert all(item["source_observations"] == [] for item in lineage)
    assert stack.latest_bindings == ()
    assert stack._identity_commitment_binding_hold_count == 2
    assert stack._identity_commitment_binding_hold_event_count == 1
    assert stack._identity_commitment_replan_required is True
    assert set(stack._identity_commitment_binding_hold_target_ids) == set(
        committed_track_ids
    )
    assert stack._committed_d2_target_ids() == frozenset()
    d3_tracks = stack._d3_tracks()
    assert {
        item.identity_commitment_state for item in d3_tracks
    } == {"identity_uncommitted_ambiguity_hold"}
    assert stack._run_active_vision(
        SimpleNamespace(cameras=()),
        now=0.65,
    ) == ()
    assert stack.latest_active_vision_snapshot.plan.assignments == ()
    assert stack._guidance_inputs(
        SimpleNamespace(),
        now=0.65,
    ) == ()
    for track in stack.d2.active_tracks():
        previous_hits, previous_misses, previous_trace = before[
            track.global_track_id
        ]
        assert track.hits == previous_hits
        assert track.misses == previous_misses
        assert float(np.trace(track.covariance)) >= previous_trace


def test_atomic_ambiguity_treatment_rejects_partial_or_invalid_config() -> None:
    with pytest.raises(
        ValueError,
        match="cannot both be enabled",
    ):
        IntegratedStackConfig(
            d1_radar_assignment_ambiguity_governance_v2=True,
            d1_d2_structural_ambiguity_hold_enabled=True,
        )
    with pytest.raises(
        ValueError,
        match="hard hold cannot be shorter",
    ):
        IntegratedStackConfig(
            d2_ambiguity_hold_gap_scan_periods=5,
            d2_ambiguity_hold_hard_scan_periods=2,
        )


def test_d2_consumes_pending_d1_posterior_at_next_association_tick() -> None:
    config = ScenarioConfig(
        scenario_name="pending_d1_to_d2_schedule_3v3",
        scenario_version="pending-d1-to-d2-schedule-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )

    result = run_episode(config, module_stack=IntegratedScalableModuleStack())

    scheduled_d2 = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
        and abs(message.timestamp - 1.0) <= 1.0e-9
    )
    assert len(scheduled_d2) == 1
    d2_publications = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
    )
    consumed_generations = tuple(
        int(message.payload["source_d1_posterior_generation"])
        for message in d2_publications
    )
    assert consumed_generations == tuple(sorted(set(consumed_generations)))
    assert not any(
        abs(message.timestamp - 1.05) <= 1.0e-9
        for message in d2_publications
    )
    assert min(
        float(track["timestamp"])
        for track in scheduled_d2[0].payload["tracks"]
    ) > 0.4

    scheduled_guidance = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and abs(message.timestamp - 1.0) <= 1.0e-9
    )
    assert all(
        command["gate_reason"] != "global_track_stale"
        for command in scheduled_guidance.payload["commands"]
    )
    full_d1_publications = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d1.fused_tracks"
        and message.payload["tracks_materialized"]
    )
    d1_generations = tuple(
        int(message.payload["posterior_generation"])
        for message in full_d1_publications
    )
    assert d1_generations == tuple(range(1, len(d1_generations) + 1))
    assert set(consumed_generations).issubset(set(d1_generations))

    governance = result.observation_governance_audit
    assert governance["schema_version"] == (
        "scalable3d-observation-governance-runtime-v2"
    )
    assert governance["d1_posterior_generation"] == d1_generations[-1]
    assert governance["d2_consumed_d1_posterior_generation"] == (
        consumed_generations[-1]
    )
    assert governance["d2_posterior_consumption_count"] == len(
        d2_publications
    )
    assert governance["d2_pending_d1_posterior_generation"] is None
    assert governance["d2_pre_tick_posterior_merge_count"] >= 1


def test_finalize_consumes_pending_d1_posterior_without_emitting_control() -> None:
    config = ScenarioConfig(
        scenario_name="pending_d1_finalize_3v3",
        scenario_version="pending-d1-finalize-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=0.95,
        seed=7,
        radar_detection_probability=1.0,
    )

    result = run_episode(config, module_stack=IntegratedScalableModuleStack())

    final_d2 = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
        and abs(message.timestamp - config.duration_s) <= 1.0e-9
    )
    assert len(final_d2) == 1
    final_generation = int(
        final_d2[0].payload["source_d1_posterior_generation"]
    )
    full_d1_generations = tuple(
        int(message.payload["posterior_generation"])
        for message in result.online_messages
        if message.topic == "modules.d1.fused_tracks"
        and message.payload["tracks_materialized"]
    )
    assert final_generation == full_d1_generations[-1]
    assert not any(
        message.topic in {
            "modules.d5.active_vision",
            "modules.d7.guidance_commands",
        }
        and abs(message.timestamp - config.duration_s) <= 1.0e-9
        for message in result.online_messages
    )
    governance = result.observation_governance_audit
    assert governance["d2_pending_d1_posterior_generation"] is None
    assert governance["d2_consumed_d1_posterior_generation"] == (
        governance["d1_posterior_generation"]
    )


@pytest.mark.parametrize(
    ("scale", "seed"),
    (
        (5, 1000),
        (5, 1005),
        (5, 1008),
        (5, 1018),
        (20, 1009),
    ),
)
def test_formal_r0_delayed_noisy_final_posterior_is_consumed_once(
    scale: int,
    seed: int,
) -> None:
    config = make_curriculum_scenario(
        "delayed_noisy",
        scale=scale,
        seed=seed,
        duration_s=2.0,
        base=ScenarioConfig(),
    )
    config = replace(
        config,
        sensor_random_schedule_version="entity_fixed_v1",
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    governance = result.observation_governance_audit
    d2_publications = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
    )
    assert governance["d2_consumed_d1_posterior_generation"] == (
        governance["d1_posterior_generation"]
    )
    assert governance["d2_pending_d1_posterior_generation"] is None
    assert governance["d2_posterior_consumption_count"] == len(
        d2_publications
    )
    assert governance["d2_finalize_unchanged_posterior_skip_count"] == 0
    assert int(
        d2_publications[-1].payload["source_d1_posterior_generation"]
    ) == governance["d1_posterior_generation"]
    assert result.summary["online_truth_use_count"] == 0

    final_metadata = stack.latest_d2_result.metadata
    assert final_metadata["fresh_detection_count"] == 0
    assert final_metadata["replay_quarantined_detection_count"] > 0
    assert final_metadata["replay_coast_count"] > 0
    assert final_metadata["created_track_ids_by_detection"] == {}
    assert final_metadata["duplicate_coalescence_count"] == 0
    assert final_metadata["global_track_id_owner"] == "D2_center"


def test_a3_runtime_bridge_keeps_delayed_anonymous_observation_window() -> None:
    policy = _AdmittedActiveVisionPolicyFixture()
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d5_active_vision_mode="assist",
            capture_learning_artifacts=True,
        ),
        d5_active_vision_policy=policy,
        learning_runtime_diagnostics={
            "d5_active_vision": {
                "bundle_loaded": True,
                "assist_admitted": True,
                "effective_mode": "assist",
                "model_fingerprint": policy.model_fingerprint,
                "bundle_manifest_sha256": (
                    policy.bundle_manifest_sha256
                ),
                "bundle_weights_sha256": policy.bundle_weights_sha256,
            }
        },
    )
    config = ScenarioConfig(
        scenario_name="a3_delayed_anonymous_window",
        scenario_version="a3-delayed-anonymous-window-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=3.5,
        seed=9,
        world_half_extent_m=500.0,
        protected_radius_m=100.0,
        target_proxy_width_m=10.0,
        target_proxy_height_m=4.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
    )

    result = run_episode(config, module_stack=stack)

    records = stack.learning_adoption_evidence_records()["a3"]
    stage_records = stack.active_vision_a3_candidate_stage_records()
    candidate_records = tuple(
        item for item in records if item["candidate_physical_window_available"]
    )
    assert candidate_records
    assert len(stage_records) == len(records)
    assert {
        item["comparison_key"] for item in stage_records
    } == {
        item["adoption_trace"]["comparison_key"] for item in records
    }
    assert all(
        item["evidence_kind"] == "runtime_observed"
        and item["runtime_event_inventory_complete"] is True
        and item["runtime_ack_applied"] is True
        and item["camera_feedback_timestamp"] is not None
        for item in stage_records
    )
    assert all(item["model_action_adopted"] for item in records)
    assert all(
        item["blocker_codes"] == ["same_key_r0_window_missing"]
        for item in candidate_records
    )
    assert all(
        item["candidate_window"]["outcome"][
            "association_outcome_available"
        ]
        and item["candidate_window"]["outcome"][
            "coverage_outcome_available"
        ]
        for item in candidate_records
    )
    diagnostics = result.summary["module_final_diagnostics"]
    assert diagnostics["d5_a3_runtime_ack_count"] > 0
    assert diagnostics["d5_a3_observation_frame_count"] == len(
        candidate_records
    )
    assert diagnostics["d5_a3_physical_window_count"] == len(
        candidate_records
    )
    assert diagnostics["d5_a3_candidate_stage_record_count"] == len(
        records
    )
    assert result.active_vision_a3_candidate_stage_records == (
        stage_records
    )
    assert result.summary["learning_adoption_status"]["A3"] == (
        "verified_adoption"
    )
    audit = result.summary["learning_adoption_audit"]
    assert audit["variants"]["A3"]["highest_evidence_stage"] == (
        "physical_window_validated"
    )
    assert audit["variants"]["A3"]["actual_adoption_count"] == {
        "availability": "available",
        "value": len(records),
        "reason_codes": [],
    }
    assert "a3_same_key_r0_incomplete" in audit["blocker_codes"]
    assert not any(audit["permissions"].values())


def test_a3_runtime_bridge_records_assigned_zero_detection_as_reacquire() -> None:
    policy = _AdmittedActiveVisionPolicyFixture()
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d5_active_vision_mode="assist",
            capture_learning_artifacts=True,
            d5_active_vision_evidence_tail_s=0.25,
        ),
        d5_active_vision_policy=policy,
        learning_runtime_diagnostics={
            "d5_active_vision": {
                "bundle_loaded": True,
                "assist_admitted": True,
                "effective_mode": "assist",
                "model_fingerprint": policy.model_fingerprint,
                "bundle_manifest_sha256": policy.bundle_manifest_sha256,
                "bundle_weights_sha256": policy.bundle_weights_sha256,
            }
        },
    )
    config = ScenarioConfig(
        scenario_name="a3_zero_detection_window",
        scenario_version="a3-zero-detection-window-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=2.5,
        seed=9,
        world_half_extent_m=500.0,
        protected_radius_m=100.0,
        target_proxy_width_m=10.0,
        target_proxy_height_m=4.0,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=0.0,
        communication_drop_probability=0.0,
        communication_jitter_s=0.0,
    )

    result = run_episode(config, module_stack=stack)

    records = stack.learning_adoption_evidence_records()["a3"]
    physical = tuple(
        item
        for item in records
        if item["candidate_physical_window_available"]
    )
    assert physical
    frames = tuple(
        frame
        for item in physical
        for frame in item["candidate_window"]["observation_frames"]
    )
    assigned_frames = tuple(
        frame
        for frame in frames
        if frame["target_global_track_id"] is not None
    )
    assert assigned_frames
    assert all(
        frame["schema_version"]
        == "d5.active-vision-a3-anonymous-observation-frame.v2"
        and frame["frame_observation_state"] == "processed_zero_detections"
        and frame["association_state"] == "reacquire"
        and frame["assigned_reference_visible"] is False
        and frame["observed_tracklet_keys"] == []
        and frame["bindings"] == []
        for frame in assigned_frames
    )
    diagnostics = result.summary["module_final_diagnostics"]
    assert diagnostics["d5_camera_empty_frame_received_count"] > 0
    assert diagnostics["d5_camera_empty_frame_consumed_count"] > 0
    assert diagnostics["d5_camera_empty_frame_rejected_count"] == 0
    assert diagnostics["d5_active_vision_tail_suppressed_count"] > 0
    assert result.summary["online_truth_use_count"] == 0
    assert not any(
        result.summary["learning_adoption_audit"]["permissions"].values()
    )


class _StaleCameraFrameVersionStack(IntegratedScalableModuleStack):
    def step(self, step_input):
        stale_events = tuple(
            replace(
                event,
                communication_version=max(
                    0,
                    event.communication_version - 1,
                ),
            )
            for event in step_input.arrived_camera_frame_events
        )
        return super().step(
            replace(
                step_input,
                arrived_camera_frame_events=stale_events,
            )
        )


def test_a3_zero_detection_frame_with_stale_command_version_fails_closed() -> None:
    policy = _AdmittedActiveVisionPolicyFixture()
    stack = _StaleCameraFrameVersionStack(
        IntegratedStackConfig(
            d5_active_vision_mode="assist",
            capture_learning_artifacts=True,
            d5_active_vision_evidence_tail_s=0.25,
        ),
        d5_active_vision_policy=policy,
        learning_runtime_diagnostics={
            "d5_active_vision": {
                "bundle_loaded": True,
                "assist_admitted": True,
                "effective_mode": "assist",
                "model_fingerprint": policy.model_fingerprint,
                "bundle_manifest_sha256": policy.bundle_manifest_sha256,
                "bundle_weights_sha256": policy.bundle_weights_sha256,
            }
        },
    )
    config = ScenarioConfig(
        scenario_name="a3_stale_empty_frame_version",
        scenario_version="a3-stale-empty-frame-version-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=2.5,
        seed=9,
        world_half_extent_m=500.0,
        protected_radius_m=100.0,
        target_proxy_width_m=10.0,
        target_proxy_height_m=4.0,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=0.0,
        communication_drop_probability=0.0,
        communication_jitter_s=0.0,
    )

    result = run_episode(config, module_stack=stack)

    diagnostics = result.summary["module_final_diagnostics"]
    assert diagnostics["d5_camera_empty_frame_received_count"] > 0
    assert diagnostics["d5_camera_empty_frame_consumed_count"] == 0
    assert diagnostics["d5_a3_bridge_blocker_counts"][
        "camera_empty_frame_version_mismatch"
    ] > 0
    assert all(
        not item["candidate_physical_window_available"]
        for item in stack.learning_adoption_evidence_records()["a3"]
    )
    assert result.summary["online_truth_use_count"] == 0
    assert not any(
        result.summary["learning_adoption_audit"]["permissions"].values()
    )


def test_active_vision_observation_trigger_blocks_blind_periodic_reissue() -> None:
    config = ScenarioConfig(
        scenario_name="active_vision_no_camera_frames",
        scenario_version="active-vision-no-camera-frames-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=2.0,
        seed=12,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )
    triggered = run_episode(
        config,
        module_stack=IntegratedScalableModuleStack(
            IntegratedStackConfig(
                d5_active_vision_observation_triggered=True,
                d5_active_vision_evidence_tail_s=0.25,
            )
        ),
    )
    periodic = run_episode(
        config,
        module_stack=IntegratedScalableModuleStack(
            IntegratedStackConfig(
                d5_active_vision_observation_triggered=False,
                d5_active_vision_evidence_tail_s=0.25,
            )
        ),
    )

    assert 0 < triggered.summary["camera_command_issued_count"]
    assert triggered.summary["camera_command_issued_count"] < (
        periodic.summary["camera_command_issued_count"]
    )
    assert periodic.summary["module_final_diagnostics"][
        "d5_active_vision_tail_suppressed_count"
    ] > 0


def test_active_vision_r0_runtime_bridge_exports_independent_rule_windows() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d5_active_vision_mode="disabled",
            capture_learning_artifacts=True,
        )
    )
    config = ScenarioConfig(
        scenario_name="a3_delayed_anonymous_window",
        scenario_version="a3-delayed-anonymous-window-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=3.5,
        seed=9,
        world_half_extent_m=500.0,
        protected_radius_m=100.0,
        target_proxy_width_m=10.0,
        target_proxy_height_m=4.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
    )

    result = run_episode(config, module_stack=stack)

    windows = stack.active_vision_r0_window_records()
    assert windows
    assert result.active_vision_r0_window_records == windows
    assert all(item["arm"] == "R0" for item in windows)
    assert all(item["command_source"] == "deterministic_rule" for item in windows)
    assert all(item["adoption_trace_sha256"] is None for item in windows)
    assert all(
        item["runtime_ack_evidence_kind"] == "runtime_observed"
        and item["camera_feedback_evidence_kind"] == "runtime_observed"
        and item["observation_evidence_kind"] == "runtime_observed"
        and item["synthetic_fixture"] is False
        for item in windows
    )
    assert all(item["online_truth_use_count"] == 0 for item in windows)
    assert all(item["global_track_id_rewrite_count"] == 0 for item in windows)
    diagnostics = result.summary["module_final_diagnostics"]
    assert diagnostics["d5_a3_r0_runtime_ack_count"] > 0
    assert diagnostics["d5_a3_r0_observation_frame_count"] == len(windows)
    assert diagnostics["d5_a3_r0_physical_window_count"] == len(windows)
    assert diagnostics["d5_a3_r0_window_record_count"] == len(windows)
    assert not stack.learning_adoption_evidence_records()["a3"]


def test_5v5_online_stack_connects_d1_to_d7_without_truth_identity(tmp_path) -> None:
    config = ScenarioConfig(
        scenario_name="integrated_5v5",
        scenario_version="integrated-5v5-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d5_recon_track_cues_enabled=True)
    )

    result = run_episode(config, module_stack=stack, output_dir=tmp_path)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert result.d1_consistency_evidence_records
    d1_publications = tuple(
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d1.fused_tracks"
    )
    assert d1_publications
    state_only = tuple(
        payload
        for payload in d1_publications
        if not payload["tracks_materialized"]
    )
    full_snapshots = tuple(
        payload for payload in d1_publications if payload["tracks_materialized"]
    )
    assert state_only
    assert len(full_snapshots) == len(
        {payload["summary"]["published_at"] for payload in d1_publications}
    )
    assert all(
        payload["snapshot_kind"] == "state_update"
        and payload["tracks"] == []
        and payload["track_count"] == 0
        and payload["current_track_count"] > 0
        for payload in state_only
    )
    assert all(
        payload["snapshot_kind"] == "full_posterior"
        and payload["track_count"] == payload["current_track_count"]
        and payload["track_count"] == len(payload["tracks"])
        for payload in full_snapshots
    )
    published_observation_ids = {
        item["observation_id"]
        for payload in d1_publications
        for item in payload["observation_lineage"]
    }
    assert published_observation_ids == {
        item.observation_id for item in result.d1_consistency_evidence_records
    }
    assert result.observation_governance_audit["d1_state_only_scan_count"] == len(
        state_only
    )
    assert result.observation_governance_audit[
        "d1_materialized_snapshot_count"
    ] == len(full_snapshots)
    final_diagnostics = result.summary["module_final_diagnostics"]
    assert final_diagnostics["d1_fusion_performance"]["current_track_count"] == 5
    assert final_diagnostics["d5_terminal_performance"]["process_frame_count"] > 0
    assert final_diagnostics["d5_terminal_performance"]["graph_build_count"] > 0
    assert len(stack.latest_d1_tracks) == 5
    assert len(stack.latest_d2_tracks) == 5
    assert len(stack.latest_plan.assignments) == 5
    assert stack.latest_plan.unassigned_target_ids == ()
    assert len(stack.latest_guidance_batch.pair_commands) == 5
    assert all(
        command.mode.value == "midcourse_pn_3d"
        for command in stack.latest_guidance_batch.pair_commands
    )
    topics = {message.topic for message in result.online_messages}
    assert {
        "modules.d1.fused_tracks",
        "modules.d2.associated_tracks",
        "modules.d3.assignment_plan",
        "modules.d4.regional_failover",
        "modules.d5.terminal_association",
        "modules.d5.active_vision",
        "modules.d7.guidance_commands",
    }.issubset(topics)
    d5_payload = next(
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.terminal_association"
    )
    assert "all_possible_camera_pairs" in d5_payload["diagnostics"]
    assert "candidate_tracklet_edges" in d5_payload["diagnostics"]
    assert len(d5_payload["local_tracklets"]) == d5_payload["tracklet_count"]
    assert all(
        item["tracklet_key"]
        == (
            f"{item['resource_id']}/{item['camera_id']}:"
            f"{item['local_track_id']}"
        )
        and len(item["center_px"]) == 2
        and np.asarray(item["covariance_px"]).shape == (2, 2)
        and item["measurement_timestamp"] <= item["arrival_timestamp"]
        for item in d5_payload["local_tracklets"]
    )
    assert stack.latest_d5_result is not None
    assert all(
        tracklet.local_track_id.startswith("trk-")
        for tracklet in stack.latest_d5_result.tracklets
    )
    center_ids = {track.global_track_id for track in stack.latest_d2_tracks}
    assert {
        binding.global_track_id
        for binding in stack.latest_d5_result.association.bindings
        if binding.global_track_id is not None
    }.issubset(center_ids)
    active_vision_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.active_vision"
    ]
    assert active_vision_payloads
    assert result.summary["camera_command_issued_count"] > 0
    assert result.summary["camera_command_applied_count"] == result.summary[
        "camera_command_issued_count"
    ]
    assert result.summary["camera_command_rejected_count"] == 0
    assert all(
        command["target_global_track_id"] is None
        or command["target_global_track_id"] in center_ids
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    assert all(
        command["payload_version"]
        == "main.camera-observation-command-payload.v1"
        and len(command["aim_point_ned"]) == 3
        and all(np.isfinite(command["aim_point_ned"]))
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    assert all(
        not str(command["target_global_track_id"]).startswith("TGT-")
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    assert stack.latest_active_vision_snapshot is not None
    recon_targets = stack.latest_active_vision_snapshot.assigned_target_ids(
        "CAM-RECON-001"
    )
    assert len(recon_targets) == 1
    assert set(recon_targets).issubset(center_ids)
    assert stack.latest_active_vision_recon_cue_count == 1
    assert all(not target_id.startswith("TGT-") for target_id in recon_targets)
    camera_acks = [
        message.payload
        for message in result.online_messages
        if message.topic == "runtime.camera_command_ack"
    ]
    assert len(camera_acks) == result.summary["camera_command_ack_count"]
    assert {ack["status"] for ack in camera_acks} == {"applied"}
    assert result.summary["learning_adoption_status"] == {
        "A1": "evidence_unavailable",
        "A2": "evidence_unavailable",
        "A3": "evidence_unavailable",
    }
    timings = {item.stage: item for item in result.stage_timings}
    assert timings["module.d1_fusion"].call_count > 0
    assert timings["module.d3_assignment"].wall_time_s > 0.0
    assert timings["module.main_d4_adapter"].mean_wall_time_ms > 0.0
    fusion_timing = timings["module.d1_fusion"]
    assert fusion_timing.distribution_available is True
    assert fusion_timing.distribution_unavailable_reason is None
    assert (
        0.0
        < fusion_timing.p50_wall_time_ms
        <= fusion_timing.p95_wall_time_ms
        <= fusion_timing.max_wall_time_ms
    )
    with (tmp_path / "stage_timings.csv").open(
        newline="",
        encoding="utf-8",
    ) as stream:
        timing_rows = list(csv.DictReader(stream))
    fusion_row = next(
        row for row in timing_rows if row["stage"] == "module.d1_fusion"
    )
    assert fusion_row["schema_version"] == STAGE_TIMING_SCHEMA_VERSION
    assert fusion_row["distribution_available"] == "True"
    assert fusion_row["distribution_unavailable_reason"] == ""
    assert float(fusion_row["p50_wall_time_ms"]) > 0.0
    assert float(fusion_row["p95_wall_time_ms"]) >= float(
        fusion_row["p50_wall_time_ms"]
    )
    assert float(fusion_row["max_wall_time_ms"]) >= float(
        fusion_row["p95_wall_time_ms"]
    )
    report = (tmp_path / "SCALABLE_3D_EPISODE_REPORT_CN.md").read_text(
        encoding="utf-8"
    )
    assert "本次启用 D1-D7 规则集成栈" in report
    assert "D1/D2 航迹数分别为 5/5" in report
    online_lines = (tmp_path / "online_observations.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    d1_lines = (tmp_path / "offline_identity" / "online_d1_records.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    d2_lines = (tmp_path / "offline_identity" / "online_d2_records.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert d1_lines == [
        line
        for line in online_lines
        if json.loads(line)["topic"] == "modules.d1.fused_tracks"
    ]
    assert d2_lines == [
        line
        for line in online_lines
        if json.loads(line)["topic"] == "modules.d2.associated_tracks"
    ]
    with (tmp_path / "post_run_timings.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        post_run_rows = list(csv.DictReader(stream))
    assert {row["stage"] for row in post_run_rows}.issuperset(
        {
            "online_bus_and_identity_views",
            "offline_identity",
            "offline_consistency",
            "d6_runtime_plan_outcomes",
            "total_before_timing_artifact",
        }
    )
    assert {
        row["schema_version"] for row in post_run_rows
    } == {"scalable3d-post-run-timings-v1"}
    assert all(float(row["wall_time_s"]) >= 0.0 for row in post_run_rows)
    consistency_manifest = json.loads(
        (tmp_path / "offline_consistency" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    consistency_result = json.loads(
        (tmp_path / "offline_consistency" / "offline_result.json").read_text(
            encoding="utf-8"
        )
    )
    d2_lineage_mapping = json.loads(
        (tmp_path / "offline_consistency" / "d2_lineage_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    assert consistency_manifest["status"] == "available"
    assert consistency_manifest["truth_metrics_available"] is True
    assert consistency_manifest["mapping_audit"]["available"] is True
    assert consistency_manifest["mapping_audit"]["policy"] == (
        "d2_source_observation_exact_join_v1"
    )
    assert all(
        value.startswith("sha256:")
        for value in consistency_manifest["source_hashes"].values()
    )
    assert consistency_result["metrics"]["position_rmse_m"]["available"] is True
    assert consistency_result["metrics"]["mean_nees"]["available"] is True
    assert d2_lineage_mapping["producer_role"] == "d2_evaluator_only"
    assert d2_lineage_mapping["mapping_count"] >= 5
    d6_record = json.loads(
        (tmp_path / "d6_truth_isolated" / "episode_record.json").read_text(
            encoding="utf-8"
        )
    )
    assert d6_record["d1_consistency"]["status"] == "available"
    assert d6_record["d2_identity"]["id_switch_count"] == 0
    assert d6_record["d2_identity"]["id_switch_count_availability"] == (
        "available"
    )
    assert d6_record["d2_identity"]["truth_isolation_verified"] is True
    recovery_provenance = d6_record["d2_identity"][
        "identity_recovery_config_provenance"
    ]
    assert recovery_provenance["availability"] == "available"
    assert recovery_provenance["provenance_verified"] is True
    assert recovery_provenance["online_d2_records_verified"] is True
    assert recovery_provenance[
        "identity_commitment_recovery_config_consistency_verified"
    ] is True
    assert recovery_provenance[
        "identity_commitment_recovery_config_record_count"
    ] == len(d2_lines)
    assert recovery_provenance["d2_record_count"] == len(d2_lines)
    assert recovery_provenance[
        "identity_commitment_recovery_config"
    ]["max_recovery_evidence_age_seconds"] == pytest.approx(
        config.identity_lineage_freshness_budget_s
    )
    runtime_root = tmp_path / "d6_runtime_plan_outcomes"
    runtime_inputs = json.loads(
        (runtime_root / "input_specification.json").read_text(encoding="utf-8")
    )
    runtime_result = json.loads(
        (runtime_root / "runtime_plan_outcome_join.json").read_text(
            encoding="utf-8"
        )
    )
    runtime_manifest = json.loads(
        (runtime_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(runtime_inputs["artifacts"]) == 11
    assert all(
        not item["path"].startswith("/")
        and item["sha256"].startswith("sha256:")
        for item in runtime_inputs["artifacts"].values()
    )
    assert runtime_result["runtime_ack_evidence"]["ack_count"] >= 1
    assert runtime_result["runtime_ack_evidence"]["binding_count"] >= 5
    assert runtime_result["runtime_ack_evidence"]["online_truth_use_count"] == 0
    assert runtime_result["d2_identity_recovery_config_provenance"][
        "provenance_verified"
    ] is True
    assert runtime_result["admission"]["ppo_allowed"] is False
    assert runtime_result["admission"]["assist_allowed"] is False
    assert runtime_result["admission"]["authority_allowed"] is False
    assert runtime_result["admission"]["rule_fallback_required"] is True
    assert runtime_manifest["runtime_assignment_plan_ack_count"] == (
        result.summary["assignment_plan_ack_count"]
    )
    assert runtime_manifest["admission"] == {
        "assist_allowed": False,
        "authority_allowed": False,
        "ppo_allowed": False,
        "rule_fallback_required": True,
        "status": "runtime_observed_diagnostic_only_admission_closed",
    }
    governance = result.observation_governance_audit
    assert governance is not None
    assert governance["online_truth_use_count"] == 0
    assert governance["d1_scan_input"]["closed"] is True
    assert governance["d1_scan_input"]["current_buffered_scan_count"] == 0
    ledger = governance["d2_claim_ledger"]
    assert ledger["current_count"] <= ledger["max_count"]
    assert ledger["peak_count"] <= ledger["max_count"]
    governance_manifest = json.loads(
        (
            tmp_path
            / "observation_governance"
            / "observation_governance_manifest.json"
        ).read_text(encoding="utf-8")
    )
    governance_online = json.loads(
        (
            tmp_path
            / "observation_governance"
            / "observation_governance_online_audit.json"
        ).read_text(encoding="utf-8")
    )
    governance_aggregate = json.loads(
        (
            tmp_path
            / "observation_governance"
            / "d6_report"
            / "observation_governance_aggregate.json"
        ).read_text(encoding="utf-8")
    )
    assert governance_manifest["online_truth_use_count"] == 0
    assert governance_online["online_truth_use_count"] == 0
    assert governance_online["d1_scan_oosm_audit"]["metrics"][
        "current_oosm_buffer_count"
    ]["value"] == 0
    assert governance_aggregate["episode_count"] == 1
    assert governance_aggregate["truth_isolation"]["online_truth_use_count"] == 0


def test_d1_same_time_snapshot_coalescing_preserves_final_module_state() -> None:
    config = ScenarioConfig(
        scenario_name="d1_snapshot_coalescing_equivalence",
        scenario_version="d1-snapshot-coalescing-equivalence-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )
    baseline = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_coalesce_same_fusion_time=False)
    )
    candidate = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_coalesce_same_fusion_time=True)
    )

    baseline_result = run_episode(config, module_stack=baseline)
    candidate_result = run_episode(config, module_stack=candidate)

    assert candidate_result.observation_governance_audit[
        "d1_state_only_scan_count"
    ] > 0
    assert baseline_result.observation_governance_audit[
        "d1_state_only_scan_count"
    ] == 0
    assert candidate_result.observation_governance_audit[
        "d1_materialized_snapshot_count"
    ] < baseline_result.observation_governance_audit[
        "d1_materialized_snapshot_count"
    ]
    assert tuple(track.global_track_id for track in candidate.latest_d1_tracks) == tuple(
        track.global_track_id for track in baseline.latest_d1_tracks
    )
    for candidate_track, baseline_track in zip(
        candidate.latest_d1_tracks,
        baseline.latest_d1_tracks,
        strict=True,
    ):
        assert candidate_track.timestamp == baseline_track.timestamp
        np.testing.assert_array_equal(candidate_track.state, baseline_track.state)
        np.testing.assert_array_equal(
            candidate_track.covariance,
            baseline_track.covariance,
        )
        assert candidate_track.track_level == baseline_track.track_level
    assert tuple(track.global_track_id for track in candidate.latest_d2_tracks) == tuple(
        track.global_track_id for track in baseline.latest_d2_tracks
    )
    for candidate_track, baseline_track in zip(
        candidate.latest_d2_tracks,
        baseline.latest_d2_tracks,
        strict=True,
    ):
        np.testing.assert_array_equal(candidate_track.state, baseline_track.state)
        np.testing.assert_array_equal(
            candidate_track.covariance,
            baseline_track.covariance,
        )
        assert candidate_track.lifecycle_state == baseline_track.lifecycle_state
    assert candidate.latest_plan.execution_signature() == (
        baseline.latest_plan.execution_signature()
    )
    np.testing.assert_array_equal(
        candidate.latest_guidance_batch.acceleration_ned_mps2,
        baseline.latest_guidance_batch.acceleration_ned_mps2,
    )
    assert tuple(
        replace(command, plan_id="")
        for command in candidate.latest_guidance_batch.pair_commands
    ) == tuple(
        replace(command, plan_id="")
        for command in baseline.latest_guidance_batch.pair_commands
    )
    assert [
        item.to_dict() for item in candidate_result.d1_consistency_evidence_records
    ] == [
        item.to_dict() for item in baseline_result.d1_consistency_evidence_records
    ]


def test_d6_batch_aggregates_distinct_seed_episode_artifacts(tmp_path) -> None:
    results = []
    for seed in (31, 32):
        config = ScenarioConfig(
            scenario_name="d6_batch_3v3",
            scenario_version="d6-batch-3v3-v1",
            target_count=3,
            resource_count=3,
            recon_count=1,
            duration_s=0.8,
            seed=seed,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
            communication_enabled=False,
        )
        results.append(
            run_episode(
                config,
                module_stack=IntegratedScalableModuleStack(),
                output_dir=tmp_path / f"seed_{seed}",
            )
        )

    paths = write_batch_outputs(results, tmp_path / "batch")

    aggregate = json.loads(
        paths["d6_truth_isolated_batch_aggregate_json"].read_text(
            encoding="utf-8"
        )
    )
    assert aggregate["episode_count"] == 2
    assert aggregate["scale_values"] == [3]
    assert len(aggregate["groups"]) == 1
    group = aggregate["groups"][0]
    assert group["episode_count"] == 2
    assert group["seed_count"] == 2
    assert group["metrics"]["d2.id_switch_count"]["episode_value_count"] == 2


def test_200v200_stack_uses_sparse_candidates_and_commands_every_assignment() -> None:
    config = ScenarioConfig(
        scenario_name="integrated_200v200_smoke",
        scenario_version="integrated-200v200-smoke-v1",
        target_count=200,
        resource_count=200,
        recon_count=8,
        region_count=8,
        duration_s=0.45,
        seed=17,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert len(stack.latest_d1_tracks) == 200
    assert len(stack.latest_d2_tracks) == 200
    assert len(stack.latest_plan.assignments) == 200
    assert stack.latest_plan.unassigned_target_ids == ()
    assert stack.latest_plan.metadata["candidate_full_edge_count"] == 40_000
    assert stack.latest_plan.metadata["candidate_edge_count"] == 6_400
    assert len(stack.latest_guidance_batch.pair_commands) == 200
    assert stack.latest_guidance_batch.acceleration_ned_mps2.shape == (200, 3)


def test_center_failure_reissues_a_secondary_owned_plan_before_guidance_continues() -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    config = replace(
        config,
        metadata={
            **config.metadata,
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ],
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[0]["summary"]["selected_layer_counts"]["center"] == 8
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["secondary"] == 8
    assert d4_payloads[-1]["summary"]["execution_allowed_region_count"] == 8
    assert stack.latest_plan.version == 2
    assert stack.latest_plan.metadata["active_plan_owner"] == "secondary"
    assert stack.latest_plan.metadata["owner_node_id"] == "RECON-001"
    assert all(
        command.mode.value == "midcourse_pn_3d"
        for command in stack.latest_guidance_batch.pair_commands
    )


def test_d4_secondary_execution_waits_for_delivered_plan_messages() -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    config = replace(
        config,
        metadata={
            **config.metadata,
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ],
        },
    )
    result = run_episode(
        config,
        module_stack=IntegratedScalableModuleStack(
            IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
        ),
    )

    secondary_plan = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d3.assignment_plan"
        and message.payload["metadata"].get("active_plan_owner") == "secondary"
    )
    transition = next(
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
        and abs(message.timestamp - secondary_plan.timestamp) <= 1.0e-9
    )
    released = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
        and message.timestamp > secondary_plan.timestamp
        and message.payload["summary"]["execution_allowed_region_count"] == 8
    )

    assert transition["summary"]["execution_allowed_region_count"] == 0
    assert released.timestamp - secondary_plan.timestamp <= 0.15
    assert result.summary["delivered_control_topic_counts"][
        "d4.regional_plan_broadcast.v1"
    ] >= 5
    assert result.summary["delivered_control_topic_counts"][
        "d4.secondary_readiness.v1"
    ] >= 3


def test_center_failure_without_communication_stays_fail_closed() -> None:
    config = ScenarioConfig(
        scenario_name="center_failure_without_communication",
        scenario_version="center-failure-without-communication-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=8,
        duration_s=3.2,
        seed=1251,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
        metadata={
            "fault_schedule": [
                {"time_s": 1.5, "component": "center", "action": "failed"}
            ]
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    final_d4 = next(
        message.payload
        for message in reversed(result.online_messages)
        if message.topic == "modules.d4.regional_failover"
    )
    assert final_d4["summary"]["execution_allowed_region_count"] == 0
    assert final_d4["summary"]["fail_closed_region_count"] == 8
    assert result.summary["delivered_control_message_count"] == 0
    assert stack.latest_plan.metadata["active_plan_owner"] == "center"
    assert Counter(
        (command.mode.value, command.gate_reason)
        for command in stack.latest_guidance_batch.pair_commands
    ) == {("hold", "d4_hold_for_review"): 5}


def test_m_to_n_secondary_coalition_waits_for_all_delivered_acks() -> None:
    config = ScenarioConfig(
        scenario_name="center_failure_m_to_n_async_ack",
        scenario_version="center-failure-m-to-n-async-ack-v1",
        target_count=2,
        resource_count=4,
        recon_count=1,
        region_count=1,
        duration_s=3.2,
        seed=1271,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_latency_s=0.04,
        communication_jitter_s=0.0,
        communication_drop_probability=0.0,
        metadata={
            "demand_pattern": "hybrid_2_primary_1_reserve",
            "high_threat_fraction": 0.5,
            "fault_schedule": [
                {"time_s": 1.5, "component": "center", "action": "failed"}
            ],
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    secondary_plan = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d3.assignment_plan"
        and message.payload["metadata"].get("active_plan_owner") == "secondary"
    )
    assignment_counts = Counter(
        item["global_track_id"] for item in secondary_plan.payload["assignments"]
    )
    coalition_target_id, required_count = max(
        assignment_counts.items(),
        key=lambda item: item[1],
    )
    assert required_count == 3
    coalition_assignments = [
        item
        for item in secondary_plan.payload["assignments"]
        if item["global_track_id"] == coalition_target_id
    ]
    primary_resource_ids = {
        item["resource_id"]
        for item in coalition_assignments
        if item["member_role"] == "primary"
    }
    reserve_resource_ids = {
        item["resource_id"]
        for item in coalition_assignments
        if item["member_role"] == "reserve"
    }
    assert len(primary_resource_ids) == 2
    assert len(reserve_resource_ids) == 1

    commit_frames = []
    for message in result.online_messages:
        if (
            message.topic != "modules.d4.regional_failover"
            or message.timestamp < secondary_plan.timestamp
        ):
            continue
        commits = [
            commit
            for region in message.payload["regions"]
            for commit in region["coalition_commits"]
            if commit["global_track_id"] == coalition_target_id
            and commit["commit_required"]
        ]
        if commits:
            commit_frames.append((message, commits[0]))

    collecting_message, collecting = next(
        item
        for item in commit_frames
        if item[1]["state"] == "collecting_acks"
    )
    committed_message, committed = next(
        item for item in commit_frames if item[1]["state"] == "committed"
    )
    assert collecting_message.timestamp < committed_message.timestamp
    assert collecting["acked_member_ids"] == []
    assert len(collecting["missing_member_ids"]) == required_count
    assert collecting["execution_authorized"] is False
    assert set(committed["acked_member_ids"]) == set(
        committed["required_member_ids"]
    )
    assert len(committed["acked_member_ids"]) == required_count
    assert committed["missing_member_ids"] == []
    assert committed["execution_authorized"] is True

    coalition_resource_ids = set(committed["required_member_ids"])
    precommit_commands = [
        command
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and collecting_message.timestamp
        <= message.timestamp
        < committed_message.timestamp
        for command in message.payload["commands"]
        if command["resource_id"] in coalition_resource_ids
        and command["global_track_id"] == coalition_target_id
    ]
    assert len(precommit_commands) == required_count
    assert {command["mode"] for command in precommit_commands} == {"hold"}
    assert {
        command["gate_reason"]
        for command in precommit_commands
        if command["resource_id"] in primary_resource_ids
    } == {"d4_hold_for_review"}
    assert {
        command["gate_reason"]
        for command in precommit_commands
        if command["resource_id"] in reserve_resource_ids
    } == {"assignment_not_current"}

    released_commands = next(
        [
            command
            for command in message.payload["commands"]
            if command["resource_id"] in coalition_resource_ids
            and command["global_track_id"] == coalition_target_id
        ]
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and message.timestamp >= committed_message.timestamp
        and sum(
            command["mode"] == "midcourse_pn_3d"
            for command in message.payload["commands"]
            if command["resource_id"] in primary_resource_ids
            and command["global_track_id"] == coalition_target_id
        )
        == len(primary_resource_ids)
    )
    assert len(released_commands) == required_count
    assert {
        command["mode"]
        for command in released_commands
        if command["resource_id"] in primary_resource_ids
    } == {"midcourse_pn_3d"}
    assert {
        (command["mode"], command["gate_reason"])
        for command in released_commands
        if command["resource_id"] in reserve_resource_ids
    } == {("hold", "assignment_not_current")}
    assert sum(
        decision.execution_allowed
        for decision in stack.latest_d4_decision.region_decisions
    ) == 1
    assert result.summary["delivered_control_topic_counts"][
        "d4.coalition_member_ack.v1"
    ] >= required_count
    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_guidance_batch.lifecycle_diagnostics is not None
    assert (
        stack.latest_guidance_batch.lifecycle_diagnostics
        .global_track_id_rewrite_count
        == 0
    )


def test_partition_generation_change_rejects_in_flight_d4_evidence() -> None:
    config = ScenarioConfig(
        scenario_name="d4_partition_generation_change",
        scenario_version="d4-partition-generation-change-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=2,
        duration_s=1.4,
        seed=1261,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_latency_s=0.20,
        communication_jitter_s=0.0,
        communication_drop_probability=0.0,
        metadata={
            "communication_partition_schedule": [
                {"time_s": 0.8, "generation": 1}
            ]
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)
    diagnostics = result.summary["module_final_diagnostics"]

    assert diagnostics["d4_communication_partition_generation"] == 1
    assert diagnostics["d4_communication_rejection_counts"][
        "partition_generation_mismatch"
    ] > 0
    assert diagnostics["d4_communication_accepted_count"] > 0
    assert result.summary["online_truth_use_count"] == 0


def test_secondary_failure_reissues_a_distributed_regional_plan() -> None:
    config = make_curriculum_scenario(
        "secondary_failure",
        scale=5,
        seed=4,
        duration_s=4.4,
    )
    # Radar arrives later than the faster vision stream in this scenario. Keep
    # the production lateness window so valid radar scans survive reordering
    # while the distributed handover is exercised.
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["distributed"] == 8
    active_regions = [
        item for item in d4_payloads[-1]["regions"] if item["task_ids"]
    ]
    assert len(active_regions) == 5
    assert all(item["execution_allowed"] for item in active_regions)
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["regional_owner_layers"] == ("distributed",)
    assert stack.latest_plan.metadata["regional_single_member_authority_count"] == 5
    assert stack.latest_plan.metadata["regional_atomic_coalition_commit_count"] == 0
    assert all(
        assignment.metadata["regional_owner_layer"] == "distributed"
        for assignment in stack.latest_plan.assignments
    )
    distributed_plan = next(
        message
        for message in reversed(result.online_messages)
        if message.topic == "modules.d3.assignment_plan"
        and tuple(
            message.payload["metadata"].get("regional_owner_layers", ())
        ) == ("distributed",)
    )
    transition_guidance = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and abs(message.timestamp - distributed_plan.timestamp) <= 1.0e-9
    )
    assert Counter(
        command["mode"] for command in transition_guidance.payload["commands"]
    ) == {"hold": 5}
    distributed_guidance = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and message.timestamp > distributed_plan.timestamp
        and Counter(
            command["mode"] for command in message.payload["commands"]
        )
        == {"midcourse_pn_3d": 5}
    )
    assert distributed_guidance.timestamp - distributed_plan.timestamp <= 0.15
    distributed_ack = next(
        message
        for message in result.online_messages
        if message.topic == "runtime.assignment_plan_ack"
        and abs(message.timestamp - distributed_plan.timestamp) <= 1.0e-9
    )
    assert distributed_ack.payload["held_binding_count"] == 5
    assert Counter(
        (command.mode.value, command.gate_reason)
        for command in stack.latest_guidance_batch.pair_commands
    ) == {("hold", "global_track_stale"): 5}
    assert stack._regional_plan_rejection_reason is None
    target_id = stack.latest_plan.assignments[0].target_id
    permission = stack._d4_permission(target_id)
    assert permission.action == "continue"
    assert permission.mode == "distributed"
    assert permission.atomic_coalition_formed is None
    assert permission.coalition_commit_state == "single_member_authorized"
    assert permission.metadata["commit_required"] is False


def test_two_secondary_nodes_publish_one_multi_owner_regional_plan() -> None:
    config = ScenarioConfig(
        scenario_name="multi_secondary_50v50",
        scenario_version="multi-secondary-50v50-v1",
        target_count=50,
        resource_count=50,
        recon_count=2,
        region_count=8,
        duration_s=2.4,
        seed=13,
        interceptor_speed_mps=30.0,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        metadata={
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ]
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["regional_owner_layers"] == ("secondary",)
    assert stack.latest_plan.metadata["regional_owner_node_ids"] == (
        "RECON-001",
        "RECON-002",
    )
    assert stack.latest_plan.metadata["regional_single_member_authority_count"] == 50
    assert stack.latest_plan.metadata["regional_atomic_coalition_commit_count"] == 0
    assert {
        assignment.target_id for assignment in stack.latest_plan.assignments
    } == {track.global_track_id for track in stack.latest_d2_tracks}
    assert Counter(
        command.mode.value for command in stack.latest_guidance_batch.pair_commands
    ) == {"midcourse_pn_3d": 50}
    assert stack._regional_plan_rejection_reason is None


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("expired", "regional_d4_authority_lease_expired"),
        ("missing_commit", "regional_d4_commit_evidence_missing"),
        ("stale_source", "regional_d4_stale_source_plan"),
    ),
)
def test_regional_authority_adapter_rejects_incomplete_d4_evidence(
    mutation: str,
    expected_reason: str,
) -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    config = replace(
        config,
        metadata={
            **config.metadata,
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ],
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )
    run_episode(config, module_stack=stack)

    target_ids = {track.global_track_id for track in stack.latest_d2_tracks}
    now = float(stack.latest_d4_decision.timestamp_s)
    if mutation == "expired":
        now = 10.0
    else:
        decisions = list(stack.latest_d4_decision.region_decisions)
        index = next(
            index for index, item in enumerate(decisions) if item.task_ids
        )
        selected = decisions[index]
        if mutation == "missing_commit":
            selected = replace(selected, coalition_commits=())
        else:
            selected = replace(
                selected,
                ownership=replace(
                    selected.ownership,
                    plan_version=selected.ownership.plan_version - 1,
                ),
            )
        decisions[index] = selected
        stack.latest_d4_decision = replace(
            stack.latest_d4_decision,
            region_decisions=tuple(decisions),
        )

    with pytest.raises(RegionalPlanAuthorityError) as error:
        stack._regional_authority_from_d4(
            stack.latest_plan,
            target_ids=target_ids,
            now=now,
        )
    assert error.value.reason == expected_reason


def test_d4_noop_advisory_is_consumed_without_false_successor() -> None:
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
    stack = IntegratedScalableModuleStack(
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )

    result = run_episode(config, module_stack=stack)

    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_d4_region_consumption is not None
    assert stack.latest_d4_region_consumption.consumable is True
    assert stack.latest_plan.metadata["regional_hint_applied"] is False
    assert stack.latest_plan.metadata[
        "regional_hint_successor_plan_available"
    ] is False
    assert stack.latest_plan.metadata["regional_hint_successor_state"] == (
        "no_successor"
    )
    assert stack.latest_plan.metadata["regional_hint_advisory_version"] == 1
    consumption_payloads = [
        item.payload
        for item in result.online_messages
        if item.topic == "modules.d4.region_resource_consumption"
    ]
    assert len(consumption_payloads) == 1
    assert consumption_payloads[0]["consumable"] is True
    assert consumption_payloads[0]["d3_hint_applied"] is False
    assert consumption_payloads[0][
        "d3_successor_plan_available"
    ] is False
    assert consumption_payloads[0]["d3_successor_state"] == "no_successor"
    assert consumption_payloads[0]["bridge_rejection_reason"] == (
        "d3_regional_hint_rejected:"
        "regional_hint_no_executable_successor"
    )
    a2_records = stack.learning_adoption_evidence_records()["a2"]
    assert len(a2_records) == 1
    assert a2_records[0]["stage"] == "safe_adoption_rejected"
    assert a2_records[0]["reason_codes"] == [
        "identifiable_regional_intervention_missing"
    ]
    assert a2_records[0]["identifiable_intervention_available"] is False
    assert a2_records[0]["d3_successor_plan_available"] is False
    assert a2_records[0]["safe_adoption_available"] is False
    assert a2_records[0]["authority_granted"] is False


def test_d4_a2_runtime_bridge_observes_later_current_plan_control() -> None:
    config = ScenarioConfig(
        scenario_name="d4_a2_dynamic_physical_adoption",
        scenario_version="d4-a2-dynamic-physical-adoption-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=3.0,
        seed=1,
        radar_detection_probability=0.45,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_drop_probability=0.0,
        communication_jitter_s=0.0,
        communication_latency_s=0.01,
    )
    stack = IntegratedScalableModuleStack(
        d4_region_advisor=_development_region_advisor(),
        d4_unseen_seed_count=1,
    )

    result = run_episode(config, module_stack=stack)
    diagnostics = stack._diagnostics(config.duration_s)

    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_d4_region_advice.recommendation.policy_name == (
        "d4-a2-constrained-development-intervention"
    )
    assert stack.latest_plan.metadata["regional_hint_applied"] is True
    assert stack.latest_plan.metadata[
        "regional_hint_successor_plan_available"
    ] is True
    assert stack.latest_plan.metadata["regional_hint_successor_state"] == (
        "successor_published"
    )
    assert stack.latest_plan.metadata["authority_epoch"] == 1
    consumption_payload = next(
        item.payload
        for item in result.online_messages
        if item.topic == "modules.d4.region_resource_consumption"
        and item.payload.get("d3_successor_plan_available") is True
    )
    assert consumption_payload["d3_hint_applied"] is True
    assert consumption_payload["d3_successor_state"] == (
        "successor_published"
    )
    assert consumption_payload["d3_successor_plan_id"] == (
        stack.latest_plan.plan_id
    )
    assert consumption_payload["d3_successor_plan_version"] == (
        stack.latest_plan.version
    )
    assert diagnostics["d4_a2_owner_ack_delivery_count"] == 1
    assert diagnostics["d4_a2_physical_window_count"] == 1
    assert diagnostics["d4_a2_safe_adoption_count"] == 1
    assert diagnostics["d4_a2_evidence_stage_counts"] == {
        "physical_window_available": 1
    }
    pending = next(iter(stack._d4_a2_pending_by_plan.values()))
    assert pending.non_hold_control_applied_count > 0
    assert pending.plan_reference.plan_id == stack.latest_plan.plan_id
    assert pending.plan_reference.plan_version == stack.latest_plan.version


def test_d4_a2_runtime_bridge_rejects_incomplete_consumption_payload() -> None:
    stack = IntegratedScalableModuleStack()
    source_envelopes = (
        SimpleNamespace(
            topic="modules.d4.region_resource_consumption",
            payload={
                "bridge_rejection_reason": None,
                "d3_hint_applied": True,
                "d3_successor_plan_available": False,
                "d3_successor_state": "no_successor",
            },
        ),
        SimpleNamespace(topic="modules.d3.assignment_plan", payload={}),
        SimpleNamespace(topic="modules.d7.guidance_commands", payload={}),
    )

    intents = stack.record_assignment_plan_runtime_ack(
        acknowledgement={},
        acknowledgement_envelope=SimpleNamespace(),
        source_publication_envelopes=source_envelopes,
        timestamp_s=1.0,
        partition_generation=0,
    )

    assert intents == ()
    assert stack._d4_a2_bridge_blocker_counts == {
        "runtime_ack_bridge_keyerror": 1
    }


def test_d4_a2_later_control_count_is_current_plan_and_binding_scoped() -> None:
    stack = IntegratedScalableModuleStack()
    stack.latest_plan = SimpleNamespace(
        plan_id="plan-current",
        version=2,
        assignments=(
            SimpleNamespace(resource_id="R-1", target_id="T-1"),
            SimpleNamespace(resource_id="R-2", target_id="T-2"),
        ),
    )
    stack.latest_guidance_batch = SimpleNamespace(
        pair_commands=(
            SimpleNamespace(
                resource_id="R-1",
                assigned_global_track_id="T-1",
                plan_id="plan-current",
                plan_version=2,
                mode=SimpleNamespace(value="midcourse_pn_3d"),
            ),
            SimpleNamespace(
                resource_id="R-2",
                assigned_global_track_id="T-2",
                plan_id="plan-current",
                plan_version=2,
                mode=SimpleNamespace(value="hold"),
            ),
            SimpleNamespace(
                resource_id="R-3",
                assigned_global_track_id="T-3",
                plan_id="plan-current",
                plan_version=2,
                mode=SimpleNamespace(value="midcourse_pn_3d"),
            ),
            SimpleNamespace(
                resource_id="R-1",
                assigned_global_track_id="T-1",
                plan_id="plan-stale",
                plan_version=1,
                mode=SimpleNamespace(value="midcourse_pn_3d"),
            ),
        )
    )

    assert (
        stack._d4_current_plan_non_hold_control_count(
            plan_id="plan-current",
            plan_version=2,
        )
        == 1
    )
    assert (
        stack._d4_current_plan_non_hold_control_count(
            plan_id="plan-stale",
            plan_version=1,
        )
        == 0
    )


def test_d4_advisory_bridge_rejects_replay_and_strict_expiry() -> None:
    config = ScenarioConfig(
        scenario_name="d4_advisory_replay",
        scenario_version="d4-advisory-replay-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.8,
        seed=42,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0),
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )
    run_episode(config, module_stack=stack)
    advice = stack.latest_d4_region_advice
    snapshot = stack.latest_d4_region_snapshot
    decision = stack.latest_d4_decision
    plan = stack.latest_plan
    advisory = advice.advisory_contract

    hint = stack._d3_regional_hint_from_previous_d4(
        previous_plan=plan,
        advice_result=advice,
        source_snapshot=snapshot,
        source_decision=decision,
        now=advisory.created_at_s + 0.1,
        fault_generation_changed=False,
    )
    assert hint is not None
    replay = stack._d3_regional_hint_from_previous_d4(
        previous_plan=plan,
        advice_result=advice,
        source_snapshot=snapshot,
        source_decision=decision,
        now=advisory.created_at_s + 0.2,
        fault_generation_changed=False,
    )
    assert replay is None
    assert "advisory_already_consumed" in (
        stack._d4_region_hint_bridge_rejection_reason or ""
    )

    expiry_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0),
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )
    run_episode(config, module_stack=expiry_stack)
    expiry_advice = expiry_stack.latest_d4_region_advice
    expired = expiry_stack._d3_regional_hint_from_previous_d4(
        previous_plan=expiry_stack.latest_plan,
        advice_result=expiry_advice,
        source_snapshot=expiry_stack.latest_d4_region_snapshot,
        source_decision=expiry_stack.latest_d4_decision,
        now=expiry_advice.advisory_contract.valid_until_s,
        fault_generation_changed=False,
    )
    assert expired is None
    assert "advisory_expired" in (
        expiry_stack._d4_region_hint_bridge_rejection_reason or ""
    )


def test_fault_generation_blocks_d4_advisory_before_gate_consumption() -> None:
    config = ScenarioConfig(
        scenario_name="d4_advisory_fault_fence",
        scenario_version="d4-advisory-fault-fence-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.8,
        seed=43,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0),
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )
    run_episode(config, module_stack=stack)
    advice = stack.latest_d4_region_advice

    hint = stack._d3_regional_hint_from_previous_d4(
        previous_plan=stack.latest_plan,
        advice_result=advice,
        source_snapshot=stack.latest_d4_region_snapshot,
        source_decision=stack.latest_d4_decision,
        now=advice.advisory_contract.created_at_s + 0.1,
        fault_generation_changed=True,
    )

    assert hint is None
    assert stack.latest_d4_region_consumption is None
    assert stack._d4_region_advisory_gate.consumed_advisory_ids == frozenset()
    assert stack._d4_region_hint_bridge_rejection_reason == (
        "fault_generation_changed_before_advisory_consumption"
    )
