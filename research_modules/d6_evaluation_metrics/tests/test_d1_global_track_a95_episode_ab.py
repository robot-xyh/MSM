from __future__ import annotations

import copy
import csv
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from d6_evaluation_metrics.d1_global_track_a95_episode_ab import (
    CANDIDATE_IMPLEMENTATION_ID,
    CANDIDATE_SELECTOR,
    D1_GLOBAL_TRACK_A95_PAIR_LIST_SCHEMA_VERSION,
    REFERENCE_IMPLEMENTATION_ID,
    REFERENCE_SELECTOR,
    evaluate_d1_global_track_a95_episode_ab,
    write_d1_global_track_a95_episode_ab_report,
)


SOURCE_COMMIT = "4" * 40


def test_equivalent_pair_passes_and_writes_required_bundle(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    assert result["status"] == "passed"
    assert result["evaluation_passed"] is True
    assert result["formal_promotion_supported"] is False
    assert result["aggregate"]["available_pair_count"] == 1
    assert result["aggregate"]["exact_equivalence_rate"] == 1.0
    assert result["aggregate"]["sample_sufficiency"]["small_sample"] is True
    pair = result["pairs"][0]
    assert pair["exogenous_input_equivalent"] is True
    assert pair["runtime_bus_timing_equivalent"] is True
    assert pair["comparison_disposition"] == (
        "business_and_runtime_timing_equivalent"
    )
    assert pair["business_equivalent"] is True
    assert pair["operation_contract_passed"] is True
    assert pair["reference"]["scalar_a95_count"] == 2
    assert pair["candidate"]["batched_eigvalsh_call_count"] == 1
    assert pair["candidate"]["batched_matrix_count"] == 2
    assert pair["business_surface"]["d1_track_sample_count"] == 1
    assert pair["business_surface"]["d2_track_sample_count"] == 1

    outputs = write_d1_global_track_a95_episode_ab_report(
        result, tmp_path / "report"
    )
    assert set(outputs) == {"pairs_csv", "aggregate_json", "markdown"}
    assert all(path.is_file() for path in outputs.values())
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "小样本描述性证据" in markdown
    assert "module.d1_fusion" in markdown
    assert "正式晋级" in markdown
    rows = list(csv.DictReader(outputs["pairs_csv"].open(encoding="utf-8")))
    assert rows[0]["status"] == "passed"


def test_business_field_drift_is_rejected(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    online_path = pair_root / "candidate" / "online_observations.jsonl"
    records = _read_jsonl(online_path)
    records[1]["payload"]["tracks"][0]["state_ned"][0] += 0.25
    _write_jsonl(online_path, records)

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    pair = result["pairs"][0]
    assert pair["available"] is True
    assert pair["status"] == "failed"
    assert pair["business_equivalent"] is False
    assert pair["checks"]["d1_global_track_business_surface_equal"] is False
    assert "d1_global_track_business_surface_equal" in pair["failure_reasons"]


def test_explicit_comparison_key_mismatch_is_unavailable(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    key = _comparison_key(pair_root / "reference")
    key["seed"] = 78
    pair_list = tmp_path / "pairs.json"
    _write_json(
        pair_list,
        {
            "schema_version": D1_GLOBAL_TRACK_A95_PAIR_LIST_SCHEMA_VERSION,
            "pairs": [
                {
                    "pair_id": "fixture-pair",
                    "comparison_key": key,
                    "reference_episode_dir": "paired/reference",
                    "candidate_episode_dir": "paired/candidate",
                }
            ],
        },
    )

    result = evaluate_d1_global_track_a95_episode_ab(pair_list)

    pair = result["pairs"][0]
    assert pair["available"] is False
    assert pair["business_equivalent"] is None
    assert pair["reference"] is None
    assert pair["failure_reasons"] == ["comparison_key_mismatch"]


def test_explicit_pair_list_accepts_relative_episode_paths(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    pair_list = tmp_path / "pairs.json"
    _write_json(
        pair_list,
        {
            "schema_version": D1_GLOBAL_TRACK_A95_PAIR_LIST_SCHEMA_VERSION,
            "pairs": [
                {
                    "pair_id": "fixture-pair",
                    "comparison_key": _comparison_key(
                        pair_root / "reference"
                    ),
                    "reference_episode_dir": "paired/reference",
                    "candidate_episode_dir": "paired/candidate",
                }
            ],
        },
    )

    result = evaluate_d1_global_track_a95_episode_ab(pair_list)

    assert result["status"] == "passed"
    assert result["pairs"][0]["pair_id"] == "fixture-pair"


def test_missing_required_timing_metric_is_unavailable_not_zero(
    tmp_path: Path,
) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    timing_path = pair_root / "candidate" / "stage_timings.csv"
    rows = list(csv.DictReader(timing_path.open(encoding="utf-8")))
    with timing_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            row for row in rows if row["stage"] != "module.d1_fusion"
        )

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    pair = result["pairs"][0]
    assert pair["available"] is False
    assert pair["candidate"] is None
    assert pair["failure_reasons"] == [
        "required_metric_unavailable:module.d1_fusion"
    ]
    assert result["aggregate"]["candidate_wall_time_mean_s"] is None


def test_candidate_without_batch_call_is_rejected(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    _replace_candidate_operation_counts(
        pair_root / "candidate",
        {
            "global_tracks_call_count": 1,
            "global_track_metadata_materialization_count": 2,
            "track_quality_summary_request_count": 2,
        },
    )

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    pair = result["pairs"][0]
    assert pair["available"] is True
    assert pair["business_equivalent"] is True
    assert pair["operation_contract_passed"] is False
    assert pair["operation_checks"]["candidate_batched_call_exercised"] is False
    assert pair["candidate"]["batched_eigvalsh_call_count"] == 0


def test_runtime_bus_timing_drift_is_separate_from_exogenous_input(
    tmp_path: Path,
) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    for arm in ("reference", "candidate"):
        _append_runtime_transport_records(pair_root / arm)
    candidate_path = pair_root / "candidate" / "online_observations.jsonl"
    candidate = _read_jsonl(candidate_path)
    candidate[-2], candidate[-1] = candidate[-1], candidate[-2]
    candidate[-1]["timestamp"] = 0.37
    candidate[-1]["payload"]["delivery_timestamp_s"] = 0.37
    _write_jsonl(candidate_path, candidate)

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    pair = result["pairs"][0]
    assert pair["status"] == "passed"
    assert pair["exogenous_input_equivalent"] is True
    assert pair["runtime_bus_timing_equivalent"] is False
    assert pair["business_equivalent"] is True
    assert pair["comparison_disposition"] == (
        "business_equivalent_with_runtime_timing_drift"
    )
    assert pair["business_surface"]["runtime_bus_timing_mismatches"]


def test_runtime_timing_drift_with_d1_business_drift_is_rejected(
    tmp_path: Path,
) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    for arm in ("reference", "candidate"):
        _append_runtime_transport_records(pair_root / arm)
    candidate_path = pair_root / "candidate" / "online_observations.jsonl"
    candidate = _read_jsonl(candidate_path)
    candidate[-1]["timestamp"] = 0.39
    candidate[-1]["payload"]["delivery_timestamp_s"] = 0.39
    candidate[1]["payload"]["tracks"][0]["state_ned"][0] += 0.5
    _write_jsonl(candidate_path, candidate)

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    pair = result["pairs"][0]
    assert pair["status"] == "failed"
    assert pair["exogenous_input_equivalent"] is True
    assert pair["runtime_bus_timing_equivalent"] is False
    assert pair["business_equivalent"] is False
    assert pair["comparison_disposition"] == (
        "runtime_timing_induced_business_divergence"
    )
    assert "runtime_timing_induced_business_divergence" in pair[
        "failure_reasons"
    ]
    assert pair["business_surface"]["d1_business_mismatches"]


def test_exogenous_sensor_drift_is_incomparable(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    candidate_path = pair_root / "candidate" / "online_observations.jsonl"
    candidate = _read_jsonl(candidate_path)
    candidate[0]["payload"]["measurements"][0]["measurement"][0] += 1.0
    _write_jsonl(candidate_path, candidate)

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    pair = result["pairs"][0]
    assert pair["status"] == "incomparable"
    assert pair["available"] is False
    assert pair["exogenous_input_equivalent"] is False
    assert pair["business_equivalent"] is None
    assert pair["comparison_disposition"] == (
        "incomparable_exogenous_input_mismatch"
    )


def test_discovers_arm_grouped_seed_directories(tmp_path: Path) -> None:
    root = tmp_path / "arm-grouped"
    _write_episode(root / "reference" / "seed_77", arm="reference")
    _write_episode(root / "candidate" / "seed_77", arm="candidate")

    result = evaluate_d1_global_track_a95_episode_ab(root)

    assert result["status"] == "passed"
    assert result["aggregate"]["pair_count"] == 1
    assert result["pairs"][0]["pair_id"] == "seed_77"


def test_arm_grouped_seed_set_mismatch_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "arm-grouped"
    _write_episode(root / "reference" / "seed_77", arm="reference")
    _write_episode(root / "reference" / "seed_78", arm="reference")
    _write_episode(root / "candidate" / "seed_77", arm="candidate")

    result = evaluate_d1_global_track_a95_episode_ab(root)

    assert result["status"] == "unavailable"
    assert result["pairs"] == []
    assert result["availability"]["reasons"][0].startswith(
        "reference_candidate_seed_directory_set_mismatch:"
    )


def test_runtime_profile_hash_mismatch_is_unavailable(tmp_path: Path) -> None:
    pair_root = _write_pair(tmp_path / "paired")
    manifest_path = pair_root / "candidate" / "manifest.json"
    manifest = _read_json(manifest_path)
    manifest["runtime_profile_sha256"] = "0" * 64
    _write_json(manifest_path, manifest)

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    assert result["pairs"][0]["available"] is False
    assert result["pairs"][0]["failure_reasons"] == [
        "runtime_profile_sha256_mismatch"
    ]


def test_reserved_seed_stops_before_episode_payload_read(tmp_path: Path) -> None:
    pair_root = tmp_path / "paired"
    for arm in ("reference", "candidate"):
        arm_dir = pair_root / arm
        arm_dir.mkdir(parents=True)
        _write_json(arm_dir / "manifest.json", {"seed": 1000})
        # These sentinels are intentionally not valid episode payloads. The
        # preflight guard must reject before attempting to parse them.
        (arm_dir / "summary.json").write_text("not-json", encoding="utf-8")

    result = evaluate_d1_global_track_a95_episode_ab(pair_root)

    assert result["pairs"][0]["failure_reasons"] == [
        "reserved_formal_seed_payload_read_forbidden"
    ]
    assert result["reserved_formal_seed_payload_read"] is False
    assert result["formal_shards_10_19_run"] is False


def _write_pair(root: Path) -> Path:
    _write_episode(root / "reference", arm="reference")
    _write_episode(root / "candidate", arm="candidate")
    return root


def _write_episode(root: Path, *, arm: str) -> None:
    root.mkdir(parents=True)
    candidate = arm == "candidate"
    selector = CANDIDATE_SELECTOR if candidate else REFERENCE_SELECTOR
    implementation_id = (
        CANDIDATE_IMPLEMENTATION_ID
        if candidate
        else REFERENCE_IMPLEMENTATION_ID
    )
    scenario = {
        "scenario_name": "a95_complete_3d_fixture",
        "scenario_version": "a95-complete-3d-fixture-v1",
        "seed": 77,
        "target_count": 2,
        "resource_count": 2,
        "recon_count": 1,
        "duration_s": 1.0,
    }
    execution = {
        "schema_version": "d1.global_track_materialization_diagnostics.v1",
        "selector": selector,
        "implementation_id": implementation_id,
        "candidate_enabled": candidate,
        "candidate_scope": "same_publication_frame_position_covariance_a95",
        "default_enabled": False,
        "truth_dependent_inputs_allowed": False,
    }
    profile_diagnostics = {
        "schema_version": "d1.global_track_materialization_diagnostics.v1",
        "global_track_materialization_implementation_id": implementation_id,
        "batched_global_track_a95_summary": candidate,
        "operation_counts": {},
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "configuration": {
            "d1_global_track_materialization_implementation": selector,
            "unchanged_setting": "same",
        },
        "d1_global_track_materialization_execution_config": execution,
        "d1_global_track_materialization_diagnostics": profile_diagnostics,
        "other_selector": "unchanged",
    }
    operation_counts = {
        "global_tracks_call_count": 1,
        "global_track_metadata_materialization_count": 2,
        "track_quality_summary_request_count": 2,
    }
    if candidate:
        operation_counts.update(
            {
                "batched_a95_summary_build_count": 1,
                "batched_a95_summary_matrix_count": 2,
                "batched_a95_eigvalsh_call_count": 1,
                "batched_a95_summary_reuse_count": 2,
            }
        )
    else:
        operation_counts["per_track_a95_summary_call_count"] = 2
    final_diagnostics = {
        "schema_version": "d1.global_track_materialization_diagnostics.v1",
        "implementation_id": "d1.publication_metadata.immutable_shared_audit.v1",
        "global_track_materialization_implementation_id": implementation_id,
        "batched_global_track_a95_summary": candidate,
        "publication_audit_contract_version": "d1.publication_audit_tree.v2",
        "immutable_shared_publication_metadata": True,
        "operation_counts": operation_counts,
    }
    stage_mapping = {
        "d1_fusion": {
            "call_count": 1,
            "wall_time_s": 0.20 if candidate else 0.25,
            "mean_wall_time_ms": 200.0 if candidate else 250.0,
            "p50_wall_time_ms": 200.0 if candidate else 250.0,
            "p95_wall_time_ms": 200.0 if candidate else 250.0,
            "max_wall_time_ms": 200.0 if candidate else 250.0,
        }
    }
    module_final = {
        "d1_track_count": 1,
        "d2_track_count": 1,
        "d3_assignment_count": 0,
        "d5_binding_count": 0,
        "d7_command_count": 0,
        "stage_timings": stage_mapping,
        "d1_global_track_materialization_implementation": selector,
        "d1_global_track_materialization_execution_config": execution,
        "d1_global_track_materialization_diagnostics": final_diagnostics,
    }
    summary = {
        "episode_id": f"a95-fixture-{arm}",
        "scenario_name": scenario["scenario_name"],
        "scenario_version": scenario["scenario_version"],
        "seed": scenario["seed"],
        "target_count": scenario["target_count"],
        "resource_count": scenario["resource_count"],
        "recon_count": scenario["recon_count"],
        "simulated_duration_s": 1.0,
        "physics_step_count": 20,
        "finite_state": True,
        "online_truth_use_count": 0,
        "online_observation_count": 1,
        "online_batch_count": 1,
        "radar_observation_count": 1,
        "acoustic_observation_count": 0,
        "visual_observation_count": 0,
        "module_publication_count": 2,
        "module_publication_topic_counts": {
            "modules.d1.fused_tracks": 1,
            "modules.d2.associated_tracks": 1,
        },
        "assignment_plan_ack_count": 0,
        "assignment_plan_binding_ack_count": 0,
        "assignment_plan_control_applied_count": 0,
        "assignment_plan_hold_count": 0,
        "camera_command_ack_count": 0,
        "camera_command_applied_count": 0,
        "camera_command_issued_count": 0,
        "camera_command_rejected_count": 0,
        "camera_command_rejection_reason_counts": {},
        "intercepted_target_count": 0,
        "wall_time_s": 0.80 if candidate else 1.00,
        "real_time_factor": 1.25 if candidate else 1.00,
        "d1_global_track_materialization_implementation": selector,
        "d1_global_track_materialization_execution_config": execution,
        "d1_global_track_materialization_diagnostics": final_diagnostics,
        "module_final_diagnostics": module_final,
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "d1_global_track_materialization_implementation": selector,
        "d1_global_track_materialization_execution_config": execution,
        "d1_global_track_materialization_diagnostics": final_diagnostics,
        "unchanged_governance": True,
    }
    manifest = {
        "episode_id": f"a95-fixture-{arm}",
        "git_commit": SOURCE_COMMIT,
        "repository_dirty": False,
        "config_sha256": _canonical_sha256(scenario),
        "scenario_name": scenario["scenario_name"],
        "scenario_version": scenario["scenario_version"],
        "seed": scenario["seed"],
        "world_schema": "scalable3d-world-v1",
        "bus_schema": "scalable3d-episode-bus-v1",
        "scenario_schema": "scalable3d-scenario-v1",
        "online_observation_schema": "scalable3d-observation-v1",
        "offline_truth_schema": "scalable3d-offline-truth-v2",
        "d1_model_version": "same-d1",
        "d2_model_version": "same-d2",
        "d3_policy_version": "same-d3",
        "d4_policy_version": "same-d4",
        "d5_model_version": "same-d5",
        "d5_active_vision_policy_version": "same-d5-active",
        "d7_model_version": "same-d7",
        "threshold_version": "same-thresholds",
        "runtime_profile_schema": runtime_profile["schema_version"],
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
        "runtime_profile": runtime_profile,
    }
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "scenario_config.json", scenario)
    _write_json(root / "summary.json", summary)
    _write_json(root / "observation_governance_audit.json", governance)
    _write_stage_timings(root / "stage_timings.csv", candidate=candidate)
    _write_jsonl(root / "online_observations.jsonl", _online_records())
    np.savez_compressed(
        root / "offline_truth_state.npz",
        timestamps=np.asarray([0.0, 1.0]),
        intruder_state=np.asarray(
            [[[100.0, 0.0, -50.0, 1.0, 0.0, 0.0]], [[101.0, 0.0, -50.0, 1.0, 0.0, 0.0]]]
        ),
        intruder_ids=np.asarray(["TGT-0001"]),
    )
    _write_jsonl(
        root / "offline_truth_labels.jsonl",
        [
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "obs-0001",
                "measurement_timestamp": 0.1,
                "truth_entity_id": "TGT-0001",
                "disposition": "target",
            }
        ],
    )
    (root / "offline_proximity_intercepts.jsonl").write_text(
        "", encoding="utf-8"
    )


def _online_records() -> list[dict[str, object]]:
    covariance = np.diag([4.0, 9.0, 16.0, 1.0, 1.0, 1.0]).tolist()
    track = {
        "global_track_id": "GT3D-000001",
        "timestamp": 0.1,
        "state_ned": [100.0, 5.0, -50.0, 1.0, 0.0, 0.0],
        "covariance": covariance,
        "track_state": "stable_track",
    }
    return [
        {
            "sequence": 1,
            "topic": "sensor.observations",
            "source": "RADAR-01",
            "timestamp": 0.2,
            "schema_version": "scalable3d-observation-v1",
            "payload": {
                "batch_id": "batch-0001",
                "sensor_id": "RADAR-01",
                "measurement_timestamp": 0.1,
                "arrival_timestamp": 0.2,
                "measurements": [
                    {
                        "observation_id": "obs-0001",
                        "sensor_id": "RADAR-01",
                        "measurement_timestamp": 0.1,
                        "arrival_timestamp": 0.2,
                        "measurement": [100.0, 5.0, -50.0],
                        "covariance": [[4.0, 0.0], [0.0, 9.0]],
                    }
                ],
            },
        },
        {
            "sequence": 2,
            "topic": "modules.d1.fused_tracks",
            "source": "D1",
            "timestamp": 0.2,
            "schema_version": "d1-scalable3d-fusion-v1",
            "payload": {
                "timestamp": 0.2,
                "batch_id": "batch-0001",
                "sensor_id": "RADAR-01",
                "track_count": 1,
                "current_track_count": 1,
                "tracks_materialized": True,
                "posterior_generation": 1,
                "snapshot_kind": "full_posterior",
                "tracks": [copy.deepcopy(track)],
                "summary": {"association_innovation_solve_count": 1},
                "observation_lineage": [
                    {
                        "observation_id": "obs-0001",
                        "measurement_timestamp": 0.1,
                        "source_lineage": ["RADAR-01", "obs-0001"],
                        "replay_generation": 0,
                    }
                ],
                "structural_ambiguity_evidence_count": 0,
                "structural_ambiguity_evidence": [],
            },
        },
        {
            "sequence": 3,
            "topic": "modules.d2.associated_tracks",
            "source": "D2",
            "timestamp": 0.2,
            "schema_version": "d2-scalable3d-association-v1",
            "payload": {
                "timestamp": 0.2,
                "source_d1_posterior_generation": 1,
                "track_count": 1,
                "tracks": [copy.deepcopy(track)],
                "id_switch_count": None,
                "id_switch_count_available": False,
                "identity_lineage": [
                    {
                        "global_track_id": "GT3D-000001",
                        "source_observations": [
                            {
                                "observation_id": "obs-0001",
                                "measurement_timestamp": 0.1,
                            }
                        ],
                    }
                ],
                "identity_lineage_policy": "fixture-lineage-v1",
                "association": {
                    "timestamp": 0.1,
                    "associator_type": "gnn_hungarian",
                    "matched_pairs": [],
                    "unmatched_track_ids": [],
                    "unmatched_detection_ids": [],
                    "ambiguity_score": 0.0,
                    "rejected_pair_count": 0,
                },
            },
        },
    ]


def _write_stage_timings(path: Path, *, candidate: bool) -> None:
    fields = [
        "schema_version",
        "stage",
        "call_count",
        "wall_time_s",
        "mean_wall_time_ms",
        "p50_wall_time_ms",
        "p95_wall_time_ms",
        "max_wall_time_ms",
        "distribution_available",
        "distribution_unavailable_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "schema_version": "scalable3d-stage-timings-v2",
                "stage": "module.d1_fusion",
                "call_count": 1,
                "wall_time_s": 0.20 if candidate else 0.25,
                "mean_wall_time_ms": 200.0 if candidate else 250.0,
                "p50_wall_time_ms": 200.0 if candidate else 250.0,
                "p95_wall_time_ms": 200.0 if candidate else 250.0,
                "max_wall_time_ms": 200.0 if candidate else 250.0,
                "distribution_available": "true",
                "distribution_unavailable_reason": "",
            }
        )


def _append_runtime_transport_records(root: Path) -> None:
    path = root / "online_observations.jsonl"
    records = _read_jsonl(path)
    records.extend(
        [
            {
                "sequence": 4,
                "topic": "d4.regional_plan_broadcast.v1",
                "source": "D4",
                "timestamp": 0.30,
                "schema_version": "d4-runtime-transport-fixture-v1",
                "payload": {
                    "message_id": "d4-message-0001",
                    "delivery_timestamp_s": 0.30,
                    "plan_payload_sha256": "1" * 64,
                },
            },
            {
                "sequence": 5,
                "topic": "d4.regional_plan_broadcast.v1",
                "source": "D4",
                "timestamp": 0.31,
                "schema_version": "d4-runtime-transport-fixture-v1",
                "payload": {
                    "message_id": "d4-message-0002",
                    "delivery_timestamp_s": 0.31,
                    "plan_payload_sha256": "2" * 64,
                },
            },
        ]
    )
    _write_jsonl(path, records)


def _replace_candidate_operation_counts(root: Path, counts: dict[str, int]) -> None:
    summary_path = root / "summary.json"
    summary = _read_json(summary_path)
    summary["d1_global_track_materialization_diagnostics"][
        "operation_counts"
    ] = copy.deepcopy(counts)
    summary["module_final_diagnostics"][
        "d1_global_track_materialization_diagnostics"
    ]["operation_counts"] = copy.deepcopy(counts)
    _write_json(summary_path, summary)
    governance_path = root / "observation_governance_audit.json"
    governance = _read_json(governance_path)
    governance["d1_global_track_materialization_diagnostics"][
        "operation_counts"
    ] = copy.deepcopy(counts)
    _write_json(governance_path, governance)


def _comparison_key(root: Path) -> dict[str, object]:
    scenario = _read_json(root / "scenario_config.json")
    manifest = _read_json(root / "manifest.json")
    return {
        "scenario_name": scenario["scenario_name"],
        "scenario_version": scenario["scenario_version"],
        "seed": scenario["seed"],
        "target_count": scenario["target_count"],
        "resource_count": scenario["resource_count"],
        "recon_count": scenario["recon_count"],
        "duration_s": scenario["duration_s"],
        "config_sha256": manifest["config_sha256"],
    }


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
