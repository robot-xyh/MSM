from __future__ import annotations

import csv
import json

import numpy as np

import pytest

from dual_optical_100target_gnn.schema import EDGE_FEATURE_NAMES
from dual_optical_100target_lightweight import pipeline
from dual_optical_100target_lightweight.evaluation import evaluate_frozen
from dual_optical_100target_lightweight.pipeline import (
    ValidationSelectionError,
    _load_split,
    train_validate_and_freeze,
    verify_freeze_manifest,
)
from dual_optical_100target_lightweight.models import LightweightModel


def test_test_split_access_is_rejected_before_freeze(dataset_manifest):
    from dual_optical_100target_gnn.dataset import load_dataset_manifest

    manifest, root = load_dataset_manifest(dataset_manifest)
    with pytest.raises(RuntimeError, match="cannot be opened"):
        _load_split(
            manifest,
            root,
            "test",
            freeze_already_written=False,
            access_log=[],
        )


def test_training_reads_train_and_validation_only(dataset_manifest, tmp_path, monkeypatch):
    opened_splits = []
    original = pipeline.load_entry

    def monitored(root, entry, *, include_labels):
        opened_splits.append(entry["split"])
        return original(root, entry, include_labels=include_labels)

    monkeypatch.setattr(pipeline, "load_entry", monitored)
    freeze_path = train_validate_and_freeze(dataset_manifest, tmp_path / "model")
    assert set(opened_splits) == {"train", "val"}
    assert "test" not in opened_splits
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["expected_target_count"] == 4
    assert freeze["test_graph_files_opened_before_freeze"] is False
    assert freeze["reserved_test_seeds"] == [504]
    assert freeze["edge_feature_names"] == list(EDGE_FEATURE_NAMES)
    assert freeze["selected_unmatched_cost"] in (0.15, 0.25, 0.4, 0.6, 0.9, 1.2)
    assert len(freeze["geometry_component_names"]) == 8
    assert len(freeze["model_fingerprint_sha256"]) == 64
    assert freeze["selected_probability_threshold"] in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    verify_freeze_manifest(freeze_path)


def test_frozen_evaluation_groups_corruptions_by_seed(dataset_manifest, tmp_path):
    freeze_path = train_validate_and_freeze(dataset_manifest, tmp_path / "model")
    metrics_path = evaluate_frozen(
        freeze_path,
        tmp_path / "evaluation",
        latency_repeats=1,
        bootstrap_resamples=50,
        bootstrap_seed=11,
    )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["evidence_status"] == "nonformal_fixture_or_limited_test"
    assert metrics["test_seeds"] == [504]
    assert metrics["independent_seed_count"] == 1
    assert metrics["test_sample_count"] == 3
    assert metrics["bootstrap_protocol"]["light_medium_heavy_are_not_independent_samples"] is True
    assert metrics["grouped_bootstrap_95ci"]["selected_lightweight"]["f1"]["independent_seed_count"] == 1
    assert metrics["truth_isolation"]["truth_fields_in_model_features"] is False
    assert metrics["truth_isolation"]["actor_name_in_model_features"] is False
    assert metrics["truth_isolation"]["true_world_position_in_model_features"] is False
    assert set(metrics["assignment"]) == {"original_geometry", "selected_lightweight"}
    assert len(metrics["candidate_fingerprints"]["per_sample"]) == 3
    assert len(metrics["candidate_fingerprints"]["aggregate_sha256"]) == 64

    with (metrics_path.parent / "per_seed_metrics.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    for level in ("light", "medium", "heavy"):
        level_rows = [row for row in rows if row["corruption_level"] == level]
        assert len(level_rows) == 2
        assert len({row["candidate_fingerprint_sha256"] for row in level_rows}) == 1
        assert all(int(row["duplicate_track_assignment_count"]) == 0 for row in level_rows)


def test_freeze_verification_rejects_model_tamper(dataset_manifest, tmp_path):
    freeze_path = train_validate_and_freeze(dataset_manifest, tmp_path / "model")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    model_path = freeze_path.parent / freeze["selected_model"]
    model_path.write_text(model_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_freeze_manifest(freeze_path)


def test_validation_all_zero_assignments_fail_closed(dataset_manifest):
    from dual_optical_100target_gnn.dataset import load_dataset_manifest, load_entry, sample_entries

    manifest, root = load_dataset_manifest(dataset_manifest)
    validation = []
    for entry in sample_entries(manifest, "val"):
        graph, labels = load_entry(root, entry, include_labels=True)
        assert labels is not None
        validation.append((graph, labels))
    model = LightweightModel(
        "platt_geometry_cost",
        {"coefficient": 0.0, "intercept": -100.0, "C": 1.0},
        2,
    )
    rows = pipeline._validation_rows([model], validation, manifest["geometry_gate"])
    assert all(int(row["selected_count"]) == 0 for row in rows)
    with pytest.raises(RuntimeError, match="zero assignments"):
        pipeline._rank_validation_rows(rows, [model])


def test_precision_floor_rejection_preserves_best_validation_evidence():
    model = LightweightModel(
        "platt_geometry_cost",
        {"coefficient": 1.0, "intercept": 0.0, "C": 1.0},
        2,
    )
    common = {
        "model_id": model.model_id,
        "model_kind": model.kind,
        "selected_count": 10,
        "false_association_count": 4,
        "duplicate_identity_match_count": 0,
        "probability_threshold": 0.5,
        "unmatched_cost": 0.6,
    }
    rows = [
        {
            **common,
            "conditional_precision": 0.60,
            "macro_recall": 0.50,
            "macro_f1": 0.54,
        },
        {
            **common,
            "conditional_precision": 0.69,
            "macro_recall": 0.40,
            "macro_f1": 0.50,
            "false_association_count": 3,
        },
    ]

    with pytest.raises(ValidationSelectionError) as caught:
        pipeline._rank_validation_rows(rows, [model])

    failure = caught.value
    assert failure.reason_code == "conditional_precision_floor_not_met"
    assert failure.best_validation_result is not None
    assert failure.best_validation_result["conditional_precision"] == 0.69
    assert failure.best_validation_result["minimum_conditional_precision"] == 0.70
    assert failure.best_validation_result["selection_eligible"] is False
    assert all(row["selection_eligible"] is False for row in failure.validation_rows)
