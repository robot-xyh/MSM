from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource_v6_external_evaluation import (
    _EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256,
    _EXPECTED_MODEL_STATE_CONTENT_SHA256,
    _EXPECTED_STATE_FILE_SHA256,
    _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256,
    RegionResourceV6ExternalEvaluationConfig,
    RegionResourceV6ExternalEvaluationError,
    _assert_tree_unchanged,
    _classify_transfer_errors,
    _closed_candidate_status,
    _data_usage,
    _summarize_records,
    _tree_sha256,
    _verify_candidate_manifest_identity,
    _verify_content_sha256,
    _with_content_sha256,
)
from d4_distributed_fallback.region_resource_v6_transfer_candidate import (
    REGION_RESOURCE_V6_CANDIDATE_ID,
    REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE,
    REGION_RESOURCE_V6_MODEL_VERSION,
)


def _candidate_manifest() -> dict[str, object]:
    return {
        "content_sha256": _EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256,
        "candidate_id": REGION_RESOURCE_V6_CANDIDATE_ID,
        "model_version": REGION_RESOURCE_V6_MODEL_VERSION,
        "training_audit_content_sha256": (
            _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256
        ),
        "model_state_content_sha256": (
            _EXPECTED_MODEL_STATE_CONTENT_SHA256
        ),
        "bundle_state_file_sha256": _EXPECTED_STATE_FILE_SHA256,
        "fixed_minimum_confidence": (
            REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE
        ),
        "candidate_status": "unregistered_edge_transfer_development",
        "confidence_calibration_status": (
            "not_started_actor_must_freeze_first"
        ),
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "formal_holdout_evaluated": False,
        "runtime_preflight_completed": False,
        "permissions": {
            "schema": "d4-region-resource-edge-transfer-permissions-v6",
            "assist_enabled": False,
            "assignment_enabled": False,
            "control_enabled": False,
        },
    }


def _record(
    *,
    split: str = "test",
    rule_positive: bool,
    actor_derived_positive: bool,
    exact_positive: bool = False,
    negative_exact_r0: bool = False,
) -> dict[str, object]:
    return {
        "evaluation_available": True,
        "unavailable_reason": None,
        "split": split,
        "rule_positive": rule_positive,
        "rule_negative": not rule_positive,
        "actor_raw_transfer_count": 1 if actor_derived_positive else 0,
        "actor_raw_transfer_resource_count": (
            1 if actor_derived_positive else 0
        ),
        "actor_projected_transfer_count": (
            1 if actor_derived_positive else 0
        ),
        "actor_projected_transfer_resource_count": (
            1 if actor_derived_positive else 0
        ),
        "correct_directed_edge_count": 1 if exact_positive else 0,
        "correct_directed_edge_frame": exact_positive,
        "projected_exact_positive_action": exact_positive,
        "negative_exact_r0": negative_exact_r0,
        "wrong_direction_count": 0,
        "wrong_quantity_count": 0,
        "wrong_edge_count": 0,
        "false_transfer_count": 0,
        "projection_rejection_count": 0,
        "projection_rejected": False,
        "projection_rejection_reasons": [],
        "invariant_failure": False,
        "invariant_failure_reasons": [],
        "actor_derived_positive": actor_derived_positive,
        "failure_reasons": [],
    }


def test_v6_external_candidate_identity_tamper_is_rejected() -> None:
    manifest = _candidate_manifest()
    _verify_candidate_manifest_identity(manifest)
    manifest["model_state_content_sha256"] = "0" * 64
    with pytest.raises(
        RegionResourceV6ExternalEvaluationError,
        match="candidate_manifest_identity_mismatch",
    ):
        _verify_candidate_manifest_identity(manifest)


def test_v6_external_content_hash_tamper_is_rejected() -> None:
    payload = _with_content_sha256({"dataset": "frozen"})
    _verify_content_sha256(payload, "fixture")
    payload["dataset"] = "mutated"
    with pytest.raises(
        RegionResourceV6ExternalEvaluationError,
        match="content_sha256_mismatch",
    ):
        _verify_content_sha256(payload, "fixture")


def test_v6_external_candidate_and_input_are_immutable(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    external_input = tmp_path / "external-input"
    candidate.mkdir()
    external_input.mkdir()
    (candidate / "state.bin").write_bytes(b"candidate")
    (external_input / "manifest.json").write_text(
        '{"input":"frozen"}\n',
        encoding="utf-8",
    )
    candidate_before = _tree_sha256(candidate)
    input_before = _tree_sha256(external_input)
    _assert_tree_unchanged(
        "candidate", candidate_before, _tree_sha256(candidate)
    )
    _assert_tree_unchanged(
        "external_input", input_before, _tree_sha256(external_input)
    )
    (external_input / "manifest.json").write_text(
        '{"input":"changed"}\n',
        encoding="utf-8",
    )
    with pytest.raises(
        RegionResourceV6ExternalEvaluationError,
        match="external_input_mutation_detected",
    ):
        _assert_tree_unchanged(
            "external_input", input_before, _tree_sha256(external_input)
        )


def test_v6_external_test_payload_is_evaluation_only() -> None:
    usage = _data_usage(
        {
            "train": {"sample_count": 89},
            "validation": {"sample_count": 20},
            "test": {"sample_count": 17},
        }
    )
    assert usage["test_payload_use"] == "read_only_external_evaluation"
    assert usage["v6_actor_training_use_count_by_external_split"]["test"] == 0
    assert usage["v6_checkpoint_selection_use_count_by_external_split"][
        "test"
    ] == 0
    assert usage["v6_threshold_tuning_use_count_by_external_split"][
        "test"
    ] == 0
    assert usage["model_fit_count"] == 0


def test_v6_external_uncalibrated_confidence_cannot_admit() -> None:
    config = RegionResourceV6ExternalEvaluationConfig()
    status = _closed_candidate_status()
    assert config.fixed_minimum_confidence == 0.60
    assert config.confidence_gate_available is False
    assert config.admission_allowed is False
    assert status["confidence_gate_available"] is False
    assert status["uncalibrated_confidence_head_used_for_gate"] is False
    assert status["admission_closed"] is True
    assert not any(status["permissions"].values())
    with pytest.raises(
        ValueError,
        match="must remain read-only",
    ):
        replace(config, confidence_gate_available=True)


def test_wrong_direction_and_wrong_quantity_are_separate() -> None:
    target = {("region-a", "region-b", "edge-1"): 1}
    wrong_direction = _classify_transfer_errors(
        target,
        {("region-b", "region-a", "edge-1"): 1},
    )
    wrong_quantity = _classify_transfer_errors(
        target,
        {("region-a", "region-b", "edge-1"): 2},
    )
    assert wrong_direction["wrong_direction_count"] == 1
    assert wrong_direction["wrong_quantity_count"] == 0
    assert wrong_quantity["correct_directed_edge_count"] == 1
    assert wrong_quantity["wrong_direction_count"] == 0
    assert wrong_quantity["wrong_quantity_count"] == 1


def test_actor_positive_zero_denominator_is_unavailable() -> None:
    metrics = _summarize_records(
        (
            _record(
                rule_positive=True,
                actor_derived_positive=False,
            ),
            _record(
                rule_positive=False,
                actor_derived_positive=False,
                negative_exact_r0=True,
            ),
        )
    )
    assert metrics["actor_derived_positive_denominator_count"] == 0
    assert (
        metrics["actor_derived_positive_denominator_available"] is False
    )
    assert metrics["actor_derived_exact_positive_rate"] is None
    assert metrics["actor_derived_exact_positive_rate_status"] == (
        "unavailable_zero_actor_derived_positive_denominator"
    )


def test_external_contract_cannot_fit_update_or_read_forbidden_data() -> None:
    config = RegionResourceV6ExternalEvaluationConfig()
    assert config.model_fit_allowed is False
    assert config.checkpoint_update_allowed is False
    assert config.threshold_tuning_allowed is False
    assert config.formal_holdout_read_allowed is False
    assert config.old_external_evaluation_read_allowed is False
    with pytest.raises(ValueError, match="must remain read-only"):
        replace(config, model_fit_allowed=True)
