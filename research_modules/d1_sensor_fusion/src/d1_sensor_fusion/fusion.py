from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .ekf import EKFState, ekf_update, predict_to
from .motion import wrap_residual
from .observations import measurement_model_for, radar_state_from_observation
from .types import GlobalTrack, SensorObservation, TrackLevel

CHI2_2_95 = 5.991464547107979


def covariance_a95(covariance: np.ndarray) -> float:
    p_xy = np.asarray(covariance, dtype=float)[:2, :2]
    eigvals = np.linalg.eigvalsh(p_xy)
    return float(np.sqrt(CHI2_2_95 * max(float(eigvals[-1]), 0.0)))


@dataclass
class TrackRecord:
    track_id: str
    observations: list[SensorObservation]
    initial_state: EKFState
    initial_observation_id: str
    current_state: EKFState
    source_support: Counter = field(default_factory=Counter)
    identity_likelihood: Counter = field(default_factory=Counter)
    recent_nis: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    created_timestamp: float = 0.0
    hits: int = 0
    metadata: dict = field(default_factory=dict)


class FusionAdapter:
    """NumPy EKF fusion adapter with fixed-lag delay compensation.

    The adapter intentionally stays inside simulation/offline evaluation scope.
    It consumes canonical observations and outputs `GlobalTrack` objects. It has
    no control or automatic action interface.
    """

    def __init__(
        self,
        process_noise: float = 6.0,
        bucket_size: float = 0.1,
        buffer_horizon: float = 6.0,
        stable_threshold_m: float = 30.0,
        handover_threshold_m: float = 12.0,
        association_gate: float = 40.0,
        latency_compensation: bool = True,
        use_truth_hints_for_association: bool = False,
    ) -> None:
        self.process_noise = float(process_noise)
        self.bucket_size = float(bucket_size)
        self.buffer_horizon = float(buffer_horizon)
        self.stable_threshold_m = float(stable_threshold_m)
        self.handover_threshold_m = float(handover_threshold_m)
        self.association_gate = float(association_gate)
        self.latency_compensation = bool(latency_compensation)
        self.use_truth_hints_for_association = bool(use_truth_hints_for_association)
        self.tracks: dict[str, TrackRecord] = {}
        self.current_time = 0.0
        self._next_track_id = 1

    def _bucket(self, timestamp: float) -> int:
        """Return the fixed-lag cache bucket for a timestamp."""

        return int(np.floor((float(timestamp) + 1e-9) / self.bucket_size))

    def process(self, observation: SensorObservation) -> list[GlobalTrack]:
        """Process one arrived observation and return current global tracks."""

        current_time = max(self.current_time, float(observation.arrival_timestamp))
        self.current_time = current_time
        effective = observation
        if not self.latency_compensation:
            effective = observation.with_measurement_timestamp(observation.arrival_timestamp)

        self._predict_all_to(current_time)
        track_id = self._associate(effective)
        if track_id is None:
            record = self._create_track(effective, current_time)
            if record is None:
                self._predict_all_to(current_time)
                return self.global_tracks()
            track_id = record.track_id
        else:
            self.compensate_latency(track_id, effective, current_time)
        self._predict_all_to(current_time)
        return self.global_tracks()

    def predict_track(self, track: str | GlobalTrack, timestamp: float) -> GlobalTrack:
        """Predict an internal or detached track to `timestamp`."""

        if isinstance(track, GlobalTrack):
            state = predict_to(
                EKFState(track.state, track.covariance, track.timestamp),
                timestamp,
                self.process_noise,
            )
            out = track.copy()
            out.state = state.state
            out.covariance = state.covariance
            out.timestamp = state.timestamp
            return out

        record = self.tracks[str(track)]
        record.current_state = predict_to(record.current_state, timestamp, self.process_noise)
        return self._to_global_track(record)

    def update_at_measurement_time(
        self,
        observation: SensorObservation,
        track_id: str | None = None,
        current_time: float | None = None,
    ) -> GlobalTrack | None:
        """Update a track at the observation measurement time.

        If the observation is delayed, this method rewinds through the record's
        observation log and replays the state to `current_time`.
        """

        current_time = (
            float(observation.arrival_timestamp) if current_time is None else float(current_time)
        )
        if track_id is None:
            track_id = self._associate(observation)
        if track_id is None:
            record = self._create_track(observation, current_time)
            return None if record is None else self._to_global_track(record)
        return self.compensate_latency(track_id, observation, current_time)

    def compensate_latency(
        self,
        track_id: str,
        observation: SensorObservation,
        current_time: float | None = None,
    ) -> GlobalTrack:
        """Insert an observation by measurement time and replay to current time."""

        record = self.tracks[track_id]
        current_time = self.current_time if current_time is None else float(current_time)
        if observation.observation_id not in {obs.observation_id for obs in record.observations}:
            record.observations.append(observation)
        record.hits += 1
        record.source_support[observation.modality] += 1
        if observation.classification_hint:
            record.identity_likelihood[observation.classification_hint] += observation.confidence
        state, nises = self._replay_record(record, current_time)
        record.current_state = state
        record.recent_nis = deque(nises[-50:], maxlen=50)
        self._prune_record(record, current_time)
        return self._to_global_track(record)

    def global_tracks(self) -> list[GlobalTrack]:
        return [self._to_global_track(record) for record in self.tracks.values()]

    def _create_track(
        self,
        observation: SensorObservation,
        current_time: float,
    ) -> TrackRecord | None:
        if observation.modality != "radar":
            return None
        state, covariance = radar_state_from_observation(observation)
        initial = EKFState(state, covariance, observation.measurement_timestamp)
        current = predict_to(initial, current_time, self.process_noise)
        track_id = f"global_track_{self._next_track_id:03d}"
        self._next_track_id += 1
        source_support = Counter({observation.modality: 1})
        identity_likelihood: Counter = Counter()
        if observation.classification_hint:
            identity_likelihood[observation.classification_hint] += observation.confidence
        record = TrackRecord(
            track_id=track_id,
            observations=[observation],
            initial_state=initial,
            initial_observation_id=observation.observation_id,
            current_state=current,
            source_support=source_support,
            identity_likelihood=identity_likelihood,
            created_timestamp=observation.measurement_timestamp,
            hits=1,
            metadata={"truth_id": observation.metadata.get("truth_id")},
        )
        self.tracks[track_id] = record
        return record

    def _predict_all_to(self, timestamp: float) -> None:
        for record in self.tracks.values():
            if record.current_state.timestamp < timestamp - 1e-12:
                record.current_state = predict_to(record.current_state, timestamp, self.process_noise)

    def _associate(self, observation: SensorObservation) -> str | None:
        if not self.tracks:
            return None
        if self.use_truth_hints_for_association and "truth_id" in observation.metadata:
            truth_id = observation.metadata.get("truth_id")
            for track_id, record in self.tracks.items():
                if record.metadata.get("truth_id") == truth_id:
                    return track_id

        best_track_id: str | None = None
        best_score = np.inf
        for track_id, record in self.tracks.items():
            score = self._association_score(record, observation)
            if score < best_score:
                best_score = score
                best_track_id = track_id
        if best_score <= self.association_gate:
            return best_track_id
        return None

    def _association_score(self, record: TrackRecord, observation: SensorObservation) -> float:
        try:
            state_at_measurement = self._state_at(record, observation.measurement_timestamp)
            if observation.modality == "radar":
                obs_state, obs_cov = radar_state_from_observation(observation)
                diff = obs_state[:3] - state_at_measurement.state[:3]
                s = obs_cov[:3, :3] + state_at_measurement.covariance[:3, :3]
                s = s + 1e-6 * np.eye(3)
                return float(diff.T @ np.linalg.pinv(s) @ diff)
            return self._innovation_nis(state_at_measurement, observation)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            return np.inf

    def _innovation_nis(self, state: EKFState, observation: SensorObservation) -> float:
        model = measurement_model_for(observation)
        h = model.h_fn(state.state)
        h_j = model.h_jacobian_fn(state.state)
        residual = wrap_residual(model.z - h, model.angle_indices)
        s = h_j @ state.covariance @ h_j.T + model.r
        s = 0.5 * (s + s.T) + 1e-9 * np.eye(s.shape[0])
        return float(residual.T @ np.linalg.pinv(s) @ residual)

    def _state_at(self, record: TrackRecord, timestamp: float) -> EKFState:
        state, _ = self._replay_record(record, timestamp)
        return state

    def _replay_record(
        self,
        record: TrackRecord,
        until_time: float,
    ) -> tuple[EKFState, list[float]]:
        self._refresh_initial(record)
        state = record.initial_state.copy()
        nises: list[float] = []
        sorted_observations = sorted(
            record.observations,
            key=lambda obs: (obs.measurement_timestamp, obs.arrival_timestamp, obs.observation_id),
        )
        for observation in sorted_observations:
            if observation.observation_id == record.initial_observation_id:
                continue
            if observation.measurement_timestamp < state.timestamp - 1e-9:
                continue
            if observation.measurement_timestamp > until_time + 1e-9:
                continue
            state = predict_to(state, observation.measurement_timestamp, self.process_noise)
            model = measurement_model_for(observation)
            state, nis = ekf_update(
                state,
                model.z,
                model.h_fn,
                model.h_jacobian_fn,
                model.r,
                model.angle_indices,
            )
            nises.append(nis)
        state = predict_to(state, until_time, self.process_noise)
        return state, nises

    def _refresh_initial(self, record: TrackRecord) -> None:
        radar_observations = [obs for obs in record.observations if obs.modality == "radar"]
        if not radar_observations:
            return
        earliest = min(
            radar_observations,
            key=lambda obs: (obs.measurement_timestamp, obs.arrival_timestamp, obs.observation_id),
        )
        if earliest.observation_id == record.initial_observation_id:
            return
        state, covariance = radar_state_from_observation(earliest)
        record.initial_state = EKFState(state, covariance, earliest.measurement_timestamp)
        record.initial_observation_id = earliest.observation_id
        record.created_timestamp = earliest.measurement_timestamp

    def _prune_record(self, record: TrackRecord, current_time: float) -> None:
        """Keep all radar initializers but limit old non-essential observations."""

        if self.buffer_horizon <= 0:
            return
        min_time = current_time - self.buffer_horizon
        kept: list[SensorObservation] = []
        for obs in record.observations:
            if obs.observation_id == record.initial_observation_id or obs.measurement_timestamp >= min_time:
                kept.append(obs)
        record.observations = kept

    def _to_global_track(self, record: TrackRecord) -> GlobalTrack:
        level = self._classify(record)
        likelihood_sum = sum(record.identity_likelihood.values())
        identity_likelihood = (
            {key: value / likelihood_sum for key, value in record.identity_likelihood.items()}
            if likelihood_sum > 0
            else {}
        )
        last_nis = record.recent_nis[-1] if record.recent_nis else None
        metadata = dict(record.metadata)
        metadata.update(
            {
                "a95_m": covariance_a95(record.current_state.covariance),
                "frame_id": "ned",
                "valid_at": record.current_state.timestamp,
                "published_at": self.current_time,
                "hits": record.hits,
                "latency_compensation": self.latency_compensation,
            }
        )
        return GlobalTrack(
            global_track_id=record.track_id,
            state=record.current_state.state,
            covariance=record.current_state.covariance,
            timestamp=record.current_state.timestamp,
            track_level=level,
            source_support=dict(record.source_support),
            identity_likelihood=identity_likelihood,
            last_nis=last_nis,
            metadata=metadata,
        )

    def _classify(self, record: TrackRecord) -> TrackLevel:
        a95 = covariance_a95(record.current_state.covariance)
        source_count = sum(1 for count in record.source_support.values() if count > 0)
        if record.recent_nis:
            nis_pass_rate = sum(nis <= self.association_gate for nis in record.recent_nis) / len(
                record.recent_nis
            )
        else:
            nis_pass_rate = 1.0

        if (
            a95 <= self.handover_threshold_m
            and source_count >= 2
            and record.hits >= 8
            and nis_pass_rate >= 0.55
        ):
            return TrackLevel.HANDOVER
        if a95 <= self.stable_threshold_m and record.hits >= 3 and nis_pass_rate >= 0.45:
            return TrackLevel.STABLE
        return TrackLevel.COARSE

    def ingest_many(self, observations: Iterable[SensorObservation]) -> list[GlobalTrack]:
        tracks: list[GlobalTrack] = []
        for observation in sorted(observations, key=lambda obs: obs.arrival_timestamp):
            tracks = self.process(observation)
        return tracks
