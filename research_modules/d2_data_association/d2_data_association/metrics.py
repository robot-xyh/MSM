"""Metrics recorder for offline tracking and association evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from math import sqrt
from typing import Iterable

import numpy as np

from .models import AssociationLogEntry, AssociationResult, AssociationRiskSummary


@dataclass(slots=True)
class AssociationRiskSummaryWindowGenerator:
    """Generate sliding-window association risk summaries from D2 evidence."""

    window_size: int = 5
    _frames: deque[dict[str, float | int | str | None]] = field(
        default_factory=deque, init=False
    )

    def __post_init__(self) -> None:
        if self.window_size <= 0:
            raise ValueError("window_size must be positive")

    def update(
        self,
        association_result: AssociationResult,
        *,
        id_switch_delta: int = 0,
        track_continuity: float = 0.0,
    ) -> AssociationRiskSummary:
        """Return a risk summary using the latest frame plus window history."""

        metadata = association_result.metadata
        frame = {
            "timestamp": float(association_result.timestamp),
            "association_ambiguity": _association_ambiguity_from_result(
                association_result
            ),
            "candidate_overlap_rate": _candidate_overlap_rate(metadata),
            "mean_candidate_count": _mean_candidate_count(metadata),
            "cost_margin_risk": _cost_margin_risk(association_result.cost_matrix),
            "id_switch_delta": int(id_switch_delta),
            "continuity_risk": max(0.0, 1.0 - float(track_continuity)),
            "d5_disagreement_count": int(metadata.get("d5_disagreement_count", 0)),
            "source_node_id": association_result.source_node_id
            or _optional_string(metadata.get("source_node_id")),
            "link_type": association_result.link_type
            or _optional_string(metadata.get("link_type")),
        }
        self._frames.append(frame)
        while len(self._frames) > self.window_size:
            self._frames.popleft()

        window = list(self._frames)
        association_ambiguity = _mean_float(window, "association_ambiguity")
        candidate_overlap_rate = _mean_float(window, "candidate_overlap_rate")
        cost_margin_risk = _mean_float(window, "cost_margin_risk")
        id_switch_delta_sum = sum(int(item["id_switch_delta"]) for item in window)
        continuity_risk = _mean_float(window, "continuity_risk")
        d5_disagreement_count = sum(
            int(item["d5_disagreement_count"]) for item in window
        )
        candidate_count_risk = min(
            1.0, max(0.0, (_mean_float(window, "mean_candidate_count") - 1.0) / 4.0)
        )

        duplicate_track_risk = max(
            float(metadata.get("duplicate_track_risk", 0.0)),
            candidate_overlap_rate,
            min(1.0, id_switch_delta_sum / max(1, self.window_size)),
            continuity_risk,
        )
        association_ambiguity = max(
            float(metadata.get("association_ambiguity", association_ambiguity)),
            association_ambiguity,
            candidate_count_risk,
            cost_margin_risk,
        )
        covariance_overlap_rate = max(
            float(metadata.get("covariance_overlap_rate", 0.0)),
            candidate_overlap_rate,
        )

        return AssociationRiskSummary(
            timestamp=association_result.timestamp,
            source_node_id=_latest_string(window, "source_node_id"),
            link_type=_latest_string(window, "link_type"),
            d5_disagreement_count=d5_disagreement_count,
            duplicate_track_risk=duplicate_track_risk,
            association_ambiguity=association_ambiguity,
            covariance_overlap_rate=covariance_overlap_rate,
            metadata={
                "window_size": len(window),
                "configured_window_size": self.window_size,
                "id_switch_delta": int(id_switch_delta),
                "id_switch_delta_sum": id_switch_delta_sum,
                "d5_disagreement_delta": int(
                    metadata.get("d5_disagreement_count", 0)
                ),
                "track_continuity": float(track_continuity),
                "mean_candidate_count": _mean_float(window, "mean_candidate_count"),
                "candidate_overlap_rate": candidate_overlap_rate,
                "cost_margin_risk": cost_margin_risk,
                **dict(metadata.get("risk_metadata", {})),
            },
        )


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
    risk_summary_generator: AssociationRiskSummaryWindowGenerator = field(
        default_factory=AssociationRiskSummaryWindowGenerator
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
        id_switch_count_before = self.id_switch_count
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

        risk_summary = _risk_summary_from_result(
            association_result,
            generator=self.risk_summary_generator,
            id_switch_delta=self.id_switch_count - id_switch_count_before,
            track_continuity=self.track_continuity,
        )
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
        self.d5_disagreement_count += int(
            risk_summary.metadata.get(
                "d5_disagreement_delta", risk_summary.d5_disagreement_count
            )
        )
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
    return track_ids[0]


def _risk_summary_from_result(
    association_result: AssociationResult,
    *,
    generator: AssociationRiskSummaryWindowGenerator | None = None,
    id_switch_delta: int = 0,
    track_continuity: float = 0.0,
) -> AssociationRiskSummary:
    if association_result.risk_summary is not None:
        return association_result.risk_summary
    if generator is not None:
        return generator.update(
            association_result,
            id_switch_delta=id_switch_delta,
            track_continuity=track_continuity,
        )

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


def _association_ambiguity_from_result(association_result: AssociationResult) -> float:
    metadata = association_result.metadata
    if "association_ambiguity" in metadata:
        return float(metadata["association_ambiguity"])
    return float(association_result.ambiguity_score)


def _candidate_overlap_rate(metadata: dict[str, object]) -> float:
    counts = []
    for key in ("candidate_counts_by_track", "candidate_counts_by_detection"):
        value = metadata.get(key)
        if isinstance(value, dict):
            counts.extend(int(count) for count in value.values())
    if not counts:
        return 0.0
    return sum(1 for count in counts if count > 1) / len(counts)


def _mean_candidate_count(metadata: dict[str, object]) -> float:
    counts = []
    for key in ("candidate_counts_by_track", "candidate_counts_by_detection"):
        value = metadata.get(key)
        if isinstance(value, dict):
            counts.extend(int(count) for count in value.values())
    if not counts:
        return 0.0
    return float(sum(counts) / len(counts))


def _cost_margin_risk(cost_matrix: object) -> float:
    if cost_matrix is None:
        return 0.0
    matrix = np.asarray(cost_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.size == 0:
        return 0.0
    row_risks: list[float] = []
    for row in matrix:
        finite = sorted(
            float(value) for value in row if np.isfinite(value) and value < 1.0e8
        )
        if len(finite) < 2:
            continue
        margin = max(finite[1] - finite[0], 0.0)
        row_risks.append(1.0 / (1.0 + margin))
    return float(sum(row_risks) / len(row_risks)) if row_risks else 0.0


def _mean_float(items: list[dict[str, object]], key: str) -> float:
    if not items:
        return 0.0
    return float(sum(float(item[key]) for item in items) / len(items))


def _latest_string(items: list[dict[str, object]], key: str) -> str | None:
    for item in reversed(items):
        value = item.get(key)
        if value is not None:
            return str(value)
    return None
