from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceProjectionConfig,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
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
from d4_distributed_fallback.region_resource_learning import (
    LearnedRegionResourcePolicy,
    SharedRegionGraphActorCritic,
    snapshot_to_region_graph,
)
import d4_distributed_fallback.region_resource_v4_shadow_candidate as v4_module
from d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V3_FROZEN_TREE_SHA256,
    REGION_RESOURCE_V4_CANDIDATE_ID,
    REGION_RESOURCE_V4_DOMAIN_FIXTURE_OBSERVABLE_KEY_SHA256,
    REGION_RESOURCE_V4_DOMAIN_FIXTURE_SCHEMA,
    REGION_RESOURCE_V4_DOMAIN_FIXTURE_VERSION,
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256,
    REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256,
    REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256,
    REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256,
    RegionResourceV4BuildConfig,
    RegionResourceV4CandidateError,
    RegionResourceV4CandidateManifest,
    RegionResourceV4CandidateLoader,
    RegionResourceV4ClassBalance,
    RegionResourceV4ConfidenceBalance,
    RegionResourceV4ExternalDatasetEvidence,
    RegionResourceV4Permissions,
    RegionResourceV4ShadowAdvisor,
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    _audit_v4_confidence_identifiability,
    _confidence_metrics,
    _confidence_records,
    _derive_v4_actor_class_balance,
    _derive_v4_confidence_balance,
    _v4_confidence_checkpoint_selection_key,
    _v4_confidence_margin_loss,
    _fit_confidence_head,
    _v4_confidence_sample_weights,
    _load_external_dataset_for_v4,
    _v4_confidence_observable_key,
    _v4_actor_metrics,
    _v4_actor_records,
    _v4_checkpoint_selection_key,
    build_region_resource_v4_development_candidate,
    build_region_resource_v4_development_fixture,
    build_region_resource_v4_domain_representative_fixture,
    evaluate_v4_intervention_invariants,
    executable_signature,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
V3_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
    / "region_resource_a2_8region_runtime_action_readiness_shadow_v3"
)
_COMMIT = "a" * 40


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    inventory = {
        str(path.relative_to(root)): _file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return sha256(
        json.dumps(
            inventory,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _policies() -> tuple[
    DeterministicResourceProjector,
    RuleRegionResourcePolicy,
]:
    projector = DeterministicResourceProjector(_V4_PROJECTION)
    return projector, RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )


def _transfer_proposal(
    snapshot: object,
    *,
    count: int = 1,
    confidence: float = 0.95,
) -> object:
    projector, rule_policy = _policies()
    baseline = rule_policy.recommend(snapshot)
    edge = snapshot.edges[0]
    source_region_id = edge.source_region_id
    target_region_id = edge.target_region_id
    actions = tuple(
        replace(
            action,
            resource_quota_delta=(
                -count
                if action.region_id == source_region_id
                else count
                if action.region_id == target_region_id
                else 0
            ),
        )
        for action in baseline.actions
    )
    transfer = RegionTransferSuggestion(
        source_region_id=source_region_id,
        target_region_id=target_region_id,
        resource_count=count,
        edge_id=edge.edge_id,
        expected_transfer_time_s=edge.transfer_time_s,
        reasons=("external_runtime_transfer_label",),
    )
    return replace(
        baseline,
        policy_name="external-runtime-transfer-label",
        policy_version="v1",
        source=RecommendationSource.RULE,
        confidence=confidence,
        actions=actions,
        transfers=(transfer,),
        projected=False,
        fallback_reason=None,
        projection_rejections=(),
    )


def _projected_transfer_target(snapshot: object) -> object:
    projector, _ = _policies()
    return projector.project(snapshot, _transfer_proposal(snapshot))


def _dataset(
    tmp_path: Path,
    *,
    dirty: bool = False,
    include_positive: bool = True,
    include_negative: bool = True,
    negative_frames_per_episode: int = 1,
) -> tuple[Path, Path]:
    if not include_positive and not include_negative:
        raise ValueError("test dataset requires at least one target class")
    if negative_frames_per_episode <= 0:
        raise ValueError("negative frame count must be positive")
    staging = tmp_path / "staging"
    dataset = tmp_path / "dataset"
    for seed in range(7100, 7106):
        source = RegionLearningEpisodeSource(
            scenario_id="main-runtime-region-frames",
            scenario_version="v1",
            scenario_scale="R8",
            seed=seed,
            episode_id=f"main-runtime-region-frames-{seed}",
            git_commit=_COMMIT,
            git_dirty=bool(dirty and seed == 7100),
            config_sha256=sha256(f"runtime:{seed}".encode()).hexdigest(),
        )
        frames: list[RegionLearningFrame] = []
        target_classes = (
            ([True] if include_positive else [])
            + (
                [False] * negative_frames_per_episode
                if include_negative
                else []
            )
        )
        for frame_index, target_positive in enumerate(target_classes):
            timestamp_s = 0.5 * frame_index
            base = build_region_resource_v4_development_fixture(
                seed=seed,
                timestamp_s=timestamp_s,
            )
            if not target_positive:
                regions = tuple(
                    replace(node, target_demand=2.0)
                    if node.region_id == "region-001"
                    else node
                    for node in base.regions
                )
                base = replace(
                    base,
                    regions=regions,
                )
            snapshot = replace(
                base,
                snapshot_id=f"runtime-{seed}-{frame_index}",
                scenario_id=source.scenario_id,
                scenario_version=source.scenario_version,
            )
            _, rule_policy = _policies()
            target = (
                _projected_transfer_target(snapshot)
                if target_positive
                else rule_policy.recommend(snapshot)
            )
            frames.append(
                RegionLearningFrame(
                    frame_index=frame_index,
                    timestamp_s=timestamp_s,
                    snapshot=snapshot,
                    target=RegionLearningTarget.available(
                        RegionLearningTargetKind.RULE,
                        target,
                    ),
                    reward=RegionLearningReward.unavailable(
                        "runtime_outcome_not_used"
                    ),
                    recommendation=target,
                )
            )
        stage_region_learning_episode(staging, source, frames)
    manifest = finalize_region_learning_dataset(
        staging,
        dataset,
        created_at_utc="2026-07-29T00:00:00Z",
        split_seed=99,
        minimum_unique_seeds=6,
        minimum_unseen_seeds=2,
    )
    evidence = RegionResourceV4ExternalDatasetEvidence(
        dataset_sha256=manifest.dataset_sha256,
        dataset_split_sha256=manifest.split.split_sha256,
        source_artifact_sha256="b" * 64,
        source_kind="main_runtime_frames",
        truth_free_online_features=True,
        generated_by_v4_builder=False,
        source_worktree_dirty=False,
    )
    evidence_path = tmp_path / "external_dataset_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dataset, evidence_path


def _small_config() -> RegionResourceV4BuildConfig:
    return RegionResourceV4BuildConfig(
        minimum_train_seeds=1,
        minimum_validation_seeds=1,
        minimum_test_seeds=1,
        epochs=1,
        confidence_epochs=1,
    )


def _actor_records(
    dataset: Path,
) -> tuple[object, tuple[object, ...], tuple[object, ...]]:
    loaded = load_region_learning_dataset_splits(
        dataset,
        splits=(
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ),
    )
    projector, rule_policy = _policies()
    train_records = _v4_actor_records(
        loaded,
        split=RegionLearningSplit.TRAIN,
        projector=projector,
        rule_policy=rule_policy,
    )
    validation_records = _v4_actor_records(
        loaded,
        split=RegionLearningSplit.VALIDATION,
        projector=projector,
        rule_policy=rule_policy,
    )
    return loaded, train_records, validation_records


def _evaluation_loader(policy: object) -> RegionResourceV4CandidateLoader:
    projector, rule_policy = _policies()
    loader = object.__new__(RegionResourceV4CandidateLoader)
    loader.projector = projector
    loader.rule_policy = rule_policy
    loader.intervention_gate = REGION_RESOURCE_V4_INTERVENTION_GATE
    loader.policy = policy
    loader.manifest = SimpleNamespace(
        runtime_gate_content_sha256=(
            REGION_RESOURCE_V4_INTERVENTION_GATE.content_sha256
        )
    )
    return loader


class _FixedPolicy:
    def __init__(self, recommendation: object, *, ood: bool = False) -> None:
        self.recommendation = recommendation
        self.ood = ood

    def is_ood(self, _snapshot: object, *, margin: float) -> bool:
        assert margin == 0.05
        return self.ood

    def recommend_raw(self, _snapshot: object) -> object:
        return self.recommendation


def _advisor_with_loader(
    loader: RegionResourceV4CandidateLoader,
) -> RegionResourceV4ShadowAdvisor:
    advisor = object.__new__(RegionResourceV4ShadowAdvisor)
    advisor.loader = loader
    advisor.load_rejection_reasons = ()
    advisor.projector = loader.projector
    advisor.rule_policy = loader.rule_policy
    return advisor


def test_v4_uses_main_safety_shell_and_same_key_rule() -> None:
    assert _V4_PROJECTION == RegionResourceProjectionConfig(
        minimum_reserve_ratio=0.10,
        minimum_reserve_resources=1,
        advisory_ttl_s=1.5,
    )
    assert _V4_RULE_CONFIG == RuleRegionResourcePolicyConfig(
        projection=_V4_PROJECTION,
        high_threat_weight=2.0,
        uncertainty_weight=0.5,
        transfer_pressure_margin=0.05,
    )
    snapshot = build_region_resource_v4_development_fixture()
    projector, rule_policy = _policies()
    r0 = rule_policy.recommend(snapshot)

    assert snapshot.total_resources == 21
    assert sum(node.committed_resources for node in snapshot.regions) == 19
    source = snapshot.region_by_id["region-000"]
    assert source.available_resources - source.committed_resources == 2
    assert not r0.transfers
    assert build_region_resource_v4_development_fixture(
        region_count=5
    ).region_count == 5

    candidate = projector.project(
        snapshot,
        _transfer_proposal(snapshot),
    )
    valid, reasons = evaluate_v4_intervention_invariants(
        snapshot,
        candidate,
        r0,
        gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
        projector=projector,
        formal_decision=None,
    )
    advisory = projector.build_advisory_contract(snapshot, candidate)
    advisory_regions = {
        region.region_id: region for region in advisory.regions
    }
    assert valid, reasons
    assert not advisory.publication_rejections
    assert advisory_regions["region-000"].resources_after == 2
    assert (
        advisory_regions["region-000"].protected_reserve_resources
        == 1
    )

    tampered_r0 = replace(r0, fallback_reason="not-the-same-key-r0")
    valid, reasons = evaluate_v4_intervention_invariants(
        snapshot,
        candidate,
        tampered_r0,
        gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
        projector=projector,
        formal_decision=None,
    )
    assert not valid
    assert "r0_same_key_baseline_mismatch" in reasons


def test_v4_domain_representative_fixture_is_fixed_and_truth_free() -> None:
    first = build_region_resource_v4_domain_representative_fixture()
    second = build_region_resource_v4_domain_representative_fixture()

    assert first.to_dict() == second.to_dict()
    assert first.scenario_version == REGION_RESOURCE_V4_DOMAIN_FIXTURE_VERSION
    assert first.seed == 0
    assert first.region_count == 4
    assert first.total_resources == 17
    assert [node.available_resources for node in first.regions] == [
        14,
        1,
        1,
        1,
    ]
    assert [edge.transferable_resources for edge in first.edges] == [
        3,
        0,
        0,
        0,
    ]
    assert all(
        node.lease_expires_at_s - first.timestamp_s == 120.0
        for node in first.regions
    )
    serialized = json.dumps(
        first.to_dict(),
        sort_keys=True,
    ).lower()
    assert "curriculum" not in serialized
    assert "global_track_id" not in serialized
    assert "truth_id" not in serialized
    assert "reward" not in serialized
    observable_key = _v4_confidence_observable_key(
        snapshot_to_region_graph(first)
    )
    assert observable_key == (
        REGION_RESOURCE_V4_DOMAIN_FIXTURE_OBSERVABLE_KEY_SHA256
    )
    metadata_variant = replace(
        first,
        snapshot_id="metadata-variant",
        scenario_id="metadata-variant",
        seed=999999,
    )
    assert _v4_confidence_observable_key(
        snapshot_to_region_graph(metadata_variant)
    ) == observable_key
    assert (
        REGION_RESOURCE_V4_INTERVENTION_GATE.fixed_ood_margin == 0.05
    )
    assert (
        REGION_RESOURCE_V4_INTERVENTION_GATE.fixed_minimum_confidence
        == 0.60
    )


def test_v4_domain_fixture_evaluation_uses_projected_transfer_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_region_resource_v4_domain_representative_fixture()
    renamed_ids = {
        f"region-{index:03d}": f"area-{index:03d}"
        for index in range(4)
    }
    renamed = replace(
        snapshot,
        snapshot_id="identity-metadata-variant",
        regions=tuple(
            replace(node, region_id=renamed_ids[node.region_id])
            for node in snapshot.regions
        ),
        edges=tuple(
            replace(
                edge,
                source_region_id=renamed_ids[edge.source_region_id],
                target_region_id=renamed_ids[edge.target_region_id],
                edge_id=f"renamed-{index:03d}",
            )
            for index, edge in enumerate(snapshot.edges)
        ),
        authority_digest="",
    )
    assert _v4_confidence_observable_key(
        snapshot_to_region_graph(renamed)
    ) == REGION_RESOURCE_V4_DOMAIN_FIXTURE_OBSERVABLE_KEY_SHA256
    recommendation = _transfer_proposal(renamed)
    policy = _FixedPolicy(recommendation)
    monkeypatch.setattr(
        v4_module,
        "build_region_resource_v4_domain_representative_fixture",
        lambda: renamed,
    )
    monkeypatch.setattr(
        v4_module,
        "LearnedRegionResourcePolicy",
        lambda _model, _manifest: policy,
    )
    projector, rule_policy = _policies()

    fixture = v4_module._evaluate_development_fixture(
        SimpleNamespace(model=object(), manifest=object()),
        config=_small_config(),
        projector=projector,
        rule_policy=rule_policy,
    )

    assert fixture["fixture_definition_schema"] == (
        REGION_RESOURCE_V4_DOMAIN_FIXTURE_SCHEMA
    )
    assert fixture["fixture_definition_version"] == (
        REGION_RESOURCE_V4_DOMAIN_FIXTURE_VERSION
    )
    assert fixture["source_region_ids"] == ["area-000"]
    assert fixture["target_region_ids"] == ["area-001"]
    assert fixture["raw_transfer_count"] == 1
    assert fixture["projected_transfer_count"] == 1
    assert fixture["projection_rejection_count"] == 0
    assert fixture["treatment_differs_source"] is True
    assert fixture["treatment_differs_r0"] is True
    assert fixture["intervention_gate_passed"] is True
    assert fixture["candidate_ood"] is False
    assert fixture["fixed_ood_margin"] == 0.05
    assert fixture["fixed_minimum_confidence"] == 0.60
    assert fixture["confidence_margin_above_threshold"] == pytest.approx(
        0.35
    )
    assert fixture["training_domain_smoke_only"] is True
    assert (
        fixture["independent_generalization_evidence_available"] is False
    )
    assert fixture["formal_validation_claim_allowed"] is False
    assert fixture["selection_split"] == "train"
    assert fixture["selection_target_label_use_count"] == 0
    assert fixture["selection_reward_use_count"] == 0
    assert fixture["selection_validation_payload_use_count"] == 0
    assert fixture["selection_test_payload_use_count"] == 0
    assert fixture["selection_seed_or_source_identity_use_count"] == 0
    assert fixture["truth_identifier_use_count"] == 0


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    (
        ("training_domain_smoke_only", False),
        ("independent_generalization_evidence_available", True),
        ("formal_validation_claim_allowed", True),
        ("confidence_margin_above_threshold", 0.0),
        ("confidence_margin_above_threshold", 0.25),
    ),
)
def test_v4_manifest_rejects_fixture_governance_tampering(
    field_name: str,
    tampered_value: object,
) -> None:
    effective_confidence = 0.61
    fixture = {
        "schema": v4_module.REGION_RESOURCE_V4_FIXTURE_SCHEMA,
        "fixture_definition_schema": (
            REGION_RESOURCE_V4_DOMAIN_FIXTURE_SCHEMA
        ),
        "fixture_definition_version": (
            REGION_RESOURCE_V4_DOMAIN_FIXTURE_VERSION
        ),
        "observable_key_sha256": (
            REGION_RESOURCE_V4_DOMAIN_FIXTURE_OBSERVABLE_KEY_SHA256
        ),
        "observable_key_matches_versioned_definition": True,
        "executable_signature_different": True,
        "difference_fields": ["transfer_allowances"],
        "intervention_gate_passed": True,
        "candidate_ood": False,
        "fixed_ood_margin": 0.05,
        "fixed_minimum_confidence": 0.60,
        "effective_confidence": effective_confidence,
        "confidence_margin_above_threshold": (
            effective_confidence - 0.60
        ),
        "training_domain_smoke_only": True,
        "independent_generalization_evidence_available": False,
        "formal_validation_claim_allowed": False,
        "projected_transfer_count": 1,
        "selection_target_label_use_count": 0,
        "selection_reward_use_count": 0,
        "selection_validation_payload_use_count": 0,
        "selection_test_payload_use_count": 0,
        "selection_seed_or_source_identity_use_count": 0,
        "truth_identifier_use_count": 0,
    }
    manifest_kwargs = {
        "candidate_id": REGION_RESOURCE_V4_CANDIDATE_ID,
        "model_version": v4_module.REGION_RESOURCE_V4_MODEL_VERSION,
        "source_identity_sha256": "a" * 64,
        "dataset_sha256": "b" * 64,
        "dataset_split_sha256": "c" * 64,
        "external_dataset_evidence_sha256": "d" * 64,
        "config_sha256": "e" * 64,
        "training_summary_content_sha256": "f" * 64,
        "bundle_manifest_sha256": "1" * 64,
        "model_state_sha256": "2" * 64,
        "runtime_gate_content_sha256": "3" * 64,
        "artifact_files": {"bundle/state_dict.pt": "4" * 64},
    }

    valid = RegionResourceV4CandidateManifest(
        development_fixture=fixture,
        **manifest_kwargs,
    )
    assert valid.development_fixture["training_domain_smoke_only"] is True

    with pytest.raises(
        ValueError,
        match="v4 development fixture lacks executable difference",
    ):
        RegionResourceV4CandidateManifest(
            development_fixture={
                **fixture,
                field_name: tampered_value,
            },
            **manifest_kwargs,
        )


def test_v4_domain_fixture_fails_closed_on_observable_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_region_resource_v4_domain_representative_fixture()
    drifted = replace(
        snapshot,
        regions=(
            replace(snapshot.regions[0], d5_visibility=0.88),
            *snapshot.regions[1:],
        ),
        authority_digest="",
    )
    monkeypatch.setattr(
        v4_module,
        "build_region_resource_v4_domain_representative_fixture",
        lambda: drifted,
    )
    projector, rule_policy = _policies()

    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_development_fixture_observable_key_mismatch",
    ):
        v4_module._evaluate_development_fixture(
            SimpleNamespace(model=object(), manifest=object()),
            config=_small_config(),
            projector=projector,
            rule_policy=rule_policy,
        )


@pytest.mark.parametrize(
    ("ood", "confidence", "reason"),
    (
        (True, 0.95, "v4_development_fixture_is_ood"),
        (
            False,
            0.59,
            "v4_development_fixture_executable_difference_unavailable",
        ),
    ),
)
def test_v4_domain_fixture_keeps_fixed_ood_and_confidence_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    ood: bool,
    confidence: float,
    reason: str,
) -> None:
    snapshot = build_region_resource_v4_domain_representative_fixture()
    policy = _FixedPolicy(
        _transfer_proposal(snapshot, confidence=confidence),
        ood=ood,
    )
    monkeypatch.setattr(
        v4_module,
        "LearnedRegionResourcePolicy",
        lambda _model, _manifest: policy,
    )
    projector, rule_policy = _policies()

    with pytest.raises(RegionResourceV4CandidateError, match=reason):
        v4_module._evaluate_development_fixture(
            SimpleNamespace(model=object(), manifest=object()),
            config=_small_config(),
            projector=projector,
            rule_policy=rule_policy,
        )


def test_external_dataset_governance_accepts_clean_diverse_train_validation(
    tmp_path: Path,
) -> None:
    dataset, evidence = _dataset(tmp_path)
    loaded, _, report = _load_external_dataset_for_v4(
        dataset,
        source_evidence_path=evidence,
        config=_small_config(),
    )

    assert {
        episode.split.value for episode in loaded.episode_records
    } == {"train", "validation"}
    assert report["test_payload_read_count"] == 0
    assert report["positive_negative_calibration_available"] is True
    for split in ("train", "validation"):
        inventory = report["split_action_inventory"][split]
        assert inventory["positive_executable_difference_count"] > 0
        assert (
            inventory["negative_no_executable_difference_count"] > 0
        )
        assert inventory["transfer_target_count"] > 0


@pytest.mark.parametrize(
    ("dirty", "include_negative", "reason"),
    (
        (True, True, "v4_external_dataset_dirty_or_bc_unavailable"),
        (
            False,
            False,
            "v4_train_action_diversity_or_calibration_invalid",
        ),
    ),
)
def test_external_dataset_governance_rejects_dirty_or_all_positive(
    tmp_path: Path,
    dirty: bool,
    include_negative: bool,
    reason: str,
) -> None:
    dataset, evidence = _dataset(
        tmp_path,
        dirty=dirty,
        include_negative=include_negative,
    )
    with pytest.raises(RegionResourceV4CandidateError, match=reason):
        _load_external_dataset_for_v4(
            dataset,
            source_evidence_path=evidence,
            config=_small_config(),
        )


def test_v4_train_only_class_balance_counts_and_caps(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(
        tmp_path,
        negative_frames_per_episode=40,
    )
    _, train_records, _ = _actor_records(dataset)

    balance = _derive_v4_actor_class_balance(train_records)

    assert balance.target_positive_count > 0
    assert (
        balance.target_negative_count
        == 40 * balance.target_positive_count
    )
    assert balance.raw_positive_sample_ratio == pytest.approx(40.0)
    assert balance.positive_sample_weight == 8.0
    assert balance.positive_sample_weight_clipped is True
    assert balance.raw_nonzero_edge_ratio > 32.0
    assert balance.nonzero_edge_weight == 32.0
    assert balance.nonzero_edge_weight_clipped is True
    assert balance.negative_sample_weight == 1.0
    assert balance.zero_edge_weight == 1.0
    assert balance.weight_source_split == "train"
    assert balance.validation_weight_fit_count == 0
    assert balance.test_payload_weight_fit_count == 0
    assert RegionResourceV4ClassBalance.from_mapping(
        balance.to_dict()
    ) == balance


def test_v4_class_balance_rejects_all_noop_train_targets(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(
        tmp_path,
        include_positive=False,
    )
    _, train_records, _ = _actor_records(dataset)

    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_actor_balance_requires_positive_negative",
    ):
        _derive_v4_actor_class_balance(train_records)


@pytest.mark.parametrize(
    "split",
    (RegionLearningSplit.VALIDATION, RegionLearningSplit.TEST),
)
def test_v4_class_balance_rejects_validation_or_test_weight_source(
    tmp_path: Path,
    split: RegionLearningSplit,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    loaded, _, validation_records = _actor_records(dataset)
    if split == RegionLearningSplit.VALIDATION:
        with pytest.raises(
            RegionResourceV4CandidateError,
            match="v4_actor_weights_train_split_only",
        ):
            _derive_v4_actor_class_balance(
                validation_records,
                split=split,
            )
    else:
        projector, rule_policy = _policies()
        with pytest.raises(
            RegionResourceV4CandidateError,
            match="v4_actor_test_or_holdout_payload_read_forbidden",
        ):
            _v4_actor_records(
                loaded,
                split=split,
                projector=projector,
                rule_policy=rule_policy,
            )


def test_v4_class_balance_rejects_tampered_or_nonfinite_weights(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    _, train_records, _ = _actor_records(dataset)
    balance = _derive_v4_actor_class_balance(train_records)

    with pytest.raises(ValueError, match="positive sample weight was altered"):
        replace(
            balance,
            positive_sample_weight=balance.positive_sample_weight + 0.25,
            content_sha256="",
        )
    with pytest.raises(ValueError, match="must be finite and positive"):
        replace(
            balance,
            nonzero_edge_weight=float("nan"),
            content_sha256="",
        )
    with pytest.raises(ValueError, match="fit from TRAIN only"):
        replace(
            balance,
            validation_weight_fit_count=1,
            content_sha256="",
        )


def test_v4_confidence_balance_is_train_only_bounded_and_content_bound() -> None:
    records = (
        (None, True, True, True, ()),
        (None, False, False, True, ("inconsistent",)),
        *(
            (None, False, True, False, ("negative",))
            for _ in range(19)
        ),
    )

    balance = _derive_v4_confidence_balance(records)

    assert balance.target_positive_count == 1
    assert balance.target_negative_count == 20
    assert balance.inconsistent_negative_count == 1
    assert balance.executable_negative_count == 1
    assert balance.ordinary_negative_count == 19
    assert balance.raw_positive_sample_ratio == 20.0
    assert balance.positive_sample_weight == 8.0
    assert balance.positive_sample_weight_clipped is True
    assert balance.raw_inconsistent_negative_ratio == 20.0
    assert balance.inconsistent_negative_weight == 8.0
    assert balance.inconsistent_negative_weight_clipped is True
    assert balance.raw_executable_negative_ratio == 20.0
    assert balance.executable_negative_weight == 20.0
    assert balance.executable_negative_weight_clipped is False
    assert balance.negative_sample_weight == 1.0
    assert balance.weight_source_split == "train"
    assert balance.validation_weight_fit_count == 0
    assert balance.test_payload_weight_fit_count == 0
    assert RegionResourceV4ConfidenceBalance.from_mapping(
        balance.to_dict()
    ) == balance

    with pytest.raises(
        ValueError,
        match="positive sample weight was altered",
    ):
        replace(
            balance,
            positive_sample_weight=7.5,
            content_sha256="",
        )
    with pytest.raises(ValueError, match="finite and positive"):
        replace(
            balance,
            positive_sample_weight=float("inf"),
            content_sha256="",
        )
    with pytest.raises(
        ValueError,
        match="executable-negative weight was altered",
    ):
        replace(
            balance,
            executable_negative_weight=19.0,
            content_sha256="",
        )
    with pytest.raises(ValueError, match="fit from TRAIN only"):
        replace(
            balance,
            test_payload_weight_fit_count=1,
            content_sha256="",
        )

    capped = _derive_v4_confidence_balance(
        (
            (None, True, True, True, ()),
            (None, False, False, True, ("hard-negative",)),
            *(
                (None, False, True, False, ("ordinary-negative",))
                for _ in range(39)
            ),
        )
    )
    assert capped.raw_executable_negative_ratio == 40.0
    assert capped.executable_negative_weight == 32.0
    assert capped.executable_negative_weight_clipped is True


@pytest.mark.parametrize(
    "split",
    (RegionLearningSplit.VALIDATION, RegionLearningSplit.TEST),
)
def test_v4_confidence_balance_rejects_nontrain_weight_source(
    split: RegionLearningSplit,
) -> None:
    records = (
        (None, True, True, True, ()),
        (None, False, False, False, ("negative",)),
    )
    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_confidence_weights_train_split_only",
    ):
        _derive_v4_confidence_balance(records, split=split)


@pytest.mark.parametrize(
    "records",
    (
        ((None, False, True, False, ("no-op",)),),
        ((None, True, True, True, ()),),
    ),
)
def test_v4_confidence_balance_fails_closed_without_both_classes(
    records: tuple[tuple[object, bool, bool, bool, tuple[str, ...]], ...],
) -> None:
    with pytest.raises(
        RegionResourceV4CandidateError,
        match="requires_positive_and_negative_train_labels",
    ):
        _derive_v4_confidence_balance(records)


def test_v4_confidence_validation_weights_reuse_train_only_balance() -> None:
    train_records = (
        (None, True, True, True, ()),
        (None, False, False, True, ("hard-negative",)),
        *((None, False, True, False, ()) for _ in range(7)),
    )
    balance = _derive_v4_confidence_balance(train_records)
    validation_records = (
        *((None, True, True, True, ()) for _ in range(10)),
        (None, False, False, True, ("hard-negative",)),
    )

    weights = _v4_confidence_sample_weights(
        validation_records,
        balance=balance,
    )

    assert weights[:10] == (8.0,) * 10
    assert weights[-1] == 8.0
    assert balance.validation_weight_fit_count == 0
    assert balance.test_payload_weight_fit_count == 0


def test_v4_confidence_margin_is_bound_to_fixed_point_six_gate() -> None:
    torch = pytest.importorskip("torch")
    threshold_logit = torch.logit(torch.tensor(0.60))
    records = (
        (
            torch.sigmoid(threshold_logit + 0.20),
            True,
            True,
            True,
            (),
        ),
        (
            torch.sigmoid(threshold_logit - 0.20),
            False,
            True,
            False,
            (),
        ),
    )
    balance = _derive_v4_confidence_balance(records)
    model = lambda probability: SimpleNamespace(confidence=probability)

    loss = _v4_confidence_margin_loss(
        model,
        records,
        balance=balance,
        logit_margin=0.20,
    )

    assert float(loss) == pytest.approx(0.0, abs=1.0e-12)
    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_confidence_logit_margin_invalid",
    ):
        _v4_confidence_margin_loss(
            model,
            records,
            balance=balance,
            logit_margin=0.10,
        )


def test_v4_confidence_checkpoint_rejects_all_noop_preference() -> None:
    all_noop = {
        "target_positive_count": 4,
        "target_negative_count": 8,
        "positive_threshold_pass_count": 0,
        "negative_threshold_pass_count": 0,
        "inconsistent_threshold_pass_count": 0,
        "executable_threshold_pass_count": 0,
    }
    accepted = {
        **all_noop,
        "positive_threshold_pass_count": 2,
        "executable_threshold_pass_count": 2,
    }

    assert _v4_confidence_checkpoint_selection_key(
        accepted,
        accepted,
        weighted_validation_loss=1.0,
        epoch=20,
    ) > _v4_confidence_checkpoint_selection_key(
        all_noop,
        all_noop,
        weighted_validation_loss=0.0,
        epoch=1,
    )


def test_v4_confidence_identifiability_detects_exact_train_collision(
    tmp_path: Path,
) -> None:
    torch = pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    _, train_records, _ = _actor_records(dataset)
    graph = train_records[0].sample.graph
    identity_metadata_variant = replace(
        graph,
        node_ids=tuple(
            f"renamed-node-{index}"
            for index, _ in enumerate(graph.node_ids)
        ),
        edge_refs=tuple(
            replace(
                edge,
                edge_id=f"renamed-edge-{index}",
                source_region_id=f"renamed-source-{index}",
                target_region_id=f"renamed-target-{index}",
                transferable_resources=edge.transferable_resources + 100,
                transfer_time_s=edge.transfer_time_s + 100.0,
            )
            for index, edge in enumerate(graph.edge_refs)
        ),
    )
    records = (
        (graph, True, True, True, ()),
        (
            identity_metadata_variant,
            False,
            False,
            True,
            ("actor_target_signature_mismatch",),
        ),
        (
            train_records[1].sample.graph,
            False,
            True,
            False,
            ("actor_no_executable_difference",),
        ),
    )

    audit = _audit_v4_confidence_identifiability(records)

    assert audit["fit_split"] == "train"
    assert audit["train_record_count"] == 3
    assert audit["conflicting_key_count"] == 1
    assert audit["conflicting_record_count"] == 2
    assert audit["conflicting_positive_count"] == 1
    assert audit["conflicting_negative_count"] == 1
    assert audit["accepted"] is False
    assert audit["validation_label_use_count"] == 0
    assert audit["test_payload_use_count"] == 0
    assert (
        audit["observable_key_uses_target_or_source_identity"] is False
    )
    assert (
        audit["observable_key_uses_node_or_edge_identity_metadata"] is False
    )
    assert (
        audit["observable_key_binds_tensor_shape_dtype_and_architecture"]
        is True
    )
    assert len(audit["content_sha256"]) == 64
    assert _v4_confidence_observable_key(
        graph
    ) == _v4_confidence_observable_key(identity_metadata_variant)
    dtype_variant = replace(
        graph,
        node_features=graph.node_features.to(dtype=torch.float64),
    )
    assert _v4_confidence_observable_key(
        graph
    ) != _v4_confidence_observable_key(dtype_variant)

    accepted = _audit_v4_confidence_identifiability(
        (
            (graph, True, True, True, ()),
            (
                train_records[1].sample.graph,
                False,
                True,
                False,
                ("actor_no_executable_difference",),
            ),
        )
    )
    assert accepted["conflicting_key_count"] == 0
    assert accepted["accepted"] is True


@pytest.mark.parametrize(
    "split",
    (RegionLearningSplit.VALIDATION, RegionLearningSplit.TEST),
)
def test_v4_confidence_identifiability_rejects_nontrain_source(
    tmp_path: Path,
    split: RegionLearningSplit,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    _, train_records, _ = _actor_records(dataset)
    graph = train_records[0].sample.graph
    records = (
        (graph, True, True, True, ()),
        (graph, False, False, True, ("negative",)),
    )

    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_confidence_identifiability_train_split_only",
    ):
        _audit_v4_confidence_identifiability(records, split=split)


def test_v4_confidence_fit_fails_closed_on_train_observable_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    _, train_records, validation_records = _actor_records(dataset)
    train_graph = train_records[0].sample.graph
    validation_graph = validation_records[0].sample.graph
    confidence_records = {
        RegionLearningSplit.TRAIN: (
            (train_graph, True, True, True, ()),
            (
                train_graph,
                False,
                False,
                True,
                ("actor_target_signature_mismatch",),
            ),
        ),
        RegionLearningSplit.VALIDATION: (
            (validation_graph, True, True, True, ()),
            (
                validation_graph,
                False,
                False,
                True,
                ("actor_target_signature_mismatch",),
            ),
        ),
    }
    monkeypatch.setattr(
        v4_module,
        "_confidence_records",
        lambda _model, _loaded, *, split, projector, rule_policy: (
            confidence_records[split]
        ),
    )
    config = _small_config()
    model = SharedRegionGraphActorCritic(
        hidden_dim=config.hidden_dim,
        message_passing_steps=config.message_passing_steps,
    )
    projector, rule_policy = _policies()

    with pytest.raises(
        RegionResourceV4CandidateError,
        match=(
            "v4_confidence_train_observable_label_conflict:"
            "keys=1,records=2,positive=1,negative=1"
        ),
    ):
        _fit_confidence_head(
            model,
            object(),
            config=config,
            projector=projector,
            rule_policy=rule_policy,
        )


def test_v4_checkpoint_selection_prefers_dual_class_over_noop_loss() -> None:
    all_noop = {
        "dual_class_checkpoint_threshold_passed": False,
        "minimum_class_hit_rate": 0.0,
        "balanced_hit_rate": 0.5,
        "actor_projection_rejection_count": 0,
    }
    dual_class = {
        "dual_class_checkpoint_threshold_passed": True,
        "minimum_class_hit_rate": 0.1,
        "balanced_hit_rate": 0.2,
        "actor_projection_rejection_count": 5,
    }

    assert _v4_checkpoint_selection_key(
        dual_class,
        weighted_validation_loss=10.0,
        epoch=20,
    ) > _v4_checkpoint_selection_key(
        all_noop,
        weighted_validation_loss=0.001,
        epoch=1,
    )


def test_v4_actor_audit_retains_projection_rejected_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    _, train_records, _ = _actor_records(dataset)
    projector, rule_policy = _policies()
    monkeypatch.setattr(
        LearnedRegionResourcePolicy,
        "recommend_raw",
        lambda _self, snapshot: _transfer_proposal(
            snapshot,
            count=2,
        ),
    )

    metrics = _v4_actor_metrics(
        object(),
        train_records,
        projector=projector,
        rule_policy=rule_policy,
    )

    assert metrics["sample_count"] == len(train_records)
    assert metrics["actor_projection_rejection_count"] == len(
        train_records
    )
    assert (
        metrics["negative_reason_inventory"][
            "actor_projection_clipped_or_rejected"
        ]
        == len(train_records)
    )


@pytest.mark.parametrize(
    "split",
    (RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
)
def test_v4_confidence_audit_retains_projection_rejected_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    split: RegionLearningSplit,
) -> None:
    pytest.importorskip("torch")
    dataset, _ = _dataset(tmp_path)
    loaded, _, _ = _actor_records(dataset)
    projector, rule_policy = _policies()
    monkeypatch.setattr(
        LearnedRegionResourcePolicy,
        "recommend_raw",
        lambda _self, snapshot: _transfer_proposal(
            snapshot,
            count=2,
        ),
    )
    config = _small_config()
    model = SharedRegionGraphActorCritic(
        hidden_dim=config.hidden_dim,
        message_passing_steps=config.message_passing_steps,
    )

    records = _confidence_records(
        model,
        loaded,
        split=split,
        projector=projector,
        rule_policy=rule_policy,
    )
    metrics = _confidence_metrics(model, records)

    assert len(records) > 0
    assert all(
        "actor_projection_clipped_or_rejected" in record[4]
        for record in records
    )
    assert metrics["projection_rejected_record_count"] == len(records)
    assert (
        metrics["negative_reason_inventory"][
            "actor_projection_clipped_or_rejected"
        ]
        == len(records)
    )


def test_external_source_evidence_rejects_missing_or_dirty_identity() -> None:
    base = {
        "dataset_sha256": "a" * 64,
        "dataset_split_sha256": "b" * 64,
        "source_artifact_sha256": "c" * 64,
        "source_kind": "main_runtime_frames",
        "truth_free_online_features": True,
        "generated_by_v4_builder": False,
        "source_worktree_dirty": False,
    }
    RegionResourceV4ExternalDatasetEvidence(**base)
    with pytest.raises(ValueError, match="zero-filled"):
        RegionResourceV4ExternalDatasetEvidence(
            **{**base, "source_artifact_sha256": "0" * 64}
        )
    with pytest.raises(ValueError, match="provenance is not admissible"):
        RegionResourceV4ExternalDatasetEvidence(
            **{**base, "source_worktree_dirty": True}
        )


def test_unregistered_v4_cannot_enter_registry_or_runtime(
    tmp_path: Path,
) -> None:
    assert (
        REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256,
        REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256,
        REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256,
        REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256,
        REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256,
    ) == (None, None, None, None, None)
    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_candidate_unregistered",
    ):
        RegionResourceV4CandidateLoader(
            tmp_path / REGION_RESOURCE_V4_CANDIDATE_ID
        )
    with pytest.raises(
        RegionResourceV4CandidateError,
        match="v4_unregistered_registry_destination_forbidden",
    ):
        build_region_resource_v4_development_candidate(
            REPOSITORY_ROOT
            / "research_modules/d4_distributed_fallback/model_registry"
            / REGION_RESOURCE_V4_CANDIDATE_ID,
            repository_root=REPOSITORY_ROOT,
            input_dataset_dir=tmp_path / "missing-dataset",
            source_evidence_path=tmp_path / "missing-evidence.json",
            config=_small_config(),
        )
    assert not any(
        value
        for name, value in RegionResourceV4Permissions().to_dict().items()
        if name != "schema"
    )


def test_v3_registry_tree_is_byte_for_byte_unchanged() -> None:
    assert _tree_sha256(V3_ROOT) == REGION_RESOURCE_V3_FROZEN_TREE_SHA256


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    (
        ("ood", "candidate_ood_rejected"),
        ("expired", "candidate_advisory_window_expired"),
        ("illegal", "clipped_by_safety_projection"),
        ("low_confidence", "candidate_effective_confidence_below_minimum"),
    ),
)
def test_ood_expired_illegal_and_low_confidence_fall_back_to_rule(
    case: str,
    expected_reason: str,
) -> None:
    snapshot = build_region_resource_v4_development_fixture()
    if case == "ood":
        recommendation = _transfer_proposal(snapshot)
        policy = _FixedPolicy(recommendation, ood=True)
    elif case == "illegal":
        recommendation = _transfer_proposal(
            snapshot,
            count=2,
            confidence=0.99,
        )
        policy = _FixedPolicy(recommendation)
    elif case == "low_confidence":
        recommendation = _transfer_proposal(
            snapshot,
            confidence=0.10,
        )
        policy = _FixedPolicy(recommendation)
    else:
        recommendation = _transfer_proposal(snapshot)
        policy = _FixedPolicy(recommendation)
    loader = _evaluation_loader(policy)
    advisor = _advisor_with_loader(loader)
    evaluated_at_s = (
        snapshot.timestamp_s + _V4_PROJECTION.advisory_ttl_s + 0.01
        if case == "expired"
        else snapshot.timestamp_s
    )

    decision = advisor.advise_pair(
        snapshot,
        evaluated_at_s=evaluated_at_s,
    )

    assert decision.rule_fallback_used is True
    assert decision.shadow_treatment_selected is False
    assert decision.executable_signature_different is False
    assert expected_reason in ",".join(decision.rejection_reasons)
    control_signature, _ = executable_signature(decision.control_advisory)
    treatment_signature, _ = executable_signature(
        decision.treatment_advisory
    )
    assert treatment_signature == control_signature
    assert decision.production_runtime_ack_emitted is False
    assert decision.assignment_authority_granted is False
    assert decision.degradation_authority_granted is False
    assert decision.control_authority_granted is False
