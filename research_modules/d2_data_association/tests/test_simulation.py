from __future__ import annotations

from d2_data_association.compat import optional_dependency_status
from d2_data_association.simulation import format_markdown_table, results_to_rows, run_benchmark


def test_simulation_runs_all_associators_for_crossing() -> None:
    results = run_benchmark(
        scenarios=["crossing"],
        associators=["gnn", "jpda", "mht"],
        steps=28,
        seed=11,
    )

    assert len(results) == 3
    for result in results:
        metrics = result.metrics
        assert "id_switch_count" in metrics
        assert "track_continuity" in metrics
        assert "duplicate_assignment_count" in metrics
        assert "confusion_matrix" in metrics
        assert result.elapsed_seconds >= 0.0

    table = format_markdown_table(results)
    assert "| scenario | associator | IDSW |" in table


def test_deterministic_dense_5v5_fixture_compares_associators() -> None:
    first = run_benchmark(
        scenarios=["crossing_dense_5v5"],
        associators=["gnn", "jpda", "mht"],
        steps=32,
        seed=19,
    )
    second = run_benchmark(
        scenarios=["crossing_dense_5v5"],
        associators=["gnn", "jpda", "mht"],
        steps=32,
        seed=19,
    )

    assert len(first) == 3
    rows = results_to_rows(first)
    assert {row["associator"] for row in rows} == {"gnn", "jpda", "mht"}
    for row in rows:
        assert row["scenario"] == "crossing_dense_5v5"
        assert isinstance(row["IDSW"], int)
        assert 0.0 <= float(row["continuity"]) <= 1.0
        assert float(row["runtime_ms"]) >= 0.0

    stable_first = [
        (
            result.associator,
            result.metrics["id_switch_count"],
            result.metrics["track_continuity"],
        )
        for result in first
    ]
    stable_second = [
        (
            result.associator,
            result.metrics["id_switch_count"],
            result.metrics["track_continuity"],
        )
        for result in second
    ]
    assert stable_first == stable_second


def test_optional_integrations_are_reported_without_importing_them() -> None:
    status = optional_dependency_status()
    names = {item.name for item in status}
    assert {"filterpy", "stonesoup"} <= names
