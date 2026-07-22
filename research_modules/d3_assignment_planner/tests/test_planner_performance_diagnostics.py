from __future__ import annotations

from dataclasses import fields

from d3_assignment_planner import (
    AssignmentPlan,
    AssignmentPlanner,
    D3PlannerOperationCounts,
    PlannerConfig,
    build_reproducible_assignment_fixture,
    canonical_plan_binding_sha256,
    canonical_plan_business_sha256,
    run_reproducible_planner_performance_benchmark,
)


def _planner(*, max_edges: int = 32) -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            max_candidate_edges_per_target=max_edges,
            human_authorization_state="approved",
            unassigned_base_cost=50.0,
        )
    )


def test_fixture_and_business_hash_are_reproducible_without_plan_identity() -> None:
    first_fixture = build_reproducible_assignment_fixture(count=24, seed=42_000)
    second_fixture = build_reproducible_assignment_fixture(count=24, seed=42_000)
    assert first_fixture.input_sha256 == second_fixture.input_sha256

    first = _planner(max_edges=8).plan(
        first_fixture.tracks,
        first_fixture.resources,
        timestamp=0.0,
    )
    second = _planner(max_edges=8).plan(
        second_fixture.tracks,
        second_fixture.resources,
        timestamp=0.0,
    )
    assert first.plan_id != second.plan_id
    assert canonical_plan_binding_sha256(first) == canonical_plan_binding_sha256(
        second
    )
    assert canonical_plan_business_sha256(first) == canonical_plan_business_sha256(
        second
    )


def test_diagnostic_is_fixed_size_and_never_enters_plan_metadata() -> None:
    fixture = build_reproducible_assignment_fixture(count=20, seed=42_001)
    plan = _planner(max_edges=6).plan(
        fixture.tracks,
        fixture.resources,
        timestamp=0.0,
    )
    forbidden = {
        "performance_diagnostic",
        "performance_diagnostics",
        "phase_timings",
        "wall_clock_ms",
    }
    assert forbidden.isdisjoint(plan.metadata)

    report = run_reproducible_planner_performance_benchmark(
        count=20,
        seed=42_001,
        max_candidate_edges_per_target=6,
        repeat=1,
    )
    keys = set(report["modes"][0]["initial"]["operation_counts"])
    assert keys == {field.name for field in fields(D3PlannerOperationCounts)}
    assert not any("ms" in key or "time" in key for key in keys)
    assert report["plan_metadata_contains_performance_diagnostics"] is False
    assert report["latest_published_signature_source"] == "planner_owned_cache"
    assert report["caller_previous_signature_used_as_latest"] is False


def test_refresh_computes_previous_and_candidate_execution_signatures_once(
    monkeypatch,
) -> None:
    fixture = build_reproducible_assignment_fixture(count=20, seed=42_003)
    planner = _planner(max_edges=6)
    first = planner.plan(fixture.tracks, fixture.resources, timestamp=0.0)
    original = AssignmentPlan.execution_signature
    calls_by_object: dict[int, int] = {}

    def counted(plan: AssignmentPlan):
        calls_by_object[id(plan)] = calls_by_object.get(id(plan), 0) + 1
        return original(plan)

    monkeypatch.setattr(AssignmentPlan, "execution_signature", counted)
    planner.plan(
        fixture.tracks,
        fixture.resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert calls_by_object[id(first)] == 1
    assert sum(calls_by_object.values()) == 2


def test_reference_switches_preserve_bindings_versions_and_business_hashes() -> None:
    report = run_reproducible_planner_performance_benchmark(
        count=32,
        seed=42_002,
        max_candidate_edges_per_target=8,
        repeat=2,
    )
    modes = {item["mode"]: item for item in report["modes"]}
    assert set(modes) == {
        "default",
        "identity_recompute_reference",
        "evidence_bypass_reference",
    }
    assert report["semantic_equivalence"] == {
        "bindings_equal": True,
        "plan_versions_equal": True,
        "canonical_business_hashes_equal": True,
        "refresh_reuses_plan_identity": True,
        "rule_costs_changed": False,
        "hungarian_changed": False,
        "hysteresis_changed": False,
        "d5_d7_binding_changed": False,
    }
    default = modes["default"]
    bypass = modes["evidence_bypass_reference"]
    assert default["initial"]["evidence_available"] is True
    assert bypass["initial"]["evidence_available"] is False
    assert (
        bypass["initial"]["operation_counts"]["evidence_matrix_cell_copy_count"]
        == 0
    )
    assert default["initial"]["plan_version"] == 1
    assert default["refresh"]["plan_version"] == 1
    assert default["refresh"]["decision_state"] == "unchanged"


def test_200x200_operation_counts_expose_each_hot_path_boundary() -> None:
    report = run_reproducible_planner_performance_benchmark(
        count=200,
        seed=42_000,
        max_candidate_edges_per_target=32,
        repeat=1,
    )
    default = report["modes"][0]
    initial = default["initial"]["operation_counts"]
    refresh = default["refresh"]["operation_counts"]

    assert initial["full_pair_count"] == 40_000
    assert initial["vectorized_rule_pair_count"] == 40_000
    assert initial["candidate_edge_count"] == 6_400
    assert initial["plan_edge_materialization_count"] == 6_400
    assert initial["canonical_edge_hash_call_count"] == 1
    assert initial["canonical_edge_hash_item_count"] == 6_400
    assert initial["evidence_matrix_cell_copy_count"] == 80_000
    assert initial["evidence_candidate_mask_cell_copy_count"] == 80_000
    assert initial["evidence_breakdown_cell_visit_count"] == 40_000
    assert initial["evidence_unique_breakdown_sanitize_count"] < 40_000
    assert initial["hysteresis_candidate_edge_visit_count"] == 0
    assert refresh["hysteresis_candidate_edge_visit_count"] == 6_400
    assert refresh["hysteresis_binding_rescore_count"] == 400
    assert refresh["plan_id_generation_count"] == 1
    assert refresh["publish_validation_call_count"] == 1
