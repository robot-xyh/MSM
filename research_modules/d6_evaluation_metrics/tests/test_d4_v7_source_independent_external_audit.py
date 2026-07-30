from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.d4_v7_source_independent_external_audit import (
    D4V7ExternalAuditError,
    _EXPECTED_FORMAL_HOLDOUT_SEEDS,
    _EXPECTED_INDEPENDENT_SEEDS,
    _EXPECTED_PILOT_SEEDS,
    _EXPECTED_PRIOR_EVALUATION_SEEDS,
    _EXPECTED_TRAINING_SEEDS,
    _audit_no_confidence_gate,
    _compare_d4_summary_claims,
    _reject_truth_pollution,
    _validate_disjoint_seed_classes,
    _verify_expected_hashes,
    audit_d4_v7_source_independent_external,
    load_d4_v7_external_audit_inputs,
    write_d4_v7_external_audit_report,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INPUT_SPEC = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/configs/"
    "d4_v7_source_independent_external_audit_m16n24_20260730.json"
)
D4_EVALUATION_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/outputs/"
    "d4_v7_source_independent_external_evaluation_20260730"
)
CANDIDATE_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/outputs/"
    "d4_v7_rule_node_residual_failclosed_final_20260730/"
    "region_resource_a2_rule_node_transfer_residual_shadow_v7"
)

_INPUTS_AVAILABLE = all(
    path.exists()
    for path in (
        INPUT_SPEC,
        D4_EVALUATION_ROOT,
        CANDIDATE_ROOT,
        Path(
            "/tmp/msm_d4_v7_transfer_labeled_m16n24_64seed_test8_4a83a37"
        ),
        Path(
            "/tmp/msm_d4_v7_transfer_independent_m16n24_64seed_4a83a37"
        ),
    )
)


@pytest.fixture(scope="module")
def frozen_audit_result() -> dict[str, object]:
    if not _INPUTS_AVAILABLE:
        pytest.skip("frozen D4 v7 external audit inputs are unavailable")
    inputs = load_d4_v7_external_audit_inputs(
        INPUT_SPEC,
        repository_root=REPOSITORY_ROOT,
    )
    return audit_d4_v7_source_independent_external(inputs)


def test_frozen_v7_audit_recomputes_expected_metrics(
    frozen_audit_result: dict[str, object],
) -> None:
    aggregate = frozen_audit_result["independent_recomputation"]["aggregate"]
    assert aggregate["sample_count"] == 128
    assert aggregate["rule_positive_count"] == 42
    assert aggregate["rule_negative_count"] == 86
    assert aggregate["actor_raw_residual_activation_count"] == 10
    assert aggregate["actor_raw_transfer_change_count"] == 3
    assert aggregate["actor_raw_transfer_count"] == 3
    assert aggregate["actor_projected_transfer_count"] == 3
    assert aggregate["projected_exact_positive_action_count"] == 0
    assert aggregate["negative_exact_r0_count"] == 83
    assert aggregate["raw_wrong_edge_count"] == 3
    assert aggregate["wrong_edge_count"] == 3
    assert aggregate["false_transfer_count"] == 3
    assert aggregate["projection_rejection_count"] == 0
    assert aggregate["invariant_failure_count"] == 0
    assert aggregate["r0_action_tuple_preservation_failure_count"] == 0
    assert (
        aggregate["projected_r0_action_tuple_difference_frame_count"] == 3
    )
    assert frozen_audit_result["d4_artifact_reconciliation"][
        "frame_record_mismatch_count"
    ] == 0
    assert frozen_audit_result["input_immutability"][
        "input_mutation_count"
    ] == 0
    assert frozen_audit_result["admission_conclusion"][
        "confidence_calibration_allowed"
    ] is False


def test_summary_tampering_cannot_change_independent_recomputation(
    frozen_audit_result: dict[str, object],
) -> None:
    d4_summary = json.loads(
        (D4_EVALUATION_ROOT / "external_evaluation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    d4_summary["aggregate_metrics"]["rule_positive_count"] = 999
    recomputed = frozen_audit_result["independent_recomputation"]
    comparison = _compare_d4_summary_claims(
        recomputed["split_metrics"],
        recomputed["aggregate"],
        d4_summary,
        fail_on_mismatch=False,
    )
    assert comparison["passed"] is False
    assert "aggregate_metrics" in comparison["mismatched_fields"]
    assert recomputed["aggregate"]["rule_positive_count"] == 42
    with pytest.raises(
        D4V7ExternalAuditError,
        match="d4_summary_claim_mismatch",
    ):
        _compare_d4_summary_claims(
            recomputed["split_metrics"],
            recomputed["aggregate"],
            d4_summary,
            fail_on_mismatch=True,
        )


def test_frozen_hash_mutation_is_rejected() -> None:
    with pytest.raises(D4V7ExternalAuditError, match="frozen_hash_mismatch"):
        _verify_expected_hashes(
            {"candidate_state_file": "a" * 64},
            {"candidate_state_file": "b" * 64},
        )


def test_actor_derived_denominator_counts_only_executable_residuals(
    frozen_audit_result: dict[str, object],
) -> None:
    aggregate = frozen_audit_result["independent_recomputation"]["aggregate"]
    actor_metric = aggregate["actor_derived_exact_positive_rate_metric"]
    assert actor_metric == {
        "availability": "available",
        "value": 0.0,
        "numerator": 0,
        "denominator": 3,
    }
    assert aggregate["actor_derived_exact_positive_rate"] == 0.0
    test_metric = frozen_audit_result["independent_recomputation"][
        "split_metrics"
    ]["test"]["actor_derived_exact_positive_rate_metric"]
    assert test_metric["availability"] == "unavailable"
    assert test_metric["value"] is None
    assert test_metric["denominator"] == 0


def test_test_split_rule_positive_denominator_is_counted_independently(
    frozen_audit_result: dict[str, object],
) -> None:
    split_metrics = frozen_audit_result["independent_recomputation"][
        "split_metrics"
    ]
    assert split_metrics["train"]["rule_positive_count"] == 24
    assert split_metrics["validation"]["rule_positive_count"] == 9
    assert split_metrics["test"]["rule_positive_count"] == 9
    test_metric = split_metrics["test"][
        "rule_positive_exact_action_recall_metric"
    ]
    assert test_metric["availability"] == "available"
    assert test_metric["numerator"] == 0
    assert test_metric["denominator"] == 9
    assert test_metric["value"] == 0.0


def test_uncalibrated_v7_rejects_confidence_gate(
    frozen_audit_result: dict[str, object],
) -> None:
    candidate_manifest = json.loads(
        (
            CANDIDATE_ROOT
            / "v7_rule_node_transfer_residual_candidate_manifest.json"
        ).read_text(encoding="utf-8")
    )
    bundle_manifest = json.loads(
        (CANDIDATE_ROOT / "bundle/manifest.json").read_text(encoding="utf-8")
    )
    d4_integrity = json.loads(
        (D4_EVALUATION_ROOT / "input_integrity.json").read_text(
            encoding="utf-8"
        )
    )
    d4_summary = json.loads(
        (D4_EVALUATION_ROOT / "external_evaluation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    records = frozen_audit_result["recomputed_records"]
    accepted = _audit_no_confidence_gate(
        candidate_manifest=candidate_manifest,
        bundle_manifest=bundle_manifest,
        d4_integrity=d4_integrity,
        d4_summary=d4_summary,
        records=records,
    )
    assert accepted["fixed_confidence_gate_applied"] is False
    tampered_bundle = deepcopy(bundle_manifest)
    tampered_bundle["runtime_confidence_gate_available"] = True
    with pytest.raises(
        D4V7ExternalAuditError,
        match="uncalibrated_confidence_gate_forbidden",
    ):
        _audit_no_confidence_gate(
            candidate_manifest=candidate_manifest,
            bundle_manifest=tampered_bundle,
            d4_integrity=d4_integrity,
            d4_summary=d4_summary,
            records=records,
        )


def test_seed_overlap_and_truth_pollution_are_rejected() -> None:
    expected = {
        "training": set(_EXPECTED_TRAINING_SEEDS),
        "formal_holdout": set(_EXPECTED_FORMAL_HOLDOUT_SEEDS),
        "prior_evaluation": set(_EXPECTED_PRIOR_EVALUATION_SEEDS),
        "pilot": set(_EXPECTED_PILOT_SEEDS),
        "independent": set(_EXPECTED_INDEPENDENT_SEEDS),
    }
    polluted = {name: set(values) for name, values in expected.items()}
    polluted["independent"].add(1000)
    expected_polluted = {
        name: set(values) for name, values in polluted.items()
    }
    with pytest.raises(D4V7ExternalAuditError, match="seed_class_overlap"):
        _validate_disjoint_seed_classes(
            polluted,
            expected_classes=expected_polluted,
        )
    with pytest.raises(
        D4V7ExternalAuditError,
        match="online_truth_pollution_detected",
    ):
        _reject_truth_pollution(
            {"fixture": {"truth_identifier_use_count": 1}}
        )


def test_v7_audit_keeps_all_evaluation_and_runtime_permissions_closed(
    frozen_audit_result: dict[str, object],
) -> None:
    scope = frozen_audit_result["scope"]
    for field in (
        "model_fit_count",
        "checkpoint_update_count",
        "threshold_tuning_count",
        "confidence_calibration_count",
        "confidence_gate_application_count",
        "input_mutation_count",
        "candidate_mutation_count",
        "registration_count",
        "admission_count",
        "formal_holdout_payload_read_count",
        "prior_evaluation_payload_read_count",
        "d4_high_level_evaluator_call_count",
    ):
        assert scope[field] == 0
    permissions = frozen_audit_result["permissions_and_fallback"]
    assert permissions["all_permission_fields_false"] is True
    assert permissions["rule_fallback_required"] is True
    conclusion = frozen_audit_result["admission_conclusion"]
    assert conclusion["admission_allowed"] is False
    assert conclusion["confidence_calibration_allowed"] is False
    assert conclusion["formal_holdout_allowed"] is False
    assert conclusion["runtime_preflight_allowed"] is False


def test_v7_audit_preserves_five_frozen_input_trees(
    frozen_audit_result: dict[str, object],
) -> None:
    immutability = frozen_audit_result["input_immutability"]
    five_input_trees = {
        "source_tree_sha256",
        "labeled_export_tree_sha256",
        "labeled_dataset_tree_sha256",
        "frozen_v4_tree_sha256",
        "candidate_v7_tree_sha256",
    }
    assert all(
        immutability["before_sha256"][name]
        == immutability["after_sha256"][name]
        for name in five_input_trees
    )
    assert (
        immutability["before_sha256"]["d4_evaluation_tree_sha256"]
        == immutability["after_sha256"]["d4_evaluation_tree_sha256"]
    )
    assert immutability["input_mutation_count"] == 0


def test_v7_audit_does_not_import_d4_high_level_evaluator() -> None:
    source = (
        REPOSITORY_ROOT
        / "research_modules/d6_evaluation_metrics/d6_evaluation_metrics/"
        "d4_v7_source_independent_external_audit.py"
    ).read_text(encoding="utf-8")
    assert "region_resource_v7_external_evaluation" not in source
    assert "evaluate_region_resource_v7_external_dataset" not in source


def test_report_preserves_lf_csv_and_unavailable_value(
    tmp_path: Path,
    frozen_audit_result: dict[str, object],
) -> None:
    outputs = write_d4_v7_external_audit_report(
        tmp_path / "audit",
        frozen_audit_result,
    )
    csv_bytes = outputs["csv"].read_bytes()
    csv_text = outputs["csv"].read_text(encoding="utf-8")
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert b"\r" not in csv_bytes
    assert csv_bytes.endswith(b"\n")
    assert "unavailable" in csv_text
    assert "0/42" in report
    assert len(outputs["sha256sums"].read_text().splitlines()) == 4
    assert outputs["records_jsonl"].read_bytes() == (
        D4_EVALUATION_ROOT / "evaluation_records.jsonl"
    ).read_bytes()
    assert frozen_audit_result["d4_artifact_reconciliation"][
        "d4_d6_jsonl_byte_identical"
    ] is True
