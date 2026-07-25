from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from d6_evaluation_metrics.d1_association_sparse_prefilter_multiseed import (
    CANDIDATE_IMPLEMENTATION,
    CANDIDATE_IMPLEMENTATION_ID,
    D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION,
    D1_ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_SCHEMA_VERSION,
    D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION,
    D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID,
    D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256,
    D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT,
    D1AssociationSparsePrefilterEvidenceError,
    REFERENCE_IMPLEMENTATION,
    REFERENCE_IMPLEMENTATION_ID,
    evaluate_d1_association_sparse_prefilter_multiseed,
    main,
    write_d1_association_sparse_prefilter_multiseed_report,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_association_sparse_prefilter_multiseed_v1.json"
)
MODALITIES = (
    "radar",
    "lidar",
    "acoustic",
    "acoustic_3d",
    "eo",
    "other",
)
COUNTERS = (
    "candidate_pair_count",
    "conservative_prefilter_rejection_count",
    "exact_innovation_solve_count",
    "exact_gate_pass_count",
    "fallback_count",
)
SELECTOR_FIELD = "d1_association_sparse_prefilter_implementation"
CONFIG_FIELD = "d1_association_sparse_prefilter_execution_config"
DIAGNOSTICS_FIELD = "d1_association_sparse_prefilter_diagnostics"
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
    manifest_path = _build_evidence(tmp_path)

    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )

    assert result["availability"]["available"] is True
    assert result["schema_version"] == (
        D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256
    )
    assert len(result["pairs"]) == 13
    assert result["input_contract"]["fresh_arm_count"] == 26
    assert all(
        pair["business_semantics_passed"] for pair in result["pairs"]
    )
    assert all(
        pair["exact_gate_pass_counts_equal"] for pair in result["pairs"]
    )
    assert all(
        gate["passed"] for gate in result["admission_gates"].values()
    )
    assert result["verdict"] == "admit"
    assert result["main_default_promotion_allowed"] is True
    assert result["system_realtime_gap_closed"] is False
    aggregate = result[
        "association_sparse_prefilter_diagnostics_aggregate"
    ]["groups"]["all"]
    assert (
        aggregate["candidate_non_radar_exact_solve_reduction_pct"]
        == pytest.approx(75.0)
    )
    assert set(aggregate["candidate_modality_counts"]) == set(MODALITIES)


def test_report_bundle_is_complete_deterministic_and_read_only(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    before = _tree_fingerprint(manifest_path.parent)
    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )

    paths = write_d1_association_sparse_prefilter_multiseed_report(
        result, tmp_path / "report"
    )

    assert _tree_fingerprint(manifest_path.parent) == before
    assert set(paths) == {
        "evaluation_json",
        "compact_json",
        "pairs_csv",
        "markdown",
        "plot_png",
        "sha256sums",
    }
    assert all(path.is_file() for path in paths.values())
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "正式 verdict 为 **admit**" in markdown
    assert "系统实时缺口仍开放" in markdown
    assert "不代表 AirSim、目标硬件、实机或实飞结论" in markdown
    compact = _read_json(paths["compact_json"])
    assert "pairs" not in compact
    assert compact["verdict"] == "admit"
    with pytest.raises(ValueError, match="independent"):
        write_d1_association_sparse_prefilter_multiseed_report(
            result, manifest_path.parent / "forbidden"
        )


def test_cli_writes_formal_products(tmp_path: Path, capsys: Any) -> None:
    manifest_path = _build_evidence(tmp_path)
    output = tmp_path / "cli"

    assert (
        main(
            [
                "--evidence-manifest",
                str(manifest_path),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )

    stdout = capsys.readouterr().out
    assert "verdict: admit" in stdout
    assert "main_default_promotion_allowed: true" in stdout
    assert "system_realtime_gap_closed: false" in stdout


def test_missing_evidence_and_missing_episode_file_fail_closed(
    tmp_path: Path,
) -> None:
    missing = evaluate_d1_association_sparse_prefilter_multiseed(
        tmp_path / "missing.json"
    )
    assert missing["availability"]["available"] is False
    assert missing["verdict"] == "reject"

    manifest_path = _build_evidence(tmp_path / "episode")
    stage_path = (
        manifest_path.parent
        / "short_seed_1131"
        / "candidate_episode"
        / "stage_timings.csv"
    )
    stage_path.unlink()
    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )
    assert result["availability"]["available"] is False
    assert "missing stage_timings.csv" in result["availability"]["reason"]


def test_matrix_sha_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    matrix_path = Path(manifest["matrix_path"])
    matrix = _read_json(matrix_path)
    matrix["cooldown_s"] = 3.0
    _write_json(matrix_path, matrix)

    with pytest.raises(
        D1AssociationSparsePrefilterEvidenceError,
        match="does not match matrix_path bytes",
    ):
        evaluate_d1_association_sparse_prefilter_multiseed(
            manifest_path, raise_on_invalid=True
        )


def test_source_commit_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["source_commit"] = "b" * 40
    _write_json(manifest_path, manifest)

    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )

    assert result["availability"]["available"] is False
    assert "frozen producer commit" in result["availability"]["reason"]


def test_selector_and_execution_config_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    selector_manifest = _build_evidence(tmp_path / "selector")
    selector_episode = _episode(
        selector_manifest, "short_seed_1131", "candidate"
    )
    summary = _read_json(selector_episode / "summary.json")
    summary[SELECTOR_FIELD] = REFERENCE_IMPLEMENTATION
    _write_json(selector_episode / "summary.json", summary)
    selector_result = evaluate_d1_association_sparse_prefilter_multiseed(
        selector_manifest
    )
    assert selector_result["availability"]["available"] is False
    assert "selector mismatch" in selector_result["availability"]["reason"]

    config_manifest = _build_evidence(tmp_path / "config")
    config_episode = _episode(
        config_manifest, "short_seed_1131", "candidate"
    )
    summary = _read_json(config_episode / "summary.json")
    summary[CONFIG_FIELD]["truth_dependent_inputs"] = True
    _write_json(config_episode / "summary.json", summary)
    config_result = evaluate_d1_association_sparse_prefilter_multiseed(
        config_manifest
    )
    assert config_result["availability"]["available"] is False
    assert "execution config value mismatch" in config_result[
        "availability"
    ]["reason"]


def test_diagnostics_schema_and_count_conservation_fail_closed(
    tmp_path: Path,
) -> None:
    schema_manifest = _build_evidence(tmp_path / "schema")
    episode = _episode(schema_manifest, "short_seed_1131", "candidate")
    manifest_path = episode / "manifest.json"
    episode_manifest = _read_json(manifest_path)
    episode_manifest["runtime_profile"][DIAGNOSTICS_FIELD][
        "schema_version"
    ] = "old"
    episode_manifest["runtime_profile_sha256"] = _canonical_sha256(
        episode_manifest["runtime_profile"]
    )
    _write_json(manifest_path, episode_manifest)
    _mutate_final_diagnostics(
        episode,
        lambda item: item.__setitem__("schema_version", "old"),
    )
    schema_result = evaluate_d1_association_sparse_prefilter_multiseed(
        schema_manifest
    )
    assert schema_result["availability"]["available"] is False
    assert "diagnostics schema" in schema_result["availability"]["reason"]

    count_manifest = _build_evidence(tmp_path / "counts")
    episode = _episode(count_manifest, "short_seed_1131", "candidate")

    def break_total(item: dict[str, Any]) -> None:
        item["total_counts"]["candidate_pair_count"] += 1

    _mutate_final_diagnostics(episode, break_total)
    count_result = evaluate_d1_association_sparse_prefilter_multiseed(
        count_manifest
    )
    assert count_result["availability"]["available"] is False
    assert "total count conservation failed" in count_result[
        "availability"
    ]["reason"]


def test_exact_gate_pass_mismatch_rejects_without_masking(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode = _episode(manifest_path, "short_seed_1131", "candidate")

    def change_gate(item: dict[str, Any]) -> None:
        item["modality_counts"]["eo"]["exact_gate_pass_count"] -= 1
        item["total_counts"]["exact_gate_pass_count"] -= 1

    _mutate_final_diagnostics(episode, change_gate)
    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )

    assert result["availability"]["available"] is True
    assert result["pairs"][0]["business_semantics_passed"] is True
    assert result["pairs"][0]["exact_gate_pass_counts_equal"] is False
    assert result["admission_gates"][
        "all_pairs_exact_gate_pass_counts_equal"
    ]["passed"] is False
    assert result["verdict"] == "reject"


def test_nonregistered_semantic_change_rejects(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode = _episode(manifest_path, "short_seed_1131", "candidate")
    summary = _read_json(episode / "summary.json")
    summary["module_final_diagnostics"]["d2_track_count"] = 202
    _write_json(episode / "summary.json", summary)

    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )

    assert result["availability"]["available"] is True
    assert result["pairs"][0]["business_semantics_passed"] is False
    assert result["admission_gates"][
        "all_pairs_business_semantics_equal"
    ]["passed"] is False
    assert result["verdict"] == "reject"


def test_performance_and_exact_solve_gates_reject(
    tmp_path: Path,
) -> None:
    performance = evaluate_d1_association_sparse_prefilter_multiseed(
        _build_evidence(
            tmp_path / "performance",
            candidate_d1_fusion_wall_s=0.995,
            candidate_core_wall_s=9.99,
        )
    )
    assert performance["admission_gates"][
        "short_minimum_d1_fusion_improvement_pct"
    ]["passed"] is False
    assert performance["admission_gates"][
        "long_minimum_core_wall_improvement_pct"
    ]["passed"] is False
    assert performance["verdict"] == "reject"

    solve = evaluate_d1_association_sparse_prefilter_multiseed(
        _build_evidence(
            tmp_path / "solve",
            candidate_non_radar_solves=350,
            candidate_non_radar_rejections=50,
        )
    )
    assert solve["admission_gates"][
        "minimum_candidate_non_radar_exact_solve_reduction_pct"
    ]["passed"] is False
    assert solve["verdict"] == "reject"


def test_rss_and_d2_gates_reject(tmp_path: Path) -> None:
    rss = evaluate_d1_association_sparse_prefilter_multiseed(
        _build_evidence(tmp_path / "rss", candidate_rss_kib=105_001)
    )
    assert rss["admission_gates"][
        "maximum_any_pair_rss_increase_pct"
    ]["passed"] is False
    assert rss["verdict"] == "reject"

    d2 = evaluate_d1_association_sparse_prefilter_multiseed(
        _build_evidence(
            tmp_path / "d2", candidate_d2_association_wall_s=0.526
        )
    )
    assert d2["admission_gates"][
        "maximum_short_d2_association_mean_increase_pct"
    ]["passed"] is False
    assert d2["admission_gates"][
        "maximum_long_d2_association_mean_increase_pct"
    ]["passed"] is False
    assert d2["verdict"] == "reject"


def test_nonzero_online_truth_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode = _episode(manifest_path, "short_seed_1131", "candidate")
    summary = _read_json(episode / "summary.json")
    governance = _read_json(
        episode / "observation_governance_audit.json"
    )
    summary["online_truth_use_count"] = 1
    governance["online_truth_use_count"] = 1
    _write_json(episode / "summary.json", summary)
    _write_json(
        episode / "observation_governance_audit.json", governance
    )

    result = evaluate_d1_association_sparse_prefilter_multiseed(
        manifest_path
    )

    assert result["availability"]["available"] is False
    assert "online_truth_use_count must be zero" in result[
        "availability"
    ]["reason"]


def _build_evidence(
    tmp_path: Path,
    *,
    candidate_d1_fusion_wall_s: float = 0.98,
    candidate_core_wall_s: float = 9.9,
    candidate_d1_scan_input_wall_s: float = 1.02,
    candidate_d2_association_wall_s: float = 0.51,
    candidate_rss_kib: int = 102_000,
    candidate_non_radar_solves: int = 100,
    candidate_non_radar_rejections: int = 300,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    matrix_bytes = MATRIX_PATH.read_bytes()
    assert hashlib.sha256(matrix_bytes).hexdigest() == (
        D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256
    )
    matrix_path = (tmp_path / "matrix.json").resolve()
    matrix_path.write_bytes(matrix_bytes)
    matrix = _read_json(matrix_path)
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir(parents=True)
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
                core_wall_s=(
                    candidate_core_wall_s if candidate else 10.0
                ),
                real_time_factor=0.51 if candidate else 0.5,
                d1_fusion_wall_s=(
                    candidate_d1_fusion_wall_s if candidate else 1.0
                ),
                d1_scan_input_wall_s=(
                    candidate_d1_scan_input_wall_s
                    if candidate
                    else 1.0
                ),
                d2_association_wall_s=(
                    candidate_d2_association_wall_s if candidate else 0.5
                ),
                candidate_non_radar_solves=(
                    candidate_non_radar_solves if candidate else 400
                ),
                candidate_non_radar_rejections=(
                    candidate_non_radar_rejections if candidate else 0
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
                        + (
                            str(candidate_rss_kib)
                            if candidate
                            else "100000"
                        ),
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
                "validation_kind": "association_sparse_prefilter",
                "expected_commit": (
                    D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT
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
            D1_ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_SCHEMA_VERSION
        ),
        "experiment_id": D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID,
        "matrix_path": str(matrix_path),
        "matrix_sha256": D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256,
        "matrix": matrix,
        "source_worktree": str(ROOT.resolve()),
        "source_commit": D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT,
        "source_repository_dirty": False,
        "output_root": str(evidence_root),
        "required_d6_evaluator_schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "association_sparse_prefilter_execution_config_schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "association_sparse_prefilter_diagnostics_schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "status": "episodes_complete_pending_d6",
        "started_at_utc": "2026-07-25T00:00:00+00:00",
        "completed_at_utc": "2026-07-25T00:01:00+00:00",
        "cases": cases,
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
    core_wall_s: float,
    real_time_factor: float,
    d1_fusion_wall_s: float,
    d1_scan_input_wall_s: float,
    d2_association_wall_s: float,
    candidate_non_radar_solves: int,
    candidate_non_radar_rejections: int,
) -> None:
    episode_dir.mkdir(parents=True)
    candidate = arm == "candidate"
    config = {
        "schema_version": "scalable3d-scenario-v1",
        "scenario_name": "nominal_200v200_cli_200v200",
        "scenario_version": "nominal-200v200-v1-cli-200v200",
        "seed": case["seed"],
        "duration_s": case["duration_s"],
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    execution_config = _execution_config(arm)
    initial = _diagnostics(arm, execution_config, initial=True)
    diagnostics = _diagnostics(
        arm,
        execution_config,
        initial=False,
        non_radar_solves=candidate_non_radar_solves,
        non_radar_rejections=candidate_non_radar_rejections,
    )
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "test_fixture": True,
        SELECTOR_FIELD: implementation,
        CONFIG_FIELD: copy.deepcopy(execution_config),
        DIAGNOSTICS_FIELD: copy.deepcopy(diagnostics),
        "d1_fusion_association": {"association_gate": 40.0},
    }
    stage_values = {
        "module.d1_fusion": d1_fusion_wall_s,
        "module.d1_scan_input": d1_scan_input_wall_s,
        "module.d2_association": d2_association_wall_s,
    }
    module_final = {
        "d1_track_count": 201,
        "d2_track_count": 201,
        "d3_assignment_count": 200,
        "d5_binding_count": 3,
        "d7_command_count": 200,
        SELECTOR_FIELD: implementation,
        CONFIG_FIELD: copy.deepcopy(execution_config),
        DIAGNOSTICS_FIELD: copy.deepcopy(diagnostics),
        "d1_fusion_performance": {
            "association_innovation_solve_count": diagnostics[
                "total_counts"
            ]["exact_innovation_solve_count"]
        },
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
        SELECTOR_FIELD: implementation,
        CONFIG_FIELD: copy.deepcopy(execution_config),
        DIAGNOSTICS_FIELD: copy.deepcopy(diagnostics),
        "module_final_diagnostics": module_final,
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "configuration": {
            "test_fixture": True,
            SELECTOR_FIELD: implementation,
        },
        SELECTOR_FIELD: implementation,
        CONFIG_FIELD: copy.deepcopy(execution_config),
        DIAGNOSTICS_FIELD: initial,
    }
    manifest = {
        "episode_id": episode_id,
        "git_commit": D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT,
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
        episode_dir / "observation_governance_audit.json", governance
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


def _execution_config(arm: str) -> dict[str, Any]:
    candidate = arm == "candidate"
    return {
        "schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION
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
        "candidate_default_enabled": False,
        "reference_selector": REFERENCE_IMPLEMENTATION,
        "reference_implementation_id": REFERENCE_IMPLEMENTATION_ID,
        "candidate_selector": CANDIDATE_IMPLEMENTATION,
        "candidate_implementation_id": CANDIDATE_IMPLEMENTATION_ID,
        "candidate_enabled": candidate,
        "rollback_selector": REFERENCE_IMPLEMENTATION,
        "legacy_radar_lower_bound_gate_enabled": True,
        "modality_order": list(MODALITIES),
        "modality_policies": {
            "radar": "legacy_certified_quadratic_bound_v1",
            "lidar": (
                "certified_exact_residual_quadratic_bound_v1"
                if candidate
                else "exact_reference_innovation_solve_v1"
            ),
            "acoustic": (
                "certified_exact_wrapped_residual_quadratic_bound_v1"
                if candidate
                else "exact_reference_innovation_solve_v1"
            ),
            "acoustic_3d": (
                "certified_exact_wrapped_residual_quadratic_bound_v1"
                if candidate
                else "exact_reference_innovation_solve_v1"
            ),
            "eo": (
                "certified_exact_projection_residual_quadratic_bound_v1"
                if candidate
                else "exact_reference_innovation_solve_v1"
            ),
            "other": "fail_open_exact_reference_v1",
        },
        "truth_dependent_inputs": False,
        "exact_association_gate_changed": False,
    }


def _diagnostics(
    arm: str,
    execution_config: dict[str, Any],
    *,
    initial: bool,
    non_radar_solves: int = 0,
    non_radar_rejections: int = 0,
) -> dict[str, Any]:
    candidate = arm == "candidate"
    zero = {field: 0 for field in COUNTERS}
    modality_counts = {
        modality: copy.deepcopy(zero) for modality in MODALITIES
    }
    if not initial:
        modality_counts["radar"] = {
            "candidate_pair_count": 1000,
            "conservative_prefilter_rejection_count": 900,
            "exact_innovation_solve_count": 100,
            "exact_gate_pass_count": 10,
            "fallback_count": 0,
        }
        modality_counts["eo"] = {
            "candidate_pair_count": 500,
            "conservative_prefilter_rejection_count": (
                non_radar_rejections
            ),
            "exact_innovation_solve_count": non_radar_solves,
            "exact_gate_pass_count": 5,
            "fallback_count": 10 if candidate else 0,
        }
    total_counts = {
        field: sum(
            modality_counts[modality][field] for modality in MODALITIES
        )
        for field in COUNTERS
    }
    conservation = {
        "modalities": {
            modality: {
                "prefilter_rejections_not_above_candidates": True,
                "exact_solves_not_above_candidates": True,
                "exact_gate_passes_not_above_exact_solves": True,
                "fallbacks_not_above_candidates": True,
            }
            for modality in MODALITIES
        },
        "all_counter_bounds_hold": True,
        "fixed_modality_bucket_count": True,
    }
    return {
        "schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "execution_config": copy.deepcopy(execution_config),
        "selector": execution_config["selector"],
        "selected_implementation_id": execution_config[
            "selected_implementation_id"
        ],
        "reference_implementation_id": REFERENCE_IMPLEMENTATION_ID,
        "candidate_implementation_id": CANDIDATE_IMPLEMENTATION_ID,
        "candidate_enabled": candidate,
        "legacy_radar_lower_bound_gate_enabled": True,
        "modality_order": list(MODALITIES),
        "modality_counts": modality_counts,
        "total_counts": total_counts,
        "conservation": conservation,
    }


def _mutate_final_diagnostics(
    episode: Path, mutate: Any
) -> None:
    summary_path = episode / "summary.json"
    governance_path = episode / "observation_governance_audit.json"
    summary = _read_json(summary_path)
    governance = _read_json(governance_path)
    locations = (
        summary[DIAGNOSTICS_FIELD],
        summary["module_final_diagnostics"][DIAGNOSTICS_FIELD],
        summary["module_final_diagnostics"]["observation_governance"][
            DIAGNOSTICS_FIELD
        ],
        governance[DIAGNOSTICS_FIELD],
    )
    for diagnostics in locations:
        mutate(diagnostics)
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
        "--d1-association-sparse-prefilter-implementation",
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


def _episode(manifest_path: Path, case_id: str, arm: str) -> Path:
    return manifest_path.parent / case_id / f"{arm}_episode"


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
