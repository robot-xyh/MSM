from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from pathlib import Path

import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.association import (
    associate_crossview_tracks,
    build_pair_candidates,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.config import (
    CrossViewConfig,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.fixture import (
    build_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.gnn import (
    graph_from_candidates,
    load_model_bundle,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.training import (
    TrainingConfig,
    train_and_save,
)


def _histories(bundle):
    values = {}
    for record in bundle.records:
        values.setdefault(record.camera_id, {}).setdefault(record.local_track_id, []).append(record)
    return values


class _AlwaysPositiveScorer:
    def __init__(self) -> None:
        self.saw_rejected = False

    def score(self, histories_a, histories_b, candidates, calibration_a, calibration_b):
        self.saw_rejected = any(not item.gate_passed for item in candidates)
        return {(item.track_a_id, item.track_b_id): 1.0 for item in candidates}


class _ConstantScorer:
    def __init__(self, probability: float) -> None:
        self.probability = probability

    def score(self, histories_a, histories_b, candidates, calibration_a, calibration_b):
        assert all(item.gate_passed for item in candidates)
        return {
            (item.track_a_id, item.track_b_id): self.probability
            for item in candidates
        }


def test_gnn_never_receives_or_restores_geometry_rejected_edges() -> None:
    bundle = build_fixture("no_common_targets")
    scorer = _AlwaysPositiveScorer()
    result = associate_crossview_tracks(
        bundle.records,
        bundle.calibrations,
        backend="gnn",
        scorer=scorer,
    )
    assert scorer.saw_rejected is False
    assert result.matches == ()

    histories = _histories(bundle)
    camera_a, camera_b = sorted(histories)
    candidates = build_pair_candidates(
        histories[camera_a],
        histories[camera_b],
        bundle.calibrations[camera_a],
        bundle.calibrations[camera_b],
        CrossViewConfig(),
    )
    rejected = next(item for item in candidates if not item.gate_passed)
    with pytest.raises(ValueError, match="geometry-gated"):
        graph_from_candidates(
            histories[camera_a],
            histories[camera_b],
            (rejected,),
            bundle.calibrations[camera_a],
            bundle.calibrations[camera_b],
        )


def test_gnn_cost_fusion_keeps_fixed_geometry_weight_and_hard_gate() -> None:
    bundle = build_fixture("two_by_two_crossing")
    result = associate_crossview_tracks(
        bundle.records,
        bundle.calibrations,
        backend="gnn",
        scorer=_ConstantScorer(0.8),
    )
    candidates = [
        item
        for item in result.candidates
        if item.gate_passed
        and item.learned_probability == pytest.approx(0.8)
        and item.reference_timestamp == min(
            value.reference_timestamp
            for value in result.candidates
            if value.gate_passed and value.learned_probability is not None
        )
    ]
    assert candidates
    for candidate in candidates:
        assert candidate.final_cost == pytest.approx(
            0.55 * candidate.geometry_cost + 0.45 * (1.0 - 0.8)
        )


def test_training_validation_seeds_are_disjoint_and_model_round_trips(tmp_path: Path) -> None:
    model_dir = train_and_save(
        tmp_path / "model",
        config=TrainingConfig(
            train_seeds=(101,),
            validation_seeds=(201,),
            epochs=1,
            hidden_dim=12,
            target_count=7,
        ),
    )
    scorer = load_model_bundle(model_dir)
    bundle = build_fixture("dense_multicamera", target_count=7, frame_count=5)
    result = associate_crossview_tracks(
        bundle.records,
        bundle.calibrations,
        backend="gnn",
        scorer=scorer,
    )
    assert result.backend == "gnn"
    assert result.metrics.camera_uniqueness_violation_count == 0
    manifest = (model_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"sha256"' in manifest
    assert '"node_feature_names"' in manifest


def test_model_bundle_hash_tampering_fails_closed(tmp_path: Path) -> None:
    model_dir = train_and_save(
        tmp_path / "model",
        config=TrainingConfig(
            train_seeds=(111,),
            validation_seeds=(211,),
            epochs=1,
            hidden_dim=8,
            target_count=5,
        ),
    )
    weights = model_dir / "weights.pt"
    weights.write_bytes(weights.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_model_bundle(model_dir)


def test_model_bundle_rejects_evaluation_seed_overlap(tmp_path: Path) -> None:
    model_dir = train_and_save(
        tmp_path / "model",
        config=TrainingConfig(
            train_seeds=(121,),
            validation_seeds=(221,),
            epochs=1,
            hidden_dim=8,
            target_count=5,
        ),
    )
    with pytest.raises(ValueError, match="overlaps evaluation"):
        load_model_bundle(model_dir, evaluation_seeds=(121,))


def test_training_configuration_rejects_seed_overlap() -> None:
    with pytest.raises(ValueError, match="disjoint"):
        TrainingConfig(train_seeds=(1, 2), validation_seeds=(2, 3))
