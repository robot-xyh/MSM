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
