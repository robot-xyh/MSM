from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d6_evaluation_metrics.d4_a2_paired_shadow_audit import (
    D4_A2_CANDIDATE_MANIFEST_SHA256,
    D4_A2_FROZEN_SEED_REGISTRY_SCHEMA_VERSION,
    D4_A2_MODEL_STATE_SHA256,
    audit_d4_a2_paired_shadow,
    build_d4_a2_paired_shadow_audit_input,
)
from d6_evaluation_metrics.learning_run_readiness import (
    LEARNING_VARIANTS,
    READINESS_GATES,
    audit_learning_run_readiness,
    build_learning_run_readiness_input,
)
from d6_evaluation_metrics.learning_run_source_adapters import (
    D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION,
    D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION,
    LearningRunSourceAdapterError,
    load_learning_run_source_evidence_bytes,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceSnapshot,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_current_lineage_shadow import (
    RegionResourceCurrentLineageShadowAdapter,
    RegionResourceCurrentLineageShadowSeedRegistration,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.regional_failover import (
    RegionalAuthorityLayer,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_CANDIDATE = (
    REPOSITORY_ROOT
    / "research_modules"
    / "d4_distributed_fallback"
    / "model_registry"
    / "region_resource_a2_current_lineage_development_v1"
)
SOURCE_REFERENCE = (
    REPOSITORY_ROOT
    / "research_modules"
    / "d6_evaluation_metrics"
    / "configs"
    / "d4_a2_current_lineage_model_source_reference_20260728.json"
)


def _canonical_sha(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reference(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "file_sha256": sha256(path.read_bytes()).hexdigest(),
    }


def _candidate_fixture(root: Path) -> Path:
    target = root / SOURCE_CANDIDATE.name
    shutil.copytree(SOURCE_CANDIDATE, target)
    return target


def _model_source_reference(root: Path, candidate: Path) -> Path:
    manifest = candidate / "current_lineage_candidate_manifest.json"
    body = {
        "schema_version": (
            D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "variant": "A2",
        "candidate_manifest": _reference(root, manifest),
    }
    payload = {**body, "content_sha256": _canonical_sha(body)}
    path = root / "references" / "model_source.json"
    _write_json(path, payload)
    return path


def _snapshot(seed: int, frame_index: int) -> RegionResourceSnapshot:
    common = {
        "d1_uncertainty": 500.0,
        "d2_uncertainty": 250.0,
        "d5_visibility": 0.85,
        "d5_consistency": 0.90,
        "reserve_resources": 1,
        "secondary_coverage": 0.0,
        "secondary_readiness": 0.0,
        "communication_capacity": 50.0,
        "communication_latency_s": 0.02,
        "packet_loss_rate": 0.01,
        "current_owner_id": "CENTER",
        "current_owner_layer": RegionalAuthorityLayer.CENTER,
        "plan_id": f"smoke-plan-{frame_index}",
        "plan_version": frame_index + 2,
        "epoch": 3,
        "lease_expires_at_s": 30.0 + frame_index,
        "coalition_ack_complete": True,
        "owner_active": True,
        "fault_fenced": False,
    }
    return RegionResourceSnapshot(
        snapshot_id=f"a2-smoke-{seed}-{frame_index}",
        scenario_id="standard-5r-5t-two-region",
        scenario_version="v1",
        seed=seed,
        timestamp_s=float(frame_index),
        regions=(
            RegionResourceNode(
                region_id="west",
                target_demand=5.0,
                high_threat_backlog=1.0,
                available_resources=2,
                committed_resources=1,
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
            ),
        ),
    )


def _in_distribution_snapshot(seed: int) -> RegionResourceSnapshot:
    common = {
        "high_threat_backlog": 0.0,
        "reserve_resources": 1,
        "secondary_coverage": 0.90,
        "secondary_readiness": 0.90,
        "communication_capacity": 50.0,
        "communication_latency_s": 0.02,
        "packet_loss_rate": 0.01,
        "current_owner_id": "CENTER",
        "current_owner_layer": RegionalAuthorityLayer.CENTER,
        "plan_id": "in-distribution-plan",
        "plan_version": 7,
        "epoch": 4,
        "lease_expires_at_s": 120.0,
        "committed_resources": 0,
        "coalition_ack_complete": True,
        "owner_active": True,
        "fault_fenced": False,
        "degradation_failed": False,
    }
    region_values = (
        ("region-000", 4.0, 0.13, 0.095, 0.885, 0.905, 5),
        ("region-001", 3.0, 0.20, 0.130, 0.850, 0.870, 4),
        ("region-002", 3.0, 0.16, 0.110, 0.870, 0.890, 4),
        ("region-003", 3.0, 0.12, 0.090, 0.890, 0.910, 4),
    )
    regions = tuple(
        RegionResourceNode(
            region_id=region_id,
            target_demand=demand,
            d1_uncertainty=d1,
            d2_uncertainty=d2,
            d5_visibility=visibility,
            d5_consistency=consistency,
            available_resources=available,
            **common,
        )
        for (
            region_id,
            demand,
            d1,
            d2,
            visibility,
            consistency,
            available,
        ) in region_values
    )
    edges = tuple(
        RegionResourceEdge(
            source_region_id=f"region-{index:03d}",
            target_region_id=f"region-{(index + 1) % 4:03d}",
            transferable_resources=0,
            distance_m=500.0 + 25.0 * index,
            transfer_time_s=10.0 + index,
            bandwidth_mbps=20.0,
            edge_id=f"edge-{index:03d}",
            bidirectional=True,
            partitioned=False,
        )
        for index in range(4)
    )
    return RegionResourceSnapshot(
        snapshot_id=f"in-distribution-{seed}",
        scenario_id="in-distribution-noop-smoke",
        scenario_version="v1",
        seed=seed,
        timestamp_s=0.0,
        regions=regions,
        edges=edges,
    )


def _write_runtime_reference(
    root: Path,
    records: list[object],
    *,
    name: str = "runtime",
) -> Path:
    records_path = root / name / "shadow_records.jsonl"
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text(
        "".join(
            json.dumps(record.to_dict(), sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    body = {
        "schema_version": (
            D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "variant": "A2",
        "shadow_records": _reference(root, records_path),
    }
    payload = {**body, "content_sha256": _canonical_sha(body)}
    reference_path = root / "references" / f"{name}_distribution.json"
    _write_json(reference_path, payload)
    return reference_path


def _runtime_evidence(
    root: Path,
    candidate: Path,
    *,
    seed: int = 2000,
) -> tuple[Path, RegionResourceCurrentLineageShadowSeedRegistration]:
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    registration = RegionResourceCurrentLineageShadowSeedRegistration(
        registry_id="main-preregistered-unseen-shadow",
        registry_version=1,
        episode_id=f"a2-candidate-seed-{seed}",
        scenario_id="standard-5r-5t-two-region",
        scenario_version="v1",
        seed=seed,
        candidate_binding_sha256=adapter.candidate_binding.binding_sha256,
        excluded_calibration_seeds=(9999,),
        calibration_catalog_complete=True,
    )
    records = [
        adapter.evaluate(
            registration,
            _snapshot(seed, frame_index),
            frame_index=frame_index,
        )
        for frame_index in range(6)
    ]
    reference_path = _write_runtime_reference(root, records)
    return reference_path, registration


def _unavailable(reason: str) -> dict[str, object]:
    return {
        "availability": False,
        "source_artifact": None,
        "reason_codes": [reason],
    }


def _storage() -> dict[str, object]:
    return {
        "availability": True,
        "source_class": "filesystem_disk_usage_snapshot",
        "observed_at_utc": "2026-07-28T20:00:00Z",
        "mounts": [
            {
                "path": "/evidence",
                "available_bytes": 25 * 1024**3,
                "eligible_for_formal_output": True,
            }
        ],
        "reason_codes": [],
    }


def test_fixed_a2_source_is_recomputed_from_original_artifacts(
    tmp_path: Path,
) -> None:
    candidate = _candidate_fixture(tmp_path)
    reference = _model_source_reference(tmp_path, candidate)

    evidence = load_learning_run_source_evidence_bytes(
        reference.read_bytes(),
        artifact_root=tmp_path,
        expected_variant="A2",
        expected_gate="model_source",
    )

    assert evidence["source_class"] == "formal_current_lineage_source_audit"
    assert evidence["facts"]["audit_passed"] is True
    assert evidence["facts"]["model_identity"] == (
        f"sha256:{D4_A2_MODEL_STATE_SHA256}"
    )


def test_checked_in_reference_uses_versioned_model_registry() -> None:
    payload = json.loads(SOURCE_REFERENCE.read_text(encoding="utf-8"))
    candidate_path = Path(payload["candidate_manifest"]["path"])

    assert "model_registry" in candidate_path.parts
    assert "outputs" not in candidate_path.parts
    evidence = load_learning_run_source_evidence_bytes(
        SOURCE_REFERENCE.read_bytes(),
        artifact_root=REPOSITORY_ROOT,
        expected_variant="A2",
        expected_gate="model_source",
    )
    assert evidence["source_class"] == "formal_current_lineage_source_audit"
    assert evidence["facts"]["audit_passed"] is True
    assert evidence["facts"]["model_identity"] == (
        f"sha256:{D4_A2_MODEL_STATE_SHA256}"
    )


def test_fixed_a2_source_rejects_weight_tampering(tmp_path: Path) -> None:
    candidate = _candidate_fixture(tmp_path)
    reference = _model_source_reference(tmp_path, candidate)
    weights = candidate / "bundle" / "state_dict.pt"
    weights.write_bytes(weights.read_bytes() + b"tampered")

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="d4_a2_candidate_manifest_rejected",
    ):
        load_learning_run_source_evidence_bytes(
            reference.read_bytes(),
            artifact_root=tmp_path,
            expected_variant="A2",
            expected_gate="model_source",
        )


def test_readiness_separates_source_from_runtime_distribution(
    tmp_path: Path,
) -> None:
    candidate = _candidate_fixture(tmp_path)
    model_reference = _model_source_reference(tmp_path, candidate)
    runtime_reference, _ = _runtime_evidence(tmp_path, candidate)
    variants: dict[str, object] = {}
    for variant in LEARNING_VARIANTS:
        gates = {
            gate: _unavailable(f"{variant.lower()}_{gate}_not_supplied")
            for gate in READINESS_GATES
        }
        if variant == "A2":
            gates["model_source"] = {
                "availability": True,
                "source_artifact": _reference(tmp_path, model_reference),
                "reason_codes": [],
            }
            gates["runtime_distribution_compatible"] = {
                "availability": True,
                "source_artifact": _reference(tmp_path, runtime_reference),
                "reason_codes": [],
            }
        variants[variant] = {"variant": variant, "gates": gates}
    request = build_learning_run_readiness_input(
        audit_id="a2-current-lineage-ood-smoke",
        variants=variants,
        storage=_storage(),
    )

    result = audit_learning_run_readiness(request, artifact_root=tmp_path)
    row = result["variants"]["A2"]
    distribution = row["gates"]["runtime_distribution_compatible"]

    assert row["model_source_verified"] is True
    assert row["runtime_distribution_compatible"] is False
    assert distribution["facts"]["audited_snapshot_count"] == 6
    assert distribution["facts"]["finite_record_count"] == 6
    assert distribution["facts"]["nonfinite_record_count"] == 0
    assert distribution["facts"]["feature_ood_snapshot_count"] == 6
    assert distribution["facts"]["model_action_count"] == 0
    assert distribution["facts"]["rule_fallback_count"] == 6
    assert "a2_runtime_feature_ood" in distribution["reason_codes"]
    assert "a2_model_action_missing" not in distribution["reason_codes"]
    assert "a2_rule_fallback_only_not_treatment" not in (
        distribution["reason_codes"]
    )
    assert any(
        reason.startswith("a2_runtime_feature_ood.node:")
        for reason in distribution["reason_codes"]
    )


def test_paired_audit_keeps_ood_rule_fallback_unavailable(
    tmp_path: Path,
) -> None:
    candidate = _candidate_fixture(tmp_path)
    model_reference = _model_source_reference(tmp_path, candidate)
    runtime_reference, registration = _runtime_evidence(tmp_path, candidate)
    registry_body = {
        "schema_version": D4_A2_FROZEN_SEED_REGISTRY_SCHEMA_VERSION,
        "registry_id": "main-preregistered-unseen-shadow",
        "registry_version": 1,
        "frozen_at_utc": "2026-07-28T19:00:00Z",
        "frozen_before_execution": True,
        "candidate_manifest_file_sha256": (
            D4_A2_CANDIDATE_MANIFEST_SHA256
        ),
        "model_state_sha256": D4_A2_MODEL_STATE_SHA256,
        "evaluation_seeds": [2000],
        "registrations": [
            {
                "seed": 2000,
                "episode_id": registration.episode_id,
                "registered_at_utc": "2026-07-28T19:10:00Z",
                "candidate_binding_sha256": (
                    registration.candidate_binding_sha256
                ),
                "registration": registration.to_dict(),
            }
        ],
    }
    registry = {
        **registry_body,
        "content_sha256": _canonical_sha(registry_body),
    }
    metric = {
        "numerator": 1.0,
        "denominator": 1,
        "value": 1.0,
        "direction": "lower",
        "tolerance": 0.0,
    }
    pair = {
        "seed": 2000,
        "started_at_utc": "2026-07-28T19:20:00Z",
        "candidate_episode_id": registration.episode_id,
        "r0_episode_id": "a2-r0-seed-2000",
        "candidate_event_log_sha256": "1" * 64,
        "r0_event_log_sha256": "2" * 64,
        "candidate_external_config_sha256": "3" * 64,
        "r0_external_config_sha256": "3" * 64,
        "model_state_sha256": D4_A2_MODEL_STATE_SHA256,
        "adoption_records": [],
        "online_truth_use_count": 0,
        "audited_finite_value_count": 12,
        "nonfinite_value_count": 0,
        "candidate_metrics": {"plan_churn": metric},
        "r0_metrics": {"plan_churn": metric},
    }
    request = build_d4_a2_paired_shadow_audit_input(
        audit_id="a2-ood-rule-fallback-smoke",
        model_source_reference=_reference(tmp_path, model_reference),
        runtime_distribution_reference=_reference(
            tmp_path,
            runtime_reference,
        ),
        seed_registry=registry,
        required_metrics=("plan_churn",),
        pairs=(pair,),
    )

    result = audit_d4_a2_paired_shadow(request, artifact_root=tmp_path)
    seed_result = result["seed_results"][0]

    assert result["model_source_verified"] is True
    assert result["runtime_distribution_compatible"] is False
    assert seed_result["availability"] == "unavailable"
    assert seed_result["treatment_observed"] is False
    assert "a2_runtime_feature_ood" in seed_result["reason_codes"]
    assert "a2_model_action_missing" in seed_result["reason_codes"]
    assert (
        "a2_rule_fallback_only_not_treatment"
        in seed_result["reason_codes"]
    )
    assert result["aggregate"]["treatment_pair_count"] == 0
    assert result["aggregate"]["paired_non_degradation_available"] is False
    assert all(value is False for value in result["permissions"].values())


def test_in_distribution_noop_fallback_is_not_distribution_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate_fixture(tmp_path)
    model_reference = _model_source_reference(tmp_path, candidate)
    adapter = RegionResourceCurrentLineageShadowAdapter(candidate)
    seed = 2000
    snapshot = _in_distribution_snapshot(seed)
    registration = RegionResourceCurrentLineageShadowSeedRegistration(
        registry_id="main-preregistered-unseen-shadow",
        registry_version=1,
        episode_id="a2-noop-candidate-seed-2000",
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=seed,
        candidate_binding_sha256=adapter.candidate_binding.binding_sha256,
        excluded_calibration_seeds=(9999,),
        calibration_catalog_complete=True,
    )
    original = adapter._policy.recommend_raw

    def _recommend_noop(source: RegionResourceSnapshot):
        recommendation = original(source)
        nodes = source.region_by_id
        actions = tuple(
            replace(
                action,
                resource_quota_delta=0,
                reserve_ratio=(
                    nodes[action.region_id].reserve_resources
                    / nodes[action.region_id].available_resources
                ),
                hold=False,
                request_replan=False,
                reasons=(),
            )
            for action in recommendation.actions
        )
        return replace(recommendation, actions=actions, transfers=())

    monkeypatch.setattr(adapter._policy, "recommend_raw", _recommend_noop)
    record = adapter.evaluate(registration, snapshot, frame_index=0)
    assert record.ood_diagnostic.feature_ood is False
    assert record.identifiable_nonzero is False
    assert record.rule_fallback_required is True
    runtime_reference = _write_runtime_reference(
        tmp_path,
        [record],
        name="in_distribution_noop",
    )

    variants: dict[str, object] = {}
    for variant in LEARNING_VARIANTS:
        gates = {
            gate: _unavailable(f"{variant.lower()}_{gate}_not_supplied")
            for gate in READINESS_GATES
        }
        if variant == "A2":
            gates["model_source"] = {
                "availability": True,
                "source_artifact": _reference(
                    tmp_path,
                    model_reference,
                ),
                "reason_codes": [],
            }
            gates["runtime_distribution_compatible"] = {
                "availability": True,
                "source_artifact": _reference(
                    tmp_path,
                    runtime_reference,
                ),
                "reason_codes": [],
            }
        variants[variant] = {"variant": variant, "gates": gates}
    readiness = audit_learning_run_readiness(
        build_learning_run_readiness_input(
            audit_id="a2-in-distribution-noop",
            variants=variants,
            storage=_storage(),
        ),
        artifact_root=tmp_path,
    )
    row = readiness["variants"]["A2"]
    distribution = row["gates"]["runtime_distribution_compatible"]
    assert row["model_source_verified"] is True
    assert row["runtime_distribution_compatible"] is True
    assert distribution["passed"] is True
    assert distribution["reason_codes"] == []
    assert distribution["facts"]["feature_ood_snapshot_count"] == 0
    assert distribution["facts"]["model_action_count"] == 0
    assert distribution["facts"]["missing_model_action_count"] == 1
    assert distribution["facts"]["rule_fallback_count"] == 1
    assert row["formal_evidence_readiness"]["availability"] is False
    assert row["formal_evidence_readiness"]["ready"] is None

    registry_body = {
        "schema_version": D4_A2_FROZEN_SEED_REGISTRY_SCHEMA_VERSION,
        "registry_id": "main-preregistered-unseen-shadow",
        "registry_version": 1,
        "frozen_at_utc": "2026-07-28T19:00:00Z",
        "frozen_before_execution": True,
        "candidate_manifest_file_sha256": (
            D4_A2_CANDIDATE_MANIFEST_SHA256
        ),
        "model_state_sha256": D4_A2_MODEL_STATE_SHA256,
        "evaluation_seeds": [seed],
        "registrations": [
            {
                "seed": seed,
                "episode_id": registration.episode_id,
                "registered_at_utc": "2026-07-28T19:10:00Z",
                "candidate_binding_sha256": (
                    registration.candidate_binding_sha256
                ),
                "registration": registration.to_dict(),
            }
        ],
    }
    registry = {
        **registry_body,
        "content_sha256": _canonical_sha(registry_body),
    }
    metric = {
        "numerator": 1.0,
        "denominator": 1,
        "value": 1.0,
        "direction": "lower",
        "tolerance": 0.0,
    }
    pair = {
        "seed": seed,
        "started_at_utc": "2026-07-28T19:20:00Z",
        "candidate_episode_id": registration.episode_id,
        "r0_episode_id": "a2-noop-r0-seed-2000",
        "candidate_event_log_sha256": "4" * 64,
        "r0_event_log_sha256": "5" * 64,
        "candidate_external_config_sha256": "6" * 64,
        "r0_external_config_sha256": "6" * 64,
        "model_state_sha256": D4_A2_MODEL_STATE_SHA256,
        "adoption_records": [],
        "online_truth_use_count": 0,
        "audited_finite_value_count": 12,
        "nonfinite_value_count": 0,
        "candidate_metrics": {"plan_churn": metric},
        "r0_metrics": {"plan_churn": metric},
    }
    audit = audit_d4_a2_paired_shadow(
        build_d4_a2_paired_shadow_audit_input(
            audit_id="a2-in-distribution-noop-pair",
            model_source_reference=_reference(
                tmp_path,
                model_reference,
            ),
            runtime_distribution_reference=_reference(
                tmp_path,
                runtime_reference,
            ),
            seed_registry=registry,
            required_metrics=("plan_churn",),
            pairs=(pair,),
        ),
        artifact_root=tmp_path,
    )
    seed_result = audit["seed_results"][0]
    assert audit["runtime_distribution_compatible"] is True
    assert seed_result["rollout_precondition_satisfied"] is False
    assert seed_result["treatment_observed"] is False
    assert seed_result["availability"] == "unavailable"
    assert "a2_runtime_feature_ood" not in seed_result["reason_codes"]
    assert "a2_model_action_missing" in seed_result["reason_codes"]
    assert (
        "a2_rule_fallback_only_not_treatment"
        in seed_result["reason_codes"]
    )
    assert audit["aggregate"]["treatment_pair_count"] == 0
    assert audit["aggregate"]["paired_non_degradation_available"] is False
    assert all(value is False for value in audit["permissions"].values())
