from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from typing import Any, Iterable

import numpy as np

from .ekf import EKFState, ekf_update, predict_to
from .motion import wrap_residual
from .observations import (
    RadarCovarianceConfig,
    acoustic_covariance,
    eo_covariance_from_bbox,
    lidar_covariance,
    measurement_model_for,
    radar_covariance_from_range,
    radar_state_from_observation,
    sensor_position_from_metadata,
)
from .types import (
    COMMUNICATION_METADATA_KEYS,
    FusionQualityRegionSummary,
    GlobalTrack,
    LatencyAuditSummary,
    SensorHealthSummary,
    SensorObservation,
    TrackLevel,
    TrackUncertaintySummary,
)

CHI2_2_95 = 5.991464547107979
OBSERVATION_METADATA_LINEAGE_KEYS = (
    "coverage_cell",
    "quality_flags",
    "camera_id",
    "camera_name",
    "camera_model",
    "camera_metadata",
    "bbox",
    "bbox_xyxy",
    "center_px",
    "bbox_center_px",
    "eo_metadata",
    "detection_metadata",
    "detection_id",
    "local_track_id",
    "object_id_offline_only",
    "truth_object_id_offline_only",
    "recon_cue",
    "recon_cue_summary",
    "secondary_recon",
    "mobile_recon",
    "recon_node_id",
    "secondary_recon_node_id",
    "mobile_recon_node_id",
    "cue_source",
    "cue_position_ned",
    "cue_covariance",
    "coverage_cells",
    "timestamp_uncertainty_s",
    "timing_uncertainty_s",
    "clock_drift_s",
    "clock_offset_s",
    "timestamp_drift_s",
    "timestamp_jitter_s",
    "observation_covariance_limit_reasons",
    "track_covariance_limit_reasons",
    "covariance_limit_reasons",
    "covariance_limited",
    "covariance_limit_applied",
    "covariance_scale_reason",
    "observation_covariance_anomaly",
)
LOW_QUALITY_FLAGS = frozenset(
    {
        "low_quality",
        "poor_quality",
        "low_confidence",
        "degraded",
        "poor_snr",
        "clutter",
        "occluded",
        "partial_occlusion",
    }
)
OCCLUSION_FLAGS = frozenset({"occluded", "partial_occlusion"})
TRACK_COVARIANCE_FLOOR_DIAG = np.array([0.25, 0.25, 0.25, 0.04, 0.04, 0.04], dtype=float)
TRACK_COVARIANCE_CEILING_DIAG = np.array(
    [1_000_000.0, 1_000_000.0, 1_000_000.0, 10_000.0, 10_000.0, 10_000.0],
    dtype=float,
)
MEASUREMENT_COVARIANCE_CEILING = 1.0e6
MEASUREMENT_COVARIANCE_FLOORS = {
    "radar": np.array([1.0e-2, 1.0e-8, 1.0e-8, 1.0e-4], dtype=float),
    "acoustic": np.array([1.0e-8], dtype=float),
    "eo": np.array([0.25, 0.25], dtype=float),
    "lidar": np.array([1.0e-2, 1.0e-2, 1.0e-2], dtype=float),
}


def _state_bound_diag(
    value: Iterable[float] | None,
    default: np.ndarray,
    name: str,
) -> np.ndarray:
    if value is None:
        return np.asarray(default, dtype=float).copy()
    array = np.asarray(tuple(value), dtype=float).reshape(-1)
    if array.size != 6:
        raise ValueError(f"{name} must contain six diagonal bounds")
    if not np.isfinite(array).all() or np.any(array <= 0.0):
        raise ValueError(f"{name} must contain positive finite values")
    return array


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
    covariance_limit_reasons: Counter = field(default_factory=Counter)
    metadata: dict = field(default_factory=dict)


@dataclass
class SensorHealthState:
    sensor_id: str
    observation_count: int = 0
    duplicate_count: int = 0
    reject_count: int = 0
    oosm_count: int = 0
    stale_count: int = 0
    low_quality_count: int = 0
    anomalous_covariance_count: int = 0
    timestamp_uncertainty_count: int = 0
    max_timestamp_uncertainty_s: float = 0.0
    latest_observation_timestamp: float | None = None
    fault_reasons: Counter = field(default_factory=Counter)
    nominal_after_fault_count: int = 0


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
        covariance_floor_diag: Iterable[float] | None = None,
        covariance_ceiling_diag: Iterable[float] | None = None,
        long_extrapolation_s: float = 3.0,
        low_quality_confidence_threshold: float = 0.5,
        timestamp_uncertainty_fault_s: float = 0.05,
        sensor_isolation_reject_threshold: int = 3,
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
        self.covariance_floor_diag = _state_bound_diag(
            covariance_floor_diag,
            TRACK_COVARIANCE_FLOOR_DIAG,
            "covariance_floor_diag",
        )
        self.covariance_ceiling_diag = _state_bound_diag(
            covariance_ceiling_diag,
            TRACK_COVARIANCE_CEILING_DIAG,
            "covariance_ceiling_diag",
        )
        if np.any(self.covariance_ceiling_diag < self.covariance_floor_diag):
            raise ValueError("covariance_ceiling_diag must be greater than covariance_floor_diag")
        self.long_extrapolation_s = float(long_extrapolation_s)
        self.low_quality_confidence_threshold = float(low_quality_confidence_threshold)
        self.timestamp_uncertainty_fault_s = float(timestamp_uncertainty_fault_s)
        self.sensor_isolation_reject_threshold = int(sensor_isolation_reject_threshold)
        self.tracks: dict[str, TrackRecord] = {}
        self.sensor_health: dict[str, SensorHealthState] = {}
        self.current_time = 0.0
        self._next_track_id = 1
        self._processed_lineage_keys: set[tuple] = set()
        self.duplicate_observation_count = 0
        self.observation_count = 0
        self.replay_count = 0
        self.oosm_observation_count = 0
        self.stale_observation_count = 0
        self.stale_or_oosm_observation_count = 0
        self.max_delay_s = 0.0
        self._latency_delay_sum_s = 0.0
        self.max_replay_observation_count = 0

    def _bucket(self, timestamp: float) -> int:
        """Return the fixed-lag cache bucket for a timestamp."""

        return int(np.floor((float(timestamp) + 1e-9) / self.bucket_size))

    def process(self, observation: SensorObservation) -> list[GlobalTrack]:
        """Process one arrived observation and return current global tracks."""

        observation = self._prepare_observation(observation)
        previous_time = self.current_time
        current_time = max(self.current_time, float(observation.arrival_timestamp))
        self.current_time = current_time
        is_oosm, is_stale = self._record_latency_audit(observation, previous_time, current_time)
        self._record_sensor_observation(
            observation,
            is_oosm=is_oosm,
            is_stale=is_stale,
        )
        effective = observation
        if not self.latency_compensation:
            effective = observation.with_measurement_timestamp(observation.arrival_timestamp)

        self._predict_all_to(current_time)
        if self._is_duplicate_observation(effective):
            self.duplicate_observation_count += 1
            self._record_sensor_fault(effective, "duplicate_observation", rejected=True)
            return self.global_tracks()

        track_id = self._associate(effective)
        if track_id is None:
            record = self._create_track(effective, current_time)
            if record is None:
                self._record_sensor_fault(
                    effective,
                    "unsupported_track_initializer",
                    rejected=True,
                )
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
            previous_timestamp = float(track.timestamp)
            state = predict_to(
                EKFState(track.state, track.covariance, track.timestamp),
                timestamp,
                self.process_noise,
            )
            out = track.copy()
            out.state = state.state
            reasons = []
            if float(timestamp) - previous_timestamp > self.long_extrapolation_s:
                reasons.append("long_extrapolation")
            out.covariance, applied = self._limit_state_covariance(state.covariance, reasons)
            out.timestamp = state.timestamp
            self._update_metadata_covariance_reasons(out.metadata, applied)
            return out

        record = self.tracks[str(track)]
        previous_timestamp = float(record.current_state.timestamp)
        record.current_state = predict_to(record.current_state, timestamp, self.process_noise)
        reasons = []
        if float(timestamp) - previous_timestamp > self.long_extrapolation_s:
            reasons.append("long_extrapolation")
        self._limit_record_covariance(record, reasons)
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

        observation = self._prepare_observation(observation)
        current_time = (
            float(observation.arrival_timestamp) if current_time is None else float(current_time)
        )
        self._record_sensor_observation(
            observation,
            is_oosm=observation.measurement_timestamp < current_time - 1e-9,
            is_stale=observation.is_stale_at(current_time),
        )
        if track_id is None:
            track_id = self._associate(observation)
        if track_id is None:
            record = self._create_track(observation, current_time)
            if record is None:
                self._record_sensor_fault(
                    observation,
                    "unsupported_track_initializer",
                    rejected=True,
                )
            return None if record is None else self._to_global_track(record)
        return self.compensate_latency(track_id, observation, current_time)

    def compensate_latency(
        self,
        track_id: str,
        observation: SensorObservation,
        current_time: float | None = None,
    ) -> GlobalTrack:
        """Insert an observation by measurement time and replay to current time."""

        observation = self._prepare_observation(observation)
        record = self.tracks[track_id]
        current_time = self.current_time if current_time is None else float(current_time)
        if self._is_duplicate_observation(observation):
            self.duplicate_observation_count += 1
            self._record_sensor_fault(observation, "duplicate_observation", rejected=True)
            record.current_state = predict_to(record.current_state, current_time, self.process_noise)
            self._limit_record_covariance(record)
            return self._to_global_track(record)

        inserted_observation = False
        if observation.observation_id not in {obs.observation_id for obs in record.observations}:
            record.observations.append(observation)
            inserted_observation = True
        self._record_replay_audit(record, inserted_observation)
        record.hits += 1
        record.source_support[observation.modality] += 1
        if observation.classification_hint:
            record.identity_likelihood[observation.classification_hint] += observation.confidence
        self._update_record_metadata_from_observation(record, observation)
        state, nises = self._replay_record(record, current_time)
        record.current_state = state
        record.recent_nis = deque(nises[-50:], maxlen=50)
        self._limit_record_covariance(record)
        self._prune_record(record, current_time)
        self._mark_observation_processed(observation)
        return self._to_global_track(record)

    def global_tracks(self) -> list[GlobalTrack]:
        return [self._to_global_track(record) for record in self.tracks.values()]

    def track_uncertainty_summaries(self) -> list[TrackUncertaintySummary]:
        return [self.track_uncertainty_summary(track) for track in self.global_tracks()]

    def sensor_health_summaries(self) -> list[SensorHealthSummary]:
        return [
            self._sensor_health_summary(self.sensor_health[sensor_id])
            for sensor_id in sorted(self.sensor_health)
        ]

    def track_uncertainty_summary(self, track: GlobalTrack) -> TrackUncertaintySummary:
        metadata = dict(track.metadata)
        valid_at = float(metadata.get("valid_at", track.timestamp))
        published_at = float(metadata.get("published_at", self.current_time))
        measurement_timestamp = _optional_float(metadata.get("latest_measurement_timestamp"))
        arrival_timestamp = _optional_float(metadata.get("latest_arrival_timestamp"))
        timestamp_uncertainty_s = _optional_float(
            metadata.get("latest_timestamp_uncertainty_s", metadata.get("timestamp_uncertainty_s"))
        )
        if timestamp_uncertainty_s is None:
            timestamp_uncertainty_s = 0.0
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
            timestamp_uncertainty_s=float(timestamp_uncertainty_s),
            covariance_limit_reasons=_metadata_reasons(metadata.get("covariance_limit_reasons")),
            source_diversity_count=source_diversity_count,
            last_nis=track.last_nis,
            handover_readiness=readiness,
            quality_flags=tuple(metadata.get("quality_flags", ())),
        )

    def latency_audit_summary(self) -> LatencyAuditSummary:
        mean_delay_s = (
            self._latency_delay_sum_s / self.observation_count
            if self.observation_count > 0
            else 0.0
        )
        return LatencyAuditSummary(
            observation_count=self.observation_count,
            replay_count=self.replay_count,
            oosm_observation_count=self.oosm_observation_count,
            stale_observation_count=self.stale_observation_count,
            stale_or_oosm_observation_count=self.stale_or_oosm_observation_count,
            max_delay_s=self.max_delay_s,
            mean_delay_s=mean_delay_s,
            duplicate_observation_count=self.duplicate_observation_count,
            max_replay_observation_count=self.max_replay_observation_count,
            latency_compensation=self.latency_compensation,
        )

    def region_quality_summaries(
        self,
        required_modalities: Iterable[str] = ("radar", "eo", "acoustic"),
        stale_age_s: float | None = None,
    ) -> list[FusionQualityRegionSummary]:
        grouped: dict[str, list[TrackUncertaintySummary]] = {}
        for summary in self.track_uncertainty_summaries():
            coverage_cell = summary.coverage_cell or "unassigned"
            grouped.setdefault(coverage_cell, []).append(summary)

        stale_threshold = max(self.bucket_size, 1.0) if stale_age_s is None else float(stale_age_s)
        required = tuple(str(modality) for modality in required_modalities)
        return [
            self._region_quality_summary(coverage_cell, grouped[coverage_cell], required, stale_threshold)
            for coverage_cell in sorted(grouped)
        ]

    def _region_quality_summary(
        self,
        coverage_cell: str,
        summaries: list[TrackUncertaintySummary],
        required_modalities: tuple[str, ...],
        stale_age_s: float,
    ) -> FusionQualityRegionSummary:
        source_support: Counter = Counter()
        quality_flags: set[str] = set()
        for summary in summaries:
            source_support.update(summary.source_support)
            quality_flags.update(str(flag) for flag in summary.quality_flags)

        a95_values = [summary.a95_m for summary in summaries]
        readiness_values = [summary.handover_readiness for summary in summaries]
        age_values = [summary.measurement_age_s for summary in summaries]
        growth_rates = [
            float(summary.covariance_growth_rate)
            for summary in summaries
            if summary.covariance_growth_rate is not None
        ]
        level_counts = Counter(summary.track_level for summary in summaries)
        source_gap_modalities = tuple(
            modality for modality in required_modalities if source_support.get(modality, 0) <= 0
        )
        return FusionQualityRegionSummary(
            coverage_cell=coverage_cell,
            published_at=max(summary.published_at for summary in summaries),
            track_count=len(summaries),
            coarse_track_count=int(level_counts.get(TrackLevel.COARSE.value, 0)),
            stable_track_count=int(level_counts.get(TrackLevel.STABLE.value, 0)),
            handover_track_count=int(level_counts.get(TrackLevel.HANDOVER.value, 0)),
            stale_track_count=sum(1 for age in age_values if age > stale_age_s),
            mean_a95_m=float(np.mean(a95_values)) if a95_values else 0.0,
            max_a95_m=float(max(a95_values)) if a95_values else 0.0,
            max_measurement_age_s=float(max(age_values)) if age_values else 0.0,
            mean_handover_readiness=float(np.mean(readiness_values)) if readiness_values else 0.0,
            source_support={str(key): int(value) for key, value in source_support.items()},
            source_gap_modalities=source_gap_modalities,
            quality_flags=tuple(sorted(quality_flags)),
            mean_covariance_growth_rate=float(np.mean(growth_rates)) if growth_rates else None,
            max_covariance_growth_rate=float(max(growth_rates)) if growth_rates else None,
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
        self._limit_record_covariance(record)
        self.tracks[track_id] = record
        self._mark_observation_processed(observation)
        return record

    def _predict_all_to(self, timestamp: float) -> None:
        for record in self.tracks.values():
            if record.current_state.timestamp < timestamp - 1e-12:
                previous_timestamp = float(record.current_state.timestamp)
                record.current_state = predict_to(record.current_state, timestamp, self.process_noise)
                reasons = []
                if float(timestamp) - previous_timestamp > self.long_extrapolation_s:
                    reasons.append("long_extrapolation")
                self._limit_record_covariance(record, reasons)

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
        for reason in _metadata_reasons(observation.metadata.get("covariance_limit_reasons")):
            record.covariance_limit_reasons[reason] += 1
        if observation.metadata.get("truth_id") is not None:
            record.metadata.setdefault("truth_id", observation.metadata.get("truth_id"))
        source_node_id = observation.source_node_id or observation.metadata.get("source_node_id")
        if source_node_id:
            existing = set(record.metadata.get("source_node_ids", ()))
            existing.add(str(source_node_id))
            record.metadata["source_node_ids"] = tuple(sorted(existing))

    def _to_global_track(self, record: TrackRecord) -> GlobalTrack:
        self._limit_record_covariance(record)
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
                "latency_audit": self.latency_audit_summary().to_dict(),
                "sensor_health": {
                    summary.sensor_id: summary.to_dict()
                    for summary in self.sensor_health_summaries()
                },
            }
        )
        self._update_metadata_covariance_reasons(
            metadata,
            tuple(sorted(record.covariance_limit_reasons)),
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

    def _prepare_observation(self, observation: SensorObservation) -> SensorObservation:
        covariance, reasons, anomaly = self._limited_observation_covariance(observation)
        metadata = dict(observation.metadata)
        metadata["timestamp_uncertainty_s"] = float(observation.timestamp_uncertainty_s or 0.0)
        metadata["timing_uncertainty_s"] = float(observation.timestamp_uncertainty_s or 0.0)
        if reasons:
            existing = set(_metadata_reasons(metadata.get("covariance_limit_reasons")))
            all_reasons = tuple(sorted(existing | set(reasons)))
            metadata["observation_covariance_limit_reasons"] = tuple(reasons)
            metadata["covariance_limit_reasons"] = all_reasons
            metadata["covariance_limited"] = True
            metadata["covariance_limit_applied"] = True
        if anomaly:
            metadata["observation_covariance_anomaly"] = True
        scale_reason = self._covariance_scale_reason(observation)
        if scale_reason is not None:
            metadata["covariance_scale_reason"] = scale_reason
        return replace(observation, covariance=covariance, metadata=metadata)

    def _limited_observation_covariance(
        self,
        observation: SensorObservation,
    ) -> tuple[np.ndarray, tuple[str, ...], bool]:
        reasons: list[str] = []
        anomaly = False
        default_covariance = self._default_measurement_covariance(observation)
        expected_dim = default_covariance.shape[0]
        covariance = observation.covariance
        if covariance is None:
            covariance = default_covariance
        else:
            try:
                covariance = np.asarray(covariance, dtype=float)
                if covariance.ndim == 0:
                    covariance = covariance.reshape(1, 1)
                if covariance.ndim == 1:
                    size = int(np.sqrt(covariance.size))
                    if size * size == covariance.size:
                        covariance = covariance.reshape(size, size)
                    elif covariance.size == expected_dim:
                        covariance = np.diag(covariance)
                if covariance.shape != (expected_dim, expected_dim):
                    reasons.append("observation_covariance_shape_reset")
                    anomaly = True
                    covariance = default_covariance
            except (TypeError, ValueError):
                reasons.append("observation_covariance_invalid_reset")
                anomaly = True
                covariance = default_covariance

        covariance = np.asarray(covariance, dtype=float)
        if not np.isfinite(covariance).all():
            reasons.append("observation_covariance_nonfinite_reset")
            anomaly = True
            covariance = default_covariance

        covariance = 0.5 * (covariance + covariance.T)
        quality_scale = self._observation_quality_covariance_scale(observation)
        if quality_scale > 1.0:
            covariance = covariance * quality_scale
            reasons.append(self._covariance_scale_reason(observation) or "low_quality_observation")

        floor = MEASUREMENT_COVARIANCE_FLOORS.get(
            observation.modality,
            np.full(expected_dim, 1.0e-8, dtype=float),
        )
        if floor.size != expected_dim:
            floor = np.resize(floor, expected_dim)
        ceiling = np.full(expected_dim, MEASUREMENT_COVARIANCE_CEILING, dtype=float)
        covariance, bound_reasons = _limit_covariance_diagonal(
            covariance,
            floor,
            ceiling,
            floor_reason="observation_covariance_floor",
            ceiling_reason="observation_covariance_ceiling",
        )
        reasons.extend(bound_reasons)
        if any(
            reason
            in {
                "observation_covariance_shape_reset",
                "observation_covariance_invalid_reset",
                "observation_covariance_nonfinite_reset",
                "observation_covariance_floor",
                "observation_covariance_ceiling",
            }
            for reason in reasons
        ):
            anomaly = True
        return covariance, tuple(dict.fromkeys(reasons)), anomaly

    def _default_measurement_covariance(self, observation: SensorObservation) -> np.ndarray:
        if observation.modality == "radar":
            distance = float(observation.measurement.reshape(-1)[0])
            return radar_covariance_from_range(distance, self.radar_covariance_config)
        if observation.modality == "acoustic":
            return acoustic_covariance(observation.confidence)
        if observation.modality == "eo":
            bbox = observation.metadata.get("bbox")
            if bbox is None:
                bbox = observation.metadata.get("bbox_xyxy")
            return eo_covariance_from_bbox(bbox, observation.confidence, observation.quality_flags)
        if observation.modality == "lidar":
            sensor_position = sensor_position_from_metadata(observation)
            z = observation.measurement.reshape(-1)[:3]
            distance = float(np.linalg.norm(z - sensor_position))
            return lidar_covariance(distance, observation.confidence)
        raise ValueError(f"Unsupported modality: {observation.modality}")

    def _observation_quality_covariance_scale(self, observation: SensorObservation) -> float:
        flags = {str(flag).lower() for flag in observation.quality_flags}
        scale = 1.0
        if observation.confidence < self.low_quality_confidence_threshold:
            confidence = max(float(observation.confidence), 0.05)
            scale = max(scale, self.low_quality_confidence_threshold / confidence)
        if flags & OCCLUSION_FLAGS:
            scale = max(scale, 2.0)
        if flags & (LOW_QUALITY_FLAGS - OCCLUSION_FLAGS):
            scale = max(scale, 1.5)
        return float(min(scale, 4.0))

    def _covariance_scale_reason(self, observation: SensorObservation) -> str | None:
        flags = {str(flag).lower() for flag in observation.quality_flags}
        if flags & OCCLUSION_FLAGS:
            return "occluded_observation"
        if observation.confidence < self.low_quality_confidence_threshold or (
            flags & (LOW_QUALITY_FLAGS - OCCLUSION_FLAGS)
        ):
            return "low_quality_observation"
        return None

    def _limit_record_covariance(
        self,
        record: TrackRecord,
        reasons: Iterable[str] = (),
    ) -> None:
        covariance, applied = self._limit_state_covariance(record.current_state.covariance, reasons)
        record.current_state = EKFState(
            record.current_state.state,
            covariance,
            record.current_state.timestamp,
        )
        for reason in applied:
            record.covariance_limit_reasons[str(reason)] += 1
        if applied:
            self._update_metadata_covariance_reasons(record.metadata, tuple(applied))

    def _limit_state_covariance(
        self,
        covariance: np.ndarray,
        reasons: Iterable[str] = (),
    ) -> tuple[np.ndarray, tuple[str, ...]]:
        base_reasons = [str(reason) for reason in reasons]
        covariance = np.asarray(covariance, dtype=float)
        if covariance.shape != (6, 6) or not np.isfinite(covariance).all():
            covariance = np.diag(self.covariance_ceiling_diag)
            base_reasons.append("track_covariance_invalid_reset")
        covariance = 0.5 * (covariance + covariance.T)
        covariance, bound_reasons = _limit_covariance_diagonal(
            covariance,
            self.covariance_floor_diag,
            self.covariance_ceiling_diag,
            floor_reason="track_covariance_floor",
            ceiling_reason="track_covariance_ceiling",
        )
        base_reasons.extend(bound_reasons)
        return covariance, tuple(dict.fromkeys(base_reasons))

    def _update_metadata_covariance_reasons(
        self,
        metadata: dict,
        reasons: Iterable[str],
    ) -> None:
        _update_metadata_covariance_reasons(metadata, reasons)

    def _record_sensor_observation(
        self,
        observation: SensorObservation,
        *,
        is_oosm: bool,
        is_stale: bool,
    ) -> None:
        state = self.sensor_health.setdefault(
            observation.sensor_id,
            SensorHealthState(sensor_id=observation.sensor_id),
        )
        state.observation_count += 1
        state.latest_observation_timestamp = float(observation.arrival_timestamp)
        state.max_timestamp_uncertainty_s = max(
            state.max_timestamp_uncertainty_s,
            float(observation.timestamp_uncertainty_s or 0.0),
        )

        faults: list[str] = []
        if is_oosm:
            state.oosm_count += 1
            faults.append("oosm_observation")
        if is_stale:
            state.stale_count += 1
            faults.append("stale_observation")
        if self._covariance_scale_reason(observation) is not None:
            state.low_quality_count += 1
            faults.append(self._covariance_scale_reason(observation) or "low_quality_observation")
        if observation.metadata.get("observation_covariance_anomaly"):
            state.anomalous_covariance_count += 1
            faults.append("anomalous_covariance")
        if float(observation.timestamp_uncertainty_s or 0.0) >= self.timestamp_uncertainty_fault_s:
            state.timestamp_uncertainty_count += 1
            faults.append("timestamp_uncertainty")

        if faults:
            for reason in dict.fromkeys(faults):
                state.fault_reasons[str(reason)] += 1
            state.nominal_after_fault_count = 0
        elif state.fault_reasons:
            state.nominal_after_fault_count += 1

    def _record_sensor_fault(
        self,
        observation: SensorObservation,
        reason: str,
        *,
        rejected: bool,
    ) -> None:
        state = self.sensor_health.setdefault(
            observation.sensor_id,
            SensorHealthState(sensor_id=observation.sensor_id),
        )
        if rejected:
            state.reject_count += 1
        if reason == "duplicate_observation":
            state.duplicate_count += 1
        state.fault_reasons[str(reason)] += 1
        state.nominal_after_fault_count = 0

    def _sensor_health_summary(self, state: SensorHealthState) -> SensorHealthSummary:
        fault_reasons = tuple(sorted(state.fault_reasons))
        fault_reason = _most_common_reason(state.fault_reasons)
        status = self._sensor_status(state)
        return SensorHealthSummary(
            sensor_id=state.sensor_id,
            status=status,
            fault_reason=fault_reason,
            reject_count=state.reject_count,
            isolation_hint=_isolation_hint(fault_reason, status),
            recovery_state=self._sensor_recovery_state(state, status),
            observation_count=state.observation_count,
            duplicate_count=state.duplicate_count,
            oosm_count=state.oosm_count,
            stale_count=state.stale_count,
            low_quality_count=state.low_quality_count,
            anomalous_covariance_count=state.anomalous_covariance_count,
            timestamp_uncertainty_s=state.max_timestamp_uncertainty_s,
            latest_observation_timestamp=state.latest_observation_timestamp,
            fault_reasons=fault_reasons,
        )

    def _sensor_status(self, state: SensorHealthState) -> str:
        if (
            state.reject_count >= self.sensor_isolation_reject_threshold
            or state.anomalous_covariance_count >= self.sensor_isolation_reject_threshold
            or state.stale_count + state.oosm_count >= self.sensor_isolation_reject_threshold
        ):
            return "isolated"
        if state.fault_reasons:
            return "degraded"
        return "nominal"

    def _sensor_recovery_state(self, state: SensorHealthState, status: str) -> str:
        if status == "isolated":
            return "isolation_recommended"
        if status == "degraded" and state.nominal_after_fault_count > 0:
            return "recovering"
        if status == "degraded":
            return "monitoring_fault"
        return "healthy"

    def _record_latency_audit(
        self,
        observation: SensorObservation,
        previous_time: float,
        current_time: float,
    ) -> tuple[bool, bool]:
        delay_s = max(0.0, float(observation.latency))
        self.observation_count += 1
        self._latency_delay_sum_s += delay_s
        self.max_delay_s = max(self.max_delay_s, delay_s)

        is_oosm = observation.measurement_timestamp < float(previous_time) - 1e-9
        is_stale = observation.is_stale_at(current_time)
        if observation.stale_after_s is not None and delay_s > observation.stale_after_s:
            is_stale = True

        if is_oosm:
            self.oosm_observation_count += 1
        if is_stale:
            self.stale_observation_count += 1
        if is_oosm or is_stale:
            self.stale_or_oosm_observation_count += 1
        return is_oosm, is_stale

    def _record_replay_audit(self, record: TrackRecord, inserted_observation: bool) -> None:
        if not inserted_observation:
            return
        self.replay_count += 1
        self.max_replay_observation_count = max(
            self.max_replay_observation_count,
            len(record.observations),
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
        "latest_timestamp_uncertainty_s": float(observation.timestamp_uncertainty_s or 0.0),
        "timestamp_uncertainty_s": float(observation.timestamp_uncertainty_s or 0.0),
        "timing_uncertainty_s": float(observation.timestamp_uncertainty_s or 0.0),
    }
    if observation.communication_latency is not None:
        metadata["latest_communication_latency_s"] = observation.communication_latency
    for key in COMMUNICATION_METADATA_KEYS:
        value = getattr(observation, key)
        if value is not None:
            metadata[key] = dict(value) if key == "source_support" else value
    if observation.source_node_id:
        metadata["source_node_ids"] = (observation.source_node_id,)
    for key in OBSERVATION_METADATA_LINEAGE_KEYS:
        if key in observation.metadata:
            metadata[key] = _jsonable_metadata_value(observation.metadata[key])
    if observation.quality_flags and "quality_flags" not in metadata:
        metadata["quality_flags"] = tuple(str(flag) for flag in observation.quality_flags)
    return metadata


def _limit_covariance_diagonal(
    covariance: np.ndarray,
    floor_diag: np.ndarray,
    ceiling_diag: np.ndarray,
    *,
    floor_reason: str,
    ceiling_reason: str,
) -> tuple[np.ndarray, tuple[str, ...]]:
    covariance = np.asarray(covariance, dtype=float)
    floor_diag = np.asarray(floor_diag, dtype=float).reshape(-1)
    ceiling_diag = np.asarray(ceiling_diag, dtype=float).reshape(-1)
    if covariance.shape != (floor_diag.size, floor_diag.size):
        raise ValueError("covariance shape does not match diagonal bounds")

    reasons: list[str] = []
    bounded = 0.5 * (covariance + covariance.T)
    diag = np.diag(bounded).copy()
    if np.any(diag < floor_diag):
        reasons.append(floor_reason)
    if np.any(diag > ceiling_diag):
        reasons.append(ceiling_reason)
    clipped_diag = np.clip(diag, floor_diag, ceiling_diag)
    np.fill_diagonal(bounded, clipped_diag)

    for row in range(bounded.shape[0]):
        for col in range(row + 1, bounded.shape[1]):
            limit = 0.999 * np.sqrt(max(bounded[row, row], 0.0) * max(bounded[col, col], 0.0))
            bounded[row, col] = float(np.clip(bounded[row, col], -limit, limit))
            bounded[col, row] = bounded[row, col]
    return bounded, tuple(dict.fromkeys(reasons))


def _metadata_reasons(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(str(key) for key, count in value.items() if int(count) > 0)
    return tuple(str(item) for item in value)


def _update_metadata_covariance_reasons(metadata: dict, reasons: Iterable[str]) -> None:
    existing = set(_metadata_reasons(metadata.get("covariance_limit_reasons")))
    incoming = {str(reason) for reason in reasons if str(reason)}
    if not incoming:
        return
    merged = tuple(sorted(existing | incoming))
    metadata["covariance_limit_reasons"] = merged
    metadata["track_covariance_limit_reasons"] = merged
    metadata["covariance_limited"] = True
    metadata["covariance_limit_applied"] = True


def _most_common_reason(counter: Counter) -> str | None:
    if not counter:
        return None
    return str(counter.most_common(1)[0][0])


def _isolation_hint(fault_reason: str | None, status: str) -> str | None:
    if status == "nominal":
        return None
    if fault_reason in {"oosm_observation", "stale_observation", "timestamp_uncertainty"}:
        return "check_clock_sync"
    if fault_reason == "duplicate_observation":
        return "suppress_duplicate_payload"
    if fault_reason == "anomalous_covariance":
        return "validate_sensor_covariance"
    if fault_reason in {"low_quality_observation", "occluded_observation"}:
        return "downweight_sensor"
    if fault_reason == "unsupported_track_initializer":
        return "hold_until_radar_initializer"
    return "monitor_sensor"


def _optional_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _jsonable_metadata_value(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable_metadata_value(asdict(value))
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    if isinstance(value, dict):
        return {str(key): _jsonable_metadata_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable_metadata_value(item) for item in value]
    return value
