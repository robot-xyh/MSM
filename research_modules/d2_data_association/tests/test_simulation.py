from __future__ import annotations

from d2_data_association.compat import optional_dependency_status
from d2_data_association.simulation import format_markdown_table, run_benchmark


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


def test_optional_integrations_are_reported_without_importing_them() -> None:
    status = optional_dependency_status()
    names = {item.name for item in status}
    assert {"filterpy", "stonesoup"} <= names
