from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

import d5_terminal_association.active_vision_corpus_audit as corpus_module
from d5_terminal_association.active_vision_bc_training import (
    ActiveVisionBcConfig,
    build_behavior_cloning_feature_cache,
    load_behavior_cloning_feature_cache,
    train_cached_behavior_cloning,
)
from d5_terminal_association.active_vision_contracts import ActiveVisionIntent
from d5_terminal_association.active_vision_corpus_audit import (
    ActiveVisionCorpusCoverageError,
    active_vision_camera_role,
    audit_active_vision_training_corpus,
    require_active_vision_training_corpus_ready,
    validate_active_vision_corpus_audit,
)
from d5_terminal_association.active_vision_curriculum import (
    ActiveVisionCurriculumConfig,
    build_active_vision_curriculum_episode,
)
from d5_terminal_association.active_vision_episode_dataset import (
    ActiveVisionSourceIdentityV1,
)
from d5_terminal_association.active_vision_learning import (
    ACTIVE_VISION_FEATURE_NAMES,
    ActiveVisionResearchEpisode,
    ActiveVisionTransition,
)


_SCENARIO = "active-vision-5v5-v1"


class _CorpusDataset:
    def __init__(
        self,
        episodes_by_split: dict[str, tuple[ActiveVisionResearchEpisode, ...]],
    ) -> None:
        self._episodes_by_split = {
            split: tuple(episodes_by_split[split])
            for split in ("train", "validation", "test")
        }
        self.episode_descriptors = tuple(
            {
                "episode_uid": f"{episode.scenario_version}:{episode.seed}:{episode.episode_id}",
                "scenario_version": episode.scenario_version,
                "seed": episode.seed,
                "episode_id": episode.episode_id,
                "split": split,
                "sample_count": len(episode.transitions),
                "synthetic_fixture": episode.synthetic_fixture,
            }
            for split in ("train", "validation", "test")
            for episode in self._episodes_by_split[split]
        )
        seeds_by_split = {
            split: sorted({episode.seed for episode in self._episodes_by_split[split]})
            for split in ("train", "validation", "test")
        }
        self.manifest_sha256 = "d" * 64
        self.manifest = {
            "schema_version": "d5.active-vision-episode-dataset.v3",
            "split_sha256": "e" * 64,
            "training_set_sha256": "f" * 64,
            "availability": {
                name: {
                    "status": "unavailable",
                    "sample_count": sum(
                        len(episode.transitions)
                        for episodes in self._episodes_by_split.values()
                        for episode in episodes
                    ),
                    "available_sample_count": 0,
                }
                for name in ("outcome", "reward", "counterfactual", "causal_label")
            },
            "canonical_seed_view": {
                "training_seed_registry": {
                    "schema_version": "scalable3d-training-seed-registry-v1",
                    "file_sha256": "1" * 64,
                },
                "shared_seed_registry": {
                    "schema_version": "scalable3d-shared-seed-split-registry-v1",
                    "file_sha256": "2" * 64,
                },
                "canonical_split": {
                    "seed_values": seeds_by_split,
                    "reserved_evaluation_seed_overlap": [],
                },
                "view_contract": {
                    "sample_copy_allowed": False,
                },
            },
        }

    def split_descriptors(self, split: str) -> tuple[dict[str, object], ...]:
        return tuple(
            item for item in self.episode_descriptors if item["split"] == split
        )

    def iter_behavior_cloning_episodes(
        self,
        split: str,
    ):
        return iter(self._episodes_by_split[split])


def _episode(seed: int) -> ActiveVisionResearchEpisode:
    source = ActiveVisionSourceIdentityV1(
        git_commit="a" * 40,
        git_dirty=True,
        config_sha256="b" * 64,
    )
    record, _ = build_active_vision_curriculum_episode(
        seed,
        source_identity=source,
        config=ActiveVisionCurriculumConfig(
            global_track_id="GT-CORPUS-001",
            scenario_version=_SCENARIO,
            episode_id_prefix="corpus-audit",
        ),
    )
    transitions = tuple(
        ActiveVisionTransition(
            snapshot=sample.snapshot,
            camera_id=sample.camera_id,
            selected_action=sample.rule_demonstration_action,
            done=index == len(record.samples) - 1,
        )
        for index, sample in enumerate(record.samples)
    )
    return ActiveVisionResearchEpisode(
        scenario_version=record.scenario_version,
        seed=record.seed,
        episode_id=record.episode_id,
        transitions=transitions,
        synthetic_fixture=record.synthetic_fixture,
    )


def _balanced_dataset() -> _CorpusDataset:
    return _CorpusDataset(
        {
            "train": (_episode(10), _episode(11)),
            "validation": (_episode(20),),
            "test": (_episode(30),),
        }
    )


def _filter_training(
    dataset: _CorpusDataset,
    predicate,
) -> _CorpusDataset:
    return _CorpusDataset(
        {
            "train": tuple(
                replace(
                    episode,
                    transitions=tuple(
                        transition
                        for transition in episode.transitions
                        if predicate(transition)
                    ),
                )
                for episode in dataset._episodes_by_split["train"]
            ),
            "validation": dataset._episodes_by_split["validation"],
            "test": dataset._episodes_by_split["test"],
        }
    )


def _recompute_content_sha256(value: dict[str, object]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def test_balanced_development_fixture_passes_structure_only_without_authority() -> None:
    report = audit_active_vision_training_corpus(_balanced_dataset())

    assert report["training_gate"]["development_training_allowed"] is True
    assert report["training_gate"]["status"] == "pass_development_corpus_only"
    assert report["collection_plan"]["requests"] == []
    assert report["training_inventory"]["by_action_intent"]["hold"] == {
        "unique_sample_count": 4,
        "unique_episode_count": 2,
        "unique_seed_count": 2,
        "unique_scenario_count": 1,
    }
    assert report["training_inventory"]["by_camera_role"]["recon"][
        "unique_sample_count"
    ] == 12
    assert report["evidence_availability"]["formal_candidate"]["available"] is False
    assert report["evidence_availability"][
        "non_synthetic_unseen_seed_evidence"
    ]["available"] is False
    assert all(value is False for value in report["authority"].values())
    assert report["scope"]["online_truth_identifier_consumed"] is False
    assert report["scope"]["global_track_id_created_or_rewritten"] is False
    validate_active_vision_corpus_audit(report)


def test_missing_hold_and_minority_action_generate_deterministic_requests() -> None:
    source = _balanced_dataset()
    retained_search_roles: set[str] = set()

    def retain_all_but_hold_and_duplicate_search(transition) -> bool:
        if transition.selected_action.intent is ActiveVisionIntent.HOLD:
            return False
        if transition.selected_action.intent is not ActiveVisionIntent.SEARCH_SECTOR:
            return True
        role = active_vision_camera_role(
            transition.snapshot.camera(transition.camera_id).resource_id
        )
        if role in retained_search_roles:
            return False
        retained_search_roles.add(role)
        return True

    filtered = _filter_training(
        source,
        retain_all_but_hold_and_duplicate_search,
    )

    report = audit_active_vision_training_corpus(filtered)

    assert report["training_gate"]["development_training_allowed"] is False
    reasons = report["training_gate"]["failure_reasons"]
    assert "hold_demonstration_missing" in reasons
    assert "intent_sample_coverage_below_minimum:hold" in reasons
    assert "intent_sample_coverage_below_minimum:search_sector" in reasons
    assert "intent_seed_coverage_below_minimum:search_sector" in reasons
    hold_requests = [
        item
        for item in report["collection_plan"]["requests"]
        if item["action_intent"] == "hold"
    ]
    assert [item["camera_role"] for item in hold_requests] == [
        "interceptor",
        "recon",
    ]
    assert all(
        item["minimum_additional_new_training_seeds"] == 2
        for item in hold_requests
    )
    assert [item["request_id"] for item in report["collection_plan"]["requests"]] == [
        f"AV-CORPUS-{index:03d}"
        for index in range(1, len(report["collection_plan"]["requests"]) + 1)
    ]
    assert report["scope"]["sample_reweighting_used_for_coverage"] is False


def test_missing_runtime_action_role_cells_fail_closed_with_unique_requests() -> None:
    missing_cells = {
        (ActiveVisionIntent.HOLD.value, "interceptor"),
        (ActiveVisionIntent.HOLD.value, "recon"),
        (ActiveVisionIntent.SEARCH_SECTOR.value, "recon"),
    }

    def retain_other_cells(transition) -> bool:
        role = active_vision_camera_role(
            transition.snapshot.camera(transition.camera_id).resource_id
        )
        return (transition.selected_action.intent.value, role) not in missing_cells

    report = audit_active_vision_training_corpus(
        _filter_training(_balanced_dataset(), retain_other_cells)
    )

    assert report["training_gate"]["status"] == "fail_closed_training_corpus"
    assert report["training_gate"]["development_training_allowed"] is False
    pair_inventory = report["training_inventory"][
        "by_action_intent_and_camera_role"
    ]
    for intent, role in missing_cells:
        assert pair_inventory[intent][role] == {
            "unique_sample_count": 0,
            "unique_episode_count": 0,
            "unique_seed_count": 0,
            "unique_scenario_count": 0,
        }
        prefix = f"intent_camera_role:{intent}:{role}"
        assert f"{prefix}:sample_coverage_below_minimum" in report[
            "training_gate"
        ]["failure_reasons"]
        assert f"{prefix}:episode_coverage_below_minimum" in report[
            "training_gate"
        ]["failure_reasons"]
        assert f"{prefix}:seed_coverage_below_minimum" in report[
            "training_gate"
        ]["failure_reasons"]

    requests = {
        (item["action_intent"], item["camera_role"]): item
        for item in report["collection_plan"]["requests"]
    }
    assert set(requests) == missing_cells
    for item in requests.values():
        assert item["minimum_additional_unique_samples"] == 2
        assert item["minimum_additional_unique_episodes"] == 2
        assert item["minimum_additional_new_training_seeds"] == 2

    with pytest.raises(
        ActiveVisionCorpusCoverageError,
        match="active-vision training corpus failed closed",
    ):
        require_active_vision_training_corpus_ready(
            {"training_corpus_audit": report}
        )


def test_duplicate_episode_is_rejected_and_does_not_inflate_coverage() -> None:
    first = _episode(10)
    second = _episode(11)
    dataset = _CorpusDataset(
        {
            "train": (first, first, second),
            "validation": (_episode(20),),
            "test": (_episode(30),),
        }
    )

    report = audit_active_vision_training_corpus(dataset)

    assert report["training_gate"]["development_training_allowed"] is False
    assert "duplicate_episode_descriptor" in report["training_gate"][
        "failure_reasons"
    ]
    assert "duplicate_materialized_episode" in report["training_gate"][
        "failure_reasons"
    ]
    assert report["training_inventory"]["raw_episode_count_by_split"]["train"] == 3
    assert report["training_inventory"]["unique_training_episode_count"] == 2
    assert report["training_inventory"]["by_action_intent"]["hold"][
        "unique_sample_count"
    ] == 4
    assert report["scope"]["sample_copy_used_for_coverage"] is False


def test_duplicate_sample_within_episode_is_rejected_without_coverage_inflation() -> None:
    dataset = _balanced_dataset()
    first_episode = dataset._episodes_by_split["train"][0]
    duplicate = first_episode.transitions[0]
    duplicated_episode = replace(
        first_episode,
        transitions=(
            duplicate,
            duplicate,
            *first_episode.transitions[1:],
        ),
    )
    duplicated = _CorpusDataset(
        {
            "train": (
                duplicated_episode,
                dataset._episodes_by_split["train"][1],
            ),
            "validation": dataset._episodes_by_split["validation"],
            "test": dataset._episodes_by_split["test"],
        }
    )

    report = audit_active_vision_training_corpus(duplicated)

    assert report["training_gate"]["development_training_allowed"] is False
    assert "duplicate_sample_within_episode" in report["training_gate"][
        "failure_reasons"
    ]
    inventory = report["training_inventory"]
    assert inventory["raw_sample_count_by_split"]["train"] == 25
    assert inventory["eligible_sample_count_by_split"]["train"] == 24
    assert inventory["duplicate_sample_count_by_split"]["train"] == 1
    assert inventory["excluded_sample_reason_counts"][
        "duplicate_sample_within_episode"
    ] == 1
    assert inventory["by_action_intent"]["hold"]["unique_sample_count"] == 4
    assert report["scope"]["sample_copy_used_for_coverage"] is False


def test_missing_recon_camera_role_fails_closed() -> None:
    dataset = _filter_training(
        _balanced_dataset(),
        lambda transition: (
            active_vision_camera_role(
                transition.snapshot.camera(transition.camera_id).resource_id
            )
            == "interceptor"
        ),
    )

    report = audit_active_vision_training_corpus(dataset)

    assert report["training_inventory"]["by_camera_role"]["recon"][
        "unique_sample_count"
    ] == 0
    assert "recon_camera_training_data_missing" in report["training_gate"][
        "failure_reasons"
    ]
    assert {
        item["action_intent"]
        for item in report["collection_plan"]["requests"]
        if item["camera_role"] == "recon"
    } == {"hold", "observe_target", "reacquire", "search_sector"}


def test_seed_split_pollution_and_reserved_seed_use_are_rejected() -> None:
    training = (_episode(10), _episode(11))
    contaminated_validation = replace(
        _episode(10),
        episode_id="corpus-audit-validation-copy",
    )
    dataset = _CorpusDataset(
        {
            "train": training,
            "validation": (contaminated_validation,),
            "test": (_episode(30),),
        }
    )

    report = audit_active_vision_training_corpus(
        dataset,
        reserved_evaluation_seeds=(10, 1000),
    )

    reasons = report["training_gate"]["failure_reasons"]
    assert "seed_split_pollution" in reasons
    assert "training_evaluation_seed_overlap" in reasons
    assert "training_reserved_seed_overlap" in reasons
    assert report["split_integrity"]["training_evaluation_seed_overlap"] == [10]
    assert report["split_integrity"]["training_reserved_seed_overlap"] == [10]
    assert report["training_inventory"]["eligible_sample_count_by_split"]["train"] == 12


def test_nonfinite_candidate_features_are_excluded_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = corpus_module.active_vision_candidate_batch
    call_count = 0

    def nonfinite_once(snapshot, *, camera_id):
        nonlocal call_count
        call_count += 1
        batch = original(snapshot, camera_id=camera_id)
        if call_count == 1:
            return SimpleNamespace(
                actions=(batch.actions[0],),
                features=np.full(
                    (1, len(ACTIVE_VISION_FEATURE_NAMES)),
                    np.nan,
                    dtype=np.float32,
                ),
            )
        return batch

    monkeypatch.setattr(
        corpus_module,
        "active_vision_candidate_batch",
        nonfinite_once,
    )

    report = audit_active_vision_training_corpus(_balanced_dataset())

    assert "training_corpus_nonfinite_features" in report["training_gate"][
        "failure_reasons"
    ]
    assert report["training_inventory"]["excluded_sample_reason_counts"][
        "nonfinite_candidate_features"
    ] == 1
    assert report["training_gate"]["development_training_allowed"] is False


@dataclass(frozen=True)
class _TruthContaminatedTransition:
    snapshot: object
    camera_id: str
    selected_action: object
    truth_actor_id: str


def test_truth_field_is_detected_without_becoming_training_coverage() -> None:
    dataset = _balanced_dataset()
    episode = dataset._episodes_by_split["train"][0]
    first = episode.transitions[0]
    contaminated = _TruthContaminatedTransition(
        snapshot=first.snapshot,
        camera_id=first.camera_id,
        selected_action=first.selected_action,
        truth_actor_id="sim-actor-001",
    )
    poisoned_episode = replace(
        episode,
        transitions=(contaminated, *episode.transitions[1:]),
    )
    poisoned = _CorpusDataset(
        {
            "train": (
                poisoned_episode,
                dataset._episodes_by_split["train"][1],
            ),
            "validation": dataset._episodes_by_split["validation"],
            "test": dataset._episodes_by_split["test"],
        }
    )

    report = audit_active_vision_training_corpus(poisoned)

    assert "training_corpus_truth_identity_forbidden" in report["training_gate"][
        "failure_reasons"
    ]
    assert report["training_inventory"]["excluded_sample_reason_counts"][
        "truth_identity_field_detected"
    ] == 1
    assert report["scope"]["online_truth_identifier_consumed"] is False
    assert report["authority"]["global_track_id_write_authority_granted"] is False


def test_output_is_deterministic_when_episode_order_changes() -> None:
    forward = _balanced_dataset()
    reverse = _CorpusDataset(
        {
            split: tuple(reversed(forward._episodes_by_split[split]))
            for split in ("train", "validation", "test")
        }
    )

    first = audit_active_vision_training_corpus(forward)
    second = audit_active_vision_training_corpus(reverse)

    assert first == second
    assert first["content_sha256"] == second["content_sha256"]


def test_legacy_cache_and_permission_escalation_are_fail_closed() -> None:
    with pytest.raises(
        ActiveVisionCorpusCoverageError,
        match="legacy cache is fail-closed",
    ):
        require_active_vision_training_corpus_ready(
            {"schema_version": "d5.active-vision-bc-cache.v1"}
        )

    report = audit_active_vision_training_corpus(_balanced_dataset())
    escalated = json.loads(json.dumps(report))
    escalated["authority"]["active_vision_authority_granted"] = True
    escalated["content_sha256"] = _recompute_content_sha256(escalated)
    with pytest.raises(
        ActiveVisionCorpusCoverageError,
        match="permission escalation",
    ):
        validate_active_vision_corpus_audit(escalated)

    false_formal = json.loads(json.dumps(report))
    false_formal["evidence_availability"]["formal_candidate"]["available"] = True
    false_formal["content_sha256"] = _recompute_content_sha256(false_formal)
    with pytest.raises(
        ActiveVisionCorpusCoverageError,
        match="must remain unavailable",
    ):
        validate_active_vision_corpus_audit(false_formal)


def test_feature_cache_binds_passing_audit_before_training(tmp_path) -> None:
    manifest, data_audit, manifest_sha = build_behavior_cloning_feature_cache(
        _balanced_dataset(),
        tmp_path / "cache",
    )
    loaded_manifest, caches, loaded_sha = load_behavior_cloning_feature_cache(
        tmp_path / "cache"
    )

    assert manifest_sha == loaded_sha
    assert manifest["training_corpus_audit"]["training_gate"][
        "development_training_allowed"
    ] is True
    assert data_audit["behavior_cloning_readiness"]["full_split_training_allowed"] is True
    _, _, training = train_cached_behavior_cloning(
        loaded_manifest,
        caches,
        config=ActiveVisionBcConfig(
            seed=17,
            epochs=1,
            batch_size=8,
            evaluation_batch_size=8,
            hidden_dim=8,
            cpu_threads=1,
            latency_samples=1,
            latency_warmup=0,
        ),
    )
    assert (
        training["training_corpus_audit_sha256"]
        == manifest["training_corpus_audit"]["content_sha256"]
    )
