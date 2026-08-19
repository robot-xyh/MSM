from __future__ import annotations

import math

import pytest
import torch

from research_modules.independent_experiments.dual_optical_track_superglue.config import (
    ModelConfig,
    TrainingConfig,
)
from research_modules.independent_experiments.dual_optical_track_superglue.model import (
    TrackSuperGlue,
    log_sinkhorn,
)
from research_modules.independent_experiments.dual_optical_track_superglue.normalization import (
    FeatureNormalizer,
)
from research_modules.independent_experiments.dual_optical_track_superglue.tensors import (
    graph_tensors,
)


def test_configuration_defaults_are_frozen() -> None:
    model = ModelConfig()
    training = TrainingConfig()
    assert model.history_length == 6
    assert model.descriptor_dim == 64
    assert model.attention_cycles == 2
    assert model.attention_heads == 4
    assert model.sinkhorn_iterations == 30
    assert training.learning_rate == pytest.approx(1.0e-3)
    assert training.weight_decay == pytest.approx(1.0e-4)
    assert training.dropout == pytest.approx(0.1)
    assert training.max_epochs == 200
    assert training.patience == 25
    assert len(training.initialization_seeds) == 5
    assert training.validation_thresholds == (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    assert training.matched_loss_weight == training.dustbin_loss_weight == 0.5


def test_log_sinkhorn_is_finite_and_matches_marginals() -> None:
    torch.manual_seed(4)
    scores = torch.randn(4, 5)
    row_marginals = torch.full((4,), 0.25)
    column_marginals = torch.full((5,), 0.2)
    result = log_sinkhorn(
        scores,
        torch.log(row_marginals),
        torch.log(column_marginals),
        iterations=100,
    )
    probabilities = torch.exp(result)
    assert torch.isfinite(result).all()
    assert torch.allclose(probabilities.sum(dim=1), row_marginals, atol=1.0e-5)
    assert torch.allclose(probabilities.sum(dim=0), column_marginals, atol=1.0e-5)


def test_model_shapes_dustbin_mask_and_marginals(graph_factory) -> None:
    graph = graph_factory()
    tensors = graph_tensors(graph, FeatureNormalizer.identity())
    model = TrackSuperGlue(ModelConfig(dropout=0.0)).eval()
    with torch.no_grad():
        output = model(*tensors.model_arguments())
    assert output.descriptors_a.shape == (2, 64)
    assert output.descriptors_b.shape == (2, 64)
    assert output.similarity_logits.shape == (2, 2)
    assert output.transport.assignment.shape == (3, 3)
    assert torch.isfinite(output.transport.assignment).all()
    assert output.transport.assignment[0, 2] >= 0.0
    assert output.transport.assignment[2, 0] >= 0.0
    assert output.transport.assignment[1, 0] == 0.0
    assert torch.allclose(
        output.transport.assignment.sum(dim=1),
        output.transport.row_marginals,
        atol=2.0e-4,
    )
    assert torch.allclose(
        output.transport.assignment.sum(dim=0),
        output.transport.column_marginals,
        atol=2.0e-4,
    )


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is optional")
def test_model_can_run_on_optional_gpu(graph_factory) -> None:
    graph = graph_factory()
    tensors = graph_tensors(graph, FeatureNormalizer.identity(), "cuda")
    model = TrackSuperGlue(ModelConfig(dropout=0.0)).cuda().eval()
    with torch.no_grad():
        output = model(*tensors.model_arguments())
    assert output.transport.assignment.device.type == "cuda"
    assert torch.isfinite(output.transport.assignment).all()
