from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from d6_evaluation_metrics.d1_scan_input_multiseed import (
    D1_SCAN_INPUT_MATRIX_SHA256,
    D1_SCAN_INPUT_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1ScanInputEvidenceError,
    _normalized_summary,
    evaluate_d1_scan_input_multiseed,
    write_d1_scan_input_multiseed_report,
)
from research_modules.scalable_3d_simulation.scripts import (
    run_d1_scan_input_matrix as matrix_runner,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_scan_input_multiseed_v1.json"
)
SOURCE_COMMIT = "a" * 40


def test_strict_evaluator_accepts_same_commit_13_pair_evidence(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)

    result = evaluate_d1_scan_input_multiseed(manifest_path)

    assert result["schema_version"] == (
        D1_SCAN_INPUT_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_SCAN_INPUT_MATRIX_SHA256
    )
    assert result["input_contract"]["source_commit"] == SOURCE_COMMIT
    assert len(result["pairs"]) == 13
    assert result["groups"]["short"]["pair_count"] == 10
    assert result["groups"]["long"]["pair_count"] == 3
    assert result["groups"]["short"]["metrics"][
        "d1_scan_input_wall_s"
    ]["candidate_better_count"] == 10
    assert result["groups"]["short"]["metrics"][
        "d1_scan_input_wall_s"
    ]["improvement_pct"]["mean"] == pytest.approx(10.0)
    assert all(
        gate["passed"] for gate in result["admission_gates"].values()
    )
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False
    first = result["pairs"][0]
    assert first["business_semantics_passed"] is True
    assert first["reference"]["execution_config"]["implementation"] == (
        "reference_v1"
    )
    assert first["candidate"]["performance_diagnostics"][
        "implementation"
    ] == "candidate_v2"
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
    result = evaluate_d1_scan_input_multiseed(manifest_path)

    output = tmp_path / "d6_report"
    paths = write_d1_scan_input_multiseed_report(result, output)

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
        write_d1_scan_input_multiseed_report(
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

    with pytest.raises(D1ScanInputEvidenceError, match=match):
        evaluate_d1_scan_input_multiseed(manifest_path)


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
            "short_minimum_scan_input_improvement_pct"
        ] = 4.0
    altered_path = tmp_path / f"altered_{field}.json"
    _write_json(altered_path, altered)
    altered_sha = _file_sha256(altered_path)
    manifest["matrix_path"] = str(altered_path.resolve())
    manifest["matrix_sha256"] = altered_sha
    manifest["matrix"] = altered
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D1ScanInputEvidenceError,
        match="frozen D1 scan-input matrix",
    ):
        evaluate_d1_scan_input_multiseed(manifest_path)


def test_wrong_implementation_identity_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["d1_scan_input_performance_diagnostics"][
        "implementation"
    ] = "reference_v1"
    _write_json(summary_path, summary)

    with pytest.raises(
        D1ScanInputEvidenceError,
        match="implementation identity mismatch",
    ):
        evaluate_d1_scan_input_multiseed(manifest_path)


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

    with pytest.raises(D1ScanInputEvidenceError, match="source commit mismatch"):
        evaluate_d1_scan_input_multiseed(manifest_path)


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

    result = evaluate_d1_scan_input_multiseed(manifest_path)

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

    result = evaluate_d1_scan_input_multiseed(manifest_path)

    pair = result["pairs"][0]
    assert pair["business_semantics"]["checks"][
        "normalized_summary_contract_equal"
    ] is False
    assert pair["business_semantics_passed"] is False
    assert result["d1_optimization_admitted"] is False


def test_missing_scan_input_stage_fails_closed(tmp_path: Path) -> None:
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
        D1ScanInputEvidenceError,
        match="exactly one module.d1_scan_input",
    ):
        evaluate_d1_scan_input_multiseed(manifest_path)


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
        D1ScanInputEvidenceError,
        match="nonfinite JSON constant",
    ):
        evaluate_d1_scan_input_multiseed(manifest_path)


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
        "scenario_name": "d1_scan_input_test",
        "scenario_version": "d1-scan-input-test-v1",
        "seed": seed,
        "duration_s": duration_s,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    execution_config = {
        "schema_version": "d1.scan_input.execution_config.v1",
        "implementation": implementation,
        "candidate_is_default": True,
        "reference_implementation": "reference_v1",
        "candidate_implementation": "candidate_v2",
        "event_time_config": {
            "schema_version": "d1.scan_input.config.v1",
            "max_lateness_s": 0.5,
            "max_buffer_residence_s": 5.0,
            "max_buffered_scans": 1024,
            "max_buffered_observations": 200000,
            "max_claimed_scans": 100000,
            "max_claimed_observation_lineages": 2000000,
        },
    }
    diagnostics = {
        "schema_version": "d1.scan_input.performance_diagnostics.v2",
        "implementation": implementation,
        "validated_frame_reuse_count": 100 if candidate else 0,
        "mutated_frame_rebuild_count": 0,
        "iterable_frame_build_count": 0 if candidate else 100,
        "organizer_observation_snapshot_count": 0 if candidate else 1000,
        "claim_build_count": 100,
        "claim_observation_count": 1000,
        "cached_source_lineage_reuse_count": 100 if candidate else 0,
        "source_lineage_reconstruction_count": 0 if candidate else 100,
        "lineage_sort_key_construction_count": 1000,
        "buffer_partition_pass_count": 100 if candidate else 0,
        "buffer_partition_item_visit_count": 1000 if candidate else 0,
        "buffered_observation_count_cache_read_count": 100 if candidate else 0,
        "buffered_observation_count_rescan_count": 0 if candidate else 100,
        "buffered_observation_count_rescan_item_visit_count": (
            0 if candidate else 1000
        ),
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "module_stack_schema_version": "scalable3d-module-stack-v1",
        "configuration": {
            "d1_scan_input_implementation": implementation,
            "d1_d2_structural_ambiguity_hold_enabled": True,
        },
        "d1_scan_input_implementation": implementation,
        "d1_scan_input_execution_config": copy.deepcopy(execution_config),
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
        "d1_scan_input_implementation": implementation,
        "d1_scan_input_execution_config": copy.deepcopy(execution_config),
        "d1_scan_input_performance_diagnostics": copy.deepcopy(diagnostics),
        "stage_timings": {
            "d1_scan_input": {
                "call_count": 10,
                "wall_time_s": 9.0 if candidate else 10.0,
            }
        },
        "observation_governance": {
            "schema_version": (
                "scalable3d-observation-governance-runtime-v2"
            ),
            "online_truth_use_count": 0,
            "d1_scan_input_implementation": implementation,
            "d1_scan_input_execution_config": copy.deepcopy(execution_config),
            "d1_scan_input_performance_diagnostics": copy.deepcopy(
                diagnostics
            ),
            "d1_scan_input": {
                "schema_version": "d1.scan_input.audit_summary.v1",
                "received_scan_count": 100,
                "released_scan_count": 100,
            },
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
        "wall_time_s": 9.0 if candidate else 10.0,
        "real_time_factor": 0.25 if candidate else 0.22,
        "d1_scan_input_implementation": implementation,
        "d1_scan_input_execution_config": copy.deepcopy(execution_config),
        "d1_scan_input_performance_diagnostics": copy.deepcopy(diagnostics),
        "module_final_diagnostics": module_final,
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "d1_scan_input_implementation": implementation,
        "d1_scan_input_execution_config": copy.deepcopy(execution_config),
        "d1_scan_input_performance_diagnostics": copy.deepcopy(diagnostics),
        "d1_scan_input": {
            "schema_version": "d1.scan_input.audit_summary.v1",
            "received_scan_count": 100,
            "received_observation_count": 1000,
            "released_scan_count": 100,
            "released_observation_count": 1000,
            "rejected_scan_count": 0,
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

    scan_wall = 9.0 if candidate else 10.0
    mean_ms = scan_wall * 1000.0 / 10.0
    (episode_dir / "stage_timings.csv").write_text(
        (
            "schema_version,stage,call_count,wall_time_s,"
            "mean_wall_time_ms,p50_wall_time_ms,p95_wall_time_ms,"
            "max_wall_time_ms,distribution_available,"
            "distribution_unavailable_reason\n"
            f"scalable3d-stage-timings-v2,module.d1_scan_input,10,"
            f"{scan_wall},{mean_ms},{mean_ms * 0.8},{mean_ms * 1.1},"
            f"{mean_ms * 1.2},True,\n"
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
    execution = {
        "schema_version": "d1.scan_input.execution_config.v1",
        "implementation": "reference_v1",
        "candidate_is_default": True,
        "reference_implementation": "reference_v1",
        "candidate_implementation": "candidate_v2",
        "event_time_config": {"max_lateness_s": 0.5},
    }
    diagnostics = {
        "schema_version": "d1.scan_input.performance_diagnostics.v2",
        "implementation": "reference_v1",
        "validated_frame_reuse_count": 0,
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "d1_scan_input_implementation": "reference_v1",
        "d1_scan_input_execution_config": copy.deepcopy(execution),
        "d1_scan_input_performance_diagnostics": copy.deepcopy(diagnostics),
        "d1_scan_input": {
            "received_scan_count": 10,
            "released_scan_count": 10,
        },
    }
    reference = {
        "episode_id": "episode-runtime-profile-reference",
        "wall_time_s": 10.0,
        "real_time_factor": 0.22,
        "d1_scan_input_implementation": "reference_v1",
        "d1_scan_input_execution_config": copy.deepcopy(execution),
        "d1_scan_input_performance_diagnostics": copy.deepcopy(diagnostics),
        "module_final_diagnostics": {
            "d1_scan_input_implementation": "reference_v1",
            "d1_scan_input_execution_config": copy.deepcopy(execution),
            "d1_scan_input_performance_diagnostics": copy.deepcopy(
                diagnostics
            ),
            "stage_timings": {
                "d1_scan_input": {
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
    candidate["wall_time_s"] = 9.0
    candidate["real_time_factor"] = 0.25
    candidate["d1_scan_input_implementation"] = "candidate_v2"
    candidate["d1_scan_input_execution_config"][
        "implementation"
    ] = "candidate_v2"
    candidate["d1_scan_input_performance_diagnostics"][
        "implementation"
    ] = "candidate_v2"
    candidate["d1_scan_input_performance_diagnostics"][
        "validated_frame_reuse_count"
    ] = 10
    final = candidate["module_final_diagnostics"]
    final["d1_scan_input_implementation"] = "candidate_v2"
    final["d1_scan_input_execution_config"][
        "implementation"
    ] = "candidate_v2"
    final["d1_scan_input_performance_diagnostics"][
        "implementation"
    ] = "candidate_v2"
    final["d1_scan_input_performance_diagnostics"][
        "validated_frame_reuse_count"
    ] = 10
    final["stage_timings"]["d1_scan_input"]["wall_time_s"] = 9.0
    nested = final["observation_governance"]
    nested["d1_scan_input_implementation"] = "candidate_v2"
    nested["d1_scan_input_execution_config"][
        "implementation"
    ] = "candidate_v2"
    nested["d1_scan_input_performance_diagnostics"][
        "implementation"
    ] = "candidate_v2"
    nested["d1_scan_input_performance_diagnostics"][
        "validated_frame_reuse_count"
    ] = 10
    return reference, candidate


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
