from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

import research_modules.scalable_3d_simulation.learning_source_audit_gate as gate
from research_modules.scalable_3d_simulation.learning_source_audit_gate import (
    LearningSourceAuditGateError,
    SOURCE_AUDIT_CONFIRMATION,
    audit_only_permissions,
    build_learning_source_audit_authorization,
    build_learning_source_preflight_input,
    canonical_json_bytes,
    canonical_json_sha256,
    load_learning_source_audit_authorization,
    write_learning_source_audit_authorization,
    write_learning_source_preflight_input,
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _source_root(tmp_path: Path, module: str, manifest: str) -> Path:
    root = tmp_path / module
    count = gate.EXPECTED_EPISODE_COUNTS[module]
    common = {
        "schema_version": "fixture-v1",
        "module": module,
        "source_git_commit": {"D3": "3", "D4": "4", "D5": "5"}[module] * 40,
        "authorization_sha256": {"D3": "a", "D4": "b", "D5": "c"}[module] * 64,
        "module_request_sha256": {"D3": "d", "D4": "e", "D5": "f"}[module] * 64,
        "planned_episode_count": count,
    }
    _write_json(root / "generation_session.json", common)
    _write_json(root / "generation_checkpoint.json", common)
    (root / "episode_progress.jsonl").write_text("{}\n", encoding="utf-8")
    _write_json(root / manifest, {"schema_version": f"{module.lower()}-manifest-v1"})
    payload = root / "dataset/episode_payload.bin"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"must-not-be-opened")
    result = {
        **common,
        "artifact_inventory": {
            "file_count": 1,
            "total_size_bytes": payload.stat().st_size,
            "files": [
                {
                    "path": "dataset/episode_payload.bin",
                    "size_bytes": payload.stat().st_size,
                    "sha256": sha256(payload.read_bytes()).hexdigest(),
                }
            ],
            "tree_sha256": "0" * 64,
        },
    }
    _write_json(root / "generation_result.json", result)
    return root


def _ready_preflight(input_sha: str) -> dict[str, Any]:
    sources = {}
    for module, digit, count in (
        ("D3", "3", 300),
        ("D4", "4", 324),
        ("D5", "5", 104),
    ):
        sources[module] = {
            "module": module,
            "source_root": f"/outside/{module}",
            "status": "metadata_ready",
            "expected_episode_count": count,
            "progress_record_count": count,
            "unique_seed_count": count,
            "payload_file_open_count": 0,
            "full_payload_audit_performed": False,
            "artifact_inventory_verification_scope": (
                "producer_metadata_self_consistency_only"
            ),
            "artifact_inventory_producer_metadata_self_consistent": True,
            "artifact_inventory_payload_content_verified": False,
            "source_git_commit": digit * 40,
            "generation_authorization_sha256": "a" * 64,
            "module_request_sha256": "b" * 64,
            "artifact_inventory_tree_sha256": "c" * 64,
            "manifest_schema_field": {
                "D3": "schema_version",
                "D4": "schema",
                "D5": "schema_version",
            }[module],
            "manifest_schema_version": f"{module.lower()}-manifest-v1",
        }
    return {
        "schema_version": gate.SOURCE_PREFLIGHT_RESULT_SCHEMA,
        "status": "ready_for_explicit_d6_source_audit_authorization",
        "metadata_preflight_passed": True,
        "full_payload_audit_performed": False,
        "formal_source_data_read": False,
        "input_contract_sha256": input_sha,
        "permissions": {"training": False, "runtime": False, "control": False},
        "d6_control_participation": False,
        "sources": sources,
    }


def test_input_builder_reads_only_five_explicit_metadata_files_per_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = {
        "D3": "dataset/dataset_manifest.json",
        "D4": "dataset/manifest.json",
        "D5": "source_manifest.json",
    }
    roots = {
        module: _source_root(tmp_path, module, manifest)
        for module, manifest in manifests.items()
    }
    original = gate._read_bound_bytes
    opened: list[Path] = []

    def guarded(path: Path) -> bytes:
        opened.append(path)
        assert path.name != "episode_payload.bin"
        return original(path)

    monkeypatch.setattr(gate, "_read_bound_bytes", guarded)
    payload = build_learning_source_preflight_input(
        contract_id="d3-d4-d5-source-preflight-20260803-v1",
        source_roots=roots,
        manifest_paths=manifests,
    )

    assert [item["module"] for item in payload["sources"]] == ["D3", "D4", "D5"]
    assert len(opened) == 15
    assert {path.name for path in opened} == {
        "generation_session.json",
        "generation_checkpoint.json",
        "generation_result.json",
        "episode_progress.jsonl",
        "dataset_manifest.json",
        "manifest.json",
        "source_manifest.json",
    }
    output, digest = write_learning_source_preflight_input(
        tmp_path / "request/preflight-input.json", payload
    )
    assert output.is_file()
    assert digest == sha256(output.read_bytes()).hexdigest()


def test_input_builder_rejects_manifest_symlink(tmp_path: Path) -> None:
    roots = {
        module: _source_root(tmp_path, module, gate.DEFAULT_MANIFEST_PATHS[module])
        for module in gate.EXPECTED_EPISODE_COUNTS
    }
    manifest = roots["D4"] / gate.DEFAULT_MANIFEST_PATHS["D4"]
    target = manifest.with_name("manifest-target.json")
    manifest.replace(target)
    manifest.symlink_to(target.name)
    with pytest.raises(LearningSourceAuditGateError, match="symlink_forbidden"):
        build_learning_source_preflight_input(
            contract_id="d3-d4-d5-source-preflight-20260803-v2",
            source_roots=roots,
        )


def test_audit_authorization_is_read_only_and_exactly_bound(tmp_path: Path) -> None:
    input_sha = "1" * 64
    preflight = _ready_preflight(input_sha)
    authorization = build_learning_source_audit_authorization(
        preflight,
        authorization_id="d6-source-audit-20260803-v1",
        approver_id="main-test",
        approval_reason="independent source integrity audit",
        confirmation=SOURCE_AUDIT_CONFIRMATION,
        preflight_report_file_sha256="2" * 64,
        approved_at_utc=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    assert authorization["permissions"] == audit_only_permissions()
    assert authorization["permissions"]["source_payload_integrity_read"] is True
    for name in (
        "training",
        "model_inference",
        "future_held_out_model_consumption",
        "shadow",
        "assist",
        "assignment",
        "degradation",
        "camera_command",
        "runtime",
        "control",
        "global_track_id_create",
        "global_track_id_write",
    ):
        assert authorization["permissions"][name] is False
    path, digest = write_learning_source_audit_authorization(
        tmp_path / "authorization.json", authorization
    )
    loaded = load_learning_source_audit_authorization(
        path,
        expected_authorization_sha256=digest,
        expected_input_contract_sha256=input_sha,
        expected_preflight_result_sha256=canonical_json_sha256(preflight),
    )
    assert loaded == authorization


def test_audit_authorization_rejects_wrong_phrase_or_permission_escalation(
    tmp_path: Path,
) -> None:
    preflight = _ready_preflight("1" * 64)
    with pytest.raises(LearningSourceAuditGateError, match="confirmation"):
        build_learning_source_audit_authorization(
            preflight,
            authorization_id="d6-source-audit-20260803-v2",
            approver_id="main-test",
            approval_reason="test",
            confirmation="AUTHORIZE ALL",
            preflight_report_file_sha256="2" * 64,
        )
    authorization = build_learning_source_audit_authorization(
        preflight,
        authorization_id="d6-source-audit-20260803-v3",
        approver_id="main-test",
        approval_reason="test",
        confirmation=SOURCE_AUDIT_CONFIRMATION,
        preflight_report_file_sha256="2" * 64,
    )
    authorization["permissions"]["training"] = True
    with pytest.raises(LearningSourceAuditGateError, match="permission_escalation"):
        write_learning_source_audit_authorization(
            tmp_path / "bad-authorization.json", authorization
        )


def test_audit_authorization_rejects_preflight_that_read_payload() -> None:
    preflight = _ready_preflight("1" * 64)
    preflight["formal_source_data_read"] = True
    with pytest.raises(LearningSourceAuditGateError, match="formal_source_data_read"):
        build_learning_source_audit_authorization(
            preflight,
            authorization_id="d6-source-audit-20260803-v4",
            approver_id="main-test",
            approval_reason="test",
            confirmation=SOURCE_AUDIT_CONFIRMATION,
            preflight_report_file_sha256="2" * 64,
        )
