from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from research_modules.scalable_3d_simulation.d4_readiness_supplement import (
    D4ReadinessSupplementOptions,
    _audit_d4_frames,
    _build_supplement_config,
    _load_and_validate_seed_registry,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig


@dataclass(frozen=True)
class _Region:
    secondary_readiness: float


@dataclass(frozen=True)
class _Snapshot:
    regions: tuple[_Region, ...]


@dataclass(frozen=True)
class _Source:
    value: str


@dataclass(frozen=True)
class _Recommendation:
    source: _Source


@dataclass(frozen=True)
class _Advice:
    recommendation: _Recommendation


@dataclass(frozen=True)
class _Frame:
    snapshot: _Snapshot
    recommendation: _Advice


def test_options_require_unique_training_catalog_size() -> None:
    with pytest.raises(ValueError, match="at least three unique"):
        D4ReadinessSupplementOptions(
            output_dir="unused",
            seeds=(0, 0, 1),
        )


def test_seed_registry_rejects_reserved_or_undeclared_seed(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "training_seeds": [0, 1, 2],
                "evaluation_seeds": [1000, 1001],
            }
        ),
        encoding="utf-8",
    )

    assert _load_and_validate_seed_registry(
        registry,
        seeds=(0, 1, 2),
    )["training_seeds"] == (0, 1, 2)
    with pytest.raises(ValueError, match="declared training seeds"):
        _load_and_validate_seed_registry(
            registry,
            seeds=(0, 1, 1000),
        )


def test_build_config_preserves_runtime_scale_without_synthetic_expansion() -> None:
    options = D4ReadinessSupplementOptions(
        output_dir="unused",
        seeds=(0, 1, 2),
    )
    config = _build_supplement_config(
        ScenarioConfig(),
        options=options,
        seed=2,
    )

    assert config.target_count == 20
    assert config.resource_count == 20
    assert config.recon_count == 2
    assert config.region_count == 8
    assert config.duration_s == 1.2
    assert config.seed == 2
    assert config.metadata["synthetic_feature_expansion"] is False


def test_frame_audit_counts_authentic_readiness_and_rule_targets() -> None:
    frames = (
        _Frame(
            snapshot=_Snapshot((_Region(0.0), _Region(1.0))),
            recommendation=_Advice(_Recommendation(_Source("rule"))),
        ),
        _Frame(
            snapshot=_Snapshot((_Region(0.0), _Region(0.0))),
            recommendation=_Advice(_Recommendation(_Source("rule"))),
        ),
    )

    audit = _audit_d4_frames(frames, expected_region_count=2)

    assert audit["frame_count"] == 2
    assert audit["region_value_count"] == 4
    assert audit["zero_value_count"] == 3
    assert audit["positive_value_count"] == 1
    assert audit["zero_value_fraction"] == 0.75
    assert audit["rule_target_frame_count"] == 2


def test_frame_audit_rejects_region_scope_mismatch() -> None:
    frames = (
        _Frame(
            snapshot=_Snapshot((_Region(0.0),)),
            recommendation=_Advice(_Recommendation(_Source("rule"))),
        ),
    )
    with pytest.raises(RuntimeError, match="region count"):
        _audit_d4_frames(frames, expected_region_count=2)
