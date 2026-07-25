from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from d6_evaluation_metrics.d1_cv_motion_model_cache_multiseed import (
    CACHE_CAPACITY,
    CANDIDATE_IMPLEMENTATION,
    CANDIDATE_IMPLEMENTATION_ID,
    D1_CV_MOTION_MODEL_CACHE_EVIDENCE_SCHEMA_VERSION,
    D1_CV_MOTION_MODEL_CACHE_EXPERIMENT_ID,
    D1_CV_MOTION_MODEL_CACHE_MATRIX_SHA256,
    D1_CV_MOTION_MODEL_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1_CV_MOTION_MODEL_CACHE_SOURCE_COMMIT,
    D1CVMotionModelCacheEvidenceError,
    REFERENCE_IMPLEMENTATION,
    REFERENCE_IMPLEMENTATION_ID,
    evaluate_d1_cv_motion_model_cache_multiseed,
    write_d1_cv_motion_model_cache_multiseed_report,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_cv_motion_model_cache_multiseed_v1.json"
)


def test_cache_evaluator_binds_frozen_matrix_and_accepts_13_pairs(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)

    result = evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)

    assert result["schema_version"] == (
        D1_CV_MOTION_MODEL_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_CV_MOTION_MODEL_CACHE_MATRIX_SHA256
    )
    assert result["input_contract"]["source_commit"] == (
        D1_CV_MOTION_MODEL_CACHE_SOURCE_COMMIT
    )
    assert len(result["pairs"]) == 13
    assert all(
        pair["business_semantics_passed"] for pair in result["pairs"]
    )
    assert all(
        pair["cv_motion_model_cache_audit_passed"]
        for pair in result["pairs"]
    )
    assert result["cache_diagnostics_aggregate"]["groups"]["all"][
        "candidate_model_build_reduction_pct"
    ] > 99.0
    assert result["cache_diagnostics_aggregate"]["groups"]["all"][
        "candidate_cache_hit_ratio_pct"
    ] > 99.0
    assert all(gate["passed"] for gate in result["admission_gates"].values())
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False


def test_cache_report_bundle_is_complete_deterministic_and_read_only(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    before = _tree_fingerprint(manifest_path.parent)
    result = evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)

    paths = write_d1_cv_motion_model_cache_multiseed_report(
        result,
        tmp_path / "report",
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
    assert paths["plot_png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "D1 局部优化准入通过" in markdown
    assert "系统实时缺口未关闭" in markdown
    assert "三维质点仿真证据" in markdown
    compact = json.loads(paths["compact_json"].read_text(encoding="utf-8"))
    assert "pairs" not in compact
    assert compact["d1_optimization_admitted"] is True

    round_trip = json.loads(
        paths["evaluation_json"].read_text(encoding="utf-8")
    )
    repeated = write_d1_cv_motion_model_cache_multiseed_report(
        round_trip,
        tmp_path / "report_repeated",
    )
    for name, path in paths.items():
        assert path.read_bytes() == repeated[name].read_bytes()

    with pytest.raises(ValueError, match="independent"):
        write_d1_cv_motion_model_cache_multiseed_report(
            result,
            manifest_path.parent / "forbidden",
        )


def test_candidate_request_conservation_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_final_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda diagnostics: diagnostics["operation_counts"].__setitem__(
            "prediction_request_count",
            100_001,
        ),
    )

    with pytest.raises(
        D1CVMotionModelCacheEvidenceError,
        match="request conservation",
    ):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


def test_candidate_model_build_conservation_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    _mutate_final_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda diagnostics: diagnostics["operation_counts"].__setitem__(
            "model_build_count",
            501,
        ),
    )

    with pytest.raises(
        D1CVMotionModelCacheEvidenceError,
        match="model build conservation",
    ):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


def test_reference_cache_activity_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)

    def add_reference_hit(diagnostics: dict[str, Any]) -> None:
        operations = diagnostics["operation_counts"]
        operations["cache_hit_count"] = 1
        operations["model_build_count"] -= 1

    _mutate_final_diagnostics(
        manifest_path,
        case_id="short_seed_1101",
        arm="reference",
        mutate=add_reference_hit,
    )

    with pytest.raises(
        D1CVMotionModelCacheEvidenceError,
        match="reference unexpectedly reports cache activity",
    ):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


def test_cache_capacity_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
    )
    manifest_file = episode / "manifest.json"
    manifest = _read_json(manifest_file)
    profile = manifest["runtime_profile"]
    profile["configuration"]["d1_cv_motion_model_cache_capacity"] = 127
    manifest["runtime_profile_sha256"] = _canonical_sha256(profile)
    _write_json(manifest_file, manifest)

    with pytest.raises(
        D1CVMotionModelCacheEvidenceError,
        match="runtime cache capacity mismatch",
    ):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


def test_cache_implementation_identity_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)
    episode = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
    )
    summary_path = episode / "summary.json"
    summary = _read_json(summary_path)
    summary["module_final_diagnostics"][
        "d1_cv_motion_model_implementation"
    ] = REFERENCE_IMPLEMENTATION
    _write_json(summary_path, summary)

    with pytest.raises(
        D1CVMotionModelCacheEvidenceError,
        match="implementation identity mismatch",
    ):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


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
    summary["module_final_diagnostics"]["d2_track_count"] = 201
    _write_json(summary_path, summary)

    result = evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)

    assert result["pairs"][0]["business_semantics_passed"] is False
    assert result["admission_gates"][
        "all_pairs_business_semantics_equal"
    ]["passed"] is False
    assert result["d1_optimization_admitted"] is False


def test_cache_efficiency_gates_reject_low_hit_candidate(
    tmp_path: Path,
) -> None:
    manifest_path = _build_evidence(tmp_path)

    def lower_hit_ratio(diagnostics: dict[str, Any]) -> None:
        operations = diagnostics["operation_counts"]
        operations["cache_hit_count"] = 89_000
        operations["cache_miss_count"] = 10_000
        operations["model_build_count"] = 10_000

    for case_dir in manifest_path.parent.glob("*_seed_*"):
        _mutate_final_diagnostics_for_episode(
            case_dir / "candidate_episode",
            lower_hit_ratio,
        )

    result = evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)

    assert result["admission_gates"][
        "minimum_candidate_model_build_reduction_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "minimum_candidate_cache_hit_ratio_pct"
    ]["passed"] is False
    assert result["d1_optimization_admitted"] is False


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda manifest: manifest.__setitem__(
                "source_repository_dirty",
                True,
            ),
            "source_repository_dirty",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "source_commit",
                "b" * 40,
            ),
            "frozen source_commit",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "cv_motion_model_cache_capacity",
                64,
            ),
            "cache evidence capacity",
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

    with pytest.raises(D1CVMotionModelCacheEvidenceError, match=match):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


def test_matrix_byte_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    matrix_path = Path(manifest["matrix_path"])
    matrix = _read_json(matrix_path)
    matrix["cooldown_s"] = 3.0
    _write_json(matrix_path, matrix)

    with pytest.raises(
        D1CVMotionModelCacheEvidenceError,
        match="does not match matrix_path bytes",
    ):
        evaluate_d1_cv_motion_model_cache_multiseed(manifest_path)


def _build_evidence(tmp_path: Path) -> Path:
    matrix_bytes = MATRIX_PATH.read_bytes()
    assert hashlib.sha256(matrix_bytes).hexdigest() == (
        D1_CV_MOTION_MODEL_CACHE_MATRIX_SHA256
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
            implementation_id = (
                REFERENCE_IMPLEMENTATION_ID
                if arm == "reference"
                else CANDIDATE_IMPLEMENTATION_ID
            )
            episode_dir = case_root / f"{arm}_episode"
            resource_path = case_root / f"{arm}_resource_usage.txt"
            stdout_path = case_root / f"{arm}_stdout.log"
            stderr_path = case_root / f"{arm}_stderr.log"
            arms[arm] = {
                "arm": arm,
                "expected_implementation": implementation,
                "expected_d1_implementation_id": implementation_id,
                "validation_kind": "cv_motion_model_cache",
                "expected_commit": D1_CV_MOTION_MODEL_CACHE_SOURCE_COMMIT,
                "episode_dir": str(episode_dir),
                "resource_path": str(resource_path),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "command": _episode_command(
                    implementation=implementation,
                    duration_s=float(case["duration_s"]),
                    seed=int(case["seed"]),
                    episode_dir=episode_dir,
                ),
                "status": "complete",
                "return_code": 0,
                "started_at_utc": "2026-07-24T00:00:00+00:00",
                "completed_at_utc": "2026-07-24T00:01:00+00:00",
            }
            episode_dir.mkdir(parents=True)
            _write_episode(
                episode_dir,
                implementation=implementation,
                seed=int(case["seed"]),
                duration_s=float(case["duration_s"]),
                candidate=(arm == "candidate"),
            )
            resource_path.write_text(_resource_text(), encoding="utf-8")
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
        cases.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "seed": case["seed"],
                "duration_s": case["duration_s"],
                "arm_order": list(case["arm_order"]),
                "arms": arms,
                "d6_evaluation_status": (
                    "episodes_complete_pending_d6"
                ),
            }
        )
    manifest = {
        "schema_version": (
            D1_CV_MOTION_MODEL_CACHE_EVIDENCE_SCHEMA_VERSION
        ),
        "experiment_id": D1_CV_MOTION_MODEL_CACHE_EXPERIMENT_ID,
        "matrix_path": str(matrix_path),
        "matrix_sha256": D1_CV_MOTION_MODEL_CACHE_MATRIX_SHA256,
        "matrix": matrix,
        "source_worktree": str(ROOT.resolve()),
        "source_commit": D1_CV_MOTION_MODEL_CACHE_SOURCE_COMMIT,
        "source_repository_dirty": False,
        "output_root": str(evidence_root),
        "required_d6_evaluator_schema_version": (
            D1_CV_MOTION_MODEL_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "cv_motion_model_cache_capacity": CACHE_CAPACITY,
        "cv_motion_model_cache_diagnostics_schema_version": (
            "d1.cv_motion_model_cache_diagnostics.v1"
        ),
        "status": "episodes_complete_pending_d6",
        "started_at_utc": "2026-07-24T00:00:00+00:00",
        "completed_at_utc": "2026-07-24T01:00:00+00:00",
        "cases": cases,
    }
    manifest_path = evidence_root / "evidence_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _episode_command(
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
        "--d1-cv-motion-model-implementation",
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
        str(episode_dir),
    ]


def _write_episode(
    episode_dir: Path,
    *,
    implementation: str,
    seed: int,
    duration_s: float,
    candidate: bool,
) -> None:
    config = {
        "scenario_name": "d1_cv_motion_model_cache_test",
        "scenario_version": "d1-cv-motion-model-cache-test-v1",
        "seed": seed,
        "duration_s": duration_s,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    implementation_id = (
        CANDIDATE_IMPLEMENTATION_ID
        if candidate
        else REFERENCE_IMPLEMENTATION_ID
    )
    initial_diagnostics = {
        "schema_version": "d1.cv_motion_model_cache_diagnostics.v1",
        "implementation_id": implementation_id,
        "candidate_enabled": candidate,
        "cache_capacity": CACHE_CAPACITY,
        "cache_entry_count": 0,
        "operation_counts": {},
    }
    if candidate:
        operation_counts = {
            "prediction_request_count": 100_000,
            "model_build_count": 500,
            "nonpositive_dt_reference_bypass_count": 1_000,
            "cache_hit_count": 98_500,
            "cache_miss_count": 500,
            "peak_entry_count": 8,
        }
        cache_entry_count = 8
    else:
        operation_counts = {
            "prediction_request_count": 100_000,
            "model_build_count": 99_000,
            "nonpositive_dt_reference_bypass_count": 1_000,
        }
        cache_entry_count = 0
    diagnostics = {
        "schema_version": "d1.cv_motion_model_cache_diagnostics.v1",
        "implementation_id": implementation_id,
        "candidate_enabled": candidate,
        "cache_capacity": CACHE_CAPACITY,
        "cache_entry_count": cache_entry_count,
        "operation_counts": operation_counts,
    }
    publication_diagnostics = {
        "implementation_id": (
            "d1.publication_metadata.immutable_shared_audit.v2"
        ),
        "immutable_shared_publication_metadata": True,
        "publication_audit_contract_version": (
            "d1.publication_audit_tree.v2"
        ),
        "operation_counts": {
            "global_track_metadata_materialization_count": 1000,
            "global_tracks_call_count": 10,
            "shared_publication_context_build_count": 10,
            "immutable_shared_contract_validation_count": 30,
            "immutable_shared_contract_validated_node_count": 1000,
            "shared_audit_value_reuse_count": 3000,
        },
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "module_stack_schema_version": "scalable3d-module-stack-v1",
        "configuration": {
            "d1_publication_metadata_implementation": (
                "immutable_shared_v2"
            ),
            "d1_cv_motion_model_implementation": implementation,
            "d1_cv_motion_model_cache_capacity": CACHE_CAPACITY,
            "d1_d2_structural_ambiguity_hold_enabled": True,
        },
        "d1_publication_metadata_implementation": "immutable_shared_v2",
        "d1_cv_motion_model_implementation": implementation,
        "d1_cv_motion_model_cache_diagnostics": initial_diagnostics,
    }
    manifest = {
        "git_commit": D1_CV_MOTION_MODEL_CACHE_SOURCE_COMMIT,
        "repository_dirty": False,
        "config_sha256": _canonical_sha256(config),
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
        "runtime_profile": runtime_profile,
        "seed": seed,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
    }
    governance = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "online_truth_use_count": 0,
        "d1_publication_metadata_implementation": "immutable_shared_v2",
        "d1_publication_metadata_diagnostics": copy.deepcopy(
            publication_diagnostics
        ),
        "d1_cv_motion_model_implementation": implementation,
        "d1_cv_motion_model_cache_diagnostics": copy.deepcopy(diagnostics),
        "d1_scan_events": [],
    }
    module_final = {
        "d1_publication_metadata_implementation": "immutable_shared_v2",
        "d1_publication_metadata_diagnostics": copy.deepcopy(
            publication_diagnostics
        ),
        "d1_cv_motion_model_implementation": implementation,
        "d1_cv_motion_model_cache_diagnostics": copy.deepcopy(diagnostics),
        "stage_timings": {
            "d1_fusion": {
                "call_count": 10,
                "wall_time_s": 8.0 if candidate else 10.0,
            }
        },
        "observation_governance": copy.deepcopy(governance),
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
        "d1_publication_metadata_implementation": "immutable_shared_v2",
        "d1_publication_metadata_diagnostics": copy.deepcopy(
            publication_diagnostics
        ),
        "d1_cv_motion_model_implementation": implementation,
        "d1_cv_motion_model_cache_diagnostics": copy.deepcopy(diagnostics),
        "module_final_diagnostics": module_final,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        _write_json(episode_dir / name, payload)
    _write_stage_timings(episode_dir / "stage_timings.csv", candidate)
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
            "payload": {"tracks": [], "summary": {}},
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
            json.dumps(item, sort_keys=True) + "\n" for item in records
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


def _write_stage_timings(path: Path, candidate: bool) -> None:
    walls = {
        "module.d1_fusion": 8.0 if candidate else 10.0,
        "module.d1_scan_input": 1.0,
        "module.d2_association": 1.02 if candidate else 1.0,
        "module.d3_assignment": 1.0,
        "module.d5_active_vision": 1.0,
        "module.d7_guidance": 1.0,
        "module_publication_bus": 1.0,
    }
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            (
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
        )
        for stage, wall_s in walls.items():
            mean_ms = wall_s * 100.0
            writer.writerow(
                (
                    "scalable3d-stage-timings-v2",
                    stage,
                    10,
                    wall_s,
                    mean_ms,
                    mean_ms * 0.8,
                    mean_ms * 1.1,
                    mean_ms * 1.2,
                    True,
                    "",
                )
            )


def _mutate_final_diagnostics(
    manifest_path: Path,
    *,
    case_id: str,
    arm: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    _mutate_final_diagnostics_for_episode(
        manifest_path.parent / case_id / f"{arm}_episode",
        mutate,
    )


def _mutate_final_diagnostics_for_episode(
    episode: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    summary_path = episode / "summary.json"
    governance_path = episode / "observation_governance_audit.json"
    summary = _read_json(summary_path)
    governance = _read_json(governance_path)
    locations = (
        summary["d1_cv_motion_model_cache_diagnostics"],
        summary["module_final_diagnostics"][
            "d1_cv_motion_model_cache_diagnostics"
        ],
        summary["module_final_diagnostics"]["observation_governance"][
            "d1_cv_motion_model_cache_diagnostics"
        ],
        governance["d1_cv_motion_model_cache_diagnostics"],
    )
    for diagnostics in locations:
        mutate(diagnostics)
    _write_json(summary_path, summary)
    _write_json(governance_path, governance)


def _resource_text() -> str:
    return (
        "\tElapsed (wall clock) time (h:mm:ss or m:ss): 0:10.00\n"
        "\tMaximum resident set size (kbytes): 1000\n"
        "\tExit status: 0\n"
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
