from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.region_resource_v7_external_evaluation import (
    _EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256,
    _EXPECTED_MODEL_STATE_CONTENT_SHA256,
    _EXPECTED_SOURCE_BINDING_CONTENT_SHA256,
    _EXPECTED_STATE_FILE_SHA256,
    _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256,
    RegionResourceV7ExternalEvaluationConfig,
    RegionResourceV7ExternalEvaluationError,
    _action_tuple_differences,
    _assert_tree_unchanged,
    _classify_transfer_errors,
    _closed_candidate_status,
    _conclusion,
    _data_usage,
    _summarize_records,
    _tree_sha256,
    _validate_seed_isolation,
    _verify_candidate_manifest_identity,
    _verify_content_sha256,
    _with_content_sha256,
)
from d4_distributed_fallback.region_resource_v7_rule_node_residual_candidate import (
    REGION_RESOURCE_V7_CANDIDATE_ID,
    REGION_RESOURCE_V7_MODEL_VERSION,
)


def _candidate_manifest() -> dict[str, object]:
    return {
        "content_sha256": _EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256,
        "candidate_id": REGION_RESOURCE_V7_CANDIDATE_ID,
        "model_version": REGION_RESOURCE_V7_MODEL_VERSION,
        "source_binding_content_sha256": (
            _EXPECTED_SOURCE_BINDING_CONTENT_SHA256
        ),
        "implementation_file_sha256": (
            "a27f0c1d8653a83b8a5a8036d8aa860ab9ded50e18e1dce7700f878bb6096338"
        ),
        "training_audit_content_sha256": (
            _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256
        ),
        "model_state_content_sha256": (
            _EXPECTED_MODEL_STATE_CONTENT_SHA256
        ),
        "bundle_state_file_sha256": _EXPECTED_STATE_FILE_SHA256,
        "candidate_status": (
            "unregistered_rule_node_transfer_residual_development"
        ),
        "confidence_calibration_status": (
            "not_available_actor_must_pass_independent_evaluation"
        ),
        "confidence_calibrator_available": False,
        "fixed_minimum_confidence_gate_applied": False,
        "source_independent_evaluation_status": "not_started",
        "source_independent_evaluation_completed": False,
        "development_gate_passed": True,
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "formal_holdout_evaluated": False,
        "runtime_preflight_completed": False,
        "permissions": {
            "schema": (
                "d4-region-resource-rule-node-transfer-residual-permissions-v7"
            ),
            "source_independent_evaluation_authorized": False,
            "assist_enabled": False,
            "authority_enabled": False,
            "assignment_enabled": False,
            "degradation_enabled": False,
            "takeover_enabled": False,
            "coalition_commit_enabled": False,
            "control_enabled": False,
            "production_runtime_ack_enabled": False,
            "physical_permission_available": False,
            "d3_permission_available": False,
            "d7_permission_available": False,
            "actual_adoption_claimed": False,
            "benefit_claimed": False,
        },
    }


def _record(
    *,
    rule_positive: bool,
    actor_derived_positive: bool,
    exact_positive: bool = False,
    negative_exact_r0: bool = False,
) -> dict[str, object]:
    return {
        "evaluation_available": True,
        "unavailable_reason": None,
        "rule_positive": rule_positive,
        "rule_negative": not rule_positive,
        "actor_raw_residual_activation_count": (
            1 if actor_derived_positive else 0
        ),
        "actor_raw_transfer_change_count": (
            1 if actor_derived_positive else 0
        ),
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
        "actor_projected_transfer_change_count": (
            1 if actor_derived_positive else 0
        ),
        "raw_correct_directed_edge_count": 1 if exact_positive else 0,
        "raw_wrong_direction_count": 0,
        "raw_wrong_quantity_count": 0,
        "raw_wrong_edge_count": 0,
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
        "r0_action_tuple_preserved": True,
        "r0_action_tuple_difference_count": 0,
        "projected_r0_action_tuple_difference_count": 0,
        "actor_derived_positive": actor_derived_positive,
        "failure_reasons": [],
    }


@dataclass(frozen=True)
class _Action:
    region_id: str = "region-0"
    resource_quota_delta: int = 0
    reserve_ratio: float = 0.2
    reconnaissance_priority: float = 0.5
    hold: bool = False
    request_replan: bool = False
    expected_owner_id: str | None = "center"
    expected_owner_layer: str = "center"
    expected_plan_id: str = "plan-1"
    expected_plan_version: int = 1
    expected_epoch: int = 1
    expected_lease_expires_at_s: float = 10.0
    reasons: tuple[str, ...] = ("r0",)

    def to_dict(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


def test_candidate_identity_and_permission_tamper_are_rejected() -> None:
    manifest = _candidate_manifest()
    _verify_candidate_manifest_identity(manifest)
    manifest["model_state_content_sha256"] = "0" * 64
    with pytest.raises(
        RegionResourceV7ExternalEvaluationError,
        match="candidate_manifest_identity_mismatch",
    ):
        _verify_candidate_manifest_identity(manifest)
    manifest = _candidate_manifest()
    manifest["permissions"]["assist_enabled"] = True  # type: ignore[index]
    with pytest.raises(
        RegionResourceV7ExternalEvaluationError,
        match="candidate_manifest_identity_mismatch",
    ):
        _verify_candidate_manifest_identity(manifest)


def test_content_hash_tamper_is_rejected() -> None:
    payload = _with_content_sha256({"dataset": "frozen"})
    _verify_content_sha256(payload, "fixture")
    payload["dataset"] = "mutated"
    with pytest.raises(
        RegionResourceV7ExternalEvaluationError,
        match="content_sha256_mismatch",
    ):
        _verify_content_sha256(payload, "fixture")


def test_candidate_and_inputs_are_immutable(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    source = tmp_path / "source"
    candidate.mkdir()
    source.mkdir()
    (candidate / "state.bin").write_bytes(b"candidate")
    (source / "manifest.json").write_text(
        '{"input":"frozen"}\n',
        encoding="utf-8",
    )
    candidate_before = _tree_sha256(candidate)
    source_before = _tree_sha256(source)
    _assert_tree_unchanged(
        "candidate", candidate_before, _tree_sha256(candidate)
    )
    _assert_tree_unchanged(
        "raw_source", source_before, _tree_sha256(source)
    )
    (source / "manifest.json").write_text(
        '{"input":"changed"}\n',
        encoding="utf-8",
    )
    with pytest.raises(
        RegionResourceV7ExternalEvaluationError,
        match="raw_source_mutation_detected",
    ):
        _assert_tree_unchanged(
            "raw_source", source_before, _tree_sha256(source)
        )


def test_external_splits_are_evaluation_only() -> None:
    usage = _data_usage(
        {
            "train": {"sample_count": 90},
            "validation": {"sample_count": 20},
            "test": {"sample_count": 18},
        }
    )
    assert usage["test_payload_use"] == "read_only_external_evaluation"
    assert usage["v7_actor_training_use_count_by_external_split"]["test"] == 0
    assert (
        usage["v7_checkpoint_selection_use_count_by_external_split"]["test"]
        == 0
    )
    assert usage["v7_threshold_tuning_use_count_by_external_split"]["test"] == 0
    assert (
        usage["v7_confidence_calibration_use_count_by_external_split"]["test"]
        == 0
    )
    assert usage["model_fit_count"] == 0


def test_no_fit_tune_calibrate_register_or_admit_contract() -> None:
    config = RegionResourceV7ExternalEvaluationConfig()
    status = _closed_candidate_status()
    assert config.evaluation_splits == ("train", "validation", "test")
    assert config.model_fit_allowed is False
    assert config.checkpoint_update_allowed is False
    assert config.threshold_tuning_allowed is False
    assert config.confidence_calibration_allowed is False
    assert config.formal_holdout_read_allowed is False
    assert config.prior_external_evaluation_read_allowed is False
    assert status["confidence_calibrator_available"] is False
    assert status["fixed_minimum_confidence_gate_applied"] is False
    assert status["admission_closed"] is True
    assert not any(status["permissions"].values())
    with pytest.raises(ValueError, match="must remain read-only"):
        replace(config, model_fit_allowed=True)


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


def test_zero_external_positive_activation_fails_closed() -> None:
    positive = _summarize_records(
        (
            _record(
                rule_positive=True,
                actor_derived_positive=False,
            ),
        )
    )
    negative = _summarize_records(
        (
            _record(
                rule_positive=False,
                actor_derived_positive=False,
                negative_exact_r0=True,
            ),
        )
    )
    conclusion = _conclusion(
        {
            "train": positive,
            "validation": positive,
            "test": negative,
        },
        {"frozen_v4_exact_observable_overlap_free": True},
    )
    assert conclusion["evaluation_disposition"] == "failed_closed"
    assert (
        "validation_positive_targets_without_raw_transfer_change"
        in conclusion["behavioral_failure_reasons"]
    )
    assert conclusion["generalization_admission_supported"] is False


@pytest.mark.parametrize(
    ("field_name", "replacement_value"),
    (
        ("resource_quota_delta", 1),
        ("reserve_ratio", 0.3),
        ("reconnaissance_priority", 0.8),
        ("hold", True),
        ("request_replan", True),
        ("expected_owner_id", "secondary"),
        ("expected_owner_layer", "secondary"),
        ("expected_plan_id", "plan-2"),
        ("expected_plan_version", 2),
        ("expected_epoch", 2),
        ("expected_lease_expires_at_s", 12.0),
        ("reasons", ("changed",)),
    ),
)
def test_complete_r0_action_tuple_detects_every_field(
    field_name: str,
    replacement_value: object,
) -> None:
    baseline_action = _Action()
    candidate_action = replace(
        baseline_action,
        **{field_name: replacement_value},
    )
    baseline = SimpleNamespace(actions=(baseline_action,))
    candidate = SimpleNamespace(actions=(candidate_action,))
    differences = _action_tuple_differences(baseline, candidate)
    assert f"region:region-0:{field_name}" in differences


def test_seed_isolation_allows_only_independent_set() -> None:
    _validate_seed_isolation(tuple(range(5216, 5280)))
    with pytest.raises(
        RegionResourceV7ExternalEvaluationError,
        match="formal_holdout_seed_read_forbidden",
    ):
        _validate_seed_isolation((1000,))
    with pytest.raises(
        RegionResourceV7ExternalEvaluationError,
        match="prior_evaluation_seed_read_forbidden",
    ):
        _validate_seed_isolation((3008,))
