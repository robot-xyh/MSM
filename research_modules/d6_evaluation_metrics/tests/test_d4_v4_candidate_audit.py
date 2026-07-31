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


def test_historical_d4_v4_candidate_fails_closed_after_source_drift(
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
    with pytest.raises(D4V4CandidateAuditError) as raised:
        audit_d4_v4_candidate(inputs)

    assert raised.value.code == (
        "source_current_file_differs_from_audited_commit"
    )
    assert raised.value.detail == (
        "research_modules/d4_distributed_fallback/"
        "d4_distributed_fallback/region_resource.py"
    )


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
