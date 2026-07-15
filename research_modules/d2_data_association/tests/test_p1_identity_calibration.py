from __future__ import annotations

from copy import deepcopy
import json

import pytest

import d2_data_association.p1_identity_calibration as identity_calibration

from d2_data_association import (
    FrozenReplayCase,
    P1_IDENTITY_INPUT_SCHEMA_VERSION,
    SCENARIO_DIFFICULTIES,
    baseline_identity_config,
    build_dense_crossing_replay_fixture,
    extract_offline_truth_labels,
    fixed_identity_calibration_matrix,
    load_identity_calibration_manifest,
    run_p1_identity_calibration,
    strip_offline_truth_from_frames,
)


_MISSING = object()


def _aggregate_metric(value: float | None, *, p95: float | None = None) -> dict:
    return {
        "available": value is not None,
        "count": 0 if value is None else 20,
        "mean": value,
        "minimum": value,
        "maximum": value,
        "p95": value if p95 is None else p95,
    }


def _admission_row(
    config_id: str,
    *,
    is_baseline: bool,
    id_switch_count: float | None = 1.0,
    identity_continuity: float | None = 0.9,
    false_track_count: float | None = 1.0,
    p95_loop_latency_s: float | None = 0.02,
    online_truth_leakage_count: int | object = 0,
) -> dict:
    aggregate = {
        "id_switch_count": _aggregate_metric(id_switch_count),
        "identity_continuity": _aggregate_metric(identity_continuity),
        "false_track_count": _aggregate_metric(false_track_count),
        "p95_loop_latency_s": _aggregate_metric(
            p95_loop_latency_s, p95=p95_loop_latency_s
        ),
    }
    if online_truth_leakage_count is not _MISSING:
        aggregate["online_truth_leakage_count"] = online_truth_leakage_count
    return {
        "associator": "GNNHungarianAssociator",
        "config": {"config_id": config_id, "is_baseline": is_baseline},
        "aggregate": aggregate,
        "aggregate_by_difficulty": {},
    }


def _cases(
    count: int,
    *,
    evidence_source: str = "airsim",
    scenario_difficulty: str = "nominal",
    difficulty_metadata: dict | None = None,
) -> tuple[FrozenReplayCase, ...]:
    cases = []
    expected_spacing = 2.0 if scenario_difficulty in {"tight_crossing", "combined"} else 4.0
    for seed in range(count):
        governed = build_dense_crossing_replay_fixture(
            target_count=2,
            seed=seed,
            steps=4,
            missed_detection_frames=(),
            false_alarm_frames=(2,),
        )
        frames = deepcopy(strip_offline_truth_from_frames(governed))
        for frame in frames:
            frame.setdefault("replay_metadata", {})["target_spacing_m"] = expected_spacing
        cases.append(
            FrozenReplayCase(
                seed=seed,
                replay_name=f"frozen-{seed}",
                frames=tuple(frames),
                offline_truth_labels=tuple(extract_offline_truth_labels(governed)),
                evidence_source=evidence_source,
                scenario_difficulty=scenario_difficulty,
                difficulty_metadata=difficulty_metadata,
            )
        )
    return tuple(cases)


def test_fixed_matrix_has_all_54_combinations_and_one_baseline() -> None:
    matrix = fixed_identity_calibration_matrix()

    assert len(matrix) == 54
    assert len({config.config_id for config in matrix}) == 54
    assert sum(config.is_baseline for config in matrix) == 1
    assert {config.gate_threshold for config in matrix} == {5.99, 9.21, 13.82}
    assert {config.quality_aware_gate for config in matrix} == {False, True}
    assert {
        (config.lost_miss_threshold, config.drop_miss_threshold)
        for config in matrix
    } == {(1, 3), (2, 5), (3, 7)}
    assert {config.motion_weight_multiplier for config in matrix} == {0.5, 1.0, 2.0}


def test_ten_seed_screening_uses_one_digest_and_missing_confirmation_is_unavailable() -> None:
    report = run_p1_identity_calibration(
        _cases(10),
        frozen_p95_loop_latency_budget_s=0.1,
    ).to_dict()

    screening = report["screening"]
    assert screening["available"] is True
    assert screening["provided_seed_count"] == 10
    assert screening["configuration_count"] == 54
    assert screening["all_configurations_used_same_frozen_input"] is True
    assert len({row["frozen_input_digest"] for row in screening["results"]}) == 1
    assert all(row["aggregate"]["seed_count"] == 10 for row in screening["results"])
    assert all(
        row["aggregate"]["online_truth_leakage_count"] == 0
        for row in screening["results"]
    )
    assert report["jpda_comparison"]["screening"]["executed"] is True
    assert report["confirmation"]["available"] is False
    assert report["confirmation"]["unavailable_reason"] == (
        "insufficient_frozen_replay_seeds:0<20"
    )
    assert report["decision"]["available"] is False
    assert report["decision"]["default_online_path_changed"] is False


def test_twenty_seed_confirmation_reports_metrics_and_keeps_mainline() -> None:
    report = run_p1_identity_calibration(
        _cases(10),
        confirmation_cases=_cases(20, scenario_difficulty="combined"),
        frozen_p95_loop_latency_budget_s=0.1,
    ).to_dict()

    assert report["schema_version"] == "d2-p1-identity-calibration/v2"
    confirmation = report["confirmation"]
    assert confirmation["available"] is True
    assert confirmation["provided_seed_count"] == 20
    assert confirmation["all_configurations_used_same_frozen_input"] is True
    assert 1 <= confirmation["configuration_count"] <= 2
    for row in confirmation["results"]:
        aggregate = row["aggregate"]
        assert aggregate["seed_count"] == 20
        assert aggregate["id_switch_count"]["available"] is True
        assert aggregate["identity_continuity"]["available"] is True
        assert aggregate["coverage_continuity"]["available"] is True
        assert aggregate["false_track_count"]["available"] is True
        assert aggregate["rmse"]["available"] is True
        assert aggregate["mean_initialization_latency_s"]["available"] is True
        assert aggregate["p95_loop_latency_s"]["available"] is True
        assert aggregate["nis_available_seed_count"] == 20
        assert aggregate["nees_available_seed_count"] == 20
        assert aggregate["online_truth_leakage_count"] == 0
    assert report["jpda_comparison"]["confirmation"]["executed"] is True
    assert report["decision"]["available"] is True
    assert report["decision"]["selected_online_path"] == "baseline_gnn_hungarian"
    assert report["decision"]["default_online_path_changed"] is False
    assert report["decision"]["policy"]["promotion_effect"] == (
        "review_recommendation_only"
    )
    assert set(report["decision"]["by_difficulty"]) == {"combined"}
    combined = report["difficulty_results"]["confirmation"]["by_difficulty"][
        "combined"
    ]
    assert combined["seed_count"] == 20
    assert combined["baseline_gnn"]["metrics"]["id_switch_count"][
        "available"
    ] is True
    assert combined["baseline_gnn"]["metrics"]["identity_continuity"][
        "available"
    ] is True
    assert combined["baseline_gnn"]["metrics"]["false_track_count"][
        "available"
    ] is True
    assert combined["baseline_gnn"]["metrics"]["rmse"]["available"] is True
    assert combined["baseline_gnn"]["metrics"]["p95_loop_latency_s"][
        "available"
    ] is True


def test_ceiling_aware_continuity_can_form_review_without_changing_mainline() -> None:
    baseline = _admission_row(
        "baseline",
        is_baseline=True,
        id_switch_count=1.3583,
        identity_continuity=0.981,
        false_track_count=1.0,
        p95_loop_latency_s=0.024,
    )
    candidate = _admission_row(
        "candidate",
        is_baseline=False,
        id_switch_count=0.6167,
        identity_continuity=0.984,
        false_track_count=1.05,
        p95_loop_latency_s=0.024,
    )

    decision = identity_calibration._admission_decision(
        {"available": True, "results": [baseline, candidate]},
        {"executed": False},
        latency_budget_s=0.1,
    )
    assessment = decision["candidate_assessments"][0]

    assert decision["policy_version"] == (
        "d2-p1-identity-admission/ceiling-aware-error-reduction-v1"
    )
    assert decision["promotion_recommended"] is True
    assert decision["default_online_path_changed"] is False
    assert decision["selected_online_path"] == "baseline_gnn_hungarian"
    assert assessment["identity_continuity_baseline_headroom"] == pytest.approx(
        0.019
    )
    assert assessment["identity_continuity_increase"] == pytest.approx(0.003)
    assert assessment["identity_continuity_required_increase"] == pytest.approx(
        0.0019
    )
    assert assessment[
        "identity_continuity_headroom_reduction_fraction"
    ] == pytest.approx(0.003 / 0.019)
    assert assessment["checks"]["identity_continuity_ceiling_aware"] is True
    assert assessment["legacy_v1_identity_continuity_gate"] == {
        "minimum_absolute_increase": 0.1,
        "passed": False,
        "status": "deprecated_not_used_for_v2_admission",
        "used_for_admission": False,
    }
    assert all(assessment["checks"].values())
    assert all(assessment["gate_reasons"].values())


@pytest.mark.parametrize("baseline", [0.0, 0.5, 0.981, 0.999999, 1.0])
def test_continuity_required_increase_never_exceeds_theoretical_headroom(
    baseline: float,
) -> None:
    gate = identity_calibration._continuity_admission_gate(1.0, baseline)

    assert gate["required_increase"] <= gate["baseline_headroom"]
    assert baseline + gate["required_increase"] <= 1.0 + 1.0e-12
    assert gate["passed"] is True


def test_perfect_baseline_is_non_degradation_only_and_degradation_fails() -> None:
    unchanged = identity_calibration._continuity_admission_gate(1.0, 1.0)
    degraded = identity_calibration._continuity_admission_gate(0.999, 1.0)
    invalid = identity_calibration._continuity_admission_gate(1.001, 1.0)

    assert unchanged["passed"] is True
    assert unchanged["required_increase"] == 0.0
    assert unchanged["headroom_reduction_fraction"] is None
    assert unchanged["reason"] == (
        "no_baseline_headroom_and_candidate_non_degrading"
    )
    assert degraded["passed"] is False
    assert degraded["reason"] == "identity_continuity_degraded"
    assert invalid["passed"] is False
    assert invalid["reason"] == "candidate_metric_above_valid_range"


def test_id_switch_improvement_alone_never_recommends_promotion() -> None:
    baseline = _admission_row(
        "baseline",
        is_baseline=True,
        id_switch_count=1.0,
        identity_continuity=0.5,
    )
    candidate = _admission_row(
        "candidate",
        is_baseline=False,
        id_switch_count=0.5,
        identity_continuity=0.51,
    )

    decision = identity_calibration._admission_decision(
        {"available": True, "results": [baseline, candidate]},
        {"executed": False},
        latency_budget_s=0.1,
    )
    assessment = decision["candidate_assessments"][0]

    assert assessment["checks"]["id_switch_reduction"] is True
    assert assessment["checks"]["identity_continuity_ceiling_aware"] is False
    assert assessment["gate_reasons"]["identity_continuity_ceiling_aware"] == (
        "insufficient_continuity_error_reduction"
    )
    assert decision["promotion_recommended"] is False
    assert decision["default_online_path_changed"] is False


@pytest.mark.parametrize(
    ("field", "expected_gate", "expected_reason"),
    [
        (
            "id_switch_count",
            "id_switch_reduction",
            "candidate_metric_unavailable",
        ),
        (
            "identity_continuity",
            "identity_continuity_ceiling_aware",
            "candidate_metric_unavailable",
        ),
        (
            "false_track_count",
            "false_track_limit",
            "candidate_metric_unavailable",
        ),
        (
            "p95_loop_latency_s",
            "p95_loop_latency_budget",
            "candidate_metric_unavailable",
        ),
        (
            "online_truth_leakage_count",
            "truth_leakage_zero",
            "candidate_metric_unavailable",
        ),
    ],
)
def test_missing_admission_metrics_fail_closed_with_reason(
    field: str,
    expected_gate: str,
    expected_reason: str,
) -> None:
    kwargs = {
        "id_switch_count": 0.5,
        "identity_continuity": 0.95,
        "false_track_count": 1.0,
        "p95_loop_latency_s": 0.02,
        "online_truth_leakage_count": 0,
    }
    kwargs[field] = _MISSING if field == "online_truth_leakage_count" else None
    baseline = _admission_row("baseline", is_baseline=True)
    candidate = _admission_row("candidate", is_baseline=False, **kwargs)

    assessment = identity_calibration._assess_candidate(
        candidate, baseline, latency_budget_s=0.1
    )

    assert assessment["checks"][expected_gate] is False
    assert assessment["gate_reasons"][expected_gate] == expected_reason
    assert assessment["all_thresholds_passed"] is False


def test_other_joint_admission_gates_remain_fail_safe() -> None:
    baseline_zero_idsw = _admission_row(
        "baseline", is_baseline=True, id_switch_count=0.0
    )
    candidate_zero_idsw = _admission_row(
        "candidate", is_baseline=False, id_switch_count=0.0
    )
    zero_assessment = identity_calibration._assess_candidate(
        candidate_zero_idsw, baseline_zero_idsw, latency_budget_s=0.1
    )
    assert zero_assessment["checks"]["id_switch_reduction"] is False
    assert zero_assessment["gate_reasons"]["id_switch_reduction"] == (
        "baseline_zero_no_measurable_reduction_evidence"
    )

    for candidate, gate, reason in (
        (
            _admission_row(
                "false-track",
                is_baseline=False,
                id_switch_count=0.5,
                identity_continuity=0.95,
                false_track_count=1.11,
            ),
            "false_track_limit",
            "false_track_growth_exceeds_limit",
        ),
        (
            _admission_row(
                "latency",
                is_baseline=False,
                id_switch_count=0.5,
                identity_continuity=0.95,
                p95_loop_latency_s=0.101,
            ),
            "p95_loop_latency_budget",
            "p95_loop_latency_budget_exceeded",
        ),
        (
            _admission_row(
                "truth-leakage",
                is_baseline=False,
                id_switch_count=0.5,
                identity_continuity=0.95,
                online_truth_leakage_count=1,
            ),
            "truth_leakage_zero",
            "online_truth_leakage_detected",
        ),
    ):
        assessment = identity_calibration._assess_candidate(
            candidate,
            _admission_row("baseline", is_baseline=True),
            latency_budget_s=0.1,
        )
        assert assessment["checks"][gate] is False
        assert assessment["gate_reasons"][gate] == reason
        assert assessment["all_thresholds_passed"] is False

    baseline_leakage_assessment = identity_calibration._assess_candidate(
        _admission_row(
            "candidate",
            is_baseline=False,
            id_switch_count=0.5,
            identity_continuity=0.95,
        ),
        _admission_row(
            "baseline-truth-leakage",
            is_baseline=True,
            online_truth_leakage_count=1,
        ),
        latency_budget_s=0.1,
    )
    assert baseline_leakage_assessment["checks"]["truth_leakage_zero"] is False
    assert baseline_leakage_assessment["gate_reasons"]["truth_leakage_zero"] == (
        "online_truth_leakage_detected"
    )
    assert baseline_leakage_assessment["all_thresholds_passed"] is False


def test_insufficient_real_input_is_unavailable_not_synthetic() -> None:
    report = run_p1_identity_calibration(
        _cases(9, evidence_source="airsim"),
        confirmation_cases=_cases(19, evidence_source="airsim"),
        frozen_p95_loop_latency_budget_s=0.1,
    ).to_dict()

    assert report["screening"]["available"] is False
    assert report["screening"]["airsim_evidence"] is True
    assert report["screening"]["results"] == []
    assert report["confirmation"]["available"] is False
    assert report["jpda_comparison"]["screening"]["executed"] is False
    assert report["decision"]["available"] is False


def test_governed_real_airsim_source_is_classified_in_all_stages() -> None:
    source = "real_airsim_blocks_d1_governed_replay"
    report = run_p1_identity_calibration(
        _cases(10, evidence_source=source),
        confirmation_cases=_cases(20, evidence_source=source),
        frozen_p95_loop_latency_budget_s=0.1,
    ).to_dict()

    assert report["screening"]["evidence_sources"] == [source]
    assert report["screening"]["airsim_evidence"] is True
    assert report["confirmation"]["airsim_evidence"] is True
    assert report["jpda_comparison"]["screening"]["airsim_evidence"] is True
    assert report["jpda_comparison"]["confirmation"]["airsim_evidence"] is True


def test_synthetic_label_containing_airsim_is_not_real_evidence() -> None:
    report = run_p1_identity_calibration(
        _cases(9, evidence_source="synthetic_airsim_fixture"),
        frozen_p95_loop_latency_budget_s=0.1,
    ).to_dict()

    assert report["screening"]["airsim_evidence"] is False
    assert report["jpda_comparison"]["screening"]["airsim_evidence"] is False


def test_manifest_loader_preserves_source_and_budget(tmp_path) -> None:
    governed = build_dense_crossing_replay_fixture(
        target_count=2,
        seed=7,
        steps=4,
    )
    replay_path = tmp_path / "replay.json"
    truth_path = tmp_path / "truth.jsonl"
    replay_path.write_text(
        json.dumps(
            [
                {
                    **frame,
                    "replay_metadata": {
                        **frame.get("replay_metadata", {}),
                        "target_spacing_m": 4.0,
                    },
                }
                for frame in strip_offline_truth_from_frames(governed)
            ]
        ),
        encoding="utf-8",
    )
    truth_path.write_text(
        "\n".join(
            json.dumps(label.to_dict())
            for label in extract_offline_truth_labels(governed)
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": P1_IDENTITY_INPUT_SCHEMA_VERSION,
                "evidence_source": "airsim",
                "scenario_difficulty": "delayed_noisy",
                "difficulty_metadata": {
                    "measurement_delay_s": [0.25, 0.45],
                    "covariance_scale": 3.0,
                },
                "frozen_p95_loop_latency_budget_s": 0.02,
                "cases": [
                    {
                        "seed": 7,
                        "replay_name": "episode-7",
                        "replay_path": replay_path.name,
                        "truth_path": truth_path.name,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, budget = load_identity_calibration_manifest(manifest_path)

    assert len(cases) == 1
    assert cases[0].seed == 7
    assert cases[0].evidence_source == "airsim"
    assert cases[0].scenario_difficulty == "delayed_noisy"
    assert cases[0].scenario_difficulty_metadata["declared_parameters"] == {
        "measurement_delay_s": [0.25, 0.45],
        "covariance_scale": 3.0,
    }
    assert budget == 0.02


def test_six_difficulty_suite_uses_difficulty_seed_key_and_reports_strata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        identity_calibration,
        "fixed_identity_calibration_matrix",
        lambda: (baseline_identity_config(),),
    )
    screening = tuple(
        case
        for difficulty in SCENARIO_DIFFICULTIES
        for case in _cases(10, scenario_difficulty=difficulty)
    )
    report = run_p1_identity_calibration(
        screening,
        confirmation_cases=_cases(20, scenario_difficulty="combined"),
        frozen_p95_loop_latency_budget_s=0.1,
    ).to_dict()

    assert report["screening"]["available"] is True
    assert report["screening"]["provided_seed_count"] == 60
    assert report["screening"]["seed_count_by_difficulty"] == {
        difficulty: 10 for difficulty in SCENARIO_DIFFICULTIES
    }
    baseline = report["screening"]["results"][0]
    assert set(baseline["aggregate_by_difficulty"]) == set(SCENARIO_DIFFICULTIES)
    assert all(
        aggregate["seed_count"] == 10
        for aggregate in baseline["aggregate_by_difficulty"].values()
    )
    difficulty_results = report["difficulty_results"]["screening"][
        "by_difficulty"
    ]
    assert set(difficulty_results) == set(SCENARIO_DIFFICULTIES)
    assert all(
        row["scenario_still_non_discriminative"] is True
        for row in difficulty_results.values()
    )
    assert report["decision"]["by_difficulty"]["combined"][
        "scenario_still_non_discriminative"
    ] is True
    assert report["decision"]["by_difficulty"]["combined"][
        "promotion_recommended"
    ] is False


def test_difficulty_metadata_and_duplicate_keys_fail_closed() -> None:
    same_difficulty = _cases(1) + _cases(1)
    duplicate_validation = identity_calibration._validate_cases(
        same_difficulty, required_seed_count=1
    )
    assert duplicate_validation["available"] is False
    assert duplicate_validation["unavailable_reason"] == (
        "duplicate_seed_in_frozen_replay_suite"
    )

    different_difficulties = _cases(1) + _cases(
        1, scenario_difficulty="tight_crossing"
    )
    accepted_validation = identity_calibration._validate_cases(
        different_difficulties, required_seed_count=1
    )
    assert accepted_validation["available"] is True

    inconsistent = _cases(
        1,
        scenario_difficulty="combined",
        difficulty_metadata={"fixture_version": "a"},
    ) + tuple(
        FrozenReplayCase(
            seed=1,
            replay_name=case.replay_name,
            frames=case.frames,
            offline_truth_labels=case.offline_truth_labels,
            evidence_source=case.evidence_source,
            scenario_difficulty="combined",
            difficulty_metadata={"fixture_version": "b"},
        )
        for case in _cases(1, scenario_difficulty="combined")
    )
    inconsistent_validation = identity_calibration._validate_cases(
        inconsistent, required_seed_count=1
    )
    assert inconsistent_validation["available"] is False
    assert inconsistent_validation["unavailable_reason"] == (
        "inconsistent_scenario_difficulty_metadata:combined"
    )

    with pytest.raises(ValueError, match="scenario_difficulty must be one of"):
        _cases(1, scenario_difficulty="unknown")


def test_seed_specific_actual_parameters_do_not_break_difficulty_governance() -> None:
    first = _cases(
        1,
        scenario_difficulty="combined",
        difficulty_metadata={
            "schema_version": "d2-p1-governed-replay-stress/v1",
            "fixture_version": "dense-crossing-v1",
            "declared_target_spacing_m": 2.0,
            "seed": 1,
            "actual_parameters": {"dropout_duration_s": 0.7},
        },
    )[0]
    second_template = _cases(
        1,
        scenario_difficulty="combined",
        difficulty_metadata={
            "schema_version": "d2-p1-governed-replay-stress/v1",
            "fixture_version": "dense-crossing-v1",
            "declared_target_spacing_m": 2.0,
            "seed": 2,
            "actual_parameters": {"dropout_duration_s": 1.1},
        },
    )[0]
    second = FrozenReplayCase(
        seed=1,
        replay_name="combined-seed-1",
        frames=second_template.frames,
        offline_truth_labels=second_template.offline_truth_labels,
        evidence_source=second_template.evidence_source,
        scenario_difficulty="combined",
        difficulty_metadata=second_template.difficulty_metadata,
    )

    validation = identity_calibration._validate_cases(
        (first, second), required_seed_count=2
    )

    assert validation["available"] is True


def test_real_airsim_spacing_provenance_is_required_and_mismatch_fails_closed() -> None:
    missing_frames = tuple(
        {
            **frame,
            "replay_metadata": {
                key: value
                for key, value in frame.get("replay_metadata", {}).items()
                if key != "target_spacing_m"
            },
        }
        for frame in _cases(1)[0].frames
    )
    missing = FrozenReplayCase(
        seed=0,
        replay_name="missing-spacing",
        frames=missing_frames,
        offline_truth_labels=_cases(1)[0].offline_truth_labels,
        evidence_source="real_airsim_blocks_d1_governed_replay",
        scenario_difficulty="nominal",
    )
    missing_validation = identity_calibration._validate_cases(
        (missing,), required_seed_count=1
    )
    assert missing_validation["available"] is False
    assert "missing_real_airsim_target_spacing_provenance" in missing_validation[
        "unavailable_reason"
    ]

    mismatched = FrozenReplayCase(
        seed=0,
        replay_name="mismatched-spacing",
        frames=_cases(1, scenario_difficulty="nominal")[0].frames,
        offline_truth_labels=_cases(1)[0].offline_truth_labels,
        evidence_source="real_airsim_blocks_d1_governed_replay",
        scenario_difficulty="tight_crossing",
    )
    mismatch_validation = identity_calibration._validate_cases(
        (mismatched,), required_seed_count=1
    )
    assert mismatch_validation["available"] is False
    assert "target_spacing_outside_difficulty_tolerance" in mismatch_validation[
        "unavailable_reason"
    ]
