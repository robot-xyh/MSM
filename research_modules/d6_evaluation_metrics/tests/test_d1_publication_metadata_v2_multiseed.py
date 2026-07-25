from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from d6_evaluation_metrics import d1_publication_metadata_multiseed as v1
from d6_evaluation_metrics.d1_publication_metadata_v2_multiseed import (
    CANDIDATE_IMPLEMENTATION_ID,
    D1_PUBLICATION_METADATA_V2_MATRIX_SHA256,
    D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION,
    D1_PUBLICATION_METADATA_V2_SOURCE_COMMIT,
    D1PublicationMetadataV2EvidenceError,
    evaluate_d1_publication_metadata_v2_multiseed,
    write_d1_publication_metadata_v2_multiseed_report,
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
    / "d1_publication_metadata_v2_multiseed_v1.json"
)


def test_v1_schema_and_entrypoint_remain_frozen() -> None:
    assert v1.D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION == (
        "d6.d1_publication_metadata_multiseed_evaluation.v1"
    )
    assert callable(v1.evaluate_d1_publication_metadata_multiseed)


def test_v2_evaluator_accepts_13_pair_contract_and_normalizes_only_audit(
    tmp_path: Path,
) -> None:
    manifest_path = _build_v2_evidence(tmp_path)

    result = evaluate_d1_publication_metadata_v2_multiseed(manifest_path)

    assert result["schema_version"] == (
        D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION
    )
    assert result["input_contract"]["matrix_sha256"] == (
        D1_PUBLICATION_METADATA_V2_MATRIX_SHA256
    )
    assert result["input_contract"]["source_commit"] == (
        D1_PUBLICATION_METADATA_V2_SOURCE_COMMIT
    )
    assert len(result["pairs"]) == 13
    assert all(
        pair["business_semantics_passed"] for pair in result["pairs"]
    )
    assert all(
        pair["d2_publication_metadata_audit_passed"]
        for pair in result["pairs"]
    )
    first = result["pairs"][0]
    assert first["reference"]["normalized_summary_sha256"] == (
        first["candidate"]["normalized_summary_sha256"]
    )
    assert first["reference"]["d2_publication_metadata_audit"]["totals"][
        "shared_subtree_builtin_equivalent_reuse_count"
    ] > 0
    assert first["candidate"]["d2_publication_metadata_audit"]["totals"][
        "immutable_v2_identity_reuse_count"
    ] > 0
    assert all(gate["passed"] for gate in result["admission_gates"].values())
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False


def test_v2_report_bundle_is_compact_and_read_only(tmp_path: Path) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    evidence_before = _tree_fingerprint(manifest_path.parent)
    result = evaluate_d1_publication_metadata_v2_multiseed(manifest_path)

    paths = write_d1_publication_metadata_v2_multiseed_report(
        result,
        tmp_path / "report",
    )

    assert _tree_fingerprint(manifest_path.parent) == evidence_before
    assert set(paths) == {
        "evaluation_json",
        "aggregate_json",
        "pairs_csv",
        "markdown",
        "plot_png",
        "sha256sums",
    }
    assert all(path.is_file() for path in paths.values())
    assert paths["plot_png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    markdown = paths["markdown"].read_text(encoding="utf-8")
    gate_section = markdown.split("## 准入门", maxsplit=1)[1].split(
        "## 逐对结果",
        maxsplit=1,
    )[0]
    rendered_gate_names = [
        line.split("`", maxsplit=2)[1]
        for line in gate_section.splitlines()
        if line.startswith("| `")
    ]
    assert rendered_gate_names == sorted(result["admission_gates"])

    round_trip_result = json.loads(
        paths["evaluation_json"].read_text(encoding="utf-8")
    )
    round_trip_paths = write_d1_publication_metadata_v2_multiseed_report(
        round_trip_result,
        tmp_path / "round_trip_report",
    )
    for name, path in paths.items():
        assert path.read_bytes() == round_trip_paths[name].read_bytes()

    with pytest.raises(ValueError, match="independent"):
        write_d1_publication_metadata_v2_multiseed_report(
            result,
            manifest_path.parent / "forbidden",
        )


def test_v2_d2_audit_count_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    _mutate_d2_audit(
        manifest_path,
        case_id="short_seed_1101",
        arm="candidate",
        mutate=lambda audit: audit["totals"].__setitem__(
            "immutable_v2_full_content_audit_count",
            5,
        ),
    )

    with pytest.raises(
        D1PublicationMetadataV2EvidenceError,
        match="validation/content counts mismatch",
    ):
        evaluate_d1_publication_metadata_v2_multiseed(manifest_path)


def test_v2_non_whitelisted_summary_change_fails_business_gate(
    tmp_path: Path,
) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    summary_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "candidate_episode"
        / "summary.json"
    )
    summary = _read_json(summary_path)
    summary["module_final_diagnostics"]["d2_track_count"] = 201
    _write_json(summary_path, summary)

    result = evaluate_d1_publication_metadata_v2_multiseed(manifest_path)

    assert result["pairs"][0]["business_semantics_passed"] is False
    assert result["admission_gates"][
        "all_pairs_business_semantics_equal"
    ]["passed"] is False
    assert result["d1_optimization_admitted"] is False


def test_v2_d2_regression_gate_rejects_candidate(tmp_path: Path) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    for case_dir in manifest_path.parent.glob("*_seed_*"):
        _replace_stage_wall(
            case_dir / "candidate_episode" / "stage_timings.csv",
            "module.d2_association",
            1.2,
        )

    result = evaluate_d1_publication_metadata_v2_multiseed(manifest_path)

    assert result["admission_gates"][
        "short_d2_association_mean_increase_at_most_5_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "long_d2_association_mean_increase_at_most_5_pct"
    ]["passed"] is False
    assert result["d1_optimization_admitted"] is False


def test_v2_core_wall_gate_rejects_candidate(tmp_path: Path) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    for case_dir in manifest_path.parent.glob("*_seed_*"):
        summary_path = case_dir / "candidate_episode" / "summary.json"
        summary = _read_json(summary_path)
        summary["wall_time_s"] = 9.7
        _write_json(summary_path, summary)

    result = evaluate_d1_publication_metadata_v2_multiseed(manifest_path)

    assert result["admission_gates"][
        "short_core_wall_mean_improvement_at_least_5_pct"
    ]["passed"] is False
    assert result["admission_gates"][
        "long_core_wall_mean_improvement_at_least_5_pct"
    ]["passed"] is False
    assert result["d1_optimization_admitted"] is False


@pytest.mark.parametrize(
    "tamper,match",
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
    ],
)
def test_v2_manifest_provenance_tamper_fails_closed(
    tmp_path: Path,
    tamper: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    manifest = _read_json(manifest_path)
    tamper(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(D1PublicationMetadataV2EvidenceError, match=match):
        evaluate_d1_publication_metadata_v2_multiseed(manifest_path)


def test_v2_episode_commit_tamper_fails_closed(tmp_path: Path) -> None:
    manifest_path = _build_v2_evidence(tmp_path)
    episode_manifest_path = (
        manifest_path.parent
        / "short_seed_1101"
        / "reference_episode"
        / "manifest.json"
    )
    episode_manifest = _read_json(episode_manifest_path)
    episode_manifest["git_commit"] = "b" * 40
    _write_json(episode_manifest_path, episode_manifest)

    with pytest.raises(
        D1PublicationMetadataV2EvidenceError,
        match="source commit mismatch",
    ):
        evaluate_d1_publication_metadata_v2_multiseed(manifest_path)


def _build_v2_evidence(tmp_path: Path) -> Path:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir(parents=True)
    manifest = matrix_runner.planned_evidence_manifest(
        MATRIX_PATH,
        matrix,
        ROOT,
        D1_PUBLICATION_METADATA_V2_SOURCE_COMMIT,
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
            _write_v2_episode(
                episode_dir,
                implementation=record["expected_implementation"],
                seed=int(case["seed"]),
                duration_s=float(case["duration_s"]),
                candidate=(arm == "candidate"),
            )
            Path(record["resource_path"]).write_text(
                _resource_text(),
                encoding="utf-8",
            )
            Path(record["stdout_path"]).write_text("", encoding="utf-8")
            Path(record["stderr_path"]).write_text("", encoding="utf-8")
    manifest_path = evidence_root / "evidence_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _write_v2_episode(
    episode_dir: Path,
    *,
    implementation: str,
    seed: int,
    duration_s: float,
    candidate: bool,
) -> None:
    config = {
        "scenario_name": "d1_publication_metadata_v2_test",
        "scenario_version": "d1-publication-metadata-v2-test-v1",
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
                "immutable_shared_contract_validated_node_count": 1000,
                "immutable_shared_contract_validation_count": 30,
                "immutable_shared_mapping_build_count": 100,
                "immutable_shared_tuple_build_count": 110,
                "shared_audit_value_reuse_count": 3000,
            }
        )
        implementation_id = CANDIDATE_IMPLEMENTATION_ID
        contract_version: str | None = "d1.publication_audit_tree.v2"
    else:
        operation_counts[
            "per_track_shared_audit_mapping_copy_count"
        ] = 30_000
        implementation_id = (
            "d1.publication_metadata.per_track_audit_copy.v1"
        )
        contract_version = None
    diagnostics = {
        "implementation_id": implementation_id,
        "immutable_shared_publication_metadata": candidate,
        "operation_counts": operation_counts,
        "publication_audit_contract_version": contract_version,
    }
    d2_audit = _d2_audit(candidate=candidate)
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
        "git_commit": D1_PUBLICATION_METADATA_V2_SOURCE_COMMIT,
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
        "d1_publication_metadata_implementation": implementation,
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "d2_publication_metadata_audit": copy.deepcopy(d2_audit),
        "d1_fusion_association": {
            "association_innovation_solve_count": 20,
        },
        "d1_scan_events": [],
    }
    module_final = {
        "d1_publication_metadata_implementation": implementation,
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "d2_publication_metadata_audit": copy.deepcopy(d2_audit),
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
        "d1_publication_metadata_implementation": implementation,
        "d1_publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "d2_publication_metadata_audit": copy.deepcopy(d2_audit),
        "module_final_diagnostics": module_final,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        _write_json(episode_dir / name, payload)

    walls = {
        "module.d1_fusion": 8.0 if candidate else 10.0,
        "module.d1_scan_input": 1.0,
        "module.d2_association": 1.02 if candidate else 1.0,
        "module.d3_assignment": 1.0,
        "module.d5_active_vision": 1.0,
        "module.d7_guidance": 1.0,
        "module_publication_bus": 1.0,
    }
    with (episode_dir / "stage_timings.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
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
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
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


def _d2_audit(*, candidate: bool) -> dict[str, Any]:
    latest = {
        "metadata_count": 100,
        "shared_subtree_full_audit_count": 3,
        "shared_subtree_equivalent_reuse_count": 0 if candidate else 297,
        "shared_subtree_builtin_equivalent_reuse_count": (
            0 if candidate else 297
        ),
        "immutable_v2_contract_validation_count": 3 if candidate else 0,
        "immutable_v2_full_content_audit_count": 3 if candidate else 0,
        "immutable_v2_identity_reuse_count": 297 if candidate else 0,
        "immutable_v2_contract_rejection_count": 0,
    }
    totals = {
        "metadata_count": 200,
        "shared_subtree_full_audit_count": 6,
        "shared_subtree_equivalent_reuse_count": 0 if candidate else 594,
        "shared_subtree_builtin_equivalent_reuse_count": (
            0 if candidate else 594
        ),
        "immutable_v2_contract_validation_count": 6 if candidate else 0,
        "immutable_v2_full_content_audit_count": 6 if candidate else 0,
        "immutable_v2_identity_reuse_count": 594 if candidate else 0,
        "immutable_v2_contract_rejection_count": 0,
    }
    return {
        "schema_version": "scalable3d-d2-publication-metadata-audit-v1",
        "batch_count": 2,
        "latest": latest,
        "totals": totals,
    }


def _mutate_d2_audit(
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
        summary["d2_publication_metadata_audit"],
        summary["module_final_diagnostics"][
            "d2_publication_metadata_audit"
        ],
        summary["module_final_diagnostics"]["observation_governance"][
            "d2_publication_metadata_audit"
        ],
        governance["d2_publication_metadata_audit"],
    )
    for audit in locations:
        mutate(audit)
    _write_json(summary_path, summary)
    _write_json(governance_path, governance)


def _replace_stage_wall(path: Path, stage_name: str, wall_s: float) -> None:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for row in rows:
        if row["stage"] == stage_name:
            row["wall_time_s"] = str(wall_s)
            row["mean_wall_time_ms"] = str(wall_s * 100.0)
            row["p50_wall_time_ms"] = str(wall_s * 80.0)
            row["p95_wall_time_ms"] = str(wall_s * 110.0)
            row["max_wall_time_ms"] = str(wall_s * 120.0)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


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
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
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
