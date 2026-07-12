from d3_assignment_planner import (
    P1_ASSIGNMENT_FIXTURE_SCHEMA,
    build_p1_assignment_fixtures,
    p1_assignment_fixture_by_id,
    run_p1_assignment_calibration_matrix,
)


def test_fixture_matrix_covers_non_equal_dynamic_feedback_and_window_cases() -> None:
    fixtures = build_p1_assignment_fixtures()
    by_id = {fixture.scenario_id: fixture for fixture in fixtures}

    assert P1_ASSIGNMENT_FIXTURE_SCHEMA == "d3_assignment_fixture_v2"
    assert (by_id["3v5"].steps[0].resource_count, by_id["3v5"].steps[0].target_count) == (3, 5)
    assert (by_id["5v3"].steps[0].resource_count, by_id["5v3"].steps[0].target_count) == (5, 3)
    assert by_id["new_target"].steps[1].changed_track_ids == ("T05",)
    assert by_id["resource_failure"].steps[1].changed_resource_ids == ("R03",)
    assert by_id["threat_demand_change"].steps[1].tracks[0].effective_demand.required_resource_count == 3
    assert by_id["threat_demand_change"].steps[1].tracks[0].effective_demand.primary_resource_count == 2
    assert by_id["d5_feedback"].steps[1].metadata["feedback_case"] == "reserve_soft_hold"
    assert by_id["hard_window"].steps[1].tracks[0].hard_time_window is True


def test_calibration_matrix_compares_full_and_incremental_with_safety_metrics() -> None:
    summary = run_p1_assignment_calibration_matrix()
    rows = {row.scenario_id: row for row in summary.rows}

    assert summary.scenario_count == summary.transition_count == 8
    assert summary.equivalent_transition_count == 8
    assert summary.incremental_applied_count >= 1
    assert summary.fallback_count >= 1
    assert summary.incremental_latency_ms_total >= 0.0
    assert summary.full_latency_ms_total >= 0.0
    assert summary.incremental_churn_total == summary.full_churn_total
    assert (
        summary.incremental_unassigned_high_threat_total
        == summary.full_unassigned_high_threat_total
    )
    assert (
        summary.incremental_coalition_shortfall_total
        == summary.full_coalition_shortfall_total
    )
    assert rows["new_target"].fallback_reason == "target_set_changed"
    assert rows["resource_failure"].incremental_unassigned_high_threat_count == 1
    assert rows["threat_demand_change"].fallback_reason == "target_demand_changed"
    assert rows["threat_demand_change"].incremental_coalition_shortfall == 1
    assert rows["d5_feedback"].role_aware_primary_preserved is True
    assert rows["hard_window"].incremental_hard_window_reject_count == 1
    assert rows["hard_window"].full_hard_window_reject_count == 1

    serialized = summary.as_dict()
    assert serialized["profile_version"] == "1.1.0"
    assert len(serialized["rows"]) == 8


def test_fixture_lookup_returns_versioned_threat_demand_case() -> None:
    fixture = p1_assignment_fixture_by_id("threat_demand_change")

    assert fixture.profile_version == "1.1.0"
    assert fixture.calibration_metadata()["fixture_schema"] == (
        "d3_assignment_fixture_v2"
    )
    assert fixture.calibration_metadata()["step_shapes"][1][
        "changed_track_ids"
    ] == ("T01",)
