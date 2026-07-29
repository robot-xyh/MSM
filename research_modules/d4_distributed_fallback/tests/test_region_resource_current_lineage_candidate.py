from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from d4_distributed_fallback.region_resource import (
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.region_resource_current_lineage_candidate import (
    REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME,
    REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID,
    REGION_RESOURCE_CURRENT_LINEAGE_IMPLEMENTATION_FILES,
    REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION,
    REGION_RESOURCE_CURRENT_LINEAGE_RESERVED_SEEDS,
    LearnedRegionResourcePolicy,
    RegionResourceCurrentLineageCandidateError,
    RegionResourceCurrentLineagePermissions,
    RegionResourceCurrentLineageSplitUsage,
    build_region_resource_current_lineage_candidate,
    load_region_resource_current_lineage_candidate_manifest,
    review_region_resource_current_lineage_candidate,
)
import d4_distributed_fallback.region_resource_current_lineage_shadow as current_lineage_shadow
from d4_distributed_fallback.region_resource_current_lineage_shadow import (
    RegionResourceCurrentLineageShadowAdapter,
    RegionResourceCurrentLineageShadowError,
    RegionResourceCurrentLineageShadowPermissions,
    RegionResourceCurrentLineageShadowRecord,
    RegionResourceCurrentLineageShadowSeedRegistration,
    RegionResourceCurrentLineageShadowVerifier,
    summarize_region_resource_current_lineage_shadow_records,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningSplit,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset_splits,
    stage_region_learning_episode,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


def _clean_source_repository(root: Path) -> Path:
    root.mkdir(parents=True)
    shutil.copy2(_PROJECT_ROOT / ".gitignore", root / ".gitignore")
    package_relative = Path(
        "research_modules/d4_distributed_fallback/d4_distributed_fallback"
    )
    shutil.copytree(
        _PROJECT_ROOT / package_relative,
        root / package_relative,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    script_relative = Path(
        "research_modules/d4_distributed_fallback/scripts/"
        "build_region_resource_current_lineage_candidate.py"
    )
    (root / script_relative).parent.mkdir(parents=True)
    shutil.copy2(_PROJECT_ROOT / script_relative, root / script_relative)
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.name", "D4 Test")
    _run_git(root, "config", "user.email", "d4-test@example.invalid")
    _run_git(root, "add", ".")
    _run_git(
        root,
        "commit",
        "-q",
        "-m",
        "fixture: freeze current D4 candidate implementation",
    )
    assert _run_git(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    ) == ""
    return root


def _source(seed: int) -> RegionLearningEpisodeSource:
    return RegionLearningEpisodeSource(
        scenario_id="d4-current-lineage-development-fixture",
        scenario_version="v1",
        scenario_scale="M2N2",
        seed=seed,
        episode_id=f"d4-current-lineage-seed-{seed}",
        git_commit="a" * 40,
        git_dirty=False,
        config_sha256=sha256(f"fixture:{seed}".encode()).hexdigest(),
    )


def _snapshot(
    source: RegionLearningEpisodeSource,
) -> RegionResourceSnapshot:
    common = {
        "d1_uncertainty": 0.15,
        "d2_uncertainty": 0.10,
        "d5_visibility": 0.85,
        "d5_consistency": 0.90,
        "reserve_resources": 1,
        "secondary_coverage": 0.90,
        "secondary_readiness": 0.90,
        "communication_capacity": 50.0,
        "communication_latency_s": 0.02,
        "packet_loss_rate": 0.01,
        "current_owner_id": "CENTER",
        "current_owner_layer": RegionalAuthorityLayer.CENTER,
        "plan_id": "fixture-plan",
        "plan_version": 2,
        "epoch": 3,
        "lease_expires_at_s": 30.0,
        "coalition_ack_complete": True,
        "owner_active": True,
        "fault_fenced": False,
    }
    return RegionResourceSnapshot(
        snapshot_id=f"fixture-snapshot-{source.seed}",
        scenario_id=source.scenario_id,
        scenario_version=source.scenario_version,
        seed=source.seed,
        timestamp_s=0.0,
        regions=(
            RegionResourceNode(
                region_id="west",
                target_demand=4.0 + float(source.seed % 2),
                high_threat_backlog=1.0,
                available_resources=2,
                committed_resources=0,
                **common,
            ),
            RegionResourceNode(
                region_id="east",
                target_demand=1.0,
                high_threat_backlog=0.0,
                available_resources=5,
                committed_resources=1,
                **common,
            ),
        ),
        edges=(
            RegionResourceEdge(
                source_region_id="east",
                target_region_id="west",
                transferable_resources=2,
                distance_m=100.0,
                transfer_time_s=2.0,
                bandwidth_mbps=20.0,
                edge_id="east-west",
                bidirectional=True,
                partitioned=False,
            ),
        ),
    )


def _dataset(root: Path) -> Path:
    staging = root / "staging"
    for seed in range(5):
        source = _source(seed)
        snapshot = _snapshot(source)
        recommendation = RuleRegionResourcePolicy().recommend(snapshot)
        frame = RegionLearningFrame(
            frame_index=0,
            timestamp_s=0.0,
            snapshot=snapshot,
            target=RegionLearningTarget.available(
                RegionLearningTargetKind.RULE,
                recommendation,
            ),
            reward=RegionLearningReward.unavailable(
                "development_fixture_reward_unavailable"
            ),
            recommendation=recommendation,
        )
        stage_region_learning_episode(staging, source, (frame,))
    destination = root / "dataset"
    finalize_region_learning_dataset(
        staging,
        destination,
        created_at_utc="2026-07-28T00:00:00Z",
        split_seed=17,
        minimum_unique_seeds=5,
        minimum_unseen_seeds=2,
    )
    return destination


@pytest.fixture(scope="module")
def current_lineage_candidate_fixture(
    tmp_path_factory: pytest.TempPathFactory,
):
    root = tmp_path_factory.mktemp("d4-current-lineage-candidate")
    source_repository = _clean_source_repository(root / "source")
    dataset = _dataset(root / "data")
    output = root / "artifacts" / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
    command = (
        "python3",
        str(
            source_repository
            / "research_modules/d4_distributed_fallback/scripts/"
            "build_region_resource_current_lineage_candidate.py"
        ),
        "--dataset",
        str(dataset),
        "--repository-root",
        str(source_repository),
        "--output-dir",
        str(output),
        "--seed",
        "7",
        "--hidden-dim",
        "8",
        "--message-passing-steps",
        "1",
        "--epochs",
        "2",
        "--batch-size",
        "2",
        "--patience",
        "1",
        "--torch-num-threads",
        "1",
        "--created-at-utc",
        "2026-07-28T00:00:00Z",
    )
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(
                source_repository
                / "research_modules/d4_distributed_fallback"
            ),
        },
    )
    cli_output = json.loads(completed.stdout)
    assert cli_output["candidate_id"] == (
        REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
    )
    assert cli_output["development_shadow_candidate"] is True
    assert cli_output["a2_admitted"] is False
    assert cli_output["authority_granted"] is False
    assert cli_output["control_authority_granted"] is False
    assert cli_output["test_payload_read_count"] == 0
    assert cli_output["calibration_seed_use_count"] == 0
    assert cli_output["reserved_seed_use_count"] == 0
    return source_repository, dataset, output


def test_cli_builds_loadable_development_shadow_candidate(
    current_lineage_candidate_fixture,
) -> None:
    source_repository, dataset, output = current_lineage_candidate_fixture
    review_completed = subprocess.run(
        (
            "python3",
            str(
                source_repository
                / "research_modules/d4_distributed_fallback/scripts/"
                "build_region_resource_current_lineage_candidate.py"
            ),
            "--dataset",
            str(dataset),
            "--repository-root",
            str(source_repository),
            "--output-dir",
            str(output),
            "--review-only",
        ),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(
                source_repository
                / "research_modules/d4_distributed_fallback"
            ),
        },
    )
    cli_review = json.loads(review_completed.stdout)

    manifest = load_region_resource_current_lineage_candidate_manifest(output)
    review = review_region_resource_current_lineage_candidate(
        output,
        dataset_dir=dataset,
        repository_root=source_repository,
    )

    assert manifest.model_version == REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION
    assert manifest.development_shadow_candidate is True
    assert manifest.formal_holdout_evaluated is False
    assert manifest.split_usage.test_payload_read_count == 0
    assert manifest.split_usage.calibration_seed_use_count == 0
    assert manifest.split_usage.reserved_seed_use_count == 0
    assert manifest.permissions == RegionResourceCurrentLineagePermissions()
    assert review.bundle_loadable is True
    assert review.validation_nonfinite_output_count == 0
    assert review.a2_admitted is False
    assert review.authority_granted is False
    assert review.assignment_authority_granted is False
    assert review.takeover_authority_granted is False
    assert review.control_authority_granted is False
    assert cli_review["bundle_loadable"] is True
    assert cli_review["a2_admitted"] is False
    assert cli_review["authority_granted"] is False
    assert cli_review["control_authority_granted"] is False


def test_selective_loader_does_not_read_untouched_test_payload(
    tmp_path: Path,
) -> None:
    dataset = _dataset(tmp_path / "data")
    loaded = load_region_learning_dataset_splits(
        dataset,
        splits=(RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
    )
    test_entry = next(
        entry
        for entry in loaded.manifest.episodes
        if entry.split == RegionLearningSplit.TEST
    )
    (dataset / test_entry.relative_path).write_text(
        "untouched-test-payload-corrupted-for-loader-boundary\n",
        encoding="utf-8",
    )

    selected = load_region_learning_dataset_splits(
        dataset,
        splits=(RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
    )

    assert selected.episodes(RegionLearningSplit.TRAIN)
    assert selected.episodes(RegionLearningSplit.VALIDATION)
    assert selected.episodes(RegionLearningSplit.TEST) == ()


def test_dirty_worktree_fails_before_candidate_construction(
    tmp_path: Path,
) -> None:
    source_repository = _clean_source_repository(tmp_path / "source")
    dataset = _dataset(tmp_path / "data")
    (source_repository / "untracked-development-note.txt").write_text(
        "dirty\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RegionResourceCurrentLineageCandidateError,
        match="source_worktree_dirty",
    ):
        build_region_resource_current_lineage_candidate(
            dataset,
            repository_root=source_repository,
            output_dir=(
                tmp_path
                / "artifacts"
                / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
            ),
        )


def test_clean_later_source_commit_invalidates_candidate_review(
    current_lineage_candidate_fixture,
    tmp_path: Path,
) -> None:
    _, dataset, output = current_lineage_candidate_fixture
    source_repository = tmp_path / "source"
    shutil.copytree(current_lineage_candidate_fixture[0], source_repository)
    implementation_path = (
        source_repository
        / REGION_RESOURCE_CURRENT_LINEAGE_IMPLEMENTATION_FILES[0]
    )
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8")
        + "\n# clean later-lineage fixture\n",
        encoding="utf-8",
    )
    _run_git(source_repository, "add", ".")
    _run_git(
        source_repository,
        "commit",
        "-q",
        "-m",
        "fixture: change current implementation lineage",
    )

    with pytest.raises(
        RegionResourceCurrentLineageCandidateError,
        match="candidate_source_lineage_mismatch",
    ):
        review_region_resource_current_lineage_candidate(
            output,
            dataset_dir=dataset,
            repository_root=source_repository,
        )


def test_split_overlap_and_permission_escalation_are_rejected() -> None:
    with pytest.raises(ValueError, match="split seed catalogs overlap"):
        RegionResourceCurrentLineageSplitUsage(
            train_seeds=(1, 2),
            validation_seeds=(2, 3),
            untouched_test_seeds=(4,),
            reserved_evaluation_seeds=(
                REGION_RESOURCE_CURRENT_LINEAGE_RESERVED_SEEDS
            ),
            train_payload_read_count=2,
            validation_payload_read_count=2,
        )
    with pytest.raises(ValueError, match="cannot grant permissions"):
        RegionResourceCurrentLineagePermissions(authority_enabled=True)
    with pytest.raises(ValueError, match="cannot grant permissions"):
        RegionResourceCurrentLineagePermissions(control_enabled=True)


def test_artifact_tampering_is_rejected(
    current_lineage_candidate_fixture,
    tmp_path: Path,
) -> None:
    source = current_lineage_candidate_fixture[2]
    candidate = tmp_path / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
    shutil.copytree(source, candidate)
    config = candidate / "training_config.json"
    config.write_text(config.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(
        RegionResourceCurrentLineageCandidateError,
        match="candidate_artifact_sha256_mismatch:training_config.json",
    ):
        load_region_resource_current_lineage_candidate_manifest(candidate)


def test_nonfinite_validation_output_fails_review(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, dataset, output = current_lineage_candidate_fixture
    original = LearnedRegionResourcePolicy.recommend_raw

    def _nonfinite(self, snapshot):
        recommendation = original(self, snapshot)
        object.__setattr__(recommendation, "confidence", float("nan"))
        return recommendation

    monkeypatch.setattr(LearnedRegionResourcePolicy, "recommend_raw", _nonfinite)
    with pytest.raises(
        RegionResourceCurrentLineageCandidateError,
        match="candidate_validation_output_nonfinite",
    ):
        review_region_resource_current_lineage_candidate(
            output,
            dataset_dir=dataset,
            repository_root=source_repository,
        )


def test_manifest_permission_field_cannot_be_rewritten(
    current_lineage_candidate_fixture,
    tmp_path: Path,
) -> None:
    source = current_lineage_candidate_fixture[2]
    candidate = tmp_path / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
    shutil.copytree(source, candidate)
    manifest_path = candidate / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["permissions"]["a2_admitted"] = True
    manifest_path.write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(
        RegionResourceCurrentLineageCandidateError,
        match="candidate_manifest_invalid:ValueError",
    ):
        load_region_resource_current_lineage_candidate_manifest(candidate)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _patch_frozen_shadow_binding(
    monkeypatch: pytest.MonkeyPatch,
    candidate_root: Path,
) -> None:
    manifest_path = (
        candidate_root / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = json.loads(
        (
            candidate_root / "source_implementation_summary.json"
        ).read_text(encoding="utf-8")
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_GIT_COMMIT",
        source["git_commit"],
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_MANIFEST_FILE_SHA256",
        _sha256_file(manifest_path),
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_MANIFEST_CONTENT_SHA256",
        manifest["content_sha256"],
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_MODEL_STATE_SHA256",
        manifest["model_state_sha256"],
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_SOURCE_IDENTITY_SHA256",
        manifest["source_identity_sha256"],
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_SOURCE_SUMMARY_FILE_SHA256",
        manifest["source_summary_file_sha256"],
    )
    monkeypatch.setattr(
        current_lineage_shadow,
        "FROZEN_CURRENT_LINEAGE_BUNDLE_MANIFEST_SHA256",
        manifest["bundle_manifest_sha256"],
    )


def _shadow_registration(
    adapter: RegionResourceCurrentLineageShadowAdapter,
    *,
    seed: int,
    episode_id: str | None = None,
    registry_version: int = 1,
    excluded_calibration_seeds: tuple[int, ...] = (5,),
) -> RegionResourceCurrentLineageShadowSeedRegistration:
    return RegionResourceCurrentLineageShadowSeedRegistration(
        registry_id="main-shadow-seed-registry",
        registry_version=registry_version,
        episode_id=episode_id or f"main-shadow-episode-{seed}",
        scenario_id="d4-current-lineage-development-fixture",
        scenario_version="v1",
        seed=seed,
        candidate_binding_sha256=(
            adapter.candidate_binding.binding_sha256
        ),
        excluded_calibration_seeds=excluded_calibration_seeds,
        calibration_catalog_complete=True,
    )


def _shadow_snapshot(
    seed: int,
    *,
    timestamp_s: float = 0.0,
    snapshot_suffix: str = "0",
) -> RegionResourceSnapshot:
    snapshot = _snapshot(_source(seed))
    return replace(
        snapshot,
        snapshot_id=f"shadow-snapshot-{seed}-{snapshot_suffix}",
        timestamp_s=timestamp_s,
        authority_digest="",
    )


def test_frozen_shadow_adapter_records_and_replays_without_permissions(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    registration = _shadow_registration(adapter, seed=2000)
    snapshot = _shadow_snapshot(2000)

    record = adapter.evaluate(registration, snapshot, frame_index=0)

    assert record.candidate_binding == adapter.candidate_binding
    assert record.seed_registration_sha256 == (
        registration.registration_sha256
    )
    assert record.input_summary.episode_id == registration.episode_id
    assert record.input_summary.seed == 2000
    assert record.input_summary.frame_index == 0
    assert record.raw_model_recommendation.projected is False
    assert record.deterministic_projected_recommendation.projected is True
    assert record.projection_completed is True
    assert record.execution_source == "deterministic_rule_fallback"
    assert record.candidate_executed is False
    assert record.rule_fallback_required is True
    assert record.permissions == (
        RegionResourceCurrentLineageShadowPermissions()
    )
    assert all(
        token not in json.dumps(record.to_dict(), sort_keys=True)
        for token in (
            "global_track_id",
            "truth_id",
            "d3_successor_plan_id",
            "physical_window_id",
            "r0_episode_id",
        )
    )

    verifier = RegionResourceCurrentLineageShadowVerifier(candidate)
    review = verifier.verify_next(record.to_dict(), registration, snapshot)

    assert review.record_id == record.record_id
    assert review.permissions_closed is True
    assert review.deterministic_projection_verified is True


def test_source_controlled_frozen_shadow_registry_loads_with_permissions_closed(
) -> None:
    registry = (
        _PROJECT_ROOT
        / "research_modules/d4_distributed_fallback/model_registry/"
        "region_resource_a2_current_lineage_development_v1"
    )
    adapter = RegionResourceCurrentLineageShadowAdapter(registry)
    registration = _shadow_registration(adapter, seed=2000)
    snapshot = _shadow_snapshot(2000)

    record = adapter.evaluate(registration, snapshot, frame_index=0)

    assert record.candidate_binding.source_git_commit == (
        current_lineage_shadow.FROZEN_CURRENT_LINEAGE_GIT_COMMIT
    )
    assert record.candidate_binding.model_state_sha256 == (
        current_lineage_shadow.FROZEN_CURRENT_LINEAGE_MODEL_STATE_SHA256
    )
    assert record.execution_source == "deterministic_rule_fallback"
    assert record.candidate_executed is False
    assert record.rule_fallback_required is True
    assert record.permissions == (
        RegionResourceCurrentLineageShadowPermissions()
    )
    assert all(
        value is False
        for name, value in record.permissions.to_dict().items()
        if name != "schema"
    )


def test_shadow_adapter_rejects_every_seed_overlap_class(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    manifest = load_region_resource_current_lineage_candidate_manifest(
        candidate
    )
    cases = (
        (manifest.split_usage.train_seeds[0], (5,), "train"),
        (
            manifest.split_usage.validation_seeds[0],
            (5,),
            "validation",
        ),
        (manifest.split_usage.untouched_test_seeds[0], (5,), "test"),
        (1000, (5,), "reserved"),
        (2000, (2000,), "calibration"),
    )
    for seed, excluded, reason in cases:
        registration = _shadow_registration(
            adapter,
            seed=seed,
            excluded_calibration_seeds=excluded,
        )
        with pytest.raises(
            RegionResourceCurrentLineageShadowError,
            match=f"shadow_seed_overlap:.*{reason}",
        ):
            adapter.evaluate(
                registration,
                _shadow_snapshot(seed),
                frame_index=0,
            )


def test_shadow_adapter_rejects_stale_frame_and_plan_generation(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    registration = _shadow_registration(adapter, seed=2000)
    first = _shadow_snapshot(2000)
    adapter.evaluate(registration, first, frame_index=2)

    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_frame_version_stale_or_replayed",
    ):
        adapter.evaluate(registration, first, frame_index=2)

    stale_nodes = tuple(
        replace(node, plan_version=1) for node in first.regions
    )
    stale_plan = replace(
        first,
        snapshot_id="shadow-snapshot-2000-stale-plan",
        timestamp_s=1.0,
        regions=stale_nodes,
        authority_digest="",
    )
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_region_plan_version_stale",
    ):
        adapter.evaluate(registration, stale_plan, frame_index=3)


def test_shadow_adapter_rejects_old_registry_and_seed_reuse(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    first = _shadow_registration(
        adapter,
        seed=2000,
        registry_version=2,
    )
    adapter.evaluate(first, _shadow_snapshot(2000), frame_index=0)

    old = _shadow_registration(
        adapter,
        seed=2001,
        registry_version=1,
    )
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_seed_registry_version_stale",
    ):
        adapter.evaluate(old, _shadow_snapshot(2001), frame_index=0)

    reused = _shadow_registration(
        adapter,
        seed=2000,
        episode_id="different-main-episode",
        registry_version=2,
    )
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_seed_reused_by_different_episode",
    ):
        adapter.evaluate(reused, _shadow_snapshot(2000), frame_index=0)


def test_shadow_adapter_rejects_nonfinite_model_output(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    original = adapter._policy.recommend_raw

    def _nonfinite(snapshot):
        recommendation = original(snapshot)
        object.__setattr__(recommendation, "confidence", float("nan"))
        return recommendation

    monkeypatch.setattr(adapter._policy, "recommend_raw", _nonfinite)
    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="shadow_model_output_nonfinite_or_unavailable",
    ):
        adapter.evaluate(
            _shadow_registration(adapter, seed=2000),
            _shadow_snapshot(2000),
            frame_index=0,
        )


def test_shadow_record_rejects_permission_tampering(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    record = adapter.evaluate(
        _shadow_registration(adapter, seed=2000),
        _shadow_snapshot(2000),
        frame_index=0,
    )
    payload = record.to_dict()
    payload["permissions"]["runtime_ack_available"] = True

    with pytest.raises(ValueError, match="cannot grant evidence or permission"):
        RegionResourceCurrentLineageShadowRecord.from_mapping(payload)


def test_shadow_adapter_rejects_frozen_artifact_tampering(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, source)
    candidate = tmp_path / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
    shutil.copytree(source, candidate)
    state = candidate / "bundle" / "state_dict.pt"
    state.write_bytes(state.read_bytes() + b"tampered")

    with pytest.raises(
        RegionResourceCurrentLineageShadowError,
        match="frozen_candidate_manifest_rejected",
    ):
        RegionResourceCurrentLineageShadowAdapter(candidate)


def test_shadow_ood_diagnostics_identify_runtime_feature_mismatch(
    current_lineage_candidate_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = current_lineage_candidate_fixture[2]
    _patch_frozen_shadow_binding(monkeypatch, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    base = _shadow_snapshot(2000)
    shifted_nodes = tuple(
        replace(
            node,
            d1_uncertainty=500.0,
            d2_uncertainty=250.0,
            secondary_coverage=0.0,
            secondary_readiness=0.0,
            committed_resources=min(
                2, node.available_resources - node.reserve_resources
            ),
        )
        for node in base.regions
    )
    shifted = replace(
        base,
        snapshot_id="shadow-snapshot-2000-runtime-shift",
        regions=shifted_nodes,
        authority_digest="",
    )

    record = adapter.evaluate(
        _shadow_registration(adapter, seed=2000),
        shifted,
        frame_index=0,
    )
    feature_names = {
        item.feature_name for item in record.ood_diagnostic.violations
    }

    assert record.ood_diagnostic.feature_ood is True
    assert record.candidate_gate.candidate_ood_passed is False
    assert "d1_uncertainty_log" in feature_names
    assert "d2_uncertainty_log" in feature_names
    assert all(
        item.accepted_minimum
        == pytest.approx(
            item.training_minimum
            - 0.05
            * max(
                abs(item.training_minimum),
                abs(item.training_maximum),
                1.0,
            )
        )
        for item in record.ood_diagnostic.violations
    )
    report = summarize_region_resource_current_lineage_shadow_records(
        (record,)
    )
    assert report.feature_ood_count == 1
    assert report.feature_ood_rate == 1.0
    assert report.runtime_compatible is False
    assert report.current_candidate_blocker is True
    assert report.blocker_reasons == ("all_shadow_frames_feature_ood",)
    assert report.permissions == (
        RegionResourceCurrentLineageShadowPermissions()
    )
