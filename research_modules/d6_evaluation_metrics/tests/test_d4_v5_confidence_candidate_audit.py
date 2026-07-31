from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from d6_evaluation_metrics.d4_v5_confidence_candidate_audit import (
    D4V5CandidateAuditError,
    _audit_memory_bias,
    audit_d4_v5_confidence_candidate,
    load_d4_v5_candidate_audit_inputs,
    write_d4_v5_candidate_audit_report,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INPUT_SPEC = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/configs/"
    "d4_v5_confidence_candidate_independent_audit_20260729.json"
)


def _inputs():
    return load_d4_v5_candidate_audit_inputs(
        INPUT_SPEC,
        repository_root=REPOSITORY_ROOT,
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


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_historical_v5_candidate_fails_closed_after_v4_source_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()
    dataset_manifest = json.loads(
        (
            inputs.base_v4_root / "development_dataset/manifest.json"
        ).read_text(encoding="utf-8")
    )
    forbidden_test_paths = {
        (
            inputs.base_v4_root
            / "development_dataset"
            / episode["relative_path"]
        ).resolve()
        for episode in dataset_manifest["episodes"]
        if episode["split"] == "test"
    }
    original_read_text = Path.read_text

    def guarded_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.resolve() in forbidden_test_paths:
            raise AssertionError(f"TEST payload semantic read: {path}")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    with pytest.raises(D4V5CandidateAuditError) as raised:
        audit_d4_v5_confidence_candidate(inputs)

    source_relative = (
        "research_modules/d4_distributed_fallback/"
        "d4_distributed_fallback/region_resource.py"
    )
    current_source_sha256 = sha256(
        (REPOSITORY_ROOT / source_relative).read_bytes()
    ).hexdigest()
    assert raised.value.code == "v4_source_external_anchor_mismatch"
    assert raised.value.detail == f"{source_relative}:{current_source_sha256}"
    assert current_source_sha256 != (
        inputs.expected_v4_source_files[source_relative]
    )


def test_v5_candidate_ordinary_artifact_tamper_fails_external_anchor(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    tampered = tmp_path / inputs.candidate_root.name
    shutil.copytree(inputs.candidate_root, tampered)
    with (tampered / "calibration_state.json").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(" ")

    with pytest.raises(
        D4V5CandidateAuditError,
        match="candidate_artifact_external_anchor_mismatch",
    ):
        audit_d4_v5_confidence_candidate(
            replace(inputs, candidate_root=tampered)
        )


def test_synchronously_self_resigned_candidate_still_fails_caller_anchor(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    tampered = tmp_path / inputs.candidate_root.name
    shutil.copytree(inputs.candidate_root, tampered)

    summary_path = tampered / "calibration_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["permissions"]["assist_enabled"] = True
    summary_content = dict(summary)
    summary_content.pop("content_sha256")
    summary["content_sha256"] = _canonical_sha256(summary_content)
    _write_json(summary_path, summary)

    manifest_path = tampered / "v5_confidence_candidate_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["permissions"]["assist_enabled"] = True
    manifest["calibration_summary_content_sha256"] = summary[
        "content_sha256"
    ]
    manifest["artifact_files"]["calibration_summary.json"] = sha256(
        summary_path.read_bytes()
    ).hexdigest()
    manifest_content = dict(manifest)
    manifest_content.pop("content_sha256")
    manifest["content_sha256"] = _canonical_sha256(manifest_content)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D4V5CandidateAuditError,
        match="candidate_manifest_file_external_anchor_mismatch",
    ):
        audit_d4_v5_confidence_candidate(
            replace(inputs, candidate_root=tampered)
        )


def test_controlled_overlap_diagnostic_disagreement_fails_closed() -> None:
    expected = {
        "validation_record_count": 1,
        "exact_raw_graph_key_overlap_count": 0,
        "exact_latent_overlap_count": 1,
        "nonexact_lt_1e_3_count": 0,
        "ge_1e_3_lt_1e_1_count": 0,
        "ge_1e_1_count": 1,
        "nearest_train_label_match_count": 1,
        "positive_exact_raw_graph_key_overlap_count": 0,
        "positive_exact_latent_overlap_count": 0,
    }
    inputs = SimpleNamespace(
        expected_validation_diagnostics=expected,
        minimum_subgroup_denominator=1,
    )
    train_rows = tuple((float(index), 0.0) for index in range(12))
    latent = {
        "train_normalized": train_rows,
        "train_labels": tuple(index % 2 == 0 for index in range(12)),
        "train_raw_keys": tuple(f"raw-{index}" for index in range(12)),
        "train_latent_keys": tuple(
            f"latent-{index}" for index in range(12)
        ),
        "validation_raw_keys": ("validation-raw",),
        "validation_normalized": ((100.0, 0.0),),
        "validation_labels": (False,),
    }

    with pytest.raises(D4V5CandidateAuditError) as raised:
        _audit_memory_bias(inputs, latent=latent)

    assert raised.value.code == (
        "validation_overlap_expected_crosscheck_mismatch"
    )
    assert raised.value.detail == "exact_latent_overlap_count:0!=1"


def test_output_writer_refuses_existing_directory(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        write_d4_v5_candidate_audit_report(output, {"result": "unused"})
