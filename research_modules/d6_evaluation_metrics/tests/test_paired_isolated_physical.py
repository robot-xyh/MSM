from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    PairedIsolatedPhysicalEvaluationError,
    PairedIsolatedPhysicalInputs,
    evaluate_paired_isolated_physical,
    load_paired_isolated_physical_inputs,
    write_paired_isolated_physical_report,
)


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _artifact(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": _file_sha(path)}


def _d4_plan(
    *,
    arm_kind: str,
    region_id: str,
    lineage_sha256: str | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "active_plan_owner": "secondary",
        "owner_node_id": "SEC-0001",
        "authority_epoch": 2,
        "lease_expires_at_s": 10.0,
        "current_plan_id": f"d4-plan-{arm_kind}-{region_id}",
        "current_plan_version": 3,
        "identity_created_at_s": 0.1,
        "last_evaluated_at_s": 0.2,
        "execution_signature_changed": False,
        "plan_refresh_only": False,
        "evaluation_refresh_only": True,
        "plan_published": True,
    }
    if lineage_sha256 is not None:
        metadata.update(
            {
                "d4_isolated_execution_source": "deterministic_rule_fallback",
                "d4_candidate_payload_sha256": None,
                "d4_source_lineage_sha256": lineage_sha256,
            }
        )
    return {
        "timestamp": 0.2,
        "plan_id": f"d4-plan-{arm_kind}-{region_id}",
        "plan_version": 3,
        "created_at": 0.1,
        "assignment_count": 1,
        "assignments": [
            {
                "resource_id": "INT-0000",
                "global_track_id": "GT-0001",
                "coalition_id": None,
                "coalition_version": None,
                "member_role": "primary",
                "owner_node_id": "SEC-0001",
                "regional_owner_layer": "secondary",
                "regional_region_id": region_id,
                "regional_epoch": 2,
                "regional_commit_mode": "degrade_to_secondary",
            }
        ],
        "unassigned_global_track_ids": [],
        "metadata": metadata,
    }


def _d4_binding_sha256(plan: dict[str, object]) -> str:
    item = plan["assignments"][0]
    assert isinstance(item, dict)
    signature = (
        (
            item["resource_id"],
            item["global_track_id"],
            item["coalition_id"],
            item["coalition_version"],
            item["member_role"],
            item["owner_node_id"],
            item["regional_owner_layer"],
            item["regional_region_id"],
            item["regional_epoch"],
            item["regional_commit_mode"],
        ),
    )
    return _canonical(signature)


def _valid_d4_adoption_record(
    *,
    arm_kind: str,
    region_id: str = "REGION-0001",
) -> dict[str, object]:
    source_plan = _d4_plan(
        arm_kind=arm_kind,
        region_id=region_id,
        lineage_sha256=None,
    )
    gate = {
        "candidate_considered": False,
        "candidate_id": None,
        "candidate_payload_sha256": None,
        "candidate_confidence": None,
        "minimum_confidence": 0.6,
        "candidate_ood_passed": None,
        "candidate_latency_ms": None,
        "candidate_latency_limit_ms": 50.0,
        "candidate_finite": None,
        "candidate_failure_gate_passed": None,
        "candidate_safety_projection_passed": None,
        "gate_pass": False,
        "rule_fallback": True,
        "rejection_reasons": ["d4_development_candidate_not_admitted"],
        "isolated_simulation_only": True,
        "production_authority": False,
        "schema": "d4-region-resource-isolated-candidate-gate-v1",
    }
    lineage = {
        "scenario_kind": "center_failed",
        "scenario_id": "paired_test",
        "scenario_version": "paired-test-v1",
        "seed": 17,
        "arm_id": f"17-{arm_kind}",
        "cycle_index": 0,
        "region_id": region_id,
        "source_timestamp_s": 0.2,
        "scenario_config_sha256": "1" * 64,
        "initial_state_sha256": "2" * 64,
        "communication_schedule_sha256": "3" * 64,
        "fault_schedule_sha256": "4" * 64,
        "source_snapshot_payload_sha256": "5" * 64,
        "formal_decision_payload_sha256": "6" * 64,
        "source_plan_payload_sha256": _canonical(source_plan),
        "candidate_gate_payload_sha256": _canonical(gate),
        "isolated_simulation_only": True,
        "nominal_evidence": False,
        "schema": "d4-region-resource-degraded-scenario-lineage-v1",
    }
    lineage_sha256 = _canonical(lineage)
    applied_plan = _d4_plan(
        arm_kind=arm_kind,
        region_id=region_id,
        lineage_sha256=lineage_sha256,
    )
    ack_id = f"d4-ack-{arm_kind}-{region_id}"
    ack = {
        "ack_id": ack_id,
        "source_lineage_sha256": lineage_sha256,
        "arm_id": f"17-{arm_kind}",
        "cycle_index": 0,
        "acknowledged_at_s": 2.2,
        "accepted": True,
        "status_code": "accepted_by_isolated_simulation",
        "source_plan_id": source_plan["plan_id"],
        "source_plan_version": source_plan["plan_version"],
        "applied_plan_id": applied_plan["plan_id"],
        "applied_plan_version": applied_plan["plan_version"],
        "applied_plan_payload_sha256": _canonical(applied_plan),
        "execution_binding_sha256": _d4_binding_sha256(applied_plan),
        "execution_source": "deterministic_rule_fallback",
        "owner_layer": "secondary",
        "owner_node_id": "SEC-0001",
        "authority_epoch": 2,
        "lease_expires_at_s": 10.0,
        "assignment_count": 1,
        "control_applied_binding_count": 1,
        "fully_consumed_by_isolated_world": True,
        "network_partition_observed": False,
        "isolated_simulation_only": True,
        "production_runtime_ack": False,
        "schema": "d4-region-resource-isolated-plan-consumption-ack-v1",
    }
    evidence = {
        "code": "isolated_evaluation_refresh_applied",
        "reason": "isolated D4 evaluation refresh was consumed",
        "scenario_kind": "center_failed",
        "scenario_lineage_sha256": lineage_sha256,
        "scenario_validated": True,
        "candidate_considered": False,
        "gate_pass": False,
        "new_execution_plan_applied": False,
        "evaluation_refresh_applied": True,
        "rule_fallback": True,
        "isolated_plan_consumption_ack_available": True,
        "isolated_candidate_adoption_available": False,
        "adoption_kind": "evaluation_refresh_applied",
        "source_plan_id": source_plan["plan_id"],
        "source_plan_version": source_plan["plan_version"],
        "applied_plan_id": applied_plan["plan_id"],
        "applied_plan_version": applied_plan["plan_version"],
        "owner_layer": "secondary",
        "owner_node_id": "SEC-0001",
        "authority_epoch": 2,
        "lease_expires_at_s": 10.0,
        "ack_id": ack_id,
        "ack_timestamp_s": 2.2,
        "candidate_gate_rejection_reasons": [
            "d4_development_candidate_not_admitted"
        ],
        "rejection_reasons": [],
        "isolated_simulation_only": True,
        "production_runtime_ack": False,
        "physical_outcome_available": False,
        "paired_non_degradation_available": False,
        "counterfactual_available": False,
        "causal_effect_available": False,
        "degradation_effectiveness_claim_allowed": False,
        "ppo_enabled": False,
        "assist_enabled": False,
        "authority_enabled": False,
        "rule_fallback_enabled": True,
        "schema": "d4-region-resource-isolated-adoption-evidence-v1",
    }
    return {
        "arm_kind": arm_kind,
        "region_id": region_id,
        "intervention_kind": "center_failed",
        "available": True,
        "reason": None,
        "source_plan": source_plan,
        "applied_plan": applied_plan,
        "scenario_lineage": lineage,
        "candidate_gate": gate,
        "plan_consumption_ack": ack,
        "adoption_evidence": evidence,
        "schema_version": "scalable3d-d4-isolated-physical-adoption-v1",
    }


def _unavailable_d4_adoption_record(
    *,
    arm_kind: str,
    region_id: str,
) -> dict[str, object]:
    return {
        "arm_kind": arm_kind,
        "region_id": region_id,
        "intervention_kind": "center_failed",
        "available": False,
        "reason": "formal_region_not_executable",
        "source_plan": None,
        "applied_plan": None,
        "scenario_lineage": None,
        "candidate_gate": None,
        "plan_consumption_ack": None,
        "adoption_evidence": None,
        "schema_version": "scalable3d-d4-isolated-physical-adoption-v1",
    }


def _auditable_unavailable_d4_adoption_record(
    *,
    arm_kind: str,
    region_id: str = "REGION-0001",
) -> dict[str, object]:
    """Match a producer record whose ACK exists but was not admitted by D4."""

    record = _valid_d4_adoption_record(
        arm_kind=arm_kind,
        region_id=region_id,
    )
    record["available"] = False
    record["reason"] = "isolated_execution_plan_not_strictly_new"
    evidence = record["adoption_evidence"]
    assert isinstance(evidence, dict)
    evidence.update(
        {
            "code": "isolated_execution_plan_not_strictly_new",
            "reason": (
                "execution change requires a new plan id, higher version, "
                "and new timestamp"
            ),
            "new_execution_plan_applied": False,
            "evaluation_refresh_applied": False,
            "isolated_plan_consumption_ack_available": False,
            "isolated_candidate_adoption_available": False,
            "adoption_kind": None,
            "ack_id": None,
            "ack_timestamp_s": None,
            "rejection_reasons": [
                "isolated_execution_plan_not_strictly_new"
            ],
        }
    )
    return record


def _arm_files(
    root: Path,
    *,
    arm_kind: str,
    shared_hashes: dict[str, str],
    missing_guidance: bool,
    d4_records: list[dict[str, object]] | None,
) -> dict[str, Path]:
    arm_root = root / arm_kind
    episode_id = f"episode-17-{arm_kind}"
    world_id = f"world-17-{arm_kind}"
    plan = {
        "schema_version": "assignment_plan_v2",
        "plan_id": f"plan-{arm_kind}",
        "plan_version": 1,
        "created_at": 0.1,
        "assignments": [
            {"resource_id": "INT-0000", "global_track_id": "GT-0001"}
        ],
    }
    plan_hash = _canonical(plan)
    assignments_hash = _canonical(plan["assignments"])
    plans_path = arm_root / "assignment_plans.jsonl"
    _write_jsonl(
        plans_path,
        [
            {
                "schema_version": "d3.isolated-plan-publication.v1",
                "published_at_s": 0.1,
                "plan_payload_sha256": plan_hash,
                "plan": plan,
            }
        ],
    )
    consumption_path = arm_root / "isolated_plan_consumption.jsonl"
    consumption_id = f"consume-{arm_kind}-1"
    _write_jsonl(
        consumption_path,
        [
            {
                "schema_version": (
                    "d3.isolated-plan-consumption-confirmation.v1"
                ),
                "consumption_id": consumption_id,
                "cycle_index": 1,
                "consumed_at_s": 0.2,
                "evidence_scope": "paired_isolated_simulation_only",
                "production_runtime_ack": False,
                "accepted": True,
                "status_code": "isolated_plan_consumed",
                "plan_id": plan["plan_id"],
                "plan_version": plan["plan_version"],
                "plan_payload_sha256": plan_hash,
                "consumed_assignments_sha256": assignments_hash,
            }
        ],
    )
    commands: list[dict[str, object]] = []
    applications: list[dict[str, object]] = []
    if not missing_guidance:
        for cycle, timestamp in ((1, 0.25), (2, 1.0)):
            command_id = f"command-{arm_kind}-{cycle}"
            application_id = f"apply-{arm_kind}-{cycle}"
            command_payload = {
                "acceleration_ned_mps2": [-2.0, 0.0, 0.0],
                "guidance_mode": "position_png",
            }
            command_hash = _canonical(command_payload)
            commands.append(
                {
                    "schema_version": "d7.isolated-command-lineage.v1",
                    "command_id": command_id,
                    "cycle_index": cycle,
                    "issued_at_s": timestamp,
                    "consumption_id": consumption_id,
                    "plan_id": plan["plan_id"],
                    "plan_version": plan["plan_version"],
                    "plan_payload_sha256": plan_hash,
                    "resource_id": "INT-0000",
                    "global_track_id": "GT-0001",
                    "command_payload_sha256": command_hash,
                    "command_payload": command_payload,
                    "control_applied_to_world": True,
                    "world_application_id": application_id,
                }
            )
            applications.append(
                {
                    "schema_version": (
                        "scalable3d-isolated-world-application.v1"
                    ),
                    "world_application_id": application_id,
                    "world_id": world_id,
                    "cycle_index": cycle,
                    "applied_at_s": timestamp + 0.05,
                    "command_id": command_id,
                    "command_payload_sha256": command_hash,
                    "resource_id": "INT-0000",
                    "global_track_id": "GT-0001",
                    "control_applied_to_world": True,
                    "hard_constraint_violation_count": 0,
                }
            )
    commands_path = arm_root / "d7_command_lineage.jsonl"
    applications_path = arm_root / "world_applications.jsonl"
    _write_jsonl(commands_path, commands)
    _write_jsonl(applications_path, applications)

    identity_path = arm_root / "offline_truth_identity.json"
    _write_json(
        identity_path,
        {
            "schema_version": "d6.paired-isolated-offline-identity.v1",
            "episode_id": episode_id,
            "world_id": world_id,
            "seed": 17,
            "online_truth_isolation_verified": True,
            "online_truth_use_count": 0,
            "mappings": [
                {
                    "global_track_id": "GT-0001",
                    "truth_target_id": "TGT-0001",
                    "mapping_status": "unique_lineage_verified",
                }
            ],
        },
    )
    positions = (
        [20.0, 15.0, 10.0, 6.0, 4.0]
        if arm_kind == "control"
        else [20.0, 14.0, 8.0, 4.0, 3.0]
    )
    truth_path = arm_root / "offline_truth_state.jsonl"
    truth_rows: list[dict[str, object]] = []
    for index, timestamp in enumerate((0.0, 0.5, 1.0, 1.5, 2.0)):
        truth_rows.append(
            {
                "schema_version": "scalable3d-offline-truth-state-sample.v1",
                "episode_id": episode_id,
                "world_id": world_id,
                "seed": 17,
                "timestamp_s": timestamp,
                "interceptor_positions_ned_m": {
                    "INT-0000": [positions[index], 0.0, 0.0]
                },
                "target_positions_ned_m": {
                    "TGT-0001": [0.0, 0.0, 0.0],
                    "TGT-0002": [100.0, 0.0, 0.0],
                },
            }
        )
    _write_jsonl(truth_path, truth_rows)
    paths = {
        "assignment_plans": plans_path,
        "isolated_plan_consumption": consumption_path,
        "d7_command_lineage": commands_path,
        "world_applications": applications_path,
        "offline_truth_identity": identity_path,
        "offline_truth_state": truth_path,
    }
    if d4_records is not None:
        d4_path = arm_root / "d4_adoption_evidence.jsonl"
        _write_jsonl(d4_path, d4_records)
        paths["d4_adoption_evidence"] = d4_path
    manifest_path = arm_root / "episode_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": (
                "scalable3d-isolated-arm-episode-manifest-v1"
            ),
            "pair_id": "pair-17",
            "arm_kind": arm_kind,
            "episode_id": episode_id,
            "world_id": world_id,
            "seed": 17,
            "scenario_name": "paired_test",
            "scenario_version": "paired-test-v1",
            "world_schema": "scalable3d-world-v1",
            "bus_schema": "scalable3d-episode-bus-v1",
            "duration_s": 2.0,
            "physics_dt_s": 0.5,
            "intercept_radius_m": 5.0,
            "isolated_simulation": True,
            "truth_isolation_verified": True,
            "online_truth_use_count": 0,
            "production_runtime_ack_available": False,
            "shared_artifact_sha256": shared_hashes,
            "arm_artifact_sha256": {
                name: _file_sha(path) for name, path in paths.items()
            },
        },
    )
    return {"episode_manifest": manifest_path, **paths}


def _build_inputs(
    tmp_path: Path,
    *,
    missing_treatment_guidance: bool = False,
    d4_mode: str = "legacy",
) -> PairedIsolatedPhysicalInputs:
    shared_root = tmp_path / "shared"
    initial_state = shared_root / "initial_state.json"
    _write_json(
        initial_state,
        {
            "schema_version": "scalable3d-paired-initial-state-v1",
            "seed": 17,
            "scenario_name": "paired_test",
            "scenario_version": "paired-test-v1",
            "interceptor_positions_ned_m": {
                "INT-0000": [20.0, 0.0, 0.0]
            },
            "target_positions_ned_m": {
                "TGT-0001": [0.0, 0.0, 0.0],
                "TGT-0002": [100.0, 0.0, 0.0],
            },
        },
    )
    shared_paths = {"initial_state": initial_state}
    for name, schema in (
        ("sensor_schedule", "scalable3d-exogenous-sensor-schedule-v1"),
        (
            "communication_schedule",
            "scalable3d-exogenous-communication-schedule-v1",
        ),
        ("fault_schedule", "scalable3d-exogenous-fault-schedule-v1"),
    ):
        path = shared_root / f"{name}.json"
        _write_json(
            path,
            {
                "schema_version": schema,
                "seed": 17,
                "scenario_name": "paired_test",
                "scenario_version": "paired-test-v1",
                "events": [],
            },
        )
        shared_paths[name] = path
    shared_hashes = {name: _file_sha(path) for name, path in shared_paths.items()}
    if d4_mode == "legacy":
        d4_records = {"control": None, "treatment": None}
    elif d4_mode == "nominal_empty":
        d4_records = {"control": [], "treatment": []}
    elif d4_mode == "valid":
        d4_records = {
            arm_kind: [_valid_d4_adoption_record(arm_kind=arm_kind)]
            for arm_kind in ("control", "treatment")
        }
    elif d4_mode == "partial_treatment":
        d4_records = {
            "control": [
                _valid_d4_adoption_record(arm_kind="control"),
                _valid_d4_adoption_record(
                    arm_kind="control", region_id="REGION-0002"
                ),
            ],
            "treatment": [
                _valid_d4_adoption_record(arm_kind="treatment"),
                _unavailable_d4_adoption_record(
                    arm_kind="treatment", region_id="REGION-0002"
                ),
            ],
        }
    elif d4_mode == "auditable_unavailable":
        d4_records = {
            arm_kind: [
                _auditable_unavailable_d4_adoption_record(
                    arm_kind=arm_kind
                )
            ]
            for arm_kind in ("control", "treatment")
        }
    else:
        raise ValueError(f"unsupported D4 fixture mode: {d4_mode}")
    control = _arm_files(
        tmp_path,
        arm_kind="control",
        shared_hashes=shared_hashes,
        missing_guidance=False,
        d4_records=d4_records["control"],
    )
    treatment = _arm_files(
        tmp_path,
        arm_kind="treatment",
        shared_hashes=shared_hashes,
        missing_guidance=missing_treatment_guidance,
        d4_records=d4_records["treatment"],
    )
    mapping = {
        "schema_version": "d6.paired-isolated-physical-inputs.v1",
        "evaluation_id": "paired-evaluation-17",
        "pairs": [
            {
                "pair_id": "pair-17",
                "seed": 17,
                "shared_artifacts": {
                    name: _artifact(path) for name, path in shared_paths.items()
                },
                "arms": {
                    "control": {
                        name: _artifact(path) for name, path in control.items()
                    },
                    "treatment": {
                        name: _artifact(path) for name, path in treatment.items()
                    },
                },
            }
        ],
    }
    return PairedIsolatedPhysicalInputs.from_mapping(mapping)


def _refresh_inputs(inputs: PairedIsolatedPhysicalInputs) -> PairedIsolatedPhysicalInputs:
    mapping = inputs.to_dict()
    for pair in mapping["pairs"]:
        for item in pair["shared_artifacts"].values():
            item["sha256"] = _file_sha(Path(item["path"]))
        for arm in pair["arms"].values():
            for item in arm.values():
                item["sha256"] = _file_sha(Path(item["path"]))
    return PairedIsolatedPhysicalInputs.from_mapping(mapping)


def _rewrite_arm_manifest_binding(
    inputs: PairedIsolatedPhysicalInputs,
    *,
    arm_kind: str,
    artifact_name: str,
) -> PairedIsolatedPhysicalInputs:
    pair = inputs.pairs[0]
    arm = getattr(pair, arm_kind)
    manifest_path = arm.episode_manifest.path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["arm_artifact_sha256"][artifact_name] = _file_sha(
        getattr(arm, artifact_name).path
    )
    _write_json(manifest_path, payload)
    return _refresh_inputs(inputs)


def test_complete_pair_reports_strict_availability_and_descriptive_deltas(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path)

    report = evaluate_paired_isolated_physical(inputs)

    pair = report["pair_results"][0]
    availability = pair["availability"]
    for name in (
        "plan_consumption",
        "guidance_lineage",
        "physical_window",
        "paired_physical_effect",
        "paired_non_degradation",
    ):
        assert availability[name]["available"] is True
        assert availability[name]["value"] is not None
        assert availability[name]["reason"] is None
    assert availability["counterfactual"] == {
        "available": False,
        "status": "unavailable",
        "value": None,
        "reason": (
            "paired_isolated_trajectories_are_observed_comparisons_not_"
            "counterfactual_proof"
        ),
    }
    assert availability["causal"]["available"] is False
    assert pair["arms"]["control"]["metrics"]["success_count"] == 1
    assert pair["arms"]["treatment"]["metrics"]["success_count"] == 1
    delta = availability["paired_physical_effect"]["value"]
    assert delta["success_count_delta"] == 0
    assert delta["mean_closest_distance_delta_m"] == pytest.approx(-1.0)
    assert delta["time_to_five_meter_delta_s"] == pytest.approx(-0.5)
    assert delta["hard_constraint_violation_count_delta"] == 0
    assert delta["incorrect_binding_count_delta"] == 0
    assert availability["paired_non_degradation"]["value"]["overall"] is True
    assert report["claim_boundary"]["production_runtime_ack_evaluated"] is False
    assert report["audit"]["source_mutation_performed"] is False


def test_missing_guidance_keeps_dependent_values_null(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path, missing_treatment_guidance=True)

    report = evaluate_paired_isolated_physical(inputs)

    availability = report["pair_results"][0]["availability"]
    assert availability["plan_consumption"]["available"] is True
    for name in (
        "guidance_lineage",
        "physical_window",
        "paired_physical_effect",
        "paired_non_degradation",
        "counterfactual",
        "causal",
    ):
        assert availability[name]["available"] is False
        assert availability[name]["value"] is None
        assert availability[name]["reason"]
    aggregate = report["aggregate"]
    assert aggregate["paired_physical_effect"]["value"] is None
    assert aggregate["paired_non_degradation"]["value"] is None


def test_out_of_band_hash_tamper_fails_closed(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path)
    target = inputs.pairs[0].treatment.d7_command_lineage.path
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "input_artifact_hash_mismatch"


def test_cross_seed_manifest_mismatch_fails_closed(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path)
    manifest_path = inputs.pairs[0].treatment.episode_manifest.path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["seed"] = 18
    _write_json(manifest_path, payload)
    inputs = _refresh_inputs(inputs)

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "arm_manifest_pair_identity_mismatch"


def test_cross_arm_initial_state_mismatch_fails_closed(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path)
    truth_path = inputs.pairs[0].treatment.offline_truth_state.path
    rows = [json.loads(line) for line in truth_path.read_text().splitlines()]
    rows[0]["interceptor_positions_ned_m"]["INT-0000"][0] = 19.0
    _write_jsonl(truth_path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="offline_truth_state",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "paired_initial_state_mismatch"


def test_isolated_confirmation_cannot_impersonate_production_ack(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path)
    path = inputs.pairs[0].treatment.isolated_plan_consumption.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["production_runtime_ack"] = True
    _write_jsonl(path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="isolated_plan_consumption",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "production_runtime_ack_impersonation"


def test_d7_command_plan_lineage_mismatch_fails_closed(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path)
    path = inputs.pairs[0].treatment.d7_command_lineage.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["plan_payload_sha256"] = "a" * 64
    _write_jsonl(path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="d7_command_lineage",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "d7_command_plan_lineage_mismatch"


def test_hashed_input_spec_and_output_sidecar_are_deterministic(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path / "inputs")
    spec_path = tmp_path / "input_spec.json"
    _write_json(spec_path, inputs.to_dict())

    loaded = load_paired_isolated_physical_inputs(
        spec_path,
        expected_sha256=_file_sha(spec_path),
    )
    first_paths = write_paired_isolated_physical_report(
        loaded,
        tmp_path / "output_first",
    )
    second_paths = write_paired_isolated_physical_report(
        loaded,
        tmp_path / "output_second",
    )

    assert json.loads(first_paths["sidecar"].read_text())["schema_version"] == (
        "d6.paired-isolated-physical-evaluation.v1"
    )
    for name in ("sidecar", "markdown", "manifest", "checksums"):
        assert _file_sha(first_paths[name]) == _file_sha(second_paths[name])
    checksums = first_paths["checksums"].read_text(encoding="utf-8")
    assert "paired_isolated_physical_sidecar.json" in checksums
    assert "paired_isolated_physical_report_cn.md" in checksums


def test_valid_d4_adoption_enables_descriptive_degraded_pair_comparison(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")

    report = evaluate_paired_isolated_physical(inputs)

    pair = report["pair_results"][0]
    for arm_kind in ("control", "treatment"):
        layer = pair["arms"][arm_kind]["availability"][
            "d4_degraded_adoption"
        ]
        assert layer["available"] is True
        assert layer["value"]["region_count"] == 1
        assert layer["value"]["available_count"] == 1
        assert layer["value"]["reason_counts"] == {}
        assert layer["value"]["intervention_kind"] == "center_failed"
    paired_d4 = pair["availability"]["d4_degraded_adoption"]
    assert paired_d4["available"] is True
    degraded = pair["availability"]["degraded_paired_physical_comparison"]
    assert degraded["available"] is True
    assert degraded["value"]["comparison_scope"] == (
        "paired_isolated_simulation_comparison"
    )
    assert degraded["value"]["production_runtime_ack"] is False
    assert degraded["value"]["counterfactual_claim_allowed"] is False
    assert degraded["value"]["causal_claim_allowed"] is False
    assert pair["availability"]["counterfactual"]["available"] is False
    assert pair["availability"]["causal"]["available"] is False
    aggregate = report["aggregate"]
    assert aggregate["d4_degraded_adoption"]["available"] is True
    assert aggregate["degraded_paired_physical_comparison"]["available"] is True


def test_partial_d4_region_retains_summary_but_blocks_degraded_comparison(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="partial_treatment")

    report = evaluate_paired_isolated_physical(inputs)

    pair = report["pair_results"][0]
    control = pair["arms"]["control"]["availability"]["d4_degraded_adoption"]
    treatment = pair["arms"]["treatment"]["availability"][
        "d4_degraded_adoption"
    ]
    assert control["available"] is True
    assert control["value"]["region_count"] == 2
    assert treatment["available"] is False
    assert treatment["value"]["region_count"] == 2
    assert treatment["value"]["available_count"] == 1
    assert treatment["value"]["reason_counts"] == {
        "formal_region_not_executable": 1
    }
    assert pair["availability"]["d4_degraded_adoption"]["available"] is False
    degraded = pair["availability"]["degraded_paired_physical_comparison"]
    assert degraded["available"] is False
    assert degraded["value"] is None
    assert pair["availability"]["paired_physical_effect"]["available"] is True


def test_unadmitted_but_auditable_d4_ack_keeps_adoption_unavailable(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="auditable_unavailable")

    report = evaluate_paired_isolated_physical(inputs)

    pair = report["pair_results"][0]
    for arm_kind in ("control", "treatment"):
        layer = pair["arms"][arm_kind]["availability"][
            "d4_degraded_adoption"
        ]
        assert layer["available"] is False
        assert layer["value"]["region_count"] == 1
        assert layer["value"]["available_count"] == 0
        assert layer["value"]["reason_counts"] == {
            "isolated_execution_plan_not_strictly_new": 1
        }
    assert pair["availability"]["d4_degraded_adoption"]["available"] is False
    degraded = pair["availability"]["degraded_paired_physical_comparison"]
    assert degraded["available"] is False
    assert degraded["value"] is None
    assert pair["availability"]["counterfactual"]["available"] is False
    assert pair["availability"]["causal"]["available"] is False
    aggregate = report["aggregate"]
    assert aggregate["d4_degraded_adoption"]["available"] is False
    assert aggregate["degraded_paired_physical_comparison"]["available"] is False


def test_declared_empty_d4_file_is_nominal_not_applicable(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="nominal_empty")

    report = evaluate_paired_isolated_physical(inputs)

    pair = report["pair_results"][0]
    for arm_kind in ("control", "treatment"):
        layer = pair["arms"][arm_kind]["availability"][
            "d4_degraded_adoption"
        ]
        assert layer["status"] == "not_applicable"
        assert layer["reason"] is None
        assert layer["value"]["region_count"] == 0
    assert pair["availability"]["d4_degraded_adoption"]["status"] == (
        "not_applicable"
    )
    assert pair["availability"]["degraded_paired_physical_comparison"][
        "status"
    ] == "not_applicable"
    assert report["aggregate"]["d4_degraded_adoption"]["status"] == (
        "not_applicable"
    )


def test_legacy_input_without_d4_artifact_remains_compatible(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="legacy")

    report = evaluate_paired_isolated_physical(inputs)

    pair = report["pair_results"][0]
    assert pair["arms"]["control"]["availability"]["d4_degraded_adoption"] == {
        "available": False,
        "status": "not_declared",
        "value": None,
        "reason": "d4_adoption_artifact_not_declared_by_input_spec",
    }
    assert pair["availability"]["paired_physical_effect"]["available"] is True
    assert pair["availability"]["degraded_paired_physical_comparison"][
        "available"
    ] is False


def test_declared_d4_file_missing_fails_closed(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")
    path = inputs.pairs[0].treatment.d4_adoption_evidence
    assert path is not None
    path.path.unlink()

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "input_artifact_missing"


def test_declared_d4_sha_tamper_fails_closed(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")
    artifact = inputs.pairs[0].treatment.d4_adoption_evidence
    assert artifact is not None
    artifact.path.write_text(
        artifact.path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "input_artifact_hash_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("arm", "d4_adoption_arm_mismatch"),
        ("region", "d4_scenario_lineage_identity_mismatch"),
        ("seed", "d4_scenario_lineage_identity_mismatch"),
        ("plan", "d4_adoption_source_plan_hash_mismatch"),
    ),
)
def test_d4_identity_or_plan_tamper_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")
    artifact = inputs.pairs[0].treatment.d4_adoption_evidence
    assert artifact is not None
    rows = [json.loads(line) for line in artifact.path.read_text().splitlines()]
    if mutation == "arm":
        rows[0]["arm_kind"] = "control"
    elif mutation == "region":
        rows[0]["scenario_lineage"]["region_id"] = "REGION-X"
    elif mutation == "seed":
        rows[0]["scenario_lineage"]["seed"] = 18
    else:
        rows[0]["scenario_lineage"]["source_plan_payload_sha256"] = "a" * 64
    _write_jsonl(artifact.path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="d4_adoption_evidence",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == expected_code


def test_d4_isolated_ack_cannot_impersonate_production_runtime(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")
    artifact = inputs.pairs[0].treatment.d4_adoption_evidence
    assert artifact is not None
    rows = [json.loads(line) for line in artifact.path.read_text().splitlines()]
    rows[0]["plan_consumption_ack"]["production_runtime_ack"] = True
    _write_jsonl(artifact.path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="d4_adoption_evidence",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "production_runtime_ack_impersonation"


def test_d4_admitted_verdict_ack_id_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")
    artifact = inputs.pairs[0].treatment.d4_adoption_evidence
    assert artifact is not None
    rows = [json.loads(line) for line in artifact.path.read_text().splitlines()]
    rows[0]["adoption_evidence"]["ack_id"] = "forged-ack-id"
    _write_jsonl(artifact.path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="d4_adoption_evidence",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "d4_adoption_verdict_ack_mismatch"


def test_d4_retained_ack_plan_lineage_forgery_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="auditable_unavailable")
    artifact = inputs.pairs[0].treatment.d4_adoption_evidence
    assert artifact is not None
    rows = [json.loads(line) for line in artifact.path.read_text().splitlines()]
    rows[0]["plan_consumption_ack"]["source_plan_id"] = "forged-plan-id"
    _write_jsonl(artifact.path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="d4_adoption_evidence",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "d4_plan_ack_plan_lineage_mismatch"


def test_d4_top_level_available_cannot_use_unadmitted_ack(
    tmp_path: Path,
) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="auditable_unavailable")
    artifact = inputs.pairs[0].treatment.d4_adoption_evidence
    assert artifact is not None
    rows = [json.loads(line) for line in artifact.path.read_text().splitlines()]
    rows[0]["available"] = True
    rows[0]["reason"] = None
    _write_jsonl(artifact.path, rows)
    inputs = _rewrite_arm_manifest_binding(
        inputs,
        arm_kind="treatment",
        artifact_name="d4_adoption_evidence",
    )

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "d4_adoption_available_state_invalid"


def test_d4_spec_and_manifest_declarations_must_match(tmp_path: Path) -> None:
    inputs = _build_inputs(tmp_path, d4_mode="valid")
    manifest_path = inputs.pairs[0].treatment.episode_manifest.path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["arm_artifact_sha256"]["d4_adoption_evidence"]
    _write_json(manifest_path, payload)
    inputs = _refresh_inputs(inputs)

    with pytest.raises(PairedIsolatedPhysicalEvaluationError) as error:
        evaluate_paired_isolated_physical(inputs)

    assert error.value.code == "arm_optional_artifact_declaration_mismatch"
