"""Track lifecycle manager and constant-velocity Kalman fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Iterable

import numpy as np

from .associators import DataAssociator, GNNHungarianAssociator
from .gating import POSITION_H
from .metrics import MetricsRecorder
from .models import (
    AssociationResult,
    Detection,
    GlobalTrack,
    TrackLifecycleState,
    TrackTransition,
)


@dataclass(slots=True)
class Tracker:
    """Offline tracker with deterministic lifecycle management."""

    associator: DataAssociator = field(default_factory=GNNHungarianAssociator)
    process_noise: float = 0.20
    initial_position_variance: float = 4.0
    initial_velocity_variance: float = 25.0
    confirmation_hits: int = 2
    engageable_hits: int = 4
    lost_miss_threshold: int = 2
    drop_miss_threshold: int = 5
    engageable_covariance_trace: float = 20.0
    feature_smoothing: float = 0.85
    create_tracks_from_unmatched_detections: bool = True
    metrics: MetricsRecorder = field(default_factory=MetricsRecorder)
    tracks: dict[str, GlobalTrack] = field(default_factory=dict, init=False)
    state_transitions: list[TrackTransition] = field(default_factory=list, init=False)
    _next_track_number: int = field(default=1, init=False)

    def active_tracks(self) -> list[GlobalTrack]:
        return [
            track
            for track in self.tracks.values()
            if track.lifecycle_state != TrackLifecycleState.DROPPED
        ]

    def step(
        self,
        detections: Iterable[Detection],
        timestamp: float,
        truth_ids_present: Iterable[str] | None = None,
    ) -> AssociationResult:
        detection_list = list(detections)
        timestamp = float(timestamp)
        truth_ids = (
            list(truth_ids_present)
            if truth_ids_present is not None
            else [detection.truth_id for detection in detection_list if detection.truth_id]
        )

        start_time = perf_counter()
        self.predict_all(timestamp)
        result = self.associator.associate(self.active_tracks(), detection_list, timestamp)

        detections_by_id = {detection.detection_id: detection for detection in detection_list}
        assignments_for_metrics: list[tuple[str, str, float | None]] = []

        for pair in result.matched_pairs:
            track = self.tracks[pair.track_id]
            detection = detections_by_id[pair.detection_id]
            self._kalman_update(track, detection)
            self._advance_state_after_hit(track, timestamp)
            squared_error = _truth_squared_error(track, detection)
            if detection.truth_id is not None:
                assignments_for_metrics.append(
                    (detection.truth_id, track.global_track_id, squared_error)
                )

        for track_id in result.unmatched_track_ids:
            track = self.tracks.get(track_id)
            if track is not None and track.lifecycle_state != TrackLifecycleState.DROPPED:
                self._mark_missed(track, timestamp)

        if self.create_tracks_from_unmatched_detections:
            for detection_id in result.unmatched_detection_ids:
                detection = detections_by_id[detection_id]
                new_track = self._create_track(detection)
                squared_error = _truth_squared_error(new_track, detection)
                if detection.truth_id is not None:
                    assignments_for_metrics.append(
                        (detection.truth_id, new_track.global_track_id, squared_error)
                    )

        runtime = perf_counter() - start_time
        self.metrics.record_frame(
            timestamp=timestamp,
            truth_ids_present=truth_ids,
            association_result=result,
            assignments=assignments_for_metrics,
            runtime_seconds=runtime,
        )
        return result

    def predict_all(self, timestamp: float) -> None:
        for track in self.active_tracks():
            self._predict(track, timestamp)

    def _predict(self, track: GlobalTrack, timestamp: float) -> None:
        dt = max(float(timestamp) - track.timestamp, 0.0)
        if dt == 0.0:
            return
        transition = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2
        q = self.process_noise
        process = q * np.array(
            [
                [dt4 / 4.0, 0.0, dt3 / 2.0, 0.0],
                [0.0, dt4 / 4.0, 0.0, dt3 / 2.0],
                [dt3 / 2.0, 0.0, dt2, 0.0],
                [0.0, dt3 / 2.0, 0.0, dt2],
            ],
            dtype=float,
        )
        track.state = transition @ track.state
        track.covariance = transition @ track.covariance @ transition.T + process
        track.timestamp = float(timestamp)
        track.age += 1
        track.append_history("predict")

    def _kalman_update(self, track: GlobalTrack, detection: Detection) -> None:
        residual = detection.position - POSITION_H @ track.state
        innovation = POSITION_H @ track.covariance @ POSITION_H.T + detection.covariance
        try:
            gain = track.covariance @ POSITION_H.T @ np.linalg.inv(innovation)
        except np.linalg.LinAlgError:
            gain = track.covariance @ POSITION_H.T @ np.linalg.pinv(innovation)
        identity = np.eye(track.covariance.shape[0], dtype=float)
        track.state = track.state + gain @ residual
        joseph = identity - gain @ POSITION_H
        track.covariance = (
            joseph @ track.covariance @ joseph.T
            + gain @ detection.covariance @ gain.T
        )
        track.timestamp = float(detection.timestamp)
        track.last_update_time = float(detection.timestamp)
        track.last_detection_id = detection.detection_id
        track.truth_id = detection.truth_id
        if detection.feature is not None:
            if track.feature is None or track.feature.shape != detection.feature.shape:
                track.feature = detection.feature.copy()
            else:
                alpha = self.feature_smoothing
                track.feature = alpha * track.feature + (1.0 - alpha) * detection.feature
        track.hits += 1
        track.consecutive_hits += 1
        track.misses = 0
        track.identity_confidence = min(1.0, track.consecutive_hits / self.engageable_hits)
        track.append_history("update", detection=detection)

    def _create_track(self, detection: Detection) -> GlobalTrack:
        track_id = f"T{self._next_track_number:03d}"
        self._next_track_number += 1
        state = np.array(
            [detection.position[0], detection.position[1], 0.0, 0.0],
            dtype=float,
        )
        covariance = np.diag(
            [
                self.initial_position_variance,
                self.initial_position_variance,
                self.initial_velocity_variance,
                self.initial_velocity_variance,
            ]
        )
        track = GlobalTrack(
            global_track_id=track_id,
            state=state,
            covariance=covariance,
            timestamp=float(detection.timestamp),
            lifecycle_state=TrackLifecycleState.TENTATIVE,
            hits=1,
            consecutive_hits=1,
            misses=0,
            age=1,
            created_at=float(detection.timestamp),
            last_update_time=float(detection.timestamp),
            last_detection_id=detection.detection_id,
            truth_id=detection.truth_id,
            identity_confidence=1.0 / self.engageable_hits,
            feature=None if detection.feature is None else detection.feature.copy(),
        )
        track.append_history("create", detection=detection)
        self.tracks[track_id] = track
        self._advance_state_after_hit(track, float(detection.timestamp))
        return track

    def _advance_state_after_hit(self, track: GlobalTrack, timestamp: float) -> None:
        covariance_trace = float(np.trace(track.covariance))
        if track.lifecycle_state == TrackLifecycleState.DROPPED:
            return
        if track.lifecycle_state == TrackLifecycleState.LOST:
            if (
                track.hits >= self.engageable_hits
                and covariance_trace <= self.engageable_covariance_trace
            ):
                self._transition(
                    track,
                    TrackLifecycleState.ENGAGEABLE,
                    timestamp,
                    "reacquired_with_high_quality",
                )
            else:
                self._transition(
                    track,
                    TrackLifecycleState.CONFIRMED,
                    timestamp,
                    "reacquired",
                )
            return
        if (
            track.lifecycle_state == TrackLifecycleState.TENTATIVE
            and track.consecutive_hits >= self.confirmation_hits
        ):
            self._transition(
                track,
                TrackLifecycleState.CONFIRMED,
                timestamp,
                "confirmation_hits_reached",
            )
        if (
            track.lifecycle_state == TrackLifecycleState.CONFIRMED
            and track.hits >= self.engageable_hits
            and covariance_trace <= self.engageable_covariance_trace
        ):
            self._transition(
                track,
                TrackLifecycleState.ENGAGEABLE,
                timestamp,
                "quality_threshold_reached",
            )

    def _mark_missed(self, track: GlobalTrack, timestamp: float) -> None:
        track.misses += 1
        track.consecutive_hits = 0
        track.identity_confidence = max(0.0, track.identity_confidence - 0.25)
        track.append_history("miss")
        if track.misses >= self.drop_miss_threshold:
            self._transition(
                track,
                TrackLifecycleState.DROPPED,
                timestamp,
                "drop_miss_threshold_reached",
            )
        elif track.misses >= self.lost_miss_threshold:
            self._transition(
                track,
                TrackLifecycleState.LOST,
                timestamp,
                "lost_miss_threshold_reached",
            )

    def _transition(
        self,
        track: GlobalTrack,
        new_state: TrackLifecycleState,
        timestamp: float,
        reason: str,
    ) -> None:
        if track.lifecycle_state == new_state:
            return
        transition = TrackTransition(
            timestamp=float(timestamp),
            track_id=track.global_track_id,
            from_state=track.lifecycle_state.value,
            to_state=new_state.value,
            reason=reason,
        )
        track.lifecycle_state = new_state
        track.transition_log.append(transition)
        self.state_transitions.append(transition)


def _truth_squared_error(track: GlobalTrack, detection: Detection) -> float | None:
    truth_position = detection.metadata.get("truth_position")
    if truth_position is None:
        return None
    truth_position_array = np.asarray(truth_position, dtype=float).reshape(2)
    residual = track.position - truth_position_array
    return float(residual.T @ residual)
