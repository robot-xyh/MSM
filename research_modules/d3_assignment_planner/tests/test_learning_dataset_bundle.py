from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    EDGE_FEATURE_NAMES,
    LEARNING_DATASET_SCHEMA_V2,
    LEARNING_DATASET_SPLIT_POLICY_V2,
    LearningFrameRecord,
    MODEL_BUNDLE_SCHEMA_V2,
    OfflineRewardComponents,
    SharedEdgeActorCriticPolicy,
    assign_episode_split,
    assign_seed_splits,
    compute_split_hash,
    iter_learning_frame_records,
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
    scenario: str = "unit_sparse_v1",
    split: str = "unassigned",
) -> LearningFrameRecord:
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
        split=split,
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
    scenarios = ("unit_2v2_scale_2_v1", "unit_5v5_scale_5_v2")
    records = [
        _record(
            seed,
            f"episode_{episode}",
            frame_index=frame,
            scenario=scenario,
        )
        for seed in range(8)
        for scenario in scenarios
        for episode in ("a", "b")
        for frame in range(2)
    ]
    staging_path = tmp_path / "staging.jsonl"
    staging_path.write_text(
        "".join(
            json.dumps(record.to_dict(), ensure_ascii=True, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    manifests = []
    loaded_sets = []
    for root, ordered in (
        (tmp_path / "ordered", iter_learning_frame_records(staging_path)),
        (tmp_path / "reversed", iter(reversed(records))),
    ):
        manifests.append(
            write_learning_dataset(
                root,
                ordered,
                source_kind="synthetic_smoke",
                minimum_unseen_seed_count=1,
                staging_batch_size=3,
            )
        )
        loaded_sets.append(load_learning_dataset(root))

    manifest = manifests[0]
    loaded_manifest, loaded = loaded_sets[0]
    assert manifest.schema_version == LEARNING_DATASET_SCHEMA_V2
    assert manifest.split_policy_version == LEARNING_DATASET_SPLIT_POLICY_V2
    assert loaded_manifest.split_hash == manifest.split_hash == compute_split_hash(loaded)
    assert manifests[0].to_dict() == manifests[1].to_dict()
    assert (tmp_path / "ordered" / "frames.jsonl").read_bytes() == (
        tmp_path / "reversed" / "frames.jsonl"
    ).read_bytes()
    assert len(loaded) == len(records)
    validate_split_integrity(loaded)
    split_by_seed: dict[int, set[str]] = {}
    for item in loaded:
        split_by_seed.setdefault(item.seed, set()).add(item.split)
    assert all(len(splits) == 1 for splits in split_by_seed.values())
    seeds_by_split = {
        split: set(manifest.split_seed_values[split])
        for split in ("train", "validation", "test")
    }
    assert all(seeds_by_split.values())
    assert seeds_by_split["train"].isdisjoint(seeds_by_split["validation"])
    assert seeds_by_split["train"].isdisjoint(seeds_by_split["test"])
    assert seeds_by_split["validation"].isdisjoint(seeds_by_split["test"])
    assert assign_episode_split(
        scenarios[0], 3, "a", seed_values=range(8)
    ) == assign_episode_split(scenarios[1], 3, "b", seed_values=reversed(range(8)))
    payload = (tmp_path / "ordered" / "frames.jsonl").read_text(
        encoding="utf-8"
    ).lower()
    assert "truth" not in payload
    assert "actor" not in payload
    assert "internal_track" not in payload
    same_seed = [item for item in loaded if item.seed == loaded[0].seed]
    leaked = replace(same_seed[0], split="test" if same_seed[0].split != "test" else "train")
    with pytest.raises(ValueError, match="seed|episode"):
        validate_split_integrity(
            (
                leaked,
                *same_seed[1:],
                *[item for item in loaded if item.seed != leaked.seed],
            )
        )


def test_canonical_json_line_and_finalized_dataset_are_byte_equivalent(
    tmp_path: Path,
) -> None:
    record = _record(0, "episode", frame_index=0)
    expected_line = (
        json.dumps(
            record.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    assert record.to_json_line() == expected_line
    assert LearningFrameRecord.from_json_line(expected_line).to_dict() == record.to_dict()

    records = tuple(
        _record(seed, f"episode_{seed}", frame_index=frame)
        for seed in range(3)
        for frame in range(2)
    )
    write_learning_dataset(
        tmp_path / "dataset",
        iter(reversed(records)),
        source_kind="synthetic_smoke",
        minimum_unseen_seed_count=1,
    )
    split_by_seed = assign_seed_splits(range(3))
    expected_bytes = "".join(
        replace(item, split=split_by_seed[item.seed]).to_json_line()
        for item in sorted(
            records,
            key=lambda value: (
                value.scenario_version,
                value.seed,
                value.episode,
                value.frame_index,
            ),
        )
    ).encode("ascii")
    assert (tmp_path / "dataset" / "frames.jsonl").read_bytes() == expected_bytes


def test_dataset_writer_revalidates_mutable_frame_state_before_persistence(
    tmp_path: Path,
) -> None:
    mask_mutated = _record(0, "mask_mutated")
    mask_mutated.action_mask[0, 0] = False
    with pytest.raises(ValueError, match="candidate edges"):
        write_learning_dataset(
            tmp_path / "mask",
            (mask_mutated,),
            source_kind="synthetic_smoke",
            minimum_unseen_seed_count=1,
        )
    assert not (tmp_path / "mask" / "frames.jsonl").exists()

    identity_mutated = _record(0, "identity_mutated")
    assert isinstance(identity_mutated.hard_reject_reason_counts, dict)
    identity_mutated.hard_reject_reason_counts["truth_track_id"] = 1
    with pytest.raises(ValueError, match="identity-bearing"):
        write_learning_dataset(
            tmp_path / "identity",
            (identity_mutated,),
            source_kind="synthetic_smoke",
            minimum_unseen_seed_count=1,
        )
    assert not (tmp_path / "identity" / "frames.jsonl").exists()

    reward_mutated = _record(0, "reward_mutated")
    object.__setattr__(
        reward_mutated.reward_components,
        "rule_total_cost",
        float("nan"),
    )
    with pytest.raises(ValueError, match="reward components"):
        write_learning_dataset(
            tmp_path / "reward",
            (reward_mutated,),
            source_kind="synthetic_smoke",
            minimum_unseen_seed_count=1,
        )
    assert not (tmp_path / "reward" / "frames.jsonl").exists()


def test_dataset_split_fails_closed_for_unique_seed_budget_and_conflicting_split(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="three unique numeric seeds"):
        write_learning_dataset(
            tmp_path / "two",
            (_record(seed, "episode") for seed in (1, 2)),
            source_kind="formal",
            minimum_unseen_seed_count=1,
        )
    with pytest.raises(ValueError, match="declared unseen minimum"):
        write_learning_dataset(
            tmp_path / "unseen",
            (_record(seed, "episode") for seed in range(5)),
            source_kind="formal",
            minimum_unseen_seed_count=2,
        )

    split_map = assign_seed_splits(range(5))
    seed = next(iter(split_map))
    wrong = next(split for split in ("train", "validation", "test") if split != split_map[seed])
    with pytest.raises(ValueError, match="conflicts.*v2 policy"):
        write_learning_dataset(
            tmp_path / "conflict",
            (
                _record(value, "episode", split=wrong if value == seed else "unassigned")
                for value in range(5)
            ),
            source_kind="formal",
            minimum_unseen_seed_count=1,
        )


def test_dataset_loader_rejects_split_tamper_and_legacy_schema(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    write_learning_dataset(
        root,
        (_record(seed, "episode") for seed in range(8)),
        source_kind="formal",
        minimum_unseen_seed_count=1,
    )
    frame_path = root / "frames.jsonl"
    manifest_path = root / "dataset_manifest.json"
    original_frame_bytes = frame_path.read_bytes()
    frame_path.write_bytes(original_frame_bytes + b" ")
    with pytest.raises(ValueError, match="frames SHA256"):
        load_learning_dataset(root)
    frame_path.write_bytes(original_frame_bytes)

    lines = frame_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["split"] = "test" if payload["split"] != "test" else "train"
    lines[0] = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    frame_bytes = ("\n".join(lines) + "\n").encode("ascii")
    frame_path.write_bytes(frame_bytes)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["frames_sha256"] = sha256(frame_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="numeric seed|v2 policy|multiple"):
        load_learning_dataset(root)

    manifest_payload["split_policy_version"] = "d3_scenario_seed_group_split_v1"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported.*split policy"):
        load_learning_dataset(root)

    manifest_payload["split_policy_version"] = LEARNING_DATASET_SPLIT_POLICY_V2
    manifest_payload["schema_version"] = "d3_learning_dataset_v1"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="v1 scenario/seed splits are not compatible"):
        load_learning_dataset(root)


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "truth_actor_id"),
        (("anonymous_targets", 0), "actor_id"),
        (("reward_components",), "identity_label"),
    ],
)
def test_learning_frame_parser_recursively_rejects_identity_fields(
    path: tuple[str | int, ...],
    field: str,
) -> None:
    payload = _record(0, "episode").to_dict()
    target: object = payload
    for part in path:
        target = target[part]  # type: ignore[index]
    assert isinstance(target, dict)
    target[field] = "forbidden"

    with pytest.raises(ValueError, match="identity-bearing"):
        LearningFrameRecord.from_dict(payload)


def test_learning_frame_v2_rejects_unknown_extensions_without_schema_bump() -> None:
    payload = _record(0, "episode").to_dict()
    payload["future_metric"] = 1.0

    with pytest.raises(ValueError, match="extensions require a new schema version"):
        LearningFrameRecord.from_dict(payload)


def test_learning_frame_rejects_identity_strings_in_numeric_entity_fields() -> None:
    payload = _record(0, "episode").to_dict()
    payload["anonymous_targets"][0]["threat_score"] = "actor_target_001"

    with pytest.raises(ValueError, match="must be numeric"):
        LearningFrameRecord.from_dict(payload)


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
        dataset_frames_sha256="a" * 64,
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES)),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES)),
        training_results={"validation_loss": 0.25},
    )

    shadow = load_model_bundle(
        tmp_path,
        mode="shadow",
        expected_split_hash="1" * 64,
        expected_dataset_frames_sha256="a" * 64,
    )
    assist = load_model_bundle(tmp_path, mode="assist")
    assert shadow.loaded is True
    assert assist.loaded is False
    assert assist.fallback_reason == "promotion_not_recommended"
    assert manifest.to_dict()["state_dict"]["load_policy"] == "torch_weights_only_true"
    assert manifest.bundle_schema_version == MODEL_BUNDLE_SCHEMA_V2
    assert manifest.dataset_schema_version == LEARNING_DATASET_SCHEMA_V2
    assert manifest.split_policy_version == LEARNING_DATASET_SPLIT_POLICY_V2
    assert manifest.dataset_frames_sha256 == "a" * 64

    raw = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    raw["promotion_manifest"] = {
        "evidence_schema_version": "d3_shadow_promotion_evidence_v1",
        "evidence_kind": "paired_rule_residual_shadow",
        "cost_basis": "rule_cost_matrix_v1",
        "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
        "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "evaluated_split": "test",
        "evidence_eligible": True,
        "evidence_hashes_bound": True,
        "split_hash": raw["split_hash"],
        "dataset_frames_sha256": raw["dataset_frames_sha256"],
        "model_state_dict_sha256": raw["state_dict"]["sha256"],
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

    for field in (
        "promotion_recommended",
        "safety_non_degradation",
        "assignment_cost_non_degradation",
    ):
        raw["promotion_manifest"][field] = "true"
        (tmp_path / "manifest.json").write_text(
            json.dumps(raw, sort_keys=True), encoding="utf-8"
        )
        assert load_model_bundle(tmp_path, mode="assist").fallback_reason == (
            "promotion_not_recommended"
        )
        raw["promotion_manifest"][field] = True

    raw["promotion_manifest"]["unseen_seed_count"] = 20.0
    (tmp_path / "manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8"
    )
    assert load_model_bundle(tmp_path, mode="assist").fallback_reason == (
        "promotion_not_recommended"
    )
    raw["promotion_manifest"]["unseen_seed_count"] = 20

    bypass = load_model_bundle(
        tmp_path,
        mode="assist",
        require_promotion_for_assist=False,
    )
    assert bypass.loaded is False
    assert bypass.fallback_reason == "promotion_bypass_forbidden"

    raw["promotion_manifest"]["evidence_eligible"] = False
    (tmp_path / "manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8"
    )
    assert load_model_bundle(tmp_path, mode="assist").fallback_reason == (
        "promotion_not_recommended"
    )
    raw["promotion_manifest"]["evidence_eligible"] = True
    raw["promotion_manifest"]["evaluated_split"] = "validation"
    (tmp_path / "manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8"
    )
    assert load_model_bundle(tmp_path, mode="assist").fallback_reason == (
        "promotion_not_recommended"
    )
    raw["promotion_manifest"]["evaluated_split"] = "test"
    raw["promotion_manifest"]["dataset_frames_sha256"] = "b" * 64
    (tmp_path / "manifest.json").write_text(
        json.dumps(raw, sort_keys=True), encoding="utf-8"
    )
    assert load_model_bundle(tmp_path, mode="assist").fallback_reason == (
        "promotion_not_recommended"
    )

    mismatch = load_model_bundle(
        tmp_path,
        mode="shadow",
        expected_dataset_frames_sha256="c" * 64,
    )
    assert mismatch.loaded is False
    assert mismatch.fallback_reason == "dataset_frames_sha256_mismatch"


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
        dataset_frames_sha256="b" * 64,
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


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "bundle_schema_version",
            "d3_learning_model_bundle_v1",
            "model_bundle_schema_unsupported",
        ),
        (
            "split_policy_version",
            "d3_scenario_seed_group_split_v1",
            "model_dataset_contract_unsupported",
        ),
    ],
)
def test_legacy_bundle_contract_is_stably_rejected(
    tmp_path: Path,
    field: str,
    value: str,
    reason: str,
) -> None:
    pytest.importorskip("torch")
    save_model_bundle(
        tmp_path,
        SharedEdgeActorCriticPolicy(hidden_size=8),
        split_hash="3" * 64,
        dataset_frames_sha256="c" * 64,
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES)),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES)),
        training_results={"loss": 1.0},
    )
    manifest_path = tmp_path / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw[field] = value
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_bundle(tmp_path, mode="shadow")

    assert result.loaded is False
    assert result.fallback_reason == reason
