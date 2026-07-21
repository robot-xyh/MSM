from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

import d5_terminal_association.canonical_seed_view as canonical_module
from d5_terminal_association.active_vision_curriculum_dataset import (
    ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT,
    generate_active_vision_supplemental_curriculum,
)
from d5_terminal_association.active_vision_supplemental_bc_audit import (
    ActiveVisionSupplementalBcAuditError,
    ActiveVisionSupplementalBcExpectedBindings,
    audit_active_vision_supplemental_bc_dataset,
)
from d5_terminal_association.canonical_seed_view import (
    EXPECTED_CONSUMER_CONTRACT,
    EXPECTED_MINIMUM_TEST_SEED_COUNT,
    EXPECTED_SPLIT_SEED,
    EXPECTED_TEST_FRACTION,
    EXPECTED_UNIT,
    EXPECTED_VALIDATION_FRACTION,
    ORDERING_COMPATIBILITY_VERSION,
    SHARED_SEED_SPLIT_POLICY_VERSION,
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
)


CREATED_AT = "2026-07-21T12:00:00Z"
SOURCE_COMMIT = "c" * 40
GLOBAL_TRACK_ID = "CENTER-TRACK-SUPPLEMENTAL-BC-AUDIT"
SPLITS = ("train", "validation", "test")


@pytest.fixture(scope="module")
def supplemental_bc_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("supplemental-bc-audit")
    training_registry, shared_registry = _write_registries(
        root / "registry-source"
    )
    output = root / "generated" / "supplemental-curriculum"
    generated = generate_active_vision_supplemental_curriculum(
        output,
        training_seed_registry_path=training_registry,
        shared_seed_registry_path=shared_registry,
        created_at_utc=CREATED_AT,
        global_track_id=GLOBAL_TRACK_ID,
        source_git_commit=SOURCE_COMMIT,
        source_repository_dirty=False,
    )
    summary = dict(generated.summary)
    expected = ActiveVisionSupplementalBcExpectedBindings(
        dataset_manifest_sha256=summary["dataset"]["manifest_sha256"],
        canonical_view_sha256=summary["canonical"]["view_manifest_sha256"],
        dataset_config_sha256=summary["source_binding"]["dataset_config_sha256"],
        training_registry_sha256=summary["source_binding"][
            "training_seed_registry_sha256"
        ],
        shared_registry_sha256=summary["source_binding"][
            "shared_seed_registry_sha256"
        ],
        summary_content_sha256=summary["content_sha256"],
        source_git_commit=SOURCE_COMMIT,
    )
    return {
        "root": root,
        "output": output,
        "dataset": output / "dataset",
        "view": output / "canonical_seed_view.json",
        "summary": output / "curriculum_summary.json",
        "training_registry": training_registry,
        "shared_registry": shared_registry,
        "expected": expected,
    }


def test_full_sample_audit_is_complete_deterministic_and_chinese(
    supplemental_bc_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    fixture = supplemental_bc_fixture
    first_json = tmp_path / "first" / "audit.json"
    first_markdown = tmp_path / "first" / "audit.md"
    first = _run_audit(fixture, first_json, first_markdown)

    assert first["audit"] == {
        "passed": True,
        "violation_count": 0,
        "violations": [],
    }
    assert first["admission"] == {
        "behavior_cloning_full_sample_audit": "complete",
        "d6_cross_module_learning_admission": "pending_external_audit",
        "ppo": False,
        "assist": False,
        "online_authority": False,
        "camera_command_authority": False,
        "rule_fallback_required": True,
        "model_training_performed": False,
        "weights_written": False,
    }
    assert first["coverage"] == {
        "episode_count": 100,
        "segment_count": 800,
        "sample_count": 1200,
        "intent_counts": {
            "hold": 200,
            "observe_target": 600,
            "reacquire": 200,
            "search_sector": 200,
        },
        "fov_mode_counts": {"wide": 1000, "zoom": 200},
        "camera_role_counts": {"interceptor": 600, "recon": 600},
        "canonical_episode_counts": {
            "train": 60,
            "validation": 20,
            "test": 20,
        },
        "canonical_sample_counts": {
            "train": 720,
            "validation": 240,
            "test": 240,
        },
    }
    inventory = first["artifact_integrity"]
    assert inventory["supplemental_output_file_count"] == 308
    assert inventory["dataset_file_count_including_sha256sums"] == 303
    assert inventory["checksummed_file_count"] == 302
    assert inventory["sha256_verified_file_count"] == 302
    assert inventory["sha256_mismatch_file_count"] == 0
    assert inventory["online_file_count"] == 100
    assert inventory["offline_file_count"] == 100
    assert inventory["episode_descriptor_file_count"] == 100
    assert inventory["descriptor_manifest_match_count"] == 100
    assert inventory["source_artifacts_unchanged"] is True

    features = first["behavior_cloning_feature_audit"]
    assert features["sample_count"] == 1200
    assert features["finite_feature_sample_count"] == 1200
    assert features["nonfinite_feature_sample_count"] == 0
    assert features["candidate_row_count"] == 7800
    assert features["candidate_count_histogram"] == {"4": 200, "7": 1000}
    assert features["selected_action_unique_candidate_count"] == 1200
    assert features["version_monotonic_episode_count"] == 100
    assert features["numeric_seed_atomic"] is True
    assert features["reserved_evaluation_seed_overlap"] == []
    assert features["global_track_id_created_rewritten_or_rebound"] is False

    assert first["synthetic_ack_fault_coverage"]["counts"] == {
        "applied": 400,
        "rejected": 400,
        "missing": 400,
    }
    assert first["synthetic_ack_fault_coverage"][
        "real_runtime_distribution_evidence"
    ] is False
    for label_name in ("reward", "outcome", "counterfactual", "causal_label"):
        assert first["offline_label_availability"][label_name] == {
            "status": "unavailable",
            "available_sample_count": 0,
            "sample_count": 1200,
        }
    assert first["offline_label_availability"]["zero_padding_used"] is False

    markdown = first_markdown.read_text(encoding="utf-8")
    assert markdown.startswith("# D5 主动视觉补充行为克隆全样本准入审计\n")
    assert "验收阈值为 100 episode、1200 sample" in markdown
    assert "仅表示 synthetic 确定性故障注入覆盖" in markdown
    assert "不是实际运行 ACK 分布" in markdown
    assert "D6 跨模块学习准入的前置证据" in markdown

    second_json = tmp_path / "second" / "audit.json"
    second_markdown = tmp_path / "second" / "audit.md"
    second = _run_audit(fixture, second_json, second_markdown)
    assert second == first
    assert second_json.read_bytes() == first_json.read_bytes()
    assert second_markdown.read_bytes() == first_markdown.read_bytes()


def test_binding_mismatch_writes_pending_fail_closed_report(
    supplemental_bc_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    fixture = dict(supplemental_bc_fixture)
    fixture["expected"] = replace(
        fixture["expected"],
        dataset_config_sha256="0" * 64,
    )
    output_json = tmp_path / "pending" / "audit.json"
    output_markdown = tmp_path / "pending" / "audit.md"

    report = _run_audit(fixture, output_json, output_markdown)

    assert report["audit"]["passed"] is False
    assert report["admission"]["behavior_cloning_full_sample_audit"] == "pending"
    assert report["binding_checks"]["dataset_config_sha256"] == {
        "expected": "0" * 64,
        "actual": supplemental_bc_fixture["expected"].dataset_config_sha256,
        "passed": False,
    }
    assert any(
        item.startswith("binding_mismatch:dataset_config_sha256")
        for item in report["audit"]["violations"]
    )
    assert json.loads(output_json.read_text(encoding="utf-8")) == report
    assert "审计结论：`pending`" in output_markdown.read_text(encoding="utf-8")
    assert report["admission"]["ppo"] is False
    assert report["admission"]["assist"] is False
    assert report["admission"]["rule_fallback_required"] is True


def test_source_hash_tamper_is_reported_without_rewriting_source(
    supplemental_bc_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    copied_output = tmp_path / "copied-source"
    shutil.copytree(supplemental_bc_fixture["output"], copied_output)
    tampered_online = next((copied_output / "dataset" / "online").iterdir())
    tampered_online.chmod(0o644)
    tampered_online.write_bytes(tampered_online.read_bytes() + b"tamper")
    tampered_sha = _sha256_file(tampered_online)
    fixture = {
        **supplemental_bc_fixture,
        "output": copied_output,
        "dataset": copied_output / "dataset",
        "view": copied_output / "canonical_seed_view.json",
        "summary": copied_output / "curriculum_summary.json",
    }

    report = _run_audit(
        fixture,
        tmp_path / "tamper-report" / "audit.json",
        tmp_path / "tamper-report" / "audit.md",
    )

    assert report["audit"]["passed"] is False
    assert report["admission"]["behavior_cloning_full_sample_audit"] == "pending"
    assert report["artifact_integrity"]["sha256_mismatch_file_count"] == 1
    assert any(
        item.startswith("artifact_sha_mismatch:online/")
        for item in report["audit"]["violations"]
    )
    assert _sha256_file(tampered_online) == tampered_sha


def test_audit_outputs_are_rejected_inside_registry_source_root(
    supplemental_bc_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    fixture = supplemental_bc_fixture
    training_sha_before = _sha256_file(fixture["training_registry"])
    shared_sha_before = _sha256_file(fixture["shared_registry"])
    forbidden_paths = (
        fixture["training_registry"].parent / "audit.json",
        fixture["output"] / "audit.json",
    )
    for index, forbidden_json in enumerate(forbidden_paths):
        allowed_markdown = tmp_path / f"audit-{index}.md"
        with pytest.raises(
            ActiveVisionSupplementalBcAuditError,
            match="outside protected source root",
        ):
            _run_audit(fixture, forbidden_json, allowed_markdown)
        assert not forbidden_json.exists()
        assert not allowed_markdown.exists()
    assert _sha256_file(fixture["training_registry"]) == training_sha_before
    assert _sha256_file(fixture["shared_registry"]) == shared_sha_before


def _run_audit(
    fixture: dict[str, Any],
    output_json: Path,
    output_markdown: Path,
) -> dict[str, Any]:
    return audit_active_vision_supplemental_bc_dataset(
        fixture["dataset"],
        canonical_view_path=fixture["view"],
        training_seed_registry_path=fixture["training_registry"],
        shared_seed_registry_path=fixture["shared_registry"],
        supplemental_summary_path=fixture["summary"],
        expected=fixture["expected"],
        output_json_path=output_json,
        output_markdown_path=output_markdown,
        validation_date="2026-07-21",
    )


def _write_registries(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    training = {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": sha256(b"d5-bc-audit-test-schedule").hexdigest(),
        "training_seed_count": ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }
    training_path = root / "training_seed_registry.json"
    _write_json(training_path, training)
    assignment = canonical_module._canonical_assignment(tuple(range(100)))
    assignments = [
        {"seed": seed, "split": assignment[seed]} for seed in range(100)
    ]
    shared = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": ORDERING_COMPATIBILITY_VERSION,
        "source": {
            "training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
            "training_seed_registry_sha256": _sha256_file(training_path),
            "git_commit": training["git_commit"],
            "repository_dirty": training["repository_dirty"],
            "schedule_sha256": training["schedule_sha256"],
        },
        "unit": EXPECTED_UNIT,
        "split_seed": EXPECTED_SPLIT_SEED,
        "validation_fraction": EXPECTED_VALIDATION_FRACTION,
        "test_fraction": EXPECTED_TEST_FRACTION,
        "minimum_test_seed_count": EXPECTED_MINIMUM_TEST_SEED_COUNT,
        "training_seed_count": len(training["training_seeds"]),
        "reserved_evaluation_seed_count": len(
            training["reserved_evaluation_seeds"]
        ),
        "reserved_evaluation_seeds": training["reserved_evaluation_seeds"],
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            split: sorted(
                seed for seed, assigned in assignment.items() if assigned == split
            )
            for split in SPLITS
        },
        "assignments": assignments,
        "assignment_sha256": canonical_module._sha256_json(assignments),
        "consumer_contract": dict(EXPECTED_CONSUMER_CONTRACT),
    }
    shared["content_sha256"] = canonical_module._sha256_json(shared)
    shared_path = root / "registry.json"
    _write_json(shared_path, shared)
    return training_path, shared_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
