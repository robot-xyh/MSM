from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningSplit,
)
from d4_distributed_fallback.region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256,
    REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT,
    REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT,
    REGION_RESOURCE_EIGHT_REGION_COUNT,
    REGION_RESOURCE_EIGHT_REGION_READINESS_CONFIG_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_DATASET_SHA256,
    REGION_RESOURCE_EIGHT_REGION_READINESS_EPISODE_COUNT,
    REGION_RESOURCE_EIGHT_REGION_READINESS_FRAME_COUNT,
    REGION_RESOURCE_EIGHT_REGION_READINESS_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_EIGHT_REGION_READINESS_MODEL_VERSION,
    REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_READINESS_SOURCE_COMMIT,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_ADVISORY_TTL_S,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_VIEW_RECIPE,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_VIEW_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_VALUE_COUNT,
    REGION_RESOURCE_EIGHT_REGION_READINESS_ZERO_VALUE_COUNT,
    REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256,
    REGION_RESOURCE_EIGHT_REGION_RUNTIME_EPISODE_COUNT,
    REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT,
    REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS,
    RegionResourceEightRegionCandidateConfig,
    RegionResourceEightRegionCandidateError,
    RegionResourceEightRegionReadinessV3CandidateConfig,
    _build_readiness_training_view_manifest,
    _build_training_view_dataset,
    _load_verified_source,
    _readiness_runtime_confidence_gate_acceptance,
    _readiness_confidence_supervision_definition_from_base,
    _readiness_runtime_context,
    _sha256_json,
    _split_usage,
    _validate_global_training_seeds,
    _validate_readiness_training_view_manifest,
    load_verified_eight_region_readiness_source,
)
from d4_distributed_fallback.region_resource_dataset import (
    load_region_learning_dataset_splits,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DATASET = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/outputs"
    / "learning_generation_v1_multibatchfix/learning_dataset/d4_region"
)
ACTION_DATASET = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/outputs"
    / "region_action_coverage_curriculum_20260721_clean_9445ed6/dataset"
)
READINESS_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/outputs"
    / "d4_readiness_supplement_20v20_8region_q2_seed0_99_20260728"
)
READINESS_DATASET = READINESS_ROOT / "learning_dataset/d4_region"
READINESS_SUMMARY = READINESS_ROOT / "generation_summary.json"
READINESS_AUDIT = READINESS_ROOT / "d4_dataset_audit.json"


@pytest.fixture(scope="module")
def three_sources() -> tuple[
    LoadedRegionLearningDataset,
    LoadedRegionLearningDataset,
    LoadedRegionLearningDataset,
]:
    runtime = _load_verified_source(
        RUNTIME_DATASET,
        expected_sha256=REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256,
        expected_episode_count=REGION_RESOURCE_EIGHT_REGION_RUNTIME_EPISODE_COUNT,
        expected_frame_count=REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT,
        expected_region_count=REGION_RESOURCE_EIGHT_REGION_COUNT,
        expected_action_inventory={
            "action_count": 14384,
            "resource_quota_nonzero_count": 0,
            "transfer_count": 0,
            "hold_true_count": 0,
            "request_replan_true_count": 0,
        },
        source_name="runtime",
    )
    action = _load_verified_source(
        ACTION_DATASET,
        expected_sha256=REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256,
        expected_episode_count=REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT,
        expected_frame_count=REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT,
        expected_region_count=4,
        expected_action_inventory={
            "action_count": 1200,
            "resource_quota_nonzero_count": 200,
            "transfer_count": 100,
            "hold_true_count": 100,
            "request_replan_true_count": 200,
        },
        source_name="action_curriculum",
    )
    readiness, _ = load_verified_eight_region_readiness_source(
        READINESS_DATASET,
        generation_summary_path=READINESS_SUMMARY,
        dataset_audit_path=READINESS_AUDIT,
    )
    return runtime, action, readiness


def test_authentic_readiness_source_is_exactly_bound_and_truth_free() -> None:
    loaded, evidence = load_verified_eight_region_readiness_source(
        READINESS_DATASET,
        generation_summary_path=READINESS_SUMMARY,
        dataset_audit_path=READINESS_AUDIT,
    )
    assert loaded.manifest.dataset_sha256 == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_DATASET_SHA256
    )
    assert evidence["manifest_file_sha256"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_MANIFEST_FILE_SHA256
    )
    assert evidence["source_git_commit"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_SOURCE_COMMIT
    )
    assert evidence["repository_dirty"] is False
    assert evidence["episode_count"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_EPISODE_COUNT
    )
    assert evidence["frame_count"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_FRAME_COUNT
    )
    assert evidence["region_value_count"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_VALUE_COUNT
    )
    assert evidence["secondary_readiness_zero_value_count"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_ZERO_VALUE_COUNT
    )
    assert evidence["secondary_readiness_minimum"] == 0.0
    assert evidence["secondary_readiness_maximum"] == 1.0
    assert evidence["online_truth_use_count"] == 0
    assert evidence["all_frames_rule_labeled"] is True


def test_readiness_metadata_tamper_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(READINESS_SUMMARY.read_text(encoding="utf-8"))
    payload["online_truth_use_count"] = 1
    tampered = tmp_path / "generation_summary.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="readiness_evidence_file_sha256_mismatch",
    ):
        load_verified_eight_region_readiness_source(
            READINESS_DATASET,
            generation_summary_path=tampered,
            dataset_audit_path=READINESS_AUDIT,
        )


def test_three_source_numeric_seed_inventory_is_global_and_reserved_free(
    three_sources: tuple[
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
    ],
) -> None:
    runtime, action, readiness = three_sources
    _validate_global_training_seeds(runtime, action, readiness)
    expected = set(REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS)
    assert {
        int(item.source.seed) for item in runtime.episode_records
    } == expected
    assert {
        int(item.source.seed) for item in action.episode_records
    } == expected
    assert {
        int(item.source.seed) for item in readiness.episode_records
    } == expected
    assert not expected & set(range(1000, 1020))


def test_readiness_reserved_seed_is_hard_rejected(
    three_sources: tuple[
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
    ],
) -> None:
    runtime, action, readiness = three_sources
    first = readiness.episode_records[0]
    bad_source = replace(
        first.source,
        seed=1000,
        episode_id=first.source.episode_id + "-reserved",
    )
    bad_readiness = replace(
        readiness,
        episode_records=(
            replace(first, source=bad_source),
            *readiness.episode_records[1:],
        ),
    )
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="readiness_supplement_reserved_evaluation_seed_present",
    ):
        _validate_global_training_seeds(runtime, action, bad_readiness)


def test_three_source_composite_uses_one_atomic_split_per_numeric_seed(
    three_sources: tuple[
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
    ],
    tmp_path: Path,
) -> None:
    runtime, action, readiness = three_sources
    config = RegionResourceEightRegionCandidateConfig(
        candidate_id=REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID,
        model_version=REGION_RESOURCE_EIGHT_REGION_READINESS_MODEL_VERSION,
        schema=REGION_RESOURCE_EIGHT_REGION_READINESS_CONFIG_SCHEMA,
    )
    composite = _build_training_view_dataset(
        runtime,
        action,
        readiness=readiness,
        staging_root=tmp_path / "three_source_view",
        config=config,
        source_git_commit="a" * 40,
        source_identity_sha256="b" * 64,
    )
    dataset = composite["dataset"]
    assert dataset.manifest.availability.episode_count == 1100
    assert dataset.manifest.availability.frame_count == 2297
    split_by_seed: dict[int, set[RegionLearningSplit]] = {}
    scenario_count_by_seed: dict[int, int] = {}
    for episode in dataset.episode_records:
        seed = int(episode.source.seed)
        split_by_seed.setdefault(seed, set()).add(episode.split)
        scenario_count_by_seed[seed] = (
            scenario_count_by_seed.get(seed, 0) + 1
        )
    assert set(split_by_seed) == set(
        REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS
    )
    assert all(len(splits) == 1 for splits in split_by_seed.values())
    assert all(count >= 3 for count in scenario_count_by_seed.values())
    assert not set(split_by_seed) & set(range(1000, 1020))


def test_v3_view_binds_main_runtime_projection_contract(
    three_sources: tuple[
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
        LoadedRegionLearningDataset,
    ],
    tmp_path: Path,
) -> None:
    runtime, action, readiness = three_sources
    config = RegionResourceEightRegionReadinessV3CandidateConfig()
    composite = _build_training_view_dataset(
        runtime,
        action,
        readiness=readiness,
        staging_root=tmp_path / "v3_view",
        config=config,
        source_git_commit="a" * 40,
        source_identity_sha256="b" * 64,
    )
    loaded = load_region_learning_dataset_splits(
        composite["dataset"].root,
        splits=(
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ),
    )
    _, readiness_evidence = load_verified_eight_region_readiness_source(
        READINESS_DATASET,
        generation_summary_path=READINESS_SUMMARY,
        dataset_audit_path=READINESS_AUDIT,
    )
    view = _build_readiness_training_view_manifest(
        runtime,
        action,
        readiness,
        readiness_evidence,
        composite,
        split_usage=_split_usage(loaded),
        source_summary={"source_identity_sha256": "b" * 64},
        config=config,
    )

    assert view["schema"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_VIEW_SCHEMA
    )
    assert view["view_recipe"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_VIEW_RECIPE
    )
    gate = view["confidence_supervision"]["runtime_gate"]
    assert gate["projection_config"] == {
        "minimum_reserve_ratio": 0.1,
        "minimum_reserve_resources": 1,
        "advisory_ttl_s": (
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_ADVISORY_TTL_S
        ),
    }
    assert gate["rule_policy_config"]["projection"] == (
        gate["projection_config"]
    )
    assert gate["fixed_ood_margin"] == 0.05
    assert gate["fixed_minimum_confidence"] == 0.60
    assert gate["inconsistent_confidence_cap"] == 0.59
    assert gate["continuous_tolerance"] == 0.10
    split_usage = view["global_split"]["split_usage"]
    assert split_usage["test_payload_read_count"] == 0
    assert split_usage["calibration_seed_use_count"] == 0
    assert split_usage["reserved_seed_use_count"] == 0
    assert not (
        set(view["global_split"]["train_seeds"])
        | set(view["global_split"]["validation_seeds"])
    ) & set(range(1000, 1020))

    v2_config = RegionResourceEightRegionCandidateConfig(
        candidate_id=REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID,
        model_version=REGION_RESOURCE_EIGHT_REGION_READINESS_MODEL_VERSION,
        schema=REGION_RESOURCE_EIGHT_REGION_READINESS_CONFIG_SCHEMA,
    )
    _, _, v2_gate = _readiness_runtime_context(v2_config)
    tampered = deepcopy(view)
    tampered["confidence_supervision"] = (
        _readiness_confidence_supervision_definition_from_base(
            tampered["confidence_supervision"]["head_fit_definition"],
            runtime_gate=v2_gate,
        )
    )
    tampered["content_sha256"] = _sha256_json(
        {
            key: value
            for key, value in tampered.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="readiness_training_view_confidence_boundary_crossed",
    ):
        _validate_readiness_training_view_manifest(tampered)


def test_runtime_gate_acceptance_keeps_auditable_pass_coverage() -> None:
    acceptance = _readiness_runtime_confidence_gate_acceptance(
        {
            "sample_count": 20,
            "threshold_pass_count": 5,
            "action_inconsistent_threshold_pass_count": 0,
        }
    )
    assert acceptance["minimum_threshold_pass_count"] == 1
    assert acceptance["accepted"] is True


def test_runtime_gate_acceptance_rejects_zero_pass_evasion() -> None:
    acceptance = _readiness_runtime_confidence_gate_acceptance(
        {
            "sample_count": 20,
            "threshold_pass_count": 0,
            "action_inconsistent_threshold_pass_count": 0,
        }
    )
    assert acceptance["accepted"] is False
    assert acceptance["blockers"] == [
        "validation_threshold_pass_coverage_below_audit_floor:0<1"
    ]


def test_runtime_gate_acceptance_rejects_inconsistent_threshold_pass() -> None:
    acceptance = _readiness_runtime_confidence_gate_acceptance(
        {
            "sample_count": 20,
            "threshold_pass_count": 5,
            "action_inconsistent_threshold_pass_count": 1,
        }
    )
    assert acceptance["accepted"] is False
    assert acceptance["blockers"] == [
        "validation_action_inconsistent_threshold_pass:1"
    ]
