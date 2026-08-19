"""Association and candidate-edge metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import numpy as np

from .assignment import AssignmentResult
from .schema import GraphLabels, OnlineGraph


def average_precision(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    positives = int(np.sum(labels > 0.5))
    if positives == 0:
        return 0.0
    order = np.argsort(-scores, kind="mergesort")
    ordered = labels[order] > 0.5
    true_positive = np.cumsum(ordered)
    precision = true_positive / np.arange(1, len(ordered) + 1)
    return float(np.sum(precision[ordered]) / positives)


@dataclass(frozen=True)
class AssociationMetrics:
    selected_count: int
    correct_count: int
    false_association_count: int
    precision: float
    recall: float
    f1: float
    duplicate_track_assignment_count: int
    duplicate_identity_match_count: int
    candidate_identity_recall: float
    failure_reasons: Mapping[str, int]

    def to_dict(self) -> dict[str, object]:
        values = asdict(self)
        values["failure_reasons"] = dict(self.failure_reasons)
        return values


def evaluate_assignment(
    graph: OnlineGraph,
    labels: GraphLabels,
    result: AssignmentResult,
) -> AssociationMetrics:
    expected = set(labels.expected_identities)
    selected_identities: list[str] = []
    correct_count = 0
    false_count = 0
    selected_false_track = 0
    for pair in result.selected_pairs:
        identity_a = labels.identity_a[pair.index_a]
        identity_b = labels.identity_b[pair.index_b]
        if identity_a is not None and identity_a == identity_b:
            correct_count += 1
            selected_identities.append(identity_a)
        else:
            false_count += 1
            if identity_a is None or identity_b is None:
                selected_false_track += 1
    unique_correct = set(selected_identities)
    duplicate_identity = len(selected_identities) - len(unique_correct)
    precision = correct_count / len(result.selected_pairs) if result.selected_pairs else 0.0
    recall = len(unique_correct & expected) / len(expected) if expected else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0

    candidate_identities = {
        labels.identity_a[int(index_a)]
        for edge_label, (index_a, index_b) in zip(labels.edge_labels, graph.edge_index.T)
        if edge_label > 0.5
        and labels.identity_a[int(index_a)] is not None
        and labels.identity_a[int(index_a)] == labels.identity_b[int(index_b)]
    }
    candidate_recall = len(candidate_identities & expected) / len(expected) if expected else 0.0
    present_a = {identity for identity in labels.identity_a if identity is not None}
    present_b = {identity for identity in labels.identity_b if identity is not None}
    present_both = present_a & present_b
    failures = {
        "missing_stable_track": len(expected - present_both),
        "geometry_gate_rejected": len((expected & present_both) - candidate_identities),
        "assignment_conflict": len((candidate_identities & expected) - unique_correct),
        "false_association": false_count,
        "selected_false_track": selected_false_track,
        "duplicate_identity": duplicate_identity,
    }
    return AssociationMetrics(
        selected_count=len(result.selected_pairs),
        correct_count=correct_count,
        false_association_count=false_count,
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        duplicate_track_assignment_count=result.duplicate_track_assignment_count,
        duplicate_identity_match_count=duplicate_identity,
        candidate_identity_recall=float(candidate_recall),
        failure_reasons=failures,
    )
