"""Metrics recorder for offline tracking and association evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import sqrt
from typing import Iterable

from .models import AssociationLogEntry, AssociationResult


@dataclass(slots=True)
class MetricsRecorder:
    """Records identity, continuity, duplicate assignment, and RMSE metrics."""

    id_switch_count: int = 0
    duplicate_assignment_count: int = 0
    frame_count: int = 0
    last_truth_to_track: dict[str, str] = field(default_factory=dict)
    truth_frame_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    truth_assigned_frame_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    truth_identity_stable_frame_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    confusion_matrix: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    squared_errors: list[float] = field(default_factory=list)
    association_logs: list[AssociationLogEntry] = field(default_factory=list)
    runtime_seconds_by_associator: dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    def record_frame(
        self,
        timestamp: float,
        truth_ids_present: Iterable[str],
        association_result: AssociationResult,
        assignments: list[tuple[str, str, float | None]],
        runtime_seconds: float,
    ) -> None:
        """Record one tracker frame.

        `assignments` contains `(truth_id, track_id, squared_error)` tuples.
        False alarms are omitted by the caller because they have no truth id.
        """

        del timestamp
        self.frame_count += 1
        truth_ids = {truth_id for truth_id in truth_ids_present if truth_id is not None}
        for truth_id in truth_ids:
            self.truth_frame_count[truth_id] += 1

        matched_detection_ids = [
            pair.detection_id for pair in association_result.matched_pairs
        ]
        matched_track_ids = [pair.track_id for pair in association_result.matched_pairs]
        self.duplicate_assignment_count += _duplicate_count(matched_detection_ids)
        self.duplicate_assignment_count += _duplicate_count(matched_track_ids)

        tracks_by_truth: dict[str, list[str]] = defaultdict(list)
        for truth_id, track_id, squared_error in assignments:
            if truth_id is None:
                continue
            self.confusion_matrix[truth_id][track_id] += 1
            tracks_by_truth[truth_id].append(track_id)
            if squared_error is not None:
                self.squared_errors.append(float(squared_error))

        for truth_id, track_ids in tracks_by_truth.items():
            if track_ids:
                self.truth_assigned_frame_count[truth_id] += 1
            unique_tracks = set(track_ids)
            if len(unique_tracks) > 1:
                self.duplicate_assignment_count += len(unique_tracks) - 1
            representative_track_id = _representative_track_id(track_ids)
            if representative_track_id is None:
                continue
            previous_track_id = self.last_truth_to_track.get(truth_id)
            if previous_track_id is not None and previous_track_id != representative_track_id:
                self.id_switch_count += 1
            else:
                self.truth_identity_stable_frame_count[truth_id] += 1
            self.last_truth_to_track[truth_id] = representative_track_id

        log_entry = AssociationLogEntry(
            timestamp=association_result.timestamp,
            associator_type=association_result.associator_type,
            matched_pairs=list(association_result.matched_pairs),
            unmatched_track_ids=list(association_result.unmatched_track_ids),
            unmatched_detection_ids=list(association_result.unmatched_detection_ids),
            ambiguity_score=association_result.ambiguity_score,
            runtime_seconds=runtime_seconds,
            metadata=association_result.metadata,
        )
        self.association_logs.append(log_entry)
        self.runtime_seconds_by_associator[association_result.associator_type] += (
            runtime_seconds
        )

    @property
    def track_continuity(self) -> float:
        return self.identity_continuity

    @property
    def coverage_continuity(self) -> float:
        if not self.truth_frame_count:
            return 0.0
        ratios = []
        for truth_id, total_frames in self.truth_frame_count.items():
            if total_frames <= 0:
                continue
            assigned = self.truth_assigned_frame_count.get(truth_id, 0)
            ratios.append(assigned / total_frames)
        return float(sum(ratios) / len(ratios)) if ratios else 0.0

    @property
    def identity_continuity(self) -> float:
        if not self.truth_frame_count:
            return 0.0
        ratios = []
        for truth_id, total_frames in self.truth_frame_count.items():
            if total_frames <= 0:
                continue
            stable = self.truth_identity_stable_frame_count.get(truth_id, 0)
            ratios.append(stable / total_frames)
        return float(sum(ratios) / len(ratios)) if ratios else 0.0

    @property
    def rmse(self) -> float:
        if not self.squared_errors:
            return 0.0
        return float(sqrt(sum(self.squared_errors) / len(self.squared_errors)))

    def confusion_matrix_as_dict(self) -> dict[str, dict[str, int]]:
        return {
            truth_id: dict(track_counts)
            for truth_id, track_counts in sorted(self.confusion_matrix.items())
        }

    def summary(self) -> dict[str, object]:
        return {
            "frame_count": self.frame_count,
            "id_switch_count": self.id_switch_count,
            "track_continuity": self.track_continuity,
            "coverage_continuity": self.coverage_continuity,
            "identity_continuity": self.identity_continuity,
            "duplicate_assignment_count": self.duplicate_assignment_count,
            "rmse": self.rmse,
            "assignment_count": int(sum(sum(c.values()) for c in self.confusion_matrix.values())),
            "runtime_seconds_by_associator": dict(self.runtime_seconds_by_associator),
            "confusion_matrix": self.confusion_matrix_as_dict(),
        }


def _duplicate_count(items: list[str]) -> int:
    counts = Counter(items)
    return int(sum(count - 1 for count in counts.values() if count > 1))


def _representative_track_id(track_ids: list[str]) -> str | None:
    if not track_ids:
        return None
    counts = Counter(track_ids)
    return sorted(counts, key=lambda track_id: (-counts[track_id], track_id))[0]
