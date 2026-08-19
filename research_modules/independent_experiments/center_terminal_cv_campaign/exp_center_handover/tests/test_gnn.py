from __future__ import annotations

import json

import pytest
import torch

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.association import (
    CenterHandoverAssociator,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.fixture import (
    build_offline_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.gnn import (
    MODEL_SCHEMA,
    SparseGNNScorer,
    TrainingConfig,
    build_candidate_graph,
    ensure_no_forbidden_training_seed,
    ensure_seed_isolation,
    load_model,
    model_manifest_path,
    save_model,
    train_sparse_gnn,
)


def test_sparse_graph_contains_only_geometry_eligible_edges() -> None:
    fixture = build_offline_fixture(target_count=5, seed=20260816)
    result = CenterHandoverAssociator(fixture.camera_models).process_frame(
        fixture.source_cues, fixture.frames[0]
    )
    graph = build_candidate_graph(result.candidates, fixture.source_cues, fixture.frames[0])
    eligible_ids = {candidate.candidate_id for candidate in result.candidates if candidate.eligible}
    assert set(graph.candidate_ids) == eligible_ids
    assert graph.edge_index.shape[1] == len(eligible_ids)


def test_training_validation_seed_overlap_is_rejected() -> None:
    with pytest.raises(ValueError, match="overlap"):
        ensure_seed_isolation((1, 2), (2, 3))


def test_held_out_airsim_seed_is_rejected_from_training_and_validation() -> None:
    with pytest.raises(ValueError, match="held out"):
        ensure_no_forbidden_training_seed((20260816,), (20260101,))
    with pytest.raises(ValueError, match="held out"):
        ensure_no_forbidden_training_seed((20260001,), (20260816,))


def test_pure_torch_model_trains_saves_loads_and_scores(tmp_path) -> None:
    config = TrainingConfig(
        train_seeds=(20260001, 20260002),
        validation_seeds=(20260101,),
        epochs=2,
    )
    model, metrics = train_sparse_gnn(config)
    assert metrics["validation_motion_edge_fraction"] > 0.0
    path = save_model(
        tmp_path / "model.pt",
        model,
        config=config,
        validation_metrics=metrics,
    )
    loaded, metadata = load_model(path)
    assert model_manifest_path(path).is_file()
    assert MODEL_SCHEMA.endswith("v2")
    assert metadata["training_config"]["target_counts"] == [20, 40]
    assert metadata["training_config"]["device"] == "cpu"
    assert metadata["validation_metrics"]["validation_motion_edge_fraction"] > 0.0
    assert not any("torch_geometric" in module for module in torch.nn.modules.module.__dict__)

    fixture = build_offline_fixture(target_count=5, seed=20260816)
    base = CenterHandoverAssociator(fixture.camera_models).process_frame(
        fixture.source_cues, fixture.frames[0]
    )
    scores = SparseGNNScorer(loaded)(base.candidates, fixture.source_cues, fixture.frames[0])
    assert set(scores) == {
        candidate.candidate_id for candidate in base.candidates if candidate.eligible
    }
    assert all(0.0 <= value <= 1.0 for value in scores.values())


def test_model_load_fails_closed_without_manifest(tmp_path) -> None:
    path = tmp_path / "old-model.pt"
    torch.save({"schema_version": "center-handover-sparse-gnn-v1"}, path)

    with pytest.raises(FileNotFoundError, match="manifest"):
        load_model(path)


def test_model_load_fails_closed_on_hash_mismatch(tmp_path) -> None:
    config = TrainingConfig(
        train_seeds=(20260001,), validation_seeds=(20260101,), epochs=1
    )
    model, metrics = train_sparse_gnn(config)
    path = save_model(
        tmp_path / "model.pt", model, config=config, validation_metrics=metrics
    )
    sidecar = model_manifest_path(path)
    original_manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    wrong_schema = dict(original_manifest)
    wrong_schema["model_schema_version"] = "center-handover-sparse-gnn-v1"
    sidecar.write_text(json.dumps(wrong_schema) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="model schema"):
        load_model(path)

    sidecar.write_text(json.dumps(original_manifest) + "\n", encoding="utf-8")
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_model(path)
