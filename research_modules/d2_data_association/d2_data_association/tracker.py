"""Track lifecycle manager and constant-velocity Kalman fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterable, Mapping

import numpy as np

from .associators import DataAssociator, GNNHungarianAssociator
from .gating import POSITION_H
from .gating import (
    estimate_track_quality,
    mahalanobis_squared,
    source_track_ids_from_detection,
    track_position_covariance_trace,
)
from .metrics import (
    MetricsRecorder,
    validated_upstream_local_identity_rejection_count,
)
from .models import (
    AssociationResult,
    Detection,
    GlobalTrack,
    TrackLifecycleState,
    TrackTransition,
    TrackerTruthPolicy,
)


@dataclass(slots=True)
class Tracker:
    """Tracker with explicit online/offline truth and lifecycle policies."""

    associator: DataAssociator = field(default_factory=GNNHungarianAssociator)
    truth_policy: TrackerTruthPolicy | str = TrackerTruthPolicy.ONLINE
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
    govern_online_source_track_lineage: bool = True
    suppress_source_shadow_births: bool = True
    metrics: MetricsRecorder = field(default_factory=MetricsRecorder)
    tracks: dict[str, GlobalTrack] = field(default_factory=dict, init=False)
    state_transitions: list[TrackTransition] = field(default_factory=list, init=False)
    _next_track_number: int = field(default=1, init=False)
    _source_track_bindings: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        try:
            self.truth_policy = TrackerTruthPolicy(self.truth_policy)
        except (TypeError, ValueError) as exc:
            allowed = ", ".join(policy.value for policy in TrackerTruthPolicy)
            raise ValueError(f"truth_policy must be one of: {allowed}") from exc

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
        frame_metadata: Mapping[str, Any] | None = None,
    ) -> AssociationResult:
        detection_list = list(detections)
        timestamp = float(timestamp)
        upstream_local_identity_rejection_count = (
            validated_upstream_local_identity_rejection_count(frame_metadata)
        )
        self._enforce_truth_policy(
            detection_list,
            truth_ids_present=truth_ids_present,
            frame_metadata=frame_metadata,
        )
        truth_ids = (
            list(truth_ids_present)
            if truth_ids_present is not None
            else [
                detection.truth_id
                for detection in detection_list
                if detection.truth_id
            ]
        )

        start_time = perf_counter()
        transition_count_before = len(self.state_transitions)
        self.predict_all(timestamp)
        association_detections, quarantined_sources = (
            self._govern_source_track_continuity(detection_list)
        )
        result = self.associator.associate(
            self.active_tracks(), association_detections, timestamp
        )
        result.metadata["source_lineage_governance"] = {
            "enabled": bool(
                self.govern_online_source_track_lineage
                and self.truth_policy == TrackerTruthPolicy.ONLINE
            ),
            "quarantined_detection_ids": [
                item["detection_id"] for item in quarantined_sources
            ],
            "quarantined_sources": quarantined_sources,
        }
        if frame_metadata:
            result.metadata = _merge_association_metadata(
                result.metadata,
                frame_metadata,
            )
        result.metadata["quarantined_sources"] = quarantined_sources
        result.metadata["upstream_local_identity_rejection_count"] = (
            upstream_local_identity_rejection_count
        )

        detections_by_id = {
            detection.detection_id: detection for detection in association_detections
        }
        assignments_for_metrics: list[tuple[str, str, float | None]] = []
        created_track_ids: set[str] = set()
        source_binding_conflicts: list[dict[str, str]] = []

        for pair in result.matched_pairs:
            track = self.tracks[pair.track_id]
            detection = detections_by_id[pair.detection_id]
            self._kalman_update(track, detection)
            source_binding_conflicts.extend(
                self._bind_detection_sources(track, detection)
            )
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
            candidate_counts = _int_mapping(
                result.metadata.get("candidate_counts_by_detection", {})
            )
            suppressed_births: list[dict[str, Any]] = []
            for detection_id in result.unmatched_detection_ids:
                detection = detections_by_id[detection_id]
                suppression = self._source_birth_suppression(
                    detection,
                    candidate_count=candidate_counts.get(detection_id, 0),
                )
                if suppression is not None:
                    suppressed_births.append(suppression)
                    continue
                new_track = self._create_track(detection)
                source_binding_conflicts.extend(
                    self._bind_detection_sources(new_track, detection)
                )
                created_track_ids.add(new_track.global_track_id)
                squared_error = _truth_squared_error(new_track, detection)
                if detection.truth_id is not None:
                    assignments_for_metrics.append(
                        (detection.truth_id, new_track.global_track_id, squared_error)
                    )
            result.metadata["suppressed_birth_detection_ids"] = [
                item["detection_id"] for item in suppressed_births
            ]
            result.metadata["suppressed_births"] = suppressed_births

        result.metadata["source_track_bindings"] = dict(
            sorted(self._source_track_bindings.items())
        )
        result.metadata["source_binding_conflicts"] = source_binding_conflicts

        self._refresh_track_quality_and_risk(result, created_track_ids)
        runtime = perf_counter() - start_time
        self.metrics.record_frame(
            timestamp=timestamp,
            truth_ids_present=truth_ids,
            association_result=result,
            assignments=assignments_for_metrics,
            runtime_seconds=runtime,
            lifecycle_birth_track_ids=created_track_ids,
            lifecycle_transitions=self.state_transitions[transition_count_before:],
            frame_metadata=frame_metadata,
        )
        return result

    def _govern_source_track_continuity(
        self,
        detections: list[Detection],
    ) -> tuple[list[Detection], list[dict[str, Any]]]:
        if (
            not self.govern_online_source_track_lineage
            or self.truth_policy != TrackerTruthPolicy.ONLINE
        ):
            return detections, []

        accepted: list[Detection] = []
        quarantined: list[dict[str, Any]] = []
        gate_threshold = _associator_source_lineage_gate(self.associator)
        for detection in detections:
            rejection: dict[str, Any] | None = None
            for source_track_id in sorted(source_track_ids_from_detection(detection)):
                bound_track = self._bound_active_track(source_track_id)
                if bound_track is None:
                    continue
                distance = mahalanobis_squared(bound_track, detection)
                if distance <= gate_threshold:
                    continue
                rejection = {
                    "detection_id": detection.detection_id,
                    "source_track_id": source_track_id,
                    "bound_global_track_id": bound_track.global_track_id,
                    "reason": "bound_source_mahalanobis_discontinuity",
                    "mahalanobis_squared": distance,
                    "gate_threshold": gate_threshold,
                }
                break
            if rejection is None:
                accepted.append(detection)
            else:
                quarantined.append(rejection)
        return accepted, quarantined

    def _source_birth_suppression(
        self,
        detection: Detection,
        *,
        candidate_count: int,
    ) -> dict[str, Any] | None:
        if (
            not self.suppress_source_shadow_births
            or self.truth_policy != TrackerTruthPolicy.ONLINE
        ):
            return None
        source_track_ids = sorted(source_track_ids_from_detection(detection))
        if not source_track_ids:
            return None
        for source_track_id in source_track_ids:
            bound_track = self._bound_active_track(source_track_id)
            if bound_track is not None:
                return {
                    "detection_id": detection.detection_id,
                    "source_track_id": source_track_id,
                    "bound_global_track_id": bound_track.global_track_id,
                    "candidate_count": int(candidate_count),
                    "reason": "source_track_already_bound",
                }
        if candidate_count > 0:
            return {
                "detection_id": detection.detection_id,
                "source_track_id": source_track_ids[0],
                "bound_global_track_id": None,
                "candidate_count": int(candidate_count),
                "reason": "gated_shadow_of_existing_track",
            }
        return None

    def _bound_active_track(self, source_track_id: str) -> GlobalTrack | None:
        track_id = self._source_track_bindings.get(str(source_track_id))
        if track_id is None:
            return None
        track = self.tracks.get(track_id)
        if track is None or track.lifecycle_state == TrackLifecycleState.DROPPED:
            self._source_track_bindings.pop(str(source_track_id), None)
            return None
        return track

    def _bind_detection_sources(
        self,
        track: GlobalTrack,
        detection: Detection,
    ) -> list[dict[str, str]]:
        conflicts: list[dict[str, str]] = []
        for source_track_id in sorted(source_track_ids_from_detection(detection)):
            existing = self._bound_active_track(source_track_id)
            if existing is not None and existing.global_track_id != track.global_track_id:
                conflicts.append(
                    {
                        "source_track_id": source_track_id,
                        "bound_global_track_id": existing.global_track_id,
                        "matched_global_track_id": track.global_track_id,
                        "reason": "source_track_binding_conflict",
                    }
                )
                continue
            self._source_track_bindings[source_track_id] = track.global_track_id
            track.source_track_ids.add(source_track_id)
        return conflicts

    def _enforce_truth_policy(
        self,
        detections: Iterable[Detection],
        *,
        truth_ids_present: Iterable[str] | None,
        frame_metadata: Mapping[str, Any] | None,
    ) -> None:
        if self.truth_policy != TrackerTruthPolicy.ONLINE:
            return
        violations: list[str] = []
        if truth_ids_present is not None:
            violations.append("truth_ids_present")
        for index, detection in enumerate(detections):
            if detection.truth_id is not None:
                violations.append(f"detections[{index}].truth_id")
            violations.extend(
                _forbidden_online_metadata_paths(
                    detection.metadata,
                    path=f"detections[{index}].metadata",
                )
            )
        if frame_metadata is not None:
            violations.extend(
                _forbidden_online_metadata_paths(
                    frame_metadata,
                    path="frame_metadata",
                )
            )
        if violations:
            paths = ", ".join(sorted(set(violations)))
            raise ValueError(
                "online truth policy rejected evaluator/simulator identity fields: "
                f"{paths}"
            )

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
        track.ensure_covariance_consistency()
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
        track.ensure_covariance_consistency()
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
            source_track_ids=source_track_ids_from_detection(detection),
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

    def _refresh_track_quality_and_risk(
        self,
        result: AssociationResult,
        created_track_ids: set[str],
    ) -> None:
        matched_track_ids = {pair.track_id for pair in result.matched_pairs}
        candidate_counts = _float_mapping(
            result.metadata.get("candidate_counts_by_track", {})
        )
        motion_by_track = _float_mapping(
            result.metadata.get("motion_consistency_by_track", {})
        )
        gate_thresholds = _float_mapping(
            result.metadata.get("gate_thresholds_by_track", {})
        )
        target_density_by_track = _float_mapping(
            result.metadata.get("target_density_by_track", {})
        )

        track_quality_by_track: dict[str, float] = {}
        association_risk_by_track: dict[str, float] = {}
        quality_metadata_by_track: dict[str, dict[str, Any]] = {}

        for track in self.active_tracks():
            track_id = track.global_track_id
            quality = estimate_track_quality(track)
            candidate_count = int(candidate_counts.get(track_id, 0.0))
            motion_cost = float(motion_by_track.get(track_id, 0.0))
            matched_this_frame = track_id in matched_track_ids
            created_this_frame = track_id in created_track_ids
            association_risk, risk_components = _track_association_risk(
                track=track,
                track_quality=quality,
                candidate_count=candidate_count,
                motion_consistency_cost=motion_cost,
                matched_this_frame=matched_this_frame,
                created_this_frame=created_this_frame,
                drop_miss_threshold=self.drop_miss_threshold,
            )
            metadata = {
                "track_quality": quality,
                "association_risk": association_risk,
                "position_covariance_trace": track_position_covariance_trace(track),
                "candidate_count": candidate_count,
                "motion_consistency_cost": motion_cost,
                "target_density": float(target_density_by_track.get(track_id, 0.0)),
                "gate_threshold": gate_thresholds.get(track_id),
                "matched_this_frame": matched_this_frame,
                "created_this_frame": created_this_frame,
                "risk_components": risk_components,
            }
            track.track_quality = quality
            track.association_risk = association_risk
            track.quality_metadata = metadata
            track_quality_by_track[track_id] = quality
            association_risk_by_track[track_id] = association_risk
            quality_metadata_by_track[track_id] = metadata

        if track_quality_by_track:
            quality_values = list(track_quality_by_track.values())
            risk_values = list(association_risk_by_track.values())
            mean_quality = float(sum(quality_values) / len(quality_values))
            min_quality = float(min(quality_values))
            max_association_risk = float(max(risk_values))
            low_quality_track_count = sum(1 for value in quality_values if value < 0.5)
        else:
            mean_quality = 0.0
            min_quality = 0.0
            max_association_risk = 0.0
            low_quality_track_count = 0

        result.metadata.update(
            {
                "track_quality_by_track": track_quality_by_track,
                "association_risk_by_track": association_risk_by_track,
                "track_quality_metadata_by_track": quality_metadata_by_track,
                "mean_track_quality": mean_quality,
                "min_track_quality": min_quality,
                "max_track_association_risk": max_association_risk,
                "low_quality_track_count": low_quality_track_count,
            }
        )


def _truth_squared_error(track: GlobalTrack, detection: Detection) -> float | None:
    truth_position = detection.metadata.get("truth_position")
    if truth_position is None:
        return None
    truth_position_array = np.asarray(truth_position, dtype=float).reshape(2)
    residual = track.position - truth_position_array
    return float(residual.T @ residual)


def _track_association_risk(
    *,
    track: GlobalTrack,
    track_quality: float,
    candidate_count: int,
    motion_consistency_cost: float,
    matched_this_frame: bool,
    created_this_frame: bool,
    drop_miss_threshold: int,
) -> tuple[float, dict[str, float]]:
    quality_risk = 0.55 * max(0.0, 1.0 - track_quality)
    candidate_risk = min(0.30, max(0, candidate_count - 1) * 0.12)
    motion_risk = min(0.25, max(0.0, motion_consistency_cost) / 3.0 * 0.25)
    miss_risk = min(
        0.35,
        max(0.0, float(track.misses)) / max(float(drop_miss_threshold), 1.0) * 0.35,
    )
    unmatched_risk = 0.0 if matched_this_frame or created_this_frame else 0.18
    lifecycle_risk = _lifecycle_association_risk(track.lifecycle_state)
    created_risk = 0.05 if created_this_frame else 0.0
    components = {
        "quality_risk": quality_risk,
        "candidate_risk": candidate_risk,
        "motion_risk": motion_risk,
        "miss_risk": miss_risk,
        "unmatched_risk": unmatched_risk,
        "lifecycle_risk": lifecycle_risk,
        "created_risk": created_risk,
    }
    return float(np.clip(sum(components.values()), 0.0, 1.0)), components


def _lifecycle_association_risk(state: TrackLifecycleState) -> float:
    if state == TrackLifecycleState.DROPPED:
        return 0.50
    if state == TrackLifecycleState.LOST:
        return 0.28
    if state == TrackLifecycleState.TENTATIVE:
        return 0.08
    return 0.0


def _float_mapping(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        try:
            result[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return result


def _int_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        try:
            result[str(key)] = int(item)
        except (TypeError, ValueError):
            continue
    return result


def _associator_source_lineage_gate(associator: DataAssociator) -> float:
    for attribute in ("max_gate_threshold", "gate_threshold"):
        value = getattr(associator, attribute, None)
        if value is None:
            continue
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(threshold) and threshold > 0.0:
            return threshold
    return 16.0


def _merge_association_metadata(
    association_metadata: Mapping[str, Any],
    frame_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge replay row metadata without overriding associator diagnostics."""

    merged = dict(association_metadata)
    current_replay_metadata = merged.get("replay_metadata", {})
    replay_metadata = (
        dict(current_replay_metadata)
        if isinstance(current_replay_metadata, Mapping)
        else {}
    )
    for key, value in frame_metadata.items():
        if value is None:
            continue
        replay_metadata.setdefault(str(key), value)
        merged.setdefault(str(key), value)
    if replay_metadata:
        merged["replay_metadata"] = replay_metadata
    return merged


_ONLINE_BOOLEAN_GOVERNANCE_KEYS = {
    "continuity_available",
    "online_truth_hints_used",
    "online_truth_isolated",
    "truth_metrics_available",
}

_ONLINE_OBJECT_IDENTITY_KEYS = {
    "object",
    "objects",
    "object_id",
    "object_identity",
    "object_name",
    "sim_object_id",
    "source_object_id",
}


def _forbidden_online_metadata_paths(value: Any, *, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            item_path = f"{path}.{key}"
            if normalized in _ONLINE_BOOLEAN_GOVERNANCE_KEYS:
                if not isinstance(item, bool):
                    violations.append(item_path)
                continue
            if _is_forbidden_online_metadata_key(normalized):
                violations.append(item_path)
                continue
            violations.extend(
                _forbidden_online_metadata_paths(item, path=item_path)
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            violations.extend(
                _forbidden_online_metadata_paths(item, path=f"{path}[{index}]")
            )
    return violations


def _is_forbidden_online_metadata_key(key: str) -> bool:
    if (
        key == "truth"
        or key.startswith("truth_")
        or key.endswith("_truth")
        or "ground_truth" in key
        or "offline_truth" in key
        or "sim_truth" in key
    ):
        return True
    if key == "actor" or key == "actors" or key.startswith("actor_"):
        return True
    return key in _ONLINE_OBJECT_IDENTITY_KEYS
