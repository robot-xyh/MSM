"""Evaluator-only identity metrics for the scalable three-dimensional path."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np

from .models import AssociationResult


@dataclass(frozen=True, slots=True)
class OfflineTruthLabel3D:
    """A truth label that is accepted only by ``Sparse3DOfflineEvaluator``."""

    detection_id: str
    truth_id: str
    measurement_timestamp: float

    def __post_init__(self) -> None:
        if not str(self.detection_id).strip() or not str(self.truth_id).strip():
            raise ValueError("offline detection_id and truth_id must be non-empty")
        if not np.isfinite(self.measurement_timestamp) or self.measurement_timestamp < 0.0:
            raise ValueError(
                "offline measurement_timestamp must be finite and non-negative"
            )


@dataclass(slots=True)
class Sparse3DOfflineEvaluator:
    """Compute ID switches and continuity after online association completes."""

    id_switch_count: int = 0
    duplicate_assignment_count: int = 0
    evaluated_frame_count: int = 0
    labeled_detection_count: int = 0
    false_alarm_assignment_count: int = 0
    last_truth_to_track: dict[str, str] = field(default_factory=dict)
    truth_frame_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    truth_assigned_frame_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    truth_identity_stable_frame_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    confusion_matrix: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )

    def record_frame(
        self,
        association_result: AssociationResult,
        labels: Iterable[Any] | Mapping[str, str],
        *,
        truth_ids_present: Iterable[str] | None = None,
    ) -> None:
        """Score one completed online frame using a separate truth sidecar."""

        truth_by_detection = _truth_mapping(labels, association_result.timestamp)
        assignments = association_result.metadata.get("detection_to_track")
        if not isinstance(assignments, Mapping):
            raise ValueError(
                "association result lacks truth-free detection_to_track audit mapping"
            )
        detection_to_track = {
            str(detection_id): str(track_id)
            for detection_id, track_id in assignments.items()
        }
        present_truth_ids = (
            {str(item) for item in truth_ids_present}
            if truth_ids_present is not None
            else set(truth_by_detection.values())
        )
        if any(not item for item in present_truth_ids):
            raise ValueError("truth_ids_present cannot contain empty identifiers")

        self.evaluated_frame_count += 1
        self.labeled_detection_count += len(truth_by_detection)
        for truth_id in present_truth_ids:
            self.truth_frame_count[truth_id] += 1

        tracks_by_truth: dict[str, list[str]] = defaultdict(list)
        for detection_id, track_id in detection_to_track.items():
            truth_id = truth_by_detection.get(detection_id)
            if truth_id is None:
                self.false_alarm_assignment_count += 1
                continue
            tracks_by_truth[truth_id].append(track_id)
            self.confusion_matrix[truth_id][track_id] += 1

        for truth_id, track_ids in tracks_by_truth.items():
            if track_ids:
                self.truth_assigned_frame_count[truth_id] += 1
            unique_track_ids = set(track_ids)
            if len(unique_track_ids) > 1:
                self.duplicate_assignment_count += len(unique_track_ids) - 1
            representative = track_ids[0]
            previous = self.last_truth_to_track.get(truth_id)
            if previous is not None and previous != representative:
                self.id_switch_count += 1
            else:
                self.truth_identity_stable_frame_count[truth_id] += 1
            self.last_truth_to_track[truth_id] = representative

    @property
    def truth_metrics_available(self) -> bool:
        return bool(self.truth_frame_count)

    @property
    def track_continuity(self) -> float | None:
        if not self.truth_metrics_available:
            return None
        values = [
            self.truth_identity_stable_frame_count.get(truth_id, 0) / frame_count
            for truth_id, frame_count in self.truth_frame_count.items()
            if frame_count > 0
        ]
        return float(np.mean(values)) if values else 0.0

    @property
    def coverage_continuity(self) -> float | None:
        if not self.truth_metrics_available:
            return None
        values = [
            self.truth_assigned_frame_count.get(truth_id, 0) / frame_count
            for truth_id, frame_count in self.truth_frame_count.items()
            if frame_count > 0
        ]
        return float(np.mean(values)) if values else 0.0

    def summary(self) -> dict[str, Any]:
        available = self.truth_metrics_available
        reason = None if available else "offline_truth_labels_unavailable"
        return {
            "evaluated_frame_count": self.evaluated_frame_count,
            "labeled_detection_count": self.labeled_detection_count,
            "id_switch_count": self.id_switch_count if available else None,
            "id_switch_count_available": available,
            "id_switch_count_reason": reason,
            "track_continuity": self.track_continuity,
            "track_continuity_available": available,
            "track_continuity_reason": reason,
            "identity_continuity": self.track_continuity,
            "coverage_continuity": self.coverage_continuity,
            "continuity_available": available,
            "truth_metrics_available": available,
            "truth_metrics_reason": reason,
            "duplicate_assignment_count": self.duplicate_assignment_count,
            "false_alarm_assignment_count": self.false_alarm_assignment_count,
            "confusion_matrix": {
                truth_id: dict(counts)
                for truth_id, counts in sorted(self.confusion_matrix.items())
            },
        }


def _truth_mapping(
    labels: Iterable[Any] | Mapping[str, str],
    expected_timestamp: float,
) -> dict[str, str]:
    if isinstance(labels, Mapping):
        result = {str(key): str(value) for key, value in labels.items()}
    else:
        result: dict[str, str] = {}
        for label in labels:
            detection_id = _first_field(
                label,
                ("detection_id", "observation_id"),
            )
            truth_id = _first_field(
                label,
                ("truth_id", "truth_entity_id"),
            )
            timestamp = float(_first_field(label, ("measurement_timestamp",)))
            if abs(timestamp - expected_timestamp) > 1.0e-9:
                raise ValueError("offline truth label timestamp does not match frame")
            detection_id = str(detection_id)
            truth_id = str(truth_id)
            if detection_id in result:
                raise ValueError("duplicate offline label for one detection")
            result[detection_id] = truth_id
    if any(not key or not value for key, value in result.items()):
        raise ValueError("offline truth labels must use non-empty identifiers")
    return result


def _first_field(value: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    raise ValueError(f"offline truth label lacks one of {names}")


Scalable3DOfflineEvaluator = Sparse3DOfflineEvaluator
