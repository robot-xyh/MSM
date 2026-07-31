from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from d6_evaluation_metrics.experiment_matrix_admission import (
    EXPERIMENT_MATRIX_SCENARIOS,
    EXPERIMENT_MATRIX_SCALES,
    EXPERIMENT_MATRIX_VARIANTS,
    MatrixCellKey,
    _audit_cells,
    audit_experiment_matrix_admission,
    inventory_from_plan,
    write_experiment_matrix_admission_report,
)
from d6_evaluation_metrics.strict_offline_identity import (
    STRICT_OFFLINE_ID_SWITCH_SEMANTICS,
    STRICT_OFFLINE_ID_SWITCH_SOURCE,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (
    ExperimentMatrixPlan,
)


FORMAL_SEEDS = tuple(range(1000, 1020))
TRAINING_SEEDS = frozenset(range(100))


def test_actual_formal_plan_has_dynamic_5700_cells_and_report_bundle(
    tmp_path: Path,
) -> None:
    plan = _formal_plan()
    inventory = inventory_from_plan(plan)
    assert len(inventory["cells"]) == 5700
    assert sum(row["variant"] == "F1" for row in inventory["cells"]) == 300

    repository = _clean_git_repository(tmp_path / "repo")
    bundles = _ready_bundles(tmp_path / "bundles")
    result = audit_experiment_matrix_admission(
        plan,
        mode="pre_run",
        repository_root=repository,
        model_bundles=bundles,
    )

    assert result["verdict"] == "pass"
    assert result["cell_summary"] == {
        "expected_cell_count": 5700,
        "accepted_cell_count": 5700,
        "failed_cell_count": 0,
        "actual_matrix_row_count": 0,
        "offline_evidence_row_count": 0,
    }
    assert result["inventory"]["f1_scenarios_from_inventory"] == [
        "center_failure",
        "high_threat_m_to_n",
        "secondary_failure",
    ]

    paths = write_experiment_matrix_admission_report(tmp_path / "report", result)
    assert set(paths) == {"json", "csv", "markdown", "checksums"}
    checksum_lines = paths["checksums"].read_text(encoding="utf-8").splitlines()
    assert len(checksum_lines) == 3
    for line in checksum_lines:
        digest, filename = line.split(None, 1)
        assert digest == _sha256(paths["checksums"].parent / filename.strip())
    assert "预期 cell 数为 5700" in paths["markdown"].read_text(encoding="utf-8")


def test_inventory_count_follows_changed_plan_cells_instead_of_6300(
    tmp_path: Path,
) -> None:
    base = _formal_plan()
    cells = list(base.cells())
    cells.extend(
        MatrixCellKey("F1", "nominal", scale, seed)
        for scale in EXPERIMENT_MATRIX_SCALES
        for seed in FORMAL_SEEDS
    )
    plan = _PlanLike(cells=tuple(cells))
    result = audit_experiment_matrix_admission(
        plan,
        mode="pre_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        model_bundles=_ready_bundles(tmp_path / "bundles"),
    )

    assert result["verdict"] == "pass"
    assert result["cell_summary"]["expected_cell_count"] == 5800
    assert "nominal" in result["inventory"]["f1_scenarios_from_inventory"]


def test_post_run_missing_manifest_rejects_without_crashing_and_compacts_ranges(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "missing_matrix"
    artifact_root.mkdir()
    result = audit_experiment_matrix_admission(
        _formal_plan(),
        mode="post_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        artifact_root=artifact_root,
        model_bundles=_ready_bundles(tmp_path / "bundles"),
    )

    assert result["verdict"] == "fail_closed"
    assert "matrix_manifest_missing" in result["blockers"]
    assert result["cell_summary"]["expected_cell_count"] == 5700
    missing = [
        item
        for item in result["compact_missing_cell_ranges"]
        if item["reason"] == "matrix_cell_missing"
    ]
    assert sum(item["cell_count"] for item in missing) == 5700
    assert len(missing) == 2


def test_duplicate_inventory_fails_closed(tmp_path: Path) -> None:
    inventory = inventory_from_plan(_formal_plan())
    inventory["cells"].append(dict(inventory["cells"][0]))
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    result = audit_experiment_matrix_admission(
        path,
        mode="pre_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        model_bundles=_ready_bundles(tmp_path / "bundles"),
    )

    assert result["verdict"] == "fail_closed"
    assert result["inventory"]["duplicate_cell_count"] == 1
    assert "expected_cell_inventory_contains_duplicates" in result["blockers"]


def test_model_weight_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    bundles = _ready_bundles(tmp_path / "bundles")
    Path(bundles["d5_graph"], "weights.pt").write_bytes(b"tampered")
    result = audit_experiment_matrix_admission(
        _formal_plan(),
        mode="pre_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        model_bundles=bundles,
    )

    assert result["verdict"] == "fail_closed"
    assert result["model_bundles"]["d5_graph"]["sha_valid"] is False
    assert any(
        blocker.startswith("model_bundle_d5_graph:weight_sha_mismatch")
        for blocker in result["blockers"]
    )


def test_dimensions_only_manifest_is_rejected_as_inventory(tmp_path: Path) -> None:
    path = tmp_path / "experiment_matrix_manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "scalable3d-experiment-matrix-v1",
                "formal": True,
                "variants": list(EXPERIMENT_MATRIX_VARIANTS),
                "scenarios": list(EXPERIMENT_MATRIX_SCENARIOS),
                "scales": list(EXPERIMENT_MATRIX_SCALES),
                "seeds": list(FORMAL_SEEDS),
                "cell_count": 5700,
            }
        ),
        encoding="utf-8",
    )
    result = audit_experiment_matrix_admission(
        path,
        mode="pre_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        model_bundles=_ready_bundles(tmp_path / "bundles"),
    )

    assert result["verdict"] == "fail_closed"
    assert result["inventory_error"].startswith("expected_cell_inventory_invalid:")
    assert result["cell_summary"]["expected_cell_count"] == 0


def test_missing_inventory_zero_count_is_explicit_missing_input(
    tmp_path: Path,
) -> None:
    result = audit_experiment_matrix_admission(
        None,
        mode="post_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        artifact_root=tmp_path / "missing_matrix",
    )

    assert result["verdict"] == "fail_closed"
    assert result["inventory"]["source_kind"] == "missing"
    assert result["cell_summary"]["expected_cell_count"] == 0
    assert result["cell_summary"]["accepted_cell_count"] == 0
    assert "expected_cell_inventory_missing" in result["blockers"]

    paths = write_experiment_matrix_admission_report(tmp_path / "report", result)
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "仅表示缺少输入" in markdown
    assert "不是 5700-cell 正式清单的评估结果" in markdown


def test_malformed_d4_holdout_count_fails_closed_instead_of_crashing(
    tmp_path: Path,
) -> None:
    bundles = _ready_bundles(tmp_path / "bundles")
    manifest_path = Path(bundles["d4"], "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["final_holdout_seed_count"] = "not-an-integer"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = audit_experiment_matrix_admission(
        _formal_plan(),
        mode="pre_run",
        repository_root=_clean_git_repository(tmp_path / "repo"),
        model_bundles=bundles,
    )

    assert result["verdict"] == "fail_closed"
    assert result["model_bundles"]["d4"]["assist_declared"] is False
    assert "d4_assist_not_authorized" in (
        result["model_bundles"]["d4"]["failure_reasons"]
    )


def test_complete_post_run_artifacts_can_pass(tmp_path: Path) -> None:
    plan = _formal_plan()
    repository = _clean_git_repository(tmp_path / "repo")
    bundles = _ready_bundles(tmp_path / "bundles")
    pre_run = audit_experiment_matrix_admission(
        plan,
        mode="pre_run",
        repository_root=repository,
        model_bundles=bundles,
    )
    artifact_root = tmp_path / "matrix"
    _write_complete_post_run_fixture(
        artifact_root,
        plan=plan,
        model_audits=pre_run["model_bundles"],
    )

    result = audit_experiment_matrix_admission(
        plan,
        mode="post_run",
        repository_root=repository,
        artifact_root=artifact_root,
        model_bundles=bundles,
    )

    assert result["verdict"] == "pass"
    assert result["cell_summary"]["accepted_cell_count"] == 5700
    assert result["confidence_interval_inputs"]["available"] is True
    assert result["artifacts"]["animation"]["available"] is True


def test_post_run_rejects_online_only_id_switch_as_strict_evidence() -> None:
    cell = MatrixCellKey("R0", "nominal", 5, 1000)
    matrix_row = {
        "variant": "R0",
        "scenario": "nominal",
        "scale": "5",
        "seed": "1000",
    }
    evidence = {
        "algorithm_variant_normalized": "R0",
        "experiment_matrix_scenario_family": "nominal",
        "experiment_matrix_scale": "5",
        "seed": "1000",
        "variant_execution_valid": "true",
        "variant_execution_failure_reasons_json": "[]",
        "online_truth_use_count": "0",
        "online_truth_use_count_availability": "available",
        "finite_state": "true",
        "finite_state_availability": "available",
        "d2_id_switch_count": "0",
        "d2_id_switch_count_availability": "available",
        "offline_proximity_within_5m_count": "0",
        "offline_proximity_within_5m_count_availability": "available",
        "offline_proximity_unique_target_count": "0",
        "offline_proximity_unique_target_count_availability": "available",
        "experiment_matrix_formal_acceptance_eligible": "true",
        "experiment_matrix_formal_acceptance_eligible_availability": "available",
    }

    row = _audit_cells(
        (cell,),
        mode="post_run",
        inventory_audit={"blockers": []},
        source_audit={"formal_clean_source": True},
        bundle_audits={},
        actual_matrix_rows=(matrix_row,),
        offline_rows=(evidence,),
    )[0]

    assert row["d2_id_switch_available"] is False
    assert "d2_strict_id_switch_provenance_not_verified" in row[
        "failure_reasons"
    ]
    assert "d2_id_switch_metric_unavailable" in row["failure_reasons"]


def _formal_plan() -> ExperimentMatrixPlan:
    return ExperimentMatrixPlan(
        variants=EXPERIMENT_MATRIX_VARIANTS,
        scenarios=EXPERIMENT_MATRIX_SCENARIOS,
        scales=EXPERIMENT_MATRIX_SCALES,
        seeds=FORMAL_SEEDS,
        duration_s=2.0,
        formal=True,
        allow_rule_fallback=False,
        training_seeds=TRAINING_SEEDS,
    )


class _PlanLike:
    variants = EXPERIMENT_MATRIX_VARIANTS
    scenarios = EXPERIMENT_MATRIX_SCENARIOS
    scales = EXPERIMENT_MATRIX_SCALES
    seeds = FORMAL_SEEDS
    formal = True
    allow_rule_fallback = False
    training_seeds = TRAINING_SEEDS

    def __init__(self, *, cells: tuple[MatrixCellKey, ...]) -> None:
        self._cells = cells

    def cells(self) -> tuple[MatrixCellKey, ...]:
        return self._cells


def _ready_bundles(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True)
    manifests: dict[str, dict[str, Any]] = {
        "d3": {
            "admission": {
                "assist_authorized": True,
                "allowed_modes": ["shadow", "assist"],
            },
            "state_dict": {"file": "state_dict.pt"},
        },
        "d4": {
            "maximum_advisor_mode": "assist",
            "strategy_capability_claim_allowed": True,
            "final_holdout_seed_count": 20,
            "state_dict_file": "state_dict.pt",
        },
        "d5_graph": {
            "admission": {"g1_assist_eligible": True},
            "weights": {"filename": "weights.pt"},
        },
        "d5_active_vision": {
            "admission": {"assist_admitted": True},
            "runtime_policy": {
                "assist_admitted": True,
                "allowed_runtime_modes": ["shadow", "assist"],
            },
            "weights": {"filename": "weights.pt"},
        },
    }
    paths: dict[str, Path] = {}
    for component, manifest in manifests.items():
        bundle = root / component
        bundle.mkdir()
        weight_name = (
            manifest.get("state_dict", {}).get("file")
            or manifest.get("state_dict_file")
            or manifest.get("weights", {}).get("filename")
        )
        weight_path = bundle / str(weight_name)
        weight_path.write_bytes(f"{component}-weights".encode())
        digest = _sha256(weight_path)
        if "state_dict" in manifest:
            manifest["state_dict"]["sha256"] = digest
        elif "state_dict_file" in manifest:
            manifest["state_dict_sha256"] = digest
        else:
            manifest["weights"]["sha256"] = digest
        manifest_path = bundle / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True),
            encoding="utf-8",
        )
        paths[component] = bundle
    return paths


def _clean_git_repository(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "d6@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "D6 Test"],
        cwd=path,
        check=True,
    )
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=path,
        check=True,
    )
    return path


def _write_complete_post_run_fixture(
    root: Path,
    *,
    plan: ExperimentMatrixPlan,
    model_audits: dict[str, dict[str, Any]],
) -> None:
    root.mkdir()
    cells = list(plan.cells())
    model_inventory = {
        component: {
            "manifest_sha256": audit["manifest_sha256"],
            "weights_sha256": audit["weights_sha256_observed"],
            "bundle_sha256": audit["bundle_sha256"],
        }
        for component, audit in model_audits.items()
    }
    (root / "experiment_matrix_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "scalable3d-experiment-matrix-v1",
                "formal": True,
                "repository_dirty": False,
                "git_commit": "a" * 40,
                "cell_count": len(cells),
                "completed_cell_count": len(cells),
                "model_bundles": model_inventory,
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        root / "experiment_matrix_cells.csv",
        [
            {
                "variant": cell.variant,
                "scenario": cell.scenario,
                "scale": cell.scale,
                "seed": cell.seed,
            }
            for cell in cells
        ],
    )
    d6_root = root / "d6_evaluation"
    d6_root.mkdir()
    _write_csv(
        d6_root / "scalable_3d_offline_per_episode_seed.csv",
        [
            {
                "algorithm_variant_normalized": cell.variant,
                "experiment_matrix_scenario_family": cell.scenario,
                "experiment_matrix_scale": cell.scale,
                "seed": cell.seed,
                "variant_execution_valid": True,
                "variant_execution_failure_reasons_json": "[]",
                "online_truth_use_count": 0,
                "online_truth_use_count_availability": "available",
                "finite_state": True,
                "finite_state_availability": "available",
                "d2_id_switch_count": 0,
                "d2_id_switch_count_availability": "available",
                "d2_id_switch_count_semantics": (
                    STRICT_OFFLINE_ID_SWITCH_SEMANTICS
                ),
                "d2_id_switch_count_source_artifact": (
                    STRICT_OFFLINE_ID_SWITCH_SOURCE
                ),
                "d2_strict_identity_artifact_verified": True,
                "d2_strict_identity_truth_isolation_verified": True,
                "d2_strict_identity_id_switch_backfilled": False,
                "d2_strict_identity_verification_mode": (
                    "sha256_verified_artifact"
                ),
                "offline_proximity_within_5m_count": 0,
                "offline_proximity_within_5m_count_availability": "available",
                "offline_proximity_unique_target_count": 0,
                "offline_proximity_unique_target_count_availability": "available",
                "experiment_matrix_formal_acceptance_eligible": True,
                "experiment_matrix_formal_acceptance_eligible_availability": (
                    "available"
                ),
            }
            for cell in cells
        ],
    )
    statistic = {
        "availability": "available",
        "seed_value_count": 20,
        "bootstrap_availability": "available",
        "bootstrap_ci95_low": 0.0,
        "bootstrap_ci95_high": 0.0,
    }
    (d6_root / "scalable_3d_offline_aggregate.json").write_text(
        json.dumps(
            {
                "bootstrap": {"resamples": 2000, "rng_seed": 20260725},
                "experiment_matrix": {
                    "completeness": {
                        "expected_cell_count": len(cells),
                        "present_expected_cell_count": len(cells),
                        "execution_valid_cell_count": len(cells),
                    },
                    "variant_groups": [
                        {
                            "algorithm_variant": variant,
                            "seed_count": 20,
                            "clean_formal_metric_statistics": {
                                metric: statistic
                                for metric in (
                                    "d2_id_switch_count",
                                    "offline_proximity_within_5m_count",
                                    "offline_proximity_unique_target_count",
                                )
                            },
                        }
                        for variant in EXPERIMENT_MATRIX_VARIANTS
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (d6_root / "SCALABLE_3D_OFFLINE_EVALUATION_CN.md").write_text(
        "# fixture\n",
        encoding="utf-8",
    )
    (d6_root / "scalable_3d_stage_timing_curves.png").write_bytes(b"png-fixture")
    (root / "matrix.gif").write_bytes(b"GIF89a" + b"\x00" * 16)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
