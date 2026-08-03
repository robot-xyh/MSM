from __future__ import annotations

import json
from pathlib import Path

import pytest

import research_modules.scalable_3d_simulation.learning_source_generation as generation
from research_modules.scalable_3d_simulation.learning_source_generation import (
    LearningSourceGenerationError,
    ModuleGenerationResult,
    SOURCE_GENERATION_FAILURE_SCHEMA_VERSION,
    SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION,
    run_authorized_learning_source_generation,
)
from research_modules.scalable_3d_simulation.learning_source_generation_authorization import (
    LearningSourceGenerationAuthorization,
    generation_only_permissions,
)


ROOT = Path(__file__).resolve().parents[3]


def _authorization() -> LearningSourceGenerationAuthorization:
    return LearningSourceGenerationAuthorization(
        authorization_id="source-generation-test-authorization",
        authorization_file_sha256="a" * 64,
        source_git_commit="b" * 40,
        preflight_sha256="c" * 64,
        registry_file_sha256="d" * 64,
        module_request_sha256={
            "D3": "3" * 64,
            "D4": "4" * 64,
            "D5": "5" * 64,
        },
        planned_episode_count={"D3": 300, "D4": 324, "D5": 104},
        permissions=generation_only_permissions(),
        approver_id="main-test",
        approval_reason="generation test",
        approved_at_utc="2026-08-01T00:00:00Z",
    )


def test_generation_main_binds_session_and_pauses_one_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization()
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: authorization,
    )

    def fake_generate(**kwargs):
        assert kwargs["authorization"] is authorization
        assert kwargs["max_episodes_per_run"] == 1
        return ModuleGenerationResult(
            module="D3",
            planned_episode_count=300,
            completed_episode_count=1,
            newly_completed_episode_count=1,
            finalized=False,
            finalization_summary=None,
        )

    monkeypatch.setattr(generation, "_generate_d3", fake_generate)
    output = tmp_path / "d3-source"
    result = run_authorized_learning_source_generation(
        module="D3",
        output_dir=output,
        authorization_path=tmp_path / "authorization.json",
        authorization_sha256="a" * 64,
        repository_root=ROOT,
        max_episodes_per_run=1,
        minimum_free_gb=0.0,
    )

    assert result["state"] == "paused"
    assert result["completed_episode_count"] == 1
    session = json.loads(
        (output / "generation_session.json").read_text(encoding="utf-8")
    )
    assert session["module"] == "D3"
    assert session["module_request_sha256"] == "3" * 64
    assert session["training"] is False
    assert session["control"] is False


def test_generation_resume_rejects_session_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization()
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: authorization,
    )
    monkeypatch.setattr(
        generation,
        "_generate_d3",
        lambda **kwargs: ModuleGenerationResult(
            module="D3",
            planned_episode_count=300,
            completed_episode_count=0,
            newly_completed_episode_count=0,
            finalized=False,
            finalization_summary=None,
        ),
    )
    output = tmp_path / "resume"
    common = {
        "module": "D3",
        "output_dir": output,
        "authorization_path": tmp_path / "authorization.json",
        "authorization_sha256": "a" * 64,
        "repository_root": ROOT,
        "minimum_free_gb": 0.0,
    }
    run_authorized_learning_source_generation(**common)
    session_path = output / "generation_session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    session["module_request_sha256"] = "f" * 64
    session_path.write_text(json.dumps(session), encoding="utf-8")

    with pytest.raises(
        LearningSourceGenerationError,
        match="resume_session_binding_mismatch",
    ):
        run_authorized_learning_source_generation(**common, resume=True)


def test_generation_resume_rejects_checkpoint_binding_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization()
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: authorization,
    )
    monkeypatch.setattr(
        generation,
        "_generate_d3",
        lambda **kwargs: ModuleGenerationResult(
            module="D3",
            planned_episode_count=300,
            completed_episode_count=1,
            newly_completed_episode_count=1,
            finalized=False,
            finalization_summary=None,
        ),
    )
    output = tmp_path / "checkpoint-drift"
    common = {
        "module": "D3",
        "output_dir": output,
        "authorization_path": tmp_path / "authorization.json",
        "authorization_sha256": "a" * 64,
        "repository_root": ROOT,
        "minimum_free_gb": 0.0,
    }
    run_authorized_learning_source_generation(**common)
    checkpoint_path = output / "generation_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["module_request_sha256"] = "f" * 64
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(
        LearningSourceGenerationError,
        match="generation_checkpoint_binding_mismatch",
    ):
        run_authorized_learning_source_generation(**common, resume=True)


def test_generation_failure_is_recorded_and_resume_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization()
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: authorization,
    )

    def fail_generation(**kwargs):
        generation._append_progress(
            kwargs["progress_path"],
            {
                "schema_version": SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION,
                "module": "D3",
                "source_git_commit": authorization.source_git_commit,
                "module_request_sha256": authorization.module_request_sha256["D3"],
            },
        )
        raise RuntimeError("writer_episode_minimum_not_met:episode-1")

    monkeypatch.setattr(generation, "_generate_d3", fail_generation)
    output = tmp_path / "failed-source"
    common = {
        "module": "D3",
        "output_dir": output,
        "authorization_path": tmp_path / "authorization.json",
        "authorization_sha256": "a" * 64,
        "repository_root": ROOT,
        "minimum_free_gb": 0.0,
    }

    with pytest.raises(RuntimeError, match="writer_episode_minimum_not_met"):
        run_authorized_learning_source_generation(**common)

    failure = json.loads(
        (output / "generation_failure.json").read_text(encoding="utf-8")
    )
    assert failure["schema_version"] == SOURCE_GENERATION_FAILURE_SCHEMA_VERSION
    assert failure["state"] == "failed_closed"
    assert failure["module"] == "D3"
    assert failure["progress_record_count"] == 1
    assert failure["requires_new_source_commit"] is True
    assert failure["requires_new_authorization"] is True
    assert failure["requires_new_output_directory"] is True
    assert failure["training_started"] is False
    assert failure["runtime_authority_granted"] is False
    assert failure["control_authority_granted"] is False
    assert not (output / "generation_checkpoint.json").exists()

    with pytest.raises(
        LearningSourceGenerationError,
        match="source_generation_failed_closed",
    ):
        run_authorized_learning_source_generation(**common, resume=True)


def test_progress_gap_is_recovered_only_as_expected_prefix(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    rows: list[dict[str, object]] = []
    authorization = _authorization()

    start = generation._reconcile_prefix(
        module="D3",
        rows=rows,
        inventory_count=2,
        expected_ids=("episode-0", "episode-1", "episode-2"),
        expected_seeds=(10, 11, 12),
        progress_path=path,
        authorization=authorization,
    )

    assert start == 2
    assert [row["sequence"] for row in rows] == [0, 1]
    assert all(
        row["status"] == "staged_episode_recovered_after_progress_gap"
        for row in rows
    )
    assert all(
        row["schema_version"] == SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION
        for row in rows
    )
    with pytest.raises(LearningSourceGenerationError, match="inventory_progress"):
        generation._reconcile_prefix(
            module="D3",
            rows=rows,
            inventory_count=1,
            expected_ids=("episode-0", "episode-1", "episode-2"),
            expected_seeds=(10, 11, 12),
            progress_path=path,
            authorization=authorization,
        )


def test_generation_rejects_symlink_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: _authorization(),
    )
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(LearningSourceGenerationError, match="output_symlink"):
        run_authorized_learning_source_generation(
            module="D3",
            output_dir=link,
            authorization_path=tmp_path / "authorization.json",
            authorization_sha256="a" * 64,
            repository_root=ROOT,
            minimum_free_gb=0.0,
        )


def test_generation_rejects_symlink_output_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: _authorization(),
    )
    real = tmp_path / "real-parent"
    real.mkdir()
    link = tmp_path / "linked-parent"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(LearningSourceGenerationError, match="output_symlink"):
        run_authorized_learning_source_generation(
            module="D3",
            output_dir=link / "source",
            authorization_path=tmp_path / "authorization.json",
            authorization_sha256="a" * 64,
            repository_root=ROOT,
            minimum_free_gb=0.0,
        )


def test_generation_rejects_unfrozen_base_config_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: _authorization(),
    )

    with pytest.raises(
        LearningSourceGenerationError,
        match="base_config_override_not_authorized",
    ):
        run_authorized_learning_source_generation(
            module="D3",
            output_dir=tmp_path / "source",
            authorization_path=tmp_path / "authorization.json",
            authorization_sha256="a" * 64,
            repository_root=ROOT,
            base_config_path=(
                ROOT
                / "research_modules/scalable_3d_simulation/configs/"
                "scalable_learning_global_seed_registry_v1.json"
            ),
            minimum_free_gb=0.0,
        )


def test_final_result_converts_module_paths_and_hashes_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: _authorization(),
    )

    def fake_finalize(**kwargs):
        (kwargs["output"] / "dataset.bin").write_bytes(b"source")
        return ModuleGenerationResult(
            module="D3",
            planned_episode_count=300,
            completed_episode_count=300,
            newly_completed_episode_count=300,
            finalized=True,
            finalization_summary={"dataset_dir": kwargs["output"] / "dataset"},
        )

    monkeypatch.setattr(generation, "_generate_d3", fake_finalize)
    output = tmp_path / "final"
    result = run_authorized_learning_source_generation(
        module="D3",
        output_dir=output,
        authorization_path=tmp_path / "authorization.json",
        authorization_sha256="a" * 64,
        repository_root=ROOT,
        minimum_free_gb=0.0,
    )

    assert result["state"] == "finalized"
    assert isinstance(result["finalization_summary"]["dataset_dir"], str)
    assert result["artifact_inventory"]["file_count"] >= 3
    json.dumps(result, allow_nan=False)

    with pytest.raises(
        LearningSourceGenerationError,
        match="source_generation_already_finalized",
    ):
        run_authorized_learning_source_generation(
            module="D3",
            output_dir=output,
            authorization_path=tmp_path / "authorization.json",
            authorization_sha256="a" * 64,
            repository_root=ROOT,
            minimum_free_gb=0.0,
            resume=True,
        )


def test_authorized_episode_count_must_match_frozen_inventory() -> None:
    authorization = _authorization()

    generation._assert_authorized_episode_count("D3", 300, authorization)
    with pytest.raises(
        LearningSourceGenerationError,
        match="D3_authorized_episode_count_mismatch",
    ):
        generation._assert_authorized_episode_count("D3", 299, authorization)
