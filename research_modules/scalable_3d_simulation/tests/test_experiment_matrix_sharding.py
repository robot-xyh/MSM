from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from research_modules.scalable_3d_simulation.experiment_matrix import (
    EXPERIMENT_VARIANTS,
    ExperimentMatrixPlan,
    ModelBundlePaths,
    paired_exogenous_config_sha256,
)
from research_modules.scalable_3d_simulation import experiment_matrix_sharding as sharding
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (
    ExperimentMatrixShardError,
    create_experiment_matrix_execution_plan,
    create_formal_r0_execution_plan,
    load_experiment_matrix_execution_plan,
    merge_experiment_matrix_shards,
    run_experiment_matrix_shard,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.scenarios import AVAILABLE_SCENARIOS


ROOT = Path(__file__).resolve().parents[3]


def test_formal_r0_plan_binds_full_5700_inventory_and_balanced_shards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: ("a" * 40, False),
    )
    plan = ExperimentMatrixPlan(
        variants=EXPERIMENT_VARIANTS,
        scenarios=AVAILABLE_SCENARIOS,
        scales=(5, 20, 50, 100, 200),
        seeds=tuple(range(1000, 1020)),
        duration_s=2.0,
        formal=True,
        training_seeds=frozenset(range(100)),
    )

    path = create_formal_r0_execution_plan(
        root=ROOT,
        output_root=tmp_path / "formal",
        base_config=_base_config(),
        parent_plan=plan,
        shard_count=20,
        created_at_utc="2026-07-25T00:00:00+00:00",
    )
    payload = load_experiment_matrix_execution_plan(path)

    assert payload["parent"]["formal"] is True
    assert payload["parent"]["full_cell_count"] == 5700
    assert payload["scope"]["variants"] == ["R0"]
    assert payload["scope"]["cell_count"] == 900
    assert payload["sharding"]["strategy"] == "scope_index_modulo_v1"
    assert {
        shard["cell_count"] for shard in payload["sharding"]["shards"]
    } == {45}
    for shard in payload["sharding"]["shards"]:
        cells = [
            payload["scope"]["cells"][scope_index]
            for scope_index in shard["scope_indices"]
        ]
        assert len({cell["seed"] for cell in cells}) == 1
        assert len({(cell["scenario"], cell["scale"]) for cell in cells}) == 45


def test_shard_pause_resume_recovers_checkpoint_lag_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sharding, "_execute_r0_cell", _fake_execute_r0_cell)
    path = _development_plan(
        tmp_path,
        seeds=(11, 12, 13),
        shard_count=1,
    )

    first = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        max_new_cells=1,
    )
    assert first["status"] == "paused"
    assert first["completed_cell_count"] == 1
    assert first["new_cell_count"] == 1

    checkpoint_path = Path(first["checkpoint"])
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["completed_cell_count"] = 0
    checkpoint["next_sequence"] = 0
    checkpoint["progress_sha256"] = hashlib.sha256(b"").hexdigest()
    checkpoint_path.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    second = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        resume=True,
        max_new_cells=1,
    )
    assert second["status"] == "paused"
    assert second["completed_cell_count"] == 2
    assert second["new_cell_count"] == 1
    second_checkpoint = json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    )
    assert second_checkpoint["resume_count"] == 1
    assert second_checkpoint["recovered_checkpoint_row_count"] == 1

    completed = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        resume=True,
    )
    assert completed["status"] == "complete"
    assert completed["completed_cell_count"] == 3
    assert completed["new_cell_count"] == 1

    repeated = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        resume=True,
    )
    assert repeated["status"] == "complete"
    assert repeated["completed_cell_count"] == 3
    assert repeated["new_cell_count"] == 0
    assert (
        Path(repeated["progress"]).read_text(encoding="utf-8").count("\n")
        == 3
    )


def test_shard_pauses_at_cell_boundary_when_free_space_reaches_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed_cells: list[str] = []

    def _recording_execute(**kwargs: object) -> dict[str, object]:
        cell = kwargs["cell"]
        assert isinstance(cell, dict)
        executed_cells.append(str(cell["cell_id"]))
        return _fake_execute_r0_cell(**kwargs)

    free_bytes = [30 * 1024**3, 19 * 1024**3]

    def _disk_usage(_path: Path) -> object:
        free = free_bytes.pop(0) if len(free_bytes) > 1 else free_bytes[0]
        return type("DiskUsage", (), {"free": free})()

    monkeypatch.setattr(sharding, "_execute_r0_cell", _recording_execute)
    monkeypatch.setattr(sharding.shutil, "disk_usage", _disk_usage)
    path = _development_plan(tmp_path, seeds=(14, 15), shard_count=1)

    paused = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        minimum_free_bytes=20 * 1024**3,
    )

    assert paused["status"] == "paused"
    assert paused["pause_reason"] == "minimum_free_space_reached"
    assert paused["completed_cell_count"] == 1
    assert paused["new_cell_count"] == 1
    assert paused["available_free_bytes"] == 19 * 1024**3
    assert len(executed_cells) == 1
    assert not list(Path(paused["shard_dir"]).glob("inflight/*.partial"))

    free_bytes[:] = [30 * 1024**3]
    completed = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        resume=True,
        minimum_free_bytes=20 * 1024**3,
    )

    assert completed["status"] == "complete"
    assert completed["pause_reason"] is None
    assert completed["completed_cell_count"] == 2
    assert completed["new_cell_count"] == 1
    assert len(executed_cells) == 2


def test_shard_rejects_negative_free_space_floor(tmp_path: Path) -> None:
    path = _development_plan(tmp_path, seeds=(16,), shard_count=1)

    with pytest.raises(
        ValueError,
        match="minimum_free_bytes must be non-negative",
    ):
        run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=path,
            shard_index=0,
            minimum_free_bytes=-1,
        )

    assert not (path.parent / "shards").exists()


def test_resume_rejects_tampered_episode_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sharding, "_execute_r0_cell", _fake_execute_r0_cell)
    path = _development_plan(tmp_path, seeds=(21, 22), shard_count=1)
    result = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        max_new_cells=1,
    )
    progress = json.loads(
        Path(result["progress"]).read_text(encoding="utf-8").splitlines()[0]
    )
    execution_root = path.parent
    result_path = execution_root / progress["cell_result_relative_path"]
    record = json.loads(result_path.read_text(encoding="utf-8"))
    summary_path = execution_root / record["episode_relative_path"] / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["finite_state"] = False
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ExperimentMatrixShardError,
        match="finite_state|artifact tree",
    ):
        run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=path,
            shard_index=0,
            resume=True,
        )


def test_complete_development_scope_merges_in_parent_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sharding, "_execute_r0_cell", _fake_execute_r0_cell)
    path = _development_plan(
        tmp_path,
        seeds=(31, 32, 33, 34),
        shard_count=2,
    )
    for shard_index in range(2):
        result = run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=path,
            shard_index=shard_index,
        )
        assert result["status"] == "complete"

    paths = merge_experiment_matrix_shards(
        root=ROOT,
        execution_plan_path=path,
    )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    rows = paths["cells"].read_text(encoding="utf-8").splitlines()

    assert manifest["scope_completed_cell_count"] == 4
    assert manifest["scope_complete"] is True
    assert manifest["parent_formal"] is False
    assert manifest["formal_scope_complete"] is False
    assert manifest["formal_matrix_complete"] is False
    assert manifest["full_matrix_complete"] is True
    assert paths["legacy_full_manifest"].is_file()
    assert len(rows) == 5
    assert "\r" not in paths["cells"].read_text(encoding="utf-8")


def test_pairing_hash_ignores_shard_lineage_metadata() -> None:
    base = _base_config()
    payload = base.to_dict()
    payload["metadata"] = {
        **payload["metadata"],
        "matrix_execution_plan_sha256": "a" * 64,
        "matrix_parent_plan_sha256": "b" * 64,
        "matrix_scope_index": 17,
        "matrix_global_index": 117,
        "matrix_shard_index": 3,
    }
    with_lineage = ScenarioConfig.from_dict(payload)
    assert paired_exogenous_config_sha256(base) == (
        paired_exogenous_config_sha256(with_lineage)
    )


def test_real_development_shard_writes_valid_episode_bundle(
    tmp_path: Path,
) -> None:
    path = _development_plan(tmp_path, seeds=(41,), shard_count=1)

    result = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
    )

    assert result["status"] == "complete"
    progress = json.loads(
        Path(result["progress"]).read_text(encoding="utf-8").strip()
    )
    record_path = path.parent / progress["cell_result_relative_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    episode_dir = path.parent / record["episode_relative_path"]
    summary = json.loads(
        (episode_dir / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["finite_state"] is True
    assert summary["online_truth_use_count"] == 0
    assert (episode_dir / "d6_truth_isolated").is_dir()


def test_legacy_r0_plan_without_learning_binding_remains_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sharding, "_execute_r0_cell", _fake_execute_r0_cell)
    path = _development_plan(tmp_path, seeds=(51,), shard_count=1)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("learning_bundles")
    payload.pop("execution_plan_sha256")
    payload["execution_plan_sha256"] = sharding._digest_json(payload)
    _write_json(path, payload)
    (path.parent / "EXECUTION_PLAN_SHA256").write_text(
        f"{sharding._sha256_file(path)}  {path.name}\n",
        encoding="ascii",
    )

    loaded = load_experiment_matrix_execution_plan(path)
    assert "learning_bundles" not in loaded
    result = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
    )
    assert result["status"] == "complete"


def test_g1_scope_requires_present_and_admitted_bundle_before_output(
    tmp_path: Path,
) -> None:
    missing_output = tmp_path / "missing"
    with pytest.raises(ValueError, match="D5 graph"):
        _create_g1_development_plan(
            missing_output,
            bundles=ModelBundlePaths(),
        )
    assert not missing_output.exists()

    bundle = _write_fake_bundle(tmp_path / "unadmitted_bundle")
    unadmitted_output = tmp_path / "unadmitted"
    with pytest.raises(
        ExperimentMatrixShardError,
        match="variant preflight failed",
    ):
        _create_g1_development_plan(
            unadmitted_output,
            bundles=ModelBundlePaths(d5_graph=bundle),
        )
    assert not unadmitted_output.exists()


def test_g1_bundle_tree_and_device_are_bound_before_shard_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _g1_development_plan(
        tmp_path,
        monkeypatch,
        seeds=(61,),
    )
    payload = load_experiment_matrix_execution_plan(path)
    learning = payload["learning_bundles"]
    descriptor = learning["components"]["d5_graph"]
    assert descriptor["manifest_sha256"] == sharding._sha256_file(
        bundle / "manifest.json"
    )
    assert descriptor["tree_sha256"] == sharding._digest_json(
        sharding._tree_inventory(bundle)
    )
    assert learning["preflight_device"] == "cpu"

    with pytest.raises(
        ExperimentMatrixShardError,
        match="device differs",
    ):
        run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=path,
            shard_index=0,
            device="cuda",
            bundles=ModelBundlePaths(d5_graph=bundle),
        )
    assert not (path.parent / "shards").exists()

    (bundle / "weights.bin").write_bytes(b"tampered")
    with pytest.raises(
        ExperimentMatrixShardError,
        match="differs from execution plan binding",
    ):
        run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=path,
            shard_index=0,
            bundles=ModelBundlePaths(d5_graph=bundle),
        )
    assert not (path.parent / "shards").exists()


def test_g1_bundle_mutation_during_cell_prevents_publish_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _g1_development_plan(
        tmp_path,
        monkeypatch,
        seeds=(66,),
    )
    weights_path = bundle / "weights.bin"
    original_weights = weights_path.read_bytes()

    def _execute_then_mutate(**kwargs: object) -> dict[str, object]:
        record = _fake_execute_g1_cell(**kwargs)
        weights_path.write_bytes(b"changed-during-cell")
        return record

    monkeypatch.setattr(
        sharding,
        "_execute_learning_cell",
        _execute_then_mutate,
    )
    bundles = ModelBundlePaths(d5_graph=bundle)
    with pytest.raises(
        ExperimentMatrixShardError,
        match="differs from execution plan binding",
    ):
        run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=path,
            shard_index=0,
            bundles=bundles,
        )

    shard_dir = path.parent / "shards" / "shard_000_of_001"
    assert not list((shard_dir / "cells").glob("*"))
    assert len(list((shard_dir / "inflight").glob("*.partial"))) == 1

    weights_path.write_bytes(original_weights)
    monkeypatch.setattr(
        sharding,
        "_execute_learning_cell",
        _fake_execute_g1_cell,
    )
    completed = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        resume=True,
        bundles=bundles,
    )
    assert completed["status"] == "complete"
    assert completed["completed_cell_count"] == 1
    assert not list((shard_dir / "inflight").glob("*.partial"))


def test_g1_shard_executes_resumes_and_merges_with_runtime_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _g1_development_plan(
        tmp_path,
        monkeypatch,
        seeds=(71, 72),
    )
    monkeypatch.setattr(
        sharding,
        "_execute_learning_cell",
        _fake_execute_g1_cell,
    )
    bundles = ModelBundlePaths(d5_graph=bundle)

    first = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        max_new_cells=1,
        bundles=bundles,
    )
    assert first["status"] == "paused"
    assert first["completed_cell_count"] == 1

    completed = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=path,
        shard_index=0,
        resume=True,
        bundles=bundles,
    )
    assert completed["status"] == "complete"
    assert completed["completed_cell_count"] == 2

    paths = merge_experiment_matrix_shards(
        root=ROOT,
        execution_plan_path=path,
    )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["scope_variants"] == ["G1"]
    assert manifest["scope_completed_cell_count"] == 2
    assert manifest["scope_complete"] is True
    assert manifest["full_matrix_complete"] is False
    progress = [
        json.loads(line)
        for line in Path(completed["progress"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for row in progress:
        result_path = path.parent / row["cell_result_relative_path"]
        record = json.loads(result_path.read_text(encoding="utf-8"))
        assert record["learning_runtime"]["bundle_binding_sha256"] == (
            load_experiment_matrix_execution_plan(path)["learning_bundles"][
                "binding_sha256"
            ]
        )


def test_generic_r0_scope_cli_initializes_runs_and_merges(
    tmp_path: Path,
) -> None:
    script = (
        ROOT
        / "research_modules"
        / "scalable_3d_simulation"
        / "run_experiment_matrix_shard.py"
    )
    output = tmp_path / "cli_execution"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "init-scope",
            "--scope-variants",
            "R0",
            "--scenarios",
            "nominal",
            "--scales",
            "1",
            "--evaluation-seeds",
            "93",
            "--duration",
            "0.05",
            "--shard-count",
            "1",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    plan = output / "experiment_matrix_execution_plan.json"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "run-shard",
            "--execution-plan",
            str(plan),
            "--shard-index",
            "0",
            "--minimum-free-gib",
            "0",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(script),
            "merge-scope",
            "--execution-plan",
            str(plan),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads(
        (
            output
            / "merged_scope"
            / "experiment_matrix_scope_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["scope_variants"] == ["R0"]
    assert manifest["scope_completed_cell_count"] == 1
    assert manifest["scope_complete"] is True


def _development_plan(
    tmp_path: Path,
    *,
    seeds: tuple[int, ...],
    shard_count: int,
) -> Path:
    return create_experiment_matrix_execution_plan(
        root=ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=ExperimentMatrixPlan(
            variants=("R0",),
            scenarios=("nominal",),
            scales=(1,),
            seeds=seeds,
            duration_s=0.05,
            formal=False,
        ),
        scope_variants=("R0",),
        shard_count=shard_count,
        created_at_utc="2026-07-25T00:00:00+00:00",
    )


def _create_g1_development_plan(
    output_root: Path,
    *,
    bundles: ModelBundlePaths,
    seeds: tuple[int, ...] = (1,),
) -> Path:
    return create_experiment_matrix_execution_plan(
        root=ROOT,
        output_root=output_root,
        base_config=_base_config(),
        parent_plan=ExperimentMatrixPlan(
            variants=("R0", "G1"),
            scenarios=("nominal",),
            scales=(1,),
            seeds=seeds,
            duration_s=0.05,
            formal=False,
        ),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        device="cpu",
        created_at_utc="2026-07-26T00:00:00+00:00",
    )


def _g1_development_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    seeds: tuple[int, ...],
) -> tuple[Path, Path]:
    bundle = _write_fake_bundle(tmp_path / "g1_bundle")
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_fake_admitted_g1_runtime,
    )
    path = _create_g1_development_plan(
        tmp_path / "g1_execution",
        bundles=ModelBundlePaths(d5_graph=bundle),
        seeds=seeds,
    )
    return path, bundle


def _base_config() -> ScenarioConfig:
    return ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        metadata={"online_truth_policy": "forbidden"},
    )


def _resolve_fake_admitted_g1_runtime(
    config: ScenarioConfig,
    options: object,
    *,
    stack_config: object,
) -> SimpleNamespace:
    del stack_config
    device = str(getattr(options, "device"))
    diagnostics = _fake_g1_diagnostics(device=device)
    metadata = dict(config.metadata)
    metadata["learning_runtime"] = diagnostics
    return SimpleNamespace(
        config=replace(
            config,
            d5_model_version="d5-crossview-gnn-vtest+123456789abc",
            metadata=metadata,
        ),
        diagnostics=diagnostics,
        stack=None,
    )


def _fake_g1_diagnostics(*, device: str) -> dict[str, object]:
    return {
        "schema_version": "scalable3d-learning-runtime-v1",
        "device": device,
        "d3": {
            "bundle_loaded": False,
            "effective_mode": "disabled",
        },
        "d4": {
            "bundle_loaded": False,
            "effective_mode": "disabled",
        },
        "d5": {
            "bundle_loaded": True,
            "effective_mode": "assist",
            "fallback_reason": None,
            "model_fingerprint": "1" * 64,
        },
        "d5_active_vision": {
            "bundle_loaded": False,
            "effective_mode": "disabled",
            "assist_admitted": False,
        },
        "default_rule_path_preserved": True,
    }


def _write_fake_bundle(path: Path) -> Path:
    path.mkdir()
    _write_json(
        path / "manifest.json",
        {
            "schema_version": "fake-admitted-g1-bundle-v1",
            "model_semantic_version": "test",
        },
    )
    (path / "weights.bin").write_bytes(b"immutable-test-weights")
    return path


def _fake_execute_r0_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    execution: dict[str, object],
    cell: dict[str, object],
    cell_container: Path,
    final_container: Path,
    device: str,
) -> dict[str, object]:
    del repository_root, device
    episode_dir = cell_container / "episode"
    episode_dir.mkdir()
    manifest = {
        "git_commit": execution["source"]["git_commit"],
        "repository_dirty": execution["source"]["repository_dirty"],
        "episode_id": f"fake-{cell['cell_id']}",
    }
    config = {
        "metadata": {
            "algorithm_variant": cell["variant"],
            "matrix_execution_plan_sha256": execution[
                "execution_plan_sha256"
            ],
        }
    }
    summary = {
        "finite_state": True,
        "online_truth_use_count": 0,
        "real_time_factor": 1.0,
        "intercepted_target_count": 0,
    }
    _write_json(episode_dir / "manifest.json", manifest)
    _write_json(episode_dir / "scenario_config.json", config)
    _write_json(episode_dir / "summary.json", summary)
    (episode_dir / "online_observations.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    (episode_dir / "offline_proximity_intercepts.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    (episode_dir / "stage_timings.csv").write_text(
        "stage,wall_time_s\nfake,0.0\n",
        encoding="utf-8",
    )
    artifact_tree = sharding._tree_digest(episode_dir)
    return {
        "schema_version": sharding.EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "cell": dict(cell),
        "episode_relative_path": sharding._relative_path(
            final_container / "episode",
            execution_root,
        ),
        "episode_id": manifest["episode_id"],
        "paired_exogenous_config_sha256": "c" * 64,
        "sensor_random_schedule_version": "entity_fixed_v1",
        "artifact_tree_sha256": artifact_tree,
        "metrics": summary,
        "status": "complete",
    }


def _fake_execute_g1_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    execution: dict[str, object],
    cell: dict[str, object],
    cell_container: Path,
    final_container: Path,
    device: str,
    bundles: ModelBundlePaths,
) -> dict[str, object]:
    del repository_root
    assert bundles.d5_graph is not None
    episode_dir = cell_container / "episode"
    episode_dir.mkdir()
    preflight = execution["learning_bundles"]["variant_preflight"]["G1"]
    versions = dict(preflight["resolved_versions"])
    diagnostics = _fake_g1_diagnostics(device=device)
    manifest = {
        "git_commit": execution["source"]["git_commit"],
        "repository_dirty": execution["source"]["repository_dirty"],
        "episode_id": f"fake-{cell['cell_id']}",
    }
    config = {
        **versions,
        "metadata": {
            "algorithm_variant": cell["variant"],
            "matrix_execution_plan_sha256": execution[
                "execution_plan_sha256"
            ],
            "learning_runtime": diagnostics,
        },
    }
    summary = {
        "finite_state": True,
        "online_truth_use_count": 0,
        "real_time_factor": 1.0,
        "intercepted_target_count": 0,
    }
    _write_json(episode_dir / "manifest.json", manifest)
    _write_json(episode_dir / "scenario_config.json", config)
    _write_json(episode_dir / "summary.json", summary)
    (episode_dir / "online_observations.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    (episode_dir / "offline_proximity_intercepts.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    (episode_dir / "stage_timings.csv").write_text(
        "stage,wall_time_s\nfake,0.0\n",
        encoding="utf-8",
    )
    artifact_tree = sharding._tree_digest(episode_dir)
    return {
        "schema_version": sharding.EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "cell": dict(cell),
        "episode_relative_path": sharding._relative_path(
            final_container / "episode",
            execution_root,
        ),
        "episode_id": manifest["episode_id"],
        "paired_exogenous_config_sha256": "d" * 64,
        "sensor_random_schedule_version": "entity_fixed_v1",
        "artifact_tree_sha256": artifact_tree,
        "metrics": summary,
        "learning_runtime": {
            "bundle_binding_sha256": execution["learning_bundles"][
                "binding_sha256"
            ],
            "diagnostics_sha256": sharding._digest_json(diagnostics),
            "resolved_versions": versions,
        },
        "status": "complete",
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
