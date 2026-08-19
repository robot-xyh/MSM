from __future__ import annotations

import json

import numpy as np
import pytest

from dual_optical_target_track_gnn import (
    FiveInitializationConfig,
    TargetTrackTrainingExample,
    balanced_multiscale_samples,
    load_frozen_model,
    train_and_freeze_five_initializations,
)
from dual_optical_target_track_gnn.contracts import (
    EDGE_FEATURE_NAMES,
    TARGET_FEATURE_NAMES,
    TRACK_FEATURE_NAMES,
    TargetTrackGraph,
    payload_fingerprint,
)
from dual_optical_target_track_gnn.model import predict_cost_corrections


def make_graph(seed: int, revolution: int = 4) -> TargetTrackGraph:
    hypothesis_ids = ("H-0", "H-1")
    track_ids = ("A-0", "A-1")
    edge_index = np.asarray(((0, 0, 1), (0, 1, 1)), dtype=np.int64)
    edges = [
        [hypothesis_ids[int(target)], track_ids[int(track)]]
        for target, track in edge_index.T
    ]
    fingerprint = payload_fingerprint(
        {
            "schema_version": "dual-optical-target-track-gnn-v1",
            "seed": seed,
            "revolution_index": revolution,
            "camera_id": "camera_a",
            "edges": edges,
        }
    )
    graph = TargetTrackGraph(
        seed=seed,
        revolution_index=revolution,
        camera_id="camera_a",
        hypothesis_ids=hypothesis_ids,
        track_ids=track_ids,
        target_features=np.asarray(
            [np.linspace(0.0, 1.0, len(TARGET_FEATURE_NAMES)),
             np.linspace(1.0, 2.0, len(TARGET_FEATURE_NAMES))],
            dtype=np.float32,
        ),
        track_features=np.asarray(
            [np.linspace(0.0, 1.0, len(TRACK_FEATURE_NAMES)),
             np.linspace(1.0, 2.0, len(TRACK_FEATURE_NAMES))],
            dtype=np.float32,
        ),
        edge_index=edge_index,
        edge_features=np.asarray(
            [
                np.linspace(0.0, 1.0, len(EDGE_FEATURE_NAMES)),
                np.linspace(1.0, 2.0, len(EDGE_FEATURE_NAMES)),
                np.linspace(2.0, 3.0, len(EDGE_FEATURE_NAMES)),
            ],
            dtype=np.float32,
        ),
        rule_cost=np.asarray((0.2, 0.8, 0.3), dtype=np.float32),
        whitelist_fingerprint=fingerprint,
    )
    graph.validate()
    return graph


def make_examples(include_test: bool = False) -> tuple[TargetTrackTrainingExample, ...]:
    examples = []
    for split, offset, samples_per_scale in (
        ("train", 1000, 2),
        ("validation", 2000, 1),
    ):
        for target_count in (40, 60, 100):
            for index in range(samples_per_scale):
                seed = offset + target_count * 10 + index
                examples.append(
                    TargetTrackTrainingExample(
                        example_id=f"{split}-{target_count}-{index}",
                        split=split,
                        target_count=target_count,
                        seed=seed,
                        graph=make_graph(seed),
                        edge_labels=np.asarray((1.0, 0.0, 1.0), dtype=np.float32),
                    )
                )
    if include_test:
        examples.append(
            TargetTrackTrainingExample(
                example_id="test-40-0",
                split="test",
                target_count=40,
                seed=9999,
                graph=make_graph(9999),
                edge_labels=np.asarray((1.0, 0.0, 1.0), dtype=np.float32),
            )
        )
    return tuple(examples)


def test_balanced_selection_is_equal_across_scales_and_rejects_test_labels() -> None:
    selected = balanced_multiscale_samples(
        make_examples(), split="train", samples_per_scale=2
    )
    assert len(selected) == 6
    assert {count: sum(item.target_count == count for item in selected) for count in (40, 60, 100)} == {
        40: 2,
        60: 2,
        100: 2,
    }
    with pytest.raises(ValueError, match="test labels"):
        balanced_multiscale_samples(
            make_examples(include_test=True), split="train"
        )


def test_five_initializations_freeze_one_shared_model_without_test_labels(tmp_path) -> None:
    outcome = train_and_freeze_five_initializations(
        make_examples(),
        tmp_path / "freeze",
        config=FiveInitializationConfig(
            max_epochs=1,
            patience=1,
            dropout=0.0,
            train_samples_per_scale=1,
            validation_samples_per_scale=1,
            device="cpu",
        ),
    )

    assert len(outcome.initialization_results) == 5
    assert len({item.initialization_seed for item in outcome.initialization_results}) == 5
    manifest = json.loads(
        (tmp_path / "freeze" / "freeze_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["metadata"]["test_labels_opened"] is False
    assert manifest["metadata"]["target_counts"] == [40, 60, 100]
    model, normalizer, restored_manifest = load_frozen_model(tmp_path / "freeze")
    corrections = predict_cost_corrections(model, make_graph(1234), normalizer)
    assert corrections.shape == (3,)
    assert np.max(np.abs(corrections)) <= 1.0 + 1.0e-6
    assert restored_manifest["weights_sha256"] == manifest["weights_sha256"]


def test_training_entry_point_rejects_any_test_example(tmp_path) -> None:
    with pytest.raises(ValueError, match="test labels"):
        train_and_freeze_five_initializations(
            make_examples(include_test=True),
            tmp_path / "forbidden",
            config=FiveInitializationConfig(max_epochs=1, patience=1, device="cpu"),
        )
