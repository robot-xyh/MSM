from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from d6_evaluation_metrics.d1_publication_evidence_snapshot_multiseed import (
    CANDIDATE_IMPLEMENTATION,
    CANDIDATE_IMPLEMENTATION_ID,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVIDENCE_SCHEMA_VERSION,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT,
    REFERENCE_IMPLEMENTATION,
    REFERENCE_IMPLEMENTATION_ID,
    evaluate_d1_publication_evidence_snapshot_multiseed,
    main,
    write_d1_publication_evidence_snapshot_multiseed_report,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_publication_evidence_snapshot_multiseed_v1.json"
)
SELECTOR = "d1_publication_evidence_snapshot_implementation"
EXECUTION = "d1_publication_evidence_snapshot_execution_config"
DIAGNOSTICS = "d1_publication_evidence_snapshot_diagnostics"
REPLAY_SELECTOR = "d1_replay_prefix_summary_implementation"
REPLAY_REFERENCE = "per_checkpoint_prefix_rebuild_v1"
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

    result = evaluate_d1_publication_evidence_snapshot_multiseed(
        manifest
    )

    assert result["schema_version"] == (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["availability"]["available"] is True
    assert result["input_contract"]["source_commit"] == (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256
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
        "publication_evidence_snapshot_diagnostics_aggregate"
    ]["groups"]["all"]
    assert aggregate["candidate_returned_record_reduction_pct"] == 60.0
    assert aggregate["candidate_selection_count"] == 130
    assert aggregate["candidate_subset_success_count"] == 130
    assert aggregate["candidate_fallback_count"] == 0
    assert result["system_realtime_gate"]["passed"] is False
    assert result["optimization_admitted"] is True
    assert result["deterministic_summary_sha256"].startswith("sha256:")


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

    digest_result = evaluate_d1_publication_evidence_snapshot_multiseed(
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

    operation_result = (
        evaluate_d1_publication_evidence_snapshot_multiseed(
            operation_manifest
        )
    )
    assert operation_result["availability"]["available"] is True
    assert operation_result["verdict"] == "reject"
    assert not operation_result["admission_gates"][
        "all_pairs_existing_operation_counts_equal"
    ]["passed"]


def test_candidate_fallback_and_empty_selection_reject(
    tmp_path: Path,
) -> None:
    fallback_manifest = _build_evidence(tmp_path / "fallback")

    def add_fallback(diagnostics: dict[str, Any]) -> None:
        counts = diagnostics["operation_counts"]
        counts["candidate_subset_success_count"] -= 1
        counts["candidate_fallback_count"] += 1
        counts["subset_snapshot_call_count"] -= 1
        counts["full_snapshot_call_count"] += 1
        diagnostics["fallback_reason_counts"] = {
            "unknown_required_observation_id": 1
        }

    _mutate_workload_diagnostics(
        fallback_manifest, "short_seed_1151", add_fallback
    )
    fallback = evaluate_d1_publication_evidence_snapshot_multiseed(
        fallback_manifest
    )
    assert fallback["availability"]["available"] is True
    assert fallback["verdict"] == "reject"
    assert not fallback["admission_gates"][
        "all_pairs_publication_evidence_snapshot_audit_valid"
    ]["passed"]

    empty_manifest = _build_evidence(tmp_path / "empty")

    def add_empty(diagnostics: dict[str, Any]) -> None:
        diagnostics["operation_counts"][
            "empty_required_id_selection_count"
        ] += 1

    _mutate_workload_diagnostics(
        empty_manifest, "short_seed_1151", add_empty
    )
    empty = evaluate_d1_publication_evidence_snapshot_multiseed(
        empty_manifest
    )
    assert empty["availability"]["available"] is True
    assert empty["verdict"] == "reject"
    assert not empty["pairs"][0][
        "publication_evidence_snapshot_audit_passed"
    ]


@pytest.mark.parametrize(
    ("field", "reason_fragment"),
    (
        ("lookup_miss_count", "conservation"),
        ("invalid_required_id_count", "conservation"),
    ),
)
def test_candidate_lookup_or_invalid_id_fails_closed(
    tmp_path: Path,
    field: str,
    reason_fragment: str,
) -> None:
    manifest = _build_evidence(tmp_path / field)

    def mutate(diagnostics: dict[str, Any]) -> None:
        diagnostics["operation_counts"][field] += 1

    _mutate_workload_diagnostics(
        manifest, "short_seed_1151", mutate
    )
    result = evaluate_d1_publication_evidence_snapshot_multiseed(
        manifest
    )
    assert result["availability"]["available"] is False
    assert result["verdict"] == "reject"
    assert reason_fragment in result["availability"]["reason"]


def test_reduction_and_performance_gates_reject(
    tmp_path: Path,
) -> None:
    reduction_manifest = _build_evidence(
        tmp_path / "reduction",
        candidate_returned_records=600,
    )
    reduction = evaluate_d1_publication_evidence_snapshot_multiseed(
        reduction_manifest
    )
    assert reduction["availability"]["available"] is True
    assert reduction["verdict"] == "reject"
    gate = reduction["admission_gates"][
        "minimum_candidate_returned_record_reduction_pct"
    ]
    assert gate["actual"] == 40.0
    assert gate["passed"] is False

    performance_manifest = _build_evidence(
        tmp_path / "performance",
        candidate_d1_fusion_wall_s=1.02,
    )
    performance = evaluate_d1_publication_evidence_snapshot_multiseed(
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


def test_d1_or_d2_online_record_semantics_mismatch_reject(
    tmp_path: Path,
) -> None:
    for module in ("d1", "d2"):
        manifest = _build_evidence(tmp_path / module)
        path = (
            _episode(manifest, "short_seed_1151", "candidate")
            / "offline_identity"
            / f"online_{module}_records.jsonl"
        )
        record = json.loads(path.read_text(encoding="utf-8"))
        record["state"][0] += 1.0
        path.write_text(
            json.dumps(record, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = (
            evaluate_d1_publication_evidence_snapshot_multiseed(
                manifest
            )
        )
        assert result["availability"]["available"] is True
        assert result["verdict"] == "reject"
        assert not result["pairs"][0]["business_semantics_passed"]
        assert not result["pairs"][0]["business_semantics"]["checks"][
            f"online_{module}_records_semantically_equal"
        ]


@pytest.mark.parametrize(
    "tamper",
    ("commit", "matrix", "command", "arm_status", "replay_selector"),
)
def test_provenance_command_and_arm_tampering_fail_closed(
    tmp_path: Path, tamper: str
) -> None:
    manifest = _build_evidence(tmp_path / tamper)
    if tamper == "commit":
        value = _read_json(manifest)
        value["source_commit"] = "0" * 40
        _write_json(manifest, value)
    elif tamper == "matrix":
        value = _read_json(manifest)
        value["matrix_sha256"] = "0" * 64
        _write_json(manifest, value)
    elif tamper == "command":
        value = _read_json(manifest)
        value["cases"][0]["arms"]["candidate"]["command"].insert(
            -2, "--unexpected"
        )
        _write_json(manifest, value)
    elif tamper == "arm_status":
        value = _read_json(manifest)
        value["cases"][0]["arms"]["candidate"]["status"] = "reused"
        _write_json(manifest, value)
    else:
        episode = _episode(
            manifest, "short_seed_1151", "candidate"
        )
        manifest_path = episode / "manifest.json"
        value = _read_json(manifest_path)
        value["runtime_profile"][REPLAY_SELECTOR] = (
            "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
        )
        value["runtime_profile_sha256"] = _canonical_sha256(
            value["runtime_profile"]
        )
        _write_json(manifest_path, value)

    result = evaluate_d1_publication_evidence_snapshot_multiseed(
        manifest
    )
    assert result["availability"]["available"] is False
    assert result["verdict"] == "reject"
    assert result["main_default_promotion_allowed"] is False


def test_repeat_evaluation_and_outputs_are_deterministic_read_only(
    tmp_path: Path,
) -> None:
    manifest = _build_evidence(tmp_path)
    before = _tree_fingerprint(manifest.parent)
    first = evaluate_d1_publication_evidence_snapshot_multiseed(
        manifest
    )
    second = evaluate_d1_publication_evidence_snapshot_multiseed(
        manifest
    )
    assert first == second
    assert _tree_fingerprint(manifest.parent) == before

    first_paths = (
        write_d1_publication_evidence_snapshot_multiseed_report(
            first, tmp_path / "report_1"
        )
    )
    second_paths = (
        write_d1_publication_evidence_snapshot_multiseed_report(
            second, tmp_path / "report_2"
        )
    )
    assert set(first_paths) == {
        "evaluation_json",
        "compact_json",
        "pairs_csv",
        "markdown",
        "sha256sums",
    }
    for name in first_paths:
        if name == "sha256sums":
            continue
        assert (
            first_paths[name].read_bytes()
            == second_paths[name].read_bytes()
        )
    markdown = first_paths["markdown"].read_text(encoding="utf-8")
    assert "候选准入结论为 **admit**" in markdown
    assert "候选削减率" in markdown
    assert "实时门独立列示" in markdown
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
    assert "system_realtime_gap_closed: false" in output


def _build_evidence(
    tmp_path: Path,
    *,
    candidate_d1_fusion_wall_s: float = 0.98,
    candidate_returned_records: int = 400,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    matrix_bytes = MATRIX_PATH.read_bytes()
    assert hashlib.sha256(matrix_bytes).hexdigest() == (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256
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
                candidate_returned_records=candidate_returned_records,
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
                "validation_kind": "publication_evidence_snapshot",
                "expected_commit": (
                    D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT
                ),
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
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVIDENCE_SCHEMA_VERSION
        ),
        "experiment_id": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID
        ),
        "matrix_path": str(matrix_path),
        "matrix_sha256": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256
        ),
        "matrix": matrix,
        "source_worktree": str(ROOT.resolve()),
        "source_commit": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT
        ),
        "source_repository_dirty": False,
        "output_root": str(evidence_root),
        "required_d6_evaluator_schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "status": "episodes_complete_pending_d6",
        "started_at_utc": "2026-07-25T00:00:00+00:00",
        "completed_at_utc": "2026-07-25T00:01:00+00:00",
        "cases": cases,
        "publication_evidence_snapshot_execution_config_schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "publication_evidence_snapshot_diagnostics_schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION
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
    candidate_returned_records: int,
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
        initial=True,
        candidate_returned_records=candidate_returned_records,
    )
    workload = _diagnostics(
        arm,
        execution,
        initial=False,
        candidate_returned_records=candidate_returned_records,
    )
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "test_fixture": True,
        SELECTOR: implementation,
        EXECUTION: copy.deepcopy(execution),
        DIAGNOSTICS: copy.deepcopy(workload),
        REPLAY_SELECTOR: REPLAY_REFERENCE,
        "d1_fusion_association": {"association_gate": 40.0},
    }
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
        DIAGNOSTICS: copy.deepcopy(workload),
        REPLAY_SELECTOR: REPLAY_REFERENCE,
        "d1_fusion_performance": copy.deepcopy(d1_performance),
        "stage_timings": {
            name: {"wall_time_s": value}
            for name, value in stage_values.items()
        },
        "observation_governance": copy.deepcopy(governance),
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
        DIAGNOSTICS: copy.deepcopy(workload),
        REPLAY_SELECTOR: REPLAY_REFERENCE,
        "module_final_diagnostics": module_final,
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "configuration": {
            "test_fixture": True,
            SELECTOR: implementation,
            REPLAY_SELECTOR: REPLAY_REFERENCE,
        },
        SELECTOR: implementation,
        EXECUTION: copy.deepcopy(execution),
        DIAGNOSTICS: initial,
        REPLAY_SELECTOR: REPLAY_REFERENCE,
    }
    manifest = {
        "episode_id": episode_id,
        "git_commit": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT
        ),
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
        governance,
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
    identity_dir = episode_dir / "offline_identity"
    identity_dir.mkdir()
    d1_record = {
        "global_track_id": "GT-0001",
        "state": [1.0, 2.0, 3.0],
        "covariance_trace": 4.0,
    }
    d2_record = {
        "global_track_id": "GT-0001",
        "state": [1.0, 2.0, 3.0],
        "id_switch_count": 0,
    }
    (identity_dir / "online_d1_records.jsonl").write_text(
        json.dumps(d1_record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (identity_dir / "online_d2_records.jsonl").write_text(
        json.dumps(d2_record, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _execution_config(arm: str) -> dict[str, Any]:
    candidate = arm == "candidate"
    return {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "selector": (
            CANDIDATE_IMPLEMENTATION
            if candidate
            else REFERENCE_IMPLEMENTATION
        ),
        "implementation_id": (
            CANDIDATE_IMPLEMENTATION_ID
            if candidate
            else REFERENCE_IMPLEMENTATION_ID
        ),
        "candidate_enabled": candidate,
        "required_id_sources": [
            "source_observations",
            "materialized_track_latest_observation",
        ],
        "required_id_order": "deduplicated_lexicographic",
        "invalid_or_unknown_id_policy": "fallback_to_full_snapshot",
        "episode_final_export_scope": "full_exact_materialized_records",
        "truth_dependent_inputs_allowed": False,
    }


def _diagnostics(
    arm: str,
    execution: dict[str, Any],
    *,
    initial: bool,
    candidate_returned_records: int,
) -> dict[str, Any]:
    candidate = arm == "candidate"
    if initial:
        operations: dict[str, int] = {}
        fallbacks: dict[str, int] = {}
    elif candidate:
        operations = {
            "selection_count": 10,
            "reference_selection_count": 0,
            "candidate_selection_count": 10,
            "candidate_subset_success_count": 10,
            "candidate_fallback_count": 0,
            "adapter_snapshot_call_count": 10,
            "full_snapshot_call_count": 0,
            "subset_snapshot_call_count": 10,
            "publication_count": 100,
            "source_observation_reference_count": 100,
            "track_latest_observation_reference_count": 900,
            "required_observation_id_count": candidate_returned_records,
            "duplicate_reference_count": (
                1000 - candidate_returned_records
            ),
            "invalid_required_id_count": 0,
            "empty_required_id_selection_count": 0,
            "returned_record_count": candidate_returned_records,
            "lookup_miss_count": 0,
        }
        fallbacks = {}
    else:
        operations = {
            "selection_count": 10,
            "reference_selection_count": 10,
            "candidate_selection_count": 0,
            "candidate_subset_success_count": 0,
            "candidate_fallback_count": 0,
            "adapter_snapshot_call_count": 10,
            "full_snapshot_call_count": 10,
            "subset_snapshot_call_count": 0,
            "publication_count": 100,
            "source_observation_reference_count": 0,
            "track_latest_observation_reference_count": 0,
            "required_observation_id_count": 0,
            "duplicate_reference_count": 0,
            "invalid_required_id_count": 0,
            "empty_required_id_selection_count": 0,
            "returned_record_count": 1000,
            "lookup_miss_count": 0,
        }
        fallbacks = {}
    conservation = {
        "selection_partition": True,
        "candidate_selection_partition": True,
        "adapter_call_partition": True,
        "reference_deduplication_partition": True,
        "fallback_not_above_candidate_selection": True,
        "all_required_records_available": True,
    }
    return {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "execution_config": copy.deepcopy(execution),
        "operation_counts": operations,
        "fallback_reason_counts": fallbacks,
        "conservation": conservation,
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


def _mutate_workload_diagnostics(
    manifest_path: Path,
    case_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    episode = _episode(manifest_path, case_id, "candidate")
    summary_path = episode / "summary.json"
    governance_path = episode / "observation_governance_audit.json"
    summary = _read_json(summary_path)
    governance = _read_json(governance_path)
    diagnostics = (
        summary["module_final_diagnostics"]["observation_governance"][
            DIAGNOSTICS
        ]
    )
    locations = (
        summary[DIAGNOSTICS],
        summary["module_final_diagnostics"][DIAGNOSTICS],
        diagnostics,
        governance[DIAGNOSTICS],
    )
    for value in locations:
        mutate(value)
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
        "--d1-publication-evidence-snapshot-implementation",
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
