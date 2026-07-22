from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from typing import Any, Iterable

import numpy as np

from .consistency_evidence import (
    ConsistencySourceProvenance,
    OnlineConsistencyEvidenceBundle,
    OnlineConsistencyEvidenceRecord,
    export_online_consistency_evidence,
    initialization_consistency_evidence,
    mark_consistency_evidence_duplicate,
    mark_consistency_evidence_oosm,
    unavailable_consistency_evidence,
    update_consistency_evidence,
)
from .covariance_contract import validate_online_sensor_observation
from .ekf import EKFState, ekf_update, predict_to
from .motion import wrap_residual
from .observations import (
    MeasurementModel,
    RadarCovarianceConfig,
    measurement_model_for,
    radar_state_from_observation,
)
from .types import (
    COMMUNICATION_METADATA_KEYS,
    FusionBatchResult,
    FusionBatchSummary,
    FusionQualityRegionSummary,
    GlobalTrack,
    LatencyAuditSummary,
    SensorHealthSummary,
    SensorObservation,
    SensorTimingExpectation,
    TrackLevel,
    TrackUncertaintySummary,
)

CHI2_2_95 = 5.991464547107979
CHI2_3_999 = 16.26623619623813
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
    "local_epoch",
    "source_track_key",
    "spectral_band",
    "stream_id",
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
    "scan_id",
    "online_batch_id",
    "source_frame_id",
    "source_modality",
    "source_measurement_dimension",
    "measurement_order",
    "range_dependent_covariance",
    "radial_velocity_observed",
    "radial_velocity_placeholder_ignored",
    "filter_measurement_dimension",
    "filter_innovation_gate_chi2",
    "unobserved_velocity_variance_m2ps2",
    "velocity_initialization_model",
    "spherical_covariance_to_ned",
    "d1_fusion_schema_version",
    "soundprint_class_probabilities",
    "soundprint_category_only",
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
    "acoustic_3d": np.array([1.0e-8, 1.0e-8], dtype=float),
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


def _observation_sort_key(
    observation: SensorObservation,
) -> tuple[float, float, str]:
    return (
        float(observation.measurement_timestamp),
        float(observation.arrival_timestamp),
        str(observation.observation_id),
    )


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
    association_diagnostics: Counter = field(default_factory=Counter)
    checkpoint_active: bool = False
    checkpoint_count: int = 0
    origin_state: EKFState | None = None
    origin_observation_id: str | None = None
    archived_observations: list[SensorObservation] = field(default_factory=list)
    accepted_observer_scan_keys: set[tuple[str, str, str]] = field(default_factory=set)
    replay_checkpoints: list["_ReplayCheckpoint"] = field(default_factory=list)
    current_state_covariance_limited: bool = False
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
    expected_latency_s: float | None = None
    latency_tolerance_s: float | None = None
    oosm_expected: bool = False
    latency_sum_s: float = 0.0
    max_latency_s: float = 0.0
    latency_budget_exceedance_count: int = 0
    unexpected_oosm_count: int = 0


@dataclass(frozen=True)
class _ReplayCheckpoint:
    observation_id: str
    sort_key: tuple[float, float, str]
    posterior: EKFState
    nis: float
    gated: bool


@dataclass(frozen=True)
class _TrackPublicationContext:
    association_audit: dict[str, Any]
    latency_audit: dict[str, Any]
    sensor_health: dict[str, dict[str, Any]]


@dataclass
class _BatchProcessingContext:
    state_cache: dict[tuple[str, int, float], EKFState] = field(default_factory=dict)
    history_revision: Counter = field(default_factory=Counter)
    dirty_track_ids: set[str] = field(default_factory=set)
    checkpoint_dirty_track_ids: set[str] = field(default_factory=set)
    affected_track_ids: set[str] = field(default_factory=set)
    created_track_ids: set[str] = field(default_factory=set)
    accepted_observation_count: int = 0
    accepted_update_count: int = 0
    created_track_count: int = 0
    history_replay_count: int = 0
    origin_replay_count: int = 0
    state_cache_hit_count: int = 0
    state_cache_miss_count: int = 0
    finalization_replay_count: int = 0
    replay_filter_update_count: int = 0
    replay_checkpoint_reuse_count: int = 0
    global_track_materialization_count: int = 0
    sensor_health_snapshot_build_count: int = 0
    association_candidate_pair_count: int = 0
    association_measurement_model_build_count: int = 0
    association_projection_build_count: int = 0
    association_innovation_solve_count: int = 0
    association_radar_track_state_build_count: int = 0
    association_radar_observation_state_build_count: int = 0


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
        radar_reacquisition_gate: float | None = None,
        radar_reacquisition_max_gap_s: float = 0.5,
        non_range_position_correction_gate: float = CHI2_3_999,
        non_range_correction_min_radar_hits: int = 2,
        sensor_timing_expectations: dict[
            str, SensorTimingExpectation | dict[str, Any]
        ] | None = None,
        incremental_replay_cache: bool = True,
        shared_publication_audit_snapshot: bool = True,
        scan_association_model_cache: bool = True,
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
        self.radar_reacquisition_gate = (
            max(self.association_gate, CHI2_3_999)
            if radar_reacquisition_gate is None
            else float(radar_reacquisition_gate)
        )
        self.radar_reacquisition_max_gap_s = float(radar_reacquisition_max_gap_s)
        self.non_range_position_correction_gate = float(
            non_range_position_correction_gate
        )
        self.non_range_correction_min_radar_hits = int(
            non_range_correction_min_radar_hits
        )
        if self.radar_reacquisition_gate < self.association_gate:
            raise ValueError("radar_reacquisition_gate must not be below association_gate")
        if self.radar_reacquisition_max_gap_s < 0.0:
            raise ValueError("radar_reacquisition_max_gap_s must be non-negative")
        if self.non_range_position_correction_gate <= 0.0:
            raise ValueError("non_range_position_correction_gate must be positive")
        if self.non_range_correction_min_radar_hits < 1:
            raise ValueError("non_range_correction_min_radar_hits must be positive")
        self.sensor_timing_expectations = {
            str(key): (
                value
                if isinstance(value, SensorTimingExpectation)
                else SensorTimingExpectation(**dict(value))
            )
            for key, value in dict(sensor_timing_expectations or {}).items()
        }
        self.incremental_replay_cache = bool(incremental_replay_cache)
        self.shared_publication_audit_snapshot = bool(
            shared_publication_audit_snapshot
        )
        self.scan_association_model_cache = bool(scan_association_model_cache)
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
        self.observer_scan_suppression_count = 0
        self.radar_reacquisition_count = 0
        self.ambiguous_radar_birth_suppression_count = 0
        self.non_range_state_correction_rejection_count = 0
        self.pre_checkpoint_oosm_replay_count = 0
        self.max_non_range_position_correction_score = 0.0
        self._last_association_rejection_reason: str | None = None
        self._last_association_rejection_track_ids: tuple[str, ...] = ()
        self._batch_context: _BatchProcessingContext | None = None
        self._consistency_evidence: dict[str, OnlineConsistencyEvidenceRecord] = {}
        self._consistency_replay_revision = 0
        self._consistency_capture_context: tuple[str, int] | None = None

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
            if self._last_association_rejection_reason is not None:
                self._mark_observation_processed(effective)
                return self.global_tracks()
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

    def process_batch(
        self,
        observations: Iterable[SensorObservation],
    ) -> FusionBatchResult:
        """Process an ordered arrival batch with one final track publication.

        The iterable order has the same meaning as repeatedly calling
        :meth:`process` in that order.  Every observation keeps its physical
        measurement and arrival timestamps, covariance, source lineage, and
        modality.  The optimization only caches repeated state-at-time queries
        and defers full track replay to one pass per changed track.

        The call is not a rollback transaction: if an unexpected runtime error
        occurs after validation, observations handled before that error remain
        applied, matching the streaming API's failure semantics.
        """

        if self._batch_context is not None:
            raise RuntimeError("nested FusionAdapter.process_batch calls are not supported")

        prepared = tuple(self._prepare_observation(item) for item in observations)
        duplicate_before = self.duplicate_observation_count
        context = _BatchProcessingContext()
        self._batch_context = context
        try:
            for observation in prepared:
                self._process_prepared_batch_observation(observation, context)

            for track_id in sorted(context.dirty_track_ids):
                record = self.tracks[track_id]
                self._ensure_batch_checkpoint_current(record)
                self._finalize_record_replay(record, self.current_time)
                context.finalization_replay_count += 1
            self._predict_all_to(self.current_time)
            tracks = tuple(self.global_tracks())
        finally:
            self._batch_context = None

        duplicate_count = self.duplicate_observation_count - duplicate_before
        unaccepted_count = max(
            0,
            len(prepared) - context.accepted_observation_count,
        )
        summary = FusionBatchSummary(
            observation_count=len(prepared),
            accepted_observation_count=context.accepted_observation_count,
            unaccepted_observation_count=unaccepted_count,
            duplicate_observation_count=duplicate_count,
            created_track_count=context.created_track_count,
            updated_observation_count=context.accepted_update_count,
            updated_track_count=len(
                context.affected_track_ids - context.created_track_ids
            ),
            affected_track_ids=tuple(sorted(context.affected_track_ids)),
            history_replay_count=context.history_replay_count,
            origin_replay_count=context.origin_replay_count,
            state_cache_hit_count=context.state_cache_hit_count,
            state_cache_miss_count=context.state_cache_miss_count,
            finalization_replay_count=context.finalization_replay_count,
            replay_filter_update_count=context.replay_filter_update_count,
            replay_checkpoint_reuse_count=context.replay_checkpoint_reuse_count,
            global_track_materialization_count=(
                context.global_track_materialization_count
            ),
            sensor_health_snapshot_build_count=(
                context.sensor_health_snapshot_build_count
            ),
            association_candidate_pair_count=(
                context.association_candidate_pair_count
            ),
            association_measurement_model_build_count=(
                context.association_measurement_model_build_count
            ),
            association_projection_build_count=(
                context.association_projection_build_count
            ),
            association_innovation_solve_count=(
                context.association_innovation_solve_count
            ),
            association_radar_track_state_build_count=(
                context.association_radar_track_state_build_count
            ),
            association_radar_observation_state_build_count=(
                context.association_radar_observation_state_build_count
            ),
            deferred_update_replay_avoidance_count=max(
                0,
                context.accepted_update_count - context.finalization_replay_count,
            ),
            published_at=float(self.current_time),
        )
        return FusionBatchResult(tracks=tracks, summary=summary)

    def process_scan_batch(
        self,
        observations: Iterable[SensorObservation],
    ) -> FusionBatchResult:
        """Fuse one identity-free observer scan with one-to-one association.

        Unlike :meth:`process_batch`, this entry point intentionally does not
        emulate sequential association. All observations are associated against
        the pre-scan track set at once, and every unmatched radar detection may
        start its own track. This prevents a loose single-observation gate from
        suppressing nearby but distinct detections during dense-track birth.
        """

        if self._batch_context is not None:
            raise RuntimeError("nested FusionAdapter batch calls are not supported")

        prepared = tuple(self._prepare_observation(item) for item in observations)
        if not prepared:
            raise ValueError("scan batch must contain at least one observation")
        first = prepared[0]
        for observation in prepared[1:]:
            if observation.sensor_id != first.sensor_id:
                raise ValueError("scan batch observations must share sensor_id")
            if observation.modality != first.modality:
                raise ValueError("scan batch observations must share modality")
            if abs(observation.measurement_timestamp - first.measurement_timestamp) > 1.0e-9:
                raise ValueError("scan batch observations must share measurement_timestamp")
            if abs(observation.arrival_timestamp - first.arrival_timestamp) > 1.0e-9:
                raise ValueError("scan batch observations must share arrival_timestamp")
            if self._observer_scan_key(observation) != self._observer_scan_key(first):
                raise ValueError("scan batch observations must share one observer scan key")

        duplicate_before = self.duplicate_observation_count
        context = _BatchProcessingContext()
        self._batch_context = context
        try:
            previous_time = float(self.current_time)
            current_time = max(
                self.current_time,
                max(float(item.arrival_timestamp) for item in prepared),
            )
            self.current_time = current_time
            effective: list[SensorObservation] = []
            for observation in prepared:
                is_oosm, is_stale = self._record_latency_audit(
                    observation,
                    previous_time,
                    current_time,
                )
                self._record_sensor_observation(
                    observation,
                    is_oosm=is_oosm,
                    is_stale=is_stale,
                )
                candidate = observation
                if not self.latency_compensation:
                    candidate = observation.with_measurement_timestamp(
                        observation.arrival_timestamp
                    )
                if self._is_duplicate_observation(candidate):
                    self.duplicate_observation_count += 1
                    self._record_sensor_fault(
                        candidate,
                        "duplicate_observation",
                        rejected=True,
                    )
                    continue
                effective.append(candidate)

            self._predict_all_to(current_time)
            pre_scan_track_ids = tuple(sorted(self.tracks))
            assignments = self._scan_one_to_one_assignments(
                effective,
                pre_scan_track_ids,
            )
            for observation_index, observation in enumerate(effective):
                track_id = assignments.get(observation_index)
                if track_id is not None:
                    if self._apply_associated_observation(
                        self.tracks[track_id],
                        observation,
                        current_time,
                        defer_replay=True,
                    ):
                        context.accepted_observation_count += 1
                        context.accepted_update_count += 1
                        context.affected_track_ids.add(track_id)
                    continue

                record = self._create_track(observation, current_time)
                if record is None:
                    self._record_sensor_fault(
                        observation,
                        "unsupported_track_initializer",
                        rejected=True,
                    )
                    self._mark_observation_processed(observation)
                    continue
                context.accepted_observation_count += 1
                context.created_track_count += 1
                context.affected_track_ids.add(record.track_id)
                context.created_track_ids.add(record.track_id)

            for track_id in sorted(context.dirty_track_ids):
                record = self.tracks[track_id]
                self._ensure_batch_checkpoint_current(record)
                self._finalize_record_replay(record, self.current_time)
                context.finalization_replay_count += 1
            self._predict_all_to(self.current_time)
            tracks = tuple(self.global_tracks())
        finally:
            self._batch_context = None

        duplicate_count = self.duplicate_observation_count - duplicate_before
        summary = FusionBatchSummary(
            observation_count=len(prepared),
            accepted_observation_count=context.accepted_observation_count,
            unaccepted_observation_count=max(
                0,
                len(prepared) - context.accepted_observation_count,
            ),
            duplicate_observation_count=duplicate_count,
            created_track_count=context.created_track_count,
            updated_observation_count=context.accepted_update_count,
            updated_track_count=len(
                context.affected_track_ids - context.created_track_ids
            ),
            affected_track_ids=tuple(sorted(context.affected_track_ids)),
            history_replay_count=context.history_replay_count,
            origin_replay_count=context.origin_replay_count,
            state_cache_hit_count=context.state_cache_hit_count,
            state_cache_miss_count=context.state_cache_miss_count,
            finalization_replay_count=context.finalization_replay_count,
            replay_filter_update_count=context.replay_filter_update_count,
            replay_checkpoint_reuse_count=context.replay_checkpoint_reuse_count,
            global_track_materialization_count=(
                context.global_track_materialization_count
            ),
            sensor_health_snapshot_build_count=(
                context.sensor_health_snapshot_build_count
            ),
            association_candidate_pair_count=(
                context.association_candidate_pair_count
            ),
            association_measurement_model_build_count=(
                context.association_measurement_model_build_count
            ),
            association_projection_build_count=(
                context.association_projection_build_count
            ),
            association_innovation_solve_count=(
                context.association_innovation_solve_count
            ),
            association_radar_track_state_build_count=(
                context.association_radar_track_state_build_count
            ),
            association_radar_observation_state_build_count=(
                context.association_radar_observation_state_build_count
            ),
            deferred_update_replay_avoidance_count=max(
                0,
                context.accepted_update_count - context.finalization_replay_count,
            ),
            published_at=float(self.current_time),
        )
        return FusionBatchResult(tracks=tracks, summary=summary)

    def _process_prepared_batch_observation(
        self,
        observation: SensorObservation,
        context: _BatchProcessingContext,
    ) -> None:
        previous_time = self.current_time
        current_time = max(self.current_time, float(observation.arrival_timestamp))
        self.current_time = current_time
        is_oosm, is_stale = self._record_latency_audit(
            observation,
            previous_time,
            current_time,
        )
        self._record_sensor_observation(
            observation,
            is_oosm=is_oosm,
            is_stale=is_stale,
        )
        effective = observation
        if not self.latency_compensation:
            effective = observation.with_measurement_timestamp(observation.arrival_timestamp)

        # Preserve the streaming API's arrival-time prediction semantics for
        # untouched tracks while deferring history reconstruction for tracks
        # changed inside this batch.
        self._predict_all_to(current_time)
        if self._is_duplicate_observation(effective):
            self.duplicate_observation_count += 1
            self._record_sensor_fault(effective, "duplicate_observation", rejected=True)
            return

        track_id = self._associate(effective)
        if track_id is None:
            if self._last_association_rejection_reason is not None:
                self._mark_observation_processed(effective)
                return
            record = self._create_track(effective, current_time)
            if record is None:
                self._record_sensor_fault(
                    effective,
                    "unsupported_track_initializer",
                    rejected=True,
                )
                return
            context.accepted_observation_count += 1
            context.created_track_count += 1
            context.affected_track_ids.add(record.track_id)
            context.created_track_ids.add(record.track_id)
            return

        # Streaming ``process`` prepares once before association and public
        # ``compensate_latency`` prepares again before update.  Retain that
        # established covariance/quality behavior for numerical equivalence.
        effective = self._prepare_observation(effective)
        if self._apply_associated_observation(
            self.tracks[track_id],
            effective,
            current_time,
            defer_replay=True,
        ):
            context.accepted_observation_count += 1
            context.accepted_update_count += 1
            context.affected_track_ids.add(track_id)

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
        record.current_state_covariance_limited = False
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
            if self._last_association_rejection_reason is not None:
                self._mark_observation_processed(observation)
                return None
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
        self._apply_associated_observation(
            record,
            observation,
            current_time,
            defer_replay=False,
        )
        return self._to_global_track(record)

    def _apply_associated_observation(
        self,
        record: TrackRecord,
        observation: SensorObservation,
        current_time: float,
        *,
        defer_replay: bool,
    ) -> bool:
        if self._is_duplicate_observation(observation):
            self.duplicate_observation_count += 1
            self._record_sensor_fault(observation, "duplicate_observation", rejected=True)
            record.current_state = predict_to(record.current_state, current_time, self.process_noise)
            record.current_state_covariance_limited = False
            self._limit_record_covariance(record)
            return False

        if self._record_has_observer_scan(record, observation):
            self._record_association_rejection(
                observation,
                "observer_scan_conflict",
                (record.track_id,),
            )
            record.association_diagnostics["observer_scan_conflict"] += 1
            record.current_state = predict_to(record.current_state, current_time, self.process_noise)
            record.current_state_covariance_limited = False
            self._limit_record_covariance(record)
            self._mark_observation_processed(observation)
            return False

        correction_score = self._non_range_position_correction_score(record, observation)
        if correction_score is not None:
            self.max_non_range_position_correction_score = max(
                self.max_non_range_position_correction_score,
                correction_score,
            )
            if correction_score > self.non_range_position_correction_gate:
                self.non_range_state_correction_rejection_count += 1
                record.association_diagnostics["non_range_state_correction_rejected"] += 1
                record.metadata["latest_non_range_position_correction_score"] = float(
                    correction_score
                )
                record.metadata["non_range_position_correction_gate"] = float(
                    self.non_range_position_correction_gate
                )
                self._record_sensor_fault(
                    observation,
                    "non_range_state_correction_rejected",
                    rejected=True,
                )
                record.current_state = predict_to(
                    record.current_state,
                    current_time,
                    self.process_noise,
                )
                record.current_state_covariance_limited = False
                self._limit_record_covariance(record)
                self._mark_observation_processed(observation)
                return False

        if (
            record.checkpoint_active
            and observation.measurement_timestamp < record.initial_state.timestamp - 1e-9
        ):
            return self._compensate_pre_checkpoint_oosm(
                record,
                observation,
                current_time,
                defer_replay=defer_replay,
            )

        inserted_observation = False
        if observation.observation_id not in {obs.observation_id for obs in record.observations}:
            record.observations.append(observation)
            self._invalidate_replay_checkpoints(
                record,
                from_sort_key=_observation_sort_key(observation),
            )
            inserted_observation = True
            self._mark_batch_history_changed(record)
        self._record_replay_audit(record, inserted_observation)
        record.hits += 1
        record.source_support[observation.modality] += 1
        if observation.classification_hint:
            record.identity_likelihood[observation.classification_hint] += observation.confidence
        self._update_record_metadata_from_observation(record, observation)
        record.accepted_observer_scan_keys.add(self._observer_scan_key(observation))
        if defer_replay:
            if inserted_observation:
                context = self._require_batch_context()
                context.dirty_track_ids.add(record.track_id)
        else:
            self._finalize_record_replay(record, current_time)
        self._mark_observation_processed(observation)
        return True

    def _finalize_record_replay(self, record: TrackRecord, current_time: float) -> None:
        state, nises, gated_observation_ids = self._capture_replay_record(
            record,
            current_time,
        )
        record.current_state = state
        record.current_state_covariance_limited = False
        record.recent_nis = deque(nises[-50:], maxlen=50)
        self._update_filter_gate_metadata(
            record,
            nises,
            gated_observation_ids,
        )
        self._limit_record_covariance(record)
        self._prune_record(record, current_time)

    def _compensate_pre_checkpoint_oosm(
        self,
        record: TrackRecord,
        observation: SensorObservation,
        current_time: float,
        *,
        defer_replay: bool = False,
    ) -> bool:
        """Rebuild a checkpoint only when a legal observation predates it."""

        if record.origin_state is None or record.origin_observation_id is None:
            raise RuntimeError("fixed-lag OOSM archive is missing the original track anchor")
        existing_ids = {
            item.observation_id
            for item in (*record.archived_observations, *record.observations)
        }
        inserted_observation = observation.observation_id not in existing_ids
        if inserted_observation:
            record.archived_observations.append(observation)
            self._mark_batch_history_changed(record, checkpoint_dirty=True)

        checkpoint_timestamp = float(record.initial_state.timestamp)
        if defer_replay:
            if inserted_observation:
                context = self._require_batch_context()
                context.dirty_track_ids.add(record.track_id)
        else:
            checkpoint, _, _ = self._capture_replay_from_origin(
                record,
                checkpoint_timestamp,
            )
            record.initial_state = checkpoint
            self._invalidate_replay_checkpoints(record)
            self._finalize_record_replay(record, current_time)

        self._record_replay_audit(record, inserted_observation)
        record.hits += 1
        record.source_support[observation.modality] += 1
        if observation.classification_hint:
            record.identity_likelihood[observation.classification_hint] += observation.confidence
        self._update_record_metadata_from_observation(record, observation)
        record.accepted_observer_scan_keys.add(self._observer_scan_key(observation))
        record.association_diagnostics["pre_checkpoint_oosm_replayed"] += 1
        self.pre_checkpoint_oosm_replay_count += 1
        record.metadata.update(
            {
                "fixed_lag_checkpoint_active": True,
                "fixed_lag_checkpoint_timestamp": checkpoint_timestamp,
                "pre_checkpoint_oosm_replay_count": self.pre_checkpoint_oosm_replay_count,
                "latest_pre_checkpoint_oosm_measurement_timestamp": float(
                    observation.measurement_timestamp
                ),
            }
        )
        self._mark_observation_processed(observation)
        return True

    def global_tracks(self) -> list[GlobalTrack]:
        publication_context = (
            self._track_publication_context()
            if self.shared_publication_audit_snapshot
            else None
        )
        return [
            self._to_global_track(record, publication_context)
            for record in self.tracks.values()
        ]

    def _track_publication_context(self) -> _TrackPublicationContext:
        context = self._batch_context
        if context is not None:
            context.sensor_health_snapshot_build_count += 1
        return _TrackPublicationContext(
            association_audit=self.association_audit_summary(),
            latency_audit=self.latency_audit_summary().to_dict(),
            sensor_health={
                summary.sensor_id: summary.to_dict()
                for summary in self.sensor_health_summaries()
            },
        )

    def consistency_evidence_records(
        self,
    ) -> tuple[OnlineConsistencyEvidenceRecord, ...]:
        """Return the current truth-free per-observation evidence snapshot."""

        return tuple(
            sorted(
                self._consistency_evidence.values(),
                key=lambda item: (
                    item.arrival_timestamp,
                    item.measurement_timestamp,
                    item.observation_id,
                ),
            )
        )

    def export_consistency_evidence(
        self,
        provenance: ConsistencySourceProvenance,
    ) -> OnlineConsistencyEvidenceBundle:
        """Freeze current online evidence with episode/source hashes."""

        return export_online_consistency_evidence(
            self.consistency_evidence_records(),
            provenance,
        )

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
            published_at=self.current_time,
        )

    def association_audit_summary(self) -> dict[str, Any]:
        """Return truth-free diagnostics for D1 association governance."""

        return {
            "schema_version": "d1.association_audit.v1",
            "observer_scan_suppression_count": self.observer_scan_suppression_count,
            "radar_reacquisition_count": self.radar_reacquisition_count,
            "ambiguous_radar_birth_suppression_count": (
                self.ambiguous_radar_birth_suppression_count
            ),
            "non_range_state_correction_rejection_count": (
                self.non_range_state_correction_rejection_count
            ),
            "pre_checkpoint_oosm_replay_count": self.pre_checkpoint_oosm_replay_count,
            "max_non_range_position_correction_score": float(
                self.max_non_range_position_correction_score
            ),
            "association_gate": float(self.association_gate),
            "radar_reacquisition_gate": float(self.radar_reacquisition_gate),
            "radar_reacquisition_max_gap_s": float(
                self.radar_reacquisition_max_gap_s
            ),
            "non_range_position_correction_gate": float(
                self.non_range_position_correction_gate
            ),
            "latest_rejection_reason": self._last_association_rejection_reason,
            "latest_rejection_track_ids": self._last_association_rejection_track_ids,
        }

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
            origin_state=initial.copy(),
            origin_observation_id=observation.observation_id,
            metadata={
                **(
                    {"truth_id": observation.metadata["truth_id"]}
                    if observation.metadata.get("truth_id") is not None
                    else {}
                ),
                **_metadata_from_observation(observation),
            },
        )
        self._limit_record_covariance(record)
        self.tracks[track_id] = record
        record.accepted_observer_scan_keys.add(self._observer_scan_key(observation))
        self._mark_observation_processed(observation)
        self._capture_consistency_initialization(record, observation, initial)
        return record

    def _predict_all_to(self, timestamp: float) -> None:
        for record in self.tracks.values():
            if record.current_state.timestamp < timestamp - 1e-12:
                previous_timestamp = float(record.current_state.timestamp)
                record.current_state = predict_to(record.current_state, timestamp, self.process_noise)
                record.current_state_covariance_limited = False
                reasons = []
                if float(timestamp) - previous_timestamp > self.long_extrapolation_s:
                    reasons.append("long_extrapolation")
                self._limit_record_covariance(record, reasons)

    def _associate(self, observation: SensorObservation) -> str | None:
        self._last_association_rejection_reason = None
        self._last_association_rejection_track_ids = ()
        if not self.tracks:
            return None
        if self.use_truth_hints_for_association and "truth_id" in observation.metadata:
            truth_id = observation.metadata.get("truth_id")
            for track_id, record in self.tracks.items():
                if (
                    record.metadata.get("truth_id") == truth_id
                    and not self._record_has_observer_scan(record, observation)
                ):
                    return track_id

        candidates: list[tuple[float, str, TrackRecord]] = []
        blocked: list[tuple[float, str, TrackRecord]] = []
        for track_id, record in self.tracks.items():
            score = self._association_score(record, observation)
            item = (float(score), track_id, record)
            if self._record_has_observer_scan(record, observation):
                blocked.append(item)
            else:
                candidates.append(item)

        candidates.sort(key=lambda item: (item[0], item[1]))
        blocked.sort(key=lambda item: (item[0], item[1]))
        if candidates and candidates[0][0] <= self.association_gate:
            return candidates[0][1]

        if observation.modality == "radar":
            reacquisition_candidates = [
                item
                for item in candidates
                if item[0] <= self.radar_reacquisition_gate
                and self._radar_reacquisition_eligible(item[2], observation)
            ]
            if len(reacquisition_candidates) == 1:
                score, track_id, record = reacquisition_candidates[0]
                self.radar_reacquisition_count += 1
                record.association_diagnostics["radar_reacquisition"] += 1
                record.metadata["latest_radar_reacquisition_score"] = float(score)
                record.metadata["radar_reacquisition_gate"] = float(
                    self.radar_reacquisition_gate
                )
                return track_id
            if len(reacquisition_candidates) > 1:
                track_ids = tuple(item[1] for item in reacquisition_candidates)
                self._record_association_rejection(
                    observation,
                    "ambiguous_radar_birth_suppressed",
                    track_ids,
                )
                for _, _, record in reacquisition_candidates:
                    record.association_diagnostics[
                        "ambiguous_radar_birth_suppressed"
                    ] += 1
                return None

        if blocked and blocked[0][0] <= self.association_gate:
            track_ids = tuple(
                item[1] for item in blocked if item[0] <= self.association_gate
            )
            self._record_association_rejection(
                observation,
                "observer_scan_conflict",
                track_ids,
            )
            for _, track_id, record in blocked:
                if track_id in track_ids:
                    record.association_diagnostics["observer_scan_conflict"] += 1
        return None

    def _scan_one_to_one_assignments(
        self,
        observations: list[SensorObservation],
        pre_scan_track_ids: tuple[str, ...],
    ) -> dict[int, str]:
        if not observations or not pre_scan_track_ids:
            return {}

        track_items = [
            (track_id, self.tracks[track_id])
            for track_id in pre_scan_track_ids
            if not self._record_has_observer_scan(
                self.tracks[track_id],
                observations[0],
            )
        ]
        if not track_items:
            return {}

        context = self._batch_context
        if context is not None:
            context.association_candidate_pair_count += (
                len(track_items) * len(observations)
            )

        if all(observation.modality == "radar" for observation in observations):
            measurement_timestamp = observations[0].measurement_timestamp
            track_states = [
                self._state_at(record, measurement_timestamp)
                for _, record in track_items
            ]
            observation_states = [
                radar_state_from_observation(observation, self.radar_covariance_config)
                for observation in observations
            ]
            if context is not None:
                context.association_radar_track_state_build_count += len(track_states)
                context.association_radar_observation_state_build_count += len(
                    observation_states
                )
                context.association_innovation_solve_count += (
                    len(track_states) * len(observation_states)
                )
            track_positions = np.stack([item.state[:3] for item in track_states])
            track_covariances = np.stack(
                [item.covariance[:3, :3] for item in track_states]
            )
            observation_positions = np.stack([item[0][:3] for item in observation_states])
            observation_covariances = np.stack(
                [item[1][:3, :3] for item in observation_states]
            )
            differences = (
                observation_positions[None, :, :] - track_positions[:, None, :]
            )
            innovation_covariances = (
                track_covariances[:, None, :, :]
                + observation_covariances[None, :, :, :]
                + np.eye(3, dtype=float)[None, None, :, :] * 1.0e-6
            )
            inverses = np.linalg.pinv(innovation_covariances)
            cost_matrix = np.einsum(
                "toi,toij,toj->to",
                differences,
                inverses,
                differences,
            )
        elif self.scan_association_model_cache:
            cost_matrix = self._cached_non_radar_scan_cost_matrix(
                track_items,
                observations,
            )
        else:
            cost_matrix = np.empty((len(track_items), len(observations)), dtype=float)
            for row, (_, record) in enumerate(track_items):
                for column, observation in enumerate(observations):
                    cost_matrix[row, column] = self._association_score(
                        record,
                        observation,
                    )

        valid = np.isfinite(cost_matrix) & (cost_matrix <= self.association_gate)
        if not np.any(valid):
            return {}
        penalty = max(1.0e9, abs(self.association_gate) * 1.0e6)
        gated_cost = np.where(valid, cost_matrix, penalty)
        try:
            from scipy.optimize import linear_sum_assignment

            rows, columns = linear_sum_assignment(gated_cost)
            pairs = zip(rows.tolist(), columns.tolist())
        except ImportError:
            ordered_pairs = sorted(
                (
                    (float(cost_matrix[row, column]), row, column)
                    for row, column in zip(*np.nonzero(valid))
                ),
                key=lambda item: (item[0], item[1], item[2]),
            )
            used_rows: set[int] = set()
            used_columns: set[int] = set()
            greedy_pairs: list[tuple[int, int]] = []
            for _, row, column in ordered_pairs:
                if row in used_rows or column in used_columns:
                    continue
                used_rows.add(row)
                used_columns.add(column)
                greedy_pairs.append((row, column))
            pairs = iter(greedy_pairs)

        assignments: dict[int, str] = {}
        for row, column in pairs:
            if not valid[row, column]:
                continue
            assignments[int(column)] = track_items[int(row)][0]
        return assignments

    def _cached_non_radar_scan_cost_matrix(
        self,
        track_items: list[tuple[str, TrackRecord]],
        observations: list[SensorObservation],
    ) -> np.ndarray:
        """Build one scan cost matrix without rebuilding immutable models per pair."""

        context = self._batch_context
        states: list[EKFState | None] = []
        measurement_timestamp = observations[0].measurement_timestamp
        for _, record in track_items:
            try:
                states.append(self._state_at(record, measurement_timestamp))
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                states.append(None)

        models: list[MeasurementModel | None] = []
        for observation in observations:
            if context is not None:
                context.association_measurement_model_build_count += 1
            try:
                models.append(
                    measurement_model_for(
                        observation,
                        self.radar_covariance_config,
                    )
                )
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                models.append(None)

        cost_matrix = np.full(
            (len(track_items), len(observations)),
            np.inf,
            dtype=float,
        )
        projection_cache: dict[
            tuple[int, tuple[Any, ...]],
            tuple[np.ndarray, np.ndarray] | None,
        ] = {}
        for row, state in enumerate(states):
            if state is None:
                continue
            for column, model in enumerate(models):
                if model is None:
                    continue
                geometry_key = model.geometry_key or (
                    "observation",
                    observations[column].observation_id,
                )
                cache_key = (row, geometry_key)
                if cache_key not in projection_cache:
                    if context is not None:
                        context.association_projection_build_count += 1
                    try:
                        projection_cache[cache_key] = (
                            model.h_fn(state.state),
                            model.h_jacobian_fn(state.state),
                        )
                    except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                        projection_cache[cache_key] = None
                projection = projection_cache[cache_key]
                if projection is None:
                    continue
                try:
                    cost_matrix[row, column] = self._innovation_nis_from_model(
                        state,
                        model,
                        projection[0],
                        projection[1],
                    )
                except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                    cost_matrix[row, column] = np.inf
        return cost_matrix

    def _record_has_observer_scan(
        self,
        record: TrackRecord,
        observation: SensorObservation,
    ) -> bool:
        return self._observer_scan_key(observation) in record.accepted_observer_scan_keys

    def _observer_scan_key(self, observation: SensorObservation) -> tuple[str, str, str]:
        if observation.modality == "eo":
            observer_id = observation.metadata.get("camera_id") or observation.sensor_id
        else:
            observer_id = observation.sensor_id
        scan_id = None
        for key in ("scan_id", "sequence_id", "airsim_frame_index", "frame_index"):
            if observation.metadata.get(key) is not None:
                scan_id = observation.metadata[key]
                break
        if scan_id is None:
            scan_id = f"bucket-{self._bucket(observation.measurement_timestamp)}"
        return observation.modality, str(observer_id), str(scan_id)

    def _radar_reacquisition_eligible(
        self,
        record: TrackRecord,
        observation: SensorObservation,
    ) -> bool:
        if record.hits < 3 or record.source_support.get("radar", 0) < 2:
            return False
        previous_radar_timestamps = [
            float(item.measurement_timestamp)
            for item in record.observations
            if item.modality == "radar"
            and item.measurement_timestamp <= observation.measurement_timestamp + 1e-9
            and self._observer_scan_key(item) != self._observer_scan_key(observation)
        ]
        if not previous_radar_timestamps:
            return False
        gap_s = max(
            0.0,
            float(observation.measurement_timestamp) - max(previous_radar_timestamps),
        )
        return gap_s <= self.radar_reacquisition_max_gap_s + 1e-9

    def _record_association_rejection(
        self,
        observation: SensorObservation,
        reason: str,
        track_ids: Iterable[str],
    ) -> None:
        self._last_association_rejection_reason = str(reason)
        self._last_association_rejection_track_ids = tuple(str(item) for item in track_ids)
        self._mark_consistency_unavailable(observation, str(reason))
        if reason == "observer_scan_conflict":
            self.observer_scan_suppression_count += 1
        elif reason == "ambiguous_radar_birth_suppressed":
            self.ambiguous_radar_birth_suppression_count += 1

    def _non_range_position_correction_score(
        self,
        record: TrackRecord,
        observation: SensorObservation,
    ) -> float | None:
        if observation.modality not in {"eo", "acoustic", "acoustic_3d"}:
            return None
        if record.source_support.get("radar", 0) < self.non_range_correction_min_radar_hits:
            return None
        try:
            prior = self._state_at(record, observation.measurement_timestamp)
            model = measurement_model_for(observation, self.radar_covariance_config)
            updated, _ = ekf_update(
                prior,
                model.z,
                model.h_fn,
                model.h_jacobian_fn,
                model.r,
                model.angle_indices,
            )
            correction = updated.state[:3] - prior.state[:3]
            covariance = prior.covariance[:3, :3] + 1e-9 * np.eye(3)
            return float(correction.T @ np.linalg.pinv(covariance) @ correction)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            return np.inf

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
        context = self._batch_context
        if context is not None:
            context.association_measurement_model_build_count += 1
        model = measurement_model_for(observation, self.radar_covariance_config)
        if context is not None:
            context.association_projection_build_count += 1
        h = model.h_fn(state.state)
        h_j = model.h_jacobian_fn(state.state)
        return self._innovation_nis_from_model(state, model, h, h_j)

    def _innovation_nis_from_model(
        self,
        state: EKFState,
        model: MeasurementModel,
        predicted_measurement: np.ndarray,
        measurement_jacobian: np.ndarray,
    ) -> float:
        residual = wrap_residual(
            model.z - predicted_measurement,
            model.angle_indices,
        )
        s = measurement_jacobian @ state.covariance @ measurement_jacobian.T + model.r
        s = 0.5 * (s + s.T) + 1e-9 * np.eye(s.shape[0])
        context = self._batch_context
        if context is not None:
            context.association_innovation_solve_count += 1
        return float(residual.T @ np.linalg.pinv(s) @ residual)

    def _filter_update(
        self,
        state: EKFState,
        observation: SensorObservation,
    ) -> tuple[EKFState, float, bool]:
        model = measurement_model_for(observation, self.radar_covariance_config)
        updated, nis = ekf_update(
            state,
            model.z,
            model.h_fn,
            model.h_jacobian_fn,
            model.r,
            model.angle_indices,
        )
        gate = observation.metadata.get("filter_innovation_gate_chi2")
        gated = gate is not None and nis > float(gate)
        return (state.copy() if gated else updated), nis, bool(gated)

    def _update_filter_gate_metadata(
        self,
        record: TrackRecord,
        nises: list[float],
        gated_observation_ids: tuple[str, ...],
    ) -> None:
        if record.metadata.get("filter_innovation_gate_chi2") is None:
            return
        record.metadata.update(
            {
                "latest_replay_innovation_count": len(nises),
                "latest_replay_filter_update_count": (
                    len(nises) - len(gated_observation_ids)
                ),
                "latest_replay_innovation_gate_rejection_count": len(
                    gated_observation_ids
                ),
                "latest_replay_innovation_gate_rejected_observation_ids": (
                    gated_observation_ids
                ),
            }
        )

    def _state_at(self, record: TrackRecord, timestamp: float) -> EKFState:
        context = self._batch_context
        if context is not None:
            if (
                record.track_id in context.checkpoint_dirty_track_ids
                and timestamp >= record.initial_state.timestamp - 1e-9
            ):
                self._ensure_batch_checkpoint_current(record)
            revision = int(context.history_revision[record.track_id])
            key = (record.track_id, revision, float(timestamp))
            cached = context.state_cache.get(key)
            if cached is not None:
                context.state_cache_hit_count += 1
                return cached.copy()
            context.state_cache_miss_count += 1

        if record.checkpoint_active and timestamp < record.initial_state.timestamp - 1e-9:
            state = self._replay_from_origin(record, timestamp)[0]
        else:
            state, _, _ = self._replay_record(record, timestamp)
        if context is not None:
            context.state_cache[key] = state.copy()
        return state

    def _mark_batch_history_changed(
        self,
        record: TrackRecord,
        *,
        checkpoint_dirty: bool = False,
    ) -> None:
        context = self._batch_context
        if context is None:
            return
        context.history_revision[record.track_id] += 1
        if checkpoint_dirty:
            context.checkpoint_dirty_track_ids.add(record.track_id)

    def _ensure_batch_checkpoint_current(self, record: TrackRecord) -> None:
        context = self._batch_context
        if context is None or record.track_id not in context.checkpoint_dirty_track_ids:
            return
        checkpoint_timestamp = float(record.initial_state.timestamp)
        checkpoint, _, _ = self._capture_replay_from_origin(
            record,
            checkpoint_timestamp,
        )
        record.initial_state = checkpoint
        self._invalidate_replay_checkpoints(record)
        context.checkpoint_dirty_track_ids.remove(record.track_id)

    def _require_batch_context(self) -> _BatchProcessingContext:
        if self._batch_context is None:
            raise RuntimeError("deferred fusion replay requires an active process_batch call")
        return self._batch_context

    def _capture_replay_record(
        self,
        record: TrackRecord,
        until_time: float,
    ) -> tuple[EKFState, list[float], tuple[str, ...]]:
        previous = self._consistency_capture_context
        self._consistency_replay_revision += 1
        self._consistency_capture_context = (
            record.track_id,
            self._consistency_replay_revision,
        )
        try:
            return self._replay_record(record, until_time)
        finally:
            self._consistency_capture_context = previous

    def _capture_replay_from_origin(
        self,
        record: TrackRecord,
        until_time: float,
    ) -> tuple[EKFState, list[float], tuple[str, ...]]:
        previous = self._consistency_capture_context
        self._consistency_replay_revision += 1
        self._consistency_capture_context = (
            record.track_id,
            self._consistency_replay_revision,
        )
        try:
            return self._replay_from_origin(record, until_time)
        finally:
            self._consistency_capture_context = previous

    def _capture_consistency_initialization(
        self,
        record: TrackRecord,
        observation: SensorObservation,
        state: EKFState,
    ) -> None:
        self._consistency_replay_revision += 1
        self._consistency_evidence[observation.observation_id] = (
            initialization_consistency_evidence(
                observation,
                source_global_track_id=record.track_id,
                state=state.state,
                covariance=state.covariance,
                replay_revision=self._consistency_replay_revision,
                previous=self._consistency_evidence.get(observation.observation_id),
            )
        )

    def _capture_consistency_initialization_if_enabled(
        self,
        record: TrackRecord,
        observation: SensorObservation | None,
        state: EKFState,
    ) -> None:
        context = self._consistency_capture_context
        if observation is None or context is None or context[0] != record.track_id:
            return
        self._consistency_evidence[observation.observation_id] = (
            initialization_consistency_evidence(
                observation,
                source_global_track_id=record.track_id,
                state=state.state,
                covariance=state.covariance,
                replay_revision=context[1],
                previous=self._consistency_evidence.get(observation.observation_id),
            )
        )

    def _capture_consistency_update_if_enabled(
        self,
        record: TrackRecord,
        observation: SensorObservation,
        state: EKFState,
        nis: float,
        gated: bool,
    ) -> None:
        context = self._consistency_capture_context
        if context is None or context[0] != record.track_id:
            return
        model = measurement_model_for(observation, self.radar_covariance_config)
        self._consistency_evidence[observation.observation_id] = (
            update_consistency_evidence(
                observation,
                source_global_track_id=record.track_id,
                state=state.state,
                covariance=state.covariance,
                innovation_dimension=int(model.z.size),
                nis=nis,
                gated=gated,
                replay_revision=context[1],
                previous=self._consistency_evidence.get(observation.observation_id),
            )
        )

    def _mark_consistency_unavailable(
        self,
        observation: SensorObservation,
        reason: str,
    ) -> None:
        previous = self._consistency_evidence.get(observation.observation_id)
        self._consistency_evidence[observation.observation_id] = (
            unavailable_consistency_evidence(
                observation,
                reason,
                oosm_replayed=False if previous is None else previous.oosm_replayed,
                previous=previous,
            )
        )

    def _replay_from_origin(
        self,
        record: TrackRecord,
        until_time: float,
    ) -> tuple[EKFState, list[float], tuple[str, ...]]:
        if self._batch_context is not None:
            self._batch_context.origin_replay_count += 1
        if record.origin_state is None or record.origin_observation_id is None:
            raise RuntimeError("track origin is unavailable for historical OOSM replay")
        state = record.origin_state.copy()
        nises: list[float] = []
        gated_observation_ids: list[str] = []
        observations_by_id = {
            observation.observation_id: observation
            for observation in (*record.archived_observations, *record.observations)
        }
        sorted_observations = sorted(
            observations_by_id.values(),
            key=lambda obs: (obs.measurement_timestamp, obs.arrival_timestamp, obs.observation_id),
        )
        self._capture_consistency_initialization_if_enabled(
            record,
            observations_by_id.get(record.origin_observation_id),
            state,
        )
        for observation in sorted_observations:
            if observation.observation_id == record.origin_observation_id:
                continue
            if observation.measurement_timestamp < state.timestamp - 1e-9:
                continue
            if observation.measurement_timestamp > until_time + 1e-9:
                continue
            state = predict_to(state, observation.measurement_timestamp, self.process_noise)
            state, nis, gated = self._filter_update(state, observation)
            self._capture_consistency_update_if_enabled(
                record,
                observation,
                state,
                nis,
                gated,
            )
            nises.append(nis)
            if gated:
                gated_observation_ids.append(observation.observation_id)
        state = predict_to(state, until_time, self.process_noise)
        return state, nises, tuple(gated_observation_ids)

    def _replay_record(
        self,
        record: TrackRecord,
        until_time: float,
    ) -> tuple[EKFState, list[float], tuple[str, ...]]:
        if self._batch_context is not None:
            self._batch_context.history_replay_count += 1
        self._refresh_initial(record)
        state = record.initial_state.copy()
        nises: list[float] = []
        gated_observation_ids: list[str] = []
        sorted_observations = sorted(
            record.observations,
            key=lambda obs: (obs.measurement_timestamp, obs.arrival_timestamp, obs.observation_id),
        )
        initial_observation = next(
            (
                item
                for item in sorted_observations
                if item.observation_id == record.initial_observation_id
            ),
            None,
        )
        self._capture_consistency_initialization_if_enabled(
            record,
            initial_observation,
            state,
        )
        eligible = [
            observation
            for observation in sorted_observations
            if observation.observation_id != record.initial_observation_id
            and observation.measurement_timestamp >= state.timestamp - 1e-9
            and observation.measurement_timestamp <= until_time + 1e-9
        ]

        if not self.incremental_replay_cache:
            record.replay_checkpoints.clear()
            for observation in eligible:
                state = predict_to(
                    state,
                    observation.measurement_timestamp,
                    self.process_noise,
                )
                state, nis, gated = self._filter_update(state, observation)
                if self._batch_context is not None:
                    self._batch_context.replay_filter_update_count += 1
                self._capture_consistency_update_if_enabled(
                    record,
                    observation,
                    state,
                    nis,
                    gated,
                )
                nises.append(nis)
                if gated:
                    gated_observation_ids.append(observation.observation_id)
            state = predict_to(state, until_time, self.process_noise)
            return state, nises, tuple(gated_observation_ids)

        matching_prefix = 0
        prefix_limit = min(len(eligible), len(record.replay_checkpoints))
        while matching_prefix < prefix_limit:
            observation = eligible[matching_prefix]
            checkpoint = record.replay_checkpoints[matching_prefix]
            if (
                checkpoint.observation_id != observation.observation_id
                or checkpoint.sort_key != _observation_sort_key(observation)
            ):
                break
            matching_prefix += 1

        if matching_prefix < prefix_limit:
            del record.replay_checkpoints[matching_prefix:]

        for observation, checkpoint in zip(
            eligible[:matching_prefix],
            record.replay_checkpoints[:matching_prefix],
        ):
            state = checkpoint.posterior.copy()
            nises.append(checkpoint.nis)
            if checkpoint.gated:
                gated_observation_ids.append(observation.observation_id)
            self._capture_consistency_update_if_enabled(
                record,
                observation,
                state,
                checkpoint.nis,
                checkpoint.gated,
            )
        if self._batch_context is not None:
            self._batch_context.replay_checkpoint_reuse_count += matching_prefix

        for observation in eligible[matching_prefix:]:
            state = predict_to(
                state,
                observation.measurement_timestamp,
                self.process_noise,
            )
            state, nis, gated = self._filter_update(state, observation)
            if self._batch_context is not None:
                self._batch_context.replay_filter_update_count += 1
            self._capture_consistency_update_if_enabled(
                record,
                observation,
                state,
                nis,
                gated,
            )
            record.replay_checkpoints.append(
                _ReplayCheckpoint(
                    observation_id=observation.observation_id,
                    sort_key=_observation_sort_key(observation),
                    posterior=state.copy(),
                    nis=float(nis),
                    gated=bool(gated),
                )
            )
            nises.append(nis)
            if gated:
                gated_observation_ids.append(observation.observation_id)
        state = predict_to(state, until_time, self.process_noise)
        return state, nises, tuple(gated_observation_ids)

    def _invalidate_replay_checkpoints(
        self,
        record: TrackRecord,
        *,
        from_sort_key: tuple[float, float, str] | None = None,
    ) -> None:
        if from_sort_key is None:
            record.replay_checkpoints.clear()
            return
        first_affected = next(
            (
                index
                for index, checkpoint in enumerate(record.replay_checkpoints)
                if checkpoint.sort_key >= from_sort_key
            ),
            len(record.replay_checkpoints),
        )
        del record.replay_checkpoints[first_affected:]

    def _refresh_initial(self, record: TrackRecord) -> None:
        if record.checkpoint_active:
            return
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
        self._invalidate_replay_checkpoints(record)

    def _prune_record(self, record: TrackRecord, current_time: float) -> None:
        """Rebase at the latest observation not newer than the lag boundary.

        The CV process-noise model represents one random acceleration sample per
        prediction interval.  Splitting an existing interval at an arbitrary
        wall-clock boundary changes its covariance and therefore the gain of a
        later nonlinear update.  Anchoring the checkpoint immediately after an
        accepted observation preserves the original prediction intervals while
        still bounding the live observation window.
        """

        if self.buffer_horizon <= 0:
            return
        min_time = current_time - self.buffer_horizon
        if min_time <= record.initial_state.timestamp + 1e-9:
            return

        checkpoint_candidates = [
            observation
            for observation in record.observations
            if observation.measurement_timestamp <= min_time + 1e-9
        ]
        if not checkpoint_candidates:
            return
        checkpoint_timestamp = max(
            float(observation.measurement_timestamp)
            for observation in checkpoint_candidates
        )
        if checkpoint_timestamp < record.initial_state.timestamp - 1e-9:
            return

        state_before_rebase = record.current_state.copy()
        checkpoint, _, _ = self._replay_record(record, checkpoint_timestamp)
        discarded = [
            observation
            for observation in record.observations
            if observation.measurement_timestamp <= checkpoint_timestamp + 1e-9
        ]
        retained = [
            observation
            for observation in record.observations
            if observation.measurement_timestamp > checkpoint_timestamp + 1e-9
        ]
        archived_ids = {
            observation.observation_id for observation in record.archived_observations
        }
        record.archived_observations.extend(
            observation
            for observation in discarded
            if observation.observation_id not in archived_ids
        )
        discarded_count = len(discarded)
        record.initial_state = checkpoint
        record.initial_observation_id = (
            f"fixed-lag-checkpoint:{record.track_id}:{checkpoint_timestamp:.9f}"
        )
        record.observations = retained
        self._invalidate_replay_checkpoints(record)
        record.checkpoint_active = True
        record.checkpoint_count += 1

        rebased_state, rebased_nises, gated_observation_ids = self._replay_record(
            record,
            current_time,
        )
        record.current_state = rebased_state
        record.current_state_covariance_limited = False
        record.recent_nis = deque(rebased_nises[-50:], maxlen=50)
        self._update_filter_gate_metadata(
            record,
            rebased_nises,
            gated_observation_ids,
        )
        continuity_error_m = float(
            np.linalg.norm(rebased_state.state[:3] - state_before_rebase.state[:3])
        )
        record.metadata.update(
            {
                "fixed_lag_checkpoint_active": True,
                "fixed_lag_checkpoint_timestamp": checkpoint_timestamp,
                "fixed_lag_requested_boundary_timestamp": float(min_time),
                "fixed_lag_checkpoint_boundary_lag_s": float(
                    min_time - checkpoint_timestamp
                ),
                "fixed_lag_checkpoint_count": int(record.checkpoint_count),
                "fixed_lag_discarded_observation_count": int(discarded_count),
                "fixed_lag_retained_observation_count": len(retained),
                "fixed_lag_archived_observation_count": len(
                    record.archived_observations
                ),
                "fixed_lag_rebase_continuity_error_m": continuity_error_m,
            }
        )
        self._limit_record_covariance(record)

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
        if observation.modality == "eo":
            source_track_key = observation.metadata.get("source_track_key")
            if source_track_key is not None:
                source_track_key = str(source_track_key).strip()
                if source_track_key:
                    existing = set(record.metadata.get("source_track_ids", ()))
                    existing.add(source_track_key)
                    record.metadata["source_track_ids"] = tuple(sorted(existing))

    def _to_global_track(
        self,
        record: TrackRecord,
        publication_context: _TrackPublicationContext | None = None,
    ) -> GlobalTrack:
        batch_context = self._batch_context
        if batch_context is not None:
            batch_context.global_track_materialization_count += 1
        if not record.current_state_covariance_limited:
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
        if publication_context is None:
            publication_context = _TrackPublicationContext(
                association_audit=self.association_audit_summary(),
                latency_audit=self.latency_audit_summary().to_dict(),
                sensor_health={
                    summary.sensor_id: summary.to_dict()
                    for summary in self.sensor_health_summaries()
                },
            )
            if batch_context is not None:
                batch_context.sensor_health_snapshot_build_count += 1
        metadata.update(
            {
                "a95_m": covariance_a95(record.current_state.covariance),
                "frame_id": "ned",
                "valid_at": record.current_state.timestamp,
                "published_at": self.current_time,
                "hits": record.hits,
                "latency_compensation": self.latency_compensation,
                "source_support": dict(record.source_support),
                "association_diagnostics": dict(record.association_diagnostics),
                "association_audit": dict(publication_context.association_audit),
                "duplicate_observation_count": self.duplicate_observation_count,
                "latency_audit": dict(publication_context.latency_audit),
                "sensor_health": {
                    sensor_id: dict(summary)
                    for sensor_id, summary in publication_context.sensor_health.items()
                },
            }
        )
        self._update_metadata_covariance_reasons(
            metadata,
            tuple(sorted(record.covariance_limit_reasons)),
        )
        return GlobalTrack(
            global_track_id=record.track_id,
            state=record.current_state.state.copy(),
            covariance=record.current_state.covariance.copy(),
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
        innovation_gate = metadata.get("filter_innovation_gate_chi2")
        if innovation_gate is not None:
            innovation_gate = float(innovation_gate)
            if not np.isfinite(innovation_gate) or innovation_gate <= 0.0:
                raise ValueError(
                    "filter_innovation_gate_chi2 must be positive and finite"
                )
            metadata["filter_innovation_gate_chi2"] = innovation_gate
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
        covariance = validate_online_sensor_observation(
            observation,
            context="D1 online fusion",
        ).copy()
        expected_dim = covariance.shape[0]
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
                "observation_covariance_floor",
                "observation_covariance_ceiling",
            }
            for reason in reasons
        ):
            anomaly = True
        return covariance, tuple(dict.fromkeys(reasons)), anomaly

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
        record.current_state_covariance_limited = True
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
        previous_evidence = self._consistency_evidence.get(observation.observation_id)
        if previous_evidence is None:
            self._consistency_evidence[observation.observation_id] = (
                unavailable_consistency_evidence(
                    observation,
                    "observation_not_yet_processed",
                    oosm_replayed=is_oosm,
                )
            )
        elif is_oosm and not previous_evidence.oosm_replayed:
            self._consistency_evidence[observation.observation_id] = (
                mark_consistency_evidence_oosm(previous_evidence)
            )
        state = self._sensor_health_state_for(observation)
        state.observation_count += 1
        state.latest_observation_timestamp = float(observation.arrival_timestamp)
        state.max_timestamp_uncertainty_s = max(
            state.max_timestamp_uncertainty_s,
            float(observation.timestamp_uncertainty_s or 0.0),
        )
        latency_s = max(0.0, float(observation.latency))
        state.latency_sum_s += latency_s
        state.max_latency_s = max(state.max_latency_s, latency_s)

        faults: list[str] = []
        if is_oosm:
            state.oosm_count += 1
            if not state.oosm_expected:
                state.unexpected_oosm_count += 1
                faults.append("unexpected_oosm_observation")
        if (
            state.expected_latency_s is not None
            and latency_s
            > state.expected_latency_s + float(state.latency_tolerance_s or 0.0) + 1e-9
        ):
            state.latency_budget_exceedance_count += 1
            faults.append("latency_budget_exceeded")
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
        if rejected:
            previous = self._consistency_evidence.get(observation.observation_id)
            if (
                reason == "duplicate_observation"
                and previous is not None
                and previous.disposition != "observation_not_yet_processed"
            ):
                self._consistency_evidence[observation.observation_id] = (
                    mark_consistency_evidence_duplicate(previous)
                )
            else:
                self._mark_consistency_unavailable(observation, str(reason))
                if reason == "duplicate_observation":
                    self._consistency_evidence[observation.observation_id] = (
                        mark_consistency_evidence_duplicate(
                            self._consistency_evidence[observation.observation_id]
                        )
                    )
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

    def _sensor_health_state_for(self, observation: SensorObservation) -> SensorHealthState:
        state = self.sensor_health.get(observation.sensor_id)
        if state is not None:
            return state
        expectation = self._timing_expectation_for(observation)
        state = SensorHealthState(
            sensor_id=observation.sensor_id,
            expected_latency_s=(
                None if expectation is None else float(expectation.expected_latency_s)
            ),
            latency_tolerance_s=(
                None if expectation is None else float(expectation.latency_tolerance_s)
            ),
            oosm_expected=False if expectation is None else bool(expectation.oosm_expected),
        )
        self.sensor_health[observation.sensor_id] = state
        return state

    def _timing_expectation_for(
        self,
        observation: SensorObservation,
    ) -> SensorTimingExpectation | None:
        configured = self.sensor_timing_expectations.get(observation.sensor_id)
        if configured is None:
            configured = self.sensor_timing_expectations.get(observation.modality)
        if configured is not None:
            return configured
        expected_latency = observation.metadata.get("expected_latency_s")
        if expected_latency is None:
            return None
        return SensorTimingExpectation(
            expected_latency_s=float(expected_latency),
            latency_tolerance_s=float(observation.metadata.get("latency_tolerance_s", 0.05)),
            oosm_expected=observation.metadata.get("oosm_expected", False),
        )

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
            expected_latency_s=state.expected_latency_s,
            latency_tolerance_s=state.latency_tolerance_s,
            mean_latency_s=(
                state.latency_sum_s / state.observation_count
                if state.observation_count > 0
                else 0.0
            ),
            max_latency_s=state.max_latency_s,
            latency_budget_exceedance_count=state.latency_budget_exceedance_count,
            latency_budget_exceedance_rate=(
                state.latency_budget_exceedance_count / state.observation_count
                if state.observation_count > 0
                else 0.0
            ),
            oosm_expected=state.oosm_expected,
            unexpected_oosm_count=state.unexpected_oosm_count,
            oosm_rate=(
                state.oosm_count / state.observation_count
                if state.observation_count > 0
                else 0.0
            ),
        )

    def _sensor_status(self, state: SensorHealthState) -> str:
        if (
            state.reject_count >= self.sensor_isolation_reject_threshold
            or state.anomalous_covariance_count >= self.sensor_isolation_reject_threshold
            or state.stale_count + state.unexpected_oosm_count
            >= self.sensor_isolation_reject_threshold
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
        ordered = sorted(observations, key=lambda obs: obs.arrival_timestamp)
        return list(self.process_batch(ordered).tracks)


def _metadata_from_observation(observation: SensorObservation) -> dict:
    metadata = {
        "latest_observation_id": observation.observation_id,
        "latest_sensor_id": observation.sensor_id,
        "latest_modality": observation.modality,
        "latest_measurement_timestamp": observation.measurement_timestamp,
        "latest_arrival_timestamp": observation.arrival_timestamp,
        "measurement_timestamp": observation.measurement_timestamp,
        "arrival_timestamp": observation.arrival_timestamp,
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
