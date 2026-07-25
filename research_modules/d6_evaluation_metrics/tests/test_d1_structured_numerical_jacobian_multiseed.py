from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from d6_evaluation_metrics.d1_structured_numerical_jacobian_multiseed import (
    CANDIDATE_IMPLEMENTATION,
    CANDIDATE_IMPLEMENTATION_ID,
    D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION,
    D1_STRUCTURED_JACOBIAN_EVIDENCE_SCHEMA_VERSION,
    D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID,
    D1_STRUCTURED_JACOBIAN_MATRIX_SHA256,
    D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT,
    D1StructuredJacobianEvidenceError,
    REFERENCE_IMPLEMENTATION,
    REFERENCE_IMPLEMENTATION_ID,
    evaluate_d1_structured_jacobian_multiseed,
    main,
    write_d1_structured_jacobian_multiseed_report,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_structured_numerical_jacobian_multiseed_v1.json"
)
_STAGE_FIELDS = (
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


def test_evaluator_binds_frozen_matrix_and_accepts_13_pairs(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is True
    assert result["schema_version"] == (
        D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_STRUCTURED_JACOBIAN_MATRIX_SHA256
    )
    assert result["input_contract"]["source_commit"] == (
        D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT
    )
    assert len(result["pairs"]) == 13
    assert all(
        pair["business_semantics_passed"] for pair in result["pairs"]
    )
    assert all(
        pair["structured_jacobian_audit_passed"] for pair in result["pairs"]
    )
    assert result["structured_jacobian_diagnostics_aggregate"]["groups"][
        "all"
    ]["candidate_measurement_evaluation_reduction_pct"] > 35.0
    assert all(
        gate["passed"] for gate in result["admission_gates"].values()
    )
    assert result["optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False


def test_report_bundle_is_complete_deterministic_and_read_only(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    before = _tree_fingerprint(manifest_path.parent)
    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    paths = write_d1_structured_jacobian_multiseed_report(
        result, tmp_path / "report"
    )

    assert _tree_fingerprint(manifest_path.parent) == before
    assert set(paths) == {
        "evaluation_json",
        "compact_json",
        "pairs_csv",
        "markdown",
        "sha256sums",
    }
    assert all(path.is_file() for path in paths.values())
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "局部优化准入通过" in markdown
    assert "系统实时缺口未关闭" in markdown
    assert "三维质点仿真" in markdown
    assert "默认实现切换须由 main 另行实施" in markdown
    assert "26/26 complete、0 reused、0 failed" in markdown
    compact = json.loads(paths["compact_json"].read_text(encoding="utf-8"))
    assert "pairs" not in compact
    assert compact["optimization_admitted"] is True

    round_trip = json.loads(
        paths["evaluation_json"].read_text(encoding="utf-8")
    )
    repeated = write_d1_structured_jacobian_multiseed_report(
        round_trip, tmp_path / "report_repeated"
    )
    for name, path in paths.items():
        assert path.read_bytes() == repeated[name].read_bytes()

    with pytest.raises(ValueError, match="independent"):
        write_d1_structured_jacobian_multiseed_report(
            result, manifest_path.parent / "forbidden"
        )


def test_cli_writes_report_and_prints_separate_conclusions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = _build_evidence(tmp_path)
    output = tmp_path / "cli_report"

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
    assert "optimization_admitted: true" in stdout
    assert "system_realtime_gap_closed: false" in stdout
    assert (
        output
        / "d1_structured_numerical_jacobian_multiseed_evaluation.json"
    ).is_file()


def test_missing_evidence_is_unavailable_and_cli_returns_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing" / "evidence_manifest.json"
    result = evaluate_d1_structured_jacobian_multiseed(missing)

    assert result["availability"]["available"] is False
    assert result["optimization_admitted"] is False
    assert result["system_realtime_gap_closed"] is False
    assert result["admission_gates"]["evidence_available"]["passed"] is False

    output = tmp_path / "unavailable_report"
    assert (
        main(
            [
                "--evidence-manifest",
                str(missing),
                "--output-dir",
                str(output),
            ]
        )
        == 2
    )
    stdout = capsys.readouterr().out
    assert "availability: false" in stdout
    markdown = (
        output
        / "D1_STRUCTURED_NUMERICAL_JACOBIAN_MULTISEED_REPORT_CN.md"
    ).read_text(encoding="utf-8")
    assert "正式证据当前不可用" in markdown
    assert "候选 `known_dimension_structural_columns_v1` 保持关闭" in markdown


def test_evidence_schema_mismatch_is_unavailable(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["schema_version"] = "old"
    _write_json(manifest_path, manifest)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is False
    assert "schema_version" in result["availability"]["reason"]


def test_operation_conservation_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["d1_structured_numerical_jacobian_diagnostics"][
        "operation_counts"
    ]["measurement_function_evaluation_count"] = 6_001
    _write_json(summary_path, summary)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is False
    assert "diagnostics mismatch" in result["availability"]["reason"]


def test_missing_diagnostics_field_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
    )
    summary_path = episode / "summary.json"
    governance_path = episode / "observation_governance_audit.json"
    summary = _read_json(summary_path)
    governance = _read_json(governance_path)
    field = "d1_structured_numerical_jacobian_diagnostics"
    locations = (
        summary[field],
        summary["module_final_diagnostics"][field],
        summary["module_final_diagnostics"]["observation_governance"][
            field
        ],
        governance[field],
    )
    for diagnostics in locations:
        diagnostics.pop("implementation_id")
    _write_json(summary_path, summary)
    _write_json(governance_path, governance)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is False
    assert "final diagnostics fields mismatch" in result[
        "availability"
    ]["reason"]


def test_implementation_identity_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["d1_structured_numerical_jacobian_implementation"] = (
        REFERENCE_IMPLEMENTATION
    )
    _write_json(summary_path, summary)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is False
    assert "implementation identity mismatch" in result[
        "availability"
    ]["reason"]


def test_nonregistered_business_change_closes_semantic_gate(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["module_final_diagnostics"]["d2_track_count"] = 202
    _write_json(summary_path, summary)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["pairs"][0]["business_semantics_passed"] is False
    assert result["admission_gates"][
        "all_pairs_business_semantics_equal"
    ]["passed"] is False
    assert result["optimization_admitted"] is False


def test_d1_and_core_gates_reject_small_candidate_gain(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(
        tmp_path,
        candidate_d1_fusion_wall_s=0.995,
        candidate_core_wall_s=9.99,
    )

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["admission_gates"][
        "short_minimum_d1_fusion_improvement_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "long_minimum_d1_fusion_improvement_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "short_minimum_core_wall_improvement_pct"
    ]["passed"] is False
    assert result["optimization_admitted"] is False


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda manifest: manifest.__setitem__(
                "source_repository_dirty", True
            ),
            "source_repository_dirty",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "source_commit", "b" * 40
            ),
            "frozen producer commit",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "structured_jacobian_diagnostics_schema_version", "old"
            ),
            "diagnostics schema",
        ),
    ],
)
def test_manifest_provenance_tamper_fails_closed(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    mutate(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(D1StructuredJacobianEvidenceError, match=match):
        evaluate_d1_structured_jacobian_multiseed(
            manifest_path,
            raise_on_invalid=True,
        )


def test_episode_dirty_state_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode_manifest_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "reference_episode"
        / "manifest.json"
    )
    episode_manifest = _read_json(episode_manifest_path)
    episode_manifest["repository_dirty"] = True
    _write_json(episode_manifest_path, episode_manifest)

    with pytest.raises(
        D1StructuredJacobianEvidenceError, match="repository is dirty"
    ):
        evaluate_d1_structured_jacobian_multiseed(
            manifest_path,
            raise_on_invalid=True,
        )


def test_reused_arm_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["cases"][0]["arms"]["reference"]["status"] = "reused"
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D1StructuredJacobianEvidenceError, match="fresh complete arm"
    ):
        evaluate_d1_structured_jacobian_multiseed(
            manifest_path,
            raise_on_invalid=True,
        )


def test_matrix_byte_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    matrix_path = Path(manifest["matrix_path"])
    matrix = _read_json(matrix_path)
    matrix["cooldown_s"] = 3.0
    _write_json(matrix_path, matrix)

    with pytest.raises(
        D1StructuredJacobianEvidenceError,
        match="does not match matrix_path bytes",
    ):
        evaluate_d1_structured_jacobian_multiseed(
            manifest_path,
            raise_on_invalid=True,
        )


def test_command_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    command = manifest["cases"][0]["arms"]["candidate"]["command"]
    command[command.index("--duration") + 1] = "2.3"
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D1StructuredJacobianEvidenceError,
        match="command differs from frozen execution",
    ):
        evaluate_d1_structured_jacobian_multiseed(
            manifest_path,
            raise_on_invalid=True,
        )


def test_path_boundary_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    outside = (tmp_path / "outside_resource.txt").resolve()
    outside.write_text("Exit status: 0\n", encoding="utf-8")
    manifest["cases"][0]["arms"]["reference"]["resource_path"] = str(
        outside
    )
    _write_json(manifest_path, manifest)

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is False
    assert "strictly under output_root" in result["availability"]["reason"]


def test_measurement_reduction_gate_rejects_valid_low_gain_candidate(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(
        tmp_path,
        candidate_measurement_evaluations=10_000,
        candidate_inactive_elisions=1_000,
    )

    result = evaluate_d1_structured_jacobian_multiseed(manifest_path)

    assert result["availability"]["available"] is True
    assert result["admission_gates"][
        "minimum_candidate_measurement_evaluation_reduction_pct"
    ]["passed"] is False
    assert result["optimization_admitted"] is False


def test_rss_exact_boundary_passes_and_above_boundary_rejects(
    tmp_path: Path,
) -> None:
    boundary = evaluate_d1_structured_jacobian_multiseed(
        _build_evidence(tmp_path / "boundary", candidate_rss_kib=105_000)
    )
    above = evaluate_d1_structured_jacobian_multiseed(
        _build_evidence(tmp_path / "above", candidate_rss_kib=105_001)
    )

    assert boundary["admission_gates"][
        "maximum_any_pair_rss_increase_pct"
    ]["passed"] is True
    assert above["admission_gates"][
        "maximum_any_pair_rss_increase_pct"
    ]["passed"] is False
    assert above["optimization_admitted"] is False


def _build_evidence(
    tmp_path: Path,
    *,
    candidate_d1_fusion_wall_s: float = 0.8,
    candidate_core_wall_s: float = 9.8,
    candidate_d1_scan_input_wall_s: float = 1.02,
    candidate_d2_association_wall_s: float = 0.505,
    candidate_rss_kib: int = 101_000,
    candidate_measurement_evaluations: int = 6_000,
    candidate_inactive_elisions: int = 3_000,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    matrix_bytes = MATRIX_PATH.read_bytes()
    assert hashlib.sha256(matrix_bytes).hexdigest() == (
        D1_STRUCTURED_JACOBIAN_MATRIX_SHA256
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
            implementation = matrix["arm_implementations"][arm]
            episode_dir = case_root / f"{arm}_episode"
            is_candidate = arm == "candidate"
            _write_episode(
                episode_dir,
                case=case,
                arm=arm,
                implementation=implementation,
                core_wall_s=(
                    candidate_core_wall_s if is_candidate else 10.0
                ),
                real_time_factor=0.55 if is_candidate else 0.54,
                d1_fusion_wall_s=(
                    candidate_d1_fusion_wall_s
                    if is_candidate
                    else 1.0
                ),
                d1_scan_input_wall_s=(
                    candidate_d1_scan_input_wall_s
                    if is_candidate
                    else 1.0
                ),
                d2_association_wall_s=(
                    candidate_d2_association_wall_s
                    if is_candidate
                    else 0.5
                ),
                measurement_evaluations=(
                    candidate_measurement_evaluations
                    if is_candidate
                    else 13_000
                ),
                inactive_elisions=(
                    candidate_inactive_elisions if is_candidate else 0
                ),
            )
            resource_path = case_root / f"{arm}_resource_usage.txt"
            stdout_path = case_root / f"{arm}_stdout.log"
            stderr_path = case_root / f"{arm}_stderr.log"
            resource_path.write_text(
                "\n".join(
                    [
                        "Elapsed (wall clock) time (h:mm:ss or m:ss): "
                        + ("0:10.10" if is_candidate else "0:10.20"),
                        "Maximum resident set size (kbytes): "
                        + (
                            str(candidate_rss_kib)
                            if is_candidate
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
            command = _expected_command(
                implementation=implementation,
                duration_s=float(case["duration_s"]),
                seed=int(case["seed"]),
                episode_dir=episode_dir,
            )
            arms[arm] = {
                "arm": arm,
                "expected_implementation": implementation,
                "expected_d1_implementation_id": (
                    CANDIDATE_IMPLEMENTATION_ID
                    if is_candidate
                    else REFERENCE_IMPLEMENTATION_ID
                ),
                "validation_kind": "structured_numerical_jacobian",
                "expected_commit": D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT,
                "episode_dir": str(episode_dir.resolve()),
                "resource_path": str(resource_path.resolve()),
                "stdout_path": str(stdout_path.resolve()),
                "stderr_path": str(stderr_path.resolve()),
                "command": command,
                "status": "complete",
                "return_code": 0,
                "started_at_utc": "2026-07-24T00:00:00+00:00",
                "completed_at_utc": "2026-07-24T00:00:01+00:00",
            }
        cases.append(
            {
                **case,
                "arms": arms,
                "d6_evaluation_status": (
                    "episodes_complete_pending_d6"
                ),
            }
        )
    manifest = {
        "schema_version": D1_STRUCTURED_JACOBIAN_EVIDENCE_SCHEMA_VERSION,
        "experiment_id": D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID,
        "matrix_path": str(matrix_path),
        "matrix_sha256": D1_STRUCTURED_JACOBIAN_MATRIX_SHA256,
        "matrix": matrix,
        "source_worktree": str(ROOT.resolve()),
        "source_commit": D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT,
        "source_repository_dirty": False,
        "output_root": str(evidence_root),
        "required_d6_evaluator_schema_version": (
            D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "structured_jacobian_diagnostics_schema_version": (
            D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "status": "episodes_complete_pending_d6",
        "started_at_utc": "2026-07-24T00:00:00+00:00",
        "completed_at_utc": "2026-07-24T00:01:00+00:00",
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
    measurement_evaluations: int,
    inactive_elisions: int,
) -> None:
    episode_dir.mkdir(parents=True)
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
    candidate = arm == "candidate"
    implementation_id = (
        CANDIDATE_IMPLEMENTATION_ID
        if candidate
        else REFERENCE_IMPLEMENTATION_ID
    )
    initial_diagnostics = {
        "schema_version": (
            D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "implementation_id": implementation_id,
        "candidate_enabled": candidate,
        "operation_counts": {},
        "conservation": {
            "attempt_equals_success_plus_failure": True,
            "attempt_equals_reference_plus_candidate": True,
        },
    }
    attempts = 1_000
    operation_counts = {
        "jacobian_attempt_count": attempts,
        "jacobian_success_count": attempts,
        "jacobian_failure_count": 0,
        "reference_call_count": 0 if candidate else attempts,
        "structured_candidate_call_count": attempts if candidate else 0,
        "output_probe_evaluation_count": 0 if candidate else attempts,
        "output_probe_elision_count": attempts if candidate else 0,
        "inactive_state_column_elision_count": inactive_elisions,
        "measurement_function_evaluation_count": measurement_evaluations,
    }
    diagnostics = {
        "schema_version": (
            D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "implementation_id": implementation_id,
        "candidate_enabled": candidate,
        "operation_counts": operation_counts,
        "conservation": {
            "attempt_equals_success_plus_failure": True,
            "attempt_equals_reference_plus_candidate": True,
        },
    }
    selector_field = (
        "d1_structured_numerical_jacobian_implementation"
    )
    diagnostics_field = (
        "d1_structured_numerical_jacobian_diagnostics"
    )
    runtime_profile = {
        "schema_version": (
            "scalable3d-integrated-stack-runtime-profile-v1"
        ),
        "configuration": {
            "test_fixture": True,
            selector_field: implementation,
        },
        selector_field: implementation,
        diagnostics_field: initial_diagnostics,
    }
    episode_id = f"{case['case_id']}-{arm}"
    manifest = {
        "episode_id": episode_id,
        "git_commit": D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT,
        "repository_dirty": False,
        "seed": case["seed"],
        "config_sha256": _canonical_sha256(config),
        "runtime_profile": runtime_profile,
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
    }
    stage_values = {
        "module.d1_fusion": d1_fusion_wall_s,
        "module.d1_scan_input": d1_scan_input_wall_s,
        "module.d2_association": d2_association_wall_s,
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "test_fixture": True,
        selector_field: implementation,
        diagnostics_field: copy.deepcopy(diagnostics),
    }
    module_final = {
        "d1_track_count": 201,
        "d2_track_count": 201,
        "d3_assignment_count": 200,
        "d5_binding_count": 3,
        "d7_command_count": 200,
        selector_field: implementation,
        diagnostics_field: copy.deepcopy(diagnostics),
        "stage_timings": {
            name: {"wall_time_s": value}
            for name, value in stage_values.items()
        },
        "observation_governance": copy.deepcopy(governance),
    }
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
        selector_field: implementation,
        diagnostics_field: copy.deepcopy(diagnostics),
        "module_final_diagnostics": module_final,
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


def _write_stage_csv(
    path: Path, stage_values: dict[str, float]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=_STAGE_FIELDS, lineterminator="\n"
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
        "--d1-d2-structural-ambiguity-hold",
        "--d1-structured-numerical-jacobian-implementation",
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
