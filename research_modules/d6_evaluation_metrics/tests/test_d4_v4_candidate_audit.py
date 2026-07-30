from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d6_evaluation_metrics.d4_v4_candidate_audit import (
    D4V4CandidateAuditError,
    audit_d4_v4_candidate,
    load_d4_v4_candidate_audit_inputs,
    write_d4_v4_candidate_audit_report,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INPUT_SPEC = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/configs/"
    "d4_v4_candidate_independent_audit_20260729.json"
)


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _inputs():
    return load_d4_v4_candidate_audit_inputs(
        INPUT_SPEC,
        repository_root=REPOSITORY_ROOT,
    )


def test_d4_v4_real_candidate_recalculates_without_test_payload_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()
    manifest = json.loads(
        (
            inputs.external_evidence_root / "dataset/manifest.json"
        ).read_text(encoding="utf-8")
    )
    forbidden_test_paths = {
        (
            inputs.external_evidence_root
            / "dataset"
            / item["relative_path"]
        ).resolve()
        for item in manifest["episodes"]
        if item["split"] == "test"
    }
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def guarded_read_bytes(path: Path) -> bytes:
        if path.resolve() in forbidden_test_paths:
            raise AssertionError(f"test payload read: {path}")
        return original_read_bytes(path)

    def guarded_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.resolve() in forbidden_test_paths:
            raise AssertionError(f"test payload read: {path}")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    result = audit_d4_v4_candidate(inputs)

    assert result["audit_passed"] is True
    assert result["status"] == (
        "pass_development_integrity_only_admission_closed"
    )
    assert result["admission_blocker_codes"] == [
        "candidate_unregistered",
        "formal_holdout_not_completed",
        "runtime_preflight_not_completed",
        "development_fixture_train_domain_smoke_only",
        "confidence_positive_recall_low",
        "confidence_threshold_passing_margin_too_thin",
        "runtime_outcome_and_benefit_unavailable",
    ]
    assert result["candidate_tree"]["file_count"] == 180
    assert result["candidate_tree"]["artifact_file_count"] == 179
    assert result["candidate_tree"]["all_artifacts_manifest_bound"] is True
    assert result["source_lineage"]["source_git_commit"] == (
        "fd857457bb27a4a709a7c4937e22ebe1cbd7f848"
    )
    assert result["external_dataset_binding"]["dataset_sha256"] == (
        "b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c"
    )

    governance = result["dataset_and_use_governance"]
    assert governance["train"]["frame_count"] == 350
    assert governance["train"]["target_positive_count"] == 60
    assert governance["train"]["target_negative_count"] == 290
    assert governance["validation"]["frame_count"] == 75
    assert governance["validation"]["target_positive_count"] == 15
    assert governance["validation"]["target_negative_count"] == 60
    assert governance["test"] == {
        "manifest_seed_count": 15,
        "manifest_episode_count": 30,
        "manifest_frame_count": 74,
        "candidate_payload_file_count": 0,
        "builder_payload_read_count": 0,
        "audit_payload_read_count": 0,
        "fit_count": 0,
        "weight_fit_count": 0,
    }
    assert governance["truth_identifier_use_count"] == 0
    assert governance["future_outcome_use_count"] == 0

    actor = result["actor_recalculation"]
    assert actor["train"]["positive_recall"] == pytest.approx(58 / 60)
    assert actor["train"]["negative_recall"] == pytest.approx(276 / 290)
    assert actor["validation"]["positive_recall"] == pytest.approx(13 / 15)
    assert actor["validation"]["negative_recall"] == pytest.approx(58 / 60)
    assert actor["train_only_class_balance"]["positive_sample_weight"] == (
        pytest.approx(290 / 60)
    )
    assert actor["train_only_class_balance"]["nonzero_edge_weight"] == 32.0

    confidence = result["confidence_recalculation"]
    assert confidence["train"]["target_positive_count"] == 58
    assert confidence["train"]["target_negative_count"] == 292
    assert confidence["train"]["positive_recall"] == pytest.approx(12 / 58)
    assert confidence["train"]["negative_specificity"] == 1.0
    assert confidence["train"]["brier_score"] == pytest.approx(
        0.1868472746691231
    )
    assert confidence["validation"]["target_positive_count"] == 13
    assert confidence["validation"]["target_negative_count"] == 62
    assert confidence["validation"]["positive_recall"] == pytest.approx(
        4 / 13
    )
    assert confidence["validation"]["negative_specificity"] == 1.0
    assert confidence["validation"]["brier_score"] == pytest.approx(
        0.1864687790965994
    )
    assert confidence["train"]["thin_margin"][
        "minimum_passing_margin"
    ] == pytest.approx(0.0005049347877502663)
    assert confidence["train"]["thin_margin"][
        "maximum_negative_margin"
    ] == pytest.approx(-2.9838085174538342e-05)

    checkpoints = result["checkpoint_recalculation"]
    assert checkpoints["actor"]["selected_epoch"] == 107
    assert checkpoints["confidence"]["selected_epoch"] == 66
    assert checkpoints["confidence"]["accepted_checkpoint_epoch_count"] == 8
    assert checkpoints["confidence"][
        "longest_consecutive_accepted_checkpoint_epochs"
    ] == 7

    fixture = result["development_fixture"]
    assert fixture["classification"] == "training_domain_smoke_only"
    assert fixture["generalization_evidence"] is False
    assert fixture["formal_validation_evidence"] is False
    assert fixture["confidence_margin_above_threshold"] == pytest.approx(
        0.0023671627044677956
    )

    registry = result["v3_registry"]
    assert registry["v3_registry_tree_unchanged"] is True
    assert registry["unregistered"] is True
    boundary = result["permission_and_admission_boundary"]
    assert boundary["all_logical_permissions_false"] is True
    assert boundary["admission_closed"] is True
    assert boundary["formal_holdout_evaluated"] is False
    assert boundary["runtime_preflight_completed"] is False
    guards = result["fail_closed_guards"]
    assert guards["candidate_artifact_sha256_required"] is True
    assert guards["manifest_content_external_anchor_required"] is True
    assert guards["candidate_self_rehash_cannot_replace_external_anchor"] is True
    assert guards["negative_control_contracts"] == {
        "candidate_artifact_byte_tamper": (
            "candidate_artifact_sha256_mismatch"
        ),
        "self_rehashed_permission_claim_tamper": (
            "candidate_manifest_content_anchor_mismatch"
        ),
    }

    outputs = write_d4_v4_candidate_audit_report(
        tmp_path / "audit-output",
        result,
    )
    written = json.loads(outputs["json"].read_text(encoding="utf-8"))
    assert written["content_sha256"] == result["content_sha256"]
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "training_domain_smoke_only" in report
    assert "未运行正式 holdout" in report
    assert "逻辑权限全部为 false，核验通过" in report
    assert "confidence_positive_recall_low" in report
    assert "runtime_outcome_and_benefit_unavailable" in report
    assert "logical permissions 全 false：`True`" not in report
    assert "失败关闭负例" in report
    assert "candidate_manifest_content_anchor_mismatch" in report
    checksum_lines = outputs["sha256sums"].read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(checksum_lines) == 2


def test_d4_v4_candidate_artifact_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    tampered = tmp_path / inputs.candidate_root.name
    shutil.copytree(inputs.candidate_root, tampered)
    with (tampered / "training_config.json").open(
        "a",
        encoding="utf-8",
    ) as stream:
        stream.write(" ")

    with pytest.raises(
        D4V4CandidateAuditError,
        match="candidate_artifact_sha256_mismatch",
    ):
        audit_d4_v4_candidate(replace(inputs, candidate_root=tampered))


def test_d4_v4_candidate_self_rehashed_claim_tamper_fails_external_anchor(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    tampered = tmp_path / inputs.candidate_root.name
    shutil.copytree(inputs.candidate_root, tampered)
    path = tampered / "v4_shadow_candidate_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["permissions"]["assist_enabled"] = True
    content = dict(payload)
    content.pop("content_sha256")
    payload["content_sha256"] = _canonical_sha256(content)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        D4V4CandidateAuditError,
        match="candidate_manifest_content_anchor_mismatch",
    ):
        audit_d4_v4_candidate(replace(inputs, candidate_root=tampered))
