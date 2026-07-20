from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.experiment_matrix import (
    EXPERIMENT_VARIANTS,
    ExperimentMatrixPlan,
    ModelBundlePaths,
    _validate_resolved_variant,
    load_training_seeds,
    runtime_options_for_variant,
    validate_required_bundles,
)


def test_matrix_cells_keep_comparable_keys_and_scope_f1() -> None:
    plan = ExperimentMatrixPlan(
        variants=("R0", "C1", "F1"),
        scenarios=("nominal", "center_failure", "secondary_failure"),
        scales=(5, 20),
        seeds=(11, 12),
        duration_s=1.0,
    )
    cells = plan.cells()
    assert len(cells) == 32
    f1 = [item for item in cells if item.variant == "F1"]
    assert {item.scenario for item in f1} == {"center_failure", "secondary_failure"}
    assert len({item.comparison_key for item in cells if item.variant == "R0"}) == 12


def test_formal_plan_requires_all_variants_twenty_unseen_and_full_scenarios() -> None:
    scenarios = (
        "nominal",
        "dense_crossing",
        "formation_split",
        "evasive_multilevel",
        "delayed_noisy",
        "communication_degraded",
        "center_failure",
        "secondary_failure",
        "high_threat_m_to_n",
    )
    with pytest.raises(ValueError, match="at least 20"):
        ExperimentMatrixPlan(
            variants=EXPERIMENT_VARIANTS,
            scenarios=scenarios,
            scales=(5, 20, 50, 100, 200),
            seeds=tuple(range(19)),
            duration_s=1.0,
            formal=True,
            training_seeds=frozenset(range(100, 110)),
        )
    with pytest.raises(ValueError, match="overlap training"):
        ExperimentMatrixPlan(
            variants=EXPERIMENT_VARIANTS,
            scenarios=scenarios,
            scales=(5, 20, 50, 100, 200),
            seeds=tuple(range(20, 40)),
            duration_s=1.0,
            formal=True,
            training_seeds=frozenset({25}),
        )

    with pytest.raises(ValueError, match="training seed registry"):
        ExperimentMatrixPlan(
            variants=EXPERIMENT_VARIANTS,
            scenarios=scenarios,
            scales=(5, 20, 50, 100, 200),
            seeds=tuple(range(20, 40)),
            duration_s=1.0,
            formal=True,
        )


def test_training_seed_registry_accepts_group_records_and_rejects_invalid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "seeds.json"
    path.write_text(
        json.dumps(
            {"seed_groups": [{"scenario_version": "a", "seed": 3}, {"seed": 9}]}
        ),
        encoding="utf-8",
    )
    assert load_training_seeds(path) == frozenset({3, 9})
    path.write_text(json.dumps({"training_seeds": [True]}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integers"):
        load_training_seeds(path)


def test_variant_options_are_explicit_and_required_bundles_fail_closed(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    bundles = ModelBundlePaths(
        d3=bundle, d4=bundle, d5_graph=bundle, d5_active_vision=bundle
    )
    options = runtime_options_for_variant("C1", bundles, device="cpu")
    assert options.d3_mode == "assist"
    assert options.d4_mode == "assist"
    assert options.d5_bundle_dir == bundle
    assert options.d5_active_vision_mode == "assist"
    validate_required_bundles(("C1",), bundles)
    with pytest.raises(ValueError, match="D5 graph"):
        validate_required_bundles(("G1",), ModelBundlePaths())


def test_declared_learning_variant_cannot_silently_be_rule_fallback() -> None:
    diagnostics = {
        "d3": {
            "bundle_loaded": True,
            "effective_mode": "rule_fallback",
        }
    }
    with pytest.raises(RuntimeError, match="did not resolve"):
        _validate_resolved_variant("A1", diagnostics, allow_rule_fallback=False)
    _validate_resolved_variant("A1", diagnostics, allow_rule_fallback=True)
