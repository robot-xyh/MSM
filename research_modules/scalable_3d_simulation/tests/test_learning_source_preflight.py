from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.learning_source_preflight import (
    LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION,
    LearningSourcePreflightError,
    assemble_learning_source_preflight,
    evaluate_learning_source_preflight,
    _validated_module_generation_request,
    write_learning_source_preflight_report,
)


ROOT = Path(__file__).resolve().parents[3]


def test_repository_preflight_binds_all_requests_but_still_requires_clean_source() -> None:
    report = evaluate_learning_source_preflight(repository_root=ROOT)

    assert report["schema_version"] == LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION
    assert report["status"] == (
        "ready_for_explicit_main_execution_authorization"
        if report["source_worktree_clean"]
        else "blocked_by_dirty_generation_worktree"
    )
    assert report["all_module_plans_ready"] is True
    assert report["all_producer_adapters_complete"] is True
    assert report["all_generation_requests_ready"] is True
    assert type(report["source_worktree_clean"]) is bool
    assert report["execution_plan_ready"] is report["source_worktree_clean"]
    assert report["execution_authorized"] is False
    assert report["generation_commands"] == []
    assert report["generation_started"] is False
    assert report["training_started"] is False
    assert report["formal_seed_payload_read"] is False
    assert report["formal_shards_10_19_run"] is False
    assert report["registry"]["allocated_seed_count"] == 728
    assert report["modules"]["D3"]["producer"]["planned_episode_count"] == 300
    assert report["modules"]["D4"]["producer"]["planned_episode_count"] == 324
    assert report["modules"]["D5"]["producer"]["planned_episode_count"] == 104
    for module in ("D3", "D4", "D5"):
        producer = report["modules"][module]["producer"]
        assert producer["producer_adapter_complete"] is True
        assert producer["source_generation_request_ready"] is True
        assert producer["source_generation_request_path"]
        assert len(producer["source_generation_request_sha256"]) == 64
        assert producer["adapter_self_check"]["status"] == (
            "pass_authority_free_in_memory_smoke"
        )
        assert producer["adapter_self_check"]["online_truth_use_count"] == 0
        assert producer["adapter_self_check"]["formal_inventory_generated"] is False
    assert all(value is False for value in report["permissions"].values())


def test_preflight_report_writer_preserves_authority_free_state(
    tmp_path: Path,
) -> None:
    report = evaluate_learning_source_preflight(repository_root=ROOT)

    paths = write_learning_source_preflight_report(report, tmp_path / "report")

    decoded = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert decoded["execution_authorized"] is False
    assert decoded["generation_commands"] == []
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "生产器适配完整性" in markdown
    assert "1000--1019 未读取" in markdown


def test_assembly_rejects_generation_request_without_adapter() -> None:
    modules = {
        "D3": {"ready": True},
        "D4": {"generation_prerequisites_ready": True},
        "D5": {"plan_ready": True},
    }
    producers = {
        "D3": {
            "producer_adapter_complete": False,
            "source_generation_request_ready": True,
            "blockers": [],
        },
        "D4": {
            "producer_adapter_complete": True,
            "source_generation_request_ready": True,
            "blockers": [],
        },
        "D5": {
            "producer_adapter_complete": True,
            "source_generation_request_ready": True,
            "blockers": [],
        },
    }

    with pytest.raises(
        LearningSourcePreflightError,
        match="generation_request_inconsistent: D3",
    ):
        assemble_learning_source_preflight(
            registry={},
            module_reports=modules,
            producer_assessments=producers,
            source_state={},
        )


def test_all_ready_still_requires_explicit_main_authorization() -> None:
    modules = {
        "D3": {"ready": True},
        "D4": {"generation_prerequisites_ready": True},
        "D5": {"plan_ready": True},
    }
    producers = {
        module: {
            "producer_adapter_complete": True,
            "source_generation_request_ready": True,
            "blockers": [],
        }
        for module in ("D3", "D4", "D5")
    }

    report = assemble_learning_source_preflight(
        registry={},
        module_reports=modules,
        producer_assessments=producers,
        source_state={"repository_dirty": False},
    )

    assert report["status"] == (
        "ready_for_explicit_main_execution_authorization"
    )
    assert report["execution_plan_ready"] is True
    assert report["execution_authorized"] is False
    assert report["generation_commands"] == []
    assert all(value is False for value in report["permissions"].values())


def test_all_ready_still_blocks_dirty_generation_worktree() -> None:
    modules = {
        "D3": {"ready": True},
        "D4": {"generation_prerequisites_ready": True},
        "D5": {"plan_ready": True},
    }
    producers = {
        module: {
            "producer_adapter_complete": True,
            "source_generation_request_ready": True,
            "blockers": [],
        }
        for module in ("D3", "D4", "D5")
    }

    report = assemble_learning_source_preflight(
        registry={},
        module_reports=modules,
        producer_assessments=producers,
        source_state={"repository_dirty": True},
    )

    assert report["status"] == "blocked_by_dirty_generation_worktree"
    assert report["source_worktree_clean"] is False
    assert report["execution_plan_ready"] is False
    assert report["execution_authorized"] is False
    assert report["generation_commands"] == []
    assert "generation_worktree_dirty" in report["blockers"]
    assert all(value is False for value in report["permissions"].values())


def test_module_request_binding_rejects_hash_drift_and_symlink(
    tmp_path: Path,
) -> None:
    relative = Path("configs/request.json")
    request = tmp_path / relative
    request.parent.mkdir()
    request.write_text("{}\n", encoding="utf-8")
    digest = sha256(request.read_bytes()).hexdigest()
    report = {
        "source_generation_request_ready": True,
        "source_generation_request_path": relative.as_posix(),
        "source_generation_request_sha256": digest,
    }
    bound = _validated_module_generation_request(
        tmp_path, "D3", report, relative
    )
    assert bound["ready"] is True
    request.write_text("{\"drift\":true}\n", encoding="utf-8")
    with pytest.raises(
        LearningSourcePreflightError,
        match="source_generation_request_sha256_mismatch",
    ):
        _validated_module_generation_request(tmp_path, "D3", report, relative)

    request.unlink()
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    request.symlink_to(target)
    report["source_generation_request_sha256"] = sha256(
        target.read_bytes()
    ).hexdigest()
    with pytest.raises(
        LearningSourcePreflightError,
        match="source_generation_request_symlink_forbidden",
    ):
        _validated_module_generation_request(tmp_path, "D3", report, relative)
