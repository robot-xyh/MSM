from __future__ import annotations

import csv
import json
from pathlib import Path
from time import sleep

import numpy as np
import pytest

from d3_assignment_planner import (
    CostWeights,
    LearningAssistConfig,
    LearningCostAssistant,
    MultiCycleShadowBundle,
    MultiCycleShadowError,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    ResidualPrediction,
    build_multi_cycle_shadow_scenarios,
    evaluate_multi_cycle_shadow,
    load_multi_cycle_shadow_bundle,
    write_multi_cycle_shadow_artifacts,
)
from d3_assignment_planner.learning import FeatureDistributionGuard


class _PreviousBindingPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        previous = np.asarray(features, dtype=float)[:, 11] > 0.5
        return ResidualPrediction(
            delta_costs=np.where(previous, -2.0, 2.0),
            confidence=np.ones(len(features), dtype=float),
        )


class _ErrorPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        del features
        raise RuntimeError("controlled model failure")


class _SlowPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        sleep(0.002)
        return ResidualPrediction(
            delta_costs=np.zeros(len(features), dtype=float),
            confidence=1.0,
        )


class _CountingPredictor:
    def __init__(self) -> None:
        self.call_count = 0

    def predict(self, features: np.ndarray) -> ResidualPrediction:
        self.call_count += 1
        return ResidualPrediction(
            delta_costs=np.zeros(len(features), dtype=float),
            confidence=1.0,
        )


def _boundary_only(seed: int):
    return (build_multi_cycle_shadow_scenarios(seed)[0],)


def _assistant(
    predictor,
    *,
    timeout_s: float = 1.0,
    guard: FeatureDistributionGuard | None = None,
) -> LearningCostAssistant:
    return LearningCostAssistant(
        predictor,
        config=LearningAssistConfig(
            mode="assist",
            alpha=0.25,
            timeout_s=timeout_s,
            min_confidence=0.0,
            ood_z_threshold=6.0,
        ),
        distribution_guard=guard,
    )


def test_scenario_catalog_covers_all_required_multi_cycle_events() -> None:
    scenarios = build_multi_cycle_shadow_scenarios(1000)
    by_id = {item.scenario_id: item for item in scenarios}

    assert set(by_id) == {
        "hungarian_switch_boundary",
        "five_resources_three_targets",
        "three_resources_five_targets",
        "resource_failure",
        "target_add_remove",
        "m_to_n_demand_change",
    }
    assert len(by_id["hungarian_switch_boundary"].steps) == 6
    assert {
        (len(step.resources), len(step.tracks))
        for step in by_id["five_resources_three_targets"].steps
    } == {(5, 3)}
    assert {
        (len(step.resources), len(step.tracks))
        for step in by_id["three_resources_five_targets"].steps
    } == {(3, 5)}
    assert "resource_failure" in {
        step.event_type for step in by_id["resource_failure"].steps
    }
    assert {"target_added", "target_removed"}.issubset(
        {step.event_type for step in by_id["target_add_remove"].steps}
    )
    demand_steps = by_id["m_to_n_demand_change"].steps
    assert demand_steps[0].tracks[0].effective_demand.required_resource_count == 1
    assert demand_steps[2].tracks[0].effective_demand.required_resource_count == 3
    assert demand_steps[4].tracks[0].effective_demand.required_resource_count == 1
    assert all(
        len({step.snapshot_sha256 for step in scenario.steps})
        == len(scenario.steps)
        for scenario in scenarios
    )


def test_multi_cycle_pair_is_identifiable_without_opening_authority() -> None:
    result = evaluate_multi_cycle_shadow(
        seeds=(1000, 1001),
        training_seeds=tuple(range(100)),
        treatment_assistant=_assistant(_PreviousBindingPredictor()),
    )
    summary = result.summary

    assert summary["seed_contract"]["training_reserved_overlap_count"] == 0
    assert summary["coverage"]["scenario_count"] == 6
    assert summary["coverage"]["boundary_binding_difference_seed_count"] == 2
    assert summary["coverage"]["binding_difference_cycle_count"] > 0
    assert summary["coverage"]["cost_matrix_changed_cycle_count"] > 0
    assert summary["pairing"]["paired_rule_matrix_mismatch_count"] == 0
    assert summary["pairing"]["online_truth_use_count"] == 0
    assert summary["safety"]["duplicate_resource_count"] == 0
    assert summary["safety"]["hard_constraint_violation_count"] == 0
    assert summary["safety"]["stale_version_adoption_count"] == 0
    assert summary["admission"] == {
        "promotion_recommended": False,
        "assist_authorized": False,
        "online_authority_authorized": False,
        "ppo_enabled": False,
        "runtime_publication_allowed": False,
        "rule_fallback_required": True,
        "conclusion": "binding_difference_observed_shadow_only",
    }
    assert all(item.online_truth_use_count == 0 for item in result.cycles)
    assert all(not item.ppo_enabled for item in result.cycles)
    assert all(not item.online_assist_enabled for item in result.cycles)
    assert all(not item.online_authority_enabled for item in result.cycles)
    assert all(not item.runtime_publication_allowed for item in result.cycles)

    advanced = tuple(
        item
        for item in result.cycles
        if item.rule_lineage_state == "advanced"
    )
    assert advanced
    assert all(
        item.rule_declared_previous_plan_token
        == item.rule_input_previous_plan_token
        for item in advanced
    )


def test_custom_cost_weights_apply_to_both_paired_planners() -> None:
    result = evaluate_multi_cycle_shadow(
        seeds=(1000,),
        training_seeds=(0, 1),
        treatment_assistant=_assistant(_PreviousBindingPredictor()),
        scenario_factory=_boundary_only,
        cost_weights=CostWeights(
            window=0.0,
            covariance=0.0,
            threat=0.0,
            resource_state=0.0,
            fov=0.0,
            conflict=0.0,
            reachability_3d=0.0,
            region=0.0,
        ),
    )

    assert all(item.paired_rule_matrix_equal for item in result.cycles)
    assert all(item.rule_cost_on_rule_matrix == 0.0 for item in result.cycles)


@pytest.mark.parametrize(
    ("assistant_factory", "expected_reason"),
    (
        (
            lambda: _assistant(_ErrorPredictor()),
            "model_error",
        ),
        (
            lambda: _assistant(_SlowPredictor(), timeout_s=1.0e-6),
            "model_timeout",
        ),
    ),
)
def test_model_failure_and_timeout_fall_back_to_exact_rule_matrix(
    assistant_factory,
    expected_reason: str,
) -> None:
    result = evaluate_multi_cycle_shadow(
        seeds=(1000,),
        training_seeds=(0, 1),
        treatment_assistant=assistant_factory(),
        scenario_factory=_boundary_only,
    )

    assert result.summary["learning"]["fallback_reasons"] == {
        expected_reason: 6
    }
    assert result.summary["pairing"]["fallback_exact_rule_matrix"] is True
    assert result.summary["coverage"]["cost_matrix_changed_cycle_count"] == 0
    assert result.summary["coverage"]["binding_difference_cycle_count"] == 0
    assert all(
        item.treatment_fallback_exact_rule_matrix for item in result.cycles
    )


def test_ood_falls_back_before_predictor_and_keeps_exact_rule_matrix() -> None:
    predictor = _CountingPredictor()
    guard = FeatureDistributionGuard.fit(
        np.zeros((8, 12), dtype=np.float32)
    )
    result = evaluate_multi_cycle_shadow(
        seeds=(1000,),
        training_seeds=(0,),
        treatment_assistant=_assistant(predictor, guard=guard),
        scenario_factory=_boundary_only,
    )

    assert predictor.call_count == 0
    assert result.summary["learning"]["fallback_reasons"] == {
        "out_of_distribution": 6
    }
    assert result.summary["coverage"]["cost_matrix_changed_cycle_count"] == 0
    assert result.summary["pairing"]["fallback_exact_rule_matrix"] is True


def test_training_seed_overlap_fails_before_planning() -> None:
    with pytest.raises(MultiCycleShadowError) as captured:
        evaluate_multi_cycle_shadow(
            seeds=(1000,),
            training_seeds=(7, 1000),
            treatment_assistant=_assistant(_PreviousBindingPredictor()),
            scenario_factory=_boundary_only,
        )

    assert captured.value.code == "reserved_training_seed_overlap"


def test_missing_bundle_returns_explicit_rule_fallback(tmp_path: Path) -> None:
    bundle = load_multi_cycle_shadow_bundle(
        tmp_path / "missing",
        reserved_seeds=PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    )

    assert bundle.loaded is False
    assert bundle.fallback_reason is not None
    assert bundle.manifest_sha256 is None
    assert bundle.state_dict_sha256 is None


def test_writer_emits_json_csv_and_chinese_report(tmp_path: Path) -> None:
    bundle = MultiCycleShadowBundle(
        assistant=_assistant(_PreviousBindingPredictor()),
        loaded=True,
        fallback_reason=None,
        manifest_sha256="1" * 64,
        state_dict_sha256="2" * 64,
        policy_version="unit-policy",
        dataset_frames_sha256="3" * 64,
        training_split_hash="4" * 64,
    )
    result = evaluate_multi_cycle_shadow(
        seeds=(1000,),
        training_seeds=(0, 1),
        training_seed_registry_sha256="5" * 64,
        treatment_assistant=bundle.assistant,
        bundle=bundle,
        scenario_factory=_boundary_only,
    )
    paths = write_multi_cycle_shadow_artifacts(tmp_path, result)

    assert set(paths) == {
        "summary_json",
        "per_seed_json",
        "per_seed_csv",
        "cycle_csv",
        "report_cn",
    }
    payload = json.loads(paths["summary_json"].read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "completed_shadow_only"
    assert payload["summary"]["admission"]["promotion_recommended"] is False
    with paths["per_seed_csv"].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["seed"] == "1000"
    assert b"\r\n" not in paths["per_seed_csv"].read_bytes()
    assert paths["per_seed_csv"].read_bytes().endswith(b"\n")
    with paths["cycle_csv"].open(encoding="utf-8", newline="") as stream:
        cycle_rows = list(csv.DictReader(stream))
    assert len(cycle_rows) == 6
    assert b"\r\n" not in paths["cycle_csv"].read_bytes()
    assert paths["cycle_csv"].read_bytes().endswith(b"\n")
    report = paths["report_cn"].read_text(encoding="utf-8")
    assert "D3 多周期行为克隆残差影子评估" in report
    assert "shadow-only" in report
    assert "不证明收益" in report
