"""Offline-only evidence benchmark for observation-claim governance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .observation_governance import ObservationClaimLedgerConfig
from .scalable_3d_models import Detection3D
from .scalable_3d_offline import OfflineTruthLabel3D, Sparse3DOfflineEvaluator
from .sparse_3d import Scalable3DTracker


OBSERVATION_GOVERNANCE_BENCHMARK_SCHEMA_VERSION = (
    "d2-observation-governance-offline-benchmark-v1"
)


@dataclass(frozen=True, slots=True)
class ObservationGovernanceBenchmarkReport:
    """Truth-sidecar metrics; none of these labels enter the online tracker."""

    target_count: int
    frame_count: int
    separation_m: float
    legitimate_detection_count: int
    legitimate_false_suppression_count: int
    nearby_independent_target_recall: float
    erroneous_coalescence_count: int
    confirmation_latency_seconds_by_truth: dict[str, float | None]
    offline_identity_metrics: dict[str, Any]
    ledger_summary: dict[str, Any]

    @property
    def legitimate_false_suppression_rate(self) -> float:
        if self.legitimate_detection_count <= 0:
            return 0.0
        return (
            self.legitimate_false_suppression_count
            / self.legitimate_detection_count
        )

    @property
    def confirmation_latency_mean_seconds(self) -> float | None:
        values = [
            float(value)
            for value in self.confirmation_latency_seconds_by_truth.values()
            if value is not None
        ]
        return float(np.mean(values)) if values else None

    @property
    def confirmation_latency_p95_seconds(self) -> float | None:
        values = [
            float(value)
            for value in self.confirmation_latency_seconds_by_truth.values()
            if value is not None
        ]
        return float(np.percentile(values, 95.0)) if values else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_GOVERNANCE_BENCHMARK_SCHEMA_VERSION,
            "target_count": self.target_count,
            "frame_count": self.frame_count,
            "separation_m": self.separation_m,
            "legitimate_detection_count": self.legitimate_detection_count,
            "legitimate_false_suppression_count": (
                self.legitimate_false_suppression_count
            ),
            "legitimate_false_suppression_rate": (
                self.legitimate_false_suppression_rate
            ),
            "nearby_independent_target_recall": (
                self.nearby_independent_target_recall
            ),
            "erroneous_coalescence_count": self.erroneous_coalescence_count,
            "confirmation_latency_seconds_by_truth": dict(
                sorted(self.confirmation_latency_seconds_by_truth.items())
            ),
            "confirmation_latency_mean_seconds": (
                self.confirmation_latency_mean_seconds
            ),
            "confirmation_latency_p95_seconds": (
                self.confirmation_latency_p95_seconds
            ),
            "offline_identity_metrics": self.offline_identity_metrics,
            "ledger_summary": self.ledger_summary,
            "online_truth_used": False,
            "truth_scope": "offline_evaluator_only",
        }


def run_observation_governance_benchmark(
    *,
    target_count: int,
    frame_count: int = 12,
    separation_m: float = 0.75,
    dt_seconds: float = 0.25,
    observation_claim_config: ObservationClaimLedgerConfig | None = None,
) -> ObservationGovernanceBenchmarkReport:
    """Measure claim false suppression and close-target recall for dynamic N.

    The final target enters after the initial tracks have started.  Online
    detections contain only opaque source lineage.  The separate labels below
    are passed to ``Sparse3DOfflineEvaluator`` only after association finishes.
    """

    target_count = int(target_count)
    frame_count = int(frame_count)
    separation_m = float(separation_m)
    dt_seconds = float(dt_seconds)
    if target_count <= 0:
        raise ValueError("target_count must be positive")
    if frame_count < 3:
        raise ValueError("frame_count must be at least 3")
    if not np.isfinite(separation_m) or separation_m <= 0.0:
        raise ValueError("separation_m must be positive and finite")
    if not np.isfinite(dt_seconds) or dt_seconds <= 0.0:
        raise ValueError("dt_seconds must be positive and finite")

    tracker = Scalable3DTracker(
        observation_claim_config=(
            ObservationClaimLedgerConfig()
            if observation_claim_config is None
            else observation_claim_config
        ),
    )
    evaluator = Sparse3DOfflineEvaluator()
    entry_frame = 0 if target_count == 1 else max(2, frame_count // 3)
    first_seen: dict[str, float] = {}
    confirmation_time: dict[str, float] = {}
    legitimate_count = 0
    false_suppression_count = 0
    assigned_truth_instances = 0
    present_truth_instances = 0
    erroneous_coalescence_count = 0

    for frame_index in range(frame_count):
        timestamp = frame_index * dt_seconds
        active_count = (
            target_count
            if frame_index >= entry_frame
            else max(1, target_count - 1)
        )
        detections: list[Detection3D] = []
        labels: list[OfflineTruthLabel3D] = []
        truth_ids_present: list[str] = []
        for target_index in range(active_count):
            truth_id = f"offline-target-{target_index:04d}"
            detection_id = f"frame-{frame_index:05d}-detection-{target_index:04d}"
            observation_id = (
                f"frame-{frame_index:05d}-observation-{target_index:04d}"
            )
            position = np.asarray(
                [
                    0.8 * timestamp,
                    target_index * separation_m,
                    -100.0 - 0.05 * (target_index % 3),
                ],
                dtype=float,
            )
            detections.append(
                Detection3D(
                    detection_id=detection_id,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + 0.02,
                    position_ned=position,
                    covariance=np.eye(3, dtype=float) * 0.01,
                    velocity_ned=np.asarray([0.8, 0.0, 0.0], dtype=float),
                    velocity_covariance=np.eye(3, dtype=float) * 0.01,
                    source_node_id="d1-offline-benchmark",
                    source_track_id=f"anonymous-source-{target_index:04d}",
                    metadata={
                        "latest_observation_id": observation_id,
                        "latest_sensor_id": "benchmark-radar",
                        "source_measurement_timestamp": timestamp,
                    },
                )
            )
            labels.append(
                OfflineTruthLabel3D(
                    detection_id=detection_id,
                    truth_id=truth_id,
                    measurement_timestamp=timestamp,
                )
            )
            truth_ids_present.append(truth_id)
            first_seen.setdefault(truth_id, timestamp)

        result = tracker.step(detections, timestamp)
        evaluator.record_frame(
            result,
            labels,
            truth_ids_present=truth_ids_present,
        )
        assignments = {
            str(detection_id): str(track_id)
            for detection_id, track_id in result.metadata[
                "detection_to_track"
            ].items()
        }
        truth_by_detection = {
            label.detection_id: label.truth_id for label in labels
        }
        legitimate_count += len(labels)
        false_suppression_count += sum(
            label.detection_id not in assignments for label in labels
        )
        present_truth_instances += len(truth_ids_present)
        assigned_truth_instances += len(
            {
                truth_by_detection[detection_id]
                for detection_id in assignments
                if detection_id in truth_by_detection
            }
        )
        erroneous_coalescence_count += int(
            result.metadata["duplicate_coalescence_count"]
        )
        for detection_id, track_id in assignments.items():
            truth_id = truth_by_detection.get(detection_id)
            if truth_id is None or truth_id in confirmation_time:
                continue
            track = tracker.tracks[track_id]
            if track.lifecycle_state.value in {
                "confirmed",
                "engageable",
            }:
                confirmation_time[truth_id] = timestamp

    confirmation_latency = {
        truth_id: (
            None
            if truth_id not in confirmation_time
            else confirmation_time[truth_id] - first_timestamp
        )
        for truth_id, first_timestamp in sorted(first_seen.items())
    }
    return ObservationGovernanceBenchmarkReport(
        target_count=target_count,
        frame_count=frame_count,
        separation_m=separation_m,
        legitimate_detection_count=legitimate_count,
        legitimate_false_suppression_count=false_suppression_count,
        nearby_independent_target_recall=(
            assigned_truth_instances / present_truth_instances
            if present_truth_instances
            else 0.0
        ),
        erroneous_coalescence_count=erroneous_coalescence_count,
        confirmation_latency_seconds_by_truth=confirmation_latency,
        offline_identity_metrics=evaluator.summary(),
        ledger_summary=tracker.summary()["observation_claim_ledger"],
    )
