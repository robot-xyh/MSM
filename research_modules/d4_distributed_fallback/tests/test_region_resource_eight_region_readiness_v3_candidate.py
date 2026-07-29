from __future__ import annotations

from hashlib import sha256
import json
from math import log
from pathlib import Path
from typing import Any, cast

import pytest
import torch

from d4_distributed_fallback.region_resource import (
    AdvisorMode,
    RegionResourceNode,
    RegionResourceProjectionConfig,
    RegionResourceSnapshot,
)
from d4_distributed_fallback.region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_READINESS_CONFIG_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_MODEL_VERSION,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_ADVISORY_TTL_S,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CONFIG_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION,
    RegionResourceEightRegionCandidateConfig,
    RegionResourceEightRegionCandidateError,
    RegionResourceEightRegionCandidateManifest,
    RegionResourceEightRegionReadinessV3CandidateConfig,
    _load_verified_eight_region_candidate_config,
    _readiness_runtime_context,
    _sha256_json,
    build_region_resource_eight_region_readiness_v3_candidate,
    review_region_resource_eight_region_candidate,
)
from d4_distributed_fallback.region_resource_learning import (
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
    SharedRegionGraphActorCritic,
    save_region_resource_model_bundle,
    snapshot_to_region_graph,
)
from d4_distributed_fallback.regional_failover import (
    RegionalAuthorityLayer,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
V2_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
    / REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID
)
V2_TREE_SHA256 = (
    "324a51181017ed6baae97893f32da5bf3f9364c1da6b6c046a0a9af4109e5010"
)


def _snapshot() -> RegionResourceSnapshot:
    node = RegionResourceNode(
        region_id="region-000",
        target_demand=1.0,
        high_threat_backlog=0.0,
        d1_uncertainty=0.2,
        d2_uncertainty=0.1,
        d5_visibility=0.8,
        d5_consistency=0.9,
        available_resources=10,
        reserve_resources=2,
        secondary_coverage=0.9,
        secondary_readiness=0.0,
        communication_capacity=100.0,
        communication_latency_s=0.02,
        packet_loss_rate=0.01,
        current_owner_id="CENTER",
        current_owner_layer=RegionalAuthorityLayer.CENTER,
        plan_id="regional-plan",
        plan_version=3,
        epoch=2,
        lease_expires_at_s=20.0,
        coalition_ack_complete=True,
    )
    return RegionResourceSnapshot(
        snapshot_id="readiness-v3-runtime-contract",
        scenario_id="readiness-v3-test",
        scenario_version="v1",
        seed=7,
        timestamp_s=1.0,
        regions=(node,),
        edges=(),
    )


def _model() -> SharedRegionGraphActorCritic:
    model = SharedRegionGraphActorCritic(
        hidden_dim=16,
        message_passing_steps=1,
    )
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.node_actor.bias[1] = log(0.2 / 0.8)
        model.node_actor.bias[2] = log(0.12 / 0.88)
        model.node_actor.bias[3] = -10.0
        model.node_actor.bias[4] = -10.0
        model.confidence_head[0].bias[0] = log(0.90 / 0.10)
    model.eval()
    return model


def _v3_bundle(tmp_path: Path) -> Path:
    snapshot = _snapshot()
    _, _, gate = _readiness_runtime_context(
        RegionResourceEightRegionReadinessV3CandidateConfig()
    )
    bundle = tmp_path / "v3-bundle"
    save_region_resource_model_bundle(
        _model(),
        bundle,
        model_version=(
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
        ),
        training_graphs=(snapshot_to_region_graph(snapshot),),
        training_groups=((snapshot.scenario_id, snapshot.seed),),
        created_at_utc="2026-07-29T00:00:00Z",
        runtime_confidence_gate=gate,
    )
    return bundle


def test_v3_identity_and_projection_contract_are_immutable() -> None:
    config = RegionResourceEightRegionReadinessV3CandidateConfig()
    projector, rule_policy, gate = _readiness_runtime_context(config)

    assert config.schema == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CONFIG_SCHEMA
    )
    assert config.candidate_id == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    )
    assert config.model_version == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
    )
    assert projector.config == RegionResourceProjectionConfig(
        minimum_reserve_ratio=0.1,
        minimum_reserve_resources=1,
        advisory_ttl_s=(
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_ADVISORY_TTL_S
        ),
    )
    assert rule_policy.projector is projector
    assert gate.projection_config["advisory_ttl_s"] == 1.5
    assert gate.rule_policy_config["projection"] == gate.projection_config
    assert gate.fixed_ood_margin == 0.05
    assert gate.fixed_minimum_confidence == 0.60
    assert gate.inconsistent_confidence_cap == 0.59
    assert gate.continuous_tolerance == 0.10

    with pytest.raises(
        ValueError,
        match="readiness v3 projection contract changed",
    ):
        RegionResourceEightRegionReadinessV3CandidateConfig(
            runtime_projection_advisory_ttl_s=1.0
        )


def test_v3_builder_rejects_v2_identity_before_dataset_access(
    tmp_path: Path,
) -> None:
    v2 = RegionResourceEightRegionCandidateConfig(
        candidate_id=REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID,
        model_version=REGION_RESOURCE_EIGHT_REGION_READINESS_MODEL_VERSION,
        schema=REGION_RESOURCE_EIGHT_REGION_READINESS_CONFIG_SCHEMA,
    )
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="readiness_v3_builder_requires_v3_identity",
    ):
        build_region_resource_eight_region_readiness_v3_candidate(
            tmp_path / "runtime",
            tmp_path / "action",
            tmp_path / "readiness",
            readiness_generation_summary_path=tmp_path / "summary.json",
            readiness_dataset_audit_path=tmp_path / "audit.json",
            repository_root=tmp_path,
            output_dir=(
                tmp_path
                / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
            ),
            config=cast(Any, v2),
        )


def test_v3_review_config_loader_requires_exact_identity_and_hash(
    tmp_path: Path,
) -> None:
    root = tmp_path / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    root.mkdir()
    config = RegionResourceEightRegionReadinessV3CandidateConfig()
    payload = config.to_dict()
    config_sha = _sha256_json(payload)
    (root / "training_config.json").write_text(
        json.dumps(
            {**payload, "config_sha256": config_sha},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    loaded = _load_verified_eight_region_candidate_config(
        root,
        candidate_schema=(
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
        ),
        expected_config_sha256=config_sha,
    )
    assert isinstance(
        loaded,
        RegionResourceEightRegionReadinessV3CandidateConfig,
    )
    assert loaded.runtime_projection_advisory_ttl_s == 1.5

    tampered = dict(payload)
    tampered["runtime_projection_advisory_ttl_s"] = 1.0
    tampered_sha = _sha256_json(tampered)
    (root / "training_config.json").write_text(
        json.dumps(
            {**tampered, "config_sha256": tampered_sha},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="candidate_training_config_invalid:ValueError",
    ):
        _load_verified_eight_region_candidate_config(
            root,
            candidate_schema=(
                REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
            ),
            expected_config_sha256=tampered_sha,
        )


def test_v3_manifest_identity_cannot_mix_v2_model_version() -> None:
    payload = json.loads(
        (
            V2_ROOT / "eight_region_shadow_candidate_manifest.json"
        ).read_text(encoding="utf-8")
    )
    payload.update(
        {
            "schema": (
                REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
            ),
            "candidate_id": (
                REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
            ),
            "model_version": (
                REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
            ),
            "content_sha256": "",
        }
    )
    manifest = RegionResourceEightRegionCandidateManifest.from_mapping(
        payload
    )
    assert manifest.schema == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
    )

    payload["model_version"] = (
        REGION_RESOURCE_EIGHT_REGION_READINESS_MODEL_VERSION
    )
    with pytest.raises(
        ValueError,
        match="eight-region candidate identity mismatch",
    ):
        RegionResourceEightRegionCandidateManifest.from_mapping(payload)


def test_v3_gate_matches_15_advisor_and_rejects_10(
    tmp_path: Path,
) -> None:
    bundle = _v3_bundle(tmp_path)
    matching_projection = RegionResourceProjectionConfig(
        minimum_reserve_ratio=0.1,
        minimum_reserve_resources=1,
        advisory_ttl_s=1.5,
    )
    matching = RegionResourceAdvisor.from_bundle(
        bundle,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.60,
            ood_margin=0.05,
            projection=matching_projection,
        ),
        expected_model_version=(
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
        ),
    ).advise(_snapshot())
    matching_diagnostic = matching.runtime_confidence_gate_diagnostic
    assert matching_diagnostic is not None
    assert matching_diagnostic.model_raw_inference_executed is True
    assert matching_diagnostic.gate_applied is True
    assert matching.fallback_reason != (
        "runtime_confidence_gate_context_mismatch"
    )

    mismatching = RegionResourceAdvisor.from_bundle(
        bundle,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.60,
            ood_margin=0.05,
            projection=RegionResourceProjectionConfig(
                advisory_ttl_s=1.0
            ),
        ),
        expected_model_version=(
            REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
        ),
    ).advise(_snapshot())
    assert mismatching.fallback_used is True
    assert mismatching.fallback_reason == (
        "runtime_confidence_gate_context_mismatch"
    )
    mismatching_diagnostic = (
        mismatching.runtime_confidence_gate_diagnostic
    )
    assert mismatching_diagnostic is not None
    assert mismatching_diagnostic.model_raw_inference_executed is False
    assert mismatching_diagnostic.gate_applied is False
    assert mismatching_diagnostic.rule_fallback_due_to_gate is True


def test_v2_registry_bytes_and_ttl_10_behavior_remain_unchanged() -> None:
    inventory = {
        str(path.relative_to(V2_ROOT)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(V2_ROOT.rglob("*"))
        if path.is_file()
    }
    assert _sha256_json(inventory) == V2_TREE_SHA256
    review = review_region_resource_eight_region_candidate(V2_ROOT)
    assert review["candidate_id"] == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_CANDIDATE_ID
    )
    bundle_manifest = json.loads(
        (V2_ROOT / "bundle/manifest.json").read_text(encoding="utf-8")
    )
    gate = bundle_manifest["runtime_confidence_gate"]
    assert gate["projection_config"]["advisory_ttl_s"] == 1.0
    assert (
        gate["rule_policy_config"]["projection"]["advisory_ttl_s"]
        == 1.0
    )
