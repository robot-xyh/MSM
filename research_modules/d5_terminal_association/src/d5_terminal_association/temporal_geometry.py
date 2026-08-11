"""Stateful temporal filtering for truth-free geometric association.

The stateless AirSim geometry helper remains the source of per-frame costs.
This module adds bounded coast, conservative binding hysteresis, and explicit
events without creating or mutating center-owned global track identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping

import numpy as np

from .airsim_geometry import (
    GeometricAssociationResult,
    associate_tracks_to_detections_geometrically,
)
from .associator import AssociationConfig
from .models import CameraModel, GlobalTrack, LocalVisualTrack


TEMPORAL_BINDING_EVENTS = frozenset(
    {"continued", "pending", "held", "confirmed", "expired", "recovered"}
)
NON_MEASURED_DECISION_STATES = frozenset({"hold", "reacquire", "coast"})


@dataclass(frozen=True)
class TemporalGeometricAssociationConfig:
    """Configuration for bounded coast and binding hysteresis."""

    association_config: AssociationConfig = field(default_factory=AssociationConfig)
    coast_time_s: float = 0.25
    challenger_required_frames: int = 2
    prediction_rate_sigma_px_s: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.association_config, AssociationConfig):
            raise TypeError("association_config must be an AssociationConfig")
        if not math.isfinite(float(self.coast_time_s)) or self.coast_time_s < 0.0:
            raise ValueError("coast_time_s must be finite and non-negative")
        if int(self.challenger_required_frames) < 2:
            raise ValueError("challenger_required_frames must be at least 2")
        object.__setattr__(self, "coast_time_s", float(self.coast_time_s))
        object.__setattr__(
            self,
            "challenger_required_frames",
            int(self.challenger_required_frames),
        )
        sigma = self.prediction_rate_sigma_px_s
        if sigma is not None:
            sigma = float(sigma)
            if not math.isfinite(sigma) or sigma < 0.0:
                raise ValueError("prediction_rate_sigma_px_s must be finite and non-negative")
            object.__setattr__(self, "prediction_rate_sigma_px_s", sigma)

    @property
    def effective_prediction_rate_sigma_px_s(self) -> float:
        if self.prediction_rate_sigma_px_s is not None:
            return self.prediction_rate_sigma_px_s
        return float(self.association_config.rate_sigma_px_s)


@dataclass(frozen=True)
class TemporalBindingEvent:
    """One auditable transition of a camera-local binding."""

    resource_id: str
    camera_id: str
    stream_id: str
    local_track_id: str
    event: str
    incumbent_global_track_id: str | None
    candidate_global_track_id: str | None
    reason: str
    measurement_timestamp: float
    arrival_timestamp: float
    candidate_margin: float | None = None
    prediction_age_s: float | None = None
    measured_evidence: bool = False

    def __post_init__(self) -> None:
        if self.event not in TEMPORAL_BINDING_EVENTS:
            raise ValueError(f"unsupported temporal binding event: {self.event}")
        if not self.resource_id or not self.camera_id or not self.stream_id:
            raise ValueError("resource_id, camera_id, and stream_id must be non-empty")
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        _require_finite_timestamp(self.measurement_timestamp, "measurement_timestamp")
        _require_finite_timestamp(self.arrival_timestamp, "arrival_timestamp")
        if self.prediction_age_s is not None and self.prediction_age_s < 0.0:
            raise ValueError("prediction_age_s must be non-negative")

    @property
    def association_confirmed(self) -> bool:
        return bool(self.measured_evidence and self.event in {"continued", "confirmed", "recovered"})

    def to_log_record(self) -> dict[str, Any]:
        margin = _finite_or_none(self.candidate_margin)
        return {
            "record_type": "temporal_binding_event",
            "association_source": "temporal_geometric_detect",
            "resource_id": self.resource_id,
            "camera_id": self.camera_id,
            "stream_id": self.stream_id,
            "local_track_id": self.local_track_id,
            "incumbent_global_track_id": self.incumbent_global_track_id,
            "candidate_global_track_id": self.candidate_global_track_id,
            "binding_event": self.event,
            "binding_reason": self.reason,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "candidate_margin": margin,
            "candidate_margin_is_infinite": bool(
                self.candidate_margin is not None and math.isinf(self.candidate_margin)
            ),
            "prediction_age_s": self.prediction_age_s,
            "measured_evidence": bool(self.measured_evidence),
            "association_confirmed": self.association_confirmed,
            "terminal_authorization_allowed": False,
            "truth_identity_used": False,
        }


@dataclass(frozen=True)
class TemporalPredictionRecord:
    """Non-authorizing coast or reacquisition evidence for one local track."""

    resource_id: str
    camera_id: str
    stream_id: str
    local_track_id: str
    bound_global_track_id: str | None
    local_track_state: str
    decision_state: str
    predicted_center_px: np.ndarray
    predicted_bbox: tuple[float, float, float, float] | None
    prediction_covariance_px: np.ndarray
    prediction_age_s: float
    last_measurement_timestamp: float | None
    measurement_timestamp: float
    arrival_timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision_state not in NON_MEASURED_DECISION_STATES:
            raise ValueError("non-measured evidence can only be hold, reacquire, or coast")
        if self.local_track_state not in {"predicted", "lost"}:
            raise ValueError("local_track_state must be predicted or lost")
        if self.prediction_age_s < 0.0:
            raise ValueError("prediction_age_s must be non-negative")
        center = np.asarray(self.predicted_center_px, dtype=float).reshape(-1)
        if center.shape != (2,) or not np.all(np.isfinite(center)):
            raise ValueError("predicted_center_px must contain two finite values")
        covariance = np.asarray(self.prediction_covariance_px, dtype=float)
        if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
            raise ValueError("prediction_covariance_px must be a finite 2x2 matrix")
        if not np.allclose(covariance, covariance.T):
            raise ValueError("prediction_covariance_px must be symmetric")
        object.__setattr__(self, "predicted_center_px", center.copy())
        object.__setattr__(self, "prediction_covariance_px", covariance.copy())
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_log_record(self) -> dict[str, Any]:
        return {
            "record_type": "temporal_prediction",
            "association_source": "temporal_geometric_detect",
            "resource_id": self.resource_id,
            "camera_id": self.camera_id,
            "stream_id": self.stream_id,
            "global_track_id": self.bound_global_track_id,
            "local_track_id": self.local_track_id,
            "local_track_state": self.local_track_state,
            "decision_state": self.decision_state,
            "predicted_center_px": self.predicted_center_px.tolist(),
            "predicted_bbox": list(self.predicted_bbox) if self.predicted_bbox is not None else None,
            "prediction_covariance_px": self.prediction_covariance_px.tolist(),
            "prediction_age_s": self.prediction_age_s,
            "last_measurement_timestamp": self.last_measurement_timestamp,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "terminal_authorization_allowed": False,
            "truth_identity_used": False,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TemporalGeometricAssociationResult:
    """Per-frame temporal association output for main runtime integration."""

    frame_id: str | None
    resource_id: str
    camera_id: str
    stream_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    instantaneous_result: GeometricAssociationResult
    measured_assignments: dict[str, str]
    active_bindings: dict[str, str]
    coasted_records: tuple[TemporalPredictionRecord, ...]
    binding_events: tuple[TemporalBindingEvent, ...]
    candidate_margins: dict[str, float | None]
    reset_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "measured_assignments", dict(self.measured_assignments))
        object.__setattr__(self, "active_bindings", dict(self.active_bindings))
        object.__setattr__(self, "candidate_margins", dict(self.candidate_margins))
        object.__setattr__(self, "reset_reasons", tuple(self.reset_reasons))

    @property
    def truth_identity_used(self) -> bool:
        return False

    def to_log_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            [event.to_log_record() for event in self.binding_events]
            + [record.to_log_record() for record in self.coasted_records]
        )


@dataclass
class _TrackBindingState:
    resource_id: str
    camera_id: str
    stream_id: str
    local_track_id: str
    bound_global_track_id: str
    last_measured_track: LocalVisualTrack
    last_measurement_timestamp: float
    last_arrival_timestamp: float
    pending_challenger_id: str | None = None
    pending_challenger_frames: int = 0
    pending_frame_token: str | None = None
    was_coasting: bool = False


@dataclass
class _StreamClock:
    measurement_timestamp: float
    arrival_timestamp: float


class TemporalGeometricAssociator:
    """Add bounded temporal continuity to stateless geometric association.

    State is isolated by ``(resource_id, camera_id, stream_id,
    local_track_id)``. Only current measured evidence may establish or change
    a binding. Predicted/lost evidence remains non-authorizing.
    """

    def __init__(self, config: TemporalGeometricAssociationConfig | None = None) -> None:
        self.config = config or TemporalGeometricAssociationConfig()
        self._states: dict[tuple[str, str, str, str], _TrackBindingState] = {}
        self._stream_clocks: dict[tuple[str, str, str], _StreamClock] = {}

    def associate(
        self,
        global_tracks: Iterable[GlobalTrack],
        local_tracks: Iterable[LocalVisualTrack],
        camera: CameraModel,
        *,
        resource_id: str,
        camera_id: str,
        stream_id: str = "default",
        measurement_timestamp: float,
        arrival_timestamp: float,
        frame_id: str | None = None,
    ) -> TemporalGeometricAssociationResult:
        """Associate one camera frame and update temporal binding state."""

        resource_id = _required_id(resource_id, "resource_id")
        camera_id = _required_id(camera_id, "camera_id")
        stream_id = _required_id(stream_id, "stream_id")
        measurement_timestamp = _require_finite_timestamp(
            measurement_timestamp,
            "measurement_timestamp",
        )
        arrival_timestamp = _require_finite_timestamp(arrival_timestamp, "arrival_timestamp")
        namespace = (resource_id, camera_id, stream_id)
        track_list = list(global_tracks)
        local_list = list(local_tracks)

        events: list[TemporalBindingEvent] = []
        reset_reasons: list[str] = []
        clock = self._stream_clocks.get(namespace)
        rollback_reason = _clock_rollback_reason(
            clock,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        if rollback_reason is not None:
            events.extend(
                self._reset_namespace(
                    namespace,
                    reason=rollback_reason,
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                )
            )
            reset_reasons.append(rollback_reason)
        self._stream_clocks[namespace] = _StreamClock(
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )

        events.extend(
            self._apply_local_reset_markers(
                namespace,
                local_list,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
            )
        )
        events.extend(
            self._expire_stale_states(
                namespace,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
            )
        )

        instantaneous = associate_tracks_to_detections_geometrically(
            track_list,
            local_list,
            camera,
            config=self.config.association_config,
            timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id=frame_id,
        )
        proposals = {
            local_track_id: global_track_id
            for global_track_id, local_track_id in instantaneous.assignments.items()
        }
        pairwise_swap_ids = self._pairwise_swap_local_ids(namespace, proposals)
        measured_assignments: dict[str, str] = {}
        candidate_margins: dict[str, float | None] = {}
        seen_local_ids: set[str] = set()

        for local_track in local_list:
            local_track_id = local_track.local_track_id
            seen_local_ids.add(local_track_id)
            if local_track.local_track_state != "measured":
                continue
            key = (*namespace, local_track_id)
            state = self._states.get(key)
            candidate = proposals.get(local_track_id)
            margin = _candidate_margin(
                instantaneous,
                local_track_id=local_track_id,
                candidate_global_track_id=candidate,
                incumbent_global_track_id=(state.bound_global_track_id if state is not None else None),
                cost_inf=self.config.association_config.cost_inf,
            )
            candidate_margins[local_track_id] = margin
            event, accepted_global_track_id = self._process_measured_track(
                namespace=namespace,
                local_track=local_track,
                candidate_global_track_id=candidate,
                candidate_margin=margin,
                pairwise_swap=local_track_id in pairwise_swap_ids,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id=frame_id,
            )
            events.append(event)
            if accepted_global_track_id is not None:
                measured_assignments[accepted_global_track_id] = local_track_id

        coasted_records: list[TemporalPredictionRecord] = []
        for local_track in local_list:
            if local_track.local_track_state == "measured":
                continue
            record, event = self._record_non_measured_input(
                namespace,
                local_track,
                camera,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
            )
            if record is not None:
                coasted_records.append(record)
            if event is not None:
                events.append(event)

        for key, state in sorted(self._states.items()):
            if key[:3] != namespace or state.local_track_id in seen_local_ids:
                continue
            record = self._prediction_record(
                state,
                camera,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                local_track=None,
            )
            coasted_records.append(record)
            state.was_coasting = True
            self._clear_pending(state)
            events.append(
                self._event(
                    state,
                    event="held",
                    candidate_global_track_id=None,
                    reason="measurement_missing_within_coast_window",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    prediction_age_s=record.prediction_age_s,
                    measured_evidence=False,
                )
            )

        active_bindings = {
            state.local_track_id: state.bound_global_track_id
            for key, state in sorted(self._states.items())
            if key[:3] == namespace
        }
        return TemporalGeometricAssociationResult(
            frame_id=frame_id,
            resource_id=resource_id,
            camera_id=camera_id,
            stream_id=stream_id,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            instantaneous_result=instantaneous,
            measured_assignments=measured_assignments,
            active_bindings=active_bindings,
            coasted_records=tuple(coasted_records),
            binding_events=tuple(events),
            candidate_margins=candidate_margins,
            reset_reasons=tuple(reset_reasons),
        )

    def reset(
        self,
        *,
        resource_id: str | None = None,
        camera_id: str | None = None,
        stream_id: str | None = None,
        reason: str = "explicit_reset",
    ) -> tuple[TemporalBindingEvent, ...]:
        """Clear all state matching the optional resource/camera/stream filters."""

        reason = str(reason).strip() or "explicit_reset"
        keys = [
            key
            for key in self._states
            if _namespace_matches(
                key[:3],
                resource_id=resource_id,
                camera_id=camera_id,
                stream_id=stream_id,
            )
        ]
        events: list[TemporalBindingEvent] = []
        for key in sorted(keys):
            state = self._states.pop(key)
            events.append(
                self._event(
                    state,
                    event="expired",
                    candidate_global_track_id=None,
                    reason=reason,
                    measurement_timestamp=state.last_measurement_timestamp,
                    arrival_timestamp=state.last_arrival_timestamp,
                    prediction_age_s=0.0,
                    measured_evidence=False,
                )
            )
        clock_keys = [
            namespace
            for namespace in self._stream_clocks
            if _namespace_matches(
                namespace,
                resource_id=resource_id,
                camera_id=camera_id,
                stream_id=stream_id,
            )
        ]
        for namespace in clock_keys:
            self._stream_clocks.pop(namespace, None)
        return tuple(events)

    def _process_measured_track(
        self,
        *,
        namespace: tuple[str, str, str],
        local_track: LocalVisualTrack,
        candidate_global_track_id: str | None,
        candidate_margin: float | None,
        pairwise_swap: bool,
        measurement_timestamp: float,
        arrival_timestamp: float,
        frame_id: str | None,
    ) -> tuple[TemporalBindingEvent, str | None]:
        key = (*namespace, local_track.local_track_id)
        state = self._states.get(key)
        if state is None:
            if candidate_global_track_id is None:
                return (
                    self._unbound_event(
                        namespace,
                        local_track.local_track_id,
                        event="held",
                        candidate_global_track_id=None,
                        reason="no_feasible_measured_assignment",
                        measurement_timestamp=measurement_timestamp,
                        arrival_timestamp=arrival_timestamp,
                        candidate_margin=candidate_margin,
                        measured_evidence=True,
                    ),
                    None,
                )
            owner = self._owner_of_global(namespace, candidate_global_track_id)
            if owner is not None:
                return (
                    self._unbound_event(
                        namespace,
                        local_track.local_track_id,
                        event="held",
                        candidate_global_track_id=candidate_global_track_id,
                        reason="global_track_binding_already_active",
                        measurement_timestamp=measurement_timestamp,
                        arrival_timestamp=arrival_timestamp,
                        candidate_margin=candidate_margin,
                        measured_evidence=True,
                    ),
                    None,
                )
            state = _TrackBindingState(
                resource_id=namespace[0],
                camera_id=namespace[1],
                stream_id=namespace[2],
                local_track_id=local_track.local_track_id,
                bound_global_track_id=candidate_global_track_id,
                last_measured_track=local_track,
                last_measurement_timestamp=measurement_timestamp,
                last_arrival_timestamp=arrival_timestamp,
            )
            self._states[key] = state
            return (
                self._unbound_event(
                    namespace,
                    local_track.local_track_id,
                    event="confirmed",
                    candidate_global_track_id=candidate_global_track_id,
                    reason="initial_measured_binding",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                candidate_global_track_id,
            )

        incumbent = state.bound_global_track_id
        if candidate_global_track_id is None:
            self._clear_pending(state)
            state.was_coasting = True
            return (
                self._event(
                    state,
                    event="held",
                    candidate_global_track_id=None,
                    reason="no_feasible_measured_assignment",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                None,
            )

        if candidate_global_track_id == incumbent:
            recovered = state.was_coasting
            self._accept_measurement(
                state,
                local_track,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
            )
            return (
                self._event(
                    state,
                    event="recovered" if recovered else "continued",
                    candidate_global_track_id=candidate_global_track_id,
                    reason=(
                        "measured_binding_recovered_within_coast_window"
                        if recovered
                        else "measured_binding_continued"
                    ),
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                incumbent,
            )

        if pairwise_swap:
            self._clear_pending(state)
            state.was_coasting = True
            return (
                self._event(
                    state,
                    event="held",
                    candidate_global_track_id=candidate_global_track_id,
                    reason="pairwise_swap_or_crossing_ambiguity",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                None,
            )

        owner = self._owner_of_global(namespace, candidate_global_track_id, excluding=state.local_track_id)
        if owner is not None:
            self._clear_pending(state)
            state.was_coasting = True
            return (
                self._event(
                    state,
                    event="held",
                    candidate_global_track_id=candidate_global_track_id,
                    reason="global_track_binding_already_active",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                None,
            )

        required_margin = float(self.config.association_config.min_lock_margin)
        if candidate_margin is None or candidate_margin < required_margin:
            self._clear_pending(state)
            state.was_coasting = True
            return (
                self._event(
                    state,
                    event="held",
                    candidate_global_track_id=candidate_global_track_id,
                    reason="challenger_margin_below_min_lock_margin",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                None,
            )

        frame_token = _frame_token(frame_id, measurement_timestamp)
        if state.pending_challenger_id != candidate_global_track_id:
            state.pending_challenger_id = candidate_global_track_id
            state.pending_challenger_frames = 1
            state.pending_frame_token = frame_token
        elif state.pending_frame_token != frame_token:
            state.pending_challenger_frames += 1
            state.pending_frame_token = frame_token
        if state.pending_challenger_frames < self.config.challenger_required_frames:
            state.was_coasting = True
            return (
                self._event(
                    state,
                    event="pending",
                    candidate_global_track_id=candidate_global_track_id,
                    reason="challenger_requires_consecutive_measured_frames",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    candidate_margin=candidate_margin,
                    measured_evidence=True,
                ),
                None,
            )

        previous_global_track_id = state.bound_global_track_id
        state.bound_global_track_id = candidate_global_track_id
        self._accept_measurement(
            state,
            local_track,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        return (
            self._event(
                state,
                event="confirmed",
                incumbent_global_track_id=previous_global_track_id,
                candidate_global_track_id=candidate_global_track_id,
                reason="challenger_confirmed_after_consecutive_measured_frames",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                candidate_margin=candidate_margin,
                measured_evidence=True,
            ),
            candidate_global_track_id,
        )

    def _record_non_measured_input(
        self,
        namespace: tuple[str, str, str],
        local_track: LocalVisualTrack,
        camera: CameraModel,
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
    ) -> tuple[TemporalPredictionRecord | None, TemporalBindingEvent | None]:
        key = (*namespace, local_track.local_track_id)
        state = self._states.get(key)
        if state is None:
            age = float(local_track.prediction_age_s or 0.0)
            covariance = _prediction_covariance(
                camera,
                rate_sigma_px_s=self.config.effective_prediction_rate_sigma_px_s,
                prediction_age_s=age,
            )
            record = TemporalPredictionRecord(
                resource_id=namespace[0],
                camera_id=namespace[1],
                stream_id=namespace[2],
                local_track_id=local_track.local_track_id,
                bound_global_track_id=None,
                local_track_state=local_track.local_track_state,
                decision_state="hold",
                predicted_center_px=local_track.center_px,
                predicted_bbox=local_track.bbox,
                prediction_covariance_px=covariance,
                prediction_age_s=age,
                last_measurement_timestamp=None,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                metadata=self._prediction_metadata(covariance, age, generated=False),
            )
            event = self._unbound_event(
                namespace,
                local_track.local_track_id,
                event="held",
                candidate_global_track_id=None,
                reason="non_measured_track_has_no_binding_history",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                prediction_age_s=age,
                measured_evidence=False,
            )
            return record, event

        effective_age = max(
            measurement_timestamp - state.last_measurement_timestamp,
            float(local_track.prediction_age_s or 0.0),
        )
        if effective_age > self.config.coast_time_s:
            self._states.pop(key, None)
            return (
                None,
                self._event(
                    state,
                    event="expired",
                    candidate_global_track_id=None,
                    reason="prediction_age_exceeded_coast_window",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    prediction_age_s=effective_age,
                    measured_evidence=False,
                ),
            )
        record = self._prediction_record(
            state,
            camera,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            local_track=local_track,
        )
        state.was_coasting = True
        self._clear_pending(state)
        return (
            record,
            self._event(
                state,
                event="held",
                candidate_global_track_id=None,
                reason=f"non_measured_{local_track.local_track_state}_evidence",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                prediction_age_s=record.prediction_age_s,
                measured_evidence=False,
            ),
        )

    def _prediction_record(
        self,
        state: _TrackBindingState,
        camera: CameraModel,
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
        local_track: LocalVisualTrack | None,
    ) -> TemporalPredictionRecord:
        computed_age = max(0.0, measurement_timestamp - state.last_measurement_timestamp)
        provided_age = float(local_track.prediction_age_s or 0.0) if local_track is not None else 0.0
        age = max(computed_age, provided_age)
        if local_track is not None:
            center = local_track.center_px
            bbox = local_track.bbox
            local_state = local_track.local_track_state
            generated = False
        else:
            delta_px = state.last_measured_track.bearing_rate * age
            center = state.last_measured_track.center_px + delta_px
            bbox = _translated_bbox(state.last_measured_track.bbox, delta_px)
            local_state = "predicted"
            generated = True
        covariance = _prediction_covariance(
            camera,
            rate_sigma_px_s=self.config.effective_prediction_rate_sigma_px_s,
            prediction_age_s=age,
        )
        return TemporalPredictionRecord(
            resource_id=state.resource_id,
            camera_id=state.camera_id,
            stream_id=state.stream_id,
            local_track_id=state.local_track_id,
            bound_global_track_id=state.bound_global_track_id,
            local_track_state=local_state,
            decision_state="reacquire" if local_state == "lost" else "coast",
            predicted_center_px=center,
            predicted_bbox=bbox,
            prediction_covariance_px=covariance,
            prediction_age_s=age,
            last_measurement_timestamp=state.last_measurement_timestamp,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            metadata=self._prediction_metadata(covariance, age, generated=generated),
        )

    def _prediction_metadata(
        self,
        covariance: np.ndarray,
        prediction_age_s: float,
        *,
        generated: bool,
    ) -> dict[str, Any]:
        rate_sigma = self.config.effective_prediction_rate_sigma_px_s
        growth = (rate_sigma * prediction_age_s) ** 2
        return {
            "prediction_method": "constant_image_bearing_rate",
            "prediction_generated_by_temporal_associator": bool(generated),
            "prediction_rate_sigma_px_s": rate_sigma,
            "prediction_covariance_growth_px2": growth,
            "prediction_covariance_px": covariance.tolist(),
            "coast_time_s": self.config.coast_time_s,
            "non_authorizing_evidence": True,
        }

    def _pairwise_swap_local_ids(
        self,
        namespace: tuple[str, str, str],
        proposals: Mapping[str, str],
    ) -> set[str]:
        state_by_local = {
            state.local_track_id: state
            for key, state in self._states.items()
            if key[:3] == namespace
        }
        owner_by_global = {
            state.bound_global_track_id: state.local_track_id for state in state_by_local.values()
        }
        swap_ids: set[str] = set()
        for local_track_id, candidate_global_track_id in proposals.items():
            state = state_by_local.get(local_track_id)
            if state is None or candidate_global_track_id == state.bound_global_track_id:
                continue
            other_local_track_id = owner_by_global.get(candidate_global_track_id)
            if other_local_track_id is None or other_local_track_id == local_track_id:
                continue
            if proposals.get(other_local_track_id) == state.bound_global_track_id:
                swap_ids.update({local_track_id, other_local_track_id})
        return swap_ids

    def _apply_local_reset_markers(
        self,
        namespace: tuple[str, str, str],
        local_tracks: Iterable[LocalVisualTrack],
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
    ) -> list[TemporalBindingEvent]:
        events: list[TemporalBindingEvent] = []
        for local_track in local_tracks:
            if local_track.track_transition_state != "reset" and local_track.track_reset_reason is None:
                continue
            state = self._states.pop((*namespace, local_track.local_track_id), None)
            if state is None:
                continue
            events.append(
                self._event(
                    state,
                    event="expired",
                    candidate_global_track_id=None,
                    reason=f"local_track_reset:{local_track.track_reset_reason or 'unspecified'}",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    prediction_age_s=max(
                        0.0,
                        measurement_timestamp - state.last_measurement_timestamp,
                    ),
                    measured_evidence=False,
                )
            )
        return events

    def _expire_stale_states(
        self,
        namespace: tuple[str, str, str],
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
    ) -> list[TemporalBindingEvent]:
        events: list[TemporalBindingEvent] = []
        for key, state in list(self._states.items()):
            if key[:3] != namespace:
                continue
            age = measurement_timestamp - state.last_measurement_timestamp
            if age <= self.config.coast_time_s:
                continue
            self._states.pop(key, None)
            events.append(
                self._event(
                    state,
                    event="expired",
                    candidate_global_track_id=None,
                    reason="coast_window_expired",
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    prediction_age_s=max(0.0, age),
                    measured_evidence=False,
                )
            )
        return events

    def _reset_namespace(
        self,
        namespace: tuple[str, str, str],
        *,
        reason: str,
        measurement_timestamp: float,
        arrival_timestamp: float,
    ) -> list[TemporalBindingEvent]:
        events: list[TemporalBindingEvent] = []
        for key, state in list(self._states.items()):
            if key[:3] != namespace:
                continue
            self._states.pop(key, None)
            events.append(
                self._event(
                    state,
                    event="expired",
                    candidate_global_track_id=None,
                    reason=reason,
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    prediction_age_s=0.0,
                    measured_evidence=False,
                )
            )
        return events

    def _owner_of_global(
        self,
        namespace: tuple[str, str, str],
        global_track_id: str,
        *,
        excluding: str | None = None,
    ) -> str | None:
        for key, state in self._states.items():
            if key[:3] != namespace or state.local_track_id == excluding:
                continue
            if state.bound_global_track_id == global_track_id:
                return state.local_track_id
        return None

    @staticmethod
    def _accept_measurement(
        state: _TrackBindingState,
        local_track: LocalVisualTrack,
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
    ) -> None:
        state.last_measured_track = local_track
        state.last_measurement_timestamp = measurement_timestamp
        state.last_arrival_timestamp = arrival_timestamp
        state.was_coasting = False
        TemporalGeometricAssociator._clear_pending(state)

    @staticmethod
    def _clear_pending(state: _TrackBindingState) -> None:
        state.pending_challenger_id = None
        state.pending_challenger_frames = 0
        state.pending_frame_token = None

    @staticmethod
    def _event(
        state: _TrackBindingState,
        *,
        event: str,
        candidate_global_track_id: str | None,
        reason: str,
        measurement_timestamp: float,
        arrival_timestamp: float,
        candidate_margin: float | None = None,
        prediction_age_s: float | None = None,
        measured_evidence: bool,
        incumbent_global_track_id: str | None = None,
    ) -> TemporalBindingEvent:
        return TemporalBindingEvent(
            resource_id=state.resource_id,
            camera_id=state.camera_id,
            stream_id=state.stream_id,
            local_track_id=state.local_track_id,
            event=event,
            incumbent_global_track_id=(
                state.bound_global_track_id
                if incumbent_global_track_id is None
                else incumbent_global_track_id
            ),
            candidate_global_track_id=candidate_global_track_id,
            reason=reason,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            candidate_margin=candidate_margin,
            prediction_age_s=prediction_age_s,
            measured_evidence=measured_evidence,
        )

    @staticmethod
    def _unbound_event(
        namespace: tuple[str, str, str],
        local_track_id: str,
        *,
        event: str,
        candidate_global_track_id: str | None,
        reason: str,
        measurement_timestamp: float,
        arrival_timestamp: float,
        candidate_margin: float | None = None,
        prediction_age_s: float | None = None,
        measured_evidence: bool,
    ) -> TemporalBindingEvent:
        return TemporalBindingEvent(
            resource_id=namespace[0],
            camera_id=namespace[1],
            stream_id=namespace[2],
            local_track_id=local_track_id,
            event=event,
            incumbent_global_track_id=None,
            candidate_global_track_id=candidate_global_track_id,
            reason=reason,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            candidate_margin=candidate_margin,
            prediction_age_s=prediction_age_s,
            measured_evidence=measured_evidence,
        )


def _candidate_margin(
    result: GeometricAssociationResult,
    *,
    local_track_id: str,
    candidate_global_track_id: str | None,
    incumbent_global_track_id: str | None,
    cost_inf: float,
) -> float | None:
    if candidate_global_track_id is None:
        return None
    matrix = result.cost_matrix
    try:
        column = matrix.local_track_ids.index(local_track_id)
        candidate_row = matrix.global_track_ids.index(candidate_global_track_id)
    except ValueError:
        return None
    candidate_cost = float(matrix.costs[candidate_row, column])
    if not math.isfinite(candidate_cost) or candidate_cost >= cost_inf:
        return None
    if incumbent_global_track_id is not None and incumbent_global_track_id != candidate_global_track_id:
        try:
            incumbent_row = matrix.global_track_ids.index(incumbent_global_track_id)
        except ValueError:
            return math.inf
        incumbent_cost = float(matrix.costs[incumbent_row, column])
        if not math.isfinite(incumbent_cost) or incumbent_cost >= cost_inf:
            return math.inf
        return incumbent_cost - candidate_cost
    competitor_costs = [
        float(matrix.costs[row, column])
        for row in range(matrix.costs.shape[0])
        if row != candidate_row
        and math.isfinite(float(matrix.costs[row, column]))
        and float(matrix.costs[row, column]) < cost_inf
    ]
    if not competitor_costs:
        return math.inf
    return min(competitor_costs) - candidate_cost


def _prediction_covariance(
    camera: CameraModel,
    *,
    rate_sigma_px_s: float,
    prediction_age_s: float,
) -> np.ndarray:
    growth = (float(rate_sigma_px_s) * float(prediction_age_s)) ** 2
    return np.asarray(camera.measurement_cov, dtype=float) + np.eye(2, dtype=float) * growth


def _translated_bbox(
    bbox: tuple[float, float, float, float] | None,
    delta_px: np.ndarray,
) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    dx, dy = float(delta_px[0]), float(delta_px[1])
    x1, y1, x2, y2 = bbox
    return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


def _clock_rollback_reason(
    clock: _StreamClock | None,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> str | None:
    if clock is None:
        return None
    if measurement_timestamp < clock.measurement_timestamp:
        return "measurement_timestamp_rollback"
    if arrival_timestamp < clock.arrival_timestamp:
        return "arrival_timestamp_rollback"
    return None


def _namespace_matches(
    namespace: tuple[str, str, str],
    *,
    resource_id: str | None,
    camera_id: str | None,
    stream_id: str | None,
) -> bool:
    return bool(
        (resource_id is None or namespace[0] == resource_id)
        and (camera_id is None or namespace[1] == camera_id)
        and (stream_id is None or namespace[2] == stream_id)
    )


def _frame_token(frame_id: str | None, measurement_timestamp: float) -> str:
    if frame_id is not None:
        return f"frame:{frame_id}"
    return f"timestamp:{measurement_timestamp:.12g}"


def _required_id(value: str, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _require_finite_timestamp(value: float, name: str) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None
