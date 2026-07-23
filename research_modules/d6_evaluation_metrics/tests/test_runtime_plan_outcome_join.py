from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode

from d6_evaluation_metrics.runtime_plan_outcome_join import (
    HashedArtifact,
    RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME,
    RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION,
    RuntimePlanOutcomeJoinError,
    RuntimePlanOutcomeJoinInputs,
    evaluate_runtime_plan_outcomes,
    load_runtime_plan_outcome_join_inputs,
    write_runtime_plan_outcome_join_report,
)


def _canonical_hash(payload: Any, *, prefixed: bool = False) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    value = hashlib.sha256(encoded).hexdigest()
    return f"sha256:{value}" if prefixed else value


def _file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _report_business_hash(payload: Mapping[str, Any]) -> str:
    normalized = copy.deepcopy(payload)
    for name, artifact in normalized["source_artifacts"].items():
        artifact["path"] = f"<{name}>"
    return _canonical_hash(normalized, prefixed=True)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _envelope(
    sequence: int,
    topic: str,
    source: str,
    timestamp: float,
    schema: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "topic": topic,
        "source": source,
        "timestamp": timestamp,
        "schema_version": schema,
        "payload": dict(payload),
    }


def _assignment(plan_version: int, track_id: str) -> dict[str, Any]:
    return {
        "resource_id": "INT-0001",
        "global_track_id": track_id,
        "coalition_id": f"COAL-{track_id}",
        "coalition_version": plan_version,
        "member_role": "primary",
    }


def _plan(plan_version: int, track_id: str, timestamp: float) -> dict[str, Any]:
    return {
        "plan_id": "PLAN-A",
        "plan_version": plan_version,
        "created_at": timestamp,
        "assignment_count": 1,
        "assignments": [_assignment(plan_version, track_id)],
        "unassigned_global_track_ids": [],
        "metadata": {
            "active_plan_owner": "center",
            "owner_node_id": "C2",
            "authority_epoch": 1,
            "lease_expires_at_s": timestamp + 10.0,
            "execution_signature_changed": True,
            "evaluation_refresh_only": False,
            "plan_refresh_only": False,
        },
    }


def _guidance(
    plan_version: int,
    track_id: str,
    timestamp: float,
    *,
    mode: str = "midcourse_pn_3d",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "commands": [
            {
                "resource_id": "INT-0001",
                "global_track_id": track_id,
                "plan_id": "PLAN-A",
                "plan_version": plan_version,
                "mode": mode,
                "gate_reason": (
                    "hold_by_contract"
                    if mode == "hold"
                    else "midcourse_position_guidance"
                ),
            }
        ],
    }


def _ack(
    plan: Mapping[str, Any],
    guidance: Mapping[str, Any] | None,
    *,
    sequence: int,
    plan_sequence: int,
    guidance_sequence: int | None,
    ack_timestamp: float | None = None,
) -> dict[str, Any]:
    assignment = plan["assignments"][0]
    command = None if guidance is None else guidance["commands"][0]
    mode = None if command is None else command["mode"]
    reason = None if command is None else command["gate_reason"]
    present = command is not None
    held = command is None or mode == "hold"
    version = int(plan["plan_version"])
    plan_created_at = float(plan["created_at"])
    timestamp = plan_created_at if ack_timestamp is None else float(ack_timestamp)
    metadata = plan["metadata"]
    payload = {
        "decision_id": f"PLAN-A:v{version}",
        "ack_timestamp": timestamp,
        "plan_id": "PLAN-A",
        "plan_version": version,
        "plan_created_at": plan_created_at,
        "plan_schema_version": "assignment_plan_v2",
        "source_plan_bus_sequence": plan_sequence,
        "source_plan_payload_sha256": _canonical_hash(plan),
        "source_guidance_bus_sequence": guidance_sequence,
        "source_guidance_payload_sha256": (
            None if guidance is None else _canonical_hash(guidance)
        ),
        "accepted": True,
        "status_code": "accepted_by_main_runtime",
        "assignment_count": 1,
        "binding_ack_count": int(present),
        "fully_bound_to_guidance": present,
        "control_applied_binding_count": int(present),
        "held_binding_count": int(held),
        "active_plan_owner": metadata["active_plan_owner"],
        "owner_node_id": metadata["owner_node_id"],
        "authority_epoch": metadata["authority_epoch"],
        "lease_expires_at_s": metadata["lease_expires_at_s"],
        "d3_learning_evidence": {
            "mode": "shadow",
            "applied": False,
            "shadow_only": True,
            "bundle_loaded": True,
            "fallback_reason": None,
            "model_fingerprint": "sha256:model-d3",
        },
        "d4_regional_hint_evidence": {
            "considered": True,
            "applied": False,
            "rejected": True,
            "fallback_reason": "center_plan_retained",
            "advisory_id": "ADV-1",
            "advisory_version": 1,
            "source_plan_id": "PLAN-PREVIOUS",
            "source_plan_version": 0,
        },
        "binding_acks": [
            {
                "resource_id": assignment["resource_id"],
                "global_track_id": assignment["global_track_id"],
                "coalition_id": assignment["coalition_id"],
                "coalition_version": assignment["coalition_version"],
                "member_role": assignment["member_role"],
                "guidance_command_present": present,
                "guidance_mode": mode,
                "guidance_gate_reason": reason,
                "control_applied_to_world": present,
                "held": held,
            }
        ],
        "physical_outcome_available": False,
        "reward_available": False,
    }
    return _envelope(
        sequence,
        "runtime.assignment_plan_ack",
        "MAIN-RUNTIME",
        timestamp,
        "scalable3d-assignment-plan-runtime-ack-v1",
        payload,
    )


def _track_mapping(track_id: str, truth_id: str) -> dict[str, Any]:
    observation_id = f"OBS-{track_id}"
    return {
        "global_track_id": track_id,
        "lifecycle_state": "confirmed",
        "association_state": "matched",
        "status": "available",
        "truth_target_id": truth_id,
        "reason": None,
        "unavailable_reasons": [],
        "candidate_truth_target_ids": [truth_id],
        "source_observation_ids": [observation_id],
        "source_lineage_hashes": [
            f"sha256:{hashlib.sha256(observation_id.encode()).hexdigest()}"
        ],
        "evidence_count": 1,
        "unique_lineage_count": 1,
        "labeled_evidence_count": 1,
        "replayed_lineage_count": 0,
    }


def _identity_frame(index: int, timestamp: float) -> dict[str, Any]:
    mappings = [
        _track_mapping("GT-0001", "TGT-0001"),
        _track_mapping("GT-0002", "TGT-0002"),
    ]
    return {
        "schema_version": "d2.scalable3d_global_track_truth_mapping.v1",
        "frame_index": index,
        "frame_timestamp": timestamp,
        "truth_target_ids_present": ["TGT-0001", "TGT-0002"],
        "mappings": mappings,
        "evidence_count": 2,
        "unique_lineage_count": 2,
        "replayed_lineage_count": 0,
        "duplicate_lineage_count": 0,
        "available_mapping_count": 2,
        "ambiguous_mapping_count": 0,
        "unavailable_mapping_count": 0,
        "reason_counts": {},
    }


def _make_fixture(
    root: Path,
    *,
    first_guidance_mode: str = "midcourse_pn_3d",
    first_guidance_present: bool = True,
) -> tuple[RuntimePlanOutcomeJoinInputs, dict[str, Path]]:
    root.mkdir(parents=True, exist_ok=True)
    episode_id = "episode-runtime-outcome-join"
    d1_row = _envelope(
        1,
        "modules.d1.fused_tracks",
        "D1",
        0.8,
        "d1-scalable3d-fusion-v1",
        {"timestamp": 0.8, "tracks": [], "observation_lineage": []},
    )
    d2_row = _envelope(
        2,
        "modules.d2.associated_tracks",
        "D2",
        0.8,
        "d2-scalable3d-association-v1",
        {"timestamp": 0.8, "tracks": [], "identity_lineage": []},
    )
    plan1 = _plan(1, "GT-0001", 1.0)
    guidance1 = (
        _guidance(1, "GT-0001", 1.0, mode=first_guidance_mode)
        if first_guidance_present
        else None
    )
    plan2 = _plan(2, "GT-0002", 2.0)
    guidance2 = _guidance(2, "GT-0002", 2.0)
    rows = [
        d1_row,
        d2_row,
        _envelope(3, "modules.d3.assignment_plan", "D3", 1.0, "assignment_plan_v2", plan1),
    ]
    if guidance1 is not None:
        rows.append(
            _envelope(
                4,
                "modules.d7.guidance_commands",
                "D7",
                1.0,
                "d7-scalable3d-guidance-v1",
                guidance1,
            )
        )
    rows.append(
        _ack(
            plan1,
            guidance1,
            sequence=5,
            plan_sequence=3,
            guidance_sequence=4 if guidance1 is not None else None,
        )
    )
    rows.extend(
        [
            _envelope(6, "modules.d1.fused_tracks", "D1", 1.8, "d1-scalable3d-fusion-v1", {"timestamp": 1.8, "tracks": [], "observation_lineage": []}),
            _envelope(7, "modules.d2.associated_tracks", "D2", 1.8, "d2-scalable3d-association-v1", {"timestamp": 1.8, "tracks": [], "identity_lineage": []}),
            _envelope(8, "modules.d3.assignment_plan", "D3", 2.0, "assignment_plan_v2", plan2),
            _envelope(9, "modules.d7.guidance_commands", "D7", 2.0, "d7-scalable3d-guidance-v1", guidance2),
            _ack(plan2, guidance2, sequence=10, plan_sequence=8, guidance_sequence=9),
        ]
    )
    online_path = root / "online_observations.jsonl"
    _write_jsonl(online_path, rows)

    d1_source_path = root / "online_d1_records.jsonl"
    d2_source_path = root / "online_d2_records.jsonl"
    _write_jsonl(d1_source_path, [d1_row, rows[-5]])
    _write_jsonl(d2_source_path, [d2_row, rows[-4]])
    truth_labels_path = root / "observation_truth_labels.jsonl"
    evidence_path = root / "identity_evidence.json"
    _write_jsonl(
        truth_labels_path,
        [
            {
                "schema_version": "d2.scalable3d_observation_truth.v1",
                "observation_id": "OBS-GT-0001",
                "truth_target_id": "TGT-0001",
                "measurement_timestamp": 0.8,
            },
            {
                "schema_version": "d2.scalable3d_observation_truth.v1",
                "observation_id": "OBS-GT-0002",
                "truth_target_id": "TGT-0002",
                "measurement_timestamp": 0.8,
            },
        ],
    )
    _write_json(evidence_path, {"episode_id": episode_id, "records": []})
    identity_path = root / "identity_evaluation.json"
    source_hashes = {
        "online_d1_records": _file_hash(d1_source_path),
        "online_d2_records": _file_hash(d2_source_path),
        "observation_truth_labels": _file_hash(truth_labels_path),
        "identity_evidence_bundle": _file_hash(evidence_path),
    }
    identity = {
        "schema_version": "d2.scalable3d_identity_evaluation.v1",
        "policy_version": "d2.scalable3d_identity_policy.v1",
        "hash_algorithm": "sha256",
        "episode_id": episode_id,
        "source_hashes": source_hashes,
        "configuration": {
            "lineage_time_window_s": 1.0,
            "timestamp_tolerance_s": 1.0e-9,
        },
        "frames": [
            _identity_frame(0, 0.8),
            _identity_frame(1, 1.8),
            _identity_frame(2, 2.8),
        ],
        "metrics": {"truth_metrics_available": True},
        "audit": {
            "online_truth_isolation_verified": True,
            "source_record_semantics_verified": True,
            "source_verification": "raw_source_hashes_and_record_sequences_verified",
            "identity_heuristics_used": False,
            "identity_sources_allowed": ["source_observation_lineage"],
            "identity_sources_forbidden": [
                "target_name",
                "actor_id",
                "terminal_proximity",
                "nearest_distance",
            ],
        },
    }
    _write_json(identity_path, identity)
    identity_manifest_path = root / "identity_manifest.json"
    _write_json(
        identity_manifest_path,
        {
            "schema_version": "scalable3d-offline-identity-evaluation-manifest-v1",
            "available": True,
            "reason": None,
            "episode_id": episode_id,
            "online_truth_isolation_verified": True,
            "identity_metrics_available": True,
            "source_hashes": {
                "identity_evaluation": _file_hash(identity_path),
                "identity_evidence": _file_hash(evidence_path),
                "observation_truth_labels": _file_hash(truth_labels_path),
                "online_d1_records": _file_hash(d1_source_path),
                "online_d2_records": _file_hash(d2_source_path),
            },
        },
    )

    config = {
        "schema_version": "scalable3d-scenario-v1",
        "scenario_name": "runtime_outcome_test",
        "scenario_version": "runtime-outcome-test-v1",
        "seed": 17,
        "target_count": 2,
        "resource_count": 1,
        "recon_count": 0,
        "duration_s": 3.0,
        "physics_dt_s": 0.5,
        "intercept_radius_m": 5.0,
    }
    config_path = root / "scenario_config.json"
    _write_json(config_path, config)
    manifest_path = root / "episode_manifest.json"
    _write_json(
        manifest_path,
        {
            "episode_id": episode_id,
            "config_sha256": _canonical_hash(config),
            "scenario_name": config["scenario_name"],
            "scenario_version": config["scenario_version"],
            "seed": config["seed"],
            "world_schema": "scalable3d-world-v1",
            "bus_schema": "scalable3d-episode-bus-v1",
            "offline_truth_schema": "scalable3d-offline-truth-v1",
        },
    )

    timestamps = np.asarray([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    intruder_state = np.zeros((timestamps.size, 2, 6), dtype=float)
    intruder_state[:, 1, 0] = 20.0
    interceptor_state = np.zeros((timestamps.size, 1, 6), dtype=float)
    interceptor_state[:, 0, 0] = [15.0, 12.0, 10.0, 4.0, 4.0, 8.0, 12.0]
    intruder_active = np.ones((timestamps.size, 2), dtype=bool)
    intruder_active[3:, 0] = False
    truth_state_path = root / "offline_truth_state.npz"
    np.savez_compressed(
        truth_state_path,
        timestamps=timestamps,
        intruder_state=intruder_state,
        intruder_ids=np.asarray(["TGT-0001", "TGT-0002"], dtype="U"),
        interceptor_state=interceptor_state,
        intruder_active=intruder_active,
    )
    proximity_path = root / "offline_proximity_intercepts.jsonl"
    _write_jsonl(
        proximity_path,
        [
            {
                "timestamp": 1.5,
                "resource_index": 0,
                "target_index": 0,
                "resource_id": "INT-0001",
                "truth_target_id": "TGT-0001",
                "distance_m": 4.0,
            }
        ],
    )
    paths = {
        "online_observations": online_path,
        "d2_identity_evaluation": identity_path,
        "d2_identity_manifest": identity_manifest_path,
        "d2_online_d1_records": d1_source_path,
        "d2_online_d2_records": d2_source_path,
        "d2_observation_truth_labels": truth_labels_path,
        "d2_identity_evidence": evidence_path,
        "offline_truth_state": truth_state_path,
        "offline_proximity_intercepts": proximity_path,
        "episode_manifest": manifest_path,
        "scenario_config": config_path,
    }
    inputs = RuntimePlanOutcomeJoinInputs(
        **{name: HashedArtifact(path, _file_hash(path)) for name, path in paths.items()}
    )
    return inputs, paths


def _refresh(
    inputs: RuntimePlanOutcomeJoinInputs,
    name: str,
) -> RuntimePlanOutcomeJoinInputs:
    path = getattr(inputs, name).path
    return replace(inputs, **{name: HashedArtifact(path, _file_hash(path))})


def _rewrite_online(
    inputs: RuntimePlanOutcomeJoinInputs,
    mutate,
) -> RuntimePlanOutcomeJoinInputs:
    path = inputs.online_observations.path
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    mutate(rows)
    _write_jsonl(path, rows)
    return _refresh(inputs, "online_observations")


def _refresh_identity_manifest(
    inputs: RuntimePlanOutcomeJoinInputs,
) -> RuntimePlanOutcomeJoinInputs:
    manifest_path = inputs.d2_identity_manifest.path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_hashes"]["identity_evaluation"] = _file_hash(
        inputs.d2_identity_evaluation.path
    )
    _write_json(manifest_path, manifest)
    inputs = _refresh(inputs, "d2_identity_evaluation")
    return _refresh(inputs, "d2_identity_manifest")


def _rewrite_d2_truth_as_v2(
    inputs: RuntimePlanOutcomeJoinInputs,
    *,
    include_unknown: bool = False,
) -> RuntimePlanOutcomeJoinInputs:
    truth_path = inputs.d2_observation_truth_labels.path
    rows: list[dict[str, Any]] = [
        {
            "schema_version": "d2.scalable3d_observation_truth.v2",
            "observation_id": "OBS-GT-0001",
            "truth_target_id": "TGT-0001",
            "measurement_timestamp": 0.8,
            "disposition": "target",
        },
        {
            "schema_version": "d2.scalable3d_observation_truth.v2",
            "observation_id": "OBS-GT-0002",
            "truth_target_id": "TGT-0002",
            "measurement_timestamp": 0.8,
            "disposition": "target",
        },
        {
            "schema_version": "d2.scalable3d_observation_truth.v2",
            "observation_id": "OBS-FA",
            "measurement_timestamp": 0.8,
            "disposition": "known_false_alarm",
        },
    ]
    if include_unknown:
        rows.append(
            {
                "schema_version": "d2.scalable3d_observation_truth.v2",
                "observation_id": "OBS-UNKNOWN",
                "measurement_timestamp": 0.8,
                "disposition": "unknown",
            }
        )
    _write_jsonl(truth_path, rows)
    truth_hash = _file_hash(truth_path)

    identity_path = inputs.d2_identity_evaluation.path
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["source_hashes"]["observation_truth_labels"] = truth_hash
    identity["audit"].update(
        {
            "observation_truth_schema_version": (
                "d2.scalable3d_observation_truth.v2"
            ),
            "observation_truth_disposition_counts": {
                "target": 2,
                "known_false_alarm": 1,
                **({"unknown": 1} if include_unknown else {}),
            },
            "known_false_alarm_only_mapping_count": 0,
            "target_with_known_false_alarm_mapping_count": 0,
            "unknown_disposition_mapping_count": 0,
            "identity_metrics_blocking_reasons": (
                ["truth_label_unknown"] if include_unknown else []
            ),
        }
    )
    if include_unknown:
        identity["metrics"].update(
            {
                "truth_metrics_available": False,
                "id_switch_count_available": False,
                "id_switch_count": None,
            }
        )
    _write_json(identity_path, identity)

    manifest_path = inputs.d2_identity_manifest.path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_hashes"]["observation_truth_labels"] = truth_hash
    manifest["source_hashes"]["identity_evaluation"] = _file_hash(identity_path)
    _write_json(manifest_path, manifest)
    inputs = _refresh(inputs, "d2_observation_truth_labels")
    inputs = _refresh(inputs, "d2_identity_evaluation")
    return _refresh(inputs, "d2_identity_manifest")


def _episode_output_inputs(root: Path) -> RuntimePlanOutcomeJoinInputs:
    paths = {
        "online_observations": root / "online_observations.jsonl",
        "d2_identity_evaluation": root / "offline_identity" / "identity_evaluation.json",
        "d2_identity_manifest": root / "offline_identity" / "manifest.json",
        "d2_online_d1_records": root / "offline_identity" / "online_d1_records.jsonl",
        "d2_online_d2_records": root / "offline_identity" / "online_d2_records.jsonl",
        "d2_observation_truth_labels": (
            root / "offline_identity" / "observation_truth_labels.jsonl"
        ),
        "d2_identity_evidence": root / "offline_identity" / "identity_evidence.json",
        "offline_truth_state": root / "offline_truth_state.npz",
        "offline_proximity_intercepts": root / "offline_proximity_intercepts.jsonl",
        "episode_manifest": root / "manifest.json",
        "scenario_config": root / "scenario_config.json",
    }
    return RuntimePlanOutcomeJoinInputs(
        **{name: HashedArtifact(path, _file_hash(path)) for name, path in paths.items()}
    )


def _rewrite_second_plan_as_refresh(
    rows: list[dict[str, Any]],
    *,
    tamper_execution_signature: bool = False,
) -> None:
    refresh_plan = json.loads(json.dumps(rows[2]["payload"]))
    refresh_plan["metadata"]["execution_signature_changed"] = False
    refresh_plan["metadata"]["evaluation_refresh_only"] = True
    refresh_plan["metadata"]["plan_refresh_only"] = False
    if tamper_execution_signature:
        refresh_plan["assignments"][0]["coalition_version"] = 99
    refresh_guidance = _guidance(1, "GT-0001", 2.0)
    rows[7] = _envelope(
        8,
        "modules.d3.assignment_plan",
        "D3",
        2.0,
        "assignment_plan_v2",
        refresh_plan,
    )
    rows[8] = _envelope(
        9,
        "modules.d7.guidance_commands",
        "D7",
        2.0,
        "d7-scalable3d-guidance-v1",
        refresh_guidance,
    )
    rows[9] = _ack(
        refresh_plan,
        refresh_guidance,
        sequence=10,
        plan_sequence=8,
        guidance_sequence=9,
        ack_timestamp=2.0,
    )


def test_normal_join_builds_nonoverlapping_windows_and_keeps_admission_closed(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")

    result = evaluate_runtime_plan_outcomes(inputs)

    assert result["runtime_ack_evidence"]["ack_count"] == 2
    assert result["runtime_ack_evidence"]["binding_count"] == 2
    truth_audit = result["offline_observation_truth_disposition"]
    assert truth_audit["source_schema_version"] == (
        "d2.scalable3d_observation_truth.v1"
    )
    assert truth_audit["target_label"]["count"] == 2
    assert truth_audit["known_false_alarm"]["availability"] == "unavailable"
    assert truth_audit["strict_id_switch_backfilled"] is False
    first, second = result["binding_windows"]
    assert first["window_start_timestamp"] == 1.0
    assert first["window_end_timestamp"] == 2.0
    assert first["window_interval"] == "left_closed_right_open"
    assert first["last_state_timestamp"] == 1.5
    assert second["window_start_timestamp"] == 2.0
    assert second["window_end_timestamp"] == 3.0
    assert second["window_interval"] == "closed"
    assert first["identity_mapping"]["truth_target_id"] == "TGT-0001"
    assert first["start_3d_distance_m"] == 10.0
    assert first["min_3d_distance_m"] == 4.0
    assert first["distance_progress_m"] == 6.0
    assert first["assigned_pair_proximity_event_observed"] is True
    assert first["other_target_proximity_event_observed"] is False
    score = first["bounded_pair_progress_diagnostic"]
    assert score["name"] == RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME
    assert score["available"] is True
    assert score["value"] == 1.0
    assert score["formal_reward"] is False
    assert first["d3_learning_evidence"]["mode"] == "shadow"
    assert first["d4_regional_hint_evidence"]["considered"] is True
    assert result["observed_diagnostics"]["formal_reward_available"] is False
    assert result["observed_diagnostics"]["causal_attribution_available"] is False
    assert result["admission"]["ppo_allowed"] is False
    assert result["admission"]["assist_allowed"] is False
    assert result["admission"]["authority_allowed"] is False

    output = write_runtime_plan_outcome_join_report(inputs, tmp_path / "report")
    assert output["json"].is_file()
    assert "不是 D3 正式强化学习奖励" in output["markdown"].read_text(
        encoding="utf-8"
    )


def test_v2_truth_dispositions_are_hash_bound_and_known_false_alarm_is_excluded(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_d2_truth_as_v2(inputs)

    result = evaluate_runtime_plan_outcomes(inputs)

    audit = result["offline_observation_truth_disposition"]
    assert audit["source_schema_version"] == (
        "d2.scalable3d_observation_truth.v2"
    )
    assert audit["target_label"]["count"] == 2
    assert audit["known_false_alarm"]["count"] == 1
    assert audit["unknown"]["count"] == 0
    assert audit["source_hash_verified"] is True
    assert audit["d2_identity_audit_cross_check"] == (
        "schema_and_disposition_counts_match_hashed_sidecar"
    )
    assert audit["known_false_alarm_exclusion_verified"] is True
    assert audit["strict_id_switch_backfilled"] is False


def test_v2_unknown_disposition_keeps_d2_strict_identity_fail_closed(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_d2_truth_as_v2(inputs, include_unknown=True)

    result = evaluate_runtime_plan_outcomes(inputs)

    audit = result["offline_observation_truth_disposition"]
    assert audit["unknown"]["count"] == 1
    assert audit["strict_identity_eligible"] is False
    assert audit["strict_id_switch_backfilled"] is False


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        (
            {
                "schema_version": "d2.scalable3d_observation_truth.v2",
                "observation_id": "OBS-BAD",
                "measurement_timestamp": 0.8,
            },
            "observation_truth_disposition_missing",
        ),
        (
            {
                "schema_version": "d2.scalable3d_observation_truth.v2",
                "observation_id": "OBS-BAD",
                "measurement_timestamp": 0.8,
                "disposition": "unreviewed",
            },
            "unsupported_observation_truth_disposition",
        ),
    ],
)
def test_runtime_join_rejects_tampered_v2_disposition_sidecar(
    tmp_path: Path,
    mutation: dict[str, Any],
    error_code: str,
) -> None:
    inputs, _ = _make_fixture(tmp_path / error_code)
    truth_path = inputs.d2_observation_truth_labels.path
    _write_jsonl(truth_path, [mutation])
    truth_hash = _file_hash(truth_path)
    identity_path = inputs.d2_identity_evaluation.path
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["source_hashes"]["observation_truth_labels"] = truth_hash
    _write_json(identity_path, identity)
    manifest_path = inputs.d2_identity_manifest.path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_hashes"]["observation_truth_labels"] = truth_hash
    manifest["source_hashes"]["identity_evaluation"] = _file_hash(identity_path)
    _write_json(manifest_path, manifest)
    inputs = _refresh(inputs, "d2_observation_truth_labels")
    inputs = _refresh(inputs, "d2_identity_evaluation")
    inputs = _refresh(inputs, "d2_identity_manifest")

    with pytest.raises(RuntimePlanOutcomeJoinError) as exc:
        evaluate_runtime_plan_outcomes(inputs)

    assert exc.value.code == error_code


def test_candidate_report_matches_pre_streaming_baseline_business_hash(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")

    result = evaluate_runtime_plan_outcomes(inputs)

    assert _report_business_hash(result) == (
        "sha256:7b271562cfb62a4145f7d0e7883b4e14b5ad523b3c4b2ae2d9cb9365f572675f"
    )


def test_truth_injection_in_unretained_topic_still_fails_closed(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")

    def inject(rows: list[dict[str, Any]]) -> None:
        rows.append(
            _envelope(
                11,
                "runtime.camera_command_ack",
                "MAIN-RUNTIME",
                2.5,
                "camera-command-ack-v1",
                {"nested": [{"ground-truth": "TGT-0001"}]},
            )
        )

    inputs = _rewrite_online(inputs, inject)
    online_path = inputs.online_observations.path
    encoded = online_path.read_text(encoding="utf-8").replace(
        '"ground-truth"',
        '"ground\\u002dtruth"',
    )
    online_path.write_text(encoded, encoding="utf-8")
    inputs = _refresh(inputs, "online_observations")

    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)

    assert captured.value.code == "online_truth_field_present"


def test_digest_only_d2_source_link_still_rejects_payload_divergence(
    tmp_path: Path,
) -> None:
    inputs, paths = _make_fixture(tmp_path / "sources")
    d1_path = paths["d2_online_d1_records"]
    rows = [json.loads(line) for line in d1_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["payload"]["timestamp"] = 0.9
    _write_jsonl(d1_path, rows)
    d1_sha256 = _file_hash(d1_path)

    evaluation_path = paths["d2_identity_evaluation"]
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    evaluation["source_hashes"]["online_d1_records"] = d1_sha256
    _write_json(evaluation_path, evaluation)

    manifest_path = paths["d2_identity_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_hashes"]["online_d1_records"] = d1_sha256
    manifest["source_hashes"]["identity_evaluation"] = _file_hash(
        evaluation_path
    )
    _write_json(manifest_path, manifest)

    inputs = _refresh(inputs, "d2_online_d1_records")
    inputs = _refresh(inputs, "d2_identity_evaluation")
    inputs = _refresh(inputs, "d2_identity_manifest")

    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)

    assert captured.value.code == "d2_source_payload_not_in_online_log"


def test_same_identity_evaluation_refresh_creates_a_distinct_occurrence_window(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_online(
        inputs,
        lambda rows: _rewrite_second_plan_as_refresh(rows),
    )

    result = evaluate_runtime_plan_outcomes(inputs)

    runtime = result["runtime_ack_evidence"]
    assert runtime["ack_count"] == 2
    assert runtime["unique_occurrence_count"] == 2
    assert runtime["new_plan_identity_occurrence_count"] == 1
    assert runtime["same_identity_refresh_occurrence_count"] == 1
    first, second = result["binding_windows"]
    assert first["decision_id"] == second["decision_id"] == "PLAN-A:v1"
    assert first["occurrence_id"] != second["occurrence_id"]
    assert first["occurrence_index"] == 1
    assert second["occurrence_index"] == 2
    assert second["adoption_kind"] == "same_identity_evaluation_refresh"
    assert first["execution_signature_sha256"] == second["execution_signature_sha256"]
    assert first["window_end_timestamp"] == second["window_start_timestamp"] == 2.0


def test_real_main_3v3_refresh_episode_joins_every_ack_occurrence(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "integrated_3v3"
    config = ScenarioConfig(
        scenario_name="d6-runtime-outcome-refresh-regression",
        scenario_version="d6-runtime-outcome-refresh-regression-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=70,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    run_episode(
        config,
        module_stack=IntegratedScalableModuleStack(),
        output_dir=output_dir,
    )

    result = evaluate_runtime_plan_outcomes(_episode_output_inputs(output_dir))

    runtime = result["runtime_ack_evidence"]
    assert runtime["ack_count"] == 2
    assert runtime["unique_occurrence_count"] == 2
    assert runtime["new_plan_identity_occurrence_count"] == 1
    assert runtime["same_identity_refresh_occurrence_count"] == 1
    assert runtime["binding_count"] == 6
    windows = result["binding_windows"]
    assert len({item["occurrence_id"] for item in windows}) == 2
    assert {item["occurrence_index"] for item in windows} == {1, 2}
    assert len({item["execution_signature_sha256"] for item in windows}) == 1
    assert result["runtime_ack_evidence"]["online_truth_use_count"] == 0
    assert result["admission"]["ppo_allowed"] is False
    assert result["admission"]["assist_allowed"] is False
    assert result["admission"]["authority_allowed"] is False


def test_input_spec_and_cli_require_hash_verified_explicit_sources(tmp_path: Path) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    spec_path = tmp_path / "inputs.json"
    _write_json(spec_path, inputs.to_dict())
    loaded = load_runtime_plan_outcome_join_inputs(
        spec_path,
        expected_sha256=_file_hash(spec_path),
    )
    assert loaded.resolved() == inputs.resolved()

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_runtime_plan_outcome_join.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--inputs-json",
            str(spec_path),
            "--inputs-sha256",
            _file_hash(spec_path),
            "--output-dir",
            str(tmp_path / "cli-report"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "runtime_plan_outcome_join.json" in completed.stdout


def test_outer_online_hash_tampering_fails_before_join(tmp_path: Path) -> None:
    inputs, paths = _make_fixture(tmp_path / "sources")
    paths["online_observations"].write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == "online_observations_sha256_mismatch"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda rows: rows[4]["payload"].__setitem__(
                "source_plan_payload_sha256", "0" * 64
            ),
            "source_plan_payload_hash_mismatch",
        ),
        (
            lambda rows: rows[4]["payload"].__setitem__(
                "source_plan_bus_sequence", 2
            ),
            "source_plan_sequence_mismatch",
        ),
    ],
)
def test_source_sequence_or_payload_mismatch_fails_closed(
    tmp_path: Path,
    mutation,
    code: str,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_online(inputs, mutation)
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == code


def test_d7_wrong_plan_version_fails_after_guidance_hash_recheck(tmp_path: Path) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")

    def mutate(rows: list[dict[str, Any]]) -> None:
        guidance = rows[3]["payload"]
        guidance["commands"][0]["plan_version"] = 99
        rows[4]["payload"]["source_guidance_payload_sha256"] = _canonical_hash(
            guidance
        )

    inputs = _rewrite_online(inputs, mutate)
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == "d7_wrong_plan_version"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda rows: rows[4].__setitem__("sequence", rows[3]["sequence"]),
            "duplicate_bus_sequence",
        ),
        (
            lambda rows: rows[4]["payload"]["binding_acks"][0].__setitem__(
                "global_track_id", "GT-EXTRA"
            ),
            "extra_or_duplicate_ack_binding",
        ),
    ],
)
def test_duplicate_sequence_and_extra_binding_are_rejected(
    tmp_path: Path,
    mutation,
    code: str,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_online(inputs, mutation)
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == code


def test_same_version_refresh_with_changed_binding_signature_fails_closed(
    tmp_path: Path,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_online(
        inputs,
        lambda rows: _rewrite_second_plan_as_refresh(
            rows,
            tamper_execution_signature=True,
        ),
    )

    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)

    assert captured.value.code == "same_plan_execution_signature_changed"


def test_stale_plan_version_is_rejected(tmp_path: Path) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")

    def mutate(rows: list[dict[str, Any]]) -> None:
        plan = rows[-3]["payload"]
        guidance = rows[-2]["payload"]
        ack = rows[-1]["payload"]
        plan["plan_version"] = 0
        plan["assignments"][0]["coalition_version"] = 0
        guidance["commands"][0]["plan_version"] = 0
        ack["decision_id"] = "PLAN-A:v0"
        ack["plan_version"] = 0
        ack["binding_acks"][0]["coalition_version"] = 0
        ack["source_plan_payload_sha256"] = _canonical_hash(plan)
        ack["source_guidance_payload_sha256"] = _canonical_hash(guidance)

    inputs = _rewrite_online(inputs, mutate)
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == "stale_plan_version"


@pytest.mark.parametrize("mode", ["missing", "ambiguous"])
def test_d2_mapping_missing_or_ambiguous_keeps_score_unavailable(
    tmp_path: Path,
    mode: str,
) -> None:
    inputs, paths = _make_fixture(tmp_path / "sources")
    identity = json.loads(paths["d2_identity_evaluation"].read_text(encoding="utf-8"))
    for frame in identity["frames"]:
        if mode == "missing":
            frame["mappings"] = [
                item for item in frame["mappings"] if item["global_track_id"] != "GT-0001"
            ]
        else:
            item = next(
                item for item in frame["mappings"] if item["global_track_id"] == "GT-0001"
            )
            item["status"] = "ambiguous"
            item["truth_target_id"] = None
            item["reason"] = "multiple_truth_targets_for_global_track"
    _write_json(paths["d2_identity_evaluation"], identity)
    inputs = _refresh_identity_manifest(inputs)

    result = evaluate_runtime_plan_outcomes(inputs)
    first = result["binding_windows"][0]
    assert first["identity_mapping"]["available"] is False
    assert first["start_3d_distance_m"] is None
    assert first["bounded_pair_progress_diagnostic"]["available"] is False
    assert first["formal_d3_ppo_reward"] is None


def test_duplicate_d2_track_mapping_in_one_frame_is_rejected(tmp_path: Path) -> None:
    inputs, paths = _make_fixture(tmp_path / "sources")
    identity = json.loads(paths["d2_identity_evaluation"].read_text(encoding="utf-8"))
    identity["frames"][0]["mappings"].append(
        dict(identity["frames"][0]["mappings"][0])
    )
    _write_json(paths["d2_identity_evaluation"], identity)
    inputs = _refresh_identity_manifest(inputs)

    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == "d2_duplicate_track_mapping_in_frame"


@pytest.mark.parametrize(
    ("artifact", "suffix"),
    [
        ("offline_truth_state", b"truth-tamper"),
        ("offline_proximity_intercepts", b"proximity-tamper"),
    ],
)
def test_truth_state_or_proximity_tampering_is_rejected(
    tmp_path: Path,
    artifact: str,
    suffix: bytes,
) -> None:
    inputs, paths = _make_fixture(tmp_path / "sources")
    with paths[artifact].open("ab") as stream:
        stream.write(suffix)
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == f"{artifact}_sha256_mismatch"


@pytest.mark.parametrize("field", ["physical_outcome_available", "reward_available"])
def test_runtime_ack_cannot_self_report_outcome_or_reward(
    tmp_path: Path,
    field: str,
) -> None:
    inputs, _ = _make_fixture(tmp_path / "sources")
    inputs = _rewrite_online(
        inputs,
        lambda rows: rows[4]["payload"].__setitem__(field, True),
    )
    with pytest.raises(RuntimePlanOutcomeJoinError) as captured:
        evaluate_runtime_plan_outcomes(inputs)
    assert captured.value.code == "ack_self_claims_offline_evidence"


@pytest.mark.parametrize(
    ("mode", "present", "reason"),
    [
        ("hold", True, "d7_binding_held"),
        ("midcourse_pn_3d", False, "d7_binding_not_present"),
    ],
)
def test_hold_or_missing_d7_binding_keeps_score_unavailable(
    tmp_path: Path,
    mode: str,
    present: bool,
    reason: str,
) -> None:
    inputs, _ = _make_fixture(
        tmp_path / "sources",
        first_guidance_mode=mode,
        first_guidance_present=present,
    )
    first = evaluate_runtime_plan_outcomes(inputs)["binding_windows"][0]
    assert first["bounded_pair_progress_diagnostic"] == {
        "name": RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME,
        "available": False,
        "value": None,
        "reason": reason,
        "range": [-1.0, 1.0],
        "formal_reward": False,
        "causal": False,
        "counterfactual": False,
    }


def test_other_target_proximity_does_not_count_as_assigned_pair_outcome(
    tmp_path: Path,
) -> None:
    inputs, paths = _make_fixture(tmp_path / "sources")
    with np.load(paths["offline_truth_state"], allow_pickle=False) as original:
        arrays = {name: original[name] for name in original.files}
    arrays["intruder_state"] = arrays["intruder_state"].copy()
    arrays["intruder_state"][3, 1, 0] = 8.0
    np.savez_compressed(paths["offline_truth_state"], **arrays)
    _write_jsonl(
        paths["offline_proximity_intercepts"],
        [
            {
                "timestamp": 1.5,
                "resource_index": 0,
                "target_index": 1,
                "resource_id": "INT-0001",
                "truth_target_id": "TGT-0002",
                "distance_m": 4.0,
            }
        ],
    )
    inputs = _refresh(inputs, "offline_truth_state")
    inputs = _refresh(inputs, "offline_proximity_intercepts")

    first = evaluate_runtime_plan_outcomes(inputs)["binding_windows"][0]
    assert first["identity_mapping"]["truth_target_id"] == "TGT-0001"
    assert first["assigned_pair_proximity_event_observed"] is False
    assert first["other_target_proximity_event_observed"] is True
    assert first["other_target_proximity_events"][0]["truth_target_id"] == "TGT-0002"
