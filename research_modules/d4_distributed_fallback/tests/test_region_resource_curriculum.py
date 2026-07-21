from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

from d4_distributed_fallback.canonical_seed_split import (
    EXPECTED_CONSUMER_CONTRACT,
    EXPECTED_MINIMUM_TEST_SEED_COUNT,
    EXPECTED_SPLIT_SEED,
    EXPECTED_TEST_FRACTION,
    EXPECTED_UNIT,
    EXPECTED_VALIDATION_FRACTION,
    ORDERING_COMPATIBILITY_VERSION,
    SHARED_SEED_SPLIT_POLICY_VERSION,
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
)
from d4_distributed_fallback.region_resource_curriculum import (
    CURRICULUM_REWARD_UNAVAILABLE_REASON,
    RegionActionCoverageCurriculumConfig,
    RegionActionCoverageCurriculumError,
    build_region_action_coverage_frames,
    generate_region_action_coverage_curriculum,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningDataUnavailableError,
    RegionLearningEpisodeSource,
    RegionLearningSplit,
)
from d4_distributed_fallback.region_resource_learning import (
    load_region_behavior_cloning_samples,
    load_region_ppo_training_episodes,
)


@pytest.fixture(scope="module")
def curriculum_fixture(
    tmp_path_factory: pytest.TempPathFactory,
):
    root = tmp_path_factory.mktemp("d4-action-coverage-curriculum")
    source_registry, shared_registry = _write_registries(root)
    registry_hashes_before = (
        _sha256_file(source_registry),
        _sha256_file(shared_registry),
    )
    result = generate_region_action_coverage_curriculum(
        root / "curriculum",
        training_seed_registry_path=source_registry,
        shared_seed_registry_path=shared_registry,
        created_at_utc="2026-07-21T12:00:00Z",
        source_git_commit="b" * 40,
        source_repository_dirty=False,
        config=RegionActionCoverageCurriculumConfig(
            region_count=4,
            resource_count=17,
        ),
    )
    return result, source_registry, shared_registry, registry_hashes_before


def test_curriculum_covers_all_actions_and_preserves_hard_constraints(
    curriculum_fixture,
) -> None:
    result, source_registry, shared_registry, registry_hashes_before = (
        curriculum_fixture
    )
    summary = result.summary

    assert summary["dataset"]["episode_count"] == 100
    assert summary["dataset"]["frame_count"] == 300
    assert summary["dataset"]["numeric_seed_count"] == 100
    assert summary["config"]["region_count"] == 4
    assert summary["config"]["resource_count"] == 17
    assert summary["action_inventory"]["total"] == {
        "frame_count": 300,
        "action_count": 1200,
        "hold_true_count": 100,
        "request_replan_true_count": 200,
        "resource_quota_nonzero_count": 200,
        "transfer_count": 100,
        "transferred_resource_count": 300,
    }
    assert summary["safety"]["hard_constraint_violation_count"] == 0
    assert summary["safety"]["resource_conservation_verified"] is True
    assert summary["audit"]["passed"] is True
    assert not (result.output_dir / "_staging").exists()
    assert registry_hashes_before == (
        _sha256_file(source_registry),
        _sha256_file(shared_registry),
    )


def test_curriculum_uses_canonical_60_20_20_seed_view_and_excludes_reserved(
    curriculum_fixture,
) -> None:
    result, _, _, _ = curriculum_fixture
    summary = result.summary

    assert summary["canonical"]["canonical_split"]["seed_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert summary["canonical"]["canonical_split"]["episode_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert summary["canonical"]["canonical_split"]["frame_counts"] == {
        "train": 180,
        "validation": 60,
        "test": 60,
    }
    assert summary["canonical"]["canonical_split"]["numeric_seed_atomic"]
    assert not summary["canonical"]["canonical_split"]["reserved_seed_present"]
    assert summary["truth_isolation"]["reserved_evaluation_seed_count"] == 20
    assert (
        summary["truth_isolation"]["reserved_evaluation_seed_present_count"] == 0
    )
    for split, seed_count in (("train", 60), ("validation", 20), ("test", 20)):
        inventory = summary["action_inventory"]["by_canonical_split"][split]
        assert inventory["hold_true_count"] == seed_count
        assert inventory["request_replan_true_count"] == 2 * seed_count
        assert inventory["resource_quota_nonzero_count"] == 2 * seed_count
        assert inventory["transfer_count"] == seed_count


def test_curriculum_is_truth_free_and_reward_unavailable_blocks_ppo(
    curriculum_fixture,
) -> None:
    result, _, _, _ = curriculum_fixture
    summary = result.summary

    assert summary["truth_isolation"]["online_truth_identifier_count"] == 0
    assert summary["outcome_and_reward"] == {
        "outcome_availability": "unavailable",
        "reward_availability": "unavailable",
        "reward_available_count": 0,
        "reward_unavailable_count": 300,
        "unavailable_reason": CURRICULUM_REWARD_UNAVAILABLE_REASON,
    }
    assert summary["admission"]["behavior_cloning_manifest_available"] is True
    assert summary["admission"]["offline_shadow_evaluation_only"] is True
    assert summary["admission"]["ppo_available"] is False
    assert summary["admission"]["online_assist_available"] is False
    assert summary["admission"]["online_authority_available"] is False

    samples = load_region_behavior_cloning_samples(
        result.dataset,
        split=RegionLearningSplit.TRAIN,
        canonical_split_view=result.canonical_view,
    )
    assert len(samples) == 180
    with pytest.raises(RegionLearningDataUnavailableError, match="reward_unavailable"):
        load_region_ppo_training_episodes(result.dataset)


def test_frame_generation_is_deterministic_and_not_bound_to_equal_counts() -> None:
    config = RegionActionCoverageCurriculumConfig(
        region_count=3,
        resource_count=11,
    )
    source = RegionLearningEpisodeSource(
        scenario_id=config.scenario_id,
        scenario_version=config.scenario_version,
        scenario_scale=config.scenario_scale,
        seed=37,
        episode_id="deterministic-seed-37",
        git_commit="c" * 40,
        git_dirty=False,
        config_sha256=sha256(b"deterministic-curriculum").hexdigest(),
    )

    first = build_region_action_coverage_frames(source, config)
    second = build_region_action_coverage_frames(source, config)

    assert [frame.to_dict() for frame in first] == [frame.to_dict() for frame in second]
    assert all(frame.snapshot.region_count == 3 for frame in first)
    assert all(frame.snapshot.total_resources == 11 for frame in first)
    transfer = first[2].target.recommendation
    assert transfer is not None
    assert transfer.transfers
    assert any(action.resource_quota_delta != 0 for action in transfer.actions)


def test_complete_curriculum_generation_is_content_deterministic(
    curriculum_fixture,
) -> None:
    first, source_registry, shared_registry, _ = curriculum_fixture
    second = generate_region_action_coverage_curriculum(
        first.output_dir.parent / "curriculum-repeat",
        training_seed_registry_path=source_registry,
        shared_seed_registry_path=shared_registry,
        created_at_utc="2026-07-21T12:00:00Z",
        source_git_commit="b" * 40,
        source_repository_dirty=False,
        config=RegionActionCoverageCurriculumConfig(
            region_count=4,
            resource_count=17,
        ),
    )

    assert second.summary["content_sha256"] == first.summary["content_sha256"]
    assert (
        second.dataset.manifest.dataset_sha256
        == first.dataset.manifest.dataset_sha256
    )
    assert (
        second.canonical_view.binding.view_sha256
        == first.canonical_view.binding.view_sha256
    )


def test_curriculum_rejects_reserved_seed_leakage_before_publication(
    tmp_path: Path,
) -> None:
    source_registry, shared_registry = _write_registries(tmp_path)
    source = _read_json(source_registry)
    source["training_seeds"].append(1000)
    source["training_seeds"].sort()
    source["training_seed_count"] = len(source["training_seeds"])
    source["overlap_count"] = 1
    _write_json(source_registry, source)

    with pytest.raises(
        RegionActionCoverageCurriculumError,
        match="training and reserved evaluation seeds overlap",
    ):
        generate_region_action_coverage_curriculum(
            tmp_path / "must-not-publish",
            training_seed_registry_path=source_registry,
            shared_seed_registry_path=shared_registry,
            created_at_utc="2026-07-21T12:00:00Z",
            source_git_commit="d" * 40,
            source_repository_dirty=False,
        )
    assert not (tmp_path / "must-not-publish").exists()


def _write_registries(root: Path) -> tuple[Path, Path]:
    source_registry = root / "training_seed_registry.json"
    source_payload = {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": sha256(b"curriculum-registry-schedule").hexdigest(),
        "training_seed_count": 100,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }
    _write_json(source_registry, source_payload)
    shared_registry = root / "shared_seed_split_registry.json"
    _write_json(
        shared_registry,
        _shared_registry_payload(
            source_payload,
            source_registry_sha256=_sha256_file(source_registry),
        ),
    )
    return source_registry, shared_registry


def _shared_registry_payload(
    source: dict[str, Any], *, source_registry_sha256: str
) -> dict[str, Any]:
    assignment = _d3_assignment(tuple(source["training_seeds"]))
    assignments = [
        {"seed": seed, "split": assignment[seed]} for seed in sorted(assignment)
    ]
    payload = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": ORDERING_COMPATIBILITY_VERSION,
        "source": {
            "training_seed_registry_schema_version": source["schema_version"],
            "training_seed_registry_sha256": source_registry_sha256,
            "git_commit": source["git_commit"],
            "repository_dirty": source["repository_dirty"],
            "schedule_sha256": source["schedule_sha256"],
        },
        "unit": EXPECTED_UNIT,
        "split_seed": EXPECTED_SPLIT_SEED,
        "validation_fraction": EXPECTED_VALIDATION_FRACTION,
        "test_fraction": EXPECTED_TEST_FRACTION,
        "minimum_test_seed_count": EXPECTED_MINIMUM_TEST_SEED_COUNT,
        "training_seed_count": len(source["training_seeds"]),
        "reserved_evaluation_seed_count": len(source["reserved_evaluation_seeds"]),
        "reserved_evaluation_seeds": source["reserved_evaluation_seeds"],
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            name: sorted(seed for seed, split in assignment.items() if split == name)
            for name in ("train", "validation", "test")
        },
        "assignments": assignments,
        "assignment_sha256": _sha256_json(assignments),
        "consumer_contract": dict(EXPECTED_CONSUMER_CONTRACT),
    }
    payload["content_sha256"] = _sha256_json(payload)
    return payload


def _d3_assignment(seeds: tuple[int, ...]) -> dict[int, str]:
    ordered = sorted(
        seeds,
        key=lambda seed: (
            sha256(
                f"{ORDERING_COMPATIBILITY_VERSION}|{EXPECTED_SPLIT_SEED}\0{seed}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            seed,
        ),
    )
    return {
        seed: (
            "test"
            if index < 20
            else "validation"
            if index < 40
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_json(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
