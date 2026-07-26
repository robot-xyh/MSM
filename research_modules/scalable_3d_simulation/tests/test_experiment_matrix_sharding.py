from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.experiment_matrix import (
    EXPERIMENT_VARIANTS,
    ExperimentMatrixPlan,
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


def _base_config() -> ScenarioConfig:
    return ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        metadata={"online_truth_policy": "forbidden"},
    )


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


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
