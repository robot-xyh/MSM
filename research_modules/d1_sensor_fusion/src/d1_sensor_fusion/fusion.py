from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .ekf import EKFState, ekf_update, predict_to
from .motion import wrap_residual
from .observations import (
    RadarCovarianceConfig,
    measurement_model_for,
    radar_state_from_observation,
)
from .types import (
    COMMUNICATION_METADATA_KEYS,
    GlobalTrack,
    SensorObservation,
    TrackLevel,
    TrackUncertaintySummary,
)

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
        radar_covariance_config: RadarCovarianceConfig | dict | None = None,
        source_deduplication: bool = True,
    ) -> None:
        self.process_noise = float(process_noise)
        self.bucket_size = float(bucket_size)
        self.buffer_horizon = float(buffer_horizon)
        self.stable_threshold_m = float(stable_threshold_m)
        self.handover_threshold_m = float(handover_threshold_m)
        self.association_gate = float(association_gate)
        self.latency_compensation = bool(latency_compensation)
        self.use_truth_hints_for_association = bool(use_truth_hints_for_association)
        self.radar_covariance_config = (
            radar_covariance_config
            if isinstance(radar_covariance_config, RadarCovarianceConfig)
            else RadarCovarianceConfig(**dict(radar_covariance_config or {}))
        )
        self.source_deduplication = bool(source_deduplication)
        self.tracks: dict[str, TrackRecord] = {}
        self.current_time = 0.0
        self._next_track_id = 1
        self._processed_lineage_keys: set[tuple] = set()
        self.duplicate_observation_count = 0

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
        if self._is_duplicate_observation(effective):
            self.duplicate_observation_count += 1
            return self.global_tracks()

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
        if self._is_duplicate_observation(observation):
            self.duplicate_observation_count += 1
            record.current_state = predict_to(record.current_state, current_time, self.process_noise)
            return self._to_global_track(record)

        if observation.observation_id not in {obs.observation_id for obs in record.observations}:
            record.observations.append(observation)
        record.hits += 1
        record.source_support[observation.modality] += 1
        if observation.classification_hint:
            record.identity_likelihood[observation.classification_hint] += observation.confidence
        self._update_record_metadata_from_observation(record, observation)
        state, nises = self._replay_record(record, current_time)
        record.current_state = state
        record.recent_nis = deque(nises[-50:], maxlen=50)
        self._prune_record(record, current_time)
        self._mark_observation_processed(observation)
        return self._to_global_track(record)

    def global_tracks(self) -> list[GlobalTrack]:
        return [self._to_global_track(record) for record in self.tracks.values()]

    def track_uncertainty_summaries(self) -> list[TrackUncertaintySummary]:
        return [self.track_uncertainty_summary(track) for track in self.global_tracks()]

    def track_uncertainty_summary(self, track: GlobalTrack) -> TrackUncertaintySummary:
        metadata = dict(track.metadata)
        valid_at = float(metadata.get("valid_at", track.timestamp))
        published_at = float(metadata.get("published_at", self.current_time))
        measurement_timestamp = _optional_float(metadata.get("latest_measurement_timestamp"))
        arrival_timestamp = _optional_float(metadata.get("latest_arrival_timestamp"))
        if measurement_timestamp is not None:
            measurement_age_s = max(0.0, published_at - measurement_timestamp)
        else:
            measurement_age_s = max(0.0, published_at - valid_at)

        position_trace = float(np.trace(track.covariance[:3, :3]))
        velocity_trace = float(np.trace(track.covariance[3:, 3:]))
        a95 = float(metadata.get("a95_m", covariance_a95(track.covariance)))
        source_support = {str(key): int(value) for key, value in track.source_support.items()}
        source_diversity_count = sum(1 for count in source_support.values() if count > 0)
        readiness = self._handover_readiness(
            track.track_level,
            a95,
            measurement_age_s,
            source_diversity_count,
            track.last_nis,
        )
        return TrackUncertaintySummary(
            track_id=track.global_track_id,
            global_track_id=track.global_track_id,
            valid_at=valid_at,
            published_at=published_at,
            track_bucket=self._bucket(valid_at),
            track_level=track.track_level.value,
            position_covariance_trace=position_trace,
            velocity_covariance_trace=velocity_trace,
            a95_m=a95,
            measurement_age_s=measurement_age_s,
            source_support=source_support,
            coverage_cell=_optional_str(metadata.get("coverage_cell")),
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            source_diversity_count=source_diversity_count,
            last_nis=track.last_nis,
            handover_readiness=readiness,
            quality_flags=tuple(metadata.get("quality_flags", ())),
        )

    def _create_track(
        self,
        observation: SensorObservation,
        current_time: float,
    ) -> TrackRecord | None:
        if observation.modality != "radar":
            return None
        if self._is_duplicate_observation(observation):
            self.duplicate_observation_count += 1
            return None
        state, covariance = radar_state_from_observation(observation, self.radar_covariance_config)
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
            metadata={
                "truth_id": observation.metadata.get("truth_id"),
                **_metadata_from_observation(observation),
            },
        )
        self.tracks[track_id] = record
        self._mark_observation_processed(observation)
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
                obs_state, obs_cov = radar_state_from_observation(
                    observation,
                    self.radar_covariance_config,
                )
                diff = obs_state[:3] - state_at_measurement.state[:3]
                s = obs_cov[:3, :3] + state_at_measurement.covariance[:3, :3]
                s = s + 1e-6 * np.eye(3)
                return float(diff.T @ np.linalg.pinv(s) @ diff)
            return self._innovation_nis(state_at_measurement, observation)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            return np.inf

    def _innovation_nis(self, state: EKFState, observation: SensorObservation) -> float:
        model = measurement_model_for(observation, self.radar_covariance_config)
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
            model = measurement_model_for(observation, self.radar_covariance_config)
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
        state, covariance = radar_state_from_observation(earliest, self.radar_covariance_config)
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

    def _update_record_metadata_from_observation(
        self,
        record: TrackRecord,
        observation: SensorObservation,
    ) -> None:
        record.metadata.update(_metadata_from_observation(observation))
        if observation.metadata.get("truth_id") is not None:
            record.metadata.setdefault("truth_id", observation.metadata.get("truth_id"))
        source_node_id = observation.source_node_id or observation.metadata.get("source_node_id")
        if source_node_id:
            existing = set(record.metadata.get("source_node_ids", ()))
            existing.add(str(source_node_id))
            record.metadata["source_node_ids"] = tuple(sorted(existing))

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
                "source_support": dict(record.source_support),
                "duplicate_observation_count": self.duplicate_observation_count,
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

    def _handover_readiness(
        self,
        level: TrackLevel,
        a95_m: float,
        measurement_age_s: float,
        source_diversity_count: int,
        last_nis: float | None,
    ) -> float:
        eps = 1e-6
        covariance_score = min(1.0, self.handover_threshold_m / max(float(a95_m), eps))
        latency_budget_s = max(self.bucket_size, 1.0)
        latency_score = min(1.0, latency_budget_s / max(float(measurement_age_s), eps))
        source_score = min(1.0, source_diversity_count / 2.0)
        if last_nis is None:
            nis_score = 1.0
        else:
            nis_score = 1.0 if last_nis <= self.association_gate else 0.35
        level_score = {
            TrackLevel.HANDOVER: 1.0,
            TrackLevel.STABLE: 0.6,
            TrackLevel.COARSE: 0.2,
            TrackLevel.LOST: 0.0,
        }[level]
        return float(
            np.clip(
                min(covariance_score, latency_score, source_score, nis_score, level_score),
                0.0,
                1.0,
            )
        )

    def _is_duplicate_observation(self, observation: SensorObservation) -> bool:
        if not self.source_deduplication:
            return False
        return observation.source_lineage_key in self._processed_lineage_keys

    def _mark_observation_processed(self, observation: SensorObservation) -> None:
        if self.source_deduplication:
            self._processed_lineage_keys.add(observation.source_lineage_key)

    def ingest_many(self, observations: Iterable[SensorObservation]) -> list[GlobalTrack]:
        tracks: list[GlobalTrack] = []
        for observation in sorted(observations, key=lambda obs: obs.arrival_timestamp):
            tracks = self.process(observation)
        return tracks


def _metadata_from_observation(observation: SensorObservation) -> dict:
    metadata = {
        "latest_observation_id": observation.observation_id,
        "latest_sensor_id": observation.sensor_id,
        "latest_modality": observation.modality,
        "latest_measurement_timestamp": observation.measurement_timestamp,
        "latest_arrival_timestamp": observation.arrival_timestamp,
        "latest_observation_latency_s": observation.latency,
    }
    if observation.communication_latency is not None:
        metadata["latest_communication_latency_s"] = observation.communication_latency
    for key in COMMUNICATION_METADATA_KEYS:
        value = getattr(observation, key)
        if value is not None:
            metadata[key] = dict(value) if key == "source_support" else value
    if observation.source_node_id:
        metadata["source_node_ids"] = (observation.source_node_id,)
    for key in ("coverage_cell", "quality_flags"):
        if key in observation.metadata:
            metadata[key] = observation.metadata[key]
    return metadata


def _optional_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value) -> str | None:
    if value is None:
        return None
    return str(value)
