from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    EDGE_FEATURE_NAMES,
    LearningFrameRecord,
    OfflineRewardComponents,
    SharedEdgeActorCriticPolicy,
    assign_episode_split,
    compute_split_hash,
    load_learning_dataset,
    load_model_bundle,
    save_model_bundle,
    validate_split_integrity,
    write_learning_dataset,
)


def _record(
    seed: int,
    episode: str,
    *,
    frame_index: int = 0,
    target_count: int = 3,
    resource_count: int = 5,
    mask: np.ndarray | None = None,
) -> LearningFrameRecord:
    scenario = "unit_sparse_v1"
    action_mask = (
        np.ones((target_count, resource_count), dtype=bool)
        if mask is None
        else np.asarray(mask, dtype=bool)
    )
    rows, columns = np.nonzero(action_mask)
    edges = tuple((int(row), int(column)) for row, column in zip(rows, columns))
    selected = tuple(
        (index, index)
        for index in range(min(target_count, resource_count))
        if action_mask[index, index]
    )
    selected_set = set(selected)
    features = np.zeros((len(edges), len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    for offset, edge in enumerate(edges):
        is_selected = edge in selected_set
        features[offset, 0] = 0.05 if is_selected else 0.95
        features[offset, 1] = 0.9 if edge[0] == 0 else 0.4
        features[offset, 9] = 0.1
        features[offset, 10] = 0.1
        features[offset, 11] = float(frame_index > 0 and is_selected)
    matrix = np.asarray(
        [
            [0.1 + abs(row - column) + 0.01 * column for column in range(resource_count)]
            for row in range(target_count)
        ],
        dtype=float,
    )
    return LearningFrameRecord(
        scenario_version=scenario,
        seed=seed,
        episode=episode,
        frame_index=frame_index,
        timestamp_s=float(frame_index),
        split=assign_episode_split(scenario, seed, episode),
        anonymous_targets=tuple(
            {
                "token": f"target_{index:04d}",
                "threat_score": 0.9 if index == 0 else 0.4,
                "covariance_squashed": 0.1,
                "window_cost": 0.0,
                "required_resource_count": 1,
                "primary_resource_count": 1,
                "assignable": True,
            }
            for index in range(target_count)
        ),
        anonymous_resources=tuple(
            {
                "token": f"resource_{index:04d}",
                "available": True,
                "health_score": 1.0,
                "energy_fraction": 1.0,
                "availability_score": 1.0,
                "current_load": 0.0,
                "assignment_capacity": 1,
            }
            for index in range(resource_count)
        ),
        candidate_edge_indices=edges,
        candidate_features=features,
        action_mask=action_mask,
        rule_cost_matrix=matrix,
        rule_costs=np.asarray([matrix[row, column] for row, column in edges]),
        unassigned_costs=np.full(target_count, 10.0),
        rule_selected_edges=selected,
        previous_selected_edges=selected if frame_index else (),
        previous_plan_version=frame_index,
        feedback_result="none",
        hysteresis_result="accepted" if frame_index == 0 else "unchanged",
        hold_label=frame_index > 0,
        replan_label=False,
        advice_allowed=True,
        target_threat_scores=tuple(0.9 if index == 0 else 0.4 for index in range(target_count)),
        target_demand_slots=tuple(1 for _ in range(target_count)),
        hard_reject_reason_counts={},
        reward_components=OfflineRewardComponents(
            high_threat_coverage=1.0,
            rule_total_cost=float(sum(matrix[row, column] for row, column in selected)),
            unmet_demand_slots=max(0, target_count - len(selected)),
            reassignment_churn=0 if frame_index else len(selected),
            plan_expired=0,
            safety_rejections=0,
        ),
    )


def test_dataset_split_is_whole_seed_and_round_trips_without_identity_leakage(
    tmp_path: Path,
) -> None:
    records = tuple(
        _record(0, episode, frame_index=frame)
        for episode in ("episode_a", "episode_b")
        for frame in range(2)
    ) + (_record(1, "validation_episode"), _record(6, "test_episode"))

    validate_split_integrity(records)
    assert assign_episode_split("unit_sparse_v1", 0, "a") == assign_episode_split(
        "unit_sparse_v1", 0, "b"
    )
    manifest = write_learning_dataset(tmp_path, records, source_kind="synthetic_smoke")
    loaded_manifest, loaded = load_learning_dataset(tmp_path)

    assert loaded_manifest.split_hash == manifest.split_hash == compute_split_hash(records)
    assert len(loaded) == len(records)
    payload = (tmp_path / "frames.jsonl").read_text(encoding="utf-8").lower()
    assert "truth" not in payload
    assert "actor" not in payload
    assert "internal_track" not in payload
    leaked = replace(records[0], split="test")
    with pytest.raises(ValueError, match="seed|episode"):
        validate_split_integrity((leaked, records[1]))


@pytest.mark.parametrize(
    ("target_count", "resource_count", "edge_count"),
    [(3, 5, 15), (5, 3, 15), (200, 1, 200)],
)
def test_shared_policy_uses_variable_sparse_edges_not_a_fixed_dense_head(
    target_count: int,
    resource_count: int,
    edge_count: int,
) -> None:
    pytest.importorskip("torch")
    record = _record(
        0,
        f"shape_{target_count}_{resource_count}",
        target_count=target_count,
        resource_count=resource_count,
    )
    policy = SharedEdgeActorCriticPolicy(hidden_size=8)
    action = policy.act(
        record.candidate_features,
        edge_mask=np.ones(edge_count, dtype=bool),
        advice_allowed=False,
        deterministic=True,
    )

    assert record.candidate_features.shape == (edge_count, len(EDGE_FEATURE_NAMES))
    assert action.residuals.shape == (edge_count,)
    assert not hasattr(policy, "dense_action_head")


def test_bundle_is_weights_only_checksum_verified_and_assist_requires_promotion(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    policy = SharedEdgeActorCriticPolicy(hidden_size=8)
    manifest = save_model_bundle(
        tmp_path,
        policy,
        split_hash="1" * 64,
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES)),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES)),
        training_results={"validation_loss": 0.25},
    )

    shadow = load_model_bundle(tmp_path, mode="shadow", expected_split_hash="1" * 64)
    assist = load_model_bundle(tmp_path, mode="assist")
    assert shadow.loaded is True
    assert assist.loaded is False
    assert assist.fallback_reason == "promotion_not_recommended"
    assert manifest.to_dict()["state_dict"]["load_policy"] == "torch_weights_only_true"

    raw = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    raw["promotion_manifest"] = {
        "promotion_recommended": True,
        "promotion_status": "recommended",
        "unseen_seed_count": 19,
        "minimum_unseen_seed_count": 20,
        "safety_non_degradation": True,
        "assignment_cost_non_degradation": True,
        "fallback_frame_count": 0,
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8"
    )
    underpowered = load_model_bundle(tmp_path, mode="assist")
    assert underpowered.loaded is False
    assert underpowered.fallback_reason == "promotion_not_recommended"
    raw["promotion_manifest"]["unseen_seed_count"] = 20
    (tmp_path / "manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8"
    )
    assert load_model_bundle(tmp_path, mode="assist").loaded is True


@pytest.mark.parametrize("mutation", ["feature", "policy", "sha"])
def test_bundle_mismatch_falls_back_to_rule_without_unsafe_load(
    tmp_path: Path,
    mutation: str,
) -> None:
    pytest.importorskip("torch")
    save_model_bundle(
        tmp_path,
        SharedEdgeActorCriticPolicy(hidden_size=8),
        split_hash="2" * 64,
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES)),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES)),
        training_results={"loss": 1.0},
    )
    manifest_path = tmp_path / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "feature":
        raw["feature_names"][0] = "wrong_feature"
        manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    elif mutation == "policy":
        raw["policy_version"] = "wrong_policy"
        manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    else:
        state_path = tmp_path / "state_dict.pt"
        state_path.write_bytes(state_path.read_bytes() + b"corrupt")

    result = load_model_bundle(tmp_path, mode="shadow")

    assert result.loaded is False
    assert result.policy is None
    assert result.fallback_reason in {
        "model_manifest_invalid",
        "state_dict_sha256_mismatch",
    }
