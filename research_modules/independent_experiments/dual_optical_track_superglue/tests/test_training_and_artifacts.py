from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest
import torch

from research_modules.independent_experiments.dual_optical_track_superglue.artifacts import (
    load_weights,
    save_weights,
)
from research_modules.independent_experiments.dual_optical_track_superglue.config import (
    ModelConfig,
    TrainingConfig,
)
from research_modules.independent_experiments.dual_optical_track_superglue.model import (
    TrackSuperGlue,
)
from research_modules.independent_experiments.dual_optical_track_superglue.normalization import (
    FeatureNormalizer,
)
from research_modules.independent_experiments.dual_optical_track_superglue.schema import (
    AssociationLabels,
    TrainingExample,
)
from research_modules.independent_experiments.dual_optical_track_superglue.tensors import (
    graph_tensors,
)
from research_modules.independent_experiments.dual_optical_track_superglue.training import (
    association_loss,
    train_ensemble,
)


def test_balanced_loss_is_finite_and_differentiable(training_example) -> None:
    normalizer = FeatureNormalizer.identity()
    tensors = graph_tensors(training_example.graph, normalizer)
    model = TrackSuperGlue(ModelConfig(dropout=0.0))
    output = model(*tensors.model_arguments())
    loss = association_loss(output, training_example.labels)
    assert torch.isfinite(loss)
    loss.backward()
    assert any(parameter.grad is not None for parameter in model.parameters())


def test_training_skips_empty_first_revolution_graphs(training_example) -> None:
    graph = training_example.graph
    empty_graph = replace(
        graph,
        revolution_index=1,
        cutoff_timestamp=2.0,
        track_ids_a=(),
        track_ids_b=(),
        observation_history_a=np.empty((0, 6, 10), dtype=np.float32),
        observation_history_b=np.empty((0, 6, 10), dtype=np.float32),
        history_lengths_a=np.empty((0,), dtype=np.int64),
        history_lengths_b=np.empty((0,), dtype=np.int64),
        track_features_a=np.empty((0, 15), dtype=np.float32),
        track_features_b=np.empty((0, 15), dtype=np.float32),
        candidate_mask=np.empty((0, 0), dtype=bool),
        edge_features=np.empty((0, 0, 18), dtype=np.float32),
    )
    empty_example = TrainingExample(empty_graph, AssociationLabels(()))
    validation_example = TrainingExample(
        replace(graph, split="validation"), training_example.labels
    )
    result = train_ensemble(
        (empty_example, training_example),
        (validation_example,),
        training_config=TrainingConfig(max_epochs=1, patience=1),
        model_config=ModelConfig(dropout=0.0),
    )

    assert result.training_example_count == 2
    assert result.optimized_training_example_count == 1
    assert result.skipped_empty_training_example_count == 1


def test_test_labels_remain_sealed(graph_factory) -> None:
    example = TrainingExample(
        graph_factory(split="test"), AssociationLabels(((0, 0),))
    )
    with pytest.raises(ValueError, match="sealed"):
        example.validate()


def test_weights_only_save_and_load_round_trip(tmp_path) -> None:
    torch.manual_seed(22)
    config = ModelConfig(dropout=0.0)
    model = TrackSuperGlue(config).eval()
    path = tmp_path / "weights.pt"
    save_weights(model, path)
    restored = load_weights(path, config)
    for expected, actual in zip(model.state_dict().values(), restored.state_dict().values()):
        assert torch.equal(expected, actual)


def test_normalizer_save_load_round_trip(tmp_path, graph_factory) -> None:
    normalizer = FeatureNormalizer.fit((graph_factory(),))
    path = tmp_path / "normalizer.json"
    normalizer.save(path)
    restored = FeatureNormalizer.load(path)
    assert restored == normalizer
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["fit_split"] == "train_only"
