from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pytest

from d6_evaluation_metrics.learning_scope_formal_audit import (
    LearningScopeFormalAuditInputs,
    ScopeEvidenceArtifacts,
    audit_learning_scope_formal_evidence,
)
from d6_evaluation_metrics.scalable_3d_offline import (
    evaluate_scalable_3d_episode,
)
from research_modules.scalable_3d_simulation import (
    experiment_matrix_sharding as producer_sharding,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (
    EXPERIMENT_VARIANTS,
    ExperimentCell,
    ExperimentMatrixPlan,
    ModelBundlePaths,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (
    create_experiment_matrix_execution_plan,
    load_experiment_matrix_execution_plan,
    run_experiment_matrix_shard,
)
from research_modules.scalable_3d_simulation.formal_shard_archive import (
    create_verified_formal_shard_archive,
    merge_verified_formal_shard_archives,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.scenarios import AVAILABLE_SCENARIOS


_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = "7" * 40
_PAIRING_SHA256 = "e" * 64
_SENSOR_SCHEDULE = "entity_fixed_v1"
_FORMAL_SEEDS = tuple(range(1000, 1020))
_VERSIONS = {
    "d3_policy_version": "d3-scalable3d-rule-cost-v1",
    "d4_policy_version": "d4-region-resource-rule-v1",
    "d5_model_version": "d5-crossview-gnn-v1+" + "c" * 12,
    "d5_active_vision_policy_version": "d5-active-vision-rule-v1",
}


def test_real_producer_formal_g1_and_r0_archives_pass_d6_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep a durable real-producer compatibility boundary for D6 archives.

    The formal parent retains the complete producer matrix declaration.  Its
    cell enumerator is narrowed to one paired G1/R0 cell only for this fast
    development fixture; plan writing, plan loading, shard state, archive
    creation, archive merge, and the D6 archive audit are the real APIs.
    """

    bundle = _write_bundle(tmp_path / "g1_bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    parent = ExperimentMatrixPlan(
        variants=EXPERIMENT_VARIANTS,
        scenarios=AVAILABLE_SCENARIOS,
        scales=(5, 20, 50, 100, 200),
        seeds=_FORMAL_SEEDS,
        duration_s=0.05,
        formal=True,
        allow_rule_fallback=False,
        training_seeds=frozenset({1, 2, 3}),
    )

    monkeypatch.setattr(
        ExperimentMatrixPlan,
        "cells",
        _paired_formal_fixture_cells,
    )
    monkeypatch.setattr(
        producer_sharding,
        "repository_state",
        lambda _root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        producer_sharding,
        "resolve_learning_runtime",
        _resolve_g1_assist_runtime,
    )
    monkeypatch.setattr(
        producer_sharding,
        "_execute_r0_cell",
        _execute_r0_fixture_cell,
    )
    monkeypatch.setattr(
        producer_sharding,
        "_execute_learning_cell",
        _execute_g1_fixture_cell,
    )

    learned = _produce_archive_scope(
        tmp_path / "learned",
        parent=parent,
        variant="G1",
        bundles=bundles,
    )
    baseline = _produce_archive_scope(
        tmp_path / "baseline",
        parent=parent,
        variant="R0",
        bundles=ModelBundlePaths(),
    )

    learned_plan = load_experiment_matrix_execution_plan(
        learned.execution_plan_path
    )
    baseline_plan = load_experiment_matrix_execution_plan(
        baseline.execution_plan_path
    )
    assert learned_plan["parent"]["formal"] is True
    assert learned_plan["scope"]["variants"] == ["G1"]
    assert baseline_plan["scope"]["variants"] == ["R0"]
    assert (
        learned_plan["parent"]["plan_sha256"]
        == baseline_plan["parent"]["plan_sha256"]
    )
    for scope in (learned, baseline):
        merge_manifest = _read_json(
            scope.archive_merge_dir
            / "experiment_matrix_scope_manifest.json"
        )
        assert merge_manifest["d6_evaluation_generated"] is True
        assert isinstance(
            merge_manifest["d6_evaluation_binding_sha256"],
            str,
        )
        assert (
            scope.archive_merge_dir
            / "archive_d6_evaluation_binding.json"
        ).is_file()

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(baseline,),
            expected_preflight_device="cpu",
        ),
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "pass", json.dumps(
        result,
        indent=2,
        sort_keys=True,
    )
    assert result["formal_evidence_eligible"] is True
    assert result["learned_scope"]["verified_archive_count"] == 1
    assert result["r0_scopes"][0]["verified_archive_count"] == 1
    assert result["learned_scope"]["peak_staged_shard_count"] == 1
    assert result["r0_scopes"][0]["peak_staged_shard_count"] == 1
    assert result["r0_pairing"]["available_pair_count"] == 1
    assert result["r0_pairing"]["non_degraded_pair_count"] == 1
    assert not (learned.execution_plan_path.parent / "shards").exists()
    assert not (baseline.execution_plan_path.parent / "shards").exists()


def _paired_formal_fixture_cells(
    _plan: ExperimentMatrixPlan,
) -> tuple[ExperimentCell, ...]:
    return (
        ExperimentCell("R0", "nominal", 5, 1000),
        ExperimentCell("G1", "nominal", 5, 1000),
    )


def _produce_archive_scope(
    root: Path,
    *,
    parent: ExperimentMatrixPlan,
    variant: str,
    bundles: ModelBundlePaths,
) -> ScopeEvidenceArtifacts:
    execution_root = root / "execution"
    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=execution_root,
        base_config=ScenarioConfig(
            target_count=1,
            resource_count=1,
            recon_count=0,
            duration_s=0.05,
            metadata={"online_truth_policy": "forbidden"},
        ),
        parent_plan=parent,
        scope_variants=(variant,),
        shard_count=1,
        bundles=bundles,
        device="cpu",
        created_at_utc="2026-07-31T12:00:00+00:00",
    )
    loaded = load_experiment_matrix_execution_plan(plan_path)
    assert loaded["schema_version"] == (
        "scalable3d-experiment-matrix-execution-plan-v1"
    )
    shard = run_experiment_matrix_shard(
        root=_ROOT,
        execution_plan_path=plan_path,
        shard_index=0,
        bundles=bundles,
        minimum_free_bytes=0,
    )
    assert shard["status"] == "complete"
    episode_dir = next(
        Path(shard["shard_dir"]).glob("cells/*/episode")
    )
    offline_row = evaluate_scalable_3d_episode(episode_dir)
    assert offline_row["variant_execution_valid"] is True, json.dumps(
        offline_row,
        indent=2,
        sort_keys=True,
        default=str,
    )

    archive_root = root / "archives"
    archive_root.mkdir(parents=True)
    archive_dir = archive_root / str(shard["shard_id"])
    created = create_verified_formal_shard_archive(
        execution_plan_path=plan_path,
        shard_index=0,
        destination=archive_dir,
        created_at_utc="2026-07-31T12:01:00+00:00",
        compression_level=1,
        minimum_free_bytes=0,
    )
    assert created["status"] == "verified"

    detached = root / "detached_raw_shards"
    (execution_root / "shards").rename(detached)
    archive_merge = root / "archive_merge"
    merge = merge_verified_formal_shard_archives(
        repository_root=_ROOT,
        execution_plan_path=plan_path,
        archive_root=archive_root,
        output_dir=archive_merge,
        staging_root=root / "archive_staging",
        write_d6_report=True,
        minimum_free_bytes=0,
    )
    assert merge["status"] == "verified_archive_scope_merged"
    assert Path(merge["paths"]["d6_binding"]).is_file()
    assert detached.is_dir()

    return ScopeEvidenceArtifacts(
        execution_plan_path=plan_path,
        label=variant,
        archive_root=archive_root,
        archive_merge_dir=archive_merge,
    )


def _resolve_g1_assist_runtime(
    config: ScenarioConfig,
    options: object,
    *,
    stack_config: object,
) -> SimpleNamespace:
    del stack_config
    device = str(getattr(options, "device"))
    diagnostics = _learning_runtime("G1", device=device)
    metadata = dict(config.metadata)
    metadata["learning_runtime"] = diagnostics
    return SimpleNamespace(
        config=replace(config, **_VERSIONS, metadata=metadata),
        diagnostics=diagnostics,
        stack=None,
    )


def _execute_r0_fixture_cell(**kwargs: object) -> dict[str, object]:
    return _execute_fixture_cell(variant="R0", **kwargs)


def _execute_g1_fixture_cell(**kwargs: object) -> dict[str, object]:
    kwargs.pop("bundles", None)
    kwargs.pop("experiment_authorization", None)
    return _execute_fixture_cell(variant="G1", **kwargs)


def _execute_fixture_cell(
    *,
    variant: str,
    repository_root: Path,
    execution_root: Path,
    execution: Mapping[str, object],
    cell: Mapping[str, object],
    cell_container: Path,
    final_container: Path,
    device: str,
) -> dict[str, object]:
    del repository_root
    assert cell["variant"] == variant
    episode_dir = cell_container / "episode"
    episode_dir.mkdir()
    versions = (
        dict(_VERSIONS)
        if variant == "G1"
        else {
            name: execution["base_config"]["payload"][name]
            for name in _VERSIONS
        }
    )
    runtime = _learning_runtime(variant, device=device)
    episode_id = f"producer-fixture-{variant.lower()}"
    config = {
        **dict(execution["base_config"]["payload"]),
        **versions,
        "scenario_name": "nominal_5v5",
        "scenario_version": "nominal-5v5-v1",
        "seed": int(cell["seed"]),
        "target_count": 5,
        "resource_count": 5,
        "recon_count": 1,
        "metadata": {
            "online_truth_policy": "forbidden",
            "experiment_matrix_schema": (
                "scalable3d-experiment-matrix-v1"
            ),
            "scenario_family": "nominal",
            "algorithm_variant": variant,
            "comparison_key": cell["comparison_key"],
            "full_system_validation": False,
            "matrix_execution_plan_sha256": execution[
                "execution_plan_sha256"
            ],
            "matrix_parent_plan_sha256": execution["parent"][
                "plan_sha256"
            ],
            "matrix_scope_index": int(cell["scope_index"]),
            "matrix_global_index": int(cell["global_index"]),
            "matrix_shard_index": int(cell["shard_index"]),
            "learning_runtime": runtime,
        },
    }
    manifest = {
        "episode_id": episode_id,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": int(cell["seed"]),
        "git_commit": execution["source"]["git_commit"],
        "repository_dirty": False,
        "config_sha256": _digest_json(config),
        "world_schema": "scalable3d-world-v1",
        "bus_schema": "scalable3d-episode-bus-v1",
        "scenario_schema": "scalable3d-scenario-v1",
        "online_observation_schema": "scalable3d-observation-v1",
        "offline_truth_schema": "scalable3d-offline-truth-v2",
        "d1_model_version": config["d1_model_version"],
        "d2_model_version": config["d2_model_version"],
        **versions,
        "d7_model_version": config["d7_model_version"],
        "threshold_version": config["threshold_version"],
    }
    summary = {
        "episode_id": episode_id,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": int(cell["seed"]),
        "target_count": config["target_count"],
        "resource_count": config["resource_count"],
        "recon_count": config["recon_count"],
        "finite_state": True,
        "online_truth_use_count": 0,
        "real_time_factor": 1.0,
        "intercepted_target_count": 0,
        "module_final_diagnostics": {
            "schema_version": "scalable3d-module-stack-v1",
            "learning_runtime": runtime,
            "online_truth_use_count": 0,
        },
    }
    _write_json(episode_dir / "scenario_config.json", config)
    _write_json(episode_dir / "manifest.json", manifest)
    _write_json(episode_dir / "summary.json", summary)
    _write_jsonl(
        episode_dir / "online_observations.jsonl",
        [_d5_observation(variant)],
    )
    _write_jsonl(episode_dir / "offline_proximity_intercepts.jsonl", [])
    (episode_dir / "stage_timings.csv").write_text(
        "schema_version,stage,call_count,wall_time_s,mean_wall_time_ms,"
        "p50_wall_time_ms,p95_wall_time_ms,max_wall_time_ms,"
        "distribution_available,distribution_unavailable_reason\n"
        "scalable3d-stage-timings-v2,module_stack,1,0.01,10,10,10,10,"
        "true,\n",
        encoding="utf-8",
    )

    record: dict[str, object] = {
        "schema_version": producer_sharding.EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "cell": dict(cell),
        "episode_relative_path": producer_sharding._relative_path(
            final_container / "episode",
            execution_root,
        ),
        "episode_id": episode_id,
        "paired_exogenous_config_sha256": _PAIRING_SHA256,
        "sensor_random_schedule_version": _SENSOR_SCHEDULE,
        "artifact_tree_sha256": producer_sharding._tree_digest(episode_dir),
        "metrics": {
            "finite_state": True,
            "online_truth_use_count": 0,
            "real_time_factor": 1.0,
            "intercepted_target_count": 0,
        },
        "status": "complete",
    }
    if variant == "G1":
        record["learning_runtime"] = {
            "bundle_binding_sha256": execution["learning_bundles"][
                "binding_sha256"
            ],
            "diagnostics_sha256": producer_sharding._digest_json(runtime),
            "resolved_versions": versions,
        }
    return record


def _learning_runtime(variant: str, *, device: str) -> dict[str, object]:
    disabled = {
        "requested_mode": "disabled",
        "effective_mode": "disabled",
        "bundle_requested": False,
        "bundle_loaded": False,
        "fallback_reason": None,
        "model_fingerprint": None,
    }
    runtime: dict[str, object] = {
        "schema_version": "scalable3d-learning-runtime-v1",
        "device": device,
        "d3": dict(disabled),
        "d4": dict(disabled),
        "d5": dict(disabled),
        "d5_active_vision": {**disabled, "assist_admitted": False},
        "default_rule_path_preserved": True,
    }
    if variant == "G1":
        runtime["d5"] = {
            "requested_mode": "assist",
            "effective_mode": "assist",
            "bundle_requested": True,
            "bundle_loaded": True,
            "fallback_reason": None,
            "model_fingerprint": "c" * 64,
        }
    return runtime


def _d5_observation(variant: str) -> dict[str, object]:
    learned = variant == "G1"
    return {
        "sequence": 0,
        "topic": "modules.d5.terminal_association",
        "source": "D5",
        "timestamp": 0.01,
        "schema_version": "d5-scalable3d-association-v1",
        "payload": {
            "timestamp": 0.01,
            "camera_batch_count": 1,
            "tracklet_count": 2,
            "graph_node_count": 2,
            "graph_edge_count": 1,
            "probability_source": (
                "loaded_edge_model"
                if learned
                else "deterministic_geometry_rule"
            ),
            "scoring_status": (
                "model_scored" if learned else "deterministic_rule_scored"
            ),
            "fallback_reason": None,
            "diagnostics": {
                "candidate_tracklet_edges": 1,
                "max_tracklet_candidate_edges_per_node": 4,
                "tracklet_candidate_budget_dropped": 0,
            },
            "bindings": [
                {
                    "cluster_key": "cluster-1",
                    "global_track_id": "GT-0001",
                    "decision_state": "bound",
                    "cost": 0.1,
                    "supporting_tracklet_keys": ["CAM-1:T-1"],
                }
            ],
        },
    }


def _write_bundle(path: Path) -> Path:
    path.mkdir()
    _write_json(
        path / "manifest.json",
        {
            "schema_version": "d5-producer-compatibility-fixture-v1",
            "model_semantic_version": "test-only",
        },
    )
    (path / "weights.bin").write_bytes(b"d6-producer-compatibility-fixture")
    return path


def _digest_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_json(path: Path | None) -> dict[str, object]:
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
