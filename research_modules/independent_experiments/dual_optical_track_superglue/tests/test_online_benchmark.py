from __future__ import annotations

from dataclasses import asdict
import json

import pytest
import torch

from dual_optical_online_benchmark.contracts import AssociationPublication
from dual_optical_online_benchmark.orchestrator import _positive_validation_metrics
from research_modules.independent_experiments.dual_optical_track_superglue.artifacts import (
    save_weights,
    sha256_file,
)
from research_modules.independent_experiments.dual_optical_track_superglue.config import (
    ModelConfig,
)
from research_modules.independent_experiments.dual_optical_track_superglue.model import (
    TrackSuperGlue,
)
from research_modules.independent_experiments.dual_optical_track_superglue.normalization import (
    FeatureNormalizer,
)
from research_modules.independent_experiments.dual_optical_track_superglue.online_benchmark import (
    FREEZE_SCHEMA_VERSION,
    ROUTE_NAME,
    ROUTE_VERSION,
    freeze_route,
    load_frozen_route,
)
from research_modules.independent_experiments.dual_optical_track_superglue.training import (
    EnsembleTrainingResult,
    InitializationSummary,
    ValidationSelection,
)


def _write_freeze(root, snapshot) -> object:
    config = ModelConfig(dropout=0.0)
    model = TrackSuperGlue(config)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.dustbin_score.fill_(-10.0)
    weights = root / "track_superglue_weights.pt"
    normalizer = root / "normalizer.json"
    model_config = root / "model_config.json"
    training_summary = root / "training_summary.json"
    save_weights(model, weights)
    FeatureNormalizer.identity().save(normalizer)
    model_config.write_text(json.dumps(config.to_dict()) + "\n", encoding="utf-8")
    selection = {
        "initialization_seed": 1103,
        "threshold": 0.3,
        "macro_precision": 0.8,
        "macro_recall": 0.4,
        "macro_f1": 0.5333333333,
        "correct_assignment_count": 12,
        "selected_assignment_count": 15,
        "expected_assignment_count": 30,
        "validation_failed_closed": False,
    }
    training_summary.write_text(
        json.dumps({"selected_validation": selection}) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "route_name": ROUTE_NAME,
        "route_version": ROUTE_VERSION,
        "weights": weights.name,
        "normalizer": normalizer.name,
        "model_config": model_config.name,
        "training_summary_path": training_summary.name,
        "artifact_sha256": {
            "weights": sha256_file(weights),
            "normalizer": sha256_file(normalizer),
            "model_config": sha256_file(model_config),
            "training_summary": sha256_file(training_summary),
        },
        "model_fingerprint_sha256": "f" * 64,
        "protocol_fingerprint_sha256": snapshot.protocol_fingerprint,
        "validation_selection": selection,
        "training_summary": {"selected_validation": selection},
    }
    path = root / "freeze_manifest.json"
    path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    return path


def test_load_frozen_route_and_publish_shared_dto(tmp_path, snapshot_factory) -> None:
    snapshot = snapshot_factory(revolution_index=1)
    manifest = _write_freeze(tmp_path, snapshot)
    route = load_frozen_route(manifest)
    publication = route.publish(snapshot)
    assert isinstance(publication, AssociationPublication)
    assert publication.route_name == "track_superglue"
    assert publication.route_version == ROUTE_VERSION
    assert publication.model_fingerprint == "f" * 64
    assert publication.hungarian_ms == 0.0
    assert "attention_sinkhorn_ms" in publication.stage_latencies_ms


def test_main_accepts_fixture_and_three_revolutions_enforce_confirmation(
    tmp_path, snapshot_factory
) -> None:
    manifest = _write_freeze(tmp_path, snapshot_factory(revolution_index=1))
    acceptance = _positive_validation_metrics(ROUTE_NAME, manifest)
    assert acceptance["accepted"] is True
    assert acceptance["validation_correct_association_count"] == 12

    route = load_frozen_route(manifest)
    publications = tuple(
        route.publish(snapshot_factory(revolution_index=revolution_index))
        for revolution_index in (1, 2, 3)
    )
    assert publications[0].matches == ()
    assert publications[1].matches == ()
    assert publications[2].matches
    for publication in publications:
        ids_a = [match.track_a_id for match in publication.matches]
        ids_b = [match.track_b_id for match in publication.matches]
        assert len(ids_a) == len(set(ids_a))
        assert len(ids_b) == len(set(ids_b))
    assert all(
        match.decision_state == "confirmed" for match in publications[2].matches
    )


def test_freeze_manifest_exposes_main_readable_validation_fields(tmp_path, snapshot_factory) -> None:
    manifest = _write_freeze(tmp_path, snapshot_factory())
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    selected = payload["validation_selection"]
    assert selected["macro_f1"] > 0.0
    assert selected["correct_assignment_count"] == 12
    assert selected["selected_assignment_count"] == 15
    assert selected["validation_failed_closed"] is False
    assert payload["training_summary"]["selected_validation"] == selected


def test_freeze_route_writes_main_readable_selection(monkeypatch, tmp_path) -> None:
    from research_modules.independent_experiments.dual_optical_track_superglue import online_benchmark

    calibration_manifest = tmp_path / "calibration_manifest.json"
    calibration_manifest.write_text("{}\n", encoding="utf-8")
    config = ModelConfig(dropout=0.1)
    model = TrackSuperGlue(config)
    selection = ValidationSelection(
        initialization_seed=1103,
        threshold=0.5,
        macro_precision=0.75,
        macro_recall=0.4,
        macro_f1=0.521739,
        correct_assignment_count=9,
        selected_assignment_count=12,
        expected_assignment_count=20,
        validation_failed_closed=False,
    )
    summaries = tuple(
        InitializationSummary(seed, 2, 1, 0.25, True, selection)
        for seed in (1103, 2207, 3301, 4409, 5501)
    )
    result = EnsembleTrainingResult(
        model_config=config,
        normalizer=FeatureNormalizer.identity(),
        selected_state_dict={
            name: value.detach().cpu().clone()
            for name, value in model.state_dict().items()
        },
        validation_selection=selection,
        initialization_summaries=summaries,
    )
    monkeypatch.setattr(
        online_benchmark,
        "_load_calibration_examples",
        lambda path: (
            (),
            (),
            {
                "protocol": {"target_count": 20},
                "protocol_fingerprint": "p" * 64,
                "tracker_fingerprint": "tracker-v2",
                "train_example_count": 10,
                "validation_example_count": 4,
            },
        ),
    )
    monkeypatch.setattr(online_benchmark, "train_ensemble", lambda *args, **kwargs: result)
    manifest = freeze_route(calibration_manifest, tmp_path / "freeze")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["route_name"] == "track_superglue"
    assert payload["validation_selection"]["macro_f1"] == selection.macro_f1
    assert payload["validation_selection"]["validation_failed_closed"] is False
    assert payload["training_summary"]["initialization_count"] == 5
    assert payload["training_summary"]["test_label_access_count"] == 0


def test_freeze_route_rejects_test_entry_before_opening_artifacts(tmp_path) -> None:
    manifest = tmp_path / "calibration_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "phase": "calibration",
                "test_access_allowed": False,
                "entries": [
                    {
                        "split": "test",
                        "snapshot_path": "does-not-exist.json",
                        "label_path": "sealed-does-not-exist.json",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="test or unknown split"):
        freeze_route(manifest, tmp_path / "freeze")
