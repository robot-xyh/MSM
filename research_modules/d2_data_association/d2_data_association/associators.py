"""Data association algorithms for offline multi-target tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import count
from math import exp, log
from typing import Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment

from .gating import LARGE_COST, ambiguity_score_from_costs, build_gated_cost_matrix
from .models import AssociationResult, Detection, GlobalTrack, MatchedPair, RejectedPair


class DataAssociator(ABC):
    """Abstract data association interface."""

    @abstractmethod
    def associate(
        self,
        tracks: Iterable[GlobalTrack],
        detections: Iterable[Detection],
        timestamp: float,
    ) -> AssociationResult:
        """Associate existing tracks to detections for one frame."""


@dataclass(slots=True)
class GNNHungarianAssociator(DataAssociator):
    """Global nearest-neighbor association solved with SciPy Hungarian."""

    gate_threshold: float = 9.21
    feature_weight: float = 1.0
    large_cost: float = LARGE_COST

    def associate(
        self,
        tracks: Iterable[GlobalTrack],
        detections: Iterable[Detection],
        timestamp: float,
    ) -> AssociationResult:
        track_list = list(tracks)
        detection_list = list(detections)
        gated = build_gated_cost_matrix(
            track_list,
            detection_list,
            self.gate_threshold,
            self.large_cost,
            self.feature_weight,
        )

        matched_pairs: list[MatchedPair] = []
        matched_track_rows: set[int] = set()
        matched_detection_cols: set[int] = set()
        rejected = list(gated.rejected_pairs)

        if track_list and detection_list:
            row_indices, col_indices = linear_sum_assignment(gated.cost_matrix)
            for row, col in zip(row_indices, col_indices, strict=True):
                cost = float(gated.cost_matrix[row, col])
                distance = float(gated.distance_matrix[row, col])
                if cost >= self.large_cost or distance > self.gate_threshold:
                    rejected.append(
                        RejectedPair(
                            track_id=track_list[row].global_track_id,
                            detection_id=detection_list[col].detection_id,
                            reason="assignment_above_gate",
                            value=distance,
                        )
                    )
                    continue
                matched_pairs.append(
                    MatchedPair(
                        track_id=track_list[row].global_track_id,
                        detection_id=detection_list[col].detection_id,
                        cost=cost,
                        probability=1.0,
                    )
                )
                matched_track_rows.add(row)
                matched_detection_cols.add(col)

        unmatched_track_ids = [
            track.global_track_id
            for row, track in enumerate(track_list)
            if row not in matched_track_rows
        ]
        unmatched_detection_ids = [
            detection.detection_id
            for col, detection in enumerate(detection_list)
            if col not in matched_detection_cols
        ]
        return AssociationResult(
            timestamp=float(timestamp),
            matched_pairs=matched_pairs,
            unmatched_track_ids=unmatched_track_ids,
            unmatched_detection_ids=unmatched_detection_ids,
            ambiguity_score=ambiguity_score_from_costs(
                gated.cost_matrix, self.large_cost
            ),
            associator_type="GNNHungarianAssociator",
            rejected_pairs=rejected,
            cost_matrix=gated.cost_matrix,
            distance_matrix=gated.distance_matrix,
            metadata={
                "gate_threshold": self.gate_threshold,
                "feature_weight": self.feature_weight,
                "solver": "scipy.optimize.linear_sum_assignment",
                "candidate_counts_by_track": gated.candidate_counts_by_track,
                "candidate_counts_by_detection": gated.candidate_counts_by_detection,
            },
        )


@dataclass(slots=True)
class _JointHypothesis:
    assignments: tuple[tuple[int, int], ...]
    log_likelihood: float
    unmatched_tracks: tuple[int, ...]
    unmatched_detections: tuple[int, ...]


@dataclass(slots=True)
class JPDAAssociator(DataAssociator):
    """Simplified executable JPDA associator for small offline scenarios."""

    gate_threshold: float = 9.21
    feature_weight: float = 1.0
    detection_probability: float = 0.90
    clutter_density: float = 1.0e-3
    min_marginal_probability: float = 0.35
    max_candidates_per_track: int = 4
    max_joint_hypotheses: int = 4096
    large_cost: float = LARGE_COST

    def associate(
        self,
        tracks: Iterable[GlobalTrack],
        detections: Iterable[Detection],
        timestamp: float,
    ) -> AssociationResult:
        track_list = list(tracks)
        detection_list = list(detections)
        gated = build_gated_cost_matrix(
            track_list,
            detection_list,
            self.gate_threshold,
            self.large_cost,
            self.feature_weight,
        )

        if not track_list:
            return AssociationResult(
                timestamp=float(timestamp),
                matched_pairs=[],
                unmatched_track_ids=[],
                unmatched_detection_ids=[
                    detection.detection_id for detection in detection_list
                ],
                ambiguity_score=0.0,
                associator_type="JPDAAssociator",
                rejected_pairs=gated.rejected_pairs,
                cost_matrix=gated.cost_matrix,
                distance_matrix=gated.distance_matrix,
                metadata={"joint_hypothesis_count": 1, "truncated": False},
            )

        candidates = _candidate_indices_by_track(
            gated.cost_matrix, self.large_cost, self.max_candidates_per_track
        )
        raw_assignments, truncated = _enumerate_assignments(
            candidates,
            detection_count=len(detection_list),
            max_assignments=self.max_joint_hypotheses,
        )
        hypotheses = [
            self._score_hypothesis(
                assignments=tuple(sorted(assignment)),
                track_count=len(track_list),
                detection_count=len(detection_list),
                distance_matrix=gated.distance_matrix,
                cost_matrix=gated.cost_matrix,
            )
            for assignment in raw_assignments
        ]
        if not hypotheses:
            hypotheses = [
                self._score_hypothesis(
                    assignments=tuple(),
                    track_count=len(track_list),
                    detection_count=len(detection_list),
                    distance_matrix=gated.distance_matrix,
                    cost_matrix=gated.cost_matrix,
                )
            ]

        probabilities = _normalized_probabilities(
            [hypothesis.log_likelihood for hypothesis in hypotheses]
        )
        marginal = np.zeros((len(track_list), len(detection_list)), dtype=float)
        for hypothesis, probability in zip(hypotheses, probabilities, strict=True):
            for row, col in hypothesis.assignments:
                marginal[row, col] += probability

        matched_pairs, matched_rows, matched_cols = self._select_marginal_matches(
            track_list, detection_list, gated.cost_matrix, marginal
        )
        unmatched_track_ids = [
            track.global_track_id
            for row, track in enumerate(track_list)
            if row not in matched_rows
        ]
        unmatched_detection_ids = [
            detection.detection_id
            for col, detection in enumerate(detection_list)
            if col not in matched_cols
        ]

        return AssociationResult(
            timestamp=float(timestamp),
            matched_pairs=matched_pairs,
            unmatched_track_ids=unmatched_track_ids,
            unmatched_detection_ids=unmatched_detection_ids,
            ambiguity_score=_jpda_entropy_ambiguity(marginal),
            associator_type="JPDAAssociator",
            rejected_pairs=gated.rejected_pairs,
            cost_matrix=gated.cost_matrix,
            distance_matrix=gated.distance_matrix,
            metadata={
                "gate_threshold": self.gate_threshold,
                "feature_weight": self.feature_weight,
                "detection_probability": self.detection_probability,
                "clutter_density": self.clutter_density,
                "min_marginal_probability": self.min_marginal_probability,
                "joint_hypothesis_count": len(hypotheses),
                "truncated": truncated,
                "marginal_probabilities": marginal,
                "candidate_counts_by_track": gated.candidate_counts_by_track,
                "candidate_counts_by_detection": gated.candidate_counts_by_detection,
            },
        )

    def _score_hypothesis(
        self,
        assignments: tuple[tuple[int, int], ...],
        track_count: int,
        detection_count: int,
        distance_matrix: np.ndarray,
        cost_matrix: np.ndarray,
    ) -> _JointHypothesis:
        matched_tracks = {row for row, _ in assignments}
        matched_detections = {col for _, col in assignments}
        unmatched_tracks = tuple(
            row for row in range(track_count) if row not in matched_tracks
        )
        unmatched_detections = tuple(
            col for col in range(detection_count) if col not in matched_detections
        )
        epsilon = 1.0e-12
        log_likelihood = 0.0
        for row, col in assignments:
            log_likelihood += log(max(self.detection_probability, epsilon))
            log_likelihood += -0.5 * float(cost_matrix[row, col])
        log_likelihood += len(unmatched_tracks) * log(
            max(1.0 - self.detection_probability, epsilon)
        )
        log_likelihood += len(unmatched_detections) * log(
            max(self.clutter_density, epsilon)
        )
        return _JointHypothesis(
            assignments=assignments,
            log_likelihood=log_likelihood,
            unmatched_tracks=unmatched_tracks,
            unmatched_detections=unmatched_detections,
        )

    def _select_marginal_matches(
        self,
        tracks: list[GlobalTrack],
        detections: list[Detection],
        distance_matrix: np.ndarray,
        marginal: np.ndarray,
    ) -> tuple[list[MatchedPair], set[int], set[int]]:
        flat: list[tuple[float, float, int, int]] = []
        for row in range(marginal.shape[0]):
            for col in range(marginal.shape[1]):
                probability = float(marginal[row, col])
                if probability >= self.min_marginal_probability:
                    flat.append((probability, -float(distance_matrix[row, col]), row, col))
        flat.sort(reverse=True)

        matched_pairs: list[MatchedPair] = []
        matched_rows: set[int] = set()
        matched_cols: set[int] = set()
        for probability, negative_distance, row, col in flat:
            if row in matched_rows or col in matched_cols:
                continue
            distance = -negative_distance
            matched_pairs.append(
                MatchedPair(
                    track_id=tracks[row].global_track_id,
                    detection_id=detections[col].detection_id,
                    cost=distance,
                    probability=probability,
                )
            )
            matched_rows.add(row)
            matched_cols.add(col)
        return matched_pairs, matched_rows, matched_cols


@dataclass(slots=True)
class _MHTBranch:
    score: float
    history: tuple[tuple[tuple[str, str], ...], ...] = field(default_factory=tuple)
    branch_id: int = 0


@dataclass(slots=True)
class MHTAssociator(DataAssociator):
    """Bounded MHT-compatible research placeholder."""

    gate_threshold: float = 9.21
    feature_weight: float = 1.0
    max_hypotheses: int = 16
    max_history: int = 5
    max_candidates_per_track: int = 3
    max_generated_assignments: int = 512
    missed_track_penalty: float = 6.0
    false_alarm_penalty: float = 4.0
    large_cost: float = LARGE_COST
    _branches: list[_MHTBranch] = field(default_factory=list, init=False)
    _branch_counter: count = field(default_factory=count, init=False)

    def associate(
        self,
        tracks: Iterable[GlobalTrack],
        detections: Iterable[Detection],
        timestamp: float,
    ) -> AssociationResult:
        track_list = list(tracks)
        detection_list = list(detections)
        gated = build_gated_cost_matrix(
            track_list,
            detection_list,
            self.gate_threshold,
            self.large_cost,
            self.feature_weight,
        )

        candidates = _candidate_indices_by_track(
            gated.cost_matrix, self.large_cost, self.max_candidates_per_track
        )
        raw_assignments, truncated = _enumerate_assignments(
            candidates,
            detection_count=len(detection_list),
            max_assignments=self.max_generated_assignments,
        )
        if not raw_assignments:
            raw_assignments = [tuple()]

        previous_branches = self._branches or [
            _MHTBranch(score=0.0, history=tuple(), branch_id=next(self._branch_counter))
        ]
        expanded: list[_MHTBranch] = []
        for branch in previous_branches:
            for assignment in raw_assignments:
                pairs = tuple(
                    sorted(
                        (
                            track_list[row].global_track_id,
                            detection_list[col].detection_id,
                        )
                        for row, col in assignment
                    )
                )
                assigned_tracks = {row for row, _ in assignment}
                assigned_detections = {col for _, col in assignment}
                missed = len(track_list) - len(assigned_tracks)
                false_alarms = len(detection_list) - len(assigned_detections)
                score = branch.score
                score += sum(
                    float(gated.cost_matrix[row, col]) for row, col in assignment
                )
                score += missed * self.missed_track_penalty
                score += false_alarms * self.false_alarm_penalty
                history = (branch.history + (pairs,))[-self.max_history :]
                expanded.append(
                    _MHTBranch(
                        score=score,
                        history=history,
                        branch_id=next(self._branch_counter),
                    )
                )

        expanded.sort(key=lambda item: (item.score, item.branch_id))
        self._branches = expanded[: self.max_hypotheses]
        best = self._branches[0] if self._branches else _MHTBranch(score=0.0)
        current_pairs = best.history[-1] if best.history else tuple()

        matched_pairs: list[MatchedPair] = []
        matched_track_ids: set[str] = set()
        matched_detection_ids: set[str] = set()
        distance_by_pair = {
            (track.global_track_id, detection.detection_id): float(
                gated.distance_matrix[row, col]
                + gated.feature_cost_matrix[row, col] * self.feature_weight
            )
            for row, track in enumerate(track_list)
            for col, detection in enumerate(detection_list)
        }
        for track_id, detection_id in current_pairs:
            distance = distance_by_pair[(track_id, detection_id)]
            matched_pairs.append(
                MatchedPair(
                    track_id=track_id,
                    detection_id=detection_id,
                    cost=distance,
                    probability=exp(-0.5 * distance),
                )
            )
            matched_track_ids.add(track_id)
            matched_detection_ids.add(detection_id)

        return AssociationResult(
            timestamp=float(timestamp),
            matched_pairs=matched_pairs,
            unmatched_track_ids=[
                track.global_track_id
                for track in track_list
                if track.global_track_id not in matched_track_ids
            ],
            unmatched_detection_ids=[
                detection.detection_id
                for detection in detection_list
                if detection.detection_id not in matched_detection_ids
            ],
            ambiguity_score=ambiguity_score_from_costs(
                gated.cost_matrix, self.large_cost
            ),
            associator_type="MHTAssociator",
            rejected_pairs=gated.rejected_pairs,
            cost_matrix=gated.cost_matrix,
            distance_matrix=gated.distance_matrix,
            metadata={
                "gate_threshold": self.gate_threshold,
                "feature_weight": self.feature_weight,
                "branch_count": len(self._branches),
                "max_hypotheses": self.max_hypotheses,
                "max_history": self.max_history,
                "generated_assignment_count": len(raw_assignments),
                "truncated": truncated,
                "best_branch_score": best.score,
                "candidate_counts_by_track": gated.candidate_counts_by_track,
                "candidate_counts_by_detection": gated.candidate_counts_by_detection,
            },
        )


def _candidate_indices_by_track(
    cost_matrix: np.ndarray,
    large_cost: float,
    max_candidates_per_track: int,
) -> list[list[int]]:
    candidates: list[list[int]] = []
    for row in range(cost_matrix.shape[0]):
        valid = np.where(cost_matrix[row] < large_cost)[0]
        valid = sorted(valid.tolist(), key=lambda col: float(cost_matrix[row, col]))
        candidates.append(valid[:max_candidates_per_track])
    return candidates


def _enumerate_assignments(
    candidates_by_track: list[list[int]],
    detection_count: int,
    max_assignments: int,
) -> tuple[list[tuple[tuple[int, int], ...]], bool]:
    del detection_count
    assignments: list[tuple[tuple[int, int], ...]] = []
    truncated = False

    def visit(
        row: int,
        used_detections: set[int],
        current: list[tuple[int, int]],
    ) -> None:
        nonlocal truncated
        if len(assignments) >= max_assignments:
            truncated = True
            return
        if row >= len(candidates_by_track):
            assignments.append(tuple(current))
            return

        for col in candidates_by_track[row]:
            if col in used_detections:
                continue
            current.append((row, col))
            used_detections.add(col)
            visit(row + 1, used_detections, current)
            used_detections.remove(col)
            current.pop()
            if truncated:
                return
        visit(row + 1, used_detections, current)

    visit(0, set(), [])
    return assignments, truncated


def _normalized_probabilities(log_likelihoods: list[float]) -> list[float]:
    if not log_likelihoods:
        return []
    max_log = max(log_likelihoods)
    weights = [exp(value - max_log) for value in log_likelihoods]
    total = sum(weights)
    if total <= 0.0:
        return [1.0 / len(weights)] * len(weights)
    return [weight / total for weight in weights]


def _jpda_entropy_ambiguity(marginal: np.ndarray) -> float:
    if marginal.size == 0:
        return 0.0
    scores: list[float] = []
    for row in marginal:
        miss_probability = max(1.0 - float(np.sum(row)), 0.0)
        probabilities = [float(value) for value in row if value > 1.0e-12]
        if miss_probability > 1.0e-12:
            probabilities.append(miss_probability)
        if len(probabilities) <= 1:
            scores.append(0.0)
            continue
        entropy = -sum(probability * log(probability) for probability in probabilities)
        scores.append(float(entropy / log(len(probabilities))))
    return float(np.mean(scores)) if scores else 0.0
