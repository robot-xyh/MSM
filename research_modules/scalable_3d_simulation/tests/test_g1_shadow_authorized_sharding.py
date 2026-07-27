from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_modules.scalable_3d_simulation import experiment_matrix_sharding as sharding
from research_modules.scalable_3d_simulation.experiment_authorization import (
    G1_SHADOW_APPROVAL_CONFIRMATION,
    approve_g1_shadow_authorization_request,
    build_g1_shadow_authorization_request,
    revoke_g1_shadow_authorization,
    write_g1_shadow_authorization_request,
    write_g1_shadow_revocation_registry,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (
    ExperimentMatrixPlan,
    ModelBundlePaths,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (
    EXPERIMENT_MATRIX_AUTHORIZED_EXECUTION_PLAN_SCHEMA,
    ExperimentMatrixShardError,
    create_experiment_matrix_execution_plan,
    describe_g1_shadow_d5_bundle,
    load_experiment_matrix_execution_plan,
    run_experiment_matrix_shard,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig


_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = "a" * 40


def test_authorized_g1_shard_is_bound_and_shadow_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    paths = _authorization_files(tmp_path, bundle, now)
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )
    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=_plan(),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        device="cpu",
        created_at_utc=now.isoformat(),
        experiment_authorization_path=paths["authorization"],
        expected_experiment_authorization_sha256=paths[
            "authorization_sha256"
        ],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )
    execution = load_experiment_matrix_execution_plan(plan_path)

    assert (
        execution["schema_version"]
        == EXPERIMENT_MATRIX_AUTHORIZED_EXECUTION_PLAN_SCHEMA
    )
    assert execution["scope"]["variants"] == ["G1"]
    assert (
        execution["experiment_authorization"]["permissions"][
            "g1_shadow_edge_scoring_granted"
        ]
        is True
    )
    assert (
        execution["experiment_authorization"]["permissions"][
            "control_authority_granted"
        ]
        is False
    )
    assert (
        execution["learning_bundles"]["variant_preflight"]["G1"]["status"]
        == "authorized_shadow_resolved"
    )

    monkeypatch.setattr(
        sharding,
        "_execute_learning_cell",
        _fake_execute_authorized_g1_cell,
    )
    result = run_experiment_matrix_shard(
        root=_ROOT,
        execution_plan_path=plan_path,
        shard_index=0,
        bundles=bundles,
        experiment_authorization_path=paths["authorization"],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )
    assert result["status"] == "complete"
    cell_result = json.loads(
        next((Path(result["shard_dir"]) / "cells").glob("*/cell_result.json"))
        .read_text(encoding="utf-8")
    )
    learning = cell_result["learning_runtime"]
    assert (
        learning["experiment_authorization_sha256"]
        == paths["authorization_sha256"]
    )
    assert learning["d5_g1_shadow_scoring_frame_count"] == 1
    assert learning["d5_g1_shadow_model_output_applied"] is False


def test_authorized_plan_and_runtime_fail_closed_without_complete_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    paths = _authorization_files(tmp_path, bundle, now)
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )
    with pytest.raises(
        ExperimentMatrixShardError,
        match="must be provided together",
    ):
        create_experiment_matrix_execution_plan(
            root=_ROOT,
            output_root=tmp_path / "incomplete",
            base_config=_base_config(),
            parent_plan=_plan(),
            scope_variants=("G1",),
            shard_count=1,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            authorization_now_utc=now,
        )

    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=_plan(),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        experiment_authorization_path=paths["authorization"],
        expected_experiment_authorization_sha256=paths[
            "authorization_sha256"
        ],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )
    with pytest.raises(
        ExperimentMatrixShardError,
        match="requires authorization and revocation",
    ):
        run_experiment_matrix_shard(
            root=_ROOT,
            execution_plan_path=plan_path,
            shard_index=0,
            bundles=bundles,
            authorization_now_utc=now,
        )

    revoke_g1_shadow_authorization(
        paths["revocations"],
        authorization_id="g1-shadow-shard-test",
        reason="operator stop",
        revoked_at_utc=now + timedelta(seconds=1),
    )
    with pytest.raises(
        ExperimentMatrixShardError,
        match="revoked",
    ):
        run_experiment_matrix_shard(
            root=_ROOT,
            execution_plan_path=plan_path,
            shard_index=0,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            revocation_registry_path=paths["revocations"],
            authorization_now_utc=now + timedelta(seconds=2),
        )


def test_authorized_shard_rechecks_expiry_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    paths = _authorization_files(tmp_path, bundle, now)
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )
    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=_plan(),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        experiment_authorization_path=paths["authorization"],
        expected_experiment_authorization_sha256=paths[
            "authorization_sha256"
        ],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )

    with pytest.raises(
        ExperimentMatrixShardError,
        match="expired",
    ):
        run_experiment_matrix_shard(
            root=_ROOT,
            execution_plan_path=plan_path,
            shard_index=0,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            revocation_registry_path=paths["revocations"],
            authorization_now_utc=now + timedelta(hours=2),
        )


def test_authorization_request_rejects_incomplete_d5_authority_contract(
    tmp_path: Path,
) -> None:
    bundle = _write_v5_bundle(tmp_path / "bundle")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["admission"]["authority_contract"]["runtime_authority"][
        "assignment_authority_granted"
    ]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ExperimentMatrixShardError,
        match="authority fields",
    ):
        describe_g1_shadow_d5_bundle(bundle)


def test_authorized_shard_rejects_dirty_runtime_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    paths = _authorization_files(tmp_path, bundle, now)
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )
    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=_plan(),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        experiment_authorization_path=paths["authorization"],
        expected_experiment_authorization_sha256=paths[
            "authorization_sha256"
        ],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, True),
    )

    with pytest.raises(
        ExperimentMatrixShardError,
        match="repository_dirty=false",
    ):
        run_experiment_matrix_shard(
            root=_ROOT,
            execution_plan_path=plan_path,
            shard_index=0,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            revocation_registry_path=paths["revocations"],
            authorization_now_utc=now,
        )


def test_authorized_plan_rechecks_source_after_freezing_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    paths = _authorization_files(tmp_path, bundle, now)
    states = iter(((_COMMIT, False), (_COMMIT, True)))
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: next(states),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )

    with pytest.raises(
        ExperimentMatrixShardError,
        match="source state changed",
    ):
        create_experiment_matrix_execution_plan(
            root=_ROOT,
            output_root=tmp_path / "execution",
            base_config=_base_config(),
            parent_plan=_plan(),
            scope_variants=("G1",),
            shard_count=1,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            expected_experiment_authorization_sha256=paths[
                "authorization_sha256"
            ],
            revocation_registry_path=paths["revocations"],
            authorization_now_utc=now,
        )


def test_authorized_cell_rejects_dirty_episode_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    paths = _authorization_files(tmp_path, bundle, now)
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )
    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=_plan(),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        experiment_authorization_path=paths["authorization"],
        expected_experiment_authorization_sha256=paths[
            "authorization_sha256"
        ],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )

    def _execute_dirty_cell(**kwargs: object) -> dict[str, object]:
        result = _fake_execute_authorized_g1_cell(**kwargs)
        episode_dir = Path(kwargs["cell_container"]) / "episode"
        manifest_path = episode_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["repository_dirty"] = True
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result["artifact_tree_sha256"] = sharding._tree_digest(
            episode_dir
        )
        return result

    monkeypatch.setattr(
        sharding,
        "_execute_learning_cell",
        _execute_dirty_cell,
    )
    with pytest.raises(
        ExperimentMatrixShardError,
        match="episode manifest is dirty",
    ):
        run_experiment_matrix_shard(
            root=_ROOT,
            execution_plan_path=plan_path,
            shard_index=0,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            revocation_registry_path=paths["revocations"],
            authorization_now_utc=now,
        )


def test_authorized_shard_rechecks_revocation_before_each_new_cell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    bundle = _write_v5_bundle(tmp_path / "bundle")
    bundles = ModelBundlePaths(d5_graph=bundle)
    seeds = (1000, 1001)
    paths = _authorization_files(tmp_path, bundle, now, seeds=seeds)
    monkeypatch.setattr(
        sharding,
        "repository_state",
        lambda root: (_COMMIT, False),
    )
    monkeypatch.setattr(
        sharding,
        "resolve_learning_runtime",
        _resolve_authorized_shadow,
    )
    plan_path = create_experiment_matrix_execution_plan(
        root=_ROOT,
        output_root=tmp_path / "execution",
        base_config=_base_config(),
        parent_plan=_plan(seeds=seeds),
        scope_variants=("G1",),
        shard_count=1,
        bundles=bundles,
        experiment_authorization_path=paths["authorization"],
        expected_experiment_authorization_sha256=paths[
            "authorization_sha256"
        ],
        revocation_registry_path=paths["revocations"],
        authorization_now_utc=now,
    )
    execution_count = 0

    def _execute_then_revoke(**kwargs: object) -> dict[str, object]:
        nonlocal execution_count
        result = _fake_execute_authorized_g1_cell(**kwargs)
        execution_count += 1
        if execution_count == 1:
            revoke_g1_shadow_authorization(
                paths["revocations"],
                authorization_id="g1-shadow-shard-test",
                reason="stop before second cell",
                revoked_at_utc=now + timedelta(seconds=1),
            )
        return result

    monkeypatch.setattr(
        sharding,
        "_execute_learning_cell",
        _execute_then_revoke,
    )
    with pytest.raises(
        ExperimentMatrixShardError,
        match="revoked",
    ):
        run_experiment_matrix_shard(
            root=_ROOT,
            execution_plan_path=plan_path,
            shard_index=0,
            bundles=bundles,
            experiment_authorization_path=paths["authorization"],
            revocation_registry_path=paths["revocations"],
            authorization_now_utc=now + timedelta(seconds=2),
        )
    assert execution_count == 1


def _authorization_files(
    tmp_path: Path,
    bundle: Path,
    now: datetime,
    *,
    seeds: tuple[int, ...] = (1000,),
) -> dict[str, object]:
    bundles = ModelBundlePaths(d5_graph=bundle)
    binding = sharding._build_learning_bundle_binding(("G1",), bundles)
    descriptor = sharding._authorization_d5_bundle_descriptor(
        binding,
        bundles,
    )
    request = build_g1_shadow_authorization_request(
        authorization_id="g1-shadow-shard-test",
        purpose="bounded sharded shadow comparison",
        source_git_commit=_COMMIT,
        scenarios=("nominal",),
        scales=(1,),
        seeds=seeds,
        duration_s=0.05,
        d5_bundle_manifest_sha256=descriptor["manifest_sha256"],
        d5_bundle_tree_sha256=descriptor["tree_sha256"],
        d5_weights_sha256=descriptor["weights_sha256"],
        device="cpu",
        not_before_utc=now - timedelta(minutes=1),
        expires_at_utc=now + timedelta(hours=1),
        revocation_registry_id="g1-shadow-shard-registry",
    )
    request_path = write_g1_shadow_authorization_request(
        tmp_path / "request.json",
        request,
    )
    revocations = write_g1_shadow_revocation_registry(
        tmp_path / "revocations.json",
        registry_id="g1-shadow-shard-registry",
        updated_at_utc=now,
    )
    authorization, digest = approve_g1_shadow_authorization_request(
        request_path,
        tmp_path / "authorization.json",
        expected_request_sha256=str(request["request_sha256"]),
        approver_id="local-test-operator",
        approval_reason="test-only bounded scope",
        confirmation=G1_SHADOW_APPROVAL_CONFIRMATION,
        approved_at_utc=now,
    )
    return {
        "authorization": authorization,
        "authorization_sha256": digest,
        "revocations": revocations,
    }


def _write_v5_bundle(path: Path) -> Path:
    path.mkdir()
    weights = path / "weights.pt"
    weights.write_bytes(b"test-v5-weights")
    weights_sha256 = sharding._sha256_file(weights)
    manifest = {
        "schema_version": "d5.tracklet-model-bundle.v5",
        "model_semantic_version": "1.0.0",
        "admission": {
            "g1_assist_eligible": True,
            "authority_contract": {
                "runtime_authority": {
                    "model_promotion_granted": False,
                    "g1_assist_granted": False,
                    "default_path_change_granted": False,
                    "assignment_authority_granted": False,
                    "failover_authority_granted": False,
                    "control_authority_granted": False,
                }
            },
        },
        "weights": {
            "filename": "weights.pt",
            "sha256": weights_sha256,
        },
    }
    (path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _base_config() -> ScenarioConfig:
    return ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        metadata={"online_truth_policy": "forbidden"},
    )


def _plan(
    *,
    seeds: tuple[int, ...] = (1000,),
) -> ExperimentMatrixPlan:
    return ExperimentMatrixPlan(
        variants=("R0", "G1"),
        scenarios=("nominal",),
        scales=(1,),
        seeds=seeds,
        duration_s=0.05,
        formal=False,
    )


def _authorized_diagnostics(device: str, authorization: object) -> dict[str, object]:
    return {
        "schema_version": "scalable3d-learning-runtime-v1",
        "device": device,
        "d3": {"bundle_loaded": False, "effective_mode": "disabled"},
        "d4": {"bundle_loaded": False, "effective_mode": "disabled"},
        "d5": {
            "bundle_loaded": True,
            "effective_mode": "authorized_shadow",
            "fallback_reason": None,
            "model_fingerprint": "1" * 64,
            "model_output_applied": False,
            "experiment_authorization_valid": True,
            "experiment_authorization_id": authorization.authorization_id,
            "experiment_authorization_sha256": (
                authorization.authorization_file_sha256
            ),
            "experiment_authorization_expires_at_utc": (
                authorization.expires_at_utc
            ),
        },
        "d5_active_vision": {
            "bundle_loaded": False,
            "effective_mode": "disabled",
            "assist_admitted": False,
        },
        "default_rule_path_preserved": True,
    }


def _resolve_authorized_shadow(
    config: ScenarioConfig,
    options: object,
    *,
    stack_config: object,
) -> SimpleNamespace:
    del stack_config
    authorization = options.d5_g1_shadow_authorization
    assert authorization is not None
    diagnostics = _authorized_diagnostics(options.device, authorization)
    metadata = dict(config.metadata)
    metadata["learning_runtime"] = diagnostics
    return SimpleNamespace(
        config=replace(
            config,
            d5_model_version="d5-crossview-gnn-v1.0.0+test",
            metadata=metadata,
        ),
        diagnostics=diagnostics,
        stack=None,
    )


def _fake_execute_authorized_g1_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    execution: dict[str, object],
    cell: dict[str, object],
    cell_container: Path,
    final_container: Path,
    device: str,
    bundles: ModelBundlePaths,
    experiment_authorization: object,
) -> dict[str, object]:
    del repository_root
    assert bundles.d5_graph is not None
    diagnostics = _authorized_diagnostics(
        device,
        experiment_authorization,
    )
    versions = dict(
        execution["learning_bundles"]["variant_preflight"]["G1"][
            "resolved_versions"
        ]
    )
    episode_dir = cell_container / "episode"
    episode_dir.mkdir()
    manifest = {
        "git_commit": execution["source"]["git_commit"],
        "repository_dirty": execution["source"]["repository_dirty"],
        "episode_id": f"fake-{cell['cell_id']}",
    }
    config = {
        **versions,
        "metadata": {
            "algorithm_variant": "G1",
            "matrix_execution_plan_sha256": execution[
                "execution_plan_sha256"
            ],
            "learning_runtime": diagnostics,
        },
    }
    module_summary = {
        "d5_g1_shadow_scoring_frame_count": 1,
        "d5_g1_shadow_scoring_success_count": 1,
        "d5_g1_shadow_scoring_rejected_count": 0,
        "d5_g1_shadow_model_output_applied": False,
    }
    summary = {
        "finite_state": True,
        "online_truth_use_count": 0,
        "real_time_factor": 1.0,
        "intercepted_target_count": 0,
        "module_final_diagnostics": module_summary,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
    ):
        (episode_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (episode_dir / "online_observations.jsonl").write_text("", encoding="utf-8")
    (episode_dir / "offline_proximity_intercepts.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    (episode_dir / "stage_timings.csv").write_text(
        "stage,wall_time_s\nfake,0.0\n",
        encoding="utf-8",
    )
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
        "artifact_tree_sha256": sharding._tree_digest(episode_dir),
        "metrics": {
            "finite_state": True,
            "online_truth_use_count": 0,
            "real_time_factor": 1.0,
            "intercepted_target_count": 0,
        },
        "learning_runtime": {
            "bundle_binding_sha256": execution["learning_bundles"][
                "binding_sha256"
            ],
            "diagnostics_sha256": sharding._digest_json(diagnostics),
            "resolved_versions": versions,
            "experiment_authorization_sha256": (
                experiment_authorization.authorization_file_sha256
            ),
            "d5_g1_shadow_scoring_frame_count": 1,
            "d5_g1_shadow_scoring_success_count": 1,
            "d5_g1_shadow_scoring_rejected_count": 0,
            "d5_g1_shadow_model_output_applied": False,
        },
        "status": "complete",
    }
