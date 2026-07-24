from __future__ import annotations

import json
from pathlib import Path

import pytest

from d1_sensor_fusion import (
    STRUCTURAL_AMBIGUITY_REPLAY_DIAGNOSTIC_SCHEMA_VERSION,
    render_structural_ambiguity_replay_diagnostic_cn,
    run_structural_ambiguity_centroid_replay_diagnostic,
    write_structural_ambiguity_replay_diagnostic,
)


_REPLAY_REPLACEMENT_ROOT_CAUSE = (
    "candidate_rejection_publication_base_replacement_with_"
    "non_semigroup_discrete_process_noise_segmentation"
)
_FINITE_DIFFERENCE_INTERPRETATION = (
    "centroid_correction_not_applied_but_publication_base_replay_"
    "replacement_produces_finite_diagnostic_only_difference"
)


@pytest.fixture(scope="module")
def diagnostic_report() -> dict[str, object]:
    return run_structural_ambiguity_centroid_replay_diagnostic()


def _scenario(
    report: dict[str, object],
    scenario_kind: str,
) -> dict[str, object]:
    return next(
        item
        for item in report["scenarios"]  # type: ignore[index]
        if item["scenario_kind"] == scenario_kind
    )


def _assert_rejected_candidate_path(
    report: dict[str, object],
    scenario: dict[str, object],
    *,
    expected_reason: str,
    expected_covariance_delta_min_eigenvalue: float,
) -> None:
    outcome = scenario["target_outcome"]
    checks = scenario["invariant_checks"]
    scenario_kind = scenario["scenario_kind"]
    summary = report["rejected_scenario_diagnostics"][scenario_kind]

    assert outcome["applied_component_count"] == 0
    assert outcome["rejection_reason"] == expected_reason
    assert checks["target_centroid_formula_rejection_reason"] == expected_reason
    assert checks["target_centroid_formula_correction_produced"] is False
    assert checks[
        "target_centroid_state_or_covariance_correction_applied"
    ] is False
    assert checks["rejected_target_no_centroid_formula_output"] is True

    assert checks["target_publication_base_replacement_count"] == 1
    assert checks[
        "rejected_target_pre_replacement_matches_control_bitwise"
    ] is True
    assert checks[
        "rejected_target_post_replacement_matches_publication_base_bitwise"
    ] is True
    assert checks[
        "rejected_target_published_matches_post_replacement_bitwise"
    ] is True
    assert checks[
        "rejected_target_control_candidate_delta_explained_by_replacement_bitwise"
    ] is True
    assert checks[
        "rejected_target_publication_base_replacement_side_effect_present"
    ] is True
    assert checks["rejected_target_path_strictly_attributed"] is True
    assert checks[
        "rejected_target_prediction_segmentation_residual_max_abs"
    ] < 1.0e-12

    covariance_delta = checks[
        "rejected_target_covariance_delta_min_eigenvalue"
    ]
    assert covariance_delta < 0.0
    assert covariance_delta != 0.0
    assert covariance_delta == pytest.approx(
        expected_covariance_delta_min_eigenvalue,
        rel=0.0,
        abs=1.0e-12,
    )
    assert checks["minimum_covariance_delta_eigenvalue"] == covariance_delta
    assert checks["rejected_target_covariance_delta_max_abs"] > 0.0
    assert checks["covariance_not_contracted"] is False
    assert checks["covariance_non_contraction_required"] is False
    assert checks["covariance_non_contraction_acceptance"] is None
    assert checks[
        "rejected_scenario_covariance_delta_diagnostic_only"
    ] is True
    assert checks["applied_scenario_covariance_gate_passed"] is False

    assert checks["rejected_target_delta_root_cause"] == (
        _REPLAY_REPLACEMENT_ROOT_CAUSE
    )
    assert checks["rejected_target_finite_difference_interpretation"] == (
        _FINITE_DIFFERENCE_INTERPRETATION
    )
    assert checks["candidate_promotion_evidence_eligible"] is False
    assert checks["candidate_promotion_ineligibility_reason"] == (
        "controlled_boundary_diagnostic_only"
    )
    assert checks["rejected_target_promotion_boundary"] == (
        "candidate_not_promoted"
    )
    assert scenario["promotion_boundary"] == "candidate_not_promoted"
    assert scenario["candidate_promoted"] is False

    assert summary["rejection_reason"] == expected_reason
    assert summary["applied_component_count"] == 0
    assert summary["centroid_correction_applied"] is False
    assert summary["publication_base_replay_replacement_count"] == 1
    assert summary[
        "candidate_minus_control_covariance_delta_min_eigenvalue"
    ] == covariance_delta
    assert summary["root_cause"] == _REPLAY_REPLACEMENT_ROOT_CAUSE
    assert summary["interpretation"] == _FINITE_DIFFERENCE_INTERPRETATION
    assert summary["diagnostic_only"] is True
    assert summary["promotion_boundary"] == "candidate_not_promoted"


def test_synchronous_balanced_cycle_applies_bounded_common_translation(
    diagnostic_report: dict[str, object],
) -> None:
    scenario = _scenario(
        diagnostic_report,
        "synchronous_balanced_cycle",
    )
    outcome = scenario["target_outcome"]
    component = outcome["components"][0]
    checks = scenario["invariant_checks"]

    assert component["member_count"] == 2
    assert component["observation_count"] == 2
    assert component["free_row_count"] == 0
    assert component["free_column_count"] == 0
    assert component["component_kinds"] == ["alternating_cycle"]
    assert outcome["applied_component_count"] == 1
    assert outcome["rejection_reason"] is None
    assert checks["translation_nonzero"] is True
    assert 0.0 < checks["translation_norm_m"] <= 30.0
    assert checks["common_translation"] is True
    assert checks["velocity_unchanged"] is True
    assert checks["relative_position_unchanged"] is True
    assert checks["hits_unchanged"] is True
    assert checks["lineage_unchanged"] is True
    assert checks["identity_unchanged"] is True
    assert checks["global_track_id_unchanged"] is True
    assert checks["covariance_not_contracted"] is True
    assert checks["covariance_non_contraction_required"] is True
    assert checks["covariance_non_contraction_acceptance"] is True
    assert checks["applied_scenario_covariance_gate_passed"] is True
    assert checks["candidate_promotion_evidence_eligible"] is False
    assert checks["candidate_promotion_ineligibility_reason"] == (
        "controlled_boundary_diagnostic_only"
    )
    assert (
        checks["rejected_scenario_covariance_delta_diagnostic_only"]
        is False
    )
    assert scenario["promotion_boundary"] == "candidate_not_promoted"
    assert scenario["candidate_promoted"] is False
    assert scenario[
        "control_and_candidate_consumed_same_frozen_frames"
    ] is True


def test_reordered_balanced_cycle_preserves_timing_and_fails_closed(
    diagnostic_report: dict[str, object],
) -> None:
    scenario = _scenario(
        diagnostic_report,
        "reordered_balanced_cycle",
    )
    outcome = scenario["target_outcome"]
    component = outcome["components"][0]
    organizer = scenario["scan_organizer"]

    assert organizer["audit"]["reordered_scan_count"] == 1
    assert organizer["released_scan_ids"] == [
        "oosm-seed-000",
        "oosm-seed-001",
        "oosm-target-003",
        "oosm-watermark-002",
    ]
    assert outcome["measurement_timestamp"] == pytest.approx(0.3)
    assert outcome["arrival_timestamp"] == pytest.approx(0.65)
    assert outcome["fusion_time_before"] == pytest.approx(0.4)
    assert outcome["measurement_precedes_fusion_time"] is True
    assert component["member_count"] == 2
    assert component["observation_count"] == 2
    assert component["free_row_count"] == 0
    assert component["free_column_count"] == 0
    _assert_rejected_candidate_path(
        diagnostic_report,
        scenario,
        expected_reason="oosm_scan",
        expected_covariance_delta_min_eigenvalue=-0.0071928353214153066,
    )
    assert scenario[
        "control_and_candidate_consumed_same_frozen_frames"
    ] is True


def test_unbalanced_component_reports_cardinality_and_fails_closed(
    diagnostic_report: dict[str, object],
) -> None:
    scenario = _scenario(
        diagnostic_report,
        "unbalanced_component",
    )
    outcome = scenario["target_outcome"]
    component = outcome["components"][0]

    assert component["member_count"] == 2
    assert component["observation_count"] == 1
    assert component["maximum_matching_cardinality"] == 1
    assert component["free_row_count"] == 1
    assert component["free_column_count"] == 0
    _assert_rejected_candidate_path(
        diagnostic_report,
        scenario,
        expected_reason="unbalanced_component",
        expected_covariance_delta_min_eigenvalue=-0.004617076466238031,
    )
    assert scenario[
        "control_and_candidate_consumed_same_frozen_frames"
    ] is True


def test_frozen_replay_digest_and_report_are_deterministic(
    diagnostic_report: dict[str, object],
) -> None:
    repeated = run_structural_ambiguity_centroid_replay_diagnostic()
    first_hashes = [
        item["frozen_replay"]["bundle_sha256"]
        for item in diagnostic_report["scenarios"]  # type: ignore[index]
    ]
    repeated_hashes = [
        item["frozen_replay"]["bundle_sha256"]
        for item in repeated["scenarios"]
    ]

    assert first_hashes == repeated_hashes
    assert diagnostic_report["acceptance"]["passed"] is True  # type: ignore[index]
    assert diagnostic_report["acceptance"][  # type: ignore[index]
        "control_and_candidate_used_same_frozen_frames"
    ] is True
    assert diagnostic_report["candidate_default"] is False
    assert diagnostic_report["candidate_status"] == (
        "experimental_default_off_not_promoted"
    )
    assert diagnostic_report["promotion_boundary"] == (
        "candidate_not_promoted"
    )
    assert diagnostic_report["promotion_evidence_eligible"] is False
    assert diagnostic_report["promotion_ineligibility_reason"] == (
        "controlled_boundary_diagnostic_only"
    )
    assert diagnostic_report["acceptance"][  # type: ignore[index]
        "candidate_not_promoted"
    ] is True
    assert diagnostic_report["acceptance"][  # type: ignore[index]
        "candidate_promoted"
    ] is False


def test_writer_emits_machine_readable_json_and_chinese_markdown(
    diagnostic_report: dict[str, object],
    tmp_path: Path,
) -> None:
    paths = write_structural_ambiguity_replay_diagnostic(
        tmp_path,
        diagnostic_report,
    )
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert payload["schema_version"] == (
        STRUCTURAL_AMBIGUITY_REPLAY_DIAGNOSTIC_SCHEMA_VERSION
    )
    assert payload["acceptance"]["passed"] is True
    assert payload["promotion_boundary"] == "candidate_not_promoted"
    assert payload["promotion_evidence_eligible"] is False
    assert payload["promotion_ineligibility_reason"] == (
        "controlled_boundary_diagnostic_only"
    )
    assert payload["rejected_scenario_diagnostics"][
        "reordered_balanced_cycle"
    ]["candidate_minus_control_covariance_delta_min_eigenvalue"] == (
        pytest.approx(-0.0071928353214153066, rel=0.0, abs=1.0e-12)
    )
    assert payload["rejected_scenario_diagnostics"][
        "unbalanced_component"
    ]["candidate_minus_control_covariance_delta_min_eigenvalue"] == (
        pytest.approx(-0.004617076466238031, rel=0.0, abs=1.0e-12)
    )
    assert render_structural_ambiguity_replay_diagnostic_cn(
        diagnostic_report
    ) == markdown
    assert "同步平衡分量形成一次非零有界共同平移" in markdown
    assert "候选仍为默认关闭" in markdown
    assert "oosm_scan" in markdown
    assert "unbalanced_component" in markdown
    assert "共同质心 correction 未施加" in markdown
    assert "publication-base replay + replace" in markdown
    assert "-0.007192835321415" in markdown
    assert "-0.004617076466238" in markdown
    assert "candidate_not_promoted" in markdown
