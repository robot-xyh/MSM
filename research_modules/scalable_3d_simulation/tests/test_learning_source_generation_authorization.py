from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.learning_source_generation_authorization import (
    LearningSourceGenerationAuthorizationError,
    SOURCE_GENERATION_CONFIRMATION,
    build_learning_source_generation_authorization,
    generation_only_permissions,
    load_learning_source_generation_authorization,
    write_learning_source_generation_authorization,
)
from research_modules.scalable_3d_simulation.learning_source_preflight import (
    LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION,
)


def _preflight() -> dict[str, object]:
    return {
        "schema_version": LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION,
        "status": "ready_for_explicit_main_execution_authorization",
        "all_module_plans_ready": True,
        "all_producer_adapters_complete": True,
        "all_generation_requests_ready": True,
        "source_worktree_clean": True,
        "execution_plan_ready": True,
        "execution_authorized": False,
        "generation_started": False,
        "training_started": False,
        "formal_seed_payload_read": False,
        "formal_shards_10_19_run": False,
        "generation_commands": [],
        "permissions": {
            "generation": False,
            "training": False,
            "runtime": False,
            "control": False,
        },
        "source_state": {
            "git_commit": "1" * 40,
            "repository_dirty": False,
        },
        "registry": {"file_sha256": "2" * 64},
        "modules": {
            module: {
                "producer": {
                    "source_generation_request_sha256": digit * 64,
                    "planned_episode_count": count,
                }
            }
            for module, digit, count in (
                ("D3", "3", 300),
                ("D4", "4", 324),
                ("D5", "5", 104),
            )
        },
    }


def test_generation_authorization_is_generation_only(tmp_path: Path) -> None:
    payload = build_learning_source_generation_authorization(
        _preflight(),
        authorization_id="source-generation-test-001",
        approver_id="main-test",
        approval_reason="execute frozen source plans",
        confirmation=SOURCE_GENERATION_CONFIRMATION,
        approved_at_utc=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    assert payload["planned_episode_count"] == {
        "D3": 300,
        "D4": 324,
        "D5": 104,
    }
    assert payload["total_planned_episode_count"] == 728
    assert payload["permissions"] == generation_only_permissions()
    assert payload["permissions"]["dataset_generation"] is True
    assert all(
        value is False
        for name, value in payload["permissions"].items()
        if name != "dataset_generation"
    )
    path, digest = write_learning_source_generation_authorization(
        tmp_path / "authorization.json", payload
    )
    assert path.is_file()
    assert len(digest) == 64
    decoded = json.loads(path.read_text(encoding="utf-8"))
    assert decoded == payload


def test_generation_authorization_rejects_unready_or_wrong_confirmation() -> None:
    with pytest.raises(
        LearningSourceGenerationAuthorizationError,
        match="confirmation",
    ):
        build_learning_source_generation_authorization(
            _preflight(),
            authorization_id="source-generation-test-001",
            approver_id="main-test",
            approval_reason="test",
            confirmation="APPROVE",
        )

    preflight = _preflight()
    preflight["all_generation_requests_ready"] = False
    with pytest.raises(
        LearningSourceGenerationAuthorizationError,
        match="preflight_not_ready",
    ):
        build_learning_source_generation_authorization(
            preflight,
            authorization_id="source-generation-test-002",
            approver_id="main-test",
            approval_reason="test",
            confirmation=SOURCE_GENERATION_CONFIRMATION,
        )


def test_generation_authorization_rejects_missing_request_hash_or_escalation(
    tmp_path: Path,
) -> None:
    preflight = _preflight()
    preflight["modules"]["D4"]["producer"].pop(
        "source_generation_request_sha256"
    )
    with pytest.raises(
        LearningSourceGenerationAuthorizationError,
        match="request_sha256",
    ):
        build_learning_source_generation_authorization(
            preflight,
            authorization_id="source-generation-test-003",
            approver_id="main-test",
            approval_reason="test",
            confirmation=SOURCE_GENERATION_CONFIRMATION,
        )

    payload = build_learning_source_generation_authorization(
        _preflight(),
        authorization_id="source-generation-test-004",
        approver_id="main-test",
        approval_reason="test",
        confirmation=SOURCE_GENERATION_CONFIRMATION,
    )
    payload["permissions"]["training"] = True
    with pytest.raises(
        LearningSourceGenerationAuthorizationError,
        match="permission_escalation",
    ):
        write_learning_source_generation_authorization(
            tmp_path / "bad.json", payload
        )


def test_generation_authorization_load_rechecks_clean_source_and_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import research_modules.scalable_3d_simulation.learning_source_generation_authorization as module

    preflight = _preflight()
    payload = build_learning_source_generation_authorization(
        preflight,
        authorization_id="source-generation-test-005",
        approver_id="main-test",
        approval_reason="test",
        confirmation=SOURCE_GENERATION_CONFIRMATION,
    )
    path, digest = write_learning_source_generation_authorization(
        tmp_path / "authorization.json", payload
    )
    monkeypatch.setattr(
        module, "_repository_state", lambda root: ("1" * 40, False)
    )
    monkeypatch.setattr(
        module, "evaluate_learning_source_preflight", lambda repository_root: preflight
    )

    loaded = load_learning_source_generation_authorization(
        path,
        repository_root=tmp_path,
        expected_authorization_sha256=digest,
    )

    loaded.assert_module("D3")
    assert loaded.planned_episode_count["D5"] == 104
    monkeypatch.setattr(
        module, "_repository_state", lambda root: ("1" * 40, True)
    )
    with pytest.raises(
        LearningSourceGenerationAuthorizationError,
        match="repository_dirty",
    ):
        load_learning_source_generation_authorization(
            path,
            repository_root=tmp_path,
            expected_authorization_sha256=digest,
        )


def test_generation_authorization_load_rejects_symlink_before_resolution(
    tmp_path: Path,
) -> None:
    payload = build_learning_source_generation_authorization(
        _preflight(),
        authorization_id="source-generation-test-006",
        approver_id="main-test",
        approval_reason="test",
        confirmation=SOURCE_GENERATION_CONFIRMATION,
    )
    path, digest = write_learning_source_generation_authorization(
        tmp_path / "authorization.json", payload
    )
    link = tmp_path / "authorization-link.json"
    link.symlink_to(path.name)

    with pytest.raises(
        LearningSourceGenerationAuthorizationError,
        match="authorization_file_symlink_forbidden",
    ):
        load_learning_source_generation_authorization(
            link,
            repository_root=tmp_path,
            expected_authorization_sha256=digest,
        )
