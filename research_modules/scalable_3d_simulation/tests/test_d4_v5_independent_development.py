from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from research_modules.scalable_3d_simulation.d4_v5_independent_development import (
    D4V5IndependentDevelopmentOptions,
    _audit_frames,
    _build_development_config,
    _load_and_validate_seed_registry,
    _regional_pattern,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.world import (
    REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class _Snapshot:
    regions: tuple[object, ...]
    edges: tuple[object, ...]


@dataclass(frozen=True)
class _Source:
    value: str


@dataclass(frozen=True)
class _Recommendation:
    source: _Source
    projected: bool = True
    transfers: tuple[object, ...] = ()


@dataclass(frozen=True)
class _Advice:
    recommendation: _Recommendation


@dataclass(frozen=True)
class _Frame:
    snapshot: _Snapshot
    recommendation: _Advice


@dataclass(frozen=True)
class _Availability:
    value: str


@dataclass(frozen=True)
class _Target:
    availability: _Availability
    recommendation: _Recommendation


@dataclass(frozen=True)
class _LearningFrame:
    snapshot: _Snapshot
    target: _Target


def test_options_require_eight_unique_independent_seeds() -> None:
    with pytest.raises(ValueError, match="at least eight unique"):
        D4V5IndependentDevelopmentOptions(
            output_dir="unused",
            seeds=(3000, 3001, 3002),
        )
    with pytest.raises(ValueError, match="20 targets"):
        D4V5IndependentDevelopmentOptions(
            output_dir="unused",
            seeds=tuple(range(3000, 3008)),
            target_count=19,
        )


def test_seed_registry_requires_disjoint_development_class(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": (
                    "scalable3d-d4-v5-independent-development-"
                    "seed-registry-v1"
                ),
                "registry_id": "fixture",
                "training_seeds": [0, 1],
                "formal_holdout_seeds": [1000, 1001],
                "independent_development_seeds": list(range(3000, 3008)),
                "policy": {
                    "all_seed_classes_disjoint": True,
                    "independent_development_fit_allowed": False,
                    "formal_holdout_payload_read_allowed": False,
                    "online_truth_use_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    result = _load_and_validate_seed_registry(
        registry,
        seeds=tuple(range(3000, 3008)),
    )
    assert result["requested_seeds"] == list(range(3000, 3008))
    with pytest.raises(ValueError, match="independent development"):
        _load_and_validate_seed_registry(
            registry,
            seeds=(3000, 3001, 3002, 3003, 3004, 3005, 3006, 1000),
        )


def test_seed_registry_rejects_overlapping_classes(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": (
                    "scalable3d-d4-v5-independent-development-"
                    "seed-registry-v1"
                ),
                "registry_id": "bad",
                "training_seeds": [0, 1],
                "formal_holdout_seeds": [1000],
                "independent_development_seeds": [
                    0,
                    3001,
                    3002,
                    3003,
                    3004,
                    3005,
                    3006,
                    3007
                ],
                "policy": {
                    "all_seed_classes_disjoint": True,
                    "independent_development_fit_allowed": False,
                    "formal_holdout_payload_read_allowed": False,
                    "online_truth_use_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be disjoint"):
        _load_and_validate_seed_registry(
            registry,
            seeds=(0, 3001, 3002, 3003, 3004, 3005, 3006, 3007),
        )


def test_regional_patterns_preserve_inventory_and_rotate() -> None:
    patterns = [_regional_pattern(seed) for seed in range(3000, 3040)]
    assert len(set(patterns)) >= 16
    for targets, resources in patterns:
        assert len(targets) == 8
        assert len(resources) == 8
        assert sum(targets) == 20
        assert sum(resources) == 20
        assert any(t > r for t, r in zip(targets, resources, strict=True))
        assert any(t < r for t, r in zip(targets, resources, strict=True))


def test_build_config_marks_nonformal_no_fit_and_regional_probe() -> None:
    options = D4V5IndependentDevelopmentOptions(
        output_dir="unused",
        seeds=tuple(range(3000, 3008)),
    )
    config = _build_development_config(
        ScenarioConfig(),
        options=options,
        seed=3003,
        scenario_family="dense_crossing",
    )
    probe = config.metadata["regional_resource_probe"]
    assert config.target_count == 20
    assert config.resource_count == 20
    assert config.recon_count == 2
    assert config.region_count == 8
    assert config.seed == 3003
    assert config.metadata["development_data_class"] == (
        "independent_nonformal_no_fit"
    )
    assert config.metadata["model_fit_allowed"] is False
    assert config.metadata["formal_holdout"] is False
    assert config.metadata["regional_resource_locality_enforced"] is False
    assert config.metadata["regional_probe_layout_only"] is True
    assert probe["schema"] == REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION
    assert sum(probe["target_counts_by_region"]) == 20
    assert sum(probe["resource_counts_by_region"]) == 20


def test_frame_audit_requires_rule_labels_and_region_scope() -> None:
    recommendation = _Recommendation(_Source("rule"))
    frames = (
        _Frame(
            snapshot=_Snapshot(tuple(object() for _ in range(8)), (object(),)),
            recommendation=_Advice(recommendation),
        ),
        _Frame(
            snapshot=_Snapshot(tuple(object() for _ in range(8)), ()),
            recommendation=_Advice(recommendation),
        ),
    )
    learning_frames = tuple(
        _LearningFrame(
            snapshot=frame.snapshot,
            target=_Target(_Availability("available"), recommendation),
        )
        for frame in frames
    )
    audit = _audit_frames(
        frames,
        learning_frames=learning_frames,
        expected_region_count=8,
    )
    assert audit == {
        "frame_count": 2,
        "region_record_count": 16,
        "edge_record_count": 1,
        "safe_rule_target_frame_count": 2,
        "runtime_recommendation_frame_count": 2,
        "runtime_rule_recommendation_frame_count": 2,
        "blocked_runtime_region_record_count": 0,
        "rule_target_transfer_count": 0,
    }
    with pytest.raises(RuntimeError, match="region count"):
        _audit_frames(
            frames,
            learning_frames=learning_frames,
            expected_region_count=7,
        )
