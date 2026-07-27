from __future__ import annotations

from dataclasses import replace
import json

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    RegionResourceA2BenefitAuditError,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.paired_learning_adoption import (
    assemble_paired_learning_adoption_evidence,
    run_paired_learning_adoption_batch,
    run_paired_learning_adoption_episodes,
)
from research_modules.scalable_3d_simulation.tests.test_module_stack import (
    _AdmittedActiveVisionPolicyFixture,
    _assist_region_advisor,
    _development_region_advisor,
)


def test_a2_pair_uses_independent_rule_episode_and_is_d6_auditable() -> None:
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

    r0_result, candidate_result, paired = (
        run_paired_learning_adoption_episodes(
                config,
                r0_stack=IntegratedScalableModuleStack(),
                candidate_stack=IntegratedScalableModuleStack(
                    d4_region_advisor=_assist_region_advisor(
                        identifiable_intervention=True,
                    ),
                    d4_unseen_seed_count=1,
                ),
        )
    )

    assert r0_result.manifest.episode_id != candidate_result.manifest.episode_id
    assert paired.candidate_a2_safe_adoption_count == 1
    assert len(paired.a2_records) == 2
    a2 = paired.d6_audit["variants"]["A2"]
    assert a2["availability"] == "available"
    assert a2["same_key_r0_pair_count"]["value"] == 1
    assert a2["benefit_auditable_count"]["value"] == 1
    assert a2["positive_benefit_claimed"] is False
    assert not any(a2["permissions"].values())
    assert not any(paired.d6_audit["permissions"].values())
    reused_identity = replace(
        candidate_result,
        manifest=replace(
            candidate_result.manifest,
            episode_id=r0_result.manifest.episode_id,
        ),
    )
    with pytest.raises(ValueError, match="identities are not isolated"):
        assemble_paired_learning_adoption_evidence(
            r0_result=r0_result,
            candidate_result=reused_identity,
        )


def test_a2_development_adapter_cannot_enter_formal_benefit_pairing() -> None:
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

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="development_intervention_benefit_forbidden",
    ):
        run_paired_learning_adoption_episodes(
            config,
            r0_stack=IntegratedScalableModuleStack(),
            candidate_stack=IntegratedScalableModuleStack(
                d4_region_advisor=_development_region_advisor(),
                d4_unseen_seed_count=1,
            ),
        )


def test_a2_noop_candidate_remains_in_denominator_without_adoption() -> None:
    config = ScenarioConfig(
        scenario_name="d4_a2_noop_attribution",
        scenario_version="d4-a2-noop-attribution-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=41,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_drop_probability=0.0,
        communication_jitter_s=0.0,
        communication_latency_s=0.01,
    )

    _, _, paired = run_paired_learning_adoption_episodes(
        config,
        r0_stack=IntegratedScalableModuleStack(),
        candidate_stack=IntegratedScalableModuleStack(
            d4_region_advisor=_assist_region_advisor(),
            d4_unseen_seed_count=1,
        ),
    )

    assert paired.candidate_a2_record_count == 1
    assert paired.candidate_a2_safe_adoption_count == 0
    assert len(paired.a2_records) == 1
    source = paired.a2_records[0]
    assert source["reason_codes"] == [
        "identifiable_regional_intervention_missing"
    ]
    assert source["identifiable_intervention_available"] is False
    assert source["d3_successor_plan_available"] is False
    assert source["safe_adoption_available"] is False
    assert source["authority_granted"] is False
    a2 = paired.d6_audit["variants"]["A2"]
    assert a2["availability"] == "unavailable"
    assert a2["blocker_codes"] == ["a2_actual_adoption_absent"]
    assert a2["actual_adoption_count"]["availability"] == "available"
    assert a2["actual_adoption_count"]["value"] == 0
    assert not any(a2["permissions"].values())
    assert not any(paired.d6_audit["permissions"].values())


def test_a3_pair_uses_rule_windows_from_separate_episode(
    tmp_path,
) -> None:
    policy = _AdmittedActiveVisionPolicyFixture()
    r0_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            d5_active_vision_mode="disabled",
            capture_learning_artifacts=True,
        )
    )
    candidate_stack = IntegratedScalableModuleStack(
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
        scenario_name="a3_paired_anonymous_window",
        scenario_version="a3-paired-anonymous-window-v1",
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

    r0_result, candidate_result, paired = (
        run_paired_learning_adoption_episodes(
            config,
            r0_stack=r0_stack,
            candidate_stack=candidate_stack,
            output_dir=tmp_path,
        )
    )

    assert r0_result.active_vision_r0_window_records
    assert paired.candidate_a3_adoption_record_count > 0
    assert len(paired.a3_records) == (
        paired.candidate_a3_pairable_record_count
    )
    assert len(paired.a3_pairing_dispositions) == (
        paired.candidate_a3_adoption_record_count
    )
    assert paired.candidate_a3_pairable_record_count == sum(
        item["pairable"] for item in paired.a3_pairing_dispositions
    )
    assert paired.candidate_a3_pairable_record_count > 0
    assert paired.candidate_a3_pairable_record_count == (
        paired.candidate_a3_adoption_record_count
    )
    a3 = paired.d6_audit["variants"]["A3"]
    assert a3["availability"] == "available"
    assert a3["blocker_codes"] == []
    for metric_name in (
        "actual_adoption_count",
        "physical_window_count",
        "same_key_r0_pair_count",
        "benefit_auditable_count",
    ):
        assert a3[metric_name]["availability"] == "available"
        assert a3[metric_name]["value"] == (
            paired.candidate_a3_adoption_record_count
        )
    inventory = a3["pairing_disposition_inventory"]
    assert inventory["availability"] == "available"
    assert inventory["candidate_count"]["value"] == (
        paired.candidate_a3_adoption_record_count
    )
    assert inventory["pairable_count"]["value"] == (
        paired.candidate_a3_pairable_record_count
    )
    assert inventory["unpairable_count"]["value"] == (
        paired.candidate_a3_adoption_record_count
        - paired.candidate_a3_pairable_record_count
    )
    assert inventory["pairing_coverage"]["value"] == pytest.approx(
        paired.candidate_a3_pairable_record_count
        / paired.candidate_a3_adoption_record_count
    )
    assert inventory["inventory_completeness"]["value"] is True
    assert inventory["paired_evidence_completeness"]["value"] is True
    assert a3["positive_benefit_claimed"] is False
    assert not any(a3["permissions"].values())
    pairing_reasons = paired.to_dict()[
        "candidate_a3_pairing_reason_counts"
    ]
    paired_payload = paired.to_dict()
    assert sum(pairing_reasons.values()) == (
        paired.candidate_a3_adoption_record_count
    )
    assert pairing_reasons["pairable"] == (
        paired.candidate_a3_pairable_record_count
    )
    assert pairing_reasons == {
        "pairable": paired.candidate_a3_pairable_record_count
    }
    assert candidate_result.active_vision_a3_candidate_stage_records
    assert paired_payload["candidate_a3_stage_inventory_complete"] is True
    assert paired_payload["candidate_a3_stage_evidence_count"] == (
        paired.candidate_a3_adoption_record_count
    )
    assert (
        paired_payload["candidate_a3_stage_evidence_missing_count"] == 0
    )
    assert paired_payload["candidate_a3_stage_reason_counts"] == {}
    assert all(
        disposition["candidate_stage_evidence"] is not None
        for disposition in paired.a3_pairing_dispositions
    )
    assert all(
        disposition["candidate_stage_reason_codes"] == []
        for disposition in paired.a3_pairing_dispositions
    )
    candidate_stage_sidecar = json.loads(
        (
            tmp_path
            / "candidate"
            / "active_vision_a3_candidate_stages.json"
        ).read_text(encoding="utf-8")
    )
    assert candidate_stage_sidecar["schema_version"] == (
        "scalable3d-active-vision-a3-candidate-stage-records-v1"
    )
    assert len(candidate_stage_sidecar["records"]) == (
        paired.candidate_a3_adoption_record_count
    )
    assert {
        item["comparison_key"] for item in candidate_stage_sidecar["records"]
    } == {
        item["adoption_trace"]["comparison_key"]
        for item in (
            candidate_result.learning_adoption_evidence_records or {}
        )["a3"]
    }
    artifact = json.loads(
        (tmp_path / "paired_learning_adoption.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact["paired_result"]["r0_episode_id"] == (
        r0_result.manifest.episode_id
    )
    assert artifact["paired_result"]["candidate_episode_id"] == (
        candidate_result.manifest.episode_id
    )
    assert (
        artifact["paired_result"]["r0_event_log_sha256"]
        != artifact["paired_result"]["candidate_event_log_sha256"]
    )
    assert len(
        artifact["paired_result"]["records"][
            "a3_pairing_dispositions"
        ]
    ) == paired.candidate_a3_adoption_record_count
    duplicated_r0 = replace(
        r0_result,
        active_vision_r0_window_records=(
            *r0_result.active_vision_r0_window_records,
            r0_result.active_vision_r0_window_records[0],
        ),
    )
    duplicate_result = assemble_paired_learning_adoption_evidence(
        r0_result=duplicated_r0,
        candidate_result=candidate_result,
    )
    assert any(
        "same_key_r0_duplicate" in item["detail_codes"]
        for item in duplicate_result.a3_pairing_dispositions
    )
    assert not any(duplicate_result.d6_audit["permissions"].values())

    legacy_candidate_result = replace(
        candidate_result,
        active_vision_a3_candidate_stage_records=None,
    )
    legacy_result = assemble_paired_learning_adoption_evidence(
        r0_result=r0_result,
        candidate_result=legacy_candidate_result,
    )
    legacy_payload = legacy_result.to_dict()
    assert legacy_payload["candidate_a3_stage_inventory_complete"] is False
    assert legacy_payload["candidate_a3_stage_evidence_count"] == 0
    assert legacy_payload["candidate_a3_stage_evidence_missing_count"] == (
        legacy_result.candidate_a3_adoption_record_count
    )
    assert legacy_payload["candidate_a3_stage_reason_counts"] == {}
    assert all(
        disposition["candidate_stage_evidence"] is None
        and disposition["candidate_stage_reason_codes"] == []
        for disposition in legacy_result.a3_pairing_dispositions
    )
    legacy_a3 = legacy_result.d6_audit["variants"]["A3"]
    assert legacy_a3["availability"] == "available"
    assert legacy_a3["pairing_disposition_inventory"][
        "candidate_stage_evidence_missing_count"
    ]["value"] == legacy_result.candidate_a3_adoption_record_count
    assert not any(legacy_a3["permissions"].values())


def test_pairing_rejects_changed_external_configuration() -> None:
    config = ScenarioConfig(
        scenario_name="paired_external_mismatch",
        scenario_version="paired-external-mismatch-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=1.2,
        seed=3,
        visual_enabled=False,
    )
    r0_result, candidate_result, _ = run_paired_learning_adoption_episodes(
        config,
        r0_stack=IntegratedScalableModuleStack(),
        candidate_stack=IntegratedScalableModuleStack(
            IntegratedStackConfig(d5_active_vision_mode="shadow")
        ),
    )
    mismatched = replace(
        candidate_result,
        config=replace(
            candidate_result.config,
            communication_latency_s=(
                candidate_result.config.communication_latency_s + 0.1
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="exogenous configuration",
    ):
        assemble_paired_learning_adoption_evidence(
            r0_result=r0_result,
            candidate_result=mismatched,
        )


def test_batch_keeps_seed_and_episode_inventories_unique(tmp_path) -> None:
    configs = tuple(
        ScenarioConfig(
            scenario_name="paired_batch_smoke",
            scenario_version="paired-batch-smoke-v1",
            target_count=1,
            resource_count=1,
            recon_count=0,
            duration_s=0.2,
            seed=seed,
            visual_enabled=False,
        )
        for seed in (31, 32)
    )

    with pytest.raises(
        ValueError,
        match="cannot self-assert unseen-seed verification",
    ):
        run_paired_learning_adoption_batch(
            configs,
            r0_stack_factory=lambda _: IntegratedScalableModuleStack(),
            candidate_stack_factory=lambda _: IntegratedScalableModuleStack(),
            seeds_verified_unseen=True,
        )

    batch = run_paired_learning_adoption_batch(
        configs,
        r0_stack_factory=lambda _: IntegratedScalableModuleStack(),
        candidate_stack_factory=lambda _: IntegratedScalableModuleStack(
            IntegratedStackConfig(d5_active_vision_mode="shadow")
        ),
        output_dir=tmp_path,
    )

    payload = batch.to_dict()
    assert payload["seed_count"] == 2
    assert payload["pair_count"] == 2
    assert payload["seeds_verified_unseen"] is False
    assert payload["minimum_seed_count_met"] is False
    assert payload["minimum_unseen_seed_target_met"] is False
    assert payload["a3_candidate_record_count"] == 0
    assert payload["a3_pairable_record_count"] == 0
    assert payload["a3_unpairable_record_count"] == 0
    assert payload["a3_seed_with_pairable_record_count"] == 0
    assert payload["a3_pairing_reason_counts"] == {}
    assert payload["a3_stage_evidence_count"] == 0
    assert payload["a3_stage_evidence_missing_count"] == 0
    assert payload["a3_stage_inventory_complete"] is True
    assert payload["a3_stage_reason_counts"] == {}
    assert payload["d6_non_degradation_available"] is False
    assert payload["model_authorization_allowed"] is False
    with pytest.raises(
        ValueError,
        match="cannot self-assert unseen-seed verification",
    ):
        replace(batch, seeds_verified_unseen=True)
    persisted = json.loads(
        (tmp_path / "paired_learning_adoption_batch.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["content_sha256"] == payload["content_sha256"]
