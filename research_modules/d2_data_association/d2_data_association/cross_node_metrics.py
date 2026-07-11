"""Metrics for cross-node canonical registration.

Online transport/registry metrics are truth-free.  Truth-dependent clustering
metrics live in ``OfflineCrossNodeMetricsEvaluator`` and require an explicit,
separate mapping supplied by an offline replay or evaluation harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Mapping

import numpy as np

from .cross_node_models import CrossNodeAssociationResult, SourceTrackKey


@dataclass(slots=True)
class CrossNodeRegistryMetrics:
    """Truth-free counters and latency distributions for the online registry."""

    cross_node_id_switch_count: int = 0
    duplicate_payload_rejection_count: int = 0
    _transport_latencies: list[float] = field(default_factory=list)
    _queue_latencies: list[float] = field(default_factory=list)
    _fusion_latencies: list[float] = field(default_factory=list)

    def record_accepted_payload(
        self,
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
        fusion_timestamp: float,
    ) -> None:
        self._transport_latencies.append(arrival_timestamp - measurement_timestamp)
        self._queue_latencies.append(fusion_timestamp - arrival_timestamp)
        self._fusion_latencies.append(fusion_timestamp - measurement_timestamp)

    def record_id_switch(self) -> None:
        self.cross_node_id_switch_count += 1

    def record_duplicate_rejection(self) -> None:
        self.duplicate_payload_rejection_count += 1

    def summary(self) -> dict[str, object]:
        return {
            "cross_node_id_switch_count": self.cross_node_id_switch_count,
            "duplicate_payload_rejection_count": (
                self.duplicate_payload_rejection_count
            ),
            "fusion_latency_summary": _latency_summary(self._fusion_latencies),
            "transport_latency_summary": _latency_summary(
                self._transport_latencies
            ),
            "registry_queue_latency_summary": _latency_summary(
                self._queue_latencies
            ),
            "truth_metrics_available": False,
        }


@dataclass(slots=True)
class OfflineCrossNodeMetricsEvaluator:
    """Evaluate canonical clustering without exposing truth to online logic."""

    _true_positive_pairs: int = 0
    _false_positive_pairs: int = 0
    _false_negative_pairs: int = 0
    _canonical_duplicate_count: int = 0
    _cross_node_id_switch_count: int = 0
    _evaluated_snapshots: int = 0
    _truth_representative_by_target: dict[str, str] = field(default_factory=dict)

    def record_snapshot(
        self,
        result: CrossNodeAssociationResult,
        truth_by_source_track: Mapping[SourceTrackKey, str],
    ) -> None:
        """Score one registry snapshot using offline-only source-track labels."""

        labeled_binding: dict[SourceTrackKey, tuple[str, str]] = {}
        for canonical_id, source_keys in result.canonical_bindings.items():
            for source_key in source_keys:
                truth_id = truth_by_source_track.get(source_key)
                if truth_id is not None:
                    labeled_binding[source_key] = (canonical_id, str(truth_id))
        if not labeled_binding:
            return

        predicted_pairs: set[tuple[SourceTrackKey, SourceTrackKey]] = set()
        for source_keys in result.canonical_bindings.values():
            labeled_keys = [key for key in source_keys if key in labeled_binding]
            predicted_pairs.update(_cross_node_pairs(labeled_keys))

        truth_groups: dict[str, list[SourceTrackKey]] = {}
        canonical_groups: dict[str, set[str]] = {}
        canonical_votes: dict[str, dict[str, int]] = {}
        for source_key, (canonical_id, truth_id) in labeled_binding.items():
            truth_groups.setdefault(truth_id, []).append(source_key)
            canonical_groups.setdefault(truth_id, set()).add(canonical_id)
            votes = canonical_votes.setdefault(truth_id, {})
            votes[canonical_id] = votes.get(canonical_id, 0) + 1

        true_pairs: set[tuple[SourceTrackKey, SourceTrackKey]] = set()
        for source_keys in truth_groups.values():
            true_pairs.update(_cross_node_pairs(source_keys))

        self._true_positive_pairs += len(predicted_pairs & true_pairs)
        self._false_positive_pairs += len(predicted_pairs - true_pairs)
        self._false_negative_pairs += len(true_pairs - predicted_pairs)
        self._canonical_duplicate_count += sum(
            max(0, len(canonical_ids) - 1)
            for canonical_ids in canonical_groups.values()
        )

        for truth_id, votes in canonical_votes.items():
            representative = min(
                votes,
                key=lambda canonical_id: (-votes[canonical_id], canonical_id),
            )
            previous = self._truth_representative_by_target.get(truth_id)
            if previous is not None and previous != representative:
                self._cross_node_id_switch_count += 1
            self._truth_representative_by_target[truth_id] = representative
        self._evaluated_snapshots += 1

    def summary(self) -> dict[str, object]:
        precision_denominator = self._true_positive_pairs + self._false_positive_pairs
        recall_denominator = self._true_positive_pairs + self._false_negative_pairs
        return {
            "truth_metrics_available": self._evaluated_snapshots > 0,
            "evaluated_snapshot_count": self._evaluated_snapshots,
            "cross_node_id_switch_count": self._cross_node_id_switch_count,
            "canonical_duplicate_count": self._canonical_duplicate_count,
            "association_true_positive_pair_count": self._true_positive_pairs,
            "association_false_positive_pair_count": self._false_positive_pairs,
            "association_false_negative_pair_count": self._false_negative_pairs,
            "association_precision": (
                self._true_positive_pairs / precision_denominator
                if precision_denominator
                else 0.0
            ),
            "association_recall": (
                self._true_positive_pairs / recall_denominator
                if recall_denominator
                else 0.0
            ),
        }


def _cross_node_pairs(
    source_keys: list[SourceTrackKey],
) -> set[tuple[SourceTrackKey, SourceTrackKey]]:
    return {
        tuple(sorted((left, right)))
        for left, right in combinations(source_keys, 2)
        if left.source_node_id != right.source_node_id
    }


def _latency_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean_seconds": None,
            "min_seconds": None,
            "max_seconds": None,
            "p50_seconds": None,
            "p95_seconds": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "count": len(values),
        "mean_seconds": float(np.mean(array)),
        "min_seconds": float(np.min(array)),
        "max_seconds": float(np.max(array)),
        "p50_seconds": float(np.percentile(array, 50.0)),
        "p95_seconds": float(np.percentile(array, 95.0)),
    }
