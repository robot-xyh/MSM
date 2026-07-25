from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from d6_evaluation_metrics.d1_replay_prefix_summary_multiseed import (
    CANDIDATE_IMPLEMENTATION,
    CANDIDATE_IMPLEMENTATION_ID,
    D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION,
    D1_REPLAY_PREFIX_SUMMARY_EVIDENCE_SCHEMA_VERSION,
    D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION,
    D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID,
    D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256,
    D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT,
    REFERENCE_IMPLEMENTATION,
    REFERENCE_IMPLEMENTATION_ID,
    evaluate_d1_replay_prefix_summary_multiseed,
    main,
    write_d1_replay_prefix_summary_multiseed_report,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_replay_prefix_summary_multiseed_v1.json"
)
SELECTOR = "d1_replay_prefix_summary_implementation"
EXECUTION = "d1_replay_prefix_summary_execution_config"
DIAGNOSTICS = "d1_replay_prefix_summary_diagnostics"
STAGE_FIELDS = (
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
)


def test_accepts_frozen_13_pair_matrix_and_all_gates(
    tmp_path: Path,
) -> None:
    manifest = _build_evidence(tmp_path)

    result = evaluate_d1_replay_prefix_summary_multiseed(manifest)

    assert result["schema_version"] == (
        D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["availability"]["available"] is True
    assert result["input_contract"]["source_commit"] == (
        D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256
    )
    assert result["input_contract"]["fresh_arm_count"] == 26
    assert result["input_contract"]["reused_arm_count"] == 0
    assert result["input_contract"]["failed_arm_count"] == 0
    assert len(result["pairs"]) == 13
    assert all(
        gate["passed"] for gate in result["admission_gates"].values()
    )
    assert result["verdict"] == "admit"
    assert result["main_default_promotion_allowed"] is True
    aggregate = result[
        "replay_prefix_summary_diagnostics_aggregate"
    ]["groups"]["all"]
    assert aggregate["candidate_lazy_materialization_reduction_pct"] == 40.0
    assert aggregate[
        "candidate_online_snapshot_projected_record_count"
    ] == 13 * 700
    assert aggregate[
        "projection_count_is_not_treated_as_eliminated_work"
    ] is True


def test_digest_and_existing_operation_mismatch_reject(
    tmp_path: Path,
) -> None:
    digest_manifest = _build_evidence(tmp_path / "digest")
    candidate = _episode(
        digest_manifest, "short_seed_1151", "candidate"
    )
    evidence_path = (
        candidate / "offline_consistency" / "online_evidence.json"
    )
    evidence = _read_json(evidence_path)
    evidence["records"][0]["replay_count"] = 9
    _refresh_evidence_digests(evidence)
    _write_json(evidence_path, evidence)

    digest_result = evaluate_d1_replay_prefix_summary_multiseed(
        digest_manifest
    )
    assert digest_result["availability"]["available"] is True
    assert digest_result["verdict"] == "reject"
    assert not digest_result["admission_gates"][
        "all_pairs_consistency_evidence_records_digest_equal"
    ]["passed"]

    operation_manifest = _build_evidence(tmp_path / "operation")
    summary_path = (
        _episode(
            operation_manifest, "short_seed_1151", "candidate"
        )
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["module_final_diagnostics"]["d1_fusion_performance"][
        "checkpoint_state_query_count"
    ] += 1
    _write_json(summary_path, summary)

    operation_result = evaluate_d1_replay_prefix_summary_multiseed(
        operation_manifest
    )
    assert operation_result["availability"]["available"] is True
    assert operation_result["verdict"] == "reject"
    assert not operation_result["admission_gates"][
        "all_pairs_existing_operation_counts_equal"
    ]["passed"]


def test_pending_and_append_materialization_fail_closed(
    tmp_path: Path,
) -> None:
    pending_manifest = _build_evidence(tmp_path / "pending")
    _mutate_candidate_diagnostics(
        pending_manifest,
        "short_seed_1151",
        lambda diagnostics, phase: diagnostics.__setitem__(
            "pending_consistency_ledger_count",
            1 if phase == "exported" else diagnostics[
                "pending_consistency_ledger_count"
            ],
        ),
    )
    pending_result = evaluate_d1_replay_prefix_summary_multiseed(
        pending_manifest
    )
    assert pending_result["availability"]["available"] is False
    assert pending_result["verdict"] == "reject"
    assert "pending" in pending_result["availability"]["reason"]

    append_manifest = _build_evidence(tmp_path / "append")

    def append_materialization(
        diagnostics: dict[str, Any], phase: str
    ) -> None:
        diagnostics["materialization_reasons"][
            "checkpoint_suffix_appended"
        ] = 1
        diagnostics["operation_counts"][
            "lazy_consistency_materialization_count"
        ] += 1

    _mutate_candidate_diagnostics(
        append_manifest, "short_seed_1151", append_materialization
    )
    append_result = evaluate_d1_replay_prefix_summary_multiseed(
        append_manifest
    )
    assert append_result["availability"]["available"] is False
    assert "append materialized" in append_result["availability"]["reason"]


def test_compression_and_performance_gates_reject(
    tmp_path: Path,
) -> None:
    compression_manifest = _build_evidence(
        tmp_path / "compression",
        candidate_materialized_records=900,
    )
    compression = evaluate_d1_replay_prefix_summary_multiseed(
        compression_manifest
    )
    assert compression["availability"]["available"] is True
    assert compression["verdict"] == "reject"
    gate = compression["admission_gates"][
        "minimum_candidate_lazy_materialization_reduction_pct"
    ]
    assert gate["actual"] == 10.0
    assert gate["passed"] is False

    performance_manifest = _build_evidence(
        tmp_path / "performance",
        candidate_d1_fusion_wall_s=1.02,
    )
    performance = evaluate_d1_replay_prefix_summary_multiseed(
        performance_manifest
    )
    assert performance["availability"]["available"] is True
    assert performance["verdict"] == "reject"
    assert not performance["admission_gates"][
        "short_minimum_candidate_faster_count"
    ]["passed"]
    assert not performance["admission_gates"][
        "short_bootstrap_relative_change_upper_bound_pct"
    ]["passed"]


def test_missing_dirty_schema_and_matrix_sha_fail_closed(
    tmp_path: Path,
) -> None:
    missing_manifest = _build_evidence(tmp_path / "missing")
    (
        _episode(missing_manifest, "short_seed_1151", "reference")
        / "stage_timings.csv"
    ).unlink()
    assert evaluate_d1_replay_prefix_summary_multiseed(
        missing_manifest
    )["availability"]["available"] is False

    dirty_manifest = _build_evidence(tmp_path / "dirty")
    episode_manifest_path = (
        _episode(dirty_manifest, "short_seed_1151", "reference")
        / "manifest.json"
    )
    episode_manifest = _read_json(episode_manifest_path)
    episode_manifest["repository_dirty"] = True
    _write_json(episode_manifest_path, episode_manifest)
    dirty = evaluate_d1_replay_prefix_summary_multiseed(dirty_manifest)
    assert dirty["availability"]["available"] is False
    assert "dirty" in dirty["availability"]["reason"]

    schema_manifest = _build_evidence(tmp_path / "schema")
    value = _read_json(schema_manifest)
    value["schema_version"] = "wrong"
    _write_json(schema_manifest, value)
    assert evaluate_d1_replay_prefix_summary_multiseed(
        schema_manifest
    )["availability"]["available"] is False

    sha_manifest = _build_evidence(tmp_path / "sha")
    value = _read_json(sha_manifest)
    value["matrix_sha256"] = "0" * 64
    _write_json(sha_manifest, value)
    assert evaluate_d1_replay_prefix_summary_multiseed(
        sha_manifest
    )["availability"]["available"] is False


def test_repeat_evaluation_and_report_are_deterministic_read_only(
    tmp_path: Path,
) -> None:
    manifest = _build_evidence(tmp_path)
    before = _tree_fingerprint(manifest.parent)
    first = evaluate_d1_replay_prefix_summary_multiseed(manifest)
    second = evaluate_d1_replay_prefix_summary_multiseed(manifest)
    assert first == second
    assert _tree_fingerprint(manifest.parent) == before

    first_paths = write_d1_replay_prefix_summary_multiseed_report(
        first, tmp_path / "report_1"
    )
    second_paths = write_d1_replay_prefix_summary_multiseed_report(
        second, tmp_path / "report_2"
    )
    assert set(first_paths) == {
        "evaluation_json",
        "compact_json",
        "pairs_csv",
        "markdown",
        "plot_png",
        "sha256sums",
    }
    for name in first_paths:
        if name == "sha256sums":
            continue
        assert first_paths[name].read_bytes() == second_paths[name].read_bytes()
    markdown = first_paths["markdown"].read_text(encoding="utf-8")
    assert "候选准入结论为 **admit**" in markdown
    assert "在线快照投影构造记录" in markdown
    assert "模块微基准" in markdown
    assert _tree_fingerprint(manifest.parent) == before


def test_cli_writes_products(tmp_path: Path, capsys: Any) -> None:
    manifest = _build_evidence(tmp_path)
    assert (
        main(
            [
                "--evidence-manifest",
                str(manifest),
                "--output-dir",
                str(tmp_path / "cli"),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "verdict: admit" in output
    assert "main_default_promotion_allowed: true" in output


def _build_evidence(
    tmp_path: Path,
    *,
    candidate_d1_fusion_wall_s: float = 0.98,
    candidate_materialized_records: int = 600,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    matrix_bytes = MATRIX_PATH.read_bytes()
    assert hashlib.sha256(matrix_bytes).hexdigest() == (
        D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256
    )
    matrix_path = (tmp_path / "matrix.json").resolve()
    matrix_path.write_bytes(matrix_bytes)
    matrix = _read_json(matrix_path)
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    cases: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        case_root = evidence_root / case["case_id"]
        arms: dict[str, Any] = {}
        for arm in ("reference", "candidate"):
            candidate = arm == "candidate"
            implementation = matrix["arm_implementations"][arm]
            episode_dir = case_root / f"{arm}_episode"
            _write_episode(
                episode_dir,
                case=case,
                arm=arm,
                implementation=implementation,
                d1_fusion_wall_s=(
                    candidate_d1_fusion_wall_s if candidate else 1.0
                ),
                core_wall_s=9.95 if candidate else 10.0,
                d1_scan_input_wall_s=1.02 if candidate else 1.0,
                d2_association_wall_s=0.51 if candidate else 0.5,
                real_time_factor=0.51 if candidate else 0.5,
                candidate_materialized_records=(
                    candidate_materialized_records
                ),
            )
            resource_path = case_root / f"{arm}_resource_usage.txt"
            stdout_path = case_root / f"{arm}_stdout.log"
            stderr_path = case_root / f"{arm}_stderr.log"
            resource_path.write_text(
                "\n".join(
                    [
                        "Elapsed (wall clock) time (h:mm:ss or m:ss): "
                        + ("0:10.10" if candidate else "0:10.20"),
                        "Maximum resident set size (kbytes): "
                        + ("102000" if candidate else "100000"),
                        "Exit status: 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            stdout_path.write_text("complete\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            arms[arm] = {
                "arm": arm,
                "expected_implementation": implementation,
                "expected_d1_implementation_id": (
                    CANDIDATE_IMPLEMENTATION_ID
                    if candidate
                    else REFERENCE_IMPLEMENTATION_ID
                ),
                "validation_kind": "replay_prefix_summary",
                "expected_commit": D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT,
                "episode_dir": str(episode_dir.resolve()),
                "resource_path": str(resource_path.resolve()),
                "stdout_path": str(stdout_path.resolve()),
                "stderr_path": str(stderr_path.resolve()),
                "command": _expected_command(
                    implementation=implementation,
                    duration_s=float(case["duration_s"]),
                    seed=int(case["seed"]),
                    episode_dir=episode_dir,
                ),
                "status": "complete",
                "return_code": 0,
                "started_at_utc": "2026-07-25T00:00:00+00:00",
                "completed_at_utc": "2026-07-25T00:00:01+00:00",
            }
        cases.append(
            {
                **case,
                "arms": arms,
                "d6_evaluation_status": "episodes_complete_pending_d6",
            }
        )
    manifest = {
        "schema_version": D1_REPLAY_PREFIX_SUMMARY_EVIDENCE_SCHEMA_VERSION,
        "experiment_id": D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID,
        "matrix_path": str(matrix_path),
        "matrix_sha256": D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256,
        "matrix": matrix,
        "source_worktree": str(ROOT.resolve()),
        "source_commit": D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT,
        "source_repository_dirty": False,
        "output_root": str(evidence_root),
        "required_d6_evaluator_schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "status": "episodes_complete_pending_d6",
        "started_at_utc": "2026-07-25T00:00:00+00:00",
        "completed_at_utc": "2026-07-25T00:01:00+00:00",
        "cases": cases,
        "replay_prefix_summary_execution_config_schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "replay_prefix_summary_diagnostics_schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "replay_prefix_summary_schema_version": (
            "d1.fixed_lag_replay_prefix_summary.v1"
        ),
    }
    manifest_path = evidence_root / "evidence_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _write_episode(
    episode_dir: Path,
    *,
    case: dict[str, Any],
    arm: str,
    implementation: str,
    d1_fusion_wall_s: float,
    core_wall_s: float,
    d1_scan_input_wall_s: float,
    d2_association_wall_s: float,
    real_time_factor: float,
    candidate_materialized_records: int,
) -> None:
    episode_dir.mkdir(parents=True)
    candidate = arm == "candidate"
    config = {
        "schema_version": "scalable3d-scenario-v1",
        "scenario_name": "nominal_200v200_cli_200v200",
        "scenario_version": "200v200-nominal-v1-cli-200v200",
        "seed": case["seed"],
        "duration_s": case["duration_s"],
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    execution = _execution_config(arm)
    initial = _diagnostics(
        arm,
        execution,
        phase="initial",
        materialized_records=candidate_materialized_records,
    )
    module_final_diagnostics = _diagnostics(
        arm,
        execution,
        phase="module_final",
        materialized_records=candidate_materialized_records,
    )
    exported_diagnostics = _diagnostics(
        arm,
        execution,
        phase="exported",
        materialized_records=candidate_materialized_records,
    )
    governance_exported = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "test_fixture": True,
        SELECTOR: implementation,
        EXECUTION: copy.deepcopy(execution),
        DIAGNOSTICS: copy.deepcopy(exported_diagnostics),
        "d1_fusion_association": {"association_gate": 40.0},
    }
    governance_final = copy.deepcopy(governance_exported)
    governance_final[DIAGNOSTICS] = copy.deepcopy(
        module_final_diagnostics
    )
    stage_values = {
        "module.d1_fusion": d1_fusion_wall_s,
        "module.d1_scan_input": d1_scan_input_wall_s,
        "module.d2_association": d2_association_wall_s,
    }
    d1_performance = _d1_fusion_performance()
    module_final = {
        "d1_track_count": 201,
        "d2_track_count": 201,
        "d3_assignment_count": 200,
        "d5_binding_count": 3,
        "d7_command_count": 200,
        SELECTOR: implementation,
        EXECUTION: copy.deepcopy(execution),
        DIAGNOSTICS: copy.deepcopy(module_final_diagnostics),
        "d1_fusion_performance": copy.deepcopy(d1_performance),
        "stage_timings": {
            name: {"wall_time_s": value}
            for name, value in stage_values.items()
        },
        "observation_governance": governance_final,
    }
    episode_id = f"{case['case_id']}-{arm}"
    summary = {
        "episode_id": episode_id,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": case["seed"],
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "simulated_duration_s": case["duration_s"],
        "physics_step_count": int(float(case["duration_s"]) * 20),
        "finite_state": True,
        "online_truth_use_count": 0,
        "online_observation_count": 1,
        "online_batch_count": 1,
        "radar_observation_count": 1,
        "acoustic_observation_count": 0,
        "visual_observation_count": 0,
        "module_publication_count": 1,
        "module_publication_topic_counts": {"test.topic": 1},
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
        "wall_time_s": core_wall_s,
        "real_time_factor": real_time_factor,
        SELECTOR: implementation,
        EXECUTION: copy.deepcopy(execution),
        DIAGNOSTICS: copy.deepcopy(exported_diagnostics),
        "module_final_diagnostics": module_final,
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "configuration": {
            "test_fixture": True,
            SELECTOR: implementation,
        },
        SELECTOR: implementation,
        EXECUTION: copy.deepcopy(execution),
        DIAGNOSTICS: initial,
    }
    manifest = {
        "episode_id": episode_id,
        "git_commit": D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT,
        "repository_dirty": False,
        "seed": case["seed"],
        "config_sha256": _canonical_sha256(config),
        "runtime_profile": runtime_profile,
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
    }
    _write_json(episode_dir / "manifest.json", manifest)
    _write_json(episode_dir / "scenario_config.json", config)
    _write_json(episode_dir / "summary.json", summary)
    _write_json(
        episode_dir / "observation_governance_audit.json",
        governance_exported,
    )
    _write_stage_csv(episode_dir / "stage_timings.csv", stage_values)
    online_record = {
        "sequence": 1,
        "topic": "test.topic",
        "source": "D1",
        "timestamp": 0.1,
        "payload": {"global_track_id": "GT-0001"},
    }
    (episode_dir / "online_observations.jsonl").write_text(
        json.dumps(online_record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (episode_dir / "offline_truth_labels.jsonl").write_text(
        json.dumps({"label": "TGT-0001"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (episode_dir / "offline_proximity_intercepts.jsonl").write_text(
        json.dumps({"event_count": 0}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    np.savez_compressed(
        episode_dir / "offline_truth_state.npz",
        state=np.array([[1.0, 2.0, 3.0]], dtype=float),
    )
    evidence = _online_evidence()
    _write_json(
        episode_dir / "offline_consistency" / "online_evidence.json",
        evidence,
    )


def _execution_config(arm: str) -> dict[str, Any]:
    candidate = arm == "candidate"
    return {
        "schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "selector": (
            CANDIDATE_IMPLEMENTATION
            if candidate
            else REFERENCE_IMPLEMENTATION
        ),
        "selected_implementation_id": (
            CANDIDATE_IMPLEMENTATION_ID
            if candidate
            else REFERENCE_IMPLEMENTATION_ID
        ),
        "default_selector": REFERENCE_IMPLEMENTATION,
        "reference_selector": REFERENCE_IMPLEMENTATION,
        "reference_implementation_id": REFERENCE_IMPLEMENTATION_ID,
        "candidate_selector": CANDIDATE_IMPLEMENTATION,
        "candidate_implementation_id": CANDIDATE_IMPLEMENTATION_ID,
        "candidate_enabled": candidate,
        "candidate_default_enabled": False,
        "rollback_selector": REFERENCE_IMPLEMENTATION,
        "summary_schema_version": (
            "d1.fixed_lag_replay_prefix_summary.v1"
        ),
        "buffer_horizon_s": 6.0,
        "truth_dependent_inputs": False,
        "fixed_lag_window_changed": False,
        "checkpoint_audit_semantics_changed": False,
        "consistency_evidence_semantics_changed": False,
    }


def _diagnostics(
    arm: str,
    execution: dict[str, Any],
    *,
    phase: str,
    materialized_records: int,
) -> dict[str, Any]:
    candidate = arm == "candidate"
    if not candidate or phase == "initial":
        operations: dict[str, int] = {}
        fallback_reasons: dict[str, int] = {}
        materialization_reasons: dict[str, int] = {}
        pending = 0
    else:
        exported = phase == "exported"
        final_records = max(0, materialized_records - 200)
        operations = {
            "summary_attempt_count": 100,
            "summary_hit_count": 80,
            "summary_fallback_count": 20,
            "summary_build_count": 100,
            "summary_reused_checkpoint_count": 500,
            "summary_reused_gated_id_count": 20,
            "summary_reused_nis_count": 500,
            "lazy_consistency_refresh_event_count": 80,
            "lazy_consistency_refresh_logical_record_count": 1000,
            "lazy_consistency_materialization_count": (
                12 if exported else 10
            ),
            "lazy_consistency_materialized_event_count": (
                50 if exported else 30
            ),
            "lazy_consistency_materialized_record_count": (
                materialized_records if exported else final_records
            ),
            "append_only_revision_advance_count": 100,
            "append_only_pending_preservation_count": 80,
            "append_only_pending_preserved_record_count": 800,
            "public_snapshot_projection_count": 10,
            "public_snapshot_projected_ledger_count": 20,
            "public_snapshot_projected_event_count": 80,
            "public_snapshot_projected_record_count": 700,
        }
        fallback_reasons = {"summary_unavailable": 20}
        materialization_reasons = {"fixed_lag_rebase": 10}
        if exported:
            materialization_reasons["public_evidence_snapshot"] = 2
        pending = 0 if exported else 2
    return {
        "schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "execution_config": copy.deepcopy(execution),
        "selector": execution["selector"],
        "selected_implementation_id": execution[
            "selected_implementation_id"
        ],
        "operation_counts": operations,
        "fallback_reasons": fallback_reasons,
        "materialization_reasons": materialization_reasons,
        "pending_consistency_ledger_count": pending,
        "conservation": {
            "attempt_partition": True,
            "fallback_reason_partition": True,
            "hits_not_above_attempts": True,
            "reused_checkpoints_not_below_hits": True,
        },
    }


def _d1_fusion_performance() -> dict[str, Any]:
    return {
        "schema_version": "d1.fusion_performance_diagnostics.v1",
        "batch_count": 10,
        "scan_batch_count": 10,
        "observation_count": 100,
        "history_replay_count": 20,
        "origin_replay_count": 0,
        "finalization_replay_count": 20,
        "replay_filter_update_count": 20,
        "replay_checkpoint_reuse_count": 80,
        "checkpoint_state_query_count": 100,
        "fixed_lag_rebase_count": 1,
        "fixed_lag_checkpoint_suffix_reuse_count": 0,
        "replay_checkpoint_prefix_fast_path_count": 80,
        "cached_consistency_refresh_count": 100,
        "global_track_materialization_count": 100,
        "sensor_health_snapshot_build_count": 10,
        "association_candidate_pair_count": 1000,
        "association_innovation_solve_count": 100,
        "current_track_count": 201,
        "current_time": 2.0,
    }


def _online_evidence() -> dict[str, Any]:
    records = [
        {
            "observation_id": "obs-1",
            "evidence_id": "evidence-1",
            "replay_count": 3,
            "replay_revision": 7,
        }
    ]
    value = {
        "schema_version": "d1.consistency.online_evidence_bundle.v1",
        "record_schema_version": (
            "d1.consistency.online_evidence_record.v1"
        ),
        "range_bin_schema_version": "d1.consistency.range_bins.v1",
        "range_bin_edges_m": [1000.0, 3000.0, 5000.0],
        "provenance": {
            "schema_version": "d1.consistency.source_provenance.v1",
            "producer_id": "fixture",
        },
        "record_count": len(records),
        "records_digest": "",
        "truth_policy": "online_truth_forbidden",
        "content_digest": "",
        "records": records,
    }
    _refresh_evidence_digests(value)
    return value


def _refresh_evidence_digests(value: dict[str, Any]) -> None:
    value["record_count"] = len(value["records"])
    value["records_digest"] = _payload_sha256(value["records"])
    unsigned = {
        key: copy.deepcopy(value[key])
        for key in (
            "schema_version",
            "record_schema_version",
            "range_bin_schema_version",
            "range_bin_edges_m",
            "provenance",
            "record_count",
            "records_digest",
            "truth_policy",
        )
    }
    value["content_digest"] = _payload_sha256(unsigned)


def _mutate_candidate_diagnostics(
    manifest_path: Path,
    case_id: str,
    mutate: Callable[[dict[str, Any], str], None],
) -> None:
    episode = _episode(manifest_path, case_id, "candidate")
    summary_path = episode / "summary.json"
    governance_path = episode / "observation_governance_audit.json"
    summary = _read_json(summary_path)
    governance = _read_json(governance_path)
    for diagnostics, phase in (
        (summary[DIAGNOSTICS], "exported"),
        (governance[DIAGNOSTICS], "exported"),
        (
            summary["module_final_diagnostics"][DIAGNOSTICS],
            "module_final",
        ),
        (
            summary["module_final_diagnostics"][
                "observation_governance"
            ][DIAGNOSTICS],
            "module_final",
        ),
    ):
        mutate(diagnostics, phase)
    _write_json(summary_path, summary)
    _write_json(governance_path, governance)


def _write_stage_csv(
    path: Path, stage_values: dict[str, float]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=STAGE_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        for stage, wall_time_s in stage_values.items():
            call_count = 10
            mean_ms = wall_time_s * 1000.0 / call_count
            writer.writerow(
                {
                    "schema_version": "scalable3d-stage-timings-v2",
                    "stage": stage,
                    "call_count": call_count,
                    "wall_time_s": wall_time_s,
                    "mean_wall_time_ms": mean_ms,
                    "p50_wall_time_ms": mean_ms,
                    "p95_wall_time_ms": mean_ms,
                    "max_wall_time_ms": mean_ms,
                    "distribution_available": True,
                    "distribution_unavailable_reason": "",
                }
            )


def _expected_command(
    *,
    implementation: str,
    duration_s: float,
    seed: int,
    episode_dir: Path,
) -> list[str]:
    return [
        "python3",
        str(
            ROOT
            / "research_modules"
            / "scalable_3d_simulation"
            / "run_episode.py"
        ),
        "--integrated-stack",
        "--d1-replay-prefix-summary-implementation",
        implementation,
        "--duration",
        format(duration_s, ".15g"),
        "--seed",
        str(seed),
        "--drone-count",
        "200",
        "--target-count",
        "200",
        "--recon-count",
        "2",
        "--output",
        str(episode_dir.resolve()),
    ]


def _episode(
    manifest_path: Path, case_id: str, arm: str
) -> Path:
    return manifest_path.parent / case_id / f"{arm}_episode"


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
