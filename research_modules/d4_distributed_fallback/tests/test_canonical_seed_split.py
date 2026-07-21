from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

from d4_distributed_fallback.canonical_seed_split import (
    CANONICAL_REGION_SPLIT_AUDIT_SCHEMA,
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
    CanonicalRegionSplitError,
    audit_canonical_region_learning_split_view,
    load_canonical_region_learning_split_view,
)
from d4_distributed_fallback.region_resource import (
    RegionResourceNode,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningDataUnavailableError,
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningSplit,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    stage_region_learning_episode,
)
from d4_distributed_fallback.region_resource_learning import (
    load_region_behavior_cloning_samples,
    load_region_ppo_training_episodes,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


@pytest.fixture(scope="module")
def canonical_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, Path]:
    root = tmp_path_factory.mktemp("canonical-region-split")
    stage = root / "stage"
    for seed in range(100):
        source = _source(seed)
        stage_region_learning_episode(stage, source, (_frame(source),))
    dataset = root / "dataset"
    finalize_region_learning_dataset(
        stage,
        dataset,
        created_at_utc="2026-07-21T12:00:00Z",
        split_seed=17,
        minimum_unseen_seeds=20,
    )
    source_registry = root / "training_seed_registry.json"
    source_payload = _source_registry_payload()
    _write_json(source_registry, source_payload)
    shared_registry = root / "shared_seed_split_registry.json"
    _write_json(
        shared_registry,
        _shared_registry_payload(
            source_payload,
            source_registry_sha256=_sha256_file(source_registry),
        ),
    )
    return dataset, source_registry, shared_registry


def test_canonical_view_maps_all_100_seeds_to_d3_compatible_60_20_20(
    canonical_fixture: tuple[Path, Path, Path],
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture

    view = load_canonical_region_learning_split_view(
        dataset,
        shared_registry_path=shared_registry,
        training_seed_registry_path=source_registry,
    )
    report = audit_canonical_region_learning_split_view(view)

    assert report["schema"] == CANONICAL_REGION_SPLIT_AUDIT_SCHEMA
    assert report["canonical_split"]["seed_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert report["canonical_split"]["episode_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert report["canonical_split"]["numeric_seed_atomic"]
    assert not report["canonical_split"]["reserved_seed_present"]
    assert len(view.binding.reserved_evaluation_seeds) == 20
    assert not report["readiness"]["ppo_available"]
    assert not report["readiness"]["assist_eligible"]
    assert report["readiness"]["development_data_governance_only"]


@pytest.mark.parametrize("field", ["schema_version", "policy_version"])
def test_shared_registry_rejects_schema_or_policy_change(
    canonical_fixture: tuple[Path, Path, Path],
    tmp_path: Path,
    field: str,
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    payload = _read_json(shared_registry)
    payload[field] = "unsupported-v9"
    _refresh_content_hash(payload)
    tampered = tmp_path / f"{field}.json"
    _write_json(tampered, payload)

    with pytest.raises(CanonicalRegionSplitError) as error:
        load_canonical_region_learning_split_view(
            dataset,
            shared_registry_path=tampered,
            training_seed_registry_path=source_registry,
        )

    assert error.value.code in {
        "shared_registry_schema_mismatch",
        "shared_registry_policy_mismatch",
    }


@pytest.mark.parametrize("hash_field", ["content_sha256", "assignment_sha256"])
def test_shared_registry_rejects_tampered_hash(
    canonical_fixture: tuple[Path, Path, Path],
    tmp_path: Path,
    hash_field: str,
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    payload = _read_json(shared_registry)
    payload[hash_field] = "0" * 64
    if hash_field == "assignment_sha256":
        _refresh_content_hash(payload)
    tampered = tmp_path / f"tampered-{hash_field}.json"
    _write_json(tampered, payload)

    with pytest.raises(CanonicalRegionSplitError) as error:
        load_canonical_region_learning_split_view(
            dataset,
            shared_registry_path=tampered,
            training_seed_registry_path=source_registry,
        )

    assert error.value.code == f"{hash_field}_mismatch"


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_shared_registry_rejects_missing_or_extra_seed(
    canonical_fixture: tuple[Path, Path, Path],
    tmp_path: Path,
    mutation: str,
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    payload = _read_json(shared_registry)
    assignments = list(payload["assignments"])
    if mutation == "missing":
        assignments = assignments[1:]
    else:
        assignments.append({"seed": 999, "split": "train"})
        assignments.sort(key=lambda item: item["seed"])
    payload["assignments"] = assignments
    _refresh_assignment_catalogs_and_hashes(payload)
    tampered = tmp_path / f"{mutation}.json"
    _write_json(tampered, payload)

    with pytest.raises(CanonicalRegionSplitError) as error:
        load_canonical_region_learning_split_view(
            dataset,
            shared_registry_path=tampered,
            training_seed_registry_path=source_registry,
        )

    assert error.value.code == "registry_seed_coverage_mismatch"


def test_shared_registry_rejects_reserved_seed_assignment(
    canonical_fixture: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    payload = _read_json(shared_registry)
    payload["assignments"].append({"seed": 1000, "split": "test"})
    payload["assignments"].sort(key=lambda item: item["seed"])
    _refresh_assignment_catalogs_and_hashes(payload)
    tampered = tmp_path / "reserved.json"
    _write_json(tampered, payload)

    with pytest.raises(CanonicalRegionSplitError) as error:
        load_canonical_region_learning_split_view(
            dataset,
            shared_registry_path=tampered,
            training_seed_registry_path=source_registry,
        )

    assert error.value.code == "reserved_seed_assigned"


def test_shared_registry_rejects_source_registry_sha_mismatch(
    canonical_fixture: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    source_payload = _read_json(source_registry)
    source_payload["repository_dirty"] = True
    changed_source = tmp_path / "changed-source.json"
    _write_json(changed_source, source_payload)

    with pytest.raises(CanonicalRegionSplitError) as error:
        load_canonical_region_learning_split_view(
            dataset,
            shared_registry_path=shared_registry,
            training_seed_registry_path=changed_source,
        )

    assert error.value.code == "source_registry_sha256_mismatch"


def test_dataset_seed_missing_extra_and_reserved_fail_closed(
    canonical_fixture: tuple[Path, Path, Path],
) -> None:
    dataset_path, source_registry, shared_registry = canonical_fixture
    loaded = load_region_learning_dataset(dataset_path)
    missing = replace(loaded, episode_records=loaded.episode_records[1:])
    original = loaded.episode_records[0]
    extra_source = replace(original.source, seed=999, episode_id="extra-seed")
    extra = replace(
        loaded,
        episode_records=(
            *loaded.episode_records,
            replace(original, source=extra_source),
        ),
    )
    reserved_source = replace(original.source, seed=1000, episode_id="reserved-seed")
    reserved = replace(
        loaded,
        episode_records=(
            *loaded.episode_records[1:],
            replace(original, source=reserved_source),
        ),
    )

    for candidate, code in (
        (missing, "dataset_seed_coverage_mismatch"),
        (extra, "dataset_seed_coverage_mismatch"),
        (reserved, "reserved_seed_in_dataset"),
    ):
        with pytest.raises(CanonicalRegionSplitError) as error:
            load_canonical_region_learning_split_view(
                candidate,
                shared_registry_path=shared_registry,
                training_seed_registry_path=source_registry,
            )
        assert error.value.code == code


def test_canonical_view_does_not_modify_source_dataset(
    canonical_fixture: tuple[Path, Path, Path],
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    before = _tree_sha256(dataset)

    view = load_canonical_region_learning_split_view(
        dataset,
        shared_registry_path=shared_registry,
        training_seed_registry_path=source_registry,
        expected_training_seed_registry_sha256=_sha256_file(source_registry),
    )
    assert audit_canonical_region_learning_split_view(view)
    assert load_region_behavior_cloning_samples(
        dataset,
        canonical_split_view=view,
    )

    assert _tree_sha256(dataset) == before


def test_bc_loader_requires_explicit_canonical_view_and_keeps_legacy_default(
    canonical_fixture: tuple[Path, Path, Path],
) -> None:
    dataset, source_registry, shared_registry = canonical_fixture
    loaded = load_region_learning_dataset(dataset)
    view = load_canonical_region_learning_split_view(
        loaded,
        shared_registry_path=shared_registry,
        training_seed_registry_path=source_registry,
    )

    legacy_train = load_region_behavior_cloning_samples(loaded)
    canonical_train = load_region_behavior_cloning_samples(
        loaded,
        canonical_split_view=view,
    )
    canonical_validation = load_region_behavior_cloning_samples(
        loaded,
        split=RegionLearningSplit.VALIDATION,
        canonical_split_view=view,
    )
    canonical_test = load_region_behavior_cloning_samples(
        loaded,
        split=RegionLearningSplit.TEST,
        canonical_split_view=view,
    )

    assert len(legacy_train) == 70
    assert len(canonical_train) == 60
    assert len(canonical_validation) == 20
    assert len(canonical_test) == 20
    with pytest.raises(RegionLearningDataUnavailableError, match="reward_unavailable"):
        load_region_ppo_training_episodes(loaded)


def _source(seed: int) -> RegionLearningEpisodeSource:
    return RegionLearningEpisodeSource(
        scenario_id="canonical-split-fixture",
        scenario_version="fixture-v1",
        scenario_scale="M5N5",
        seed=seed,
        episode_id=f"canonical-split-seed-{seed}",
        git_commit="a" * 40,
        git_dirty=False,
        config_sha256=sha256(f"fixture:{seed}".encode("utf-8")).hexdigest(),
    )


def _frame(source: RegionLearningEpisodeSource) -> RegionLearningFrame:
    snapshot = RegionResourceSnapshot(
        snapshot_id=f"snapshot-{source.seed}",
        scenario_id=source.scenario_id,
        scenario_version=source.scenario_version,
        seed=source.seed,
        timestamp_s=0.0,
        regions=(
            RegionResourceNode(
                region_id="region-0",
                target_demand=1.0,
                high_threat_backlog=0.0,
                d1_uncertainty=0.1,
                d2_uncertainty=0.1,
                d5_visibility=0.8,
                d5_consistency=0.8,
                available_resources=3,
                reserve_resources=1,
                secondary_coverage=0.8,
                secondary_readiness=0.8,
                communication_capacity=10.0,
                communication_latency_s=0.02,
                packet_loss_rate=0.01,
                current_owner_id="CENTER",
                current_owner_layer=RegionalAuthorityLayer.CENTER,
                plan_id="plan-fixture",
                plan_version=1,
                epoch=1,
                lease_expires_at_s=30.0,
            ),
        ),
        edges=(),
    )
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)
    return RegionLearningFrame(
        frame_index=0,
        timestamp_s=0.0,
        snapshot=snapshot,
        target=RegionLearningTarget.available(
            RegionLearningTargetKind.RULE,
            recommendation,
        ),
        reward=RegionLearningReward.unavailable("reward_unavailable"),
        recommendation=recommendation,
    )


def _source_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": sha256(b"canonical-schedule").hexdigest(),
        "training_seed_count": 100,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }


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


def _refresh_assignment_catalogs_and_hashes(payload: dict[str, Any]) -> None:
    payload["split_seed_values"] = {
        name: sorted(
            item["seed"] for item in payload["assignments"] if item["split"] == name
        )
        for name in ("train", "validation", "test")
    }
    payload["assignment_sha256"] = _sha256_json(payload["assignments"])
    _refresh_content_hash(payload)


def _refresh_content_hash(payload: dict[str, Any]) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = _sha256_json(payload)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
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


def _tree_sha256(root: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
