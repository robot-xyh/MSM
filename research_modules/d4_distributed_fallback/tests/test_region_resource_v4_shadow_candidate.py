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
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    stage_region_learning_episode,
)
from d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V3_FROZEN_TREE_SHA256,
    REGION_RESOURCE_V4_CANDIDATE_ID,
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256,
    REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256,
    REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256,
    REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256,
    RegionResourceV4BuildConfig,
    RegionResourceV4CandidateError,
    RegionResourceV4CandidateLoader,
    RegionResourceV4ExternalDatasetEvidence,
    RegionResourceV4Permissions,
    RegionResourceV4ShadowAdvisor,
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    _load_external_dataset_for_v4,
    build_region_resource_v4_development_candidate,
    build_region_resource_v4_development_fixture,
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
    actions = tuple(
        replace(
            action,
            resource_quota_delta=(
                -count
                if action.region_id == "region-000"
                else count
                if action.region_id == "region-001"
                else 0
            ),
        )
        for action in baseline.actions
    )
    transfer = RegionTransferSuggestion(
        source_region_id="region-000",
        target_region_id="region-001",
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
    include_negative: bool = True,
) -> tuple[Path, Path]:
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
        frame_count = 2 if include_negative else 1
        for frame_index in range(frame_count):
            timestamp_s = 0.5 * frame_index
            base = build_region_resource_v4_development_fixture(
                seed=seed,
                timestamp_s=timestamp_s,
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
                if frame_index == 0
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
