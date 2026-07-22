from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    CONTROL_ARM,
    CONTROL_PLANNER_PATH,
    D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
    D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1,
    D6_SIDECAR_OWNER,
    EDGE_FEATURE_NAMES,
    OFFLINE_INTERVENTION_SCOPE,
    PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    SHADOW_EVALUATION_SCHEMA_V2,
    TREATMENT_ARM,
    TREATMENT_PLANNER_PATH,
    AssignmentPlanner,
    PairedInterventionArmSpecification,
    PairedInterventionContractError,
    PairedInterventionSeedPair,
    PairedInterventionSpecification,
    PlannerConfig,
    ResourceState,
    SharedEdgeActorCriticPolicy,
    TargetTrack,
    canonical_planning_frame_snapshot_sha256,
    development_shadow_admission,
    execute_offline_paired_intervention,
    load_model_bundle,
    save_model_bundle,
    write_offline_paired_intervention_execution,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _bundle(
    path: Path,
    *,
    deadline_s: float = 1.0,
    normalization_mean: float = 0.0,
    normalization_scale: float = 1.0,
) -> None:
    torch = pytest.importorskip("torch")
    torch.manual_seed(7)
    save_model_bundle(
        path,
        SharedEdgeActorCriticPolicy(hidden_size=8),
        split_hash="1" * 64,
        dataset_frames_sha256="2" * 64,
        normalization_mean=np.full(
            len(EDGE_FEATURE_NAMES), normalization_mean, dtype=float
        ),
        normalization_scale=np.full(
            len(EDGE_FEATURE_NAMES), normalization_scale, dtype=float
        ),
        training_results={"stage": "development_unit_fixture"},
        deadline_s=deadline_s,
        min_confidence=0.0,
        provenance={
            "repository_git_commit": "a" * 40,
            "repository_git_commit_role": "exact_training_source_commit",
            "training_worktree_state": "clean",
            "training_source_sha256": "3" * 64,
            "dataset_manifest_sha256": "4" * 64,
            "training_entrypoint": "unit_fixture",
            "training_date": "2026-07-21",
        },
        admission=development_shadow_admission(
            PAIRED_INTERVENTION_RESERVED_SEEDS_V1
        ),
        promotion_unavailable_reason="reserved_seed_evaluation_pending",
    )


def _planning_frames(
    config: PlannerConfig,
) -> dict[int, object]:
    frames = {}
    for offset, seed in enumerate(PAIRED_INTERVENTION_RESERVED_SEEDS_V1):
        planner = AssignmentPlanner(config=config)
        tracks = (
            TargetTrack(
                f"global-track-{seed}-a",
                threat_score=0.9,
                covariance=0.1 + offset * 0.001,
                window_cost=0.0,
                fov_difficulty_by_resource={
                    f"resource-{seed}-a": 0.0,
                    f"resource-{seed}-b": 0.8,
                },
            ),
            TargetTrack(
                f"global-track-{seed}-b",
                threat_score=0.6,
                covariance=0.2,
                window_cost=0.0,
                fov_difficulty_by_resource={
                    f"resource-{seed}-a": 0.8,
                    f"resource-{seed}-b": 0.0,
                },
            ),
        )
        resources = (
            ResourceState(f"resource-{seed}-a"),
            ResourceState(f"resource-{seed}-b"),
        )
        previous = planner.plan(tracks, resources, timestamp=10.0)
        planner.plan(
            tracks,
            resources,
            timestamp=12.0,
            previous_plan=previous,
            expected_previous_version=previous.version,
        )
        frames[seed] = planner.latest_planning_evidence
    return frames


def _specification(
    *,
    bundle_dir: Path,
    frames: dict[int, object],
    manifest_sha256: str | None = None,
    policy_version: str | None = None,
) -> PairedInterventionSpecification:
    raw = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    bundle_sha = manifest_sha256 or _file_digest(bundle_dir / "manifest.json")
    bundle_version = policy_version or str(raw["policy_version"])
    pairs = []
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        frame = frames[seed]
        assert frame.previous_plan is not None
        common = {
            "seed": seed,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "scenario_version": "scalable3d-d3-reserved-unit-v1",
            "scenario_config_sha256": _digest(f"scenario-{seed}"),
            "initial_world_state_sha256": _digest(f"world-{seed}"),
            "observation_input_snapshot_sha256": (
                canonical_planning_frame_snapshot_sha256(frame)
            ),
            "input_snapshot_schema_version": frame.schema_version,
            "d1_d2_lineage_contract_version": "d1-d2-lineage-v1",
            "d1_d2_lineage_contract_sha256": _digest("d1-d2-lineage"),
            "rule_cost_profile_version": "d3-rule-cost-v1",
            "rule_cost_config_sha256": _digest("rule-cost-config"),
            "d3_bundle_version": bundle_version,
            "d3_bundle_sha256": bundle_sha,
            "d3_bundle_frozen": True,
            "threshold_version": "d3-threshold-v1",
            "threshold_config_sha256": _digest("threshold-config"),
            "threshold_frozen": True,
            "safety_shell_version": "d3-safety-shell-v1",
            "safety_shell_config_sha256": _digest("safety-shell"),
            "source_plan_id": frame.previous_plan.plan_id,
            "source_plan_version": frame.previous_plan.version,
            "expected_previous_plan_version": frame.previous_plan.version,
            "current_plan_version": frame.previous_plan.version,
            "source_plan_created_at_s": frame.previous_plan.created_at,
            "intervention_timestamp_s": frame.timestamp_s,
            "plan_valid_until_s": 15.0,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "rule_fallback_enabled": True,
        }
        control = PairedInterventionArmSpecification(
            arm_id=f"d3-{seed}-control",
            arm_kind=CONTROL_ARM,
            isolation_id=f"world-{seed}-control",
            planner_path=CONTROL_PLANNER_PATH,
            learning_cost_intervention_enabled=False,
            **common,
        )
        treatment = PairedInterventionArmSpecification(
            arm_id=f"d3-{seed}-treatment",
            arm_kind=TREATMENT_ARM,
            isolation_id=f"world-{seed}-treatment",
            planner_path=TREATMENT_PLANNER_PATH,
            learning_cost_intervention_enabled=True,
            **common,
        )
        pairs.append(
            PairedInterventionSeedPair(
                pair_id=f"d3-pair-{seed}",
                seed=seed,
                control=control,
                treatment=treatment,
            )
        )
    return PairedInterventionSpecification(
        experiment_id="d3-reserved-unit",
        experiment_version="d3-reserved-unit-v1",
        reserved_seed_policy_version=PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
        reserved_seeds=PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        runtime_ack_evidence_schema_version=D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
        runtime_reward_evidence_schema_version=(
            D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1
        ),
        d6_sidecar_owner=D6_SIDECAR_OWNER,
        ppo_enabled=False,
        online_assist_enabled=False,
        online_authority_enabled=False,
        rule_fallback_enabled=True,
        pairs=tuple(pairs),
    )


def test_reserved_seed_execution_creates_real_shared_report_receipts(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )
    output = tmp_path / "execution.json"
    write_offline_paired_intervention_execution(output, result)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result.bundle_loaded is True
    assert len(result.arms) == 40
    assert result.paired_evaluator_report.frame_count == 20
    assert result.paired_evaluator_report.unseen_seed_count == 20
    assert len(result.manifest.execution_receipts) == 40
    assert {
        item.receipt.paired_evaluator_report_sha256 for item in result.arms
    } == {result.paired_evaluator_report_sha256}
    assert all(
        item.learning_cost_applied
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )
    assert all(
        item.plan.metadata["learning_bundle_loaded_for_offline_intervention"]
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )
    assert all(
        not item.learning_cost_applied
        for item in result.arms
        if item.arm_specification.arm_kind == CONTROL_ARM
    )
    assert all(
        not item.plan.metadata["learning_bundle_loaded_for_offline_intervention"]
        for item in result.arms
        if item.arm_specification.arm_kind == CONTROL_ARM
    )
    assert result.runtime_ack_available is False
    assert result.outcome_available is False
    assert result.counterfactual_available is False
    assert result.causal_available is False
    assert payload["admission"]["online_assist_enabled"] is False
    assert payload["admission"]["online_authority_enabled"] is False
    assert payload["evidence_availability"] == {
        "runtime_ack": False,
        "outcome": False,
        "counterfactual": False,
        "causal": False,
    }
    assert "truth" not in output.read_text(encoding="utf-8").lower()
    assert load_model_bundle(bundle_dir, mode="assist").fallback_reason == (
        "bundle_shadow_only"
    )


@pytest.mark.parametrize(
    ("spec_overrides", "expected_reason"),
    (
        ({"manifest_sha256": "f" * 64}, "bundle_manifest_sha256_mismatch"),
        ({"policy_version": "wrong-policy-version"}, "bundle_policy_version_mismatch"),
    ),
)
def test_bundle_identity_failure_returns_rule_fallback_receipts(
    tmp_path: Path,
    spec_overrides: dict[str, str],
    expected_reason: str,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(
        bundle_dir=bundle_dir,
        frames=frames,
        **spec_overrides,
    )

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )

    treatment = tuple(
        item
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )
    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == expected_reason
    assert all(item.rule_fallback_applied for item in treatment)
    assert all(item.fallback_reason == expected_reason for item in treatment)
    assert all(not item.learning_cost_applied for item in treatment)
    assert all(
        not item.plan.metadata["learning_bundle_loaded_for_offline_intervention"]
        for item in treatment
    )
    assert result.manifest.availability[
        "treatment_safely_applied_in_isolated_simulation"
    ]["value"] is False


@pytest.mark.parametrize(
    ("deadline_s", "mean", "scale", "expected_reason"),
    (
        (1.0e-12, 0.0, 1.0, "model_timeout"),
        (1.0, 100.0, 1.0e-3, "out_of_distribution"),
    ),
)
def test_runtime_guard_failure_falls_back_without_changing_rule_matrix(
    tmp_path: Path,
    deadline_s: float,
    mean: float,
    scale: float,
    expected_reason: str,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(
        bundle_dir,
        deadline_s=deadline_s,
        normalization_mean=mean,
        normalization_scale=scale,
    )
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )

    by_seed_and_arm = {
        (item.arm_specification.seed, item.arm_specification.arm_kind): item
        for item in result.arms
    }
    assert result.bundle_loaded is True
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        control = by_seed_and_arm[(seed, CONTROL_ARM)]
        treatment = by_seed_and_arm[(seed, TREATMENT_ARM)]
        assert treatment.fallback_reason == expected_reason
        assert treatment.rule_fallback_applied is True
        assert treatment.learning_cost_applied is False
        assert (
            treatment.plan.metadata[
                "learning_bundle_loaded_for_offline_intervention"
            ]
            is True
        )
        assert (
            treatment.plan.metadata["learning_cost_intervention_applied"]
            is False
        )
        assert treatment.plan.assignment_signature() == control.plan.assignment_signature()
        assert treatment.receipt.rule_cost_matrix_sha256 == (
            control.receipt.rule_cost_matrix_sha256
        )
        assert treatment.receipt.action_mask_sha256 == (
            control.receipt.action_mask_sha256
        )


def test_nonfinite_frozen_weights_are_rejected_before_inference(
    tmp_path: Path,
) -> None:
    torch = pytest.importorskip("torch")
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    state_path = bundle_dir / "state_dict.pt"
    state = torch.load(state_path, map_location="cpu", weights_only=True)
    first = next(iter(state))
    state[first] = torch.full_like(state[first], float("nan"))
    torch.save(state, state_path)
    raw = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    state_sha = _file_digest(state_path)
    raw["state_dict"]["sha256"] = state_sha
    raw["promotion_manifest"]["model_state_dict_sha256"] = state_sha
    (bundle_dir / "manifest.json").write_text(
        json.dumps(raw, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )

    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == "model_state_nonfinite"
    assert all(
        item.fallback_reason == "model_state_nonfinite"
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )


def test_input_snapshot_mismatch_fails_before_any_receipt(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)
    first = specification.pairs[0]
    wrong_hash = "e" * 64
    wrong_pair = replace(
        first,
        control=replace(
            first.control,
            observation_input_snapshot_sha256=wrong_hash,
        ),
        treatment=replace(
            first.treatment,
            observation_input_snapshot_sha256=wrong_hash,
        ),
    )
    bad = replace(specification, pairs=(wrong_pair, *specification.pairs[1:]))

    with pytest.raises(PairedInterventionContractError) as captured:
        execute_offline_paired_intervention(
            bad,
            frames,
            bundle_dir=bundle_dir,
            planner_config=config,
        )

    assert captured.value.code == "offline_execution_input_snapshot_sha256_mismatch"
