from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d4_distributed_fallback.coalition_safety import (
    CoalitionCommitState,
    CoalitionMemberAck,
)
from d4_distributed_fallback.region_resource import (
    RegionResourceNode,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.region_resource_a2_evidence import (
    D6_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA,
    D6_A2_EXTERNAL_AUDIT_SCHEMA,
    D6_A2_FORMAL_PROFILE,
    D6_FORMAL_SCOPE_AUDIT_SCHEMA,
    D6_IMPLEMENTATION_EVIDENCE_SCHEMA,
    REGION_RESOURCE_A2_EVIDENCE_BUNDLE_SCHEMA,
    REGION_RESOURCE_A2_PAIRED_RESULT_SCHEMA,
    REGION_RESOURCE_A2_PHYSICAL_WINDOW_SCHEMA,
    REGION_RESOURCE_A2_R0_REFERENCE_SCHEMA,
    REGION_RESOURCE_A2_RUNTIME_CHAIN_SCHEMA,
    RegionResourceA2EvidenceError,
    RegionResourceA2EvidenceInputs,
    assemble_region_resource_a2_evidence_bundle,
    load_region_resource_a2_evidence_bundle,
)
from d4_distributed_fallback.region_resource_a2_evidence_cli import (
    main as a2_evidence_cli_main,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    stage_region_learning_episode,
)
from d4_distributed_fallback.region_resource_learning import (
    SharedRegionGraphActorCritic,
    load_region_behavior_cloning_samples,
    save_region_resource_model_bundle,
)
from d4_distributed_fallback.region_resource_runtime_ack import (
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckEvidence,
    RegionResourceRuntimeAdoptionKind,
)
from d4_distributed_fallback.regional_failover import (
    RegionalAuthorityLayer,
)


_SOURCE_COMMIT = "a" * 40
_IMPLEMENTATION_FILES = (
    "canonical_seed_split.py",
    "coalition_safety.py",
    "communication_causal_evidence.py",
    "region_resource.py",
    "region_resource_dataset.py",
    "region_resource_isolated_rollout.py",
    "region_resource_learning.py",
    "region_resource_paired_intervention.py",
    "region_resource_reward_evidence.py",
    "region_resource_runtime_ack.py",
    "region_resource_training.py",
    "regional_failover.py",
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_json(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _with_content(payload: dict[str, object]) -> dict[str, object]:
    result = deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha_json(result)
    return result


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload))


def _episode_source(seed: int) -> RegionLearningEpisodeSource:
    return RegionLearningEpisodeSource(
        scenario_id="a2-fixture",
        scenario_version="v1",
        scenario_scale="M5N5",
        seed=seed,
        episode_id=f"a2-fixture-seed-{seed}",
        git_commit=_SOURCE_COMMIT,
        git_dirty=False,
        config_sha256=sha256(f"config:{seed}".encode()).hexdigest(),
    )


def _episode_frame(
    source: RegionLearningEpisodeSource,
) -> RegionLearningFrame:
    snapshot = RegionResourceSnapshot(
        snapshot_id=f"snapshot-{source.seed}",
        scenario_id=source.scenario_id,
        scenario_version=source.scenario_version,
        seed=source.seed,
        timestamp_s=1.0,
        regions=(
            RegionResourceNode(
                region_id="region-0",
                target_demand=3.0,
                high_threat_backlog=1.0,
                d1_uncertainty=0.2,
                d2_uncertainty=0.1,
                d5_visibility=0.8,
                d5_consistency=0.9,
                available_resources=5,
                reserve_resources=1,
                secondary_coverage=0.9,
                secondary_readiness=0.9,
                communication_capacity=20.0,
                communication_latency_s=0.02,
                packet_loss_rate=0.01,
                current_owner_id="CENTER",
                current_owner_layer=RegionalAuthorityLayer.CENTER,
                plan_id="plan-source",
                plan_version=10,
                epoch=4,
                lease_expires_at_s=30.0,
                coalition_ack_complete=True,
            ),
        ),
        edges=(),
    )
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)
    return RegionLearningFrame(
        frame_index=0,
        timestamp_s=1.0,
        snapshot=snapshot,
        target=RegionLearningTarget.available(
            RegionLearningTargetKind.RULE, recommendation
        ),
        reward=RegionLearningReward.available(0.0),
        recommendation=recommendation,
    )


def _build_source_bundle(root: Path) -> Path:
    stage = root / "dataset-stage"
    for seed in range(8):
        source = _episode_source(seed)
        stage_region_learning_episode(
            stage, source, (_episode_frame(source),)
        )
    dataset_dir = root / "dataset"
    finalize_region_learning_dataset(
        stage,
        dataset_dir,
        created_at_utc="2026-07-26T00:00:00Z",
        split_seed=17,
        minimum_unseen_seeds=2,
    )
    dataset = load_region_learning_dataset(dataset_dir)
    samples = load_region_behavior_cloning_samples(dataset)
    model = SharedRegionGraphActorCritic(
        hidden_dim=8, message_passing_steps=1
    )
    bundle = root / "development-bundle"
    save_region_resource_model_bundle(
        model,
        bundle,
        model_version="d4-a2-synthetic-development-v1",
        training_graphs=tuple(sample.graph for sample in samples),
        training_dataset_manifest=dataset.manifest,
        created_at_utc="2026-07-26T00:00:00Z",
    )
    return bundle


def _implementation_evidence(
    source_bundle: Path,
) -> dict[str, object]:
    package_dir = Path(
        __import__(
            "d4_distributed_fallback.region_resource_a2_evidence",
            fromlist=["dummy"],
        ).__file__
    ).resolve().parent
    source_files = {
        name: _sha_file(package_dir / name)
        for name in _IMPLEMENTATION_FILES
    }
    source_manifest = json.loads(
        (source_bundle / "manifest.json").read_text(encoding="utf-8")
    )
    return _with_content(
        {
            "schema_version": D6_IMPLEMENTATION_EVIDENCE_SCHEMA,
            "role": "D4_A2",
            "source_git_commit": _SOURCE_COMMIT,
            "source_files": source_files,
            "implementation_sha256": _sha_json(source_files),
            "dataset_manifest_sha256": _sha_file(
                source_bundle / "training_dataset_manifest.json"
            ),
            "dataset_content_sha256": source_manifest[
                "training_dataset_sha256"
            ],
            "dataset_split_sha256": source_manifest[
                "training_split_sha256"
            ],
            "bundle_manifest_sha256": _sha_file(
                source_bundle / "manifest.json"
            ),
            "bundle_weights_sha256": _sha_file(
                source_bundle / "state_dict.pt"
            ),
        }
    )


def _candidate_fingerprint(
    implementation: dict[str, object],
) -> str:
    return "sha256:" + _sha_json(
        {
            "role": "D4_A2",
            "variant": "A2",
            "dataset_manifest_sha256": implementation[
                "dataset_manifest_sha256"
            ],
            "dataset_content_sha256": implementation[
                "dataset_content_sha256"
            ],
            "dataset_split_sha256": implementation[
                "dataset_split_sha256"
            ],
            "bundle_manifest_sha256": implementation[
                "bundle_manifest_sha256"
            ],
            "bundle_weights_sha256": implementation[
                "bundle_weights_sha256"
            ],
            "implementation_sha256": implementation[
                "implementation_sha256"
            ],
        }
    )


def _formal_scope(
    bundle_manifest_sha256: str,
) -> dict[str, object]:
    cells: list[dict[str, object]] = []
    r0_cells: list[dict[str, object]] = []
    pairs: list[dict[str, object]] = []
    for seed in range(1000, 1020):
        key = f"nominal|5|{seed}"
        learned_id = f"A2-{seed}"
        r0_id = f"R0-{seed}"
        cells.append(
            {
                "variant": "A2",
                "scenario": "nominal",
                "scale": 5,
                "seed": seed,
                "comparison_key": key,
                "cell_id": learned_id,
                "evidence_status": "accepted",
                "assist_adoption_status": "actual_assist_adopted",
                "online_truth_status": "zero_verified",
                "physical_result_status": "available",
                "learning_evidence": {
                    "status": "preflight_and_episode_consistent",
                    "required_components": ["d4"],
                },
                "failure_reasons": [],
            }
        )
        r0_cells.append(
            {
                "variant": "R0",
                "scenario": "nominal",
                "scale": 5,
                "seed": seed,
                "comparison_key": key,
                "cell_id": r0_id,
                "evidence_status": "accepted",
                "failure_reasons": [],
            }
        )
        pairs.append(
            {
                "comparison_key": key,
                "variant": "A2",
                "learned_cell_id": learned_id,
                "r0_cell_id": r0_id,
                "availability": "available",
                "unavailable_reason": None,
                "non_degraded": True,
                "failure_reasons": [],
                "metric_comparisons": {
                    "intercepted_target_count": {
                        "availability": "available",
                        "non_degraded": True,
                        "required": True,
                    },
                    "offline_proximity_unique_target_count": {
                        "availability": "available",
                        "non_degraded": True,
                        "required": True,
                    },
                },
            }
        )
    return {
        "schema_version": D6_FORMAL_SCOPE_AUDIT_SCHEMA,
        "verdict": "pass",
        "fail_closed": False,
        "formal_evidence_eligible": True,
        "evidence_admission_allowed": True,
        "model_promotion": {
            "availability": "unavailable",
            "allowed": False,
        },
        "default_control_path_modified": False,
        "learned_scope": {
            "source_git_commit": _SOURCE_COMMIT,
            "scope_variants": ["A2"],
            "expected_cell_count": 20,
            "accepted_cell_count": 20,
            "formal_evidence_eligible": True,
            "bundle_binding_status": "available_and_valid",
            "scope_completeness_status": "complete",
            "bundle_binding": {
                "components": {
                    "d4": {
                        "available": True,
                        "manifest_sha256_match": True,
                        "tree_sha256_match": True,
                        "file_count_match": True,
                        "total_size_bytes_match": True,
                        "actual": {
                            "manifest_sha256": bundle_manifest_sha256
                        },
                    }
                }
            },
            "cells": cells,
            "blockers": [],
        },
        "r0_scopes": [
            {
                "label": "same-key-r0",
                "cells": r0_cells,
                "blockers": [],
            }
        ],
        "r0_pairing": {
            "availability": "available",
            "expected_pair_count": 20,
            "available_pair_count": 20,
            "non_degraded_pair_count": 20,
            "all_required_pairs_available": True,
            "all_required_pairs_non_degraded": True,
            "pairs": pairs,
            "blockers": [],
        },
        "blockers": [],
    }


def _runtime_record(
    seed: int,
    *,
    candidate_fingerprint: str,
    model_state_sha256: str,
) -> dict[str, object]:
    key = f"nominal|5|{seed}"
    advisory_id = f"advisory-{seed}"
    advisory_sha = sha256(advisory_id.encode()).hexdigest()
    source_plan_id = f"source-plan-{seed}"
    successor_plan_id = f"successor-plan-{seed}"
    successor_plan_sha = sha256(successor_plan_id.encode()).hexdigest()
    ack = RegionResourceRuntimeAckEvidence(
        code=RegionResourceRuntimeAckCode.APPLIED.value,
        reason="new execution plan applied",
        runtime_advisory_applied_ack_available=True,
        adoption_kind=(
            RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
        ),
        advisory_id=advisory_id,
        advisory_version=1,
        source_plan_id=source_plan_id,
        source_plan_version=10,
        applied_plan_id=successor_plan_id,
        applied_plan_version=11,
        consumed_at_s=2.0,
        acknowledged_at_s=3.0,
        owner_layer="center",
        owner_node_id="CENTER",
        authority_epoch=4,
        lease_expires_at_s=30.0,
        source_plan_bus_sequence=100,
        advisory_source_plan_bus_sequence=100,
        source_guidance_bus_sequence=101,
        ack_bus_sequence=102,
        advisory_payload_sha256=advisory_sha,
        source_plan_payload_sha256=sha256(
            source_plan_id.encode()
        ).hexdigest(),
        source_guidance_payload_sha256=sha256(
            f"guidance-{seed}".encode()
        ).hexdigest(),
    )
    ack_payload = ack.to_dict()
    ack_sha = _sha_json(ack_payload)
    window_id = f"physical-window-{seed}"
    state = CoalitionCommitState(
        global_track_id=f"GT-{seed}",
        coalition_id=f"coalition-{seed}",
        coalition_version=1,
        plan_id=successor_plan_id,
        plan_version=11,
        epoch=4,
        coordinator_id="CENTER",
        coordinator_role="center",
        required_member_ids=(f"INT-{seed}",),
        acked_member_ids=(f"INT-{seed}",),
        state="executing",
        lease_expires_at=30.0,
        proposed_at=1.0,
        updated_at=4.0,
        committed_at=3.5,
        executing_at=4.0,
        reason="coalition_execution_started",
    )
    member_ack = CoalitionMemberAck(
        resource_id=f"INT-{seed}",
        global_track_id=f"GT-{seed}",
        coalition_id=f"coalition-{seed}",
        coalition_version=1,
        plan_id=successor_plan_id,
        plan_version=11,
        epoch=4,
        can_execute=True,
        evidence_timestamp=3.5,
        valid_until=30.0,
    )
    state_payload = state.to_dict()
    ack_payloads = [member_ack.to_dict()]
    return {
        "seed": seed,
        "scenario_id": "nominal",
        "scale": 5,
        "comparison_key": key,
        "candidate_fingerprint": candidate_fingerprint,
        "advisory": {
            "schema": "d4-region-resource-advisory-v1",
            "advisory_id": advisory_id,
            "advisory_version": 1,
            "payload_sha256": advisory_sha,
            "model_state_sha256": model_state_sha256,
            "candidate_confidence": 0.8,
            "minimum_confidence": 0.6,
            "requested_mode": "assist",
            "effective_mode": "assist",
            "projected": True,
            "actual_safe_adoption": True,
            "rule_fallback_used": False,
            "nominal_rule_arm_used": False,
            "active_risk_rule_arm_used": False,
            "source_plan_id": source_plan_id,
            "source_plan_version": 10,
        },
        "authority_bindings": [
            {
                "region_id": "region-0",
                "owner_layer": "center",
                "owner_node_id": "CENTER",
                "authority_epoch": 4,
                "fault_generation": 7,
                "lease_expires_at_s": 30.0,
                "evidence_timestamp_s": 1.0,
            }
        ],
        "d3_successor_plan": {
            "schema_version": "assignment_plan_v2",
            "plan_id": successor_plan_id,
            "plan_version": 11,
            "previous_plan_id": source_plan_id,
            "previous_plan_version": 10,
            "created_at_s": 2.0,
            "valid_until_s": 20.0,
            "payload_sha256": successor_plan_sha,
            "accepted": True,
            "regional_hint_applied": True,
            "stale_version_rejected": True,
            "source_advisory_id": advisory_id,
            "source_advisory_version": 1,
            "source_advisory_payload_sha256": advisory_sha,
        },
        "runtime_ack": {
            "payload": ack_payload,
            "payload_sha256": ack_sha,
        },
        "physical_window": {
            "schema": REGION_RESOURCE_A2_PHYSICAL_WINDOW_SCHEMA,
            "window_id": window_id,
            "available": True,
            "window_start_s": 4.0,
            "window_end_s": 10.0,
            "advisory_id": advisory_id,
            "advisory_version": 1,
            "applied_plan_id": successor_plan_id,
            "applied_plan_version": 11,
            "runtime_ack_sha256": ack_sha,
            "source_snapshot_payload_sha256": sha256(
                f"source-{seed}".encode()
            ).hexdigest(),
            "outcome_snapshot_payload_sha256": sha256(
                f"outcome-{seed}".encode()
            ).hexdigest(),
            "physical_execution_observed": True,
            "hard_constraint_violation_count": 0,
        },
        "same_key_r0": {
            "schema": REGION_RESOURCE_A2_R0_REFERENCE_SCHEMA,
            "cell_id": f"R0-{seed}",
            "comparison_key": key,
            "unique_reference": True,
            "physical_window_available": True,
            "physical_window_payload_sha256": sha256(
                f"r0-window-{seed}".encode()
            ).hexdigest(),
            "rule_policy_name": "d4-region-resource-rule",
            "rule_policy_version": "v1",
        },
        "paired_non_degradation": {
            "schema": REGION_RESOURCE_A2_PAIRED_RESULT_SCHEMA,
            "available": True,
            "candidate_window_id": window_id,
            "r0_cell_id": f"R0-{seed}",
            "non_degraded": True,
            "hard_constraint_non_degraded": True,
            "required_metric_results": {
                "intercepted_target_count": True,
                "offline_proximity_unique_target_count": True,
            },
        },
        "coalition_integrity": {
            "commit_state": state_payload,
            "commit_state_sha256": _sha_json(state_payload),
            "member_acks": ack_payloads,
            "member_acks_sha256": _sha_json(ack_payloads),
            "fault_generation": 7,
            "complete": True,
        },
        "safety": {
            "hard_constraint_violation_count": 0,
            "online_truth_use_count": 0,
            "global_track_id_rewrite_count": 0,
            "rule_fallback_available": True,
            "coalition_integrity_passed": True,
        },
    }


def _runtime_chain(
    *,
    implementation: dict[str, object],
    candidate_fingerprint: str,
    formal_scope_sha256: str,
    formal_checksums_sha256: str,
) -> dict[str, object]:
    records = [
        _runtime_record(
            seed,
            candidate_fingerprint=candidate_fingerprint,
            model_state_sha256=str(
                implementation["bundle_weights_sha256"]
            ),
        )
        for seed in range(1000, 1020)
    ]
    return _with_content(
        {
            "schema_version": REGION_RESOURCE_A2_RUNTIME_CHAIN_SCHEMA,
            "candidate_fingerprint": candidate_fingerprint,
            "bundle_manifest_sha256": implementation[
                "bundle_manifest_sha256"
            ],
            "bundle_weights_sha256": implementation[
                "bundle_weights_sha256"
            ],
            "implementation_sha256": implementation[
                "implementation_sha256"
            ],
            "source_git_commit": _SOURCE_COMMIT,
            "formal_scope_audit_sha256": formal_scope_sha256,
            "formal_scope_checksums_sha256": formal_checksums_sha256,
            "formal_profile_version": D6_A2_FORMAL_PROFILE,
            "minimum_confidence": 0.6,
            "seed_values": list(range(1000, 1020)),
            "records": records,
            "summary": {
                "episode_count": 20,
                "actual_safe_adoption_count": 20,
                "strict_successor_plan_count": 20,
                "runtime_ack_count": 20,
                "physical_window_count": 20,
                "unique_r0_count": 20,
                "paired_non_degraded_count": 20,
                "hard_constraint_violation_count": 0,
                "coalition_integrity_pass_count": 20,
            },
            "permissions": {
                "a2_assist_eligible_requested": True,
                "default_model": False,
                "ppo_enabled": False,
                "model_promotion": False,
                "failover_authority": False,
                "assignment_authority": False,
                "control_authority": False,
                "rule_fallback_required": True,
            },
        }
    )


def _d6_audit(
    *,
    implementation: dict[str, object],
    candidate_fingerprint: str,
    formal_scope_sha256: str,
    formal_checksums_sha256: str,
) -> dict[str, object]:
    values: dict[str, object] = {
        "candidate_fingerprint": candidate_fingerprint,
        "dataset_manifest_sha256": implementation[
            "dataset_manifest_sha256"
        ],
        "dataset_content_sha256": implementation[
            "dataset_content_sha256"
        ],
        "dataset_split_sha256": implementation[
            "dataset_split_sha256"
        ],
        "bundle_manifest_sha256": implementation[
            "bundle_manifest_sha256"
        ],
        "bundle_weights_sha256": implementation[
            "bundle_weights_sha256"
        ],
        "implementation_sha256": implementation["implementation_sha256"],
        "source_git_commit": _SOURCE_COMMIT,
        "formal_scope_audit_sha256": formal_scope_sha256,
        "formal_scope_checksums_sha256": formal_checksums_sha256,
        "formal_scope_checksum_verified": True,
        "unseen_seed_count": 20,
        "formal_episode_count": 20,
        "actual_adoption_count": 20,
        "physical_window_count": 20,
        "unique_r0_pair_count": 20,
        "paired_non_degraded_count": 20,
        "safety_hard_constraint_passed": True,
        "formal_scope_audit_passed": True,
    }
    consumer: dict[str, object] = {
        "schema_version": D6_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA,
        "role": "D4_A2",
        "variant": "A2",
        "formal_profile_version": D6_A2_FORMAL_PROFILE,
        "adoption_evidence_kind": "runtime_ack",
        "adoption_source_metric": "d4_advice_control_adoption_count",
        **values,
        "field_availability": {
            name: {
                "availability": "available",
                "unavailable_reason": None,
                "value": value,
            }
            for name, value in {
                "adoption_evidence_kind": "runtime_ack",
                "adoption_source_metric": (
                    "d4_advice_control_adoption_count"
                ),
                **values,
            }.items()
        },
        "d6_external_audit_passed": True,
        "failure_reasons": [],
    }
    return _with_content(
        {
            "schema_version": D6_A2_EXTERNAL_AUDIT_SCHEMA,
            "audit_id": "d4-a2-synthetic-positive",
            "evaluated_at_utc": "2026-07-26T00:00:00Z",
            "role": "D4_A2",
            "variant": "A2",
            "formal_profile_version": D6_A2_FORMAL_PROFILE,
            "status": "pass",
            "audit_passed": True,
            "fail_closed": False,
            "evidence_audit_only": True,
            "frozen_thresholds": {},
            "artifact_evidence": [],
            "candidate": {
                **{
                    name: values[name]
                    for name in (
                        "dataset_manifest_sha256",
                        "dataset_content_sha256",
                        "dataset_split_sha256",
                        "bundle_manifest_sha256",
                        "bundle_weights_sha256",
                    )
                },
                "candidate_lifecycle": "development",
                "candidate_maximum_mode": "shadow",
            },
            "implementation": {
                "available": True,
                "lineage_verified": True,
                "current_implementation_sha256": implementation[
                    "implementation_sha256"
                ],
                "evidence_implementation_sha256": implementation[
                    "implementation_sha256"
                ],
                "source_git_commit": _SOURCE_COMMIT,
            },
            "formal_scope": {
                "available": True,
                "audit_passed": True,
                "checksums_verified": True,
                "audit_file_sha256": formal_scope_sha256,
                "checksums_file_sha256": formal_checksums_sha256,
                "unseen_seed_count": 20,
                "formal_episode_count": 20,
                "actual_adoption_count": 20,
                "physical_window_count": 20,
                "unique_r0_pair_count": 20,
                "paired_non_degraded_count": 20,
                "safety_hard_constraint_passed": True,
                "source_git_commit": _SOURCE_COMMIT,
            },
            "consumer_contract": consumer,
            "blocker_codes": [],
            "blocker_details": {},
            "authority": {
                "model_promotion_granted": False,
                "assist_granted": False,
                "assignment_authority_granted": False,
                "failover_authority_granted": False,
                "control_authority_granted": False,
                "default_path_change_granted": False,
                "reason": "evidence audit only",
            },
            "availability_policy": {},
        }
    )


def _fixture(tmp_path: Path) -> tuple[
    RegionResourceA2EvidenceInputs, Path, dict[str, Path]
]:
    source_bundle = _build_source_bundle(tmp_path / "source")
    evidence_dir = tmp_path / "input-evidence"
    implementation = _implementation_evidence(source_bundle)
    implementation_path = evidence_dir / "implementation_evidence.json"
    _write_json(implementation_path, implementation)
    fingerprint = _candidate_fingerprint(implementation)

    formal = _formal_scope(
        str(implementation["bundle_manifest_sha256"])
    )
    formal_path = evidence_dir / "learning_scope_formal_audit.json"
    _write_json(formal_path, formal)
    formal_sha = _sha_file(formal_path)
    formal_checksums = evidence_dir / "SHA256SUMS"
    formal_checksums.write_text(
        f"{formal_sha}  learning_scope_formal_audit.json\n",
        encoding="ascii",
    )
    formal_checksums_sha = _sha_file(formal_checksums)

    runtime = _runtime_chain(
        implementation=implementation,
        candidate_fingerprint=fingerprint,
        formal_scope_sha256=formal_sha,
        formal_checksums_sha256=formal_checksums_sha,
    )
    runtime_path = evidence_dir / "runtime_chain_evidence.json"
    _write_json(runtime_path, runtime)
    audit = _d6_audit(
        implementation=implementation,
        candidate_fingerprint=fingerprint,
        formal_scope_sha256=formal_sha,
        formal_checksums_sha256=formal_checksums_sha,
    )
    audit_path = evidence_dir / "d6_external_audit.json"
    _write_json(audit_path, audit)

    inputs = RegionResourceA2EvidenceInputs(
        development_bundle_dir=source_bundle,
        expected_development_manifest_sha256=_sha_file(
            source_bundle / "manifest.json"
        ),
        expected_development_weights_sha256=_sha_file(
            source_bundle / "state_dict.pt"
        ),
        expected_development_training_manifest_sha256=_sha_file(
            source_bundle / "training_dataset_manifest.json"
        ),
        implementation_evidence_path=implementation_path,
        expected_implementation_evidence_sha256=_sha_file(
            implementation_path
        ),
        d6_external_audit_path=audit_path,
        expected_d6_external_audit_sha256=_sha_file(audit_path),
        formal_scope_audit_path=formal_path,
        expected_formal_scope_audit_sha256=formal_sha,
        formal_scope_checksums_path=formal_checksums,
        expected_formal_scope_checksums_sha256=formal_checksums_sha,
        runtime_chain_evidence_path=runtime_path,
        expected_runtime_chain_evidence_sha256=_sha_file(runtime_path),
    )
    return inputs, tmp_path / "assembled", {
        "source_manifest": source_bundle / "manifest.json",
        "source_weights": source_bundle / "state_dict.pt",
        "implementation": implementation_path,
        "audit": audit_path,
        "formal": formal_path,
        "formal_checksums": formal_checksums,
        "runtime": runtime_path,
    }


def _rewrite_content_artifact(
    path: Path, payload: dict[str, object]
) -> str:
    updated = _with_content(payload)
    _write_json(path, updated)
    return _sha_file(path)


def test_complete_synthetic_chain_assembles_and_strict_loads(
    tmp_path: Path,
) -> None:
    inputs, output, paths = _fixture(tmp_path)
    source_hashes = {
        name: _sha_file(path)
        for name, path in paths.items()
        if name in {"source_manifest", "source_weights"}
    }

    result = assemble_region_resource_a2_evidence_bundle(output, inputs)
    loaded = load_region_resource_a2_evidence_bundle(output)

    assert result.a2_assist_eligible is True
    assert loaded.a2_assist_eligible is True
    assert loaded.source_manifest.lifecycle_stage == "development"
    assert loaded.source_manifest.maximum_advisor_mode == "shadow"
    assert loaded.default_model is False
    assert loaded.ppo_enabled is False
    assert loaded.failover_authority is False
    assert loaded.assignment_authority is False
    assert loaded.control_authority is False
    assert loaded.rule_fallback_required is True
    assert tuple(loaded.unseen_seed_values) == tuple(range(1000, 1020))
    assert {
        name: _sha_file(path)
        for name, path in paths.items()
        if name in {"source_manifest", "source_weights"}
    } == source_hashes
    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert (
        manifest["schema_version"]
        == REGION_RESOURCE_A2_EVIDENCE_BUNDLE_SCHEMA
    )


def test_current_actual_candidate_and_d6_fail_closed_audit_are_rejected(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    source = (
        repository_root
        / "research_modules/d4_distributed_fallback/outputs/"
        "region_resource_bc_900_20260720/bundle"
    )
    audit = (
        repository_root
        / "research_modules/d6_evaluation_metrics/outputs/"
        "d4_a2_external_audit_actual_20260726_final/"
        "d4_a2_external_audit.json"
    )
    assert source.is_dir()
    assert audit.is_file()
    original = {
        name: _sha_file(source / name)
        for name in (
            "manifest.json",
            "state_dict.pt",
            "training_dataset_manifest.json",
        )
    }
    missing = tmp_path / "not-generated.json"
    inputs = RegionResourceA2EvidenceInputs(
        development_bundle_dir=source,
        expected_development_manifest_sha256=original["manifest.json"],
        expected_development_weights_sha256=original["state_dict.pt"],
        expected_development_training_manifest_sha256=original[
            "training_dataset_manifest.json"
        ],
        implementation_evidence_path=missing,
        expected_implementation_evidence_sha256="0" * 64,
        d6_external_audit_path=audit,
        expected_d6_external_audit_sha256=_sha_file(audit),
        formal_scope_audit_path=missing,
        expected_formal_scope_audit_sha256="0" * 64,
        formal_scope_checksums_path=missing,
        expected_formal_scope_checksums_sha256="0" * 64,
        runtime_chain_evidence_path=missing,
        expected_runtime_chain_evidence_sha256="0" * 64,
    )
    output = tmp_path / "must-not-exist"

    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="d6_external_audit_fail_closed",
    ):
        assemble_region_resource_a2_evidence_bundle(output, inputs)

    assert not output.exists()
    assert {
        name: _sha_file(source / name) for name in original
    } == original


def test_input_content_hash_tampering_fails_closed(tmp_path: Path) -> None:
    inputs, output, paths = _fixture(tmp_path)
    payload = json.loads(paths["runtime"].read_text(encoding="utf-8"))
    payload["content_sha256"] = "0" * 64
    _write_json(paths["runtime"], payload)
    inputs = replace(
        inputs,
        expected_runtime_chain_evidence_sha256=_sha_file(paths["runtime"]),
    )

    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="input_content_sha256_mismatch.runtime_chain_evidence",
    ):
        assemble_region_resource_a2_evidence_bundle(output, inputs)


def test_caller_frozen_file_hash_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    inputs, output, _ = _fixture(tmp_path)
    inputs = replace(
        inputs, expected_runtime_chain_evidence_sha256="f" * 64
    )

    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="input_sha256_mismatch.runtime_chain_evidence",
    ):
        assemble_region_resource_a2_evidence_bundle(output, inputs)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda record: record["advisory"].__setitem__(
                "candidate_confidence", 0.59
            ),
            "candidate_confidence_below_0_6",
        ),
        (
            lambda record: record["advisory"].__setitem__(
                "nominal_rule_arm_used", True
            ),
            "advisory_safe_adoption_invalid.nominal_rule_arm_used",
        ),
        (
            lambda record: record["advisory"].__setitem__(
                "active_risk_rule_arm_used", True
            ),
            "advisory_safe_adoption_invalid.active_risk_rule_arm_used",
        ),
        (
            lambda record: record["d3_successor_plan"].__setitem__(
                "plan_version", 10
            ),
            "d3_strict_successor_plan_invalid",
        ),
        (
            lambda record: record["authority_bindings"][0].__setitem__(
                "lease_expires_at_s", 0.5
            ),
            "authority_lease_expired",
        ),
        (
            lambda record: record["authority_bindings"][0].__setitem__(
                "authority_epoch", 3
            ),
            "runtime_ack_cross_binding_invalid",
        ),
        (
            lambda record: record["paired_non_degradation"].__setitem__(
                "non_degraded", False
            ),
            "paired_non_degradation_invalid",
        ),
        (
            lambda record: record["coalition_integrity"].__setitem__(
                "complete", False
            ),
            "coalition_integrity_incomplete_or_stale",
        ),
    ],
)
def test_runtime_chain_semantic_failures_are_rejected(
    tmp_path: Path,
    mutation: object,
    expected_code: str,
) -> None:
    inputs, output, paths = _fixture(tmp_path)
    payload = json.loads(paths["runtime"].read_text(encoding="utf-8"))
    mutation(payload["records"][0])
    digest = _rewrite_content_artifact(paths["runtime"], payload)
    inputs = replace(
        inputs, expected_runtime_chain_evidence_sha256=digest
    )

    with pytest.raises(RegionResourceA2EvidenceError, match=expected_code):
        assemble_region_resource_a2_evidence_bundle(output, inputs)


def test_permission_opening_in_d6_or_runtime_chain_is_rejected(
    tmp_path: Path,
) -> None:
    inputs, output, paths = _fixture(tmp_path)
    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))
    audit["authority"]["control_authority_granted"] = True
    digest = _rewrite_content_artifact(paths["audit"], audit)
    d6_inputs = replace(inputs, expected_d6_external_audit_sha256=digest)
    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="d6_authority_not_closed.control_authority_granted",
    ):
        assemble_region_resource_a2_evidence_bundle(output, d6_inputs)

    inputs, output, paths = _fixture(tmp_path / "runtime-permission")
    runtime = json.loads(paths["runtime"].read_text(encoding="utf-8"))
    runtime["permissions"]["assignment_authority"] = True
    digest = _rewrite_content_artifact(paths["runtime"], runtime)
    runtime_inputs = replace(
        inputs, expected_runtime_chain_evidence_sha256=digest
    )
    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="runtime_chain_permissions_not_closed",
    ):
        assemble_region_resource_a2_evidence_bundle(
            output, runtime_inputs
        )


def test_implementation_lineage_and_candidate_fingerprint_mismatch_reject(
    tmp_path: Path,
) -> None:
    inputs, output, paths = _fixture(tmp_path)
    implementation = json.loads(
        paths["implementation"].read_text(encoding="utf-8")
    )
    implementation["source_files"]["regional_failover.py"] = "f" * 64
    implementation["implementation_sha256"] = _sha_json(
        implementation["source_files"]
    )
    digest = _rewrite_content_artifact(
        paths["implementation"], implementation
    )
    changed = replace(
        inputs, expected_implementation_evidence_sha256=digest
    )
    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="implementation_lineage_stale",
    ):
        assemble_region_resource_a2_evidence_bundle(output, changed)

    inputs, output, paths = _fixture(tmp_path / "fingerprint")
    runtime = json.loads(paths["runtime"].read_text(encoding="utf-8"))
    runtime["candidate_fingerprint"] = "sha256:" + "f" * 64
    digest = _rewrite_content_artifact(paths["runtime"], runtime)
    changed = replace(
        inputs, expected_runtime_chain_evidence_sha256=digest
    )
    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="runtime_chain_cross_binding_mismatch.candidate_fingerprint",
    ):
        assemble_region_resource_a2_evidence_bundle(output, changed)


def test_strict_loader_rejects_extra_inventory_and_manifest_fields(
    tmp_path: Path,
) -> None:
    inputs, output, _ = _fixture(tmp_path)
    assemble_region_resource_a2_evidence_bundle(output, inputs)
    extra = output / "extra.json"
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="bundle_file_inventory_mismatch",
    ):
        load_region_resource_a2_evidence_bundle(output)
    extra.unlink()

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unexpected"] = True
    manifest = _with_content(manifest)
    _write_json(manifest_path, manifest)
    checksum_path = output / "SHA256SUMS"
    lines = checksum_path.read_text(encoding="ascii").splitlines()
    lines = [
        (
            f"{_sha_file(manifest_path)}  manifest.json"
            if line.endswith("  manifest.json")
            else line
        )
        for line in lines
    ]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(
        RegionResourceA2EvidenceError,
        match="fields_mismatch.assembled_manifest",
    ):
        load_region_resource_a2_evidence_bundle(output)


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    inputs, output, _ = _fixture(tmp_path)
    output.mkdir()
    marker = output / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(
        RegionResourceA2EvidenceError, match="output_exists_no_overwrite"
    ):
        assemble_region_resource_a2_evidence_bundle(output, inputs)

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_cli_assembles_and_validates_without_opening_authority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs, output, _ = _fixture(tmp_path)
    code = a2_evidence_cli_main(
        [
            "assemble",
            "--development-bundle",
            str(inputs.development_bundle_dir),
            "--development-manifest-sha256",
            inputs.expected_development_manifest_sha256,
            "--development-weights-sha256",
            inputs.expected_development_weights_sha256,
            "--development-training-manifest-sha256",
            inputs.expected_development_training_manifest_sha256,
            "--implementation-evidence",
            str(inputs.implementation_evidence_path),
            "--implementation-evidence-sha256",
            inputs.expected_implementation_evidence_sha256,
            "--d6-external-audit",
            str(inputs.d6_external_audit_path),
            "--d6-external-audit-sha256",
            inputs.expected_d6_external_audit_sha256,
            "--formal-scope-audit",
            str(inputs.formal_scope_audit_path),
            "--formal-scope-audit-sha256",
            inputs.expected_formal_scope_audit_sha256,
            "--formal-scope-checksums",
            str(inputs.formal_scope_checksums_path),
            "--formal-scope-checksums-sha256",
            inputs.expected_formal_scope_checksums_sha256,
            "--runtime-chain-evidence",
            str(inputs.runtime_chain_evidence_path),
            "--runtime-chain-evidence-sha256",
            inputs.expected_runtime_chain_evidence_sha256,
            "--output-dir",
            str(output),
        ]
    )
    assembled = json.loads(capsys.readouterr().out)

    assert code == 0
    assert assembled["a2_assist_eligible"] is True
    assert assembled["control_authority"] is False
    assert a2_evidence_cli_main(
        ["validate", "--bundle-dir", str(output)]
    ) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["a2_assist_eligible"] is True
    assert validated["default_model"] is False
    assert validated["failover_authority"] is False
