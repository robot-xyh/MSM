from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

import d4_distributed_fallback.region_resource_v5_confidence_candidate as v5
from d4_distributed_fallback.region_resource_v5_confidence_candidate import (
    REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256,
    REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256,
    REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256,
    REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256,
    REGION_RESOURCE_V5_CANDIDATE_FILENAME,
    REGION_RESOURCE_V5_CANDIDATE_ID,
    REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE,
    REGION_RESOURCE_V5_GATE_FILENAME,
    REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN,
    REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL,
    REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256,
    REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_V5_REGISTERED_STATE_SHA256,
    REGION_RESOURCE_V5_STATE_FILENAME,
    REGION_RESOURCE_V5_SUMMARY_FILENAME,
    RegionResourceV5CandidateError,
    RegionResourceV5CandidateLoader,
    RegionResourceV5DevelopmentGate,
    build_region_resource_v5_confidence_candidate,
    evaluate_v5_development_gate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
V4_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/outputs"
    / "d4_v4_candidate_observable_calibrated_20260729"
    / "region_resource_a2_executable_transfer_shadow_v4"
)
V3_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
    / "region_resource_a2_8region_runtime_action_readiness_shadow_v3"
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


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    inventory = {
        str(path.relative_to(root)): _file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return _canonical_sha256(inventory)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: dict[str, object]) -> None:
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


@pytest.fixture(scope="module")
def built_v5_candidate(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, object]:
    if not V4_ROOT.is_dir():
        pytest.skip("frozen local v4 development candidate is unavailable")
    output_root = (
        tmp_path_factory.mktemp("d4-v5-candidate")
        / REGION_RESOURCE_V5_CANDIDATE_ID
    )
    v4_before = _tree_sha256(V4_ROOT)
    v3_before = _tree_sha256(V3_ROOT)
    manifest = build_region_resource_v5_confidence_candidate(
        V4_ROOT,
        output_root,
    )
    return {
        "root": output_root,
        "manifest": manifest,
        "v4_before": v4_before,
        "v4_after": _tree_sha256(V4_ROOT),
        "v3_before": v3_before,
        "v3_after": _tree_sha256(V3_ROOT),
    }


def test_v5_fixed_gate_cannot_be_lowered() -> None:
    gate = RegionResourceV5DevelopmentGate()
    assert gate.fixed_minimum_confidence == 0.60
    assert gate.minimum_train_positive_recall == 0.80
    assert gate.minimum_validation_positive_recall == 0.80
    assert gate.required_train_negative_specificity == 1.0
    assert gate.required_validation_negative_specificity == 1.0
    assert gate.minimum_train_positive_margin == 0.02
    assert gate.minimum_validation_positive_margin == 0.02
    with pytest.raises(ValueError, match="fixed development gate changed"):
        replace(gate, fixed_minimum_confidence=0.59)
    with pytest.raises(ValueError, match="fixed development gate changed"):
        replace(gate, minimum_validation_positive_margin=0.0)


def test_v5_development_gate_fails_closed_with_explicit_reasons() -> None:
    train = {
        "positive_recall": 0.79,
        "negative_specificity": 1.0,
        "minimum_positive_passing_margin": 0.019,
    }
    validation = {
        "positive_recall": 0.80,
        "negative_specificity": 0.99,
        "minimum_positive_passing_margin": 0.02,
    }
    usage = {
        "fit_split": "train",
        "audit_split": "validation",
        "train_fit_count": 10,
        "validation_fit_count": 0,
        "validation_weight_fit_count": 0,
        "validation_threshold_fit_count": 0,
        "validation_hyperparameter_fit_count": 0,
        "validation_selection_count": 0,
        "test_payload_read_count": 1,
        "test_payload_fit_count": 0,
        "test_payload_weight_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "formal_holdout_payload_fit_count": 0,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
        "reward_use_count": 0,
    }
    accepted, reasons = evaluate_v5_development_gate(
        train,
        validation,
        usage,
    )
    assert not accepted
    assert "train_positive_recall_below_0_80" in reasons
    assert "train_positive_margin_below_0_02" in reasons
    assert "validation_negative_specificity_not_1_0" in reasons
    assert "v5_data_usage_test_payload_read_count_invalid" in reasons


def test_v5_candidate_meets_development_recall_margin_and_usage_gate(
    built_v5_candidate: dict[str, object],
) -> None:
    root = Path(built_v5_candidate["root"])
    summary = _read_json(root / REGION_RESOURCE_V5_SUMMARY_FILENAME)
    train = summary["train_metrics"]
    validation = summary["validation_metrics"]
    usage = summary["data_usage"]
    assert isinstance(train, dict)
    assert isinstance(validation, dict)
    assert isinstance(usage, dict)

    for metrics in (train, validation):
        assert (
            float(metrics["positive_recall"])
            >= REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL
        )
        assert float(metrics["negative_specificity"]) == 1.0
        assert (
            float(metrics["minimum_positive_passing_margin"])
            >= REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN
        )
        assert (
            float(metrics["fixed_minimum_confidence"])
            == REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
        )
    assert int(usage["train_fit_count"]) == 350
    assert int(usage["validation_audit_count"]) == 75
    assert int(usage["validation_overlap_diagnostic_count"]) == 75
    assert int(usage["validation_overlap_diagnostic_fit_count"]) == 0
    assert int(usage["validation_fit_count"]) == 0
    assert int(usage["validation_selection_count"]) == 0
    assert int(usage["test_payload_read_count"]) == 0
    assert int(usage["test_payload_fit_count"]) == 0
    assert int(usage["formal_holdout_payload_read_count"]) == 0
    assert int(usage["formal_holdout_payload_fit_count"]) == 0
    assert int(usage["truth_identifier_use_count"]) == 0
    assert int(usage["future_outcome_use_count"]) == 0


def test_v5_records_train_validation_overlap_without_generalization_claim(
    built_v5_candidate: dict[str, object],
) -> None:
    root = Path(built_v5_candidate["root"])
    summary = _read_json(root / REGION_RESOURCE_V5_SUMMARY_FILENAME)
    diagnostic = summary["train_validation_overlap_diagnostic"]
    assert isinstance(diagnostic, dict)
    buckets = diagnostic["nearest_distance_bucket_counts"]
    assert isinstance(buckets, dict)

    assert int(diagnostic["validation_record_count"]) == 75
    assert int(diagnostic["exact_raw_graph_key_overlap_count"]) == 42
    assert int(diagnostic["exact_latent_overlap_count"]) == 42
    assert int(diagnostic["exact_graph_and_latent_overlap_count"]) == 42
    assert int(buckets["exact_le_1e_12"]) == 42
    assert int(buckets["nonexact_lt_1e_3"]) == 20
    assert int(buckets["ge_1e_3_lt_1e_1"]) == 10
    assert int(buckets["ge_1e_1"]) == 3
    assert int(diagnostic["nearest_train_label_match_count"]) == 75
    assert int(diagnostic["nearest_train_label_mismatch_count"]) == 0
    assert int(diagnostic["positive_exact_latent_overlap_count"]) == 12
    assert int(diagnostic["validation_positive_count"]) == 13
    assert diagnostic["source_independence_available"] is False
    assert diagnostic["generalization_evidence_available"] is False
    assert diagnostic["classification"] == "memorization_development_control"
    assert int(diagnostic["validation_fit_count"]) == 0
    assert int(diagnostic["test_payload_read_count"]) == 0
    assert int(diagnostic["formal_holdout_payload_read_count"]) == 0

    assert summary["development_gate_passed"] is True
    assert summary["independence_gate_passed"] is False
    assert summary["independence_evidence_available"] is False
    assert summary["generalization_evidence_available"] is False
    assert summary["candidate_classification"] == (
        "memorization_development_control"
    )


def test_v5_is_unregistered_shadow_only_and_grants_no_permissions(
    built_v5_candidate: dict[str, object],
) -> None:
    root = Path(built_v5_candidate["root"])
    manifest = _read_json(root / REGION_RESOURCE_V5_CANDIDATE_FILENAME)
    assert manifest["development_only"] is True
    assert manifest["shadow_only"] is True
    assert manifest["admission_closed"] is True
    assert manifest["rule_fallback_required"] is True
    assert manifest["registered"] is False
    assert manifest["independence_evidence_available"] is False
    assert manifest["generalization_evidence_available"] is False
    assert manifest["candidate_classification"] == (
        "memorization_development_control"
    )
    assert manifest["formal_holdout_evaluated"] is False
    assert manifest["runtime_preflight_completed"] is False
    permissions = manifest["permissions"]
    assert isinstance(permissions, dict)
    assert not any(
        value
        for name, value in permissions.items()
        if name != "schema"
    )
    assert REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256 is None
    assert REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256 is None
    assert REGION_RESOURCE_V5_REGISTERED_STATE_SHA256 is None
    with pytest.raises(
        RegionResourceV5CandidateError,
        match="v5_candidate_unregistered",
    ):
        RegionResourceV5CandidateLoader(root)
    loader = RegionResourceV5CandidateLoader(
        root,
        require_registered_binding=False,
        evaluation_context="offline_development",
    )
    assert loader.registered_binding_verified is False


def test_v5_binds_frozen_v4_and_preserves_v4_and_v3(
    built_v5_candidate: dict[str, object],
) -> None:
    root = Path(built_v5_candidate["root"])
    manifest = _read_json(root / REGION_RESOURCE_V5_CANDIDATE_FILENAME)
    assert (
        manifest["base_v4_manifest_content_sha256"]
        == REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256
    )
    assert (
        manifest["base_v4_manifest_file_sha256"]
        == REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256
    )
    assert (
        manifest["base_v4_model_state_sha256"]
        == REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
    )
    assert (
        manifest["base_v4_dataset_sha256"]
        == REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256
    )
    assert (
        manifest["base_v4_split_sha256"]
        == REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256
    )
    assert built_v5_candidate["v4_before"] == built_v5_candidate["v4_after"]
    assert built_v5_candidate["v3_before"] == built_v5_candidate["v3_after"]


def test_v5_artifact_byte_tamper_is_rejected(
    built_v5_candidate: dict[str, object],
    tmp_path: Path,
) -> None:
    source = Path(built_v5_candidate["root"])
    copied = tmp_path / REGION_RESOURCE_V5_CANDIDATE_ID
    shutil.copytree(source, copied)
    state_path = copied / REGION_RESOURCE_V5_STATE_FILENAME
    state_path.write_bytes(state_path.read_bytes() + b" ")
    with pytest.raises(
        RegionResourceV5CandidateError,
        match="v5_candidate_artifact_sha256_mismatch",
    ):
        RegionResourceV5CandidateLoader(
            copied,
            require_registered_binding=False,
            evaluation_context="offline_development",
        )


def test_v5_fixed_gate_cannot_be_self_resigned(
    built_v5_candidate: dict[str, object],
    tmp_path: Path,
) -> None:
    source = Path(built_v5_candidate["root"])
    copied = tmp_path / REGION_RESOURCE_V5_CANDIDATE_ID
    shutil.copytree(source, copied)
    gate_path = copied / REGION_RESOURCE_V5_GATE_FILENAME
    gate = _read_json(gate_path)
    gate["fixed_minimum_confidence"] = 0.59
    gate_without_digest = dict(gate)
    gate_without_digest.pop("content_sha256")
    gate["content_sha256"] = _canonical_sha256(gate_without_digest)
    _write_json(gate_path, gate)

    manifest_path = copied / REGION_RESOURCE_V5_CANDIDATE_FILENAME
    manifest = _read_json(manifest_path)
    artifact_files = manifest["artifact_files"]
    assert isinstance(artifact_files, dict)
    artifact_files[REGION_RESOURCE_V5_GATE_FILENAME] = _file_sha256(
        gate_path
    )
    manifest["development_gate_content_sha256"] = gate["content_sha256"]
    manifest_without_digest = dict(manifest)
    manifest_without_digest.pop("content_sha256")
    manifest["content_sha256"] = _canonical_sha256(
        manifest_without_digest
    )
    _write_json(manifest_path, manifest)

    with pytest.raises(
        ValueError,
        match="fixed development gate changed",
    ):
        RegionResourceV5CandidateLoader(
            copied,
            require_registered_binding=False,
            evaluation_context="offline_development",
        )


def test_v5_generalization_claim_cannot_be_self_resigned(
    built_v5_candidate: dict[str, object],
    tmp_path: Path,
) -> None:
    source = Path(built_v5_candidate["root"])
    copied = tmp_path / REGION_RESOURCE_V5_CANDIDATE_ID
    shutil.copytree(source, copied)
    summary_path = copied / REGION_RESOURCE_V5_SUMMARY_FILENAME
    summary = _read_json(summary_path)
    summary["generalization_evidence_available"] = True
    summary_without_digest = dict(summary)
    summary_without_digest.pop("content_sha256")
    summary["content_sha256"] = _canonical_sha256(
        summary_without_digest
    )
    _write_json(summary_path, summary)

    manifest_path = copied / REGION_RESOURCE_V5_CANDIDATE_FILENAME
    manifest = _read_json(manifest_path)
    artifact_files = manifest["artifact_files"]
    assert isinstance(artifact_files, dict)
    artifact_files[REGION_RESOURCE_V5_SUMMARY_FILENAME] = _file_sha256(
        summary_path
    )
    manifest["calibration_summary_content_sha256"] = summary[
        "content_sha256"
    ]
    manifest_without_digest = dict(manifest)
    manifest_without_digest.pop("content_sha256")
    manifest["content_sha256"] = _canonical_sha256(
        manifest_without_digest
    )
    _write_json(manifest_path, manifest)

    with pytest.raises(
        RegionResourceV5CandidateError,
        match=(
            "v5_calibration_summary_"
            "generalization_evidence_available_mismatch"
        ),
    ):
        RegionResourceV5CandidateLoader(
            copied,
            require_registered_binding=False,
            evaluation_context="offline_development",
        )


def test_v5_failed_development_gate_writes_no_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if not V4_ROOT.is_dir():
        pytest.skip("frozen local v4 development candidate is unavailable")

    def _failing_metrics(
        _actor_model: object,
        records: object,
        _state: object,
    ) -> dict[str, object]:
        sample_count = len(records)
        return {
            "sample_count": sample_count,
            "target_positive_count": 1,
            "target_negative_count": max(sample_count - 1, 1),
            "positive_threshold_pass_count": 0,
            "negative_threshold_pass_count": 0,
            "positive_recall": 0.0,
            "negative_specificity": 1.0,
            "minimum_positive_passing_margin": -1.0,
            "confidence_minimum": 0.0,
            "confidence_mean": 0.0,
            "confidence_maximum": 0.0,
            "fixed_minimum_confidence": 0.60,
            "brier_score": 1.0,
        }

    monkeypatch.setattr(v5, "_calibration_metrics", _failing_metrics)
    destination = tmp_path / REGION_RESOURCE_V5_CANDIDATE_ID
    with pytest.raises(
        RegionResourceV5CandidateError,
        match="v5_development_gate_failed",
    ):
        build_region_resource_v5_confidence_candidate(
            V4_ROOT,
            destination,
        )
    assert not destination.exists()
    failure_path = destination.with_name(
        f"{REGION_RESOURCE_V5_CANDIDATE_ID}.build_failure.json"
    )
    failure = _read_json(failure_path)
    assert failure["candidate_created"] is False
    assert failure["admission_closed"] is True
    assert failure["rule_fallback_required"] is True
    assert failure["independence_evidence_available"] is False
    assert failure["generalization_evidence_available"] is False
    assert "train_positive_recall_below_0_80" in failure["failure_reasons"]
    assert "validation_positive_recall_below_0_80" in failure[
        "failure_reasons"
    ]
