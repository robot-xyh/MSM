from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from d4_distributed_fallback.region_resource_dataset import (
    LoadedRegionLearningDataset,
)
from d4_distributed_fallback.region_resource_current_lineage_shadow import (
    RegionResourceCurrentLineageShadowAdapter,
    RegionResourceCurrentLineageShadowError,
    RegionResourceCurrentLineageShadowPermissions,
    RegionResourceCurrentLineageShadowSeedRegistration,
)
from d4_distributed_fallback.region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256,
    REGION_RESOURCE_EIGHT_REGION_CANDIDATE_FILENAME,
    REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_COUNT,
    REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256,
    REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS,
    RegionResourceEightRegionCandidateError,
    RegionResourceEightRegionPermissions,
    _build_overlay_episode,
    _load_verified_source,
    _select_runtime_donor,
    _validate_global_training_seeds,
    load_region_resource_eight_region_candidate_manifest,
    review_region_resource_eight_region_candidate,
)
from d4_distributed_fallback.region_resource import RegionResourceSnapshot


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
CANDIDATE_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
    / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
)
SOURCE_COMMIT = "923f3f6e91af0f85aed446c66420c834d2de63fb"


def _committed_blob_sha256(relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{relative_path}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return sha256(result.stdout).hexdigest()


@pytest.fixture(scope="module")
def source_datasets() -> tuple[
    LoadedRegionLearningDataset, LoadedRegionLearningDataset
]:
    runtime = _load_verified_source(
        RUNTIME_DATASET,
        expected_sha256=REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256,
        expected_episode_count=900,
        expected_frame_count=1798,
        expected_region_count=8,
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
        expected_episode_count=100,
        expected_frame_count=300,
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
    return runtime, action


def test_source_hashes_counts_and_region_geometry_are_exact(
    source_datasets: tuple[
        LoadedRegionLearningDataset, LoadedRegionLearningDataset
    ],
) -> None:
    runtime, action = source_datasets
    _validate_global_training_seeds(runtime, action)
    assert runtime.manifest.dataset_sha256 == (
        REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256
    )
    assert action.manifest.dataset_sha256 == (
        REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256
    )
    assert {
        frame.snapshot.region_count
        for episode in runtime.episode_records
        for frame in episode.frames
    } == {REGION_RESOURCE_EIGHT_REGION_COUNT}


def test_reserved_evaluation_seed_is_hard_rejected(
    source_datasets: tuple[
        LoadedRegionLearningDataset, LoadedRegionLearningDataset
    ],
) -> None:
    runtime, action = source_datasets
    first = action.episode_records[0]
    bad_source = replace(
        first.source,
        seed=1000,
        episode_id=first.source.episode_id + "-reserved",
    )
    bad_record = replace(first, source=bad_source)
    bad_action = replace(
        action,
        episode_records=(bad_record, *action.episode_records[1:]),
    )
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="reserved_evaluation_seed_present",
    ):
        _validate_global_training_seeds(runtime, bad_action)


@pytest.mark.parametrize("seed", [0, 37, 99])
def test_action_recipe_is_relabelled_on_eight_region_runtime_geometry(
    source_datasets: tuple[
        LoadedRegionLearningDataset, LoadedRegionLearningDataset
    ],
    seed: int,
) -> None:
    runtime, action = source_datasets
    runtime_by_seed = [
        item for item in runtime.episode_records if item.source.seed == seed
    ]
    action_episode = next(
        item for item in action.episode_records if item.source.seed == seed
    )
    donor = _select_runtime_donor(runtime_by_seed, seed=seed)
    frames, provenance = _build_overlay_episode(
        donor, action_episode, seed=seed
    )
    assert tuple(item["frame_kind"] for item in provenance) == (
        "hold",
        "request_replan",
        "transfer",
    )
    assert all(
        frame.snapshot.region_count == REGION_RESOURCE_EIGHT_REGION_COUNT
        for frame in frames
    )
    inventory = {
        "hold": sum(
            action.hold
            for frame in frames
            for action in frame.target.recommendation.actions
        ),
        "request_replan": sum(
            action.request_replan
            for frame in frames
            for action in frame.target.recommendation.actions
        ),
        "nonzero": sum(
            action.resource_quota_delta != 0
            for frame in frames
            for action in frame.target.recommendation.actions
        ),
        "transfer": sum(
            len(frame.target.recommendation.transfers) for frame in frames
        ),
    }
    assert all(value > 0 for value in inventory.values())


def test_source_controlled_candidate_is_self_contained_and_fail_closed() -> None:
    manifest = load_region_resource_eight_region_candidate_manifest(
        CANDIDATE_ROOT
    )
    review = review_region_resource_eight_region_candidate(CANDIDATE_ROOT)
    assert manifest.applicable_region_count == REGION_RESOURCE_EIGHT_REGION_COUNT
    assert manifest.runtime_dataset_sha256 == (
        REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256
    )
    assert manifest.action_dataset_sha256 == (
        REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256
    )
    assert review["source_datasets_required_for_runtime_load"] is False
    assert review["runtime_preflight_completed"] is False
    assert review["formal_evaluation_authorized"] is False
    assert manifest.confidence_calibration_accepted is False
    assert (
        manifest.validation_action_inconsistent_threshold_pass_count > 0
    )
    assert review["confidence_calibration_accepted"] is False
    assert review["confidence_calibration_blockers"]
    assert not any(
        value
        for name, value in manifest.permissions.to_dict().items()
        if name != "schema"
    )
    assert RegionResourceEightRegionPermissions() == manifest.permissions


def test_candidate_source_summary_binds_clean_committed_implementation() -> None:
    source = json.loads(
        (CANDIDATE_ROOT / "source_implementation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert source["git_commit"] == SOURCE_COMMIT
    assert source["training_core_matches_commit"] is True
    assert source["view_builder_content_addressed"] is True
    for relative_path, expected_sha256 in source[
        "committed_training_implementation_files"
    ].items():
        assert _committed_blob_sha256(relative_path) == expected_sha256
    assert _committed_blob_sha256(source["view_builder_file"]) == (
        source["view_builder_file_sha256"]
    )


def test_confidence_head_is_supervised_and_failed_calibration_stays_closed() -> None:
    manifest = load_region_resource_eight_region_candidate_manifest(
        CANDIDATE_ROOT
    )
    training = json.loads(
        (CANDIDATE_ROOT / "training_summary.json").read_text(
            encoding="utf-8"
        )
    )
    confidence = training["confidence_supervision"]
    definition = confidence["definition"]
    before = confidence["validation"]["before_fit"]
    after = confidence["validation"]["after_fit"]
    acceptance = confidence["acceptance"]

    assert definition["fit_split"] == "train"
    assert definition["audit_split"] == "validation"
    assert definition["test_split_use_count"] == 0
    assert definition["reserved_evaluation_seed_use_count"] == 0
    assert definition["truth_identifier_use_count"] == 0
    assert definition["future_outcome_use_count"] == 0
    assert definition["constant_positive_label_use_count"] == 0
    assert definition["fixed_minimum_confidence"] == 0.60
    assert definition["loss"] == (
        "mean_squared_error_continuous_brier_equivalent"
    )
    assert definition["loss_weight"] == 1.0
    assert after["target_minimum"] < 0.60
    assert after["target_maximum"] > 0.60
    assert after["brier_score"] < before["brier_score"]
    assert after["fixed_threshold"] == 0.60
    assert after["threshold_pass_count"] > 0
    assert after["action_inconsistent_threshold_pass_count"] > 0
    assert acceptance["accepted"] is False
    assert acceptance[
        "action_inconsistent_threshold_pass_count"
    ] == after["action_inconsistent_threshold_pass_count"]
    assert manifest.confidence_calibration_accepted is False
    assert manifest.validation_confidence_brier == after["brier_score"]
    assert manifest.validation_threshold_pass_rate == (
        after["threshold_pass_rate"]
    )


def test_candidate_global_split_is_atomic_and_action_supported_per_split() -> None:
    view = json.loads(
        (CANDIDATE_ROOT / "training_view_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    split = view["global_split"]
    train = set(split["train_seeds"])
    validation = set(split["validation_seeds"])
    test = set(split["test_seeds"])
    assert train | validation | test == set(
        REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS
    )
    assert not train & validation
    assert not train & test
    assert not validation & test
    assert not (train | validation | test) & set(range(1000, 1020))
    for inventory in view["action_inventory"]["composite_by_split"].values():
        assert inventory["hold_true_count"] > 0
        assert inventory["request_replan_true_count"] > 0
        assert inventory["resource_quota_nonzero_count"] > 0
        assert inventory["transfer_count"] > 0


def test_candidate_can_be_discovered_without_source_datasets(
    tmp_path: Path,
) -> None:
    clone_registry = tmp_path / "model_registry"
    clone_candidate = clone_registry / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
    clone_registry.mkdir()
    shutil.copytree(CANDIDATE_ROOT, clone_candidate)
    manifest = load_region_resource_eight_region_candidate_manifest(
        clone_candidate
    )
    review = review_region_resource_eight_region_candidate(clone_candidate)
    assert manifest.candidate_id == REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
    assert review["read_only_shadow_verified"] is True


def test_candidate_artifact_tamper_is_rejected(tmp_path: Path) -> None:
    copied = tmp_path / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
    shutil.copytree(CANDIDATE_ROOT, copied)
    view_path = copied / "training_view_manifest.json"
    view = json.loads(view_path.read_text(encoding="utf-8"))
    view["runtime_preflight_completed"] = True
    view_path.write_text(json.dumps(view), encoding="utf-8")
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="candidate_artifact_sha256_mismatch",
    ):
        load_region_resource_eight_region_candidate_manifest(copied)


def _shadow_snapshot(
    runtime: LoadedRegionLearningDataset,
    *,
    region_count: int,
    timestamp_s: float = 0.0,
    suffix: str = "0",
) -> RegionResourceSnapshot:
    source = runtime.episode_records[0].frames[0].snapshot
    selected_regions = tuple(
        sorted(source.regions, key=lambda item: item.region_id)[:region_count]
    )
    selected_ids = {item.region_id for item in selected_regions}
    selected_edges = tuple(
        edge
        for edge in source.edges
        if edge.source_region_id in selected_ids
        and edge.target_region_id in selected_ids
    )
    return RegionResourceSnapshot(
        snapshot_id=f"eight-region-shadow-{region_count}-{suffix}",
        scenario_id="d4-eight-region-shadow-test",
        scenario_version="v1",
        seed=2000,
        timestamp_s=timestamp_s,
        regions=selected_regions,
        edges=selected_edges,
        source_authority_schema=source.source_authority_schema,
    )


def _registration(
    adapter: RegionResourceCurrentLineageShadowAdapter,
    *,
    seed: int = 2000,
) -> RegionResourceCurrentLineageShadowSeedRegistration:
    return RegionResourceCurrentLineageShadowSeedRegistration(
        registry_id="main-eight-region-shadow-registry",
        registry_version=1,
        episode_id=f"main-eight-region-shadow-episode-{seed}",
        scenario_id="d4-eight-region-shadow-test",
        scenario_version="v1",
        seed=seed,
        candidate_binding_sha256=adapter.candidate_binding.binding_sha256,
        excluded_calibration_seeds=(500,),
        calibration_catalog_complete=True,
    )


def test_frozen_shadow_candidate_accepts_only_eight_region_scope(
    source_datasets: tuple[
        LoadedRegionLearningDataset, LoadedRegionLearningDataset
    ],
) -> None:
    runtime, _ = source_datasets
    adapter = RegionResourceCurrentLineageShadowAdapter(CANDIDATE_ROOT)
    record = adapter.evaluate(
        _registration(adapter),
        _shadow_snapshot(runtime, region_count=8),
        frame_index=0,
    )
    assert not any(
        item.feature_scope == "graph"
        for item in record.ood_diagnostic.violations
    )
    assert record.candidate_binding.model_state_sha256 == (
        load_region_resource_eight_region_candidate_manifest(
            CANDIDATE_ROOT
        ).model_state_sha256
    )
    assert record.permissions == RegionResourceCurrentLineageShadowPermissions()
    assert record.ood_diagnostic.feature_ood is False
    assert record.candidate_gate.candidate_confidence is not None
    assert record.candidate_gate.candidate_confidence >= 0.60
    assert record.candidate_gate.gate_pass is False
    assert record.candidate_gate.rule_fallback is True
    assert "candidate_confidence_calibration_not_accepted" in (
        record.candidate_gate.rejection_reasons
    )
    assert record.candidate_executed is False

    out_of_scope_adapter = RegionResourceCurrentLineageShadowAdapter(
        CANDIDATE_ROOT
    )
    out_of_scope = out_of_scope_adapter.evaluate(
        _registration(out_of_scope_adapter),
        _shadow_snapshot(runtime, region_count=2),
        frame_index=0,
    )
    assert out_of_scope.ood_diagnostic.feature_ood is True
    assert (
        out_of_scope.ood_diagnostic.feature_violation_counts[
            "graph:region_count"
        ]
        == 1
    )
    assert out_of_scope.candidate_gate.candidate_ood_passed is False
    assert out_of_scope.candidate_gate.gate_pass is False
    assert out_of_scope.candidate_gate.rule_fallback is True
    assert "candidate_region_count_out_of_scope" in (
        out_of_scope.candidate_gate.rejection_reasons
    )
    assert out_of_scope.candidate_executed is False


def test_frozen_shadow_candidate_keeps_replay_and_reserved_seed_fences(
    source_datasets: tuple[
        LoadedRegionLearningDataset, LoadedRegionLearningDataset
    ],
) -> None:
    runtime, _ = source_datasets
    adapter = RegionResourceCurrentLineageShadowAdapter(CANDIDATE_ROOT)
    registration = _registration(adapter)
    snapshot = _shadow_snapshot(runtime, region_count=8)
    adapter.evaluate(registration, snapshot, frame_index=0)
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_frame_version_stale_or_replayed",
    ):
        adapter.evaluate(registration, snapshot, frame_index=0)

    reserved_adapter = RegionResourceCurrentLineageShadowAdapter(
        CANDIDATE_ROOT
    )
    reserved = _registration(reserved_adapter, seed=1000)
    reserved_snapshot = replace(
        snapshot,
        snapshot_id="eight-region-shadow-reserved",
        seed=1000,
        authority_digest="",
    )
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_seed_overlap:.*reserved",
    ):
        reserved_adapter.evaluate(
            reserved,
            reserved_snapshot,
            frame_index=0,
        )


def test_frozen_shadow_candidate_rejects_bundle_tamper(
    tmp_path: Path,
) -> None:
    copied = tmp_path / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
    shutil.copytree(CANDIDATE_ROOT, copied)
    state = copied / "bundle/state_dict.pt"
    state.write_bytes(state.read_bytes() + b"tampered")
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="frozen_eight_region_manifest_rejected",
    ):
        RegionResourceCurrentLineageShadowAdapter(copied)
