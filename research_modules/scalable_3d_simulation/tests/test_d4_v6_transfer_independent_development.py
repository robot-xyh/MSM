from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.d4_v6_transfer_independent_development import (
    DEFAULT_CONFIG,
    DEFAULT_SEED_REGISTRY,
    D4V6TransferIndependentDevelopmentOptions,
    _build_development_config,
    _load_and_validate_seed_registry,
    _regional_pattern,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig


def test_seed_registry_is_disjoint_and_rejects_prior_evaluation() -> None:
    payload = _load_and_validate_seed_registry(
        DEFAULT_SEED_REGISTRY,
        seeds=tuple(range(4016, 4080)),
    )
    assert payload["requested_seeds"] == list(range(4016, 4080))
    assert set(payload["prior_design_and_evaluation_seeds"]) == set(
        range(3000, 3040)
    )
    with pytest.raises(ValueError, match="independent development"):
        _load_and_validate_seed_registry(
            DEFAULT_SEED_REGISTRY,
            seeds=(3008, *range(4016, 4023)),
        )
    with pytest.raises(ValueError, match="independent development"):
        _load_and_validate_seed_registry(
            DEFAULT_SEED_REGISTRY,
            seeds=(1000, *range(4016, 4023)),
        )


def test_sixty_four_seeds_cover_distinct_donor_receiver_layouts() -> None:
    patterns = [_regional_pattern(seed) for seed in range(4016, 4080)]
    assert len(set(patterns)) == 64
    for targets, resources in patterns:
        assert sum(targets) == 16
        assert sum(resources) == 24
        assert min(targets) > 0
        assert min(resources) > 0
        assert any(t > r for t, r in zip(targets, resources, strict=True))
        assert any(t < r for t, r in zip(targets, resources, strict=True))


def test_development_config_is_model_free_and_truth_free(tmp_path: Path) -> None:
    options = D4V6TransferIndependentDevelopmentOptions(
        output_dir=tmp_path / "output",
        seeds=tuple(range(4016, 4024)),
    )
    base = ScenarioConfig.from_dict(
        json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    )
    config = _build_development_config(
        base,
        options=options,
        seed=4016,
        scenario_family="nominal",
    )
    assert config.target_count == 16
    assert config.resource_count == 24
    assert config.region_count == 8
    assert config.metadata["online_truth_policy"] == "forbidden"
    assert config.metadata["model_fit_allowed"] is False
    assert config.metadata["formal_holdout"] is False
    assert config.metadata["regional_resource_locality_enforced"] is False
    assert config.metadata["resource_surplus_design"][
        "prior_evaluation_reuse_allowed"
    ] is False


def test_options_reject_wrong_scale_and_too_few_seeds(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="eight unique seeds"):
        D4V6TransferIndependentDevelopmentOptions(
            output_dir=tmp_path / "output",
            seeds=(4016, 4017),
        )
    with pytest.raises(ValueError, match="requires M16N24"):
        D4V6TransferIndependentDevelopmentOptions(
            output_dir=tmp_path / "output",
            seeds=tuple(range(4016, 4024)),
            resource_count=20,
        )
