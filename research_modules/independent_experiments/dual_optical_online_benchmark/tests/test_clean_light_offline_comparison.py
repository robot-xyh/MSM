from __future__ import annotations

from dual_optical_online_benchmark.clean_light_offline_comparison import (
    _confirmed_only_publication,
    _delta_rows,
    _summarize,
)
from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    AssociationPublication,
)


def _row(route: str, level: str, correct: int, false: int) -> dict[str, object]:
    matches = correct + false
    return {
        "route_name": route,
        "corruption_level": level,
        "correct_match_count": correct,
        "false_association_count": false,
        "match_count": matches,
        "recall": correct / 20.0,
        "revolution_index": 3,
        "deadline_met": True,
        "end_to_end_ms": 10.0,
    }


def test_clean_light_summary_and_delta_use_relation_and_target_denominators() -> None:
    rows = [
        _row("gnn", "clean", 8, 2),
        _row("gnn", "clean", 6, 4),
        _row("gnn", "light", 5, 5),
        _row("gnn", "light", 3, 7),
    ]

    summary = _summarize(rows)
    clean, light = summary
    assert clean["association_precision"] == 0.7
    assert clean["target_coverage"] == 0.35
    assert clean["confirmation_phase_target_coverage"] == 0.35
    assert light["association_precision"] == 0.4
    assert light["target_coverage"] == 0.2

    delta = _delta_rows(summary)[0]
    assert round(float(delta["association_precision_delta"]), 10) == -0.3
    assert round(float(delta["target_coverage_delta"]), 10) == -0.15


def test_confirmed_only_policy_is_identical_for_every_route() -> None:
    publication = AssociationPublication(
        route_name="epipolar_mht",
        route_version="test",
        model_fingerprint="test",
        seed=1,
        corruption_level="clean",
        revolution_index=2,
        cutoff_timestamp=4.0,
        input_fingerprint="test",
        availability="available",
        matches=(
            AssociationMatch("A-1", "B-1", 0.9, "confirmed"),
            AssociationMatch("A-2", "B-2", 0.8, "fast_confirmed"),
            AssociationMatch("A-3", "B-3", 0.7, "tentative"),
            AssociationMatch("A-4", "B-4", 0.6, "pending"),
        ),
    )

    normalized, excluded = _confirmed_only_publication(publication)

    assert [match.decision_state for match in normalized.matches] == [
        "confirmed",
        "fast_confirmed",
    ]
    assert excluded == 2
    assert len(publication.matches) == 4
