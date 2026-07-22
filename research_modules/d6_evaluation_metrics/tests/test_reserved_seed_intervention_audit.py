from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    EXPECTED_CHECKSUMS_SHA256,
    EXPECTED_CHECKSUMS_SHA256_V2,
    EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
    EXPECTED_D3_BUNDLE_STATE_SHA256,
    EXPECTED_D4_BUNDLE_MANIFEST_SHA256,
    EXPECTED_D4_BUNDLE_STATE_SHA256,
    EXPECTED_SOURCE_COMMIT,
    EXPECTED_SOURCE_COMMIT_V2,
    EXPECTED_SOURCE_MANIFEST_SHA256,
    EXPECTED_SOURCE_MANIFEST_SHA256_V2,
    RESERVED_SEED_AUDIT_PROFILE_BINDINGS,
    RESERVED_SEED_AUDIT_SCHEMA_VERSION_V2,
    ReservedSeedInterventionAuditError,
    ReservedSeedInterventionAuditInputs,
    audit_reserved_seed_interventions,
    write_reserved_seed_intervention_audit,
)
from d6_evaluation_metrics import reserved_seed_intervention_audit as audit_module
from scripts import run_reserved_seed_intervention_audit as audit_cli


def _token(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_lineage(
    source_commit: str = EXPECTED_SOURCE_COMMIT,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for seed in range(1000, 1020):
        records.append(
            {
                "schema_version": "scalable3d-reserved-seed-source-lineage-v1",
                "seed": seed,
                "source_git_commit": source_commit,
                "source_repository_dirty": False,
                "finite_state": True,
                "online_truth_use_count": 0,
                "control_and_treatment_share_source_episode": True,
                "control_and_treatment_share_sensor_random_stream": True,
                "control_and_treatment_share_communication_schedule": True,
                "control_and_treatment_share_fault_schedule": True,
                "scenario_id": "nominal_5v5",
                "scenario_version": "nominal-5v5-v1",
                "source_episode_id": f"fixture-source-{seed}",
                "communication_schedule_sha256": _token(f"comm:{seed}"),
                "d3_input_snapshot_sha256": _token(f"d3-input:{seed}"),
                "d4_region_snapshot_lineage_sha256": _token(f"d4-input:{seed}"),
                "fault_schedule_sha256": _token(f"fault:{seed}"),
                "initial_state_sha256": _token(f"initial:{seed}"),
                "scenario_config_sha256": _token(f"scenario:{seed}"),
                "source_episode_manifest_sha256": _token(f"episode:{seed}"),
                "source_summary_sha256": _token(f"summary:{seed}"),
            }
        )
    return records


def _build_d3(records: list[dict[str, object]]) -> dict[str, object]:
    paired_report = {"schema_version": "fixture-paired-report.v1"}
    paired_report_sha = audit_module._producer_json_sha256(paired_report)
    pairs: list[dict[str, object]] = []
    arms: list[dict[str, object]] = []
    receipts: list[dict[str, object]] = []
    for index, lineage in enumerate(records):
        seed = int(lineage["seed"])
        shared = {
            "seed": seed,
            "d3_bundle_frozen": True,
            "d3_bundle_sha256": EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
            "initial_world_state_sha256": lineage["initial_state_sha256"],
            "observation_input_snapshot_sha256": lineage[
                "d3_input_snapshot_sha256"
            ],
            "scenario_config_sha256": lineage["scenario_config_sha256"],
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "ppo_enabled": False,
            "rule_fallback_enabled": True,
        }
        control_spec = {
            **shared,
            "arm_id": f"d3-{seed}-control",
            "arm_kind": "control",
            "isolation_id": f"fixture-{seed}-control",
            "learning_cost_intervention_enabled": False,
            "planner_path": "rule_cost_then_hungarian",
        }
        treatment_spec = {
            **shared,
            "arm_id": f"d3-{seed}-treatment",
            "arm_kind": "treatment",
            "isolation_id": f"fixture-{seed}-treatment",
            "learning_cost_intervention_enabled": True,
            "planner_path": "bounded_residual_then_hungarian",
        }
        pair_id = f"d3-reserved-pair-{seed}"
        pairs.append(
            {
                "seed": seed,
                "pair_id": pair_id,
                "control": control_spec,
                "treatment": treatment_spec,
            }
        )
        status = (
            "unchanged"
            if index < 15
            else "held_by_hysteresis"
            if index < 18
            else "replan_ack_no_change"
        )
        for kind, spec in (
            ("control", control_spec),
            ("treatment", treatment_spec),
        ):
            fallback_reason = None if kind == "control" else "out_of_distribution"
            plan = {"plan_id": f"d3-{seed}-{kind}-plan", "version": 1}
            receipt = {
                "seed": seed,
                "arm_kind": kind,
                "pair_id": pair_id,
                "arm_spec_sha256": audit_module._producer_json_sha256(spec),
                "input_snapshot_sha256": lineage["d3_input_snapshot_sha256"],
                "paired_evaluator_report_sha256": paired_report_sha,
                "output_plan_payload_sha256": audit_module._producer_json_sha256(
                    plan
                ),
                "output_plan_id": plan["plan_id"],
                "output_plan_version": 1,
                "fallback_reason": fallback_reason,
                "learning_cost_applied": False,
                "rule_fallback_applied": kind == "treatment",
                "inference_elapsed_ms": 0.0,
                "rule_cost_matrix_sha256": _token(f"matrix:{seed}"),
                "action_mask_sha256": _token(f"mask:{seed}"),
                "isolated_simulation": True,
                "capacity_gate_enforced": True,
                "deterministic_action_mask_enforced": True,
                "hysteresis_gate_enforced": True,
                "reachability_gate_enforced": True,
                "rule_fallback_available": True,
                "safety_gate_enforced": True,
                "version_gate_enforced": True,
                "global_track_id_rewrite_count": 0,
                "nonfinite_value_count": 0,
                "online_label_key_count": 0,
                "hysteresis_decision": status,
            }
            arms.append(
                {
                    "arm_specification": spec,
                    "receipt": receipt,
                    "plan": plan,
                    "fallback_reason": fallback_reason,
                    "learning_cost_applied": False,
                    "rule_fallback_applied": kind == "treatment",
                    "inference_elapsed_ms": 0.0,
                    "effective_matrix_sha256": receipt[
                        "rule_cost_matrix_sha256"
                    ],
                }
            )
            receipts.append(receipt)

    specification = {
        "pairs": pairs,
        "reserved_seeds": list(range(1000, 1020)),
    }
    specification_sha = audit_module._producer_json_sha256(specification)
    unavailable = {
        "available": False,
        "status": "unavailable",
        "value": None,
    }
    manifest: dict[str, object] = {
        "audit": {
            "d3_computed_causal_attribution": False,
            "d3_computed_counterfactual": False,
            "d3_computed_outcome": False,
            "fail_closed": True,
            "paired_arm_count": 40,
            "reserved_seed_count": 20,
        },
        "availability": {
            "causal": dict(unavailable),
            "counterfactual": dict(unavailable),
            "outcome": dict(unavailable),
            "runtime_ack": dict(unavailable),
            "paired_input_equivalence": {
                "available": True,
                "status": "available",
                "value": True,
            },
            "treatment_safely_applied_in_isolated_simulation": {
                "available": True,
                "status": "available",
                "value": False,
                "applied_seed_count": 0,
                "fallback_seed_count": 20,
            },
        },
        "execution_receipts": receipts,
        "specification": specification,
        "specification_sha256": specification_sha,
    }
    manifest["manifest_sha256"] = audit_module._producer_json_sha256(manifest)
    return {
        "schema_version": "d3.offline-paired-intervention-execution.v1",
        "intervention_scope": "offline_simulation_intervention_arm",
        "evidence_availability": {
            "causal": False,
            "counterfactual": False,
            "outcome": False,
            "runtime_ack": False,
        },
        "admission": {
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "ppo_enabled": False,
            "rule_fallback_enabled": True,
            "runtime_publication_allowed": False,
        },
        "bundle": {
            "loaded": True,
            "manifest_sha256": EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
            "state_dict_sha256": EXPECTED_D3_BUNDLE_STATE_SHA256,
        },
        "paired_evaluator_report": paired_report,
        "paired_evaluator_report_sha256": paired_report_sha,
        "manifest": manifest,
        "specification_sha256": specification_sha,
        "arms": arms,
    }


def _build_d4(records: list[dict[str, object]]) -> dict[str, object]:
    specs: list[dict[str, object]] = []
    for lineage in records:
        seed = int(lineage["seed"])
        binding = {
            "communication_schedule_sha256": lineage[
                "communication_schedule_sha256"
            ],
            "fault_schedule_sha256": lineage["fault_schedule_sha256"],
            "initial_state_sha256": lineage["initial_state_sha256"],
            "region_snapshot_lineage_sha256": lineage[
                "d4_region_snapshot_lineage_sha256"
            ],
            "scenario_config_sha256": lineage["scenario_config_sha256"],
            "scenario_id": "nominal_5v5",
            "scenario_version": "nominal-5v5-v1",
            "seed": seed,
        }
        for kind, candidate_allowed in (
            ("control_rule", False),
            ("treatment_candidate", True),
        ):
            spec: dict[str, object] = {
                "arm": kind,
                "candidate_influence_allowed": candidate_allowed,
                "input_binding": binding,
                "isolated_offline_only": True,
                "policy_name": "fixture-policy",
            }
            spec["arm_id"] = (
                "d4-rr-paired-arm-"
                + audit_module._producer_json_sha256(spec)
            )
            specs.append(spec)
    specification: dict[str, object] = {
        "candidate_bundle": {
            "bundle_manifest_sha256": EXPECTED_D4_BUNDLE_MANIFEST_SHA256,
            "model_state_sha256": EXPECTED_D4_BUNDLE_STATE_SHA256,
        },
        "reserved_seeds": list(range(1000, 1020)),
        "assist_enabled": False,
        "authority_enabled": False,
        "ppo_enabled": False,
        "rule_fallback_enabled": True,
        "arms": specs,
    }
    specification["specification_id"] = (
        "d4-rr-paired-spec-"
        + audit_module._producer_json_sha256(specification)
    )
    specification_sha = audit_module._producer_json_sha256(specification)
    evidence: list[dict[str, object]] = []
    for index, spec in enumerate(specs):
        binding = spec["input_binding"]
        assert isinstance(binding, dict)
        seed = int(binding["seed"])
        kind = str(spec["arm"])
        treatment = kind == "treatment_candidate"
        item: dict[str, object] = {
            "seed": seed,
            "arm": kind,
            "arm_id": spec["arm_id"],
            "specification_sha256": specification_sha,
            "candidate_bundle_match": True,
            "pair_input_match": True,
            "expected_input_sha256": _token(f"d4-expected:{seed}"),
            "observed_input_sha256": _token(f"d4-expected:{seed}"),
            "snapshot_payload_sha256": binding[
                "region_snapshot_lineage_sha256"
            ],
            "assist_enabled": False,
            "online_authority": False,
            "ppo_enabled": False,
            "rule_fallback_enabled": True,
            "runtime_advisory_applied_ack_available": False,
            "post_projection_recommendation_is_applied_ack": False,
            "causal_effect_available": False,
            "counterfactual_available": False,
            "observed_outcome_available": False,
            "paired_non_degradation_available": False,
            "deterministic_rule_executed": True,
            "next_cycle_consumption_passed": True,
            "isolated_arm_safe_adopted": True,
            "advisory_payload_sha256": _token(f"advisory:{seed}:{kind}"),
            "executed_recommendation_sha256": _token(
                f"executed:{seed}:{kind}"
            ),
            "candidate_latency_ms": float((index // 2) + 1) if treatment else 0.0,
            "candidate_considered": treatment,
            "isolated_treatment_safe_adopted": False,
            "rule_fallback_used": treatment,
            "rejection_reasons": [
                "candidate_threshold_or_finite_gate_rejected"
            ]
            if treatment
            else [],
            "candidate_thresholds_passed": not treatment,
            "candidate_safety_projection_passed": not treatment,
            "candidate_recommendation_sha256": _token(
                f"candidate:{seed}"
            )
            if treatment
            else None,
        }
        evidence.append(item)
    manifest = {
        "causal_effect_available": False,
        "counterfactual_available": False,
        "d6_outcome_sidecar_attached": False,
        "formal_twenty_seed_performance_completed": False,
        "observed_outcome_available": False,
        "paired_non_degradation_available": False,
        "performance_claim_allowed": False,
        "specification": specification,
        "arm_evidence": evidence,
    }
    return {
        "schema_version": "scalable3d-reserved-seed-interventions-v1",
        "execution_scope": "offline_simulation_intervention_arm",
        "evidence_availability": {
            "causal": False,
            "counterfactual": False,
            "physical_outcome": False,
            "runtime_ack": False,
        },
        "admission": {
            "assist": False,
            "authority": False,
            "ppo": False,
            "rule_fallback": True,
            "runtime_publication_allowed": False,
        },
        "candidate_loader": {"ready": True, "load_rejection_reasons": []},
        "manifest": manifest,
    }


def _build_fixture(tmp_path: Path) -> ReservedSeedInterventionAuditInputs:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    records = _build_lineage()
    d3 = _build_d3(records)
    d4 = _build_d4(records)
    _write_json(source_dir / "d3_offline_paired_intervention.json", d3)
    _write_json(source_dir / "d4_offline_paired_intervention.json", d4)
    (source_dir / "source_lineage.jsonl").write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    (source_dir / "RESERVED_SEED_INTERVENTION_REPORT_CN.md").write_text(
        "# fixture\n",
        encoding="utf-8",
    )
    artifact_sha = {
        "d3_execution": _file_sha(
            source_dir / "d3_offline_paired_intervention.json"
        ),
        "d4_execution": _file_sha(
            source_dir / "d4_offline_paired_intervention.json"
        ),
        "report_cn": _file_sha(
            source_dir / "RESERVED_SEED_INTERVENTION_REPORT_CN.md"
        ),
        "source_lineage": _file_sha(source_dir / "source_lineage.jsonl"),
    }
    manifest = {
        "schema_version": "scalable3d-reserved-seed-interventions-v1",
        "experiment_scope": "reserved_seed_isolated_d3_d4_execution",
        "reserved_seeds": list(range(1000, 1020)),
        "source_episode_count": 20,
        "source_git_commits": [EXPECTED_SOURCE_COMMIT],
        "dirty_source_episode_count": 0,
        "source_nonfinite_count": 0,
        "online_truth_use_count": 0,
        "d3_arm_count": 40,
        "d4_arm_count": 40,
        "scenario": "nominal",
        "scale": 5,
        "resource_count": 5,
        "target_count": 5,
        "duration_s": 2.2,
        "evidence_availability": {
            "causal": False,
            "counterfactual": False,
            "execution_receipts": True,
            "physical_outcome": False,
            "runtime_ack": False,
        },
        "admission": {
            "assist": False,
            "authority": False,
            "ppo": False,
            "rule_fallback": True,
        },
        "artifacts_sha256": artifact_sha,
        "d3_bundle": {
            "loaded": True,
            "expected_manifest_sha256": EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
            "manifest_sha256": EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
            "state_dict_sha256": EXPECTED_D3_BUNDLE_STATE_SHA256,
        },
        "d4_bundle": {
            "loaded": True,
            "bundle_manifest_sha256": EXPECTED_D4_BUNDLE_MANIFEST_SHA256,
            "model_state_sha256": EXPECTED_D4_BUNDLE_STATE_SHA256,
        },
        "d3_treatment_summary": {
            "applied_count": 0,
            "fallback_reason_counts": {"out_of_distribution": 20},
            "rule_fallback_count": 20,
        },
        "d4_treatment_summary": {
            "rejection_reason_counts": {
                "candidate_threshold_or_finite_gate_rejected": 20
            },
            "rule_fallback_count": 20,
            "safe_adopted_count": 0,
        },
    }
    _write_json(source_dir / "manifest.json", manifest)
    checksum_names = (
        "d3_offline_paired_intervention.json",
        "d4_offline_paired_intervention.json",
        "manifest.json",
        "RESERVED_SEED_INTERVENTION_REPORT_CN.md",
        "source_lineage.jsonl",
    )
    (source_dir / "SHA256SUMS").write_text(
        "".join(f"{_file_sha(source_dir / name)}  {name}\n" for name in checksum_names),
        encoding="ascii",
    )
    return ReservedSeedInterventionAuditInputs(
        source_dir=source_dir,
        output_dir=tmp_path / "output",
        audited_at_utc="2026-07-22T04:00:00Z",
        expected_checksums_sha256=_file_sha(source_dir / "SHA256SUMS"),
        expected_source_manifest_sha256=_file_sha(source_dir / "manifest.json"),
    )


def _build_d3_v2(
    records: list[dict[str, object]],
) -> dict[str, object]:
    payload = _build_d3(records)
    manifest = payload["manifest"]
    assert isinstance(manifest, dict)
    specification = manifest["specification"]
    assert isinstance(specification, dict)
    pairs = specification["pairs"]
    assert isinstance(pairs, list)
    arms = payload["arms"]
    assert isinstance(arms, list)

    frames: list[dict[str, object]] = []
    per_seed_metrics: dict[str, object] = {}
    for pair in pairs:
        assert isinstance(pair, dict)
        seed = int(pair["seed"])
        pair_id = str(pair["pair_id"])
        for kind in ("control", "treatment"):
            pair_spec = pair[kind]
            assert isinstance(pair_spec, dict)
            pair_spec.update(
                {
                    "safety_shell_version": (
                        audit_module.EXPECTED_D3_SAFETY_SHELL_VERSION_V2
                    ),
                    "safety_shell_config_sha256": (
                        audit_module.EXPECTED_D3_SAFETY_SHELL_CONFIG_SHA256_V2
                    ),
                }
            )
            arm = next(
                item
                for item in arms
                if item["arm_specification"]["seed"] == seed
                and item["arm_specification"]["arm_kind"] == kind
            )
            arm_spec = arm["arm_specification"]
            assert isinstance(arm_spec, dict)
            arm_spec.update(pair_spec)
            plan = arm["plan"]
            assert isinstance(plan, dict)
            plan.update(
                {
                    "assignments": [
                        {
                            "target_id": f"T{seed}",
                            "resource_id": f"R{seed}",
                            "member_role": "primary",
                            "coalition_id": f"C{seed}",
                        }
                    ],
                    "total_cost": 12.5,
                    "unassigned_target_ids": [],
                }
            )
            receipt = arm["receipt"]
            assert isinstance(receipt, dict)
            treatment = kind == "treatment"
            receipt.update(
                {
                    "schema_version": (
                        "d3.paired-intervention-execution-receipt.v1"
                    ),
                    "paired_evaluator_schema_version": (
                        "d3_shadow_paired_evaluation_v2"
                    ),
                    "fallback_reason": None,
                    "learning_cost_applied": treatment,
                    "rule_fallback_applied": False,
                    "inference_elapsed_ms": 0.25 if treatment else 0.0,
                }
            )
            arm.update(
                {
                    "fallback_reason": None,
                    "learning_cost_applied": treatment,
                    "rule_fallback_applied": False,
                    "inference_elapsed_ms": 0.25 if treatment else 0.0,
                    "effective_matrix_sha256": (
                        _token(f"v2-effective:{seed}")
                        if treatment
                        else receipt["rule_cost_matrix_sha256"]
                    ),
                }
            )

        frame = {
            "seed": seed,
            "episode": pair_id,
            "frame_index": 0,
            "scenario_version": "nominal-5v5-v1",
            "rule_assignment_cost": 12.5,
            "shadow_assignment_cost": 12.5,
            "inference_elapsed_ms": 0.25,
            "fallback_reason": None,
            "rule_high_threat_unmet": 0,
            "shadow_high_threat_unmet": 0,
            "rule_duplicate_count": 0,
            "shadow_duplicate_count": 0,
            "rule_hard_violation_count": 0,
            "shadow_hard_violation_count": 0,
            "rule_churn": 0,
            "shadow_churn": 0,
        }
        frames.append(frame)
        per_seed_metrics[str(seed)] = {
            "fallback_frame_count": 0,
            "frame_count": 1,
            "rule_assignment_cost_mean": 12.5,
            "rule_churn_mean": 0,
            "rule_high_threat_unmet_total": 0,
            "shadow_assignment_cost_mean": 12.5,
            "shadow_churn_mean": 0,
            "shadow_high_threat_unmet_total": 0,
        }

    paired_report = {
        "schema_version": "d3_shadow_paired_evaluation_v2",
        "cost_basis": "rule_cost_matrix_v1",
        "model_state_dict_sha256": EXPECTED_D3_BUNDLE_STATE_SHA256,
        "dataset_frames_sha256": _token("v2-fixture-frames"),
        "split_hash": _token("v2-fixture-split"),
        "frame_count": 20,
        "frames": frames,
        "assignment_cost": {"rule_mean": 12.5, "shadow_mean": 12.5},
        "high_threat_unmet": {"rule_total": 0, "shadow_total": 0},
        "duplicate_hard_violation": {
            "rule_duplicate_count": 0,
            "rule_hard_violation_count": 0,
            "shadow_duplicate_count": 0,
            "shadow_hard_violation_count": 0,
        },
        "churn": {"rule_mean": 0.0, "shadow_mean": 0.0},
        "inference_ms": {"p50": 0.25, "p95": 0.25},
        "fallback_reasons": {},
        "per_seed_metrics": per_seed_metrics,
        "rule_matrix_unchanged": True,
        "promotion_manifest": {
            "promotion_recommended": False,
            "promotion_status": "unavailable",
        },
    }
    paired_report_sha = audit_module._producer_json_sha256(paired_report)
    payload["paired_evaluator_report"] = paired_report
    payload["paired_evaluator_report_sha256"] = paired_report_sha

    for arm in arms:
        assert isinstance(arm, dict)
        receipt = arm["receipt"]
        spec = arm["arm_specification"]
        plan = arm["plan"]
        assert isinstance(receipt, dict)
        assert isinstance(spec, dict)
        assert isinstance(plan, dict)
        receipt["paired_evaluator_report_sha256"] = paired_report_sha
        receipt["arm_spec_sha256"] = audit_module._producer_json_sha256(spec)
        receipt["output_plan_payload_sha256"] = (
            audit_module._producer_json_sha256(plan)
        )

    applied = manifest["availability"][
        "treatment_safely_applied_in_isolated_simulation"
    ]
    assert isinstance(applied, dict)
    applied.update(
        {
            "value": True,
            "applied_seed_count": 20,
            "fallback_seed_count": 0,
        }
    )
    specification_sha = audit_module._producer_json_sha256(specification)
    payload["specification_sha256"] = specification_sha
    manifest["specification_sha256"] = specification_sha
    manifest["execution_receipts"] = [arm["receipt"] for arm in arms]
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = audit_module._producer_json_sha256(manifest)
    return payload


def _build_d4_v2(
    records: list[dict[str, object]],
) -> dict[str, object]:
    payload = _build_d4(records)
    payload["schema_version"] = (
        audit_module.RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    manifest = payload["manifest"]
    assert isinstance(manifest, dict)
    manifest["schema"] = "d4-region-resource-paired-intervention-manifest-v1"
    specification = manifest["specification"]
    assert isinstance(specification, dict)
    specification.pop("specification_id", None)
    specification["schema"] = "d4-region-resource-paired-intervention-spec-v1"
    specification["thresholds"] = {
        "minimum_confidence": 0.6,
        "inference_timeout_s": 0.05,
    }
    specification["specification_id"] = (
        "d4-rr-paired-spec-"
        + audit_module._producer_json_sha256(specification)
    )
    specification_sha = audit_module._producer_json_sha256(specification)

    evidence = manifest["arm_evidence"]
    assert isinstance(evidence, list)
    for item in evidence:
        assert isinstance(item, dict)
        treatment = item["arm"] == "treatment_candidate"
        item.update(
            {
                "schema": audit_module.EXPECTED_D4_ARM_EVIDENCE_SCHEMA_VERSION_V2,
                "specification_sha256": specification_sha,
                "candidate_gate_diagnostics_available": True,
                "minimum_confidence": 0.6,
                "candidate_latency_limit_ms": 50.0,
                "candidate_confidence": 0.55 if treatment else None,
                "candidate_confidence_gate_passed": (
                    False if treatment else None
                ),
                "candidate_ood_passed": True if treatment else None,
                "candidate_ood_gate_passed": True if treatment else None,
                "candidate_latency_gate_passed": True if treatment else None,
                "candidate_finite": True if treatment else None,
                "candidate_finite_gate_passed": True if treatment else None,
                "candidate_failure_gate_passed": True if treatment else None,
                "candidate_thresholds_passed": not treatment,
                "candidate_safety_projection_passed": not treatment,
                "isolated_treatment_safe_adopted": False,
                "rule_fallback_used": treatment,
                "rejection_reasons": (
                    [
                        "candidate_low_confidence",
                        "candidate_threshold_or_finite_gate_rejected",
                    ]
                    if treatment
                    else []
                ),
            }
        )
    return payload


def _build_v2_fixture(tmp_path: Path) -> ReservedSeedInterventionAuditInputs:
    source_dir = tmp_path / "source-v2"
    source_dir.mkdir()
    records = _build_lineage(EXPECTED_SOURCE_COMMIT_V2)
    d3 = _build_d3_v2(records)
    d4 = _build_d4_v2(records)
    _write_json(source_dir / "d3_offline_paired_intervention.json", d3)
    _write_json(source_dir / "d4_offline_paired_intervention.json", d4)
    (source_dir / "source_lineage.jsonl").write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    (source_dir / "RESERVED_SEED_INTERVENTION_REPORT_CN.md").write_text(
        "# v2 fixture\n",
        encoding="utf-8",
    )
    artifact_sha = {
        "d3_execution": _file_sha(
            source_dir / "d3_offline_paired_intervention.json"
        ),
        "d4_execution": _file_sha(
            source_dir / "d4_offline_paired_intervention.json"
        ),
        "report_cn": _file_sha(
            source_dir / "RESERVED_SEED_INTERVENTION_REPORT_CN.md"
        ),
        "source_lineage": _file_sha(source_dir / "source_lineage.jsonl"),
    }
    candidate_latencies = [float(index) for index in range(1, 21)]
    candidate_gate_summary = {
        "candidate_considered_count": 20,
        "diagnostics_available_count": 20,
        "confidence_gate_passed_count": 0,
        "ood_gate_passed_count": 20,
        "latency_gate_passed_count": 20,
        "finite_gate_passed_count": 20,
        "failure_gate_passed_count": 20,
        "aggregate_gate_passed_count": 0,
        "arm_evidence_schema_versions": [
            audit_module.EXPECTED_D4_ARM_EVIDENCE_SCHEMA_VERSION_V2
        ],
        "candidate_confidence": audit_module._gate_distribution_summary(
            [0.55] * 20
        ),
        "candidate_latency_ms": audit_module._gate_distribution_summary(
            candidate_latencies
        ),
        "minimum_confidence_values": [0.6],
        "candidate_latency_limit_ms_values": [50.0],
    }
    manifest = {
        "schema_version": (
            audit_module.RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
        ),
        "experiment_scope": "reserved_seed_isolated_d3_d4_execution",
        "reserved_seeds": list(range(1000, 1020)),
        "source_episode_count": 20,
        "source_git_commits": [EXPECTED_SOURCE_COMMIT_V2],
        "dirty_source_episode_count": 0,
        "source_nonfinite_count": 0,
        "online_truth_use_count": 0,
        "d3_arm_count": 40,
        "d4_arm_count": 40,
        "scenario": "nominal",
        "scale": 5,
        "resource_count": 5,
        "target_count": 5,
        "duration_s": 2.2,
        "evidence_availability": {
            "causal": False,
            "counterfactual": False,
            "execution_receipts": True,
            "physical_outcome": False,
            "runtime_ack": False,
        },
        "admission": {
            "assist": False,
            "authority": False,
            "ppo": False,
            "rule_fallback": True,
        },
        "artifacts_sha256": artifact_sha,
        "d3_bundle": {
            "loaded": True,
            "expected_manifest_sha256": EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
            "manifest_sha256": EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
            "state_dict_sha256": EXPECTED_D3_BUNDLE_STATE_SHA256,
        },
        "d4_bundle": {
            "loaded": True,
            "bundle_manifest_sha256": EXPECTED_D4_BUNDLE_MANIFEST_SHA256,
            "model_state_sha256": EXPECTED_D4_BUNDLE_STATE_SHA256,
        },
        "d3_treatment_summary": {
            "applied_count": 20,
            "fallback_reason_counts": {},
            "rule_fallback_count": 0,
            "safety_shell_config_sha256": (
                audit_module.EXPECTED_D3_SAFETY_SHELL_CONFIG_SHA256_V2
            ),
            "safety_shell_version": (
                audit_module.EXPECTED_D3_SAFETY_SHELL_VERSION_V2
            ),
        },
        "d4_treatment_summary": {
            "rejection_reason_counts": {
                "candidate_low_confidence": 20,
                "candidate_threshold_or_finite_gate_rejected": 20,
            },
            "rule_fallback_count": 20,
            "safe_adopted_count": 0,
            "candidate_gate_summary": candidate_gate_summary,
        },
    }
    _write_json(source_dir / "manifest.json", manifest)
    checksum_names = (
        "d3_offline_paired_intervention.json",
        "d4_offline_paired_intervention.json",
        "manifest.json",
        "RESERVED_SEED_INTERVENTION_REPORT_CN.md",
        "source_lineage.jsonl",
    )
    (source_dir / "SHA256SUMS").write_text(
        "".join(
            f"{_file_sha(source_dir / name)}  {name}\n"
            for name in checksum_names
        ),
        encoding="ascii",
    )
    return ReservedSeedInterventionAuditInputs(
        source_dir=source_dir,
        output_dir=tmp_path / "output-v2",
        audited_at_utc="2026-07-22T12:00:00Z",
        expected_source_manifest_schema_version=(
            RESERVED_SEED_AUDIT_PROFILE_BINDINGS["v2"][
                "source_manifest_schema_version"
            ]
        ),
        expected_source_commit=EXPECTED_SOURCE_COMMIT_V2,
        expected_checksums_sha256=_file_sha(source_dir / "SHA256SUMS"),
        expected_source_manifest_sha256=_file_sha(source_dir / "manifest.json"),
    )


def _load_v2_fixture(
    inputs: ReservedSeedInterventionAuditInputs,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[int, dict[str, object]],
]:
    d3 = json.loads(
        (inputs.source_dir / "d3_offline_paired_intervention.json").read_text(
            encoding="utf-8"
        )
    )
    d4 = json.loads(
        (inputs.source_dir / "d4_offline_paired_intervention.json").read_text(
            encoding="utf-8"
        )
    )
    lineage = {
        int(record["seed"]): record
        for record in (
            json.loads(line)
            for line in (
                inputs.source_dir / "source_lineage.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        )
    }
    return d3, d4, lineage


def test_synthetic_audit_recomputes_counts_and_keeps_effect_null(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    assert inputs.expected_source_manifest_schema_version.endswith("-v1")

    result = audit_reserved_seed_interventions(inputs)

    assert result["status"] == "pass_fail_closed_only"
    assert result["source"]["schema_version"].endswith("-v1")
    assert result["evidence_availability"] == {
        "execution_receipts": True,
        "runtime_ack": False,
        "physical_outcome": False,
        "counterfactual": False,
        "causal": False,
    }
    assert result["paired_results"]["outcome"]["value"] is None
    assert result["paired_results"]["effect"]["value"] is None
    assert result["d3"]["control_decision_counts"] == {
        "held_by_hysteresis": 3,
        "replan_ack_no_change": 2,
        "unchanged": 15,
    }
    assert result["d3"]["treatment_applied_count"] == 0
    assert result["d4"]["treatment_safe_adopted_count"] == 0
    assert result["d4"]["treatment_candidate_latency_ms"]["mean_ms"] == 10.5
    assert result["d4"]["treatment_candidate_latency_ms"]["p95_ms"] == 19.0
    assert result["claims"]["candidate_policy_effectiveness_proven"] is False
    assert "offline_assignment_comparison" not in result["evidence_availability"]


def test_historical_positional_inputs_keep_v1_schema_default(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    legacy = ReservedSeedInterventionAuditInputs(
        inputs.source_dir,
        inputs.output_dir,
        inputs.audited_at_utc,
        inputs.expected_source_commit,
        inputs.expected_checksums_sha256,
        inputs.expected_source_manifest_sha256,
        inputs.expected_d3_bundle_manifest_sha256,
        inputs.expected_d3_bundle_state_sha256,
        inputs.expected_d4_bundle_manifest_sha256,
        inputs.expected_d4_bundle_state_sha256,
    )

    assert legacy.expected_source_manifest_schema_version.endswith("-v1")
    assert audit_reserved_seed_interventions(legacy)["source"][
        "schema_version"
    ].endswith("-v1")


def test_synthetic_v2_recomputes_gates_without_ignored_outputs(
    tmp_path: Path,
) -> None:
    inputs = _build_v2_fixture(tmp_path)

    result = audit_reserved_seed_interventions(inputs)

    assert result["schema_version"] == RESERVED_SEED_AUDIT_SCHEMA_VERSION_V2
    assert result["status"] == "pass_offline_assignment_comparison_only"
    assert result["d3"]["treatment_applied_count"] == 20
    assert result["d3"]["treatment_rule_fallback_count"] == 0
    comparison = result["d3"]["offline_assignment_comparison"]
    assert comparison["assignment_cost"] == {
        "control_rule_mean": 12.5,
        "treatment_assignment_mean": 12.5,
    }
    assert comparison["inference_latency_ms"]["p95_ms"] == 0.25
    gates = result["d4"]["candidate_gate_summary"]
    assert gates["confidence_gate_passed_count"] == 0
    assert gates["ood_gate_passed_count"] == 20
    assert gates["latency_gate_passed_count"] == 20
    assert gates["finite_gate_passed_count"] == 20
    assert gates["failure_gate_passed_count"] == 20
    assert gates["aggregate_gate_passed_count"] == 0
    assert result["d4"]["treatment_candidate_latency_ms"]["p95_ms"] == 19.0
    assert gates["candidate_latency_ms"]["p95"] == pytest.approx(19.05)
    assert result["paired_results"]["outcome"]["value"] is None
    assert result["paired_results"]["effect"]["value"] is None


def test_writer_does_not_mutate_inputs_and_seals_outputs(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    before = {
        path.name: _file_sha(path) for path in inputs.source_dir.iterdir()
    }

    outputs = write_reserved_seed_intervention_audit(inputs)

    after = {path.name: _file_sha(path) for path in inputs.source_dir.iterdir()}
    assert after == before
    assert set(outputs) == {
        "sidecar",
        "markdown",
        "provenance_manifest",
        "checksums",
    }
    checksum_lines = outputs["checksums"].read_text(encoding="ascii").splitlines()
    for line in checksum_lines:
        expected, name = line.split("  ", 1)
        assert _file_sha(inputs.output_dir / name) == expected
    provenance = json.loads(
        outputs["provenance_manifest"].read_text(encoding="utf-8")
    )
    assert provenance["evidence_availability"]["physical_outcome"] is False
    assert "不证明 D3 或 D4 候选策略有效" in outputs["markdown"].read_text(
        encoding="utf-8"
    )


def test_cli_profile_allows_same_schema_digest_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = _build_fixture(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_reserved_seed_intervention_audit.py",
            "--profile",
            "v1",
            "--source-dir",
            str(inputs.source_dir),
            "--output-dir",
            str(tmp_path / "cli-v1-output"),
            "--audited-at-utc",
            "2026-07-22T13:00:00Z",
            "--expected-source-commit",
            inputs.expected_source_commit,
            "--expected-checksums-sha256",
            inputs.expected_checksums_sha256,
            "--expected-source-manifest-sha256",
            inputs.expected_source_manifest_sha256,
        ],
    )

    assert audit_cli.main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["profile"] == "v1"
    assert summary["source_schema_version"].endswith("-v1")


def test_cli_profile_schema_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _build_fixture(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_reserved_seed_intervention_audit.py",
            "--profile",
            "v2",
            "--source-dir",
            str(inputs.source_dir),
            "--output-dir",
            str(tmp_path / "cli-mismatch-output"),
            "--audited-at-utc",
            "2026-07-22T13:00:00Z",
            "--expected-source-commit",
            inputs.expected_source_commit,
            "--expected-checksums-sha256",
            inputs.expected_checksums_sha256,
            "--expected-source-manifest-sha256",
            inputs.expected_source_manifest_sha256,
        ],
    )

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_cli.main()

    assert error.value.code == "source_manifest_profile_schema_mismatch"


def test_checksum_tamper_is_rejected(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    d4_path = inputs.source_dir / "d4_offline_paired_intervention.json"
    d4_path.write_text(d4_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_reserved_seed_interventions(inputs)

    assert error.value.code == "sha256sums_member_mismatch"


def test_wrong_source_commit_binding_is_rejected(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    wrong = ReservedSeedInterventionAuditInputs(
        source_dir=inputs.source_dir,
        output_dir=inputs.output_dir,
        audited_at_utc=inputs.audited_at_utc,
        expected_source_commit="f" * 40,
        expected_checksums_sha256=inputs.expected_checksums_sha256,
        expected_source_manifest_sha256=inputs.expected_source_manifest_sha256,
    )

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_reserved_seed_interventions(wrong)

    assert error.value.code == "source_lineage_commit_mismatch"


def test_lineage_seed_catalog_must_be_exact() -> None:
    records = _build_lineage()
    records[-1] = {**records[-1], "seed": 1020}

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_module._audit_source_lineage(
            records,
            expected_source_commit=EXPECTED_SOURCE_COMMIT,
        )

    assert error.value.code == "source_lineage_seed_catalog_mismatch"


def test_d3_pair_input_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    records = _build_lineage()
    payload = _build_d3(records)
    manifest = payload["manifest"]
    assert isinstance(manifest, dict)
    specification = manifest["specification"]
    assert isinstance(specification, dict)
    pairs = specification["pairs"]
    assert isinstance(pairs, list)
    first_pair = pairs[0]
    assert isinstance(first_pair, dict)
    treatment = first_pair["treatment"]
    assert isinstance(treatment, dict)
    treatment["observation_input_snapshot_sha256"] = _token("tampered")
    specification_sha = audit_module._producer_json_sha256(specification)
    payload["specification_sha256"] = specification_sha
    manifest["specification_sha256"] = specification_sha
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = audit_module._producer_json_sha256(manifest)

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_module._audit_d3(
            payload,
            lineage_by_seed={int(record["seed"]): record for record in records},
            inputs=inputs,
        )

    assert error.value.code == "d3_pair_input_identity_mismatch"


AUTHORITATIVE_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "scalable_3d_simulation"
    / "outputs"
    / "reserved_seed_interventions_nominal_5v5_1000_1019_formal_6d5bfea"
)


@pytest.mark.skipif(
    not AUTHORITATIVE_SOURCE.is_dir(),
    reason="main-generated authoritative bundle is not present",
)
def test_authoritative_bundle_matches_bound_facts(tmp_path: Path) -> None:
    inputs = ReservedSeedInterventionAuditInputs(
        source_dir=AUTHORITATIVE_SOURCE,
        output_dir=tmp_path / "authoritative-output",
        audited_at_utc="2026-07-22T04:00:00Z",
        expected_checksums_sha256=EXPECTED_CHECKSUMS_SHA256,
        expected_source_manifest_sha256=EXPECTED_SOURCE_MANIFEST_SHA256,
    )

    result = audit_reserved_seed_interventions(inputs)

    assert result["source_lineage"]["record_count"] == 20
    assert result["d3"]["treatment_fallback_reason_counts"] == {
        "out_of_distribution": 20
    }
    assert result["d4"]["treatment_rejection_reason_counts"] == {
        "candidate_threshold_or_finite_gate_rejected": 20
    }
    assert result["d4"]["treatment_candidate_latency_ms"]["mean_ms"] == pytest.approx(
        8.291408499644604
    )
    assert result["paired_results"]["effect"]["value"] is None


AUTHORITATIVE_SOURCE_V2 = (
    Path(__file__).resolve().parents[2]
    / "scalable_3d_simulation"
    / "outputs"
    / "reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296"
)


def _authoritative_v2_inputs(tmp_path: Path) -> ReservedSeedInterventionAuditInputs:
    return ReservedSeedInterventionAuditInputs(
        source_dir=AUTHORITATIVE_SOURCE_V2,
        output_dir=tmp_path / "authoritative-v2-output",
        audited_at_utc="2026-07-22T12:00:00Z",
        expected_source_manifest_schema_version=(
            RESERVED_SEED_AUDIT_PROFILE_BINDINGS["v2"][
                "source_manifest_schema_version"
            ]
        ),
        expected_source_commit=EXPECTED_SOURCE_COMMIT_V2,
        expected_checksums_sha256=EXPECTED_CHECKSUMS_SHA256_V2,
        expected_source_manifest_sha256=EXPECTED_SOURCE_MANIFEST_SHA256_V2,
    )


@pytest.mark.skipif(
    not AUTHORITATIVE_SOURCE_V2.is_dir(),
    reason="main-generated v2 authoritative bundle is not present",
)
def test_authoritative_v2_recomputes_gates_and_keeps_physical_effect_null(
    tmp_path: Path,
) -> None:
    result = audit_reserved_seed_interventions(
        _authoritative_v2_inputs(tmp_path)
    )

    assert result["schema_version"] == RESERVED_SEED_AUDIT_SCHEMA_VERSION_V2
    assert result["status"] == "pass_offline_assignment_comparison_only"
    assert result["evidence_availability"] == {
        "execution_receipts": True,
        "runtime_ack": False,
        "physical_outcome": False,
        "counterfactual": False,
        "causal": False,
        "offline_assignment_comparison": True,
    }
    assert result["d3"]["treatment_applied_count"] == 20
    assert result["d3"]["treatment_rule_fallback_count"] == 0
    comparison = result["d3"]["offline_assignment_comparison"]
    assert comparison["assignment_cost"] == {
        "control_rule_mean": 17.0560260319065,
        "treatment_assignment_mean": 17.0560260319065,
    }
    assert comparison["inference_latency_ms"]["p95_ms"] == pytest.approx(
        0.3108014891040515
    )
    gates = result["d4"]["candidate_gate_summary"]
    assert gates["candidate_considered_count"] == 20
    assert gates["confidence_gate_passed_count"] == 0
    assert gates["ood_gate_passed_count"] == 20
    assert gates["latency_gate_passed_count"] == 20
    assert gates["finite_gate_passed_count"] == 20
    assert gates["failure_gate_passed_count"] == 20
    assert gates["aggregate_gate_passed_count"] == 0
    assert result["d4"]["treatment_safe_adopted_count"] == 0
    assert result["d4"]["treatment_rule_fallback_count"] == 20
    assert result["paired_results"]["outcome"]["value"] is None
    assert result["paired_results"]["effect"]["value"] is None
    assert result["paired_results"]["non_degradation"]["value"] is None
    assert result["claims"]["candidate_policy_effectiveness_proven"] is False
    assert result["claims"]["paired_non_degradation_proven"] is False


def test_v2_writer_preserves_availability_boundary(tmp_path: Path) -> None:
    inputs = _build_v2_fixture(tmp_path)
    outputs = write_reserved_seed_intervention_audit(inputs)
    sidecar = json.loads(outputs["sidecar"].read_text(encoding="utf-8"))
    provenance = json.loads(
        outputs["provenance_manifest"].read_text(encoding="utf-8")
    )

    expected_schema = inputs.expected_source_manifest_schema_version
    assert sidecar["integrity"]["expected_bindings"][
        "source_manifest_schema_version"
    ] == expected_schema
    assert provenance["expected_bindings"][
        "source_manifest_schema_version"
    ] == expected_schema
    assert sidecar["availability_details"]["offline_assignment_comparison"][
        "available"
    ] is True
    assert sidecar["availability_details"]["physical_outcome"]["value"] is None
    assert sidecar["paired_results"]["effect"]["value"] is None
    assert provenance["schema_version"].endswith(".v2")
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "不是通信、节点或资源降级下的策略评估" in markdown
    assert "不证明 D3 或 D4 候选策略有效" in markdown
    assert "p95(nearest-rank)" in markdown
    assert "p95(linear interpolation)" in markdown


def test_v2_writer_is_byte_reproducible_for_same_timestamp(
    tmp_path: Path,
) -> None:
    inputs = _build_v2_fixture(tmp_path)
    first = write_reserved_seed_intervention_audit(inputs)
    second = write_reserved_seed_intervention_audit(
        replace(inputs, output_dir=tmp_path / "output-v2-reproduction")
    )

    assert set(first) == set(second)
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes()


def _reseal_d3_after_spec_change(payload: dict[str, object]) -> None:
    manifest = payload["manifest"]
    assert isinstance(manifest, dict)
    specification = manifest["specification"]
    assert isinstance(specification, dict)
    arms = payload["arms"]
    assert isinstance(arms, list)
    manifest["execution_receipts"] = [arm["receipt"] for arm in arms]
    specification_sha = audit_module._producer_json_sha256(specification)
    payload["specification_sha256"] = specification_sha
    manifest["specification_sha256"] = specification_sha
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = audit_module._producer_json_sha256(manifest)


def test_v2_d3_safety_shell_hash_tamper_is_diagnosed(tmp_path: Path) -> None:
    inputs = _build_v2_fixture(tmp_path)
    d3, _, lineage = _load_v2_fixture(inputs)
    manifest = d3["manifest"]
    assert isinstance(manifest, dict)
    specification = manifest["specification"]
    assert isinstance(specification, dict)
    pairs = specification["pairs"]
    assert isinstance(pairs, list)
    pair = pairs[0]
    assert isinstance(pair, dict)
    arms = d3["arms"]
    assert isinstance(arms, list)
    for kind in ("control", "treatment"):
        pair_spec = pair[kind]
        assert isinstance(pair_spec, dict)
        pair_spec["safety_shell_config_sha256"] = "0" * 64
        arm = next(
            item
            for item in arms
            if item["arm_specification"]["seed"] == 1000
            and item["arm_specification"]["arm_kind"] == kind
        )
        arm["arm_specification"]["safety_shell_config_sha256"] = "0" * 64
        arm["receipt"]["arm_spec_sha256"] = (
            audit_module._producer_json_sha256(arm["arm_specification"])
        )
    _reseal_d3_after_spec_change(d3)

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_module._audit_d3(
            d3,
            lineage_by_seed=lineage,
            inputs=inputs,
            source_schema_version=inputs.expected_source_manifest_schema_version,
        )

    assert error.value.code == "d3_safety_shell_config_sha256_mismatch"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("schema", "d4-region-resource-paired-arm-evidence-v1", "d4_v2_arm_evidence_schema_mismatch"),
        ("candidate_confidence_gate_passed", True, "d4_v2_candidate_confidence_gate_mismatch"),
    ],
)
def test_v2_d4_gate_tamper_is_diagnosed(
    tmp_path: Path,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    inputs = _build_v2_fixture(tmp_path)
    _, d4, lineage = _load_v2_fixture(inputs)
    manifest = d4["manifest"]
    assert isinstance(manifest, dict)
    evidence = manifest["arm_evidence"]
    assert isinstance(evidence, list)
    treatment = next(item for item in evidence if item["arm"] == "treatment_candidate")
    treatment[field] = value

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_module._audit_d4(
            d4,
            lineage_by_seed=lineage,
            inputs=inputs,
            source_schema_version=inputs.expected_source_manifest_schema_version,
        )

    assert error.value.code == expected_code


def test_v2_manifest_gate_summary_tamper_is_diagnosed(tmp_path: Path) -> None:
    inputs = _build_v2_fixture(tmp_path)
    result = audit_reserved_seed_interventions(inputs)
    manifest = json.loads(
        (inputs.source_dir / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["d4_treatment_summary"]["candidate_gate_summary"][
        "confidence_gate_passed_count"
    ] = 1
    input_sha = {
        path.name: _file_sha(path)
        for path in inputs.source_dir.iterdir()
    }

    with pytest.raises(ReservedSeedInterventionAuditError) as error:
        audit_module._validate_source_manifest(
            manifest,
            lineage_summary=result["source_lineage"],
            d3_summary=result["d3"],
            d4_summary=result["d4"],
            inputs=inputs,
            input_sha256=input_sha,
            source_schema_version=inputs.expected_source_manifest_schema_version,
        )

    assert error.value.code == "source_manifest_d4_summary_mismatch"
