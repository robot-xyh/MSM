"""Deterministic publication checks after learned partial assignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Sequence

import numpy as np
import torch


@dataclass(frozen=True)
class Match:
    index_a: int
    index_b: int
    score: float


@dataclass(frozen=True)
class NamedMatch:
    track_a_id: str
    track_b_id: str
    score: float


def extract_mutual_matches(
    assignment: torch.Tensor | np.ndarray,
    candidate_mask: torch.Tensor | np.ndarray,
    threshold: float,
) -> tuple[Match, ...]:
    """Apply dustbin-aware mutual-best, threshold, and one-to-one checks."""

    scores = (
        assignment.detach().cpu().numpy()
        if isinstance(assignment, torch.Tensor)
        else np.asarray(assignment)
    )
    mask = (
        candidate_mask.detach().cpu().numpy()
        if isinstance(candidate_mask, torch.Tensor)
        else np.asarray(candidate_mask)
    )
    if mask.ndim != 2 or mask.dtype != np.bool_:
        raise ValueError("candidate mask must be a boolean matrix")
    count_a, count_b = mask.shape
    if scores.shape != (count_a + 1, count_b + 1):
        raise ValueError("assignment must include one dustbin row and column")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("matching threshold must be in [0, 1]")
    if not np.all(np.isfinite(scores)):
        raise ValueError("assignment scores must be finite")
    if count_a == 0 or count_b == 0:
        return ()
    row_best = np.argmax(scores[:count_a, :], axis=1)
    column_best = np.argmax(scores[:, :count_b], axis=0)
    selected = []
    for row, column in enumerate(row_best):
        column = int(column)
        if column >= count_b:
            continue
        if int(column_best[column]) != row:
            continue
        score = float(scores[row, column])
        if not mask[row, column] or score < threshold:
            continue
        selected.append(Match(row, column, score))
    return tuple(selected)


class TemporalMatchConfirmer:
    """Require a pair in at least two of the latest three completed sweeps."""

    def __init__(self, window: int = 3, required_hits: int = 2) -> None:
        if window != 3 or required_hits != 2:
            raise ValueError("the route contract fixes temporal confirmation at 2-of-3")
        self.window = window
        self.required_hits = required_hits
        self._histories: dict[
            tuple[Hashable, str, str], list[tuple[int, bool, float]]
        ] = {}
        self._last_revolution: dict[Hashable, int] = {}

    def update(
        self,
        context: Hashable,
        revolution_index: int,
        matches: Sequence[NamedMatch],
    ) -> tuple[NamedMatch, ...]:
        if revolution_index < 1:
            raise ValueError("revolution index must be positive")
        previous = self._last_revolution.get(context, 0)
        if revolution_index <= previous:
            raise ValueError("revolution index must advance monotonically per context")
        present = {
            (match.track_a_id, match.track_b_id): float(match.score) for match in matches
        }
        if len(present) != len(matches):
            raise ValueError("one pair cannot appear twice in one revolution")
        keys = {
            (track_a, track_b)
            for stored_context, track_a, track_b in self._histories
            if stored_context == context
        } | set(present)
        confirmed = []
        for track_a, track_b in sorted(keys):
            key = (context, track_a, track_b)
            history = list(self._histories.get(key, ()))
            last = history[-1][0] if history else previous
            for missing_revolution in range(last + 1, revolution_index):
                history.append((missing_revolution, False, 0.0))
            score = present.get((track_a, track_b), 0.0)
            history.append((revolution_index, (track_a, track_b) in present, score))
            history = history[-self.window :]
            self._histories[key] = history
            hits = [item for item in history if item[1]]
            if (
                (track_a, track_b) in present
                and revolution_index >= self.window
                and len(hits) >= self.required_hits
            ):
                confirmed.append(NamedMatch(track_a, track_b, float(hits[-1][2])))
        stale = [
            key
            for key, history in self._histories.items()
            if key[0] == context
            and history
            and not any(item[1] for item in history)
        ]
        for key in stale:
            del self._histories[key]
        self._last_revolution[context] = revolution_index
        return tuple(confirmed)

    def reset(self, context: Hashable | None = None) -> None:
        if context is None:
            self._histories.clear()
            self._last_revolution.clear()
            return
        self._histories = {
            key: value for key, value in self._histories.items() if key[0] != context
        }
        self._last_revolution.pop(context, None)
