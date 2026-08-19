from __future__ import annotations

import numpy as np
import pytest

from research_modules.independent_experiments.dual_optical_track_superglue.matching import (
    NamedMatch,
    TemporalMatchConfirmer,
    extract_mutual_matches,
)


def test_mutual_best_threshold_and_one_to_one_output() -> None:
    assignment = np.asarray(
        [
            [0.85, 0.05, 0.10],
            [0.20, 0.55, 0.25],
            [0.05, 0.40, 0.0],
        ],
        dtype=float,
    )
    mask = np.asarray([[True, False], [True, True]], dtype=bool)
    matches = extract_mutual_matches(assignment, mask, threshold=0.5)
    assert [(match.index_a, match.index_b) for match in matches] == [(0, 0), (1, 1)]
    assert len({match.index_a for match in matches}) == len(matches)
    assert len({match.index_b for match in matches}) == len(matches)


def test_temporal_confirmation_requires_two_of_full_three() -> None:
    confirmer = TemporalMatchConfirmer()
    context = (7, "medium")
    pair = NamedMatch("A-1", "B-1", 0.8)
    assert confirmer.update(context, 1, (pair,)) == ()
    assert confirmer.update(context, 2, ()) == ()
    confirmed = confirmer.update(context, 3, (NamedMatch("A-1", "B-1", 0.9),))
    assert confirmed == (NamedMatch("A-1", "B-1", 0.9),)
    assert confirmer.update(context, 4, ()) == ()


def test_temporal_confirmation_rejects_non_monotonic_revolution() -> None:
    confirmer = TemporalMatchConfirmer()
    confirmer.update("episode", 1, ())
    with pytest.raises(ValueError, match="monotonically"):
        confirmer.update("episode", 1, ())


def test_temporal_confirmation_does_not_publish_a_currently_absent_pair() -> None:
    confirmer = TemporalMatchConfirmer()
    pair = NamedMatch("A-2", "B-2", 0.8)
    assert confirmer.update("episode", 1, (pair,)) == ()
    assert confirmer.update("episode", 2, (pair,)) == ()
    assert confirmer.update("episode", 3, ()) == ()
