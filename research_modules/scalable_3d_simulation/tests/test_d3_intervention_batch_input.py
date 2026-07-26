from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
    load_isolated_intervention_batch_manifest,
    run_isolated_intervention_batch,
)
from research_modules.scalable_3d_simulation.d3_intervention_batch_input import (
    D3_INTERVENTION_BATCH_INPUT_CHECKSUMS,
    D3InterventionBatchCapture,
    D3InterventionBatchInputOptions,
    D3InterventionSeedCapture,
    write_d3_intervention_batch_input,
)
from research_modules.scalable_3d_simulation.learning_runtime import (
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import (
    Scalable3DEpisodeRunner,
)
from research_modules.scalable_3d_simulation.scenarios import (
    make_curriculum_scenario,
)


ROOT = Path(__file__).resolve().parents[3]
SOURCE_BUNDLE = (
    ROOT
    / "research_modules"
    / "d3_assignment_planner"
    / "outputs"
    / "formal_bc_development_20260720"
    / "bundle"
)


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _one_replayable_frame():
    config = make_curriculum_scenario(
        "nominal",
        scale=2,
        seed=31,
        duration_s=1.2,
    )
    resolved = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    result = Scalable3DEpisodeRunner(
        resolved.config,
        module_stack=resolved.stack,
    ).run()
    frames = tuple(
        frame
        for frame in resolved.stack.learning_artifacts().d3_planning_frames
        if frame.available
        and frame.learning_state == "rule_only"
        and frame.previous_plan is not None
        and frame.effective_matrix_result is not None
    )
    assert frames
    return frames[0], resolved.stack.d3.config, resolved.stack.d3.cost_model.weights


def _capture():
    frame, planner_config, cost_weights = _one_replayable_frame()
    seeds = tuple(
        D3InterventionSeedCapture(
            seed=seed,
            source_episode_id=f"fixture-episode-{seed}",
            source_manifest_sha256=sha256(
                f"fixture-manifest-{seed}".encode("ascii")
            ).hexdigest(),
            scenario_version="fixture-scenario-v1",
            frames=(frame,),
        )
        for seed in ISOLATED_INTERVENTION_BATCH_SEEDS_V1
    )
    return D3InterventionBatchCapture(
        options=D3InterventionBatchInputOptions(
            scenario="nominal",
            scale=2,
            batch_id="d3-fixture-20seed-v1",
            evaluated_at_utc="2026-07-26T12:00:00Z",
        ),
        repository_git_commit="a" * 40,
        planner_config=planner_config,
        cost_weights=cost_weights,
        seeds=seeds,
    )


def _copy_bundle(tmp_path: Path) -> Path:
    if not SOURCE_BUNDLE.is_dir():
        pytest.skip("frozen D3 development bundle is unavailable")
    bundle = tmp_path / "source-bundle"
    shutil.copytree(SOURCE_BUNDLE, bundle)
    return bundle


def test_writer_produces_strict_self_contained_manifest(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    capture = _capture()
    output = tmp_path / "input"

    paths = write_d3_intervention_batch_input(
        output,
        capture,
        bundle_dir=bundle,
        expected_bundle_manifest_sha256=_file_sha256(
            bundle / "manifest.json"
        ),
        expected_policy_version="d3_shared_edge_actor_critic_v1",
    )

    loaded = load_isolated_intervention_batch_manifest(paths["manifest"])
    assert loaded.repository_git_commit == "a" * 40
    assert tuple(item.seed for item in loaded.seeds) == (
        ISOLATED_INTERVENTION_BATCH_SEEDS_V1
    )
    assert all(len(item.frames) == 1 for item in loaded.seeds)
    assert loaded.planner_config == capture.planner_config
    assert loaded.cost_weights == capture.cost_weights
    summary = json.loads(paths["source_summary"].read_text(encoding="ascii"))
    assert summary["seed_count"] == 20
    assert summary["frame_count"] == 20
    assert summary["online_truth_use_count"] == 0
    assert summary["execution_boundary"] == {
        "learning_bundle_loaded_online": False,
        "physical_outcome_available": False,
        "production_assignment_authority": False,
        "production_control_authority": False,
        "reward_available": False,
        "runtime_ack_created": False,
        "treatment_plan_published": False,
    }
    checksums = paths["checksums"].read_text(encoding="ascii").splitlines()
    names = []
    for row in checksums:
        digest, name = row.split("  ", maxsplit=1)
        names.append(name)
        assert _file_sha256(output / name) == digest
    assert D3_INTERVENTION_BATCH_INPUT_CHECKSUMS not in names
    assert "bundle/manifest.json" in names
    assert "bundle/state_dict.pt" in names
    assert len([name for name in names if name.startswith("frames/")]) == 20

    replay = run_isolated_intervention_batch(
        paths["manifest"],
        tmp_path / "replay",
    )
    assert replay["seed_contract"]["seed_count"] == 20
    assert replay["execution_boundary"][
        "production_assignment_authority"
    ] is False
    assert replay["execution_boundary"]["production_control_authority"] is False

    with pytest.raises(FileExistsError):
        write_d3_intervention_batch_input(
            output,
            capture,
            bundle_dir=bundle,
        )


def test_writer_rejects_bundle_tampering_and_invalid_capture(
    tmp_path: Path,
) -> None:
    bundle = _copy_bundle(tmp_path)
    capture = _capture()
    state_path = bundle / "state_dict.pt"
    state_path.write_bytes(state_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="state dictionary SHA-256"):
        write_d3_intervention_batch_input(
            tmp_path / "tampered",
            capture,
            bundle_dir=bundle,
        )

    with pytest.raises(ValueError, match="exactly 1000-1019"):
        D3InterventionBatchInputOptions(reserved_seeds=(1000,))
    with pytest.raises(ValueError, match="ordered seeds"):
        D3InterventionBatchCapture(
            options=capture.options,
            repository_git_commit=capture.repository_git_commit,
            planner_config=capture.planner_config,
            cost_weights=capture.cost_weights,
            seeds=tuple(reversed(capture.seeds)),
        )


def test_manifest_configuration_is_plain_json(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    capture = _capture()
    output = tmp_path / "plain-json"
    paths = write_d3_intervention_batch_input(
        output,
        capture,
        bundle_dir=bundle,
    )
    payload = json.loads(paths["manifest"].read_text(encoding="ascii"))
    assert payload["planner_config"] == asdict(capture.planner_config)
    assert payload["cost_weights"] == asdict(capture.cost_weights)
