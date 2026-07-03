"""Metrics recorder for offline tracking and association evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import sqrt
from typing import Iterable

from .models import AssociationLogEntry, AssociationResult, AssociationRiskSummary


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
    d5_disagreement_count: int = 0
    risk_frame_count: int = 0
    association_ambiguity_sum: float = 0.0
    covariance_overlap_rate_sum: float = 0.0
    latest_association_ambiguity: float = 0.0
    latest_duplicate_track_risk: float = 0.0
    latest_covariance_overlap_rate: float = 0.0
    max_duplicate_track_risk: float = 0.0
    max_covariance_overlap_rate: float = 0.0
    source_node_ids: set[str] = field(default_factory=set)
    link_types: set[str] = field(default_factory=set)

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

        risk_summary = _risk_summary_from_result(association_result)
        self._record_risk_summary(risk_summary)

        log_entry = AssociationLogEntry(
            timestamp=association_result.timestamp,
            associator_type=association_result.associator_type,
            matched_pairs=list(association_result.matched_pairs),
            unmatched_track_ids=list(association_result.unmatched_track_ids),
            unmatched_detection_ids=list(association_result.unmatched_detection_ids),
            ambiguity_score=association_result.ambiguity_score,
            runtime_seconds=runtime_seconds,
            metadata=association_result.metadata,
            source_node_id=association_result.source_node_id,
            link_type=association_result.link_type,
            risk_summary=risk_summary,
        )
        self.association_logs.append(log_entry)
        self.runtime_seconds_by_associator[association_result.associator_type] += (
            runtime_seconds
        )

    def _record_risk_summary(self, risk_summary: AssociationRiskSummary) -> None:
        self.risk_frame_count += 1
        self.d5_disagreement_count += risk_summary.d5_disagreement_count
        self.latest_association_ambiguity = risk_summary.association_ambiguity
        self.latest_duplicate_track_risk = risk_summary.duplicate_track_risk
        self.latest_covariance_overlap_rate = risk_summary.covariance_overlap_rate
        self.association_ambiguity_sum += risk_summary.association_ambiguity
        self.covariance_overlap_rate_sum += risk_summary.covariance_overlap_rate
        self.max_duplicate_track_risk = max(
            self.max_duplicate_track_risk, risk_summary.duplicate_track_risk
        )
        self.max_covariance_overlap_rate = max(
            self.max_covariance_overlap_rate, risk_summary.covariance_overlap_rate
        )
        if risk_summary.source_node_id:
            self.source_node_ids.add(risk_summary.source_node_id)
        if risk_summary.link_type:
            self.link_types.add(risk_summary.link_type)

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
        mean_association_ambiguity = (
            self.association_ambiguity_sum / self.risk_frame_count
            if self.risk_frame_count
            else 0.0
        )
        mean_covariance_overlap_rate = (
            self.covariance_overlap_rate_sum / self.risk_frame_count
            if self.risk_frame_count
            else 0.0
        )
        return {
            "frame_count": self.frame_count,
            "id_switch_count": self.id_switch_count,
            "track_continuity": self.track_continuity,
            "coverage_continuity": self.coverage_continuity,
            "identity_continuity": self.identity_continuity,
            "duplicate_assignment_count": self.duplicate_assignment_count,
            "d5_disagreement_count": self.d5_disagreement_count,
            "duplicate_track_risk": self.latest_duplicate_track_risk,
            "max_duplicate_track_risk": self.max_duplicate_track_risk,
            "association_ambiguity": self.latest_association_ambiguity,
            "mean_association_ambiguity": mean_association_ambiguity,
            "covariance_overlap_rate": self.latest_covariance_overlap_rate,
            "mean_covariance_overlap_rate": mean_covariance_overlap_rate,
            "max_covariance_overlap_rate": self.max_covariance_overlap_rate,
            "source_node_ids": sorted(self.source_node_ids),
            "link_types": sorted(self.link_types),
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


def _risk_summary_from_result(
    association_result: AssociationResult,
) -> AssociationRiskSummary:
    if association_result.risk_summary is not None:
        return association_result.risk_summary

    metadata = association_result.metadata
    return AssociationRiskSummary(
        timestamp=association_result.timestamp,
        source_node_id=association_result.source_node_id
        or _optional_string(metadata.get("source_node_id")),
        link_type=association_result.link_type or _optional_string(metadata.get("link_type")),
        d5_disagreement_count=int(metadata.get("d5_disagreement_count", 0)),
        duplicate_track_risk=float(metadata.get("duplicate_track_risk", 0.0)),
        association_ambiguity=float(
            metadata.get("association_ambiguity", association_result.ambiguity_score)
        ),
        covariance_overlap_rate=float(metadata.get("covariance_overlap_rate", 0.0)),
        metadata=dict(metadata.get("risk_metadata", {})),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
