from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from d6_evaluation_metrics.d1_publication_metadata_multiseed import (
    D1_PUBLICATION_METADATA_MATRIX_SHA256,
    D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1PublicationMetadataEvidenceError,
    _normalized_summary,
    evaluate_d1_publication_metadata_multiseed,
    write_d1_publication_metadata_multiseed_report,
)
from research_modules.scalable_3d_simulation.scripts import (
    run_d1_publication_metadata_matrix as matrix_runner,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_publication_metadata_multiseed_v1.json"
)
SOURCE_COMMIT = "a36f519ed954a9ba8bdc3fe149ba2835da290c39"


def test_strict_evaluator_accepts_same_commit_13_pair_evidence(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)

    result = evaluate_d1_publication_metadata_multiseed(manifest_path)

    assert result["schema_version"] == (
        D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_PUBLICATION_METADATA_MATRIX_SHA256
    )
    assert result["input_contract"]["source_commit"] == SOURCE_COMMIT
    assert len(result["pairs"]) == 13
    assert result["groups"]["short"]["pair_count"] == 10
    assert result["groups"]["long"]["pair_count"] == 3
    assert result["groups"]["short"]["metrics"][
        "d1_fusion_wall_s"
    ]["candidate_better_count"] == 10
    assert result["groups"]["short"]["metrics"][
        "d1_fusion_wall_s"
    ]["improvement_pct"]["mean"] == pytest.approx(20.0)
    assert all(
        gate["passed"] for gate in result["admission_gates"].values()
    )
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False
    first = result["pairs"][0]
    assert first["business_semantics_passed"] is True
    assert first["reference"]["publication_metadata_diagnostics"][
        "implementation_id"
    ] == "d1.publication_metadata.per_track_audit_copy.v1"
    assert first["candidate"]["publication_metadata_diagnostics"][
        "implementation_id"
    ] == "d1.publication_metadata.immutable_shared_audit.v1"
    assert len(first["reference"]["input_file_sha256"]) == 10


def test_real_summary_treatment_whitelist_is_narrow() -> None:
    reference, candidate = _realistic_summary_pair()

    assert _canonical_sha256(_normalized_summary(reference)) == (
        _canonical_sha256(_normalized_summary(candidate))
    )

    candidate["module_final_diagnostics"]["d2_track_count"] = 201
    assert _canonical_sha256(_normalized_summary(reference)) != (
        _canonical_sha256(_normalized_summary(candidate))
    )


def test_report_bundle_is_independent_and_evidence_remains_read_only(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    evidence_root = manifest_path.parent
    before = _tree_fingerprint(evidence_root)
    result = evaluate_d1_publication_metadata_multiseed(manifest_path)

    output = tmp_path / "d6_report"
    paths = write_d1_publication_metadata_multiseed_report(result, output)

    assert _tree_fingerprint(evidence_root) == before
    assert set(paths) == {
        "evaluation_json",
        "aggregate_json",
        "pairs_csv",
        "markdown",
        "plot_png",
    }
    assert all(path.is_file() for path in paths.values())
    assert paths["plot_png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="independent"):
        write_d1_publication_metadata_multiseed_report(
            result,
            evidence_root / "forbidden_d6_output",
        )


@pytest.mark.parametrize(
    "tamper,match",
    [
        (
            lambda manifest: manifest.__setitem__(
                "status", "running"
            ),
            "status must be episodes_complete_pending_d6",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "source_repository_dirty", True
            ),
            "source_repository_dirty",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "matrix_sha256", "0" * 64
            ),
            "matrix_sha256",
        ),
        (
            lambda manifest: manifest["cases"][0]["arms"][
                "reference"
            ].__setitem__("expected_commit", "b" * 40),
            "expected commit",
        ),
    ],
)
def test_manifest_contract_tampering_fails_closed(
    tmp_path: Path,
    tamper: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    tamper(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(D1PublicationMetadataEvidenceError, match=match):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


@pytest.mark.parametrize("field", ["bootstrap_resamples", "admission_gate"])
def test_bootstrap_or_gate_change_fails_frozen_matrix(
    tmp_path: Path,
    field: str,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    altered = copy.deepcopy(manifest["matrix"])
    if field == "bootstrap_resamples":
        altered["bootstrap_resamples"] = 9_999
    else:
        altered["admission_gates"][
            "short_minimum_d1_fusion_improvement_pct"
        ] = 9.0
    altered_path = tmp_path / f"altered_{field}.json"
    _write_json(altered_path, altered)
    altered_sha = _file_sha256(altered_path)
    manifest["matrix_path"] = str(altered_path.resolve())
    manifest["matrix_sha256"] = altered_sha
    manifest["matrix"] = altered
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="frozen D1 publication-metadata matrix",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_wrong_implementation_identity_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["d1_publication_metadata_diagnostics"][
        "implementation_id"
    ] = "d1.publication_metadata.per_track_audit_copy.v1"
    _write_json(summary_path, summary)

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="implementation_id mismatch",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_fake_runtime_selector_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["d1_publication_metadata_implementation"] = "per_track_copy_v1"
    _write_json(summary_path, summary)

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="implementation identity mismatch",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_candidate_copy_operation_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_all_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda item: item["operation_counts"].__setitem__(
            "per_track_shared_audit_mapping_copy_count", 1
        ),
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="candidate per-track copy count must be zero",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_reference_without_copy_operation_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_all_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="reference",
        mutate=lambda item: item["operation_counts"].__setitem__(
            "per_track_shared_audit_mapping_copy_count", 0
        ),
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="reference per-track copy count must be positive",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_candidate_without_shared_reuse_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_all_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda item: item["operation_counts"].__setitem__(
            "shared_audit_value_reuse_count", 0
        ),
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="candidate shared reuse count must be positive",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_materialization_count_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_all_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda item: item["operation_counts"].__setitem__(
            "global_track_metadata_materialization_count", 999
        ),
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="full materialization counts differ",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_candidate_false_immutable_flag_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_all_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda item: item.__setitem__(
            "immutable_shared_publication_metadata", False
        ),
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="immutable publication metadata flag mismatch",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_episode_source_commit_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode_manifest_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "reference_episode"
        / "manifest.json"
    )
    episode_manifest = _read_json(episode_manifest_path)
    episode_manifest["git_commit"] = "b" * 40
    _write_json(episode_manifest_path, episode_manifest)

    with pytest.raises(D1PublicationMetadataEvidenceError, match="source commit mismatch"):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_online_truth_leak_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["online_truth_use_count"] = 1
    _write_json(summary_path, summary)

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="online_truth_use_count must be zero",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_failed_arm_return_code_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    manifest["cases"][0]["arms"]["candidate"]["return_code"] = 1
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="return_code must be integer zero",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_unregistered_stderr_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    stderr_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_stderr.log"
    )
    stderr_path.write_text("unexpected runtime warning\n", encoding="utf-8")

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="unregistered diagnostic",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_rss_gate_failure_rejects_admission(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    for case_dir in manifest_path.parent.glob("*_seed_*"):
        resource = case_dir / "candidate_resource_usage.txt"
        text = resource.read_text(encoding="utf-8")
        resource.write_text(
            text.replace(
                "Maximum resident set size (kbytes): 1000",
                "Maximum resident set size (kbytes): 1200",
            ),
            encoding="utf-8",
        )

    result = evaluate_d1_publication_metadata_multiseed(manifest_path)

    assert result["d1_optimization_admitted"] is False
    assert result["admission_gates"][
        "rss_mean_degradation_within_5_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "every_pair_rss_degradation_within_5_pct"
    ]["passed"] is False


def test_performance_and_bootstrap_gate_failure_rejects_admission(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    for case_dir in manifest_path.parent.glob("*_seed_*"):
        _replace_stage_wall(
            case_dir / "candidate_episode" / "stage_timings.csv",
            "module.d1_fusion",
            10.0,
        )

    result = evaluate_d1_publication_metadata_multiseed(manifest_path)

    assert result["d1_optimization_admitted"] is False
    assert result["admission_gates"][
        "short_d1_fusion_mean_improvement_at_least_10_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "short_d1_fusion_bootstrap_raw_ci_upper_below_zero"
    ]["passed"] is False


def test_bootstrap_is_deterministic(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)

    first = evaluate_d1_publication_metadata_multiseed(manifest_path)
    second = evaluate_d1_publication_metadata_multiseed(manifest_path)

    first_ci = first["groups"]["short"]["metrics"]["d1_fusion_wall_s"][
        "raw_relative_change"
    ]["bootstrap_95_ci"]
    second_ci = second["groups"]["short"]["metrics"]["d1_fusion_wall_s"][
        "raw_relative_change"
    ]["bootstrap_95_ci"]
    assert first_ci == second_ci
    assert first_ci["upper"] < 0.0


def test_semantic_mismatch_returns_failed_admission(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    online_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "online_observations.jsonl"
    )
    records = [
        json.loads(line)
        for line in online_path.read_text(encoding="utf-8").splitlines()
    ]
    records[0]["payload"]["measurement_count"] = 2
    online_path.write_text(
        "".join(
            json.dumps(record, sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )

    result = evaluate_d1_publication_metadata_multiseed(manifest_path)

    pair = result["pairs"][0]
    assert pair["business_semantics_passed"] is False
    assert pair["business_semantics"]["checks"][
        "cross_build_required_checks_passed"
    ] is False
    assert result["admission_gates"][
        "all_pairs_business_semantics_equal"
    ]["passed"] is False
    assert result["d1_optimization_admitted"] is False


def test_non_whitelisted_summary_business_change_fails_admission(
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
    summary["module_final_diagnostics"]["d2_track_count"] = 201
    _write_json(summary_path, summary)

    result = evaluate_d1_publication_metadata_multiseed(manifest_path)

    pair = result["pairs"][0]
    assert pair["business_semantics"]["checks"][
        "normalized_summary_contract_equal"
    ] is False
    assert pair["business_semantics_passed"] is False
    assert result["d1_optimization_admitted"] is False


def test_missing_d1_fusion_stage_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    timing_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "stage_timings.csv"
    )
    timing_path.write_text(
        (
            "schema_version,stage,call_count,wall_time_s,"
            "mean_wall_time_ms,p50_wall_time_ms,p95_wall_time_ms,"
            "max_wall_time_ms,distribution_available,"
            "distribution_unavailable_reason\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="exactly one module.d1_fusion",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def test_nonfinite_json_number_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["wall_time_s"] = float("nan")
    summary_path.write_text(
        json.dumps(summary, allow_nan=True),
        encoding="utf-8",
    )

    with pytest.raises(
        D1PublicationMetadataEvidenceError,
        match="nonfinite JSON constant",
    ):
        evaluate_d1_publication_metadata_multiseed(manifest_path)


def _build_evidence(tmp_path: Path) -> Path:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir(parents=True)
    manifest = matrix_runner.planned_evidence_manifest(
        MATRIX_PATH,
        matrix,
        ROOT,
        SOURCE_COMMIT,
        evidence_root,
    )
    manifest["status"] = "episodes_complete_pending_d6"
    manifest["started_at_utc"] = "2026-07-24T00:00:00+00:00"
    manifest["completed_at_utc"] = "2026-07-24T01:00:00+00:00"
    for case in manifest["cases"]:
        case["d6_evaluation_status"] = "episodes_complete_pending_d6"
        for arm in ("reference", "candidate"):
            record = case["arms"][arm]
            record["status"] = "complete"
            record["return_code"] = 0
            record["started_at_utc"] = "2026-07-24T00:00:00+00:00"
            record["completed_at_utc"] = "2026-07-24T00:01:00+00:00"
            episode_dir = Path(record["episode_dir"])
            episode_dir.mkdir(parents=True)
            _write_episode(
                episode_dir,
                implementation=record["expected_implementation"],
                seed=int(case["seed"]),
                duration_s=float(case["duration_s"]),
                candidate=(arm == "candidate"),
            )
            resource_path = Path(record["resource_path"])
            resource_path.write_text(
                _resource_text(candidate=(arm == "candidate")),
                encoding="utf-8",
            )
            Path(record["stdout_path"]).write_text("", encoding="utf-8")
            Path(record["stderr_path"]).write_text("", encoding="utf-8")
    manifest_path = evidence_root / "evidence_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _write_episode(
    episode_dir: Path,
    *,
    implementation: str,
    seed: int,
    duration_s: float,
    candidate: bool,
) -> None:
    config = {
        "scenario_name": "d1_publication_metadata_test",
        "scenario_version": "d1-publication-metadata-test-v1",
        "seed": seed,
        "duration_s": duration_s,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    operation_counts = {
        "global_track_metadata_materialization_count": 1000,
        "global_tracks_call_count": 10,
        "shared_publication_context_build_count": 10,
    }
    if candidate:
        operation_counts.update(
            {
                "immutable_shared_mapping_build_count": 100,
                "immutable_shared_tuple_build_count": 110,
                "shared_audit_value_reuse_count": 3000,
            }
        )
        implementation_id = (
            "d1.publication_metadata.immutable_shared_audit.v1"
        )
    else:
        operation_counts[
            "per_track_shared_audit_mapping_copy_count"
        ] = 30_000
        implementation_id = (
            "d1.publication_metadata.per_track_audit_copy.v1"
        )
    diagnostics = {
        "implementation_id": implementation_id,
        "immutable_shared_publication_metadata": candidate,
        "operation_counts": operation_counts,
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "module_stack_schema_version": "scalable3d-module-stack-v1",
        "configuration": {
            "d1_publication_metadata_implementation": implementation,
            "d1_d2_structural_ambiguity_hold_enabled": True,
        },
        "d1_publication_metadata_implementation": implementation,
    }
    manifest = {
        "git_commit": SOURCE_COMMIT,
        "repository_dirty": False,
        "config_sha256": _canonical_sha256(config),
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
        "runtime_profile": runtime_profile,
        "seed": seed,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
    }
    module_final = {
        "d1_publication_metadata_implementation": implementation,
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "stage_timings": {
            "d1_fusion": {
                "call_count": 10,
                "wall_time_s": 8.0 if candidate else 10.0,
            }
        },
        "observation_governance": {
            "schema_version": (
                "scalable3d-observation-governance-runtime-v2"
            ),
            "online_truth_use_count": 0,
            "d1_publication_metadata_implementation": implementation,
            "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        },
        "d2_track_count": 200,
    }
    summary = {
        "episode_id": f"episode-{implementation}-{seed}",
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": seed,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "simulated_duration_s": duration_s,
        "finite_state": True,
        "online_truth_use_count": 0,
        "wall_time_s": 8.0 if candidate else 10.0,
        "real_time_factor": 0.25 if candidate else 0.22,
        "d1_publication_metadata_implementation": implementation,
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "module_final_diagnostics": module_final,
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "d1_publication_metadata_implementation": implementation,
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "d1_fusion_association": {
            "association_innovation_solve_count": 20,
        },
        "d1_scan_events": [],
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        _write_json(episode_dir / name, payload)

    stage_walls = {
        "module.d1_fusion": 8.0 if candidate else 10.0,
        "module.d1_scan_input": 1.0,
        "module.d2_association": 1.0,
        "module.d3_assignment": 1.0,
        "module.d5_active_vision": 1.0,
        "module.d7_guidance": 1.0,
        "module_publication_bus": 1.0,
    }
    stage_lines = []
    for stage_name, wall_s in stage_walls.items():
        mean_ms = wall_s * 100.0
        stage_lines.append(
            f"scalable3d-stage-timings-v2,{stage_name},10,"
            f"{wall_s},{mean_ms},{mean_ms * 0.8},{mean_ms * 1.1},"
            f"{mean_ms * 1.2},True,"
        )
    (episode_dir / "stage_timings.csv").write_text(
        (
            "schema_version,stage,call_count,wall_time_s,"
            "mean_wall_time_ms,p50_wall_time_ms,p95_wall_time_ms,"
            "max_wall_time_ms,distribution_available,"
            "distribution_unavailable_reason\n"
            + "\n".join(stage_lines)
            + "\n"
        ),
        encoding="utf-8",
    )
    plan_id = f"{implementation}-plan-{seed}"
    records = [
        {
            "schema_version": "sensor-v1",
            "sequence": 1,
            "timestamp": 0.0,
            "topic": "sensor.observations",
            "source": "sensor",
            "payload": {"measurement_count": 1},
        },
        {
            "schema_version": "d1-v1",
            "sequence": 2,
            "timestamp": 0.1,
            "topic": "modules.d1.fused_tracks",
            "source": "D1",
            "payload": {
                "tracks": [],
                "summary": {
                    "association_innovation_solve_count": (
                        10 if candidate else 20
                    )
                },
            },
        },
        {
            "schema_version": "d3-v1",
            "sequence": 3,
            "timestamp": 0.2,
            "topic": "modules.d3.assignment_plan",
            "source": "D3",
            "payload": {
                "plan_id": plan_id,
                "plan_version": 1,
                "assignments": [],
            },
        },
    ]
    (episode_dir / "online_observations.jsonl").write_text(
        "".join(
            json.dumps(record, sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )
    (episode_dir / "offline_truth_labels.jsonl").write_text(
        json.dumps({"target_id": "T001", "class": "intruder"}) + "\n",
        encoding="utf-8",
    )
    (episode_dir / "offline_proximity_intercepts.jsonl").write_text(
        json.dumps({"target_id": "T001", "distance_m": 50.0}) + "\n",
        encoding="utf-8",
    )
    np.savez(
        episode_dir / "offline_truth_state.npz",
        position=np.array([[1.0, 2.0, 3.0]], dtype=np.float64),
    )


def _resource_text(*, candidate: bool) -> str:
    elapsed = "0:09.00" if candidate else "0:10.00"
    return (
        f"\tElapsed (wall clock) time (h:mm:ss or m:ss): {elapsed}\n"
        "\tMaximum resident set size (kbytes): 1000\n"
        "\tExit status: 0\n"
    )


def _realistic_summary_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostics = {
        "implementation_id": (
            "d1.publication_metadata.per_track_audit_copy.v1"
        ),
        "immutable_shared_publication_metadata": False,
        "operation_counts": {
            "global_track_metadata_materialization_count": 100,
            "global_tracks_call_count": 10,
            "shared_publication_context_build_count": 10,
            "per_track_shared_audit_mapping_copy_count": 3000,
        },
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "d1_publication_metadata_implementation": "per_track_copy_v1",
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
    }
    reference = {
        "episode_id": "episode-runtime-profile-reference",
        "wall_time_s": 10.0,
        "real_time_factor": 0.22,
        "d1_publication_metadata_implementation": "per_track_copy_v1",
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "module_final_diagnostics": {
            "d1_publication_metadata_implementation": "per_track_copy_v1",
            "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
            "stage_timings": {
                "d1_fusion": {
                    "call_count": 10,
                    "wall_time_s": 10.0,
                },
                "d2_association": {
                    "call_count": 2,
                    "wall_time_s": 0.5,
                },
            },
            "observation_governance": copy.deepcopy(governance),
            "d2_track_count": 200,
            "d3_assignment_count": 200,
        },
    }
    candidate = copy.deepcopy(reference)
    candidate["episode_id"] = "episode-runtime-profile-candidate"
    candidate["wall_time_s"] = 8.0
    candidate["real_time_factor"] = 0.25
    candidate["d1_publication_metadata_implementation"] = (
        "immutable_shared_v1"
    )
    candidate_diagnostics = {
        "implementation_id": (
            "d1.publication_metadata.immutable_shared_audit.v1"
        ),
        "immutable_shared_publication_metadata": True,
        "operation_counts": {
            "global_track_metadata_materialization_count": 100,
            "global_tracks_call_count": 10,
            "shared_publication_context_build_count": 10,
            "immutable_shared_mapping_build_count": 30,
            "immutable_shared_tuple_build_count": 40,
            "shared_audit_value_reuse_count": 300,
        },
    }
    candidate["d1_publication_metadata_diagnostics"] = copy.deepcopy(
        candidate_diagnostics
    )
    final = candidate["module_final_diagnostics"]
    final["d1_publication_metadata_implementation"] = "immutable_shared_v1"
    final["d1_publication_metadata_diagnostics"] = copy.deepcopy(
        candidate_diagnostics
    )
    final["stage_timings"]["d1_fusion"]["wall_time_s"] = 8.0
    nested = final["observation_governance"]
    nested["d1_publication_metadata_implementation"] = "immutable_shared_v1"
    nested["d1_publication_metadata_diagnostics"] = copy.deepcopy(
        candidate_diagnostics
    )
    return reference, candidate


def _mutate_all_diagnostics(
    manifest_path: Path,
    *,
    case_id: str,
    arm: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    episode = manifest_path.parent / case_id / f"{arm}_episode"
    summary_path = episode / "summary.json"
    governance_path = episode / "observation_governance_audit.json"
    summary = _read_json(summary_path)
    governance = _read_json(governance_path)
    locations = (
        summary["d1_publication_metadata_diagnostics"],
        summary["module_final_diagnostics"][
            "d1_publication_metadata_diagnostics"
        ],
        summary["module_final_diagnostics"]["observation_governance"][
            "d1_publication_metadata_diagnostics"
        ],
        governance["d1_publication_metadata_diagnostics"],
    )
    for diagnostics in locations:
        mutate(diagnostics)
    _write_json(summary_path, summary)
    _write_json(governance_path, governance)


def _replace_stage_wall(
    path: Path,
    stage_name: str,
    wall_s: float,
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    output = [lines[0]]
    for line in lines[1:]:
        fields = line.split(",")
        if fields[1] == stage_name:
            call_count = int(fields[2])
            mean_ms = wall_s * 1000.0 / call_count
            fields[3:8] = [
                str(wall_s),
                str(mean_ms),
                str(mean_ms * 0.8),
                str(mean_ms * 1.1),
                str(mean_ms * 1.2),
            ]
        output.append(",".join(fields))
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _tree_fingerprint(root: Path) -> dict[str, tuple[str, int]]:
    return {
        str(path.relative_to(root)): (
            _file_sha256(path),
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: Any) -> None:
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
