from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.learning_source_preflight import (
    LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION,
    LearningSourcePreflightError,
    assemble_learning_source_preflight,
    evaluate_learning_source_preflight,
    write_learning_source_preflight_report,
)


ROOT = Path(__file__).resolve().parents[3]


def test_repository_preflight_fails_closed_on_missing_producer_adapters() -> None:
    report = evaluate_learning_source_preflight(repository_root=ROOT)

    assert report["schema_version"] == LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION
    assert report["status"] == (
        "blocked_by_producer_adapter_or_module_readiness"
    )
    assert report["all_module_plans_ready"] is True
    assert report["all_producer_adapters_complete"] is False
    assert report["all_generation_requests_ready"] is False
    assert type(report["source_worktree_clean"]) is bool
    assert report["execution_plan_ready"] is False
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
