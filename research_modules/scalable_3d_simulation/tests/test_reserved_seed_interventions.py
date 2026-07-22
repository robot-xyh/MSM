from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    D3DevelopmentBundleBinding,
    RESERVED_EVALUATION_SEEDS,
    RESERVED_SEED_INTERVENTION_SCHEMA_VERSION,
    ReservedSeedInterventionOptions,
    execute_reserved_seed_interventions,
    resolve_d3_development_bundle_binding,
    write_reserved_seed_intervention_execution,
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
    assert manifest["d4_treatment_summary"]["safe_adopted_count"] == 0
    assert manifest["d4_treatment_summary"]["rule_fallback_count"] == 20
    assert manifest["d4_treatment_summary"]["rejection_reason_counts"]
    assert manifest["d4_bundle"]["loaded"] is False
    assert manifest["d4_bundle"]["load_rejection_reasons"]
    assert d4_payload["admission"]["runtime_publication_allowed"] is False
    assert len(lineage) == 20
    assert all(
        json.loads(row)["control_and_treatment_share_source_episode"] is True
        for row in lineage
    )
    assert "物理结果、反事实和因果收益均未生成" in paths[
        "report_cn"
    ].read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_reserved_seed_intervention_execution(output, execution)


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
