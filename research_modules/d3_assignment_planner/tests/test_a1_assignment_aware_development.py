from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    A1_ASSIGNMENT_AWARE_BUNDLE_SCHEMA_V1,
    A1AssignmentAwareConfig,
    A1AssignmentAwareContractError,
    EDGE_FEATURE_NAMES,
    a1_assignment_aware_bundle_tree_sha256,
    build_a1_assignment_aware_teachers,
    freeze_a1_assignment_aware_bundle,
    load_a1_assignment_aware_bundle,
    solve_a1_safe_assignment,
    train_a1_assignment_aware_candidate,
)

from test_learning_dataset_bundle import _record


def _assignment_aware_record(
    seed: int,
    split: str,
    *,
    opportunity: bool,
    frame_index: int = 1,
):
    record = _record(
        seed,
        f"episode-{seed}",
        frame_index=frame_index,
        target_count=2,
        resource_count=2,
        split=split,
        scenario="assignment-aware-2v2-v1",
    )
    matrix = np.asarray(((0.10, 0.12), (0.12, 0.10)), dtype=float)
    edges = record.candidate_edge_indices
    previous = ((0, 1), (1, 0)) if opportunity else ((0, 0), (1, 1))
    features = np.zeros((len(edges), len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    for offset, edge in enumerate(edges):
        features[offset, 0] = float(matrix[edge])
        features[offset, 1] = 0.9 if edge[0] == 0 else 0.4
        features[offset, 9] = 0.1
        features[offset, 10] = 0.1
        features[offset, 11] = float(edge in previous)
    return replace(
        record,
        candidate_features=features,
        rule_cost_matrix=matrix,
        rule_costs=np.asarray([matrix[edge] for edge in edges], dtype=float),
        rule_selected_edges=((0, 0), (1, 1)),
        previous_selected_edges=previous,
        previous_plan_version=1,
    )


def _config(**overrides):
    values = {
        "epochs": 4,
        "hidden_size": 8,
        "mini_batch_frames": 2,
        "torch_num_threads": 1,
        "hard_negative_edges_per_target": 2,
        "maximum_sample_edges_per_frame": 16,
        "minimum_negative_exact_r0_rate": 0.5,
        "maximum_relative_rule_cost_difference": 0.5,
    }
    values.update(overrides)
    return A1AssignmentAwareConfig(**values)


def _teachers(config):
    records = tuple(
        _assignment_aware_record(
            seed,
            "train" if seed < 4 else "validation",
            opportunity=(seed % 2 == 0),
        )
        for seed in range(8)
    )
    return build_a1_assignment_aware_teachers(records, config=config)


def _source_dataset():
    return {
        "dataset_schema_version": "d3_learning_dataset_v2",
        "dataset_manifest_sha256": sha256(b"manifest").hexdigest(),
        "dataset_frames_sha256": sha256(b"frames").hexdigest(),
        "dataset_split_hash": sha256(b"split").hexdigest(),
        "split_policy_version": "d3_numeric_seed_atomic_split_v2",
        "consumed_splits": ["train", "validation"],
        "optimizer_consumed_splits": ["train"],
        "checkpoint_selection_consumed_splits": ["validation"],
        "train_seed_values": [0, 1, 2, 3],
        "validation_seed_values": [4, 5, 6, 7],
        "parsed_test_frame_count": 0,
        "skipped_raw_test_line_count": 2,
        "formal_holdout_seed_values": list(range(1000, 1020)),
        "formal_holdout_read_count": 0,
        "formal_holdout_status": "not_read_not_evaluated",
    }


def test_teacher_builds_bounded_safe_discrete_alternative_and_negative_r0():
    config = _config()
    positive, negative = build_a1_assignment_aware_teachers(
        (
            _assignment_aware_record(0, "train", opportunity=True),
            _assignment_aware_record(1, "train", opportunity=False),
        ),
        config=config,
    )

    assert positive.opportunity is True
    assert positive.target.selected_edges == ((0, 1), (1, 0))
    assert positive.binding_change_count == 4
    assert positive.target.safety_violation_count == 0
    assert positive.target.churn < positive.r0.churn
    assert np.max(np.abs(positive.target_cost_corrections)) <= (
        config.maximum_abs_cost_correction
    )
    assert negative.opportunity is False
    assert negative.target.selected_edges == negative.r0.selected_edges
    assert np.array_equal(
        negative.target_cost_corrections,
        np.zeros_like(negative.target_cost_corrections),
    )


def test_safe_solver_removes_partial_m_to_n_assignment():
    record = _assignment_aware_record(0, "train", opportunity=False)
    demand_record = replace(
        record,
        target_demand_slots=(2, 1),
        target_threat_scores=(0.9, 0.4),
        anonymous_targets=(
            {
                **dict(record.anonymous_targets[0]),
                "required_resource_count": 2,
                "primary_resource_count": 2,
            },
            dict(record.anonymous_targets[1]),
        ),
    )

    outcome = solve_a1_safe_assignment(
        demand_record,
        demand_record.rule_cost_matrix,
    )

    assigned = {}
    for row, _ in outcome.selected_edges:
        assigned[row] = assigned.get(row, 0) + 1
    assert assigned.get(0, 0) in {0, 2}
    assert outcome.m_to_n_atomicity_violation_count == 0
    assert outcome.duplicate_resource_count == 0
    assert outcome.hard_edge_violation_count == 0


def test_training_is_deterministic_and_checkpoint_selection_is_validation_only():
    pytest.importorskip("torch")
    config = _config(epochs=6)
    teachers = _teachers(config)

    first_policy, first = train_a1_assignment_aware_candidate(
        teachers, config=config
    )
    second_policy, second = train_a1_assignment_aware_candidate(
        teachers, config=config
    )

    assert first.to_dict() == second.to_dict()
    assert first.train_frame_count == 4
    assert first.validation_frame_count == 4
    assert all(
        row["validation"]["split"] == "validation"
        for row in first.epoch_history
    )
    assert first.selected_validation_metrics["permissions"]["assist"] is False
    for name, tensor in first_policy.state_dict().items():
        assert np.array_equal(
            tensor.detach().cpu().numpy(),
            second_policy.state_dict()[name].detach().cpu().numpy(),
        )


def test_bundle_is_byte_reproducible_strict_and_never_loads_as_assist(
    tmp_path: Path,
):
    pytest.importorskip("torch")
    config = _config(epochs=2)
    teachers = _teachers(config)
    policy, result = train_a1_assignment_aware_candidate(
        teachers, config=config
    )
    arguments = {
        "config": config,
        "source_dataset": _source_dataset(),
        "source_tree_sha256": sha256(b"source-tree").hexdigest(),
        "repository_git_commit": "a" * 40,
    }
    first = freeze_a1_assignment_aware_bundle(
        tmp_path / "first",
        policy,
        result,
        **arguments,
    )
    second = freeze_a1_assignment_aware_bundle(
        tmp_path / "second",
        policy,
        result,
        **arguments,
    )

    assert first["manifest"]["bundle_schema_version"] == (
        A1_ASSIGNMENT_AWARE_BUNDLE_SCHEMA_V1
    )
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert first["state_dict_sha256"] == second["state_dict_sha256"]
    assert first["tree_sha256"] == second["tree_sha256"]
    assert a1_assignment_aware_bundle_tree_sha256(tmp_path / "first") == (
        first["tree_sha256"]
    )
    loaded = load_a1_assignment_aware_bundle(
        tmp_path / "first",
        mode="source_independent_evaluation",
        expected_manifest_sha256=first["manifest_sha256"],
        expected_tree_sha256=first["tree_sha256"],
    )
    assert loaded.loaded is True
    assert loaded.assist_authorized is False
    assert loaded.authority_granted is False
    assert loaded.production_admission_granted is False
    assist = load_a1_assignment_aware_bundle(
        tmp_path / "first", mode="assist"
    )
    assert assist.loaded is False
    assert assist.fallback_reason == "assignment_aware_bundle_mode_forbidden"

    state_path = tmp_path / "first" / "state_dict.json"
    state_path.write_bytes(state_path.read_bytes() + b"tamper")
    tampered = load_a1_assignment_aware_bundle(
        tmp_path / "first", mode="shadow"
    )
    assert tampered.loaded is False
    assert tampered.fallback_reason == "bundle_file_sha256_mismatch"


def test_formal_holdout_seed_is_rejected_before_teacher_construction():
    with pytest.raises(A1AssignmentAwareContractError) as error:
        build_a1_assignment_aware_teachers(
            (
                _assignment_aware_record(
                    1000, "train", opportunity=True
                ),
            ),
            config=_config(),
        )

    assert error.value.code == "teacher_formal_holdout_seed_forbidden"
