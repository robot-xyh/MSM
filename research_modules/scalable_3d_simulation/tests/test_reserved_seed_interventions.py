from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    D3_SAFETY_SHELL_VERSION,
    D3DevelopmentBundleBinding,
    RESERVED_EVALUATION_SEEDS,
    RESERVED_SEED_INTERVENTION_SCHEMA_VERSION,
    ReservedSeedInterventionOptions,
    execute_reserved_seed_interventions,
    resolve_d3_development_bundle_binding,
    write_reserved_seed_intervention_execution,
)
from research_modules.scalable_3d_simulation.isolated_physical_rollout import (
    CheckpointPhysicalRolloutOptions,
    execute_checkpoint_paired_physical_rollouts,
    write_checkpoint_paired_physical_rollouts,
)


def test_reserved_seed_runner_emits_forty_fail_closed_arms(tmp_path: Path) -> None:
    missing_bundle = tmp_path / "missing-bundle"
    execution = execute_reserved_seed_interventions(
        ReservedSeedInterventionOptions(scale=5, duration_s=1.2),
        d3_bundle=D3DevelopmentBundleBinding(
            bundle_dir=missing_bundle,
            manifest_sha256="a" * 64,
            policy_version="missing-development-policy",
        ),
        d4_bundle_dir=missing_bundle,
    )

    assert tuple(item.seed for item in execution.sources) == RESERVED_EVALUATION_SEEDS
    assert len(execution.d3_execution.arms) == 40
    assert len(execution.d4_manifest.arm_evidence) == 40
    assert execution.source_nonfinite_count == 0
    assert execution.source_truth_violation_count == 0
    assert all(
        np.isclose(
            item.intervention_world_checkpoint.timestamp,
            item.intervention_timestamp_s,
        )
        for item in execution.sources
    )
    assert all(
        item.intervention_world_checkpoint.intruder_state.flags.writeable is False
        and item.intervention_world_checkpoint.interceptor_state.flags.writeable
        is False
        for item in execution.sources
    )
    assert all(
        len({track_id for track_id, _ in item.offline_track_truth_mapping})
        == len(item.offline_track_truth_mapping)
        and len({truth_id for _, truth_id in item.offline_track_truth_mapping})
        == len(item.offline_track_truth_mapping)
        for item in execution.sources
    )
    assert all(
        len(item.intervention_global_tracks) == item.scenario_config.target_count
        and len(item.planning_target_identity_bridge)
        == item.scenario_config.target_count
        and len(item.planning_resource_identity_bridge)
        == item.scenario_config.resource_count
        and len(item.offline_track_truth_mapping)
        == item.scenario_config.target_count
        for item in execution.sources
    )
    source = execution.sources[0]
    target_bridge = source.planning_target_identity_bridge
    resource_bridge = source.planning_resource_identity_bridge
    with pytest.raises(ValueError, match="source ordinal lineage"):
        replace(
            source,
            planning_target_identity_bridge=(
                target_bridge[1],
                target_bridge[0],
                *target_bridge[2:],
            ),
        )
    with pytest.raises(ValueError, match="source ordinal lineage"):
        replace(
            source,
            planning_resource_identity_bridge=(
                resource_bridge[1],
                resource_bridge[0],
                *resource_bridge[2:],
            ),
        )
    assert execution.d3_execution.bundle_loaded is False
    assert execution.d4_candidate_loader_ready is False
    assert all(
        item.rule_fallback_applied
        for item in execution.d3_execution.arms
        if item.arm_specification.arm_kind == "treatment"
    )
    assert all(
        item.rule_fallback_used
        for item in execution.d4_manifest.arm_evidence
        if item.arm.value == "treatment_candidate"
    )
    assert sum(
        item.arm.value == "treatment_candidate"
        for item in execution.d4_manifest.arm_evidence
    ) == 20
    assert execution.d3_execution.runtime_ack_available is False
    assert execution.d3_execution.outcome_available is False
    assert execution.d3_execution.counterfactual_available is False
    assert execution.d3_execution.causal_available is False
    assert execution.d4_manifest.observed_outcome_available is False
    assert execution.d4_manifest.counterfactual_available is False
    assert execution.d4_manifest.causal_effect_available is False
    assert D3_SAFETY_SHELL_VERSION == "d3-offline-intervention-safety-shell-v2"
    assert all(
        item.arm_specification.safety_shell_version == D3_SAFETY_SHELL_VERSION
        for item in execution.d3_execution.arms
    )
    assert all(
        item.schema == "d4-region-resource-paired-arm-evidence-v2"
        and item.candidate_gate_diagnostics_available is True
        for item in execution.d4_manifest.arm_evidence
    )

    output = tmp_path / "published"
    paths = write_reserved_seed_intervention_execution(output, execution)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    d4_payload = json.loads(paths["d4_execution"].read_text(encoding="utf-8"))
    lineage = paths["source_lineage"].read_text(encoding="utf-8").splitlines()

    assert manifest["schema_version"] == RESERVED_SEED_INTERVENTION_SCHEMA_VERSION
    assert manifest["source_episode_count"] == 20
    assert manifest["target_count"] == 5
    assert manifest["resource_count"] == 5
    assert manifest["source_git_commits"]
    assert 0 <= manifest["dirty_source_episode_count"] <= 20
    assert manifest["d3_arm_count"] == 40
    assert manifest["d4_arm_count"] == 40
    assert manifest["online_truth_use_count"] == 0
    assert manifest["evidence_availability"] == {
        "execution_receipts": True,
        "runtime_ack": False,
        "physical_outcome": False,
        "counterfactual": False,
        "causal": False,
    }
    assert manifest["admission"] == {
        "ppo": False,
        "assist": False,
        "authority": False,
        "rule_fallback": True,
    }
    assert manifest["d3_bundle"]["expected_policy_version"] == (
        "missing-development-policy"
    )
    assert manifest["d3_bundle"]["expected_manifest_sha256"] == "a" * 64
    assert manifest["d3_bundle"]["loaded"] is False
    assert manifest["d3_treatment_summary"]["applied_count"] == 0
    assert manifest["d3_treatment_summary"]["rule_fallback_count"] == 20
    assert manifest["d3_treatment_summary"]["fallback_reason_counts"]
    assert manifest["d3_treatment_summary"]["safety_shell_version"] == (
        D3_SAFETY_SHELL_VERSION
    )
    assert manifest["d4_treatment_summary"]["safe_adopted_count"] == 0
    assert manifest["d4_treatment_summary"]["rule_fallback_count"] == 20
    assert manifest["d4_treatment_summary"]["rejection_reason_counts"]
    gate_summary = manifest["d4_treatment_summary"]["candidate_gate_summary"]
    assert gate_summary["arm_evidence_schema_versions"] == [
        "d4-region-resource-paired-arm-evidence-v2"
    ]
    assert gate_summary["diagnostics_available_count"] == 20
    assert gate_summary["candidate_considered_count"] == 0
    assert gate_summary["minimum_confidence_values"] == [0.6]
    assert gate_summary["candidate_latency_limit_ms_values"] == [50.0]
    assert gate_summary["candidate_confidence"]["sample_count"] == 0
    assert gate_summary["candidate_confidence"]["mean"] is None
    assert manifest["d4_bundle"]["loaded"] is False
    assert manifest["d4_bundle"]["load_rejection_reasons"]
    assert d4_payload["admission"]["runtime_publication_allowed"] is False
    assert len(lineage) == 20
    assert all(
        json.loads(row)["control_and_treatment_share_source_episode"] is True
        for row in lineage
    )
    assert all(
        len(json.loads(row)["intervention_world_checkpoint_sha256"]) == 64
        for row in lineage
    )
    assert "物理结果、反事实和因果收益均未生成" in paths[
        "report_cn"
    ].read_text(encoding="utf-8")
    report_text = paths["report_cn"].read_text(encoding="utf-8")
    assert D3_SAFETY_SHELL_VERSION in report_text
    assert "候选门诊断" in report_text
    with pytest.raises(FileExistsError):
        write_reserved_seed_intervention_execution(output, execution)

    physical = execute_checkpoint_paired_physical_rollouts(
        execution,
        options=CheckpointPhysicalRolloutOptions(evaluate_with_d6=True),
    )
    assert len(physical.pairs) == 20
    for pair in physical.pairs:
        solve_source = pair.source.d3_planning_frame.previous_plan
        assert solve_source is not None
        formal_authority = pair.source.d3_planning_frame.plan
        for arm in (pair.control, pair.treatment):
            assert arm.plan_payload["plan_id"] != formal_authority.plan_id
            assert arm.plan_payload["plan_version"] == formal_authority.version + 1
            assert arm.plan_payload["previous_plan_id"] == formal_authority.plan_id
            contract = arm.d3_contract_evidence
            assert contract["schema_version"] == (
                "scalable3d-d3-isolated-execution-contract-v1"
            )
            assert contract["isolated_simulation_only"] is True
            assert contract["production_runtime_ack"] is False
            assert contract["plan_payload_sha256"] == arm.plan_payload[
                "d3_validated_plan_payload_sha256"
            ]
            assert contract["plan_conversion"]["execution_plan_id"] == (
                arm.plan_payload["plan_id"]
            )
            assert contract["plan_conversion"]["execution_plan_version"] == (
                arm.plan_payload["plan_version"]
            )
            assert contract["plan_conversion"][
                "offline_solve_source_plan_id"
            ] == solve_source.plan_id
            assert contract["plan_conversion"][
                "formal_authority_plan_id"
            ] == formal_authority.plan_id
            assert contract["plan_consumption"]["plan_payload_sha256"] == (
                contract["plan_payload_sha256"]
            )
    assert all(item.control.control_cycle_count >= 2 for item in physical.pairs)
    assert all(item.treatment.control_cycle_count >= 2 for item in physical.pairs)
    assert all(item.control.world_id != item.treatment.world_id for item in physical.pairs)
    assert all(
        item.control.plan_payload["global_track_id_owner"] == "D2_center"
        and item.treatment.plan_payload["global_track_id_owner"] == "D2_center"
        for item in physical.pairs
    )
    physical_paths = write_checkpoint_paired_physical_rollouts(
        tmp_path / "physical",
        physical,
    )
    physical_manifest = json.loads(
        physical_paths["manifest"].read_text(encoding="utf-8")
    )
    d6_sidecar = json.loads(
        physical_paths["d6_sidecar"].read_text(encoding="utf-8")
    )
    d6_inputs = json.loads(
        physical_paths["input_spec"].read_text(encoding="utf-8")
    )
    first_pair = d6_inputs["pairs"][0]
    for arm_kind in ("control", "treatment"):
        arm_inputs = first_pair["arms"][arm_kind]
        assert "d4_adoption_evidence" in arm_inputs
        arm_manifest = json.loads(
            (
                physical_paths["input_spec"].parent
                / arm_inputs["episode_manifest"]["path"]
            ).read_text(encoding="utf-8")
        )
        assert arm_manifest["arm_artifact_sha256"][
            "d4_adoption_evidence"
        ] == arm_inputs["d4_adoption_evidence"]["sha256"]
    assert physical_manifest["pair_count"] == 20
    expected_commits = sorted(
        {item.source.source_git_commit for item in physical.pairs}
    )
    expected_dirty_count = sum(
        item.source.source_repository_dirty for item in physical.pairs
    )
    assert physical_manifest["source_episode_count"] == 20
    assert physical_manifest["source_git_commits"] == expected_commits
    assert physical_manifest["source_git_commit_uniform"] is (
        len(expected_commits) == 1
    )
    assert physical_manifest["git_commit"] == (
        expected_commits[0] if len(expected_commits) == 1 else None
    )
    assert physical_manifest["dirty_source_episode_count"] == (
        expected_dirty_count
    )
    assert physical_manifest["repository_dirty"] is bool(
        expected_dirty_count
    )
    assert physical_manifest["source_episode_manifest_sha256"] == {
        str(item.seed): item.source.source_episode_manifest_sha256
        for item in physical.pairs
    }
    assert physical_manifest["claim_boundary"]["production_runtime_ack"] is False
    assert d6_sidecar["comparison_scope"] == "paired_isolated_simulation_comparison"
    assert d6_sidecar["audit"]["online_truth_use_count"] == 0
    assert d6_sidecar["pair_results"][0]["arms"]["control"]["availability"][
        "d4_degraded_adoption"
    ]["status"] == "not_applicable"
    with pytest.raises(FileExistsError):
        write_checkpoint_paired_physical_rollouts(tmp_path / "physical", physical)


def test_d3_bundle_binding_is_explicit_and_hash_checked(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    manifest = bundle / "manifest.json"
    manifest.write_text(
        json.dumps({"policy_version": "policy-v1"}, sort_keys=True),
        encoding="utf-8",
    )

    resolved = resolve_d3_development_bundle_binding(bundle)
    assert resolved.bundle_dir == bundle
    assert resolved.policy_version == "policy-v1"
    assert len(resolved.manifest_sha256) == 64

    with pytest.raises(ValueError, match="SHA-256"):
        resolve_d3_development_bundle_binding(
            bundle,
            expected_manifest_sha256="f" * 64,
        )
    with pytest.raises(ValueError, match="policy version"):
        resolve_d3_development_bundle_binding(
            bundle,
            expected_policy_version="policy-v2",
        )


def test_reserved_seed_options_reject_partial_seed_catalog() -> None:
    with pytest.raises(ValueError, match="exactly 1000-1019"):
        ReservedSeedInterventionOptions(reserved_seeds=(1000, 1001))
