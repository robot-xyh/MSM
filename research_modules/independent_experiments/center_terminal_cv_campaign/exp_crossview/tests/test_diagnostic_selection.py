from __future__ import annotations

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.diagnostic_selection import (
    ParameterSet,
    _aggregate_parameter,
    _parameter_grid,
    _selection_key,
)


def _scenario(
    scenario_id: str,
    *,
    precision: float,
    purity: float,
    completeness: float,
    mixed: int = 0,
    false_relations: int = 0,
    unregistered: int = 0,
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "association_precision": precision,
        "target_equal_mean_purity": purity,
        "target_equal_mean_completeness": completeness,
        "mixed_identity_target_count": mixed,
        "false_positive_relations": false_relations,
        "unregistered_opportunity_target_count": unregistered,
        "opportunity_target_count": 10,
        "independently_correct_target_count": 8,
        "elapsed_s": 1.0,
    }


def test_parameter_grid_only_varies_allowed_diagnostic_values() -> None:
    values = _parameter_grid((0.0, 0.8), (0.25,), (0.85, 1.05))
    assert len(values) == 4
    assert {tuple(item.to_dict()) for item in values} == {
        (
            "gnn_probability_threshold",
            "gnn_probability_weight",
            "unmatched_cost",
        )
    }


def test_selection_prioritizes_identity_mixing_then_target_equal_quality() -> None:
    clean = ParameterSet(0.8, 0.45, 1.05)
    mixed = ParameterSet(0.0, 0.45, 1.05)
    clean_record = _aggregate_parameter(
        clean,
        tuple(
            _scenario(name, precision=0.82, purity=0.9, completeness=0.8)
            for name in ("n20_m8", "n20_m30", "n40_m50")
        ),
    )
    mixed_record = _aggregate_parameter(
        mixed,
        tuple(
            _scenario(
                name,
                precision=0.99,
                purity=0.99,
                completeness=0.99,
                mixed=1,
            )
            for name in ("n20_m8", "n20_m30", "n40_m50")
        ),
    )
    selected = min(
        (clean_record, mixed_record),
        key=lambda item: _selection_key(item, has_qualified=True),
    )
    assert selected["parameter_id"] == clean.parameter_id
