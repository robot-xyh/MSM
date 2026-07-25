from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from numbers import Integral, Real
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
from .ekf import EKFState, ekf_update, predict_to, predict_to_with_cv_model
from .motion import cv_process_noise, cv_transition, wrap_residual
from .observations import (
    MeasurementModel,
    RadarCovarianceConfig,
    measurement_model_for,
    radar_state_from_observation,
)
from .publication_audit import (
    PUBLICATION_AUDIT_TREE_CONTRACT_VERSION,
    PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID,
    PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION_ID,
    ImmutablePublicationAuditMap,
    freeze_publication_audit_tree,
)
from .types import (
    COMMUNICATION_METADATA_KEYS,
    DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_EPOCH,
    DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
    FusionBatchResult,
    FusionBatchSummary,
    FusionPerformanceDiagnostics,
    FusionQualityRegionSummary,
    FusionStateUpdateResult,
    FusionTrackSnapshot,
    GlobalTrack,
    LatencyAuditSummary,
    SensorHealthSummary,
    SensorObservation,
    SensorTimingExpectation,
    StructuralAmbiguityCandidateEdge,
    StructuralAmbiguityEvidence,
    StructuralAmbiguityMemberState,
    StructuralAmbiguityObservationEvidence,
    STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION,
    TrackLevel,
    TrackUncertaintySummary,
    structural_ambiguity_member_track_token,
    structural_ambiguity_source_key,
    structural_ambiguity_source_track_id,
)

CHI2_2_95 = 5.991464547107979
CHI2_3_999 = 16.26623619623813
CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION_ID = (
    "d1.fusion.cv_motion_model.per_prediction_build.v1"
)
CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION_ID = (
    "d1.fusion.cv_motion_model.bounded_exact_lru.v1"
)
CV_MOTION_MODEL_CACHE_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.cv_motion_model_cache_diagnostics.v1"
)
DEFAULT_CV_MOTION_MODEL_CACHE_CAPACITY = 128
MAX_CV_MOTION_MODEL_CACHE_CAPACITY = 4_096
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
    "observation_covariance_limit_operation_count",
    "observation_covariance_limit_operation_counts",
    "track_covariance_limit_reasons",
    "track_covariance_limit_operation_count",
    "track_covariance_limit_operation_counts",
    "covariance_limit_reasons",
    "covariance_limit_operation_count",
    "covariance_limit_operation_counts",
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
_COVARIANCE_STRICT_UPPER_INDICES = tuple(
    np.triu_indices(dimension, k=1) for dimension in range(7)
)
for _upper_rows, _upper_columns in _COVARIANCE_STRICT_UPPER_INDICES:
    _upper_rows.setflags(write=False)
    _upper_columns.setflags(write=False)
COVARIANCE_CORRELATION_LIMIT = 0.999
COVARIANCE_PSD_NORMALIZED_EIGENVALUE_FLOOR = 1.0e-12
COVARIANCE_PSD_MAX_PROJECTION_ITERATIONS = 3
RADAR_ASSOCIATION_LOWER_BOUND_RELATIVE_MARGIN = 1.0e-12
RADAR_ASSOCIATION_PINV_RCOND = 1.0e-15
RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION = (
    "fail_closed_gate_feasible_alternating_cycle_v1"
)
RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION = (
    "fail_closed_maximum_matching_allowed_edge_component_v2"
)
RADAR_ASSIGNMENT_AMBIGUITY_CANDIDATE_POLICY_VERSIONS = (
    RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION,
    RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION,
)
RADAR_ASSIGNMENT_AMBIGUITY_V2_GOVERNANCE_STATUS = (
    "experimental_v2_enabled_rejected_candidate"
)
RADAR_ASSIGNMENT_AMBIGUITY_HOLD_EVIDENCE_STATUS = (
    "experimental_hold_evidence_enabled_pending_main_clean_ab"
)
RADAR_ASSIGNMENT_AMBIGUITY_NEUTRAL_CENTROID_STATUS = (
    "experimental_identity_neutral_centroid_candidate_not_promoted"
)
NEUTRAL_CENTROID_MAX_CONFIGURABLE_COMPONENT_SIZE = 256
NEUTRAL_CENTROID_MAX_GENERATION_REGISTRY_ENTRIES = 1_000_000
_NEUTRAL_CENTROID_IDENTITY_METADATA_EXACT_KEYS = frozenset(
    {
        "actor",
        "actor_id",
        "actor_name",
        "offline_label",
        "target",
        "target_id",
        "target_label",
        "target_name",
        "truth",
        "truth_id",
        "truth_label",
    }
)
_NEUTRAL_CENTROID_IDENTITY_METADATA_MARKERS = (
    "actor",
    "offline",
    "target_id",
    "target_label",
    "target_name",
    "truth",
)
_NEUTRAL_CENTROID_IDENTITY_METADATA_ALLOWED_KEYS = frozenset(
    {
        "target_node_id",
    }
)
def _strict_real_parameter(
    value: object,
    name: str,
    *,
    minimum: float,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    number = float(value)
    if not np.isfinite(number):
        raise ValueError(f"{name} must be finite")
    below_minimum = (
        number < minimum
        if minimum_inclusive
        else number <= minimum
    )
    if below_minimum:
        qualifier = "at least" if minimum_inclusive else "greater than"
        raise ValueError(f"{name} must be {qualifier} {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return number


def _contains_neutral_centroid_identity_metadata(value: object) -> bool:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().lower()
            if key not in _NEUTRAL_CENTROID_IDENTITY_METADATA_ALLOWED_KEYS and (
                key in _NEUTRAL_CENTROID_IDENTITY_METADATA_EXACT_KEYS
                or any(
                    marker in key
                    for marker in _NEUTRAL_CENTROID_IDENTITY_METADATA_MARKERS
                )
            ):
                return True
            if _contains_neutral_centroid_identity_metadata(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(
            _contains_neutral_centroid_identity_metadata(item)
            for item in value
        )
    return False


def _radar_lower_bound_applicability(
    innovation_covariances: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Certify matrices where the legacy pseudoinverse equals an inverse.

    Exact symmetry plus a positive Gershgorin lower bound proves strict
    positive definiteness.  Requiring that lower bound to exceed an upper
    bound on NumPy ``pinv``'s singular-value cutoff proves that no eigenmode is
    truncated by the legacy solve.  Uncertified matrices must use ``pinv``.
    """

    transposed = np.swapaxes(innovation_covariances, -1, -2)
    finite = np.all(np.isfinite(innovation_covariances), axis=(-2, -1))
    exactly_symmetric = np.all(
        innovation_covariances == transposed,
        axis=(-2, -1),
    )
    diagonal = np.diagonal(innovation_covariances, axis1=-2, axis2=-1)
    absolute_row_sums = np.sum(np.abs(innovation_covariances), axis=-1)
    off_diagonal_radii = absolute_row_sums - np.abs(diagonal)
    gershgorin_lower = np.min(diagonal - off_diagonal_radii, axis=-1)
    spectral_upper = np.max(absolute_row_sums, axis=-1)
    safe_spectral_upper = spectral_upper * (
        1.0 + RADAR_ASSOCIATION_LOWER_BOUND_RELATIVE_MARGIN
    )
    safe_gershgorin_lower = (
        gershgorin_lower
        - RADAR_ASSOCIATION_LOWER_BOUND_RELATIVE_MARGIN * spectral_upper
    )
    cutoff_upper = RADAR_ASSOCIATION_PINV_RCOND * safe_spectral_upper
    certified = (
        finite
        & exactly_symmetric
        & (safe_spectral_upper > 0.0)
        & (safe_gershgorin_lower > 0.0)
        & (safe_gershgorin_lower > cutoff_upper)
    )
    return certified, safe_spectral_upper


def _radar_lower_bound_rejection_mask(
    differences: np.ndarray,
    innovation_covariances: np.ndarray,
    association_gate: float,
) -> np.ndarray:
    """Return pairs whose Mahalanobis distance must exceed the gate.

    For a certified ``S``, the legacy pseudoinverse retains every eigenmode
    and therefore equals ``inv(S)``.  Its quadratic form is bounded below by
    ``||d||^2 / ||S||_2``; the maximum absolute row sum is a conservative
    upper bound for ``||S||_2``.  Uncertified pairs are never pre-rejected.
    """

    squared_distances = np.einsum("toi,toi->to", differences, differences)
    certified, spectral_upper = _radar_lower_bound_applicability(
        innovation_covariances
    )
    threshold = (
        float(association_gate)
        * spectral_upper
        * (1.0 + RADAR_ASSOCIATION_LOWER_BOUND_RELATIVE_MARGIN)
    )
    return (
        certified
        & np.isfinite(squared_distances)
        & (squared_distances > threshold)
    )


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


def _strongly_connected_assignment_components(
    adjacency: dict[int, tuple[int, ...]],
) -> tuple[tuple[int, ...], ...]:
    """Return deterministic strongly connected components for assignment rows."""

    next_index = 0
    indices: dict[int, int] = {}
    low_links: dict[int, int] = {}
    stack: list[int] = []
    on_stack: set[int] = set()
    components: list[tuple[int, ...]] = []

    def visit(node: int) -> None:
        nonlocal next_index
        indices[node] = next_index
        low_links[node] = next_index
        next_index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency.get(node, ()):
            if neighbor not in indices:
                visit(neighbor)
                low_links[node] = min(low_links[node], low_links[neighbor])
            elif neighbor in on_stack:
                low_links[node] = min(low_links[node], indices[neighbor])

        if low_links[node] != indices[node]:
            return
        component: list[int] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for node in sorted(adjacency):
        if node not in indices:
            visit(node)
    return tuple(sorted(components, key=lambda item: item[0]))


def _reachable_assignment_vertices(
    adjacency: dict[int, tuple[int, ...]],
    starts: Iterable[int],
) -> frozenset[int]:
    """Return vertices reachable from ``starts`` in a deterministic graph."""

    reached: set[int] = set()
    pending = list(reversed(sorted(set(int(item) for item in starts))))
    while pending:
        node = pending.pop()
        if node in reached:
            continue
        reached.add(node)
        for neighbor in reversed(adjacency.get(node, ())):
            if neighbor not in reached:
                pending.append(neighbor)
    return frozenset(reached)


def _maximum_cardinality_assignment(
    valid: np.ndarray,
    preferred_row_to_column: dict[int, int],
    cost_matrix: np.ndarray,
) -> dict[int, int]:
    """Extend a valid preferred matching to maximum cardinality.

    The online Hungarian result is already maximum-cardinality when SciPy is
    available. This augmenting-path pass certifies that property and repairs
    the deterministic greedy fallback without enumerating matchings.
    """

    valid = np.asarray(valid, dtype=bool)
    costs = np.asarray(cost_matrix, dtype=float)
    if valid.ndim != 2 or costs.shape != valid.shape:
        raise ValueError("valid and cost_matrix must be matching 2D arrays")

    row_count, column_count = valid.shape
    row_to_column: dict[int, int] = {}
    column_to_row: dict[int, int] = {}
    for row, column in sorted(preferred_row_to_column.items()):
        row = int(row)
        column = int(column)
        if (
            0 <= row < row_count
            and 0 <= column < column_count
            and bool(valid[row, column])
            and row not in row_to_column
            and column not in column_to_row
        ):
            row_to_column[row] = column
            column_to_row[column] = row

    column_order = tuple(
        tuple(
            sorted(
                np.flatnonzero(valid[row]).tolist(),
                key=lambda column: (float(costs[row, column]), int(column)),
            )
        )
        for row in range(row_count)
    )

    def augment(
        row: int,
        visited_rows: set[int],
        visited_columns: set[int],
    ) -> bool:
        if row in visited_rows:
            return False
        visited_rows.add(row)
        for column in column_order[row]:
            if column in visited_columns:
                continue
            visited_columns.add(column)
            owner = column_to_row.get(column)
            if owner is not None and not augment(
                owner,
                visited_rows,
                visited_columns,
            ):
                continue
            row_to_column[row] = column
            column_to_row[column] = row
            return True
        return False

    for row in range(row_count):
        if row not in row_to_column:
            augment(row, set(), set())
    return dict(sorted(row_to_column.items()))


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
    covariance_limit_operation_counts: Counter = field(default_factory=Counter)
    association_diagnostics: Counter = field(default_factory=Counter)
    checkpoint_active: bool = False
    checkpoint_count: int = 0
    origin_state: EKFState | None = None
    origin_observation_id: str | None = None
    archived_observations: list[SensorObservation] = field(default_factory=list)
    accepted_observer_scan_keys: set[tuple[str, str, str]] = field(default_factory=set)
    replay_checkpoints: list["_ReplayCheckpoint"] = field(default_factory=list)
    replay_checkpoints_complete: bool = False
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
    association_audit: Mapping[str, Any]
    latency_audit: Mapping[str, Any]
    sensor_health: Mapping[str, Mapping[str, Any]]


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
    checkpoint_state_query_count: int = 0
    fixed_lag_rebase_count: int = 0
    fixed_lag_checkpoint_suffix_reuse_count: int = 0
    replay_checkpoint_prefix_fast_path_count: int = 0
    cached_consistency_refresh_count: int = 0


@dataclass(frozen=True)
class _RadarAmbiguityCandidateEdge:
    track_id: str
    observation_index: int
    nis: float
    edge_roles: tuple[str, ...]


@dataclass(frozen=True)
class _RadarAssignmentAmbiguity:
    track_ids: tuple[str, ...]
    component_size: int
    observation_indices: tuple[int, ...] = ()
    observation_count: int = 0
    candidate_edges: tuple[_RadarAmbiguityCandidateEdge, ...] = ()
    deferred_birth_observation_indices: tuple[int, ...] = ()
    free_row_count: int = 0
    free_column_count: int = 0
    maximum_matching_cardinality: int = 0
    component_kinds: tuple[str, ...] = ("alternating_cycle",)
    reason: str = "gate_feasible_alternating_cycle"
    policy_version: str = RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION


@dataclass(frozen=True)
class _ScanAssociationResult:
    assignments: dict[int, str]
    radar_ambiguities: dict[int, _RadarAssignmentAmbiguity] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class _NeutralCentroidCorrection:
    track_ids: tuple[str, ...]
    translation_ned: np.ndarray
    position_covariance_inflation: np.ndarray
    centroid_nis: float
    shape_mismatch_m2: float
    linear_input_operation_count: int


@dataclass(frozen=True)
class _NeutralCentroidGenerationWatermark:
    max_seen_generation: int
    max_applied_generation: int
    last_measurement_timestamp: float


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
        immutable_shared_publication_metadata: bool = False,
        scan_association_model_cache: bool = True,
        batched_non_radar_innovation_solve: bool = True,
        radar_association_lower_bound_gate: bool = True,
        reuse_track_classification_a95: bool = True,
        direct_checkpoint_state_queries: bool = True,
        fixed_lag_checkpoint_suffix_reuse: bool = True,
        trusted_replay_checkpoint_prefix: bool = True,
        cached_consistency_prefix_refresh: bool = True,
        trusted_consistency_counter_refresh: bool = True,
        radar_assignment_ambiguity_governance: bool = False,
        radar_assignment_ambiguity_governance_v2: bool = False,
        radar_assignment_ambiguity_hold_evidence: bool = False,
        publish_opaque_source_key: bool = False,
        radar_assignment_ambiguity_neutral_centroid_correction: bool = False,
        neutral_centroid_max_component_size: int = 8,
        neutral_centroid_gain: float = 0.5,
        neutral_centroid_max_translation_m: float = 30.0,
        neutral_centroid_gate_chi2: float = CHI2_3_999,
        neutral_centroid_shape_gate_m2: float = 2_500.0,
        neutral_centroid_shape_inflation_scale: float = 0.05,
        neutral_centroid_min_position_variance_m2: float = 0.25,
        neutral_centroid_generation_registry_max_entries: int = 1_024,
        publisher_node_id: str = DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
        publisher_epoch: str = DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_EPOCH,
        vectorized_covariance_limit: bool = True,
        cached_cv_motion_model: bool = False,
        cv_motion_model_cache_capacity: int = (
            DEFAULT_CV_MOTION_MODEL_CACHE_CAPACITY
        ),
    ) -> None:
        self.process_noise = float(process_noise)
        self.bucket_size = float(bucket_size)
        self.buffer_horizon = float(buffer_horizon)
        self.stable_threshold_m = float(stable_threshold_m)
        self.handover_threshold_m = float(handover_threshold_m)
        self.association_gate = float(association_gate)
        self.latency_compensation = bool(latency_compensation)
        self.use_truth_hints_for_association = bool(use_truth_hints_for_association)
        if not isinstance(radar_assignment_ambiguity_governance, bool):
            raise TypeError(
                "radar_assignment_ambiguity_governance must be a bool"
            )
        self.radar_assignment_ambiguity_governance = (
            radar_assignment_ambiguity_governance
        )
        if not isinstance(radar_assignment_ambiguity_governance_v2, bool):
            raise TypeError(
                "radar_assignment_ambiguity_governance_v2 must be a bool"
            )
        self.radar_assignment_ambiguity_governance_v2 = (
            radar_assignment_ambiguity_governance_v2
        )
        if not isinstance(radar_assignment_ambiguity_hold_evidence, bool):
            raise TypeError(
                "radar_assignment_ambiguity_hold_evidence must be a bool"
            )
        self.radar_assignment_ambiguity_hold_evidence = (
            radar_assignment_ambiguity_hold_evidence
        )
        if not isinstance(publish_opaque_source_key, bool):
            raise TypeError("publish_opaque_source_key must be a bool")
        self.publish_opaque_source_key = publish_opaque_source_key
        self.opaque_source_key_publication_enabled = bool(
            self.radar_assignment_ambiguity_hold_evidence
            or self.publish_opaque_source_key
        )
        if not isinstance(
            radar_assignment_ambiguity_neutral_centroid_correction,
            bool,
        ):
            raise TypeError(
                "radar_assignment_ambiguity_neutral_centroid_correction "
                "must be a bool"
            )
        self.radar_assignment_ambiguity_neutral_centroid_correction = (
            radar_assignment_ambiguity_neutral_centroid_correction
        )
        if (
            self.radar_assignment_ambiguity_neutral_centroid_correction
            and not self.radar_assignment_ambiguity_hold_evidence
        ):
            raise ValueError(
                "neutral centroid correction requires "
                "radar_assignment_ambiguity_hold_evidence=True"
            )
        if (
            self.radar_assignment_ambiguity_neutral_centroid_correction
            and self.use_truth_hints_for_association
        ):
            raise ValueError(
                "neutral centroid correction is incompatible with "
                "use_truth_hints_for_association"
            )
        if (
            isinstance(neutral_centroid_max_component_size, bool)
            or not isinstance(neutral_centroid_max_component_size, Integral)
        ):
            raise TypeError(
                "neutral_centroid_max_component_size must be an integer"
            )
        self.neutral_centroid_max_component_size = int(
            neutral_centroid_max_component_size
        )
        if self.neutral_centroid_max_component_size < 2:
            raise ValueError(
                "neutral_centroid_max_component_size must be at least 2"
            )
        if (
            self.neutral_centroid_max_component_size
            > NEUTRAL_CENTROID_MAX_CONFIGURABLE_COMPONENT_SIZE
        ):
            raise ValueError(
                "neutral_centroid_max_component_size must be at most "
                f"{NEUTRAL_CENTROID_MAX_CONFIGURABLE_COMPONENT_SIZE}"
            )
        self.neutral_centroid_gain = _strict_real_parameter(
            neutral_centroid_gain,
            "neutral_centroid_gain",
            minimum=0.0,
            maximum=1.0,
        )
        self.neutral_centroid_max_translation_m = _strict_real_parameter(
            neutral_centroid_max_translation_m,
            "neutral_centroid_max_translation_m",
            minimum=0.0,
            minimum_inclusive=False,
        )
        self.neutral_centroid_gate_chi2 = _strict_real_parameter(
            neutral_centroid_gate_chi2,
            "neutral_centroid_gate_chi2",
            minimum=0.0,
            minimum_inclusive=False,
        )
        self.neutral_centroid_shape_gate_m2 = _strict_real_parameter(
            neutral_centroid_shape_gate_m2,
            "neutral_centroid_shape_gate_m2",
            minimum=0.0,
        )
        self.neutral_centroid_shape_inflation_scale = _strict_real_parameter(
            neutral_centroid_shape_inflation_scale,
            "neutral_centroid_shape_inflation_scale",
            minimum=0.0,
        )
        self.neutral_centroid_min_position_variance_m2 = (
            _strict_real_parameter(
                neutral_centroid_min_position_variance_m2,
                "neutral_centroid_min_position_variance_m2",
                minimum=0.0,
            )
        )
        if (
            isinstance(neutral_centroid_generation_registry_max_entries, bool)
            or not isinstance(
                neutral_centroid_generation_registry_max_entries,
                Integral,
            )
        ):
            raise TypeError(
                "neutral_centroid_generation_registry_max_entries "
                "must be an integer"
            )
        self.neutral_centroid_generation_registry_max_entries = int(
            neutral_centroid_generation_registry_max_entries
        )
        if self.neutral_centroid_generation_registry_max_entries < 1:
            raise ValueError(
                "neutral_centroid_generation_registry_max_entries "
                "must be at least 1"
            )
        if (
            self.neutral_centroid_generation_registry_max_entries
            > NEUTRAL_CENTROID_MAX_GENERATION_REGISTRY_ENTRIES
        ):
            raise ValueError(
                "neutral_centroid_generation_registry_max_entries "
                "must be at most "
                f"{NEUTRAL_CENTROID_MAX_GENERATION_REGISTRY_ENTRIES}"
            )
        if (
            self.radar_assignment_ambiguity_governance
            and self.radar_assignment_ambiguity_governance_v2
        ):
            raise ValueError(
                "radar assignment ambiguity v1 and v2 cannot both be enabled"
            )
        enabled_ambiguity_policies = sum(
            (
                self.radar_assignment_ambiguity_governance,
                self.radar_assignment_ambiguity_governance_v2,
                self.radar_assignment_ambiguity_hold_evidence,
            )
        )
        if enabled_ambiguity_policies > 1:
            raise ValueError(
                "radar assignment ambiguity hold evidence is mutually exclusive "
                "with v1 and v2"
            )
        structural_ambiguity_member_track_token(
            publisher_node_id,
            publisher_epoch,
            "__configuration_validation__",
        )
        self.publisher_node_id = str(publisher_node_id).strip()
        self.publisher_epoch = str(publisher_epoch).strip()
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
        if not isinstance(immutable_shared_publication_metadata, bool):
            raise TypeError(
                "immutable_shared_publication_metadata must be a bool"
            )
        self.immutable_shared_publication_metadata = (
            immutable_shared_publication_metadata
        )
        if (
            self.immutable_shared_publication_metadata
            and not self.shared_publication_audit_snapshot
        ):
            raise ValueError(
                "immutable shared publication metadata requires "
                "shared_publication_audit_snapshot=True"
            )
        self.scan_association_model_cache = bool(scan_association_model_cache)
        self.batched_non_radar_innovation_solve = bool(
            batched_non_radar_innovation_solve
        )
        self.radar_association_lower_bound_gate = bool(
            radar_association_lower_bound_gate
        )
        self.reuse_track_classification_a95 = bool(
            reuse_track_classification_a95
        )
        self.direct_checkpoint_state_queries = bool(direct_checkpoint_state_queries)
        self.fixed_lag_checkpoint_suffix_reuse = bool(
            fixed_lag_checkpoint_suffix_reuse
        )
        self.trusted_replay_checkpoint_prefix = bool(
            trusted_replay_checkpoint_prefix
        )
        self.cached_consistency_prefix_refresh = bool(
            cached_consistency_prefix_refresh
        )
        self.trusted_consistency_counter_refresh = bool(
            trusted_consistency_counter_refresh
        )
        if not isinstance(vectorized_covariance_limit, bool):
            raise TypeError("vectorized_covariance_limit must be a bool")
        self.vectorized_covariance_limit = vectorized_covariance_limit
        if not isinstance(cached_cv_motion_model, bool):
            raise TypeError("cached_cv_motion_model must be a bool")
        self.cached_cv_motion_model = cached_cv_motion_model
        if (
            isinstance(cv_motion_model_cache_capacity, bool)
            or not isinstance(cv_motion_model_cache_capacity, Integral)
        ):
            raise TypeError(
                "cv_motion_model_cache_capacity must be an integer"
            )
        self.cv_motion_model_cache_capacity = int(
            cv_motion_model_cache_capacity
        )
        if self.cv_motion_model_cache_capacity < 1:
            raise ValueError(
                "cv_motion_model_cache_capacity must be at least 1"
            )
        if (
            self.cv_motion_model_cache_capacity
            > MAX_CV_MOTION_MODEL_CACHE_CAPACITY
        ):
            raise ValueError(
                "cv_motion_model_cache_capacity must be at most "
                f"{MAX_CV_MOTION_MODEL_CACHE_CAPACITY}"
            )
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
        self.radar_assignment_ambiguity_scan_count = 0
        self.radar_assignment_ambiguity_observation_suppression_count = 0
        self.radar_assignment_ambiguity_track_coast_count = 0
        self.max_radar_assignment_ambiguity_component_size = 0
        self.structural_ambiguity_evidence_component_count = 0
        self.structural_ambiguity_evidence_observation_count = 0
        self.structural_ambiguity_evidence_member_count = 0
        self.structural_ambiguity_deferred_birth_count = 0
        self.structural_ambiguity_prediction_only_member_count = 0
        self.non_range_state_correction_rejection_count = 0
        self.pre_checkpoint_oosm_replay_count = 0
        self.max_non_range_position_correction_score = 0.0
        self.eo_projection_gate_pass_count = 0
        self.eo_projection_gate_rejection_count = 0
        self.eo_projection_unavailable_count = 0
        self.eo_one_to_one_unassigned_count = 0
        self.max_eo_projection_gate_pass_nis = 0.0
        self._latest_eo_projection_rejection_reason: str | None = None
        self._latest_radar_assignment_ambiguity_track_ids: tuple[str, ...] = ()
        self._structural_ambiguity_component_generations: Counter[str] = Counter()
        self._latest_structural_ambiguity_component_ids: tuple[str, ...] = ()
        self.neutral_centroid_candidate_component_count = 0
        self.neutral_centroid_applied_component_count = 0
        self.neutral_centroid_applied_member_count = 0
        self.neutral_centroid_rejected_component_count = 0
        self.neutral_centroid_duplicate_generation_rejection_count = 0
        self.neutral_centroid_regressed_generation_rejection_count = 0
        self.neutral_centroid_generation_registry_peak_entry_count = 0
        self.neutral_centroid_generation_registry_eviction_count = 0
        self.neutral_centroid_generation_registry_capacity_rejection_count = 0
        self.neutral_centroid_linear_input_operation_count = 0
        self.max_neutral_centroid_component_size = 0
        self.max_neutral_centroid_nis = 0.0
        self.max_neutral_centroid_shape_mismatch_m2 = 0.0
        self.max_neutral_centroid_translation_m = 0.0
        self._neutral_centroid_rejection_reasons: Counter[str] = Counter()
        self._latest_neutral_centroid_rejection_reason: str | None = None
        self._latest_neutral_centroid_applied_evidence_id: str | None = None
        self._neutral_centroid_generation_registry: dict[
            str,
            _NeutralCentroidGenerationWatermark,
        ] = {}
        self._last_association_rejection_reason: str | None = None
        self._last_association_rejection_track_ids: tuple[str, ...] = ()
        self._batch_context: _BatchProcessingContext | None = None
        self._consistency_evidence: dict[str, OnlineConsistencyEvidenceRecord] = {}
        self._consistency_replay_revision = 0
        self._consistency_capture_context: tuple[str, int] | None = None
        self._performance_totals: Counter[str] = Counter()
        self._publication_materialization_operations: Counter[str] = Counter()
        self._cv_motion_model_cache: OrderedDict[
            tuple[float, float],
            tuple[np.ndarray, np.ndarray],
        ] = OrderedDict()
        self._cv_motion_model_cache_operations: Counter[str] = Counter()

    def _bucket(self, timestamp: float) -> int:
        """Return the fixed-lag cache bucket for a timestamp."""

        return int(np.floor((float(timestamp) + 1e-9) / self.bucket_size))

    def _predict_to(self, state: EKFState, timestamp: float) -> EKFState:
        """Predict through the selected CV model-construction implementation."""

        timestamp = float(timestamp)
        dt = timestamp - state.timestamp
        operations = self._cv_motion_model_cache_operations
        operations["prediction_request_count"] += 1
        if dt <= 1.0e-12:
            operations["nonpositive_dt_reference_bypass_count"] += 1
            return predict_to(state, timestamp, self.process_noise)

        if not self.cached_cv_motion_model:
            operations["model_build_count"] += 1
            return predict_to(state, timestamp, self.process_noise)

        process_noise = float(self.process_noise)
        if not np.isfinite(dt) or not np.isfinite(process_noise):
            operations["nonfinite_reference_bypass_count"] += 1
            operations["model_build_count"] += 1
            return predict_to(state, timestamp, process_noise)

        key = (float(dt), process_noise)
        model = self._cv_motion_model_cache.get(key)
        if model is None:
            operations["cache_miss_count"] += 1
            operations["model_build_count"] += 1
            transition = cv_transition(dt)
            process_covariance = cv_process_noise(dt, process_noise)
            transition.setflags(write=False)
            process_covariance.setflags(write=False)
            if (
                len(self._cv_motion_model_cache)
                >= self.cv_motion_model_cache_capacity
            ):
                self._cv_motion_model_cache.popitem(last=False)
                operations["cache_eviction_count"] += 1
            model = (transition, process_covariance)
            self._cv_motion_model_cache[key] = model
            operations["peak_entry_count"] = max(
                int(operations["peak_entry_count"]),
                len(self._cv_motion_model_cache),
            )
        else:
            operations["cache_hit_count"] += 1
            self._cv_motion_model_cache.move_to_end(key)

        return predict_to_with_cv_model(
            state,
            timestamp,
            model[0],
            model[1],
        )

    def cv_motion_model_cache_diagnostics(self) -> dict[str, Any]:
        """Return bounded scalar diagnostics for the explicit A/B candidate."""

        implementation_id = (
            CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION_ID
            if self.cached_cv_motion_model
            else CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION_ID
        )
        return {
            "schema_version": (
                CV_MOTION_MODEL_CACHE_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "implementation_id": implementation_id,
            "candidate_enabled": bool(self.cached_cv_motion_model),
            "cache_capacity": int(self.cv_motion_model_cache_capacity),
            "cache_entry_count": len(self._cv_motion_model_cache),
            "operation_counts": dict(
                sorted(self._cv_motion_model_cache_operations.items())
            ),
        }

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
        self._accumulate_batch_performance(
            context,
            observation_count=len(prepared),
            scan_batch=False,
        )
        return FusionBatchResult(tracks=tracks, summary=summary)

    def process_scan_batch(
        self,
        observations: Iterable[SensorObservation],
        *,
        materialize_tracks: bool = True,
    ) -> FusionBatchResult | FusionStateUpdateResult:
        """Fuse one identity-free observer scan with one-to-one association.

        Unlike :meth:`process_batch`, this entry point intentionally does not
        emulate sequential association. All observations are associated against
        the pre-scan track set at once, and every unmatched radar detection may
        start its own track. This prevents a loose single-observation gate from
        suppressing nearby but distinct detections during dense-track birth.

        The default remains a fully materialized :class:`FusionBatchResult`.
        Runtime orchestrators that release several scans in one tick may pass
        ``materialize_tracks=False`` for each scan, then call
        :meth:`materialize_global_tracks` once after the final state update.
        State-only results fail closed if their ``tracks`` property is accessed.
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

        if not isinstance(materialize_tracks, bool):
            raise TypeError("materialize_tracks must be a bool")

        duplicate_before = self.duplicate_observation_count
        context = _BatchProcessingContext()
        tracks: tuple[GlobalTrack, ...] | None = None
        structural_ambiguity_evidence: tuple[
            StructuralAmbiguityEvidence, ...
        ] = ()
        scan_has_oosm = False
        scan_has_stale_observation = False
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
                scan_has_oosm = scan_has_oosm or is_oosm
                scan_has_stale_observation = (
                    scan_has_stale_observation or is_stale
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
            association_result = self._scan_one_to_one_assignments(
                effective,
                pre_scan_track_ids,
            )
            if self.radar_assignment_ambiguity_hold_evidence:
                structural_ambiguity_evidence = (
                    self._build_structural_ambiguity_evidence(
                        effective,
                        association_result,
                        published_at=current_time,
                    )
                )
                self._record_structural_ambiguity_prediction_only(
                    association_result,
                    structural_ambiguity_evidence,
                )
                if (
                    self.radar_assignment_ambiguity_neutral_centroid_correction
                ):
                    self._apply_structural_ambiguity_neutral_centroid_corrections(
                        effective,
                        association_result,
                        structural_ambiguity_evidence,
                        scan_has_oosm=scan_has_oosm,
                        scan_has_stale_observation=(
                            scan_has_stale_observation
                        ),
                    )
            else:
                self._record_radar_assignment_ambiguity_tracks(
                    effective,
                    association_result,
                )
            for observation_index, observation in enumerate(effective):
                ambiguity = association_result.radar_ambiguities.get(
                    observation_index
                )
                if ambiguity is not None:
                    self._record_association_rejection(
                        observation,
                        (
                            "structural_ambiguity_prediction_only"
                            if self.radar_assignment_ambiguity_hold_evidence
                            else "radar_assignment_ambiguity_suppressed"
                        ),
                        ambiguity.track_ids,
                    )
                    self._mark_observation_processed(observation)
                    continue

                track_id = association_result.assignments.get(observation_index)
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
            if materialize_tracks:
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
        self._accumulate_batch_performance(
            context,
            observation_count=len(prepared),
            scan_batch=True,
        )
        if tracks is None:
            return FusionStateUpdateResult(
                summary=summary,
                current_track_count=len(self.tracks),
                structural_ambiguity_evidence=structural_ambiguity_evidence,
            )
        return FusionBatchResult(
            tracks=tracks,
            summary=summary,
            structural_ambiguity_evidence=structural_ambiguity_evidence,
        )

    def materialize_global_tracks(self) -> FusionTrackSnapshot:
        """Build one explicit full snapshot after one or more state-only scans.

        This method does not update, replay, or reassociate observations. It
        only copies the current state, covariance, lifecycle classification,
        lineage, health, latency, and publication metadata into detached track
        objects. Its operation counts enter cumulative fusion diagnostics
        without creating a synthetic observation batch.
        """

        if self._batch_context is not None:
            raise RuntimeError(
                "global tracks cannot be materialized inside an active fusion batch"
            )
        context = _BatchProcessingContext()
        self._batch_context = context
        try:
            tracks = tuple(self.global_tracks())
        finally:
            self._batch_context = None
            self._accumulate_materialization_performance(context)
        return FusionTrackSnapshot(
            tracks=tracks,
            published_at=float(self.current_time),
            global_track_materialization_count=(
                context.global_track_materialization_count
            ),
            sensor_health_snapshot_build_count=(
                context.sensor_health_snapshot_build_count
            ),
        )

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
            state = self._predict_to(
                EKFState(track.state, track.covariance, track.timestamp),
                timestamp,
            )
            out = track.copy()
            out.state = state.state
            reasons = []
            if float(timestamp) - previous_timestamp > self.long_extrapolation_s:
                reasons.append("long_extrapolation")
            operation_counts: Counter[str] = Counter()
            out.covariance, applied = self._limit_state_covariance(
                state.covariance,
                reasons,
                operation_counts=operation_counts,
            )
            out.timestamp = state.timestamp
            self._update_metadata_covariance_reasons(out.metadata, applied)
            _update_metadata_covariance_operation_counts(
                out.metadata,
                operation_counts,
            )
            return out

        record = self.tracks[str(track)]
        previous_timestamp = float(record.current_state.timestamp)
        record.current_state = self._predict_to(
            record.current_state,
            timestamp,
        )
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
            record.current_state = self._predict_to(
                record.current_state,
                current_time,
            )
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
            record.current_state = self._predict_to(
                record.current_state,
                current_time,
            )
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
                record.current_state = self._predict_to(
                    record.current_state,
                    current_time,
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
        record.replay_checkpoints_complete = self.incremental_replay_cache
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
        record.replay_checkpoints_complete = self.incremental_replay_cache

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
        self._publication_materialization_operations[
            "global_tracks_call_count"
        ] += 1
        publication_context = (
            self._track_publication_context()
            if self.shared_publication_audit_snapshot
            else None
        )
        return [
            self._to_global_track(record, publication_context)
            for record in self.tracks.values()
        ]

    def publication_materialization_diagnostics(self) -> dict[str, Any]:
        """Return implementation identity and materialization operation counts."""

        implementation_id = (
            PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID
            if self.immutable_shared_publication_metadata
            else PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION_ID
        )
        return {
            "implementation_id": implementation_id,
            "publication_audit_contract_version": (
                PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
                if self.immutable_shared_publication_metadata
                else None
            ),
            "immutable_shared_publication_metadata": bool(
                self.immutable_shared_publication_metadata
            ),
            "operation_counts": dict(
                sorted(self._publication_materialization_operations.items())
            ),
        }

    def fusion_performance_diagnostics(self) -> FusionPerformanceDiagnostics:
        """Return fixed-size cumulative counters for episode-level profiling."""

        totals = self._performance_totals
        return FusionPerformanceDiagnostics(
            batch_count=int(totals["batch_count"]),
            scan_batch_count=int(totals["scan_batch_count"]),
            observation_count=int(totals["observation_count"]),
            history_replay_count=int(totals["history_replay_count"]),
            origin_replay_count=int(totals["origin_replay_count"]),
            finalization_replay_count=int(totals["finalization_replay_count"]),
            replay_filter_update_count=int(totals["replay_filter_update_count"]),
            replay_checkpoint_reuse_count=int(
                totals["replay_checkpoint_reuse_count"]
            ),
            checkpoint_state_query_count=int(totals["checkpoint_state_query_count"]),
            fixed_lag_rebase_count=int(totals["fixed_lag_rebase_count"]),
            fixed_lag_checkpoint_suffix_reuse_count=int(
                totals["fixed_lag_checkpoint_suffix_reuse_count"]
            ),
            replay_checkpoint_prefix_fast_path_count=int(
                totals["replay_checkpoint_prefix_fast_path_count"]
            ),
            cached_consistency_refresh_count=int(
                totals["cached_consistency_refresh_count"]
            ),
            global_track_materialization_count=int(
                totals["global_track_materialization_count"]
            ),
            sensor_health_snapshot_build_count=int(
                totals["sensor_health_snapshot_build_count"]
            ),
            association_candidate_pair_count=int(
                totals["association_candidate_pair_count"]
            ),
            association_innovation_solve_count=int(
                totals["association_innovation_solve_count"]
            ),
            current_track_count=len(self.tracks),
            current_time=float(self.current_time),
        )

    def _accumulate_batch_performance(
        self,
        context: _BatchProcessingContext,
        *,
        observation_count: int,
        scan_batch: bool,
    ) -> None:
        totals = self._performance_totals
        totals["batch_count"] += 1
        totals["scan_batch_count"] += int(scan_batch)
        totals["observation_count"] += int(observation_count)
        for name in (
            "history_replay_count",
            "origin_replay_count",
            "finalization_replay_count",
            "replay_filter_update_count",
            "replay_checkpoint_reuse_count",
            "checkpoint_state_query_count",
            "fixed_lag_rebase_count",
            "fixed_lag_checkpoint_suffix_reuse_count",
            "replay_checkpoint_prefix_fast_path_count",
            "cached_consistency_refresh_count",
            "global_track_materialization_count",
            "sensor_health_snapshot_build_count",
            "association_candidate_pair_count",
            "association_innovation_solve_count",
        ):
            totals[name] += int(getattr(context, name))

    def _accumulate_materialization_performance(
        self,
        context: _BatchProcessingContext,
    ) -> None:
        totals = self._performance_totals
        totals["global_track_materialization_count"] += int(
            context.global_track_materialization_count
        )
        totals["sensor_health_snapshot_build_count"] += int(
            context.sensor_health_snapshot_build_count
        )

    def _track_publication_context(self) -> _TrackPublicationContext:
        context = self._batch_context
        if context is not None:
            context.sensor_health_snapshot_build_count += 1
        self._publication_materialization_operations[
            "shared_publication_context_build_count"
        ] += 1
        association_audit = self.association_audit_summary()
        latency_audit = self.latency_audit_summary().to_dict()
        sensor_health = {
            summary.sensor_id: summary.to_dict()
            for summary in self.sensor_health_summaries()
        }
        if self.immutable_shared_publication_metadata:
            freeze_counts: Counter[str] = Counter()
            association_audit = freeze_publication_audit_tree(
                association_audit,
                freeze_counts,
            )
            latency_audit = freeze_publication_audit_tree(
                latency_audit,
                freeze_counts,
            )
            sensor_health = freeze_publication_audit_tree(
                sensor_health,
                freeze_counts,
            )
            if not all(
                type(value) is ImmutablePublicationAuditMap
                for value in (
                    association_audit,
                    latency_audit,
                    sensor_health,
                )
            ):
                raise RuntimeError(
                    "publication audit freeze returned a non-v2 contract root"
                )
            self._publication_materialization_operations.update(freeze_counts)
        return _TrackPublicationContext(
            association_audit=association_audit,
            latency_audit=latency_audit,
            sensor_health=sensor_health,
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

        if self.radar_assignment_ambiguity_governance_v2:
            ambiguity_policy_version = (
                RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
            )
            selected_ambiguity_policy_version: str | None = (
                RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
            )
            ambiguity_governance_status = (
                RADAR_ASSIGNMENT_AMBIGUITY_V2_GOVERNANCE_STATUS
            )
        else:
            ambiguity_policy_version = RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION
            selected_ambiguity_policy_version = (
                RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION
                if self.radar_assignment_ambiguity_governance
                else None
            )
            ambiguity_governance_status = (
                "experimental_enabled"
                if self.radar_assignment_ambiguity_governance
                else "disabled"
            )
        return {
            "schema_version": "d1.association_audit.v1",
            "observer_scan_suppression_count": self.observer_scan_suppression_count,
            "radar_reacquisition_count": self.radar_reacquisition_count,
            "ambiguous_radar_birth_suppression_count": (
                self.ambiguous_radar_birth_suppression_count
            ),
            "radar_assignment_ambiguity_scan_count": (
                self.radar_assignment_ambiguity_scan_count
            ),
            "radar_assignment_ambiguity_observation_suppression_count": (
                self.radar_assignment_ambiguity_observation_suppression_count
            ),
            "radar_assignment_ambiguity_track_coast_count": (
                self.radar_assignment_ambiguity_track_coast_count
            ),
            "max_radar_assignment_ambiguity_component_size": (
                self.max_radar_assignment_ambiguity_component_size
            ),
            "radar_assignment_ambiguity_governance_enabled": (
                self.radar_assignment_ambiguity_governance
                or self.radar_assignment_ambiguity_governance_v2
            ),
            "radar_assignment_ambiguity_policy_version": (
                ambiguity_policy_version
            ),
            "radar_assignment_ambiguity_selected_policy_version": (
                selected_ambiguity_policy_version
            ),
            "radar_assignment_ambiguity_candidate_policy_versions": (
                RADAR_ASSIGNMENT_AMBIGUITY_CANDIDATE_POLICY_VERSIONS
            ),
            "radar_assignment_ambiguity_governance_status": (
                ambiguity_governance_status
            ),
            "latest_radar_assignment_ambiguity_track_ids": (
                self._latest_radar_assignment_ambiguity_track_ids
            ),
            "radar_assignment_ambiguity_hold_evidence_enabled": (
                self.radar_assignment_ambiguity_hold_evidence
            ),
            "opaque_source_key_publication_requested": (
                self.publish_opaque_source_key
            ),
            "opaque_source_key_publication_enabled": (
                self.opaque_source_key_publication_enabled
            ),
            "opaque_source_key_publication_mode": (
                "structural_ambiguity_hold"
                if self.radar_assignment_ambiguity_hold_evidence
                else (
                    "source_only"
                    if self.publish_opaque_source_key
                    else "disabled"
                )
            ),
            "opaque_source_key_publisher_node_id": (
                self.publisher_node_id
                if self.opaque_source_key_publication_enabled
                else None
            ),
            "opaque_source_key_publisher_epoch": (
                self.publisher_epoch
                if self.opaque_source_key_publication_enabled
                else None
            ),
            "structural_ambiguity_evidence_policy_version": (
                STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION
            ),
            "structural_ambiguity_evidence_status": (
                RADAR_ASSIGNMENT_AMBIGUITY_HOLD_EVIDENCE_STATUS
                if self.radar_assignment_ambiguity_hold_evidence
                else "disabled"
            ),
            "structural_ambiguity_evidence_component_count": (
                self.structural_ambiguity_evidence_component_count
            ),
            "structural_ambiguity_evidence_observation_count": (
                self.structural_ambiguity_evidence_observation_count
            ),
            "structural_ambiguity_evidence_member_count": (
                self.structural_ambiguity_evidence_member_count
            ),
            "structural_ambiguity_deferred_birth_count": (
                self.structural_ambiguity_deferred_birth_count
            ),
            "structural_ambiguity_prediction_only_member_count": (
                self.structural_ambiguity_prediction_only_member_count
            ),
            "latest_structural_ambiguity_component_ids": (
                self._latest_structural_ambiguity_component_ids
            ),
            "structural_ambiguity_publisher_node_id": (
                self.publisher_node_id
                if self.radar_assignment_ambiguity_hold_evidence
                else None
            ),
            "structural_ambiguity_publisher_epoch": (
                self.publisher_epoch
                if self.radar_assignment_ambiguity_hold_evidence
                else None
            ),
            **(
                {
                    "neutral_centroid_correction_requested": True,
                    "neutral_centroid_correction_enabled": True,
                    "neutral_centroid_correction_status": (
                        RADAR_ASSIGNMENT_AMBIGUITY_NEUTRAL_CENTROID_STATUS
                    ),
                    "neutral_centroid_publication_state_semantics": (
                        "exact_replay_frame_replacement_v1"
                    ),
                    "neutral_centroid_generation_registry_policy": (
                        "per_component_fixed_lag_watermark_hard_capacity_v1"
                    ),
                    "neutral_centroid_max_component_size": (
                        self.neutral_centroid_max_component_size
                    ),
                    "neutral_centroid_gain": float(
                        self.neutral_centroid_gain
                    ),
                    "neutral_centroid_max_translation_m": float(
                        self.neutral_centroid_max_translation_m
                    ),
                    "neutral_centroid_gate_chi2": float(
                        self.neutral_centroid_gate_chi2
                    ),
                    "neutral_centroid_shape_gate_m2": float(
                        self.neutral_centroid_shape_gate_m2
                    ),
                    "neutral_centroid_shape_inflation_scale": float(
                        self.neutral_centroid_shape_inflation_scale
                    ),
                    "neutral_centroid_min_position_variance_m2": float(
                        self.neutral_centroid_min_position_variance_m2
                    ),
                    "neutral_centroid_generation_registry_max_entries": (
                        self.neutral_centroid_generation_registry_max_entries
                    ),
                    "neutral_centroid_generation_registry_current_entry_count": (
                        len(self._neutral_centroid_generation_registry)
                    ),
                    "neutral_centroid_generation_registry_peak_entry_count": (
                        self.neutral_centroid_generation_registry_peak_entry_count
                    ),
                    "neutral_centroid_generation_registry_eviction_count": (
                        self.neutral_centroid_generation_registry_eviction_count
                    ),
                    "neutral_centroid_generation_registry_capacity_rejection_count": (
                        self.neutral_centroid_generation_registry_capacity_rejection_count
                    ),
                    "neutral_centroid_candidate_component_count": (
                        self.neutral_centroid_candidate_component_count
                    ),
                    "neutral_centroid_applied_component_count": (
                        self.neutral_centroid_applied_component_count
                    ),
                    "neutral_centroid_applied_member_count": (
                        self.neutral_centroid_applied_member_count
                    ),
                    "neutral_centroid_rejected_component_count": (
                        self.neutral_centroid_rejected_component_count
                    ),
                    "neutral_centroid_duplicate_generation_rejection_count": (
                        self.neutral_centroid_duplicate_generation_rejection_count
                    ),
                    "neutral_centroid_regressed_generation_rejection_count": (
                        self.neutral_centroid_regressed_generation_rejection_count
                    ),
                    "neutral_centroid_linear_input_operation_count": (
                        self.neutral_centroid_linear_input_operation_count
                    ),
                    "max_neutral_centroid_component_size": (
                        self.max_neutral_centroid_component_size
                    ),
                    "max_neutral_centroid_nis": float(
                        self.max_neutral_centroid_nis
                    ),
                    "max_neutral_centroid_shape_mismatch_m2": float(
                        self.max_neutral_centroid_shape_mismatch_m2
                    ),
                    "max_neutral_centroid_translation_m": float(
                        self.max_neutral_centroid_translation_m
                    ),
                    "neutral_centroid_rejection_reasons": dict(
                        sorted(
                            self._neutral_centroid_rejection_reasons.items()
                        )
                    ),
                    "latest_neutral_centroid_rejection_reason": (
                        self._latest_neutral_centroid_rejection_reason
                    ),
                    "latest_neutral_centroid_applied_evidence_id": (
                        self._latest_neutral_centroid_applied_evidence_id
                    ),
                    "neutral_centroid_cross_covariance_available": False,
                }
                if self.radar_assignment_ambiguity_neutral_centroid_correction
                else {}
            ),
            "non_range_state_correction_rejection_count": (
                self.non_range_state_correction_rejection_count
            ),
            "pre_checkpoint_oosm_replay_count": self.pre_checkpoint_oosm_replay_count,
            "max_non_range_position_correction_score": float(
                self.max_non_range_position_correction_score
            ),
            "eo_projection_gate_pass_count": self.eo_projection_gate_pass_count,
            "eo_projection_gate_rejection_count": (
                self.eo_projection_gate_rejection_count
            ),
            "eo_projection_unavailable_count": self.eo_projection_unavailable_count,
            "eo_one_to_one_unassigned_count": self.eo_one_to_one_unassigned_count,
            "max_eo_projection_gate_pass_nis": float(
                self.max_eo_projection_gate_pass_nis
            ),
            "latest_eo_projection_rejection_reason": (
                self._latest_eo_projection_rejection_reason
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
        current = self._predict_to(initial, current_time)
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
            replay_checkpoints_complete=self.incremental_replay_cache,
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
                record.current_state = self._predict_to(
                    record.current_state,
                    timestamp,
                )
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
    ) -> _ScanAssociationResult:
        if not observations or not pre_scan_track_ids:
            return _ScanAssociationResult(assignments={})

        track_items = sorted(
            (
                (track_id, self.tracks[track_id])
                for track_id in pre_scan_track_ids
                if not self._record_has_observer_scan(
                    self.tracks[track_id],
                    observations[0],
                )
            ),
            key=lambda item: item[0],
        )
        if not track_items:
            return _ScanAssociationResult(assignments={})

        context = self._batch_context
        if context is not None:
            context.association_candidate_pair_count += (
                len(track_items) * len(observations)
            )

        if all(observation.modality == "radar" for observation in observations):
            cost_matrix = self._radar_scan_cost_matrix(
                track_items,
                observations,
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
            self._record_eo_projection_scan_diagnostics(
                observations,
                cost_matrix,
                {},
            )
            return _ScanAssociationResult(assignments={})
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
        radar_ambiguities: dict[int, _RadarAssignmentAmbiguity] = {}
        if (
            (
                self.radar_assignment_ambiguity_governance
                or self.radar_assignment_ambiguity_governance_v2
                or self.radar_assignment_ambiguity_hold_evidence
            )
            and all(observation.modality == "radar" for observation in observations)
        ):
            if (
                self.radar_assignment_ambiguity_governance_v2
                or self.radar_assignment_ambiguity_hold_evidence
            ):
                row_by_track_id = {
                    track_id: row
                    for row, (track_id, _) in enumerate(track_items)
                }
                if self.radar_assignment_ambiguity_hold_evidence:
                    structural_observation_keys = (
                        self._structural_ambiguity_observation_keys(observations)
                    )
                    canonical_columns = tuple(
                        sorted(
                            range(len(observations)),
                            key=structural_observation_keys.__getitem__,
                        )
                    )
                    canonical_valid = valid[:, canonical_columns]
                    canonical_cost = cost_matrix[:, canonical_columns]
                    canonical_matching = _maximum_cardinality_assignment(
                        canonical_valid,
                        {},
                        canonical_cost,
                    )
                    maximum_row_to_column = {
                        row: canonical_columns[column]
                        for row, column in canonical_matching.items()
                    }
                else:
                    preferred_row_to_column = {
                        row_by_track_id[track_id]: observation_index
                        for observation_index, track_id in assignments.items()
                    }
                    maximum_row_to_column = _maximum_cardinality_assignment(
                        valid,
                        preferred_row_to_column,
                        cost_matrix,
                    )
                assignments = {
                    column: track_items[row][0]
                    for row, column in maximum_row_to_column.items()
                }
                radar_ambiguities = self._radar_assignment_ambiguities_v2(
                    track_items,
                    valid,
                    maximum_row_to_column,
                    cost_matrix,
                )
            else:
                radar_ambiguities = self._radar_assignment_ambiguities(
                    track_items,
                    valid,
                    assignments,
                )
            for observation_index in radar_ambiguities:
                assignments.pop(observation_index, None)
        self._record_eo_projection_scan_diagnostics(
            observations,
            cost_matrix,
            assignments,
        )
        return _ScanAssociationResult(
            assignments=assignments,
            radar_ambiguities=radar_ambiguities,
        )

    def _radar_assignment_ambiguities(
        self,
        track_items: list[tuple[str, TrackRecord]],
        valid: np.ndarray,
        assignments: dict[int, str],
    ) -> dict[int, _RadarAssignmentAmbiguity]:
        """Find assigned radar observations that belong to alternating cycles.

        The gate-valid bipartite graph can admit another same-cardinality
        matching even when Hungarian ranks one matching first. Each directed
        cycle below is exactly such an identity permutation. The observation
        is therefore withheld instead of turning a likelihood ranking into a
        deterministic identity claim.
        """

        row_by_track_id = {
            track_id: row
            for row, (track_id, _) in enumerate(track_items)
        }
        column_by_row = {
            row_by_track_id[track_id]: observation_index
            for observation_index, track_id in assignments.items()
        }
        adjacency: dict[int, tuple[int, ...]] = {}
        assigned_rows = tuple(sorted(column_by_row))
        for row in assigned_rows:
            alternatives = tuple(
                other_row
                for other_row in assigned_rows
                if other_row != row
                and bool(valid[row, column_by_row[other_row]])
            )
            adjacency[row] = alternatives

        ambiguities: dict[int, _RadarAssignmentAmbiguity] = {}
        for component in _strongly_connected_assignment_components(adjacency):
            if len(component) < 2:
                continue
            track_ids = tuple(sorted(track_items[row][0] for row in component))
            ambiguity = _RadarAssignmentAmbiguity(
                track_ids=track_ids,
                component_size=len(component),
            )
            for row in component:
                ambiguities[column_by_row[row]] = ambiguity
        return ambiguities

    def _radar_assignment_ambiguities_v2(
        self,
        track_items: list[tuple[str, TrackRecord]],
        valid: np.ndarray,
        row_to_column: dict[int, int],
        cost_matrix: np.ndarray,
    ) -> dict[int, _RadarAssignmentAmbiguity]:
        """Find complete maximum-matching uncertainty components.

        Matched edges are directed observation-to-track and unmatched allowed
        edges track-to-observation. An unmatched edge can occur in another
        maximum matching when it is on a directed alternating cycle, is
        reachable from a free track row, or can reach a free observation
        column. Connected components of those allowed edges are suppressed as
        a unit so an unmatched observation cannot bypass update suppression by
        creating a new track.
        """

        valid = np.asarray(valid, dtype=bool)
        row_count, column_count = valid.shape
        column_offset = row_count
        node_count = row_count + column_count
        column_to_row = {
            column: row
            for row, column in row_to_column.items()
        }

        directed_lists: dict[int, list[int]] = {
            node: [] for node in range(node_count)
        }
        reverse_lists: dict[int, list[int]] = {
            node: [] for node in range(node_count)
        }
        for row, column in zip(*np.nonzero(valid)):
            row = int(row)
            column = int(column)
            column_node = column_offset + column
            if row_to_column.get(row) == column:
                source, target = column_node, row
            else:
                source, target = row, column_node
            directed_lists[source].append(target)
            reverse_lists[target].append(source)

        directed = {
            node: tuple(sorted(neighbors))
            for node, neighbors in directed_lists.items()
        }
        reverse = {
            node: tuple(sorted(neighbors))
            for node, neighbors in reverse_lists.items()
        }
        components = _strongly_connected_assignment_components(directed)
        component_by_node = {
            node: component_index
            for component_index, component in enumerate(components)
            for node in component
        }

        free_rows = (
            row for row in range(row_count) if row not in row_to_column
        )
        free_columns = (
            column_offset + column
            for column in range(column_count)
            if column not in column_to_row
        )
        reachable_from_free_rows = _reachable_assignment_vertices(
            directed,
            free_rows,
        )
        can_reach_free_columns = _reachable_assignment_vertices(
            reverse,
            free_columns,
        )

        undirected_lists: dict[int, set[int]] = {
            node: set() for node in range(node_count)
        }
        alternative_kinds: dict[tuple[int, int], tuple[str, ...]] = {}
        for row, column in zip(*np.nonzero(valid)):
            row = int(row)
            column = int(column)
            column_node = column_offset + column
            kinds: list[str] = []
            matched = row_to_column.get(row) == column
            if not matched:
                if component_by_node[row] == component_by_node[column_node]:
                    kinds.append("alternating_cycle")
                if row in reachable_from_free_rows:
                    kinds.append("free_row_alternating_path")
                if column_node in can_reach_free_columns:
                    kinds.append("free_column_alternating_path")
                if not kinds:
                    continue
                alternative_kinds[(row, column)] = tuple(kinds)
            undirected_lists[row].add(column_node)
            undirected_lists[column_node].add(row)

        ambiguities: dict[int, _RadarAssignmentAmbiguity] = {}
        visited: set[int] = set()
        for start in range(node_count):
            if start in visited or not undirected_lists[start]:
                continue
            pending = [start]
            component_nodes: set[int] = set()
            while pending:
                node = pending.pop()
                if node in component_nodes:
                    continue
                component_nodes.add(node)
                pending.extend(
                    sorted(undirected_lists[node] - component_nodes, reverse=True)
                )
            visited.update(component_nodes)

            rows = tuple(
                sorted(node for node in component_nodes if node < column_offset)
            )
            columns = tuple(
                sorted(
                    node - column_offset
                    for node in component_nodes
                    if node >= column_offset
                )
            )
            kinds = tuple(
                sorted(
                    {
                        kind
                        for (row, column), edge_kinds in alternative_kinds.items()
                        if row in component_nodes
                        and column_offset + column in component_nodes
                        for kind in edge_kinds
                    }
                )
            )
            if not kinds:
                continue
            track_ids = tuple(sorted(track_items[row][0] for row in rows))
            candidate_edges = tuple(
                sorted(
                    (
                        _RadarAmbiguityCandidateEdge(
                            track_id=track_items[row][0],
                            observation_index=column,
                            nis=float(cost_matrix[row, column]),
                            edge_roles=tuple(
                                sorted(
                                    {
                                        "maximum_matching_allowed",
                                        *(
                                            ("matched_reference",)
                                            if row_to_column.get(row) == column
                                            else alternative_kinds[(row, column)]
                                        ),
                                    }
                                )
                            ),
                        )
                        for row in rows
                        for column in columns
                        if bool(valid[row, column])
                        and (
                            row_to_column.get(row) == column
                            or (row, column) in alternative_kinds
                        )
                    ),
                    key=lambda item: (
                        item.track_id,
                        item.observation_index,
                        item.edge_roles,
                    ),
                )
            )
            matching_cardinality = sum(
                1
                for row in rows
                if row_to_column.get(row) in set(columns)
            )
            ambiguity = _RadarAssignmentAmbiguity(
                track_ids=track_ids,
                component_size=len(track_ids),
                observation_indices=columns,
                observation_count=len(columns),
                candidate_edges=candidate_edges,
                deferred_birth_observation_indices=tuple(
                    column for column in columns if column not in column_to_row
                ),
                free_row_count=len(rows) - matching_cardinality,
                free_column_count=len(columns) - matching_cardinality,
                maximum_matching_cardinality=matching_cardinality,
                component_kinds=kinds,
                reason="maximum_matching_allowed_edge_component",
                policy_version=(
                    STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION
                    if self.radar_assignment_ambiguity_hold_evidence
                    else RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
                ),
            )
            for column in columns:
                ambiguities[column] = ambiguity
        return ambiguities

    def _build_structural_ambiguity_evidence(
        self,
        observations: list[SensorObservation],
        result: _ScanAssociationResult,
        *,
        published_at: float,
    ) -> tuple[StructuralAmbiguityEvidence, ...]:
        """Build complete component sidecars without assigning observation identity."""

        if not result.radar_ambiguities:
            return ()
        if not observations:
            raise ValueError(
                "structural ambiguity evidence requires the source scan observations"
            )

        unique_components = {
            (
                ambiguity.track_ids,
                ambiguity.observation_indices,
                ambiguity.policy_version,
            ): ambiguity
            for ambiguity in result.radar_ambiguities.values()
        }
        all_observation_keys = self._structural_ambiguity_observation_keys(
            observations
        )
        observation_keys = {
            index: all_observation_keys[index]
            for ambiguity in unique_components.values()
            for index in ambiguity.observation_indices
        }
        track_tokens = {
            track_id: structural_ambiguity_member_track_token(
                self.publisher_node_id,
                self.publisher_epoch,
                track_id,
            )
            for ambiguity in unique_components.values()
            for track_id in ambiguity.track_ids
        }
        ordered_components = sorted(
            unique_components.values(),
            key=lambda item: (
                tuple(track_tokens[track_id] for track_id in item.track_ids),
                tuple(observation_keys[index] for index in item.observation_indices),
                item.component_kinds,
            ),
        )
        measurement_timestamp = float(observations[0].measurement_timestamp)
        arrival_timestamp = float(observations[0].arrival_timestamp)
        scan_id = _opaque_structural_digest(
            "d1-scan-sha256:",
            self._observer_scan_key(observations[0]),
        )

        evidence_items: list[StructuralAmbiguityEvidence] = []
        for ambiguity in ordered_components:
            members = tuple(
                sorted(
                    (
                        StructuralAmbiguityMemberState(
                            opaque_member_track_token=track_tokens[track_id],
                            source_key=structural_ambiguity_source_key(
                                self.publisher_node_id,
                                self.publisher_epoch,
                                track_tokens[track_id],
                            ),
                            state=state.state,
                            covariance=state.covariance,
                        )
                        for track_id in ambiguity.track_ids
                        for state in (
                            self._state_at(
                                self.tracks[track_id],
                                measurement_timestamp,
                            ),
                        )
                    ),
                    key=lambda item: item.opaque_member_track_token,
                )
            )
            component_observations = tuple(
                sorted(
                    (
                        StructuralAmbiguityObservationEvidence(
                            observation_evidence_key=observation_keys[index],
                            position_ned=state[:3],
                            covariance_ned=covariance[:3, :3],
                            radial_velocity_observed=bool(
                                observations[index].metadata.get(
                                    "radial_velocity_observed",
                                    observations[index].measurement.size >= 4,
                                )
                                and observations[index].measurement.size >= 4
                            ),
                            birth_deferred=(
                                index
                                in ambiguity.deferred_birth_observation_indices
                            ),
                            velocity_evidence_used=False,
                        )
                        for index in ambiguity.observation_indices
                        for state, covariance in (
                            radar_state_from_observation(
                                observations[index],
                                self.radar_covariance_config,
                            ),
                        )
                    ),
                    key=lambda item: item.observation_evidence_key,
                )
            )
            candidate_edges = tuple(
                sorted(
                    (
                        StructuralAmbiguityCandidateEdge(
                            opaque_member_track_token=track_tokens[edge.track_id],
                            observation_evidence_key=observation_keys[
                                edge.observation_index
                            ],
                            nis=edge.nis,
                            gate_threshold=float(self.association_gate),
                            edge_roles=edge.edge_roles,
                        )
                        for edge in ambiguity.candidate_edges
                    ),
                    key=lambda item: (
                        item.opaque_member_track_token,
                        item.observation_evidence_key,
                        item.edge_roles,
                    ),
                )
            )
            component_id = _opaque_structural_digest(
                "d1-component-sha256:",
                (
                    self.publisher_node_id,
                    self.publisher_epoch,
                    observations[0].sensor_id,
                    tuple(item.source_key for item in members),
                ),
            )
            self._structural_ambiguity_component_generations[component_id] += 1
            generation = int(
                self._structural_ambiguity_component_generations[component_id]
            )
            evidence_id = _opaque_structural_digest(
                "d1-evidence-sha256:",
                (
                    component_id,
                    generation,
                    measurement_timestamp,
                    arrival_timestamp,
                    float(published_at),
                    scan_id,
                    tuple(
                        (
                            item.opaque_member_track_token,
                            item.observation_evidence_key,
                            item.nis,
                            item.gate_threshold,
                            item.edge_roles,
                        )
                        for item in candidate_edges
                    ),
                ),
            )
            evidence_items.append(
                StructuralAmbiguityEvidence(
                    evidence_id=evidence_id,
                    component_id=component_id,
                    component_generation=generation,
                    publisher_node_id=self.publisher_node_id,
                    publisher_epoch=self.publisher_epoch,
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    state_valid_timestamp=measurement_timestamp,
                    published_at=float(published_at),
                    sensor_id=observations[0].sensor_id,
                    scan_id=scan_id,
                    member_states=members,
                    observations=component_observations,
                    candidate_edges=candidate_edges,
                    component_kinds=ambiguity.component_kinds,
                    member_count=len(members),
                    observation_count=len(component_observations),
                    candidate_edge_count=len(candidate_edges),
                    free_row_count=ambiguity.free_row_count,
                    free_column_count=ambiguity.free_column_count,
                    maximum_matching_cardinality=(
                        ambiguity.maximum_matching_cardinality
                    ),
                    policy_version=STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION,
                )
            )
        return tuple(evidence_items)

    def _apply_structural_ambiguity_neutral_centroid_corrections(
        self,
        observations: list[SensorObservation],
        result: _ScanAssociationResult,
        evidence: tuple[StructuralAmbiguityEvidence, ...],
        *,
        scan_has_oosm: bool,
        scan_has_stale_observation: bool,
    ) -> None:
        """Apply an identity-neutral translation to eligible hold components.

        The identity sidecar remains prediction-only. This local state
        correction never chooses an observation-to-member edge and therefore
        never changes hit, lineage, source-support, or identity freshness.
        """

        if not evidence or not result.radar_ambiguities:
            return

        evidence_by_member_tokens = {
            tuple(
                sorted(
                    member.opaque_member_track_token
                    for member in item.member_states
                )
            ): item
            for item in evidence
        }
        unique_components = {
            (
                ambiguity.track_ids,
                ambiguity.observation_indices,
                ambiguity.policy_version,
            ): ambiguity
            for ambiguity in result.radar_ambiguities.values()
        }
        ordered_components = sorted(
            unique_components.values(),
            key=lambda item: (
                item.track_ids,
                item.observation_indices,
                item.component_kinds,
            ),
        )

        for ambiguity in ordered_components:
            self.neutral_centroid_candidate_component_count += 1
            self.max_neutral_centroid_component_size = max(
                self.max_neutral_centroid_component_size,
                int(
                    max(
                        len(ambiguity.track_ids),
                        len(ambiguity.observation_indices),
                    )
                ),
            )
            member_tokens = tuple(
                sorted(
                    structural_ambiguity_member_track_token(
                        self.publisher_node_id,
                        self.publisher_epoch,
                        track_id,
                    )
                    for track_id in ambiguity.track_ids
                )
            )
            component_evidence = evidence_by_member_tokens.get(member_tokens)
            if component_evidence is None:
                self._reject_neutral_centroid_component(
                    "evidence_member_contract_mismatch"
                )
                continue
            generation_rejection = (
                self._admit_neutral_centroid_evidence_generation(
                    component_evidence
                )
            )
            if generation_rejection is not None:
                if (
                    generation_rejection
                    == "generation_registry_capacity_reached"
                ):
                    publication_bases, _ = (
                        self._neutral_centroid_publication_base_states(
                            ambiguity.track_ids
                        )
                    )
                    if publication_bases is not None:
                        self._replace_neutral_centroid_publication_states(
                            publication_bases
                        )
                self._reject_neutral_centroid_component(
                    generation_rejection
                )
                continue

            publication_bases, base_rejection = (
                self._neutral_centroid_publication_base_states(
                    ambiguity.track_ids
                )
            )
            if publication_bases is None:
                self._reject_neutral_centroid_component(
                    base_rejection or "publication_base_replay_failed"
                )
                continue

            correction, rejection_reason = (
                self._build_neutral_centroid_correction(
                    observations,
                    ambiguity,
                    component_evidence,
                    publication_base_states=publication_bases,
                    scan_has_oosm=scan_has_oosm,
                    scan_has_stale_observation=(
                        scan_has_stale_observation
                    ),
                )
            )
            if correction is None:
                self._replace_neutral_centroid_publication_states(
                    publication_bases
                )
                self._reject_neutral_centroid_component(
                    rejection_reason or "candidate_validation_failed"
                )
                continue

            for track_id in correction.track_ids:
                record = self.tracks[track_id]
                publication_base = publication_bases[track_id]
                state = publication_base.state.copy()
                covariance = publication_base.covariance.copy()
                state[:3] += correction.translation_ned
                covariance[:3, :3] += (
                    correction.position_covariance_inflation
                )
                covariance = 0.5 * (covariance + covariance.T)
                record.current_state = EKFState(
                    state,
                    covariance,
                    publication_base.timestamp,
                )
                record.current_state_covariance_limited = True

            self._mark_neutral_centroid_generation_applied(
                component_evidence
            )
            self.neutral_centroid_applied_component_count += 1
            self.neutral_centroid_applied_member_count += len(
                correction.track_ids
            )
            self.neutral_centroid_linear_input_operation_count += (
                correction.linear_input_operation_count
            )
            self.max_neutral_centroid_nis = max(
                self.max_neutral_centroid_nis,
                correction.centroid_nis,
            )
            self.max_neutral_centroid_shape_mismatch_m2 = max(
                self.max_neutral_centroid_shape_mismatch_m2,
                correction.shape_mismatch_m2,
            )
            self.max_neutral_centroid_translation_m = max(
                self.max_neutral_centroid_translation_m,
                float(np.linalg.norm(correction.translation_ned)),
            )
            self._latest_neutral_centroid_applied_evidence_id = (
                component_evidence.evidence_id
            )

    def _admit_neutral_centroid_evidence_generation(
        self,
        evidence: StructuralAmbiguityEvidence,
    ) -> str | None:
        """Admit one strictly newer generation into the bounded registry."""

        self._prune_neutral_centroid_generation_registry()
        generation = int(evidence.component_generation)
        if generation < 1:
            return "invalid_evidence_generation"
        if (
            self.buffer_horizon > 0.0
            and float(evidence.measurement_timestamp)
            < self.current_time - self.buffer_horizon - 1.0e-9
        ):
            return "evidence_outside_fixed_lag"

        component_id = str(evidence.component_id)
        watermark = self._neutral_centroid_generation_registry.get(
            component_id
        )
        if watermark is not None:
            if generation == watermark.max_seen_generation:
                self.neutral_centroid_duplicate_generation_rejection_count += 1
                return "duplicate_evidence_generation"
            if generation < watermark.max_seen_generation:
                self.neutral_centroid_regressed_generation_rejection_count += 1
                return "regressed_evidence_generation"
            self._neutral_centroid_generation_registry[component_id] = replace(
                watermark,
                max_seen_generation=generation,
                last_measurement_timestamp=max(
                    watermark.last_measurement_timestamp,
                    float(evidence.measurement_timestamp),
                ),
            )
            return None

        if (
            len(self._neutral_centroid_generation_registry)
            >= self.neutral_centroid_generation_registry_max_entries
        ):
            self.neutral_centroid_generation_registry_capacity_rejection_count += 1
            return "generation_registry_capacity_reached"
        self._neutral_centroid_generation_registry[component_id] = (
            _NeutralCentroidGenerationWatermark(
                max_seen_generation=generation,
                max_applied_generation=0,
                last_measurement_timestamp=float(
                    evidence.measurement_timestamp
                ),
            )
        )
        self.neutral_centroid_generation_registry_peak_entry_count = max(
            self.neutral_centroid_generation_registry_peak_entry_count,
            len(self._neutral_centroid_generation_registry),
        )
        return None

    def _prune_neutral_centroid_generation_registry(self) -> None:
        """Evict only entries whose evidence is outside the fixed-lag window."""

        if self.buffer_horizon <= 0.0:
            return
        cutoff = self.current_time - self.buffer_horizon
        expired = tuple(
            component_id
            for component_id, watermark in (
                self._neutral_centroid_generation_registry.items()
            )
            if watermark.last_measurement_timestamp < cutoff - 1.0e-9
        )
        for component_id in expired:
            del self._neutral_centroid_generation_registry[component_id]
        self.neutral_centroid_generation_registry_eviction_count += len(
            expired
        )

    def _mark_neutral_centroid_generation_applied(
        self,
        evidence: StructuralAmbiguityEvidence,
    ) -> None:
        component_id = str(evidence.component_id)
        generation = int(evidence.component_generation)
        watermark = self._neutral_centroid_generation_registry.get(
            component_id
        )
        if watermark is None or generation != watermark.max_seen_generation:
            raise RuntimeError(
                "neutral centroid generation must be admitted before apply"
            )
        self._neutral_centroid_generation_registry[component_id] = replace(
            watermark,
            max_applied_generation=max(
                watermark.max_applied_generation,
                generation,
            ),
        )

    def _neutral_centroid_publication_base_states(
        self,
        track_ids: Iterable[str],
    ) -> tuple[dict[str, EKFState] | None, str | None]:
        """Rebuild exact observation-history states at publication time."""

        publication_bases: dict[str, EKFState] = {}
        for track_id in track_ids:
            record = self.tracks.get(track_id)
            if record is None:
                return None, "member_track_missing"
            try:
                state = self._state_at(record, self.current_time)
            except (
                ValueError,
                FloatingPointError,
                np.linalg.LinAlgError,
                RuntimeError,
            ):
                return None, "publication_base_replay_failed"
            covariance = np.asarray(state.covariance, dtype=float)
            if (
                state.state.shape != (6,)
                or covariance.shape != (6, 6)
                or not np.isfinite(state.state).all()
                or not np.isfinite(covariance).all()
                or abs(state.timestamp - self.current_time) > 1.0e-9
            ):
                return None, "publication_base_state_invalid"
            covariance = 0.5 * (covariance + covariance.T)
            if float(np.linalg.eigvalsh(covariance)[0]) < -1.0e-8:
                return None, "publication_base_covariance_not_psd"
            publication_bases[track_id] = EKFState(
                state.state.copy(),
                covariance,
                state.timestamp,
            )
        return publication_bases, None

    def _replace_neutral_centroid_publication_states(
        self,
        publication_bases: Mapping[str, EKFState],
    ) -> None:
        """Remove any older temporary correction from the named members."""

        for track_id, publication_base in publication_bases.items():
            record = self.tracks[track_id]
            record.current_state = publication_base.copy()
            record.current_state_covariance_limited = False

    def _build_neutral_centroid_correction(
        self,
        observations: list[SensorObservation],
        ambiguity: _RadarAssignmentAmbiguity,
        evidence: StructuralAmbiguityEvidence,
        *,
        publication_base_states: Mapping[str, EKFState],
        scan_has_oosm: bool,
        scan_has_stale_observation: bool,
    ) -> tuple[_NeutralCentroidCorrection | None, str | None]:
        member_count = len(ambiguity.track_ids)
        observation_count = len(ambiguity.observation_indices)
        if member_count != observation_count:
            return None, "unbalanced_component"
        if member_count < 2:
            return None, "component_too_small"
        if member_count > self.neutral_centroid_max_component_size:
            return None, "component_exceeds_k_max"
        if (
            ambiguity.free_row_count != 0
            or evidence.free_row_count != 0
        ):
            return None, "free_row_present"
        if (
            ambiguity.free_column_count != 0
            or evidence.free_column_count != 0
        ):
            return None, "free_column_present"
        if (
            ambiguity.maximum_matching_cardinality != member_count
            or evidence.maximum_matching_cardinality != member_count
        ):
            return None, "maximum_matching_not_full"
        if (
            ambiguity.component_kinds != ("alternating_cycle",)
            or evidence.component_kinds != ("alternating_cycle",)
        ):
            return None, "component_not_pure_alternating_cycle"
        if scan_has_oosm:
            return None, "oosm_scan"
        if scan_has_stale_observation:
            return None, "stale_scan"
        if evidence.frame_id != "NED":
            return None, "frame_contract_mismatch"
        if (
            evidence.member_count != member_count
            or evidence.observation_count != observation_count
        ):
            return None, "evidence_cardinality_mismatch"

        try:
            component_observations = tuple(
                observations[index]
                for index in ambiguity.observation_indices
            )
        except IndexError:
            return None, "observation_index_out_of_range"
        if not component_observations:
            return None, "empty_component"

        first = component_observations[0]
        if (
            first.modality != "radar"
            or first.frame_id.upper() != "NED"
            or evidence.sensor_id != first.sensor_id
        ):
            return None, "sensor_frame_contract_mismatch"
        first_scan_key = self._observer_scan_key(first)
        for observation in component_observations:
            if (
                observation.modality != "radar"
                or observation.sensor_id != first.sensor_id
                or observation.frame_id.upper() != "NED"
                or self._observer_scan_key(observation) != first_scan_key
                or abs(
                    observation.measurement_timestamp
                    - first.measurement_timestamp
                )
                > 1.0e-9
                or abs(
                    observation.arrival_timestamp
                    - first.arrival_timestamp
                )
                > 1.0e-9
            ):
                return None, "sensor_scan_time_frame_contract_mismatch"
        if (
            abs(
                evidence.measurement_timestamp
                - first.measurement_timestamp
            )
            > 1.0e-9
            or abs(evidence.arrival_timestamp - first.arrival_timestamp)
            > 1.0e-9
            or abs(
                evidence.state_valid_timestamp
                - first.measurement_timestamp
            )
            > 1.0e-9
        ):
            return None, "evidence_timestamp_contract_mismatch"

        if any(
            _contains_neutral_centroid_identity_metadata(
                observation.metadata
            )
            for observation in component_observations
        ):
            return None, "forbidden_identity_metadata"
        if any(
            _contains_neutral_centroid_identity_metadata(
                self.tracks[track_id].metadata
            )
            for track_id in ambiguity.track_ids
        ):
            return None, "forbidden_member_identity_metadata"

        lineage_payloads: dict[str, str] = {}
        for observation in component_observations:
            lineage_key = _opaque_structural_digest(
                "d1-neutral-centroid-lineage-sha256:",
                observation.source_lineage_key,
            )
            payload_digest = _opaque_structural_digest(
                "d1-neutral-centroid-payload-sha256:",
                (
                    observation.measurement,
                    observation.covariance,
                    observation.measurement_timestamp,
                    observation.arrival_timestamp,
                ),
            )
            previous_payload = lineage_payloads.get(lineage_key)
            if previous_payload is not None:
                if previous_payload == payload_digest:
                    return None, "duplicate_source_claim"
                return None, "conflicting_source_claim"
            lineage_payloads[lineage_key] = payload_digest

        member_positions = np.stack(
            [item.state[:3] for item in evidence.member_states],
            axis=0,
        )
        observation_positions = np.stack(
            [item.position_ned for item in evidence.observations],
            axis=0,
        )
        if (
            member_positions.shape != (member_count, 3)
            or observation_positions.shape != (observation_count, 3)
        ):
            return None, "cartesian_state_shape_mismatch"

        predicted_centroid = np.mean(member_positions, axis=0)
        observed_centroid = np.mean(observation_positions, axis=0)
        centroid_innovation = observed_centroid - predicted_centroid
        centered_members = member_positions - predicted_centroid
        centered_observations = observation_positions - observed_centroid
        member_shape = centered_members.T @ centered_members / member_count
        observation_shape = (
            centered_observations.T
            @ centered_observations
            / observation_count
        )
        shape_mismatch_m2 = float(
            np.linalg.norm(observation_shape - member_shape, ord="fro")
        )
        if not np.isfinite(shape_mismatch_m2):
            return None, "nonfinite_shape_mismatch"
        self.max_neutral_centroid_shape_mismatch_m2 = max(
            self.max_neutral_centroid_shape_mismatch_m2,
            shape_mismatch_m2,
        )
        if (
            shape_mismatch_m2
            > self.neutral_centroid_shape_gate_m2 + 1.0e-12
        ):
            return None, "shape_gate_rejected"

        member_centroid_covariance = sum(
            (
                np.asarray(item.covariance[:3, :3], dtype=float)
                for item in evidence.member_states
            ),
            start=np.zeros((3, 3), dtype=float),
        ) / float(member_count * member_count)
        observation_centroid_covariance = sum(
            (
                np.asarray(item.covariance_ned, dtype=float)
                for item in evidence.observations
            ),
            start=np.zeros((3, 3), dtype=float),
        ) / float(observation_count * observation_count)
        centroid_covariance = (
            member_centroid_covariance
            + observation_centroid_covariance
        )
        centroid_covariance = 0.5 * (
            centroid_covariance + centroid_covariance.T
        )
        if not np.isfinite(centroid_covariance).all():
            return None, "nonfinite_centroid_covariance"
        centroid_covariance_eigenvalues = np.linalg.eigvalsh(
            centroid_covariance
        )
        if float(centroid_covariance_eigenvalues[0]) < -1.0e-8:
            return None, "centroid_covariance_not_psd"
        if float(centroid_covariance_eigenvalues[0]) < 0.0:
            eigenvalues, eigenvectors = np.linalg.eigh(
                centroid_covariance
            )
            centroid_covariance = (
                eigenvectors
                @ np.diag(np.maximum(eigenvalues, 0.0))
                @ eigenvectors.T
            )
            centroid_covariance = 0.5 * (
                centroid_covariance + centroid_covariance.T
            )

        innovation_covariance = (
            centroid_covariance
            + max(
                self.neutral_centroid_min_position_variance_m2,
                1.0e-12,
            )
            * np.eye(3)
        )
        try:
            centroid_nis = float(
                centroid_innovation.T
                @ np.linalg.pinv(innovation_covariance)
                @ centroid_innovation
            )
        except np.linalg.LinAlgError:
            return None, "centroid_innovation_solve_failed"
        if not np.isfinite(centroid_nis):
            return None, "nonfinite_centroid_nis"
        self.max_neutral_centroid_nis = max(
            self.max_neutral_centroid_nis,
            centroid_nis,
        )
        if centroid_nis > self.neutral_centroid_gate_chi2 + 1.0e-12:
            return None, "centroid_gate_rejected"

        innovation_norm = float(np.linalg.norm(centroid_innovation))
        if not np.isfinite(innovation_norm):
            return None, "nonfinite_centroid_innovation"
        if innovation_norm > self.neutral_centroid_max_translation_m:
            clipped_innovation = (
                centroid_innovation
                * (
                    self.neutral_centroid_max_translation_m
                    / innovation_norm
                )
            )
        else:
            clipped_innovation = centroid_innovation
        translation_ned = (
            self.neutral_centroid_gain * clipped_innovation
        )
        position_covariance_inflation = (
            self.neutral_centroid_gain**2 * centroid_covariance
            + (
                self.neutral_centroid_shape_inflation_scale
                * shape_mismatch_m2
                + self.neutral_centroid_min_position_variance_m2
            )
            * np.eye(3)
        )
        position_covariance_inflation = 0.5 * (
            position_covariance_inflation
            + position_covariance_inflation.T
        )
        if (
            not np.isfinite(translation_ned).all()
            or not np.isfinite(position_covariance_inflation).all()
        ):
            return None, "nonfinite_correction"
        inflation_eigenvalues = np.linalg.eigvalsh(
            position_covariance_inflation
        )
        if float(inflation_eigenvalues[0]) < -1.0e-8:
            return None, "covariance_inflation_not_psd"

        for track_id in ambiguity.track_ids:
            record = self.tracks.get(track_id)
            if record is None:
                return None, "member_track_missing"
            publication_base = publication_base_states.get(track_id)
            if publication_base is None:
                return None, "publication_base_member_missing"
            prior_covariance = np.asarray(
                publication_base.covariance,
                dtype=float,
            )
            if (
                prior_covariance.shape != (6, 6)
                or not np.isfinite(prior_covariance).all()
                or not np.isfinite(publication_base.state).all()
            ):
                return None, "member_state_invalid"
            candidate_covariance = prior_covariance.copy()
            candidate_covariance[:3, :3] += (
                position_covariance_inflation
            )
            candidate_covariance = 0.5 * (
                candidate_covariance + candidate_covariance.T
            )
            if np.any(
                np.diag(candidate_covariance)
                > self.covariance_ceiling_diag + 1.0e-9
            ):
                return None, "member_covariance_ceiling_exceeded"
            if float(np.linalg.eigvalsh(candidate_covariance)[0]) < -1.0e-8:
                return None, "member_covariance_not_psd"
            covariance_delta = candidate_covariance - prior_covariance
            covariance_delta = 0.5 * (
                covariance_delta + covariance_delta.T
            )
            if float(np.linalg.eigvalsh(covariance_delta)[0]) < -1.0e-8:
                return None, "member_covariance_would_contract"
            prior_level = self._classify(
                record,
                a95_m=covariance_a95(prior_covariance),
            )
            candidate_level = self._classify(
                record,
                a95_m=covariance_a95(candidate_covariance),
            )
            if candidate_level != prior_level:
                return None, "track_level_change_rejected"

        return (
            _NeutralCentroidCorrection(
                track_ids=tuple(ambiguity.track_ids),
                translation_ned=np.asarray(
                    translation_ned,
                    dtype=float,
                ),
                position_covariance_inflation=np.asarray(
                    position_covariance_inflation,
                    dtype=float,
                ),
                centroid_nis=centroid_nis,
                shape_mismatch_m2=shape_mismatch_m2,
                linear_input_operation_count=(
                    member_count + observation_count
                ),
            ),
            None,
        )

    def _reject_neutral_centroid_component(self, reason: str) -> None:
        normalized = str(reason)
        self.neutral_centroid_rejected_component_count += 1
        self._neutral_centroid_rejection_reasons[normalized] += 1
        self._latest_neutral_centroid_rejection_reason = normalized

    def _structural_ambiguity_observation_keys(
        self,
        observations: list[SensorObservation],
    ) -> dict[int, str]:
        """Build permutation-stable keys from numeric online evidence only."""

        signatures: list[tuple[str, int]] = []
        for index, observation in enumerate(observations):
            state, covariance = radar_state_from_observation(
                observation,
                self.radar_covariance_config,
            )
            radial_velocity_observed = bool(
                observation.metadata.get(
                    "radial_velocity_observed",
                    observation.measurement.size >= 4,
                )
                and observation.measurement.size >= 4
            )
            signature = (
                observation.sensor_id,
                observation.modality,
                observation.frame_id,
                float(observation.measurement_timestamp),
                float(observation.arrival_timestamp),
                state[:3],
                covariance[:3, :3],
                radial_velocity_observed,
            )
            signatures.append(
                (
                    _opaque_structural_digest(
                        "d1-observation-content-sha256:",
                        signature,
                    ),
                    index,
                )
            )

        occurrence_by_signature: defaultdict[str, int] = defaultdict(int)
        keys: dict[int, str] = {}
        for content_digest, index in sorted(signatures):
            occurrence = occurrence_by_signature[content_digest]
            occurrence_by_signature[content_digest] += 1
            keys[index] = _opaque_structural_digest(
                "d1-observation-sha256:",
                (content_digest, occurrence),
            )
        return keys

    def _record_structural_ambiguity_prediction_only(
        self,
        result: _ScanAssociationResult,
        evidence: tuple[StructuralAmbiguityEvidence, ...],
    ) -> None:
        if not evidence:
            return
        self.structural_ambiguity_evidence_component_count += len(evidence)
        self.structural_ambiguity_evidence_observation_count += sum(
            item.observation_count for item in evidence
        )
        self.structural_ambiguity_evidence_member_count += sum(
            item.member_count for item in evidence
        )
        self.structural_ambiguity_deferred_birth_count += sum(
            int(observation.birth_deferred)
            for item in evidence
            for observation in item.observations
        )
        self.structural_ambiguity_prediction_only_member_count += sum(
            item.member_count for item in evidence
        )
        self._latest_structural_ambiguity_component_ids = tuple(
            item.component_id for item in evidence
        )
        track_ids = {
            track_id
            for ambiguity in result.radar_ambiguities.values()
            for track_id in ambiguity.track_ids
        }
        for track_id in track_ids:
            self.tracks[track_id].association_diagnostics[
                "structural_ambiguity_prediction_only"
            ] += 1

    def _record_radar_assignment_ambiguity_tracks(
        self,
        observations: list[SensorObservation],
        result: _ScanAssociationResult,
    ) -> None:
        if not result.radar_ambiguities:
            return

        unique_components = {
            (
                ambiguity.track_ids,
                ambiguity.observation_indices,
                ambiguity.policy_version,
            ): ambiguity
            for ambiguity in result.radar_ambiguities.values()
        }
        track_ids = tuple(
            sorted(
                {
                    track_id
                    for ambiguity in unique_components.values()
                    for track_id in ambiguity.track_ids
                }
            )
        )
        self.radar_assignment_ambiguity_scan_count += 1
        self.radar_assignment_ambiguity_track_coast_count += len(track_ids)
        self.max_radar_assignment_ambiguity_component_size = max(
            self.max_radar_assignment_ambiguity_component_size,
            max(item.component_size for item in unique_components.values()),
        )
        self._latest_radar_assignment_ambiguity_track_ids = track_ids

        measurement_timestamp = float(observations[0].measurement_timestamp)
        arrival_timestamp = float(observations[0].arrival_timestamp)
        for track_id in track_ids:
            relevant_components = [
                item
                for item in unique_components.values()
                if track_id in item.track_ids
            ]
            record = self.tracks[track_id]
            record.association_diagnostics[
                "radar_assignment_ambiguity_suppressed"
            ] += 1
            metadata = {
                "latest_radar_assignment_ambiguity_reason": (
                    relevant_components[0].reason
                ),
                "latest_radar_assignment_ambiguity_policy_version": (
                    relevant_components[0].policy_version
                ),
                "latest_radar_assignment_ambiguity_measurement_timestamp": (
                    measurement_timestamp
                ),
                "latest_radar_assignment_ambiguity_arrival_timestamp": (
                    arrival_timestamp
                ),
                "latest_radar_assignment_ambiguity_component_size": max(
                    item.component_size for item in relevant_components
                ),
            }
            if (
                relevant_components[0].policy_version
                == RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
            ):
                metadata.update(
                    {
                        "latest_radar_assignment_ambiguity_observation_count": max(
                            item.observation_count
                            for item in relevant_components
                        ),
                        "latest_radar_assignment_ambiguity_component_kinds": tuple(
                            sorted(
                                {
                                    kind
                                    for item in relevant_components
                                    for kind in item.component_kinds
                                }
                            )
                        ),
                    }
                )
            record.metadata.update(metadata)

    def _record_eo_projection_scan_diagnostics(
        self,
        observations: list[SensorObservation],
        cost_matrix: np.ndarray,
        assignments: dict[int, str],
    ) -> None:
        """Record truth-free outcomes of the existing EO innovation gate."""

        for column, observation in enumerate(observations):
            if observation.modality != "eo":
                continue
            finite_costs = cost_matrix[np.isfinite(cost_matrix[:, column]), column]
            if finite_costs.size == 0:
                self.eo_projection_unavailable_count += 1
                self._latest_eo_projection_rejection_reason = (
                    "camera_geometry_or_projection_unavailable"
                )
                continue
            best_nis = float(np.min(finite_costs))
            if best_nis > self.association_gate:
                self.eo_projection_gate_rejection_count += 1
                self._latest_eo_projection_rejection_reason = (
                    "projection_innovation_gate_rejected"
                )
                continue
            self.eo_projection_gate_pass_count += 1
            self.max_eo_projection_gate_pass_nis = max(
                self.max_eo_projection_gate_pass_nis,
                best_nis,
            )
            if column not in assignments:
                self.eo_one_to_one_unassigned_count += 1
                self._latest_eo_projection_rejection_reason = (
                    "one_to_one_assignment_conflict"
                )

    def _radar_scan_cost_matrix(
        self,
        track_items: list[tuple[str, TrackRecord]],
        observations: list[SensorObservation],
    ) -> np.ndarray:
        """Build exact radar costs after a conservative gate lower bound."""

        context = self._batch_context
        measurement_timestamp = observations[0].measurement_timestamp
        track_states = [
            self._state_at(record, measurement_timestamp)
            for _, record in track_items
        ]
        observation_states = [
            radar_state_from_observation(
                observation,
                self.radar_covariance_config,
            )
            for observation in observations
        ]
        if context is not None:
            context.association_radar_track_state_build_count += len(track_states)
            context.association_radar_observation_state_build_count += len(
                observation_states
            )

        track_positions = np.stack([item.state[:3] for item in track_states])
        track_covariances = np.stack(
            [item.covariance[:3, :3] for item in track_states]
        )
        observation_positions = np.stack(
            [item[0][:3] for item in observation_states]
        )
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
        pair_count = len(track_states) * len(observation_states)
        if not self.radar_association_lower_bound_gate:
            if context is not None:
                context.association_innovation_solve_count += pair_count
            inverses = np.linalg.pinv(
                innovation_covariances,
                rcond=RADAR_ASSOCIATION_PINV_RCOND,
            )
            return np.einsum(
                "toi,toij,toj->to",
                differences,
                inverses,
                differences,
            )

        rejected = _radar_lower_bound_rejection_mask(
            differences,
            innovation_covariances,
            self.association_gate,
        )
        exact = ~rejected
        exact_solve_count = int(np.count_nonzero(exact))
        if context is not None:
            context.association_innovation_solve_count += exact_solve_count
        cost_matrix = np.full(rejected.shape, np.inf, dtype=float)
        if exact_solve_count == 0:
            return cost_matrix

        exact_differences = differences[exact]
        exact_inverses = np.linalg.pinv(
            innovation_covariances[exact],
            rcond=RADAR_ASSOCIATION_PINV_RCOND,
        )
        cost_matrix[exact] = np.einsum(
            "ni,nij,nj->n",
            exact_differences,
            exact_inverses,
            exact_differences,
        )
        return cost_matrix

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
        if self.batched_non_radar_innovation_solve:
            return self._batched_non_radar_scan_cost_matrix(
                observations,
                states,
                models,
                cost_matrix,
                projection_cache,
            )

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

    def _batched_non_radar_scan_cost_matrix(
        self,
        observations: list[SensorObservation],
        states: list[EKFState | None],
        models: list[MeasurementModel | None],
        cost_matrix: np.ndarray,
        projection_cache: dict[
            tuple[int, tuple[Any, ...]],
            tuple[np.ndarray, np.ndarray] | None,
        ],
    ) -> np.ndarray:
        """Batch identical-shape innovation inversions without changing costs.

        A scan may contain many observations from one camera geometry.  Their
        projected mean and Jacobian are identical for a given track, while
        their measurement and covariance remain observation-specific.  NumPy
        ``pinv`` accepts a stack of matrices and returns the same per-matrix
        pseudoinverse as individual calls.  Residual wrapping and each scalar
        quadratic form deliberately retain the legacy operation order.
        """

        grouped_columns: dict[
            tuple[tuple[Any, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]],
            list[int],
        ] = {}
        for column, model in enumerate(models):
            if model is None:
                continue
            geometry_key = model.geometry_key or (
                "observation",
                observations[column].observation_id,
            )
            group_key = (
                geometry_key,
                tuple(int(item) for item in model.z.shape),
                tuple(int(item) for item in model.r.shape),
                tuple(int(item) for item in model.angle_indices),
            )
            grouped_columns.setdefault(group_key, []).append(column)

        context = self._batch_context
        for group_key, columns in grouped_columns.items():
            geometry_key = group_key[0]
            representative = models[columns[0]]
            if representative is None:
                continue
            measurement_dimension = int(representative.z.size)
            identity = np.eye(measurement_dimension, dtype=float)
            valid_rows: list[int] = []
            predicted_measurements: list[np.ndarray] = []
            base_innovation_covariances: list[np.ndarray] = []

            for row, state in enumerate(states):
                if state is None:
                    continue
                cache_key = (row, geometry_key)
                if cache_key not in projection_cache:
                    if context is not None:
                        context.association_projection_build_count += 1
                    try:
                        projection_cache[cache_key] = (
                            representative.h_fn(state.state),
                            representative.h_jacobian_fn(state.state),
                        )
                    except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                        projection_cache[cache_key] = None
                projection = projection_cache[cache_key]
                if projection is None:
                    continue
                try:
                    base_covariance = (
                        projection[1]
                        @ state.covariance
                        @ projection[1].T
                    )
                except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                    continue
                valid_rows.append(row)
                predicted_measurements.append(projection[0])
                base_innovation_covariances.append(base_covariance)

            if not valid_rows:
                continue

            try:
                innovation_covariances = np.empty(
                    (
                        len(valid_rows),
                        len(columns),
                        measurement_dimension,
                        measurement_dimension,
                    ),
                    dtype=float,
                )
                for local_row, base_covariance in enumerate(
                    base_innovation_covariances
                ):
                    for local_column, column in enumerate(columns):
                        model = models[column]
                        if model is None:
                            raise RuntimeError("grouped measurement model disappeared")
                        innovation_covariance = base_covariance + model.r
                        innovation_covariances[local_row, local_column] = (
                            0.5
                            * (
                                innovation_covariance
                                + innovation_covariance.T
                            )
                            + 1.0e-9 * identity
                        )
                inverses = np.linalg.pinv(innovation_covariances)
            except (
                ValueError,
                FloatingPointError,
                np.linalg.LinAlgError,
                RuntimeError,
            ):
                self._fill_non_radar_group_scalar(
                    models,
                    valid_rows,
                    columns,
                    predicted_measurements,
                    base_innovation_covariances,
                    cost_matrix,
                )
                continue

            if context is not None:
                context.association_innovation_solve_count += (
                    len(valid_rows) * len(columns)
                )
            for local_row, row in enumerate(valid_rows):
                predicted_measurement = predicted_measurements[local_row]
                for local_column, column in enumerate(columns):
                    model = models[column]
                    if model is None:
                        continue
                    residual = wrap_residual(
                        model.z - predicted_measurement,
                        model.angle_indices,
                    )
                    cost_matrix[row, column] = float(
                        residual.T
                        @ inverses[local_row, local_column]
                        @ residual
                    )
        return cost_matrix

    def _fill_non_radar_group_scalar(
        self,
        models: list[MeasurementModel | None],
        valid_rows: list[int],
        columns: list[int],
        predicted_measurements: list[np.ndarray],
        base_innovation_covariances: list[np.ndarray],
        cost_matrix: np.ndarray,
    ) -> None:
        """Preserve per-pair failure isolation if a batched solve is rejected."""

        context = self._batch_context
        for local_row, row in enumerate(valid_rows):
            predicted_measurement = predicted_measurements[local_row]
            for column in columns:
                model = models[column]
                if model is None:
                    continue
                try:
                    residual = wrap_residual(
                        model.z - predicted_measurement,
                        model.angle_indices,
                    )
                    innovation_covariance = (
                        base_innovation_covariances[local_row] + model.r
                    )
                    innovation_covariance = (
                        0.5
                        * (
                            innovation_covariance
                            + innovation_covariance.T
                        )
                        + 1.0e-9 * np.eye(innovation_covariance.shape[0])
                    )
                    if context is not None:
                        context.association_innovation_solve_count += 1
                    inverse = np.linalg.pinv(innovation_covariance)
                    cost_matrix[row, column] = float(
                        residual.T @ inverse @ residual
                    )
                except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                    cost_matrix[row, column] = np.inf

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
        elif reason == "radar_assignment_ambiguity_suppressed":
            self.radar_assignment_ambiguity_observation_suppression_count += 1

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
        elif (
            self.incremental_replay_cache
            and self.direct_checkpoint_state_queries
            and record.replay_checkpoints_complete
        ):
            self._refresh_initial(record)
            if record.replay_checkpoints_complete:
                if context is not None:
                    context.checkpoint_state_query_count += 1
                state = self._state_from_complete_replay_checkpoints(
                    record,
                    timestamp,
                )
            else:
                state, _, _ = self._replay_record(record, timestamp)
        else:
            state, _, _ = self._replay_record(record, timestamp)
        if context is not None:
            context.state_cache[key] = state.copy()
        return state

    def _state_from_complete_replay_checkpoints(
        self,
        record: TrackRecord,
        timestamp: float,
    ) -> EKFState:
        """Query an exact state without walking an already-cached history."""

        cutoff = float(timestamp) + 1.0e-9
        checkpoint_count = bisect_right(
            record.replay_checkpoints,
            cutoff,
            key=lambda checkpoint: checkpoint.sort_key[0],
        )
        state = (
            record.initial_state.copy()
            if checkpoint_count == 0
            else record.replay_checkpoints[checkpoint_count - 1].posterior.copy()
        )
        return self._predict_to(state, timestamp)

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

    def _refresh_cached_consistency_evidence_if_enabled(
        self,
        record: TrackRecord,
        observation: SensorObservation | None,
    ) -> bool:
        """Advance unchanged cached evidence without rebuilding its model/state."""

        context = self._consistency_capture_context
        if (
            not self.cached_consistency_prefix_refresh
            or observation is None
            or context is None
            or context[0] != record.track_id
        ):
            return False
        previous = self._consistency_evidence.get(observation.observation_id)
        if previous is None or previous.source_global_track_id != record.track_id:
            return False
        if self.trusted_consistency_counter_refresh:
            refreshed = previous.with_replay_counters(
                replay_revision=context[1],
                replay_count=previous.replay_count + 1,
            )
        else:
            refreshed = replace(
                previous,
                replay_revision=context[1],
                replay_count=previous.replay_count + 1,
            )
        self._consistency_evidence[observation.observation_id] = refreshed
        if self._batch_context is not None:
            self._batch_context.cached_consistency_refresh_count += 1
        return True

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
            state = self._predict_to(
                state,
                observation.measurement_timestamp,
            )
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
        state = self._predict_to(state, until_time)
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
        if not self._refresh_cached_consistency_evidence_if_enabled(
            record,
            initial_observation,
        ):
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
                state = self._predict_to(
                    state,
                    observation.measurement_timestamp,
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
            state = self._predict_to(state, until_time)
            return state, nises, tuple(gated_observation_ids)

        prefix_limit = min(len(eligible), len(record.replay_checkpoints))
        if self.trusted_replay_checkpoint_prefix:
            matching_prefix = prefix_limit
            if self._batch_context is not None:
                self._batch_context.replay_checkpoint_prefix_fast_path_count += (
                    matching_prefix
                )
        else:
            matching_prefix = 0
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
            nises.append(checkpoint.nis)
            if checkpoint.gated:
                gated_observation_ids.append(observation.observation_id)
            if not self._refresh_cached_consistency_evidence_if_enabled(
                record,
                observation,
            ):
                self._capture_consistency_update_if_enabled(
                    record,
                    observation,
                    checkpoint.posterior,
                    checkpoint.nis,
                    checkpoint.gated,
                )
        if matching_prefix:
            state = record.replay_checkpoints[matching_prefix - 1].posterior.copy()
        if self._batch_context is not None:
            self._batch_context.replay_checkpoint_reuse_count += matching_prefix

        for observation in eligible[matching_prefix:]:
            state = self._predict_to(
                state,
                observation.measurement_timestamp,
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
        state = self._predict_to(state, until_time)
        return state, nises, tuple(gated_observation_ids)

    def _invalidate_replay_checkpoints(
        self,
        record: TrackRecord,
        *,
        from_sort_key: tuple[float, float, str] | None = None,
    ) -> None:
        record.replay_checkpoints_complete = False
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
        can_reuse_suffix = (
            self.incremental_replay_cache
            and self.fixed_lag_checkpoint_suffix_reuse
            and record.replay_checkpoints_complete
        )
        if can_reuse_suffix:
            checkpoint = self._state_from_complete_replay_checkpoints(
                record,
                checkpoint_timestamp,
            )
        else:
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
        if can_reuse_suffix:
            record.replay_checkpoints = [
                checkpoint_item
                for checkpoint_item in record.replay_checkpoints
                if checkpoint_item.sort_key[0] > checkpoint_timestamp + 1.0e-9
            ]
            context = self._batch_context
            if context is not None:
                context.fixed_lag_checkpoint_suffix_reuse_count += len(
                    record.replay_checkpoints
                )
        else:
            self._invalidate_replay_checkpoints(record)
        record.checkpoint_active = True
        record.checkpoint_count += 1
        context = self._batch_context
        if context is not None:
            context.fixed_lag_rebase_count += 1

        rebased_state, rebased_nises, gated_observation_ids = self._replay_record(
            record,
            current_time,
        )
        record.current_state = rebased_state
        record.replay_checkpoints_complete = self.incremental_replay_cache
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
        record.covariance_limit_operation_counts.update(
            _metadata_operation_counts(
                observation.metadata.get(
                    "covariance_limit_operation_counts"
                )
            )
        )
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
        self._publication_materialization_operations[
            "global_track_metadata_materialization_count"
        ] += 1
        if not record.current_state_covariance_limited:
            self._limit_record_covariance(record)
        if self.reuse_track_classification_a95:
            a95_m = covariance_a95(record.current_state.covariance)
            level = self._classify(record, a95_m=a95_m)
        else:
            level = self._classify(record)
            a95_m = covariance_a95(record.current_state.covariance)
        likelihood_sum = sum(record.identity_likelihood.values())
        identity_likelihood = (
            {key: value / likelihood_sum for key, value in record.identity_likelihood.items()}
            if likelihood_sum > 0
            else {}
        )
        last_nis = record.recent_nis[-1] if record.recent_nis else None
        metadata = dict(record.metadata)
        if publication_context is None:
            if self.immutable_shared_publication_metadata:
                publication_context = self._track_publication_context()
            else:
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
        if self.immutable_shared_publication_metadata:
            association_audit = publication_context.association_audit
            latency_audit = publication_context.latency_audit
            sensor_health = publication_context.sensor_health
            self._publication_materialization_operations[
                "shared_audit_value_reuse_count"
            ] += 3
        else:
            association_audit = dict(publication_context.association_audit)
            latency_audit = dict(publication_context.latency_audit)
            sensor_health = {
                sensor_id: dict(summary)
                for sensor_id, summary in publication_context.sensor_health.items()
            }
            self._publication_materialization_operations[
                "per_track_shared_audit_mapping_copy_count"
            ] += 3 + len(publication_context.sensor_health)
        metadata.update(
            {
                "a95_m": a95_m,
                "frame_id": "ned",
                "valid_at": record.current_state.timestamp,
                "published_at": self.current_time,
                "hits": record.hits,
                "latency_compensation": self.latency_compensation,
                "source_support": dict(record.source_support),
                "association_diagnostics": dict(record.association_diagnostics),
                "association_audit": association_audit,
                "duplicate_observation_count": self.duplicate_observation_count,
                "latency_audit": latency_audit,
                "sensor_health": sensor_health,
            }
        )
        if self.opaque_source_key_publication_enabled:
            member_token = structural_ambiguity_member_track_token(
                self.publisher_node_id,
                self.publisher_epoch,
                record.track_id,
            )
            metadata.update(
                {
                    "source_node_id": self.publisher_node_id,
                    "source_track_id": structural_ambiguity_source_track_id(
                        self.publisher_epoch,
                        member_token,
                    ),
                    "publisher_epoch": self.publisher_epoch,
                    "opaque_member_track_token": member_token,
                    "source_key": structural_ambiguity_source_key(
                        self.publisher_node_id,
                        self.publisher_epoch,
                        member_token,
                    ),
                }
            )
        self._update_metadata_covariance_reasons(
            metadata,
            tuple(sorted(record.covariance_limit_reasons)),
        )
        serialized_operation_counts = dict(
            sorted(record.covariance_limit_operation_counts.items())
        )
        if serialized_operation_counts:
            operation_count = int(sum(serialized_operation_counts.values()))
            metadata["covariance_limit_operation_counts"] = (
                serialized_operation_counts
            )
            metadata["covariance_limit_operation_count"] = operation_count
            track_operation_counts = {
                name: count
                for name, count in serialized_operation_counts.items()
                if name.startswith("track_covariance_")
            }
            if track_operation_counts:
                metadata["track_covariance_limit_operation_counts"] = (
                    track_operation_counts
                )
                metadata["track_covariance_limit_operation_count"] = int(
                    sum(track_operation_counts.values())
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

    def _classify(
        self,
        record: TrackRecord,
        *,
        a95_m: float | None = None,
    ) -> TrackLevel:
        a95 = (
            covariance_a95(record.current_state.covariance)
            if a95_m is None
            else float(a95_m)
        )
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
        covariance, reasons, anomaly, operation_counts = (
            self._limited_observation_covariance(observation)
        )
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
        if operation_counts:
            existing_counts = _metadata_operation_counts(
                metadata.get("observation_covariance_limit_operation_counts")
            )
            existing_counts.update(operation_counts)
            serialized_counts = dict(sorted(existing_counts.items()))
            metadata["observation_covariance_limit_operation_counts"] = (
                serialized_counts
            )
            metadata["observation_covariance_limit_operation_count"] = int(
                sum(serialized_counts.values())
            )
            _update_metadata_covariance_operation_counts(
                metadata,
                operation_counts,
            )
        scale_reason = self._covariance_scale_reason(observation)
        if scale_reason is not None:
            metadata["covariance_scale_reason"] = scale_reason
        return replace(observation, covariance=covariance, metadata=metadata)

    def _limited_observation_covariance(
        self,
        observation: SensorObservation,
    ) -> tuple[np.ndarray, tuple[str, ...], bool, Counter[str]]:
        reasons: list[str] = []
        operation_counts: Counter[str] = Counter()
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
            vectorized_off_diagonal=self.vectorized_covariance_limit,
            reason_prefix="observation_covariance",
            operation_counts=operation_counts,
        )
        reasons.extend(bound_reasons)
        if any(
            reason
            in {
                "observation_covariance_floor",
                "observation_covariance_ceiling",
                "observation_covariance_correlation_bound",
                "observation_covariance_psd_projection",
                "observation_covariance_psd_diagonal_fallback",
            }
            for reason in reasons
        ):
            anomaly = True
        return (
            covariance,
            tuple(dict.fromkeys(reasons)),
            anomaly,
            operation_counts,
        )

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
        operation_counts: Counter[str] = Counter()
        covariance, applied = self._limit_state_covariance(
            record.current_state.covariance,
            reasons,
            operation_counts=operation_counts,
        )
        record.current_state = EKFState(
            record.current_state.state,
            covariance,
            record.current_state.timestamp,
        )
        record.current_state_covariance_limited = True
        for reason in applied:
            record.covariance_limit_reasons[str(reason)] += 1
        record.covariance_limit_operation_counts.update(operation_counts)
        if applied:
            self._update_metadata_covariance_reasons(record.metadata, tuple(applied))

    def _limit_state_covariance(
        self,
        covariance: np.ndarray,
        reasons: Iterable[str] = (),
        *,
        operation_counts: Counter[str] | None = None,
    ) -> tuple[np.ndarray, tuple[str, ...]]:
        base_reasons = [str(reason) for reason in reasons]
        covariance = np.asarray(covariance, dtype=float)
        if covariance.shape != (6, 6) or not np.isfinite(covariance).all():
            covariance = np.diag(self.covariance_ceiling_diag)
            base_reasons.append("track_covariance_invalid_reset")
            _increment_operation_count(
                operation_counts,
                "track_covariance_invalid_reset_count",
                1,
            )
        covariance = 0.5 * (covariance + covariance.T)
        covariance, bound_reasons = _limit_covariance_diagonal(
            covariance,
            self.covariance_floor_diag,
            self.covariance_ceiling_diag,
            floor_reason="track_covariance_floor",
            ceiling_reason="track_covariance_ceiling",
            vectorized_off_diagonal=self.vectorized_covariance_limit,
            reason_prefix="track_covariance",
            operation_counts=operation_counts,
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
    vectorized_off_diagonal: bool = False,
    reason_prefix: str = "covariance",
    operation_counts: Counter[str] | None = None,
) -> tuple[np.ndarray, tuple[str, ...]]:
    covariance = np.asarray(covariance, dtype=float)
    floor_diag = np.asarray(floor_diag, dtype=float).reshape(-1)
    ceiling_diag = np.asarray(ceiling_diag, dtype=float).reshape(-1)
    if covariance.shape != (floor_diag.size, floor_diag.size):
        raise ValueError("covariance shape does not match diagonal bounds")
    if not np.isfinite(covariance).all():
        raise ValueError("covariance must contain only finite values")
    if (
        not np.isfinite(floor_diag).all()
        or not np.isfinite(ceiling_diag).all()
        or np.any(floor_diag <= 0.0)
        or np.any(ceiling_diag < floor_diag)
    ):
        raise ValueError("covariance diagonal bounds must be positive and ordered")

    reasons: list[str] = []
    bounded = 0.5 * (covariance + covariance.T)
    diag = np.diag(bounded).copy()
    floor_mask = diag < floor_diag
    ceiling_mask = diag > ceiling_diag
    if np.any(floor_mask):
        reasons.append(floor_reason)
        _increment_operation_count(
            operation_counts,
            f"{reason_prefix}_diagonal_floor_element_count",
            int(np.count_nonzero(floor_mask)),
        )
    if np.any(ceiling_mask):
        reasons.append(ceiling_reason)
        _increment_operation_count(
            operation_counts,
            f"{reason_prefix}_diagonal_ceiling_element_count",
            int(np.count_nonzero(ceiling_mask)),
        )
    clipped_diag = np.clip(diag, floor_diag, ceiling_diag)
    np.fill_diagonal(bounded, clipped_diag)

    if vectorized_off_diagonal:
        correlation_clip_count = _clip_covariance_off_diagonal_vectorized(
            bounded
        )
    else:
        correlation_clip_count = _clip_covariance_off_diagonal_reference(
            bounded
        )
    if correlation_clip_count:
        reasons.append(f"{reason_prefix}_correlation_bound")
        _increment_operation_count(
            operation_counts,
            f"{reason_prefix}_correlation_clip_pair_count",
            correlation_clip_count,
        )

    bounded, psd_reasons = _project_bounded_covariance_to_psd(
        bounded,
        clipped_diag,
        reason_prefix=reason_prefix,
        operation_counts=operation_counts,
    )
    reasons.extend(psd_reasons)
    return bounded, tuple(dict.fromkeys(reasons))


def _clip_covariance_off_diagonal_reference(bounded: np.ndarray) -> int:
    """Apply the established scalar pairwise correlation bound in place."""

    clip_count = 0
    for row in range(bounded.shape[0]):
        for col in range(row + 1, bounded.shape[1]):
            limit = COVARIANCE_CORRELATION_LIMIT * np.sqrt(
                max(bounded[row, row], 0.0)
                * max(bounded[col, col], 0.0)
            )
            original = bounded[row, col]
            bounded[row, col] = float(np.clip(original, -limit, limit))
            clip_count += int(bounded[row, col] != original)
            bounded[col, row] = bounded[row, col]
    return clip_count


def _clip_covariance_off_diagonal_vectorized(bounded: np.ndarray) -> int:
    """Apply the same pairwise bound without per-element NumPy calls."""

    dimension = bounded.shape[0]
    if dimension < len(_COVARIANCE_STRICT_UPPER_INDICES):
        rows, columns = _COVARIANCE_STRICT_UPPER_INDICES[dimension]
    else:
        rows, columns = np.triu_indices(dimension, k=1)
    nonnegative_diagonal = np.maximum(np.diag(bounded), 0.0)
    limits = COVARIANCE_CORRELATION_LIMIT * np.sqrt(
        nonnegative_diagonal[rows] * nonnegative_diagonal[columns]
    )
    original = bounded[rows, columns]
    clipped = np.clip(original, -limits, limits)
    clip_count = int(np.count_nonzero(clipped != original))
    bounded[rows, columns] = clipped
    bounded[columns, rows] = clipped
    return clip_count


def _project_bounded_covariance_to_psd(
    bounded: np.ndarray,
    diagonal: np.ndarray,
    *,
    reason_prefix: str,
    operation_counts: Counter[str] | None,
) -> tuple[np.ndarray, tuple[str, ...]]:
    """Repair a bounded covariance without changing its governed diagonal.

    Pairwise correlation clipping constrains every two-dimensional principal
    submatrix but can make the complete matrix indefinite. The repair projects
    the normalized correlation matrix onto the positive-semidefinite cone,
    restores unit diagonal by congruence scaling, and shrinks it toward the
    identity only as far as required by the correlation bound. A diagonal
    fallback closes the numerical edge case after a finite number of attempts.
    """

    result = 0.5 * (
        np.asarray(bounded, dtype=float)
        + np.asarray(bounded, dtype=float).T
    )
    diagonal = np.asarray(diagonal, dtype=float).reshape(-1)
    eigenvalues = np.linalg.eigvalsh(result)
    if float(eigenvalues[0]) >= 0.0:
        return result, ()

    projection_reason = f"{reason_prefix}_psd_projection"
    reasons = [projection_reason]
    dimension = result.shape[0]
    identity = np.eye(dimension, dtype=float)
    standard_deviation = np.sqrt(diagonal)
    diagonal_scale = float(np.max(diagonal) / np.min(diagonal))
    normalized_floor = min(
        0.25,
        max(
            COVARIANCE_PSD_NORMALIZED_EIGENVALUE_FLOOR,
            np.finfo(float).eps
            * 64.0
            * max(1, dimension)
            * diagonal_scale,
        ),
    )
    correlation_target = np.nextafter(
        COVARIANCE_CORRELATION_LIMIT,
        0.0,
    )

    for _ in range(COVARIANCE_PSD_MAX_PROJECTION_ITERATIONS):
        _increment_operation_count(
            operation_counts,
            f"{reason_prefix}_psd_projection_iteration_count",
            1,
        )
        correlation = result / np.outer(standard_deviation, standard_deviation)
        correlation = 0.5 * (correlation + correlation.T)
        np.fill_diagonal(correlation, 1.0)

        correlation_eigenvalues, eigenvectors = np.linalg.eigh(correlation)
        floor_mask = correlation_eigenvalues < normalized_floor
        floor_count = int(np.count_nonzero(floor_mask))
        _increment_operation_count(
            operation_counts,
            f"{reason_prefix}_psd_eigenvalue_floor_count",
            floor_count,
        )
        projected = (
            eigenvectors
            @ np.diag(
                np.maximum(correlation_eigenvalues, normalized_floor)
            )
            @ eigenvectors.T
        )
        projected = 0.5 * (projected + projected.T)
        projected_diagonal = np.diag(projected).copy()
        if (
            not np.isfinite(projected).all()
            or np.any(projected_diagonal <= 0.0)
        ):
            break

        normalization = np.sqrt(projected_diagonal)
        correlation = projected / np.outer(normalization, normalization)
        correlation = 0.5 * (correlation + correlation.T)
        np.fill_diagonal(correlation, 1.0)

        rows, columns = _strict_upper_indices(dimension)
        max_abs_correlation = (
            0.0
            if rows.size == 0
            else float(np.max(np.abs(correlation[rows, columns])))
        )
        shrink = (
            1.0
            if max_abs_correlation <= correlation_target
            else correlation_target / max_abs_correlation
        )
        normalized_min_eigenvalue = float(
            np.linalg.eigvalsh(correlation)[0]
        )
        if normalized_min_eigenvalue < normalized_floor:
            denominator = 1.0 - normalized_min_eigenvalue
            positive_definite_shrink = (
                0.0
                if denominator <= 0.0
                else (1.0 - normalized_floor) / denominator
            )
            shrink = min(shrink, positive_definite_shrink)
        shrink = float(np.clip(shrink, 0.0, 1.0))
        if shrink < 1.0:
            correlation = shrink * correlation + (1.0 - shrink) * identity
            _increment_operation_count(
                operation_counts,
                f"{reason_prefix}_psd_correlation_shrink_count",
                1,
            )

        result = (
            np.outer(standard_deviation, standard_deviation) * correlation
        )
        result = 0.5 * (result + result.T)
        np.fill_diagonal(result, diagonal)
        if _bounded_covariance_constraints_satisfied(result, diagonal):
            return result, tuple(reasons)

    result = np.diag(diagonal)
    reasons.append(f"{reason_prefix}_psd_diagonal_fallback")
    _increment_operation_count(
        operation_counts,
        f"{reason_prefix}_psd_diagonal_fallback_count",
        1,
    )
    return result, tuple(reasons)


def _bounded_covariance_constraints_satisfied(
    covariance: np.ndarray,
    diagonal: np.ndarray,
) -> bool:
    if (
        not np.isfinite(covariance).all()
        or not np.array_equal(covariance, covariance.T)
        or not np.array_equal(np.diag(covariance), diagonal)
        or float(np.linalg.eigvalsh(covariance)[0]) < 0.0
    ):
        return False
    rows, columns = _strict_upper_indices(covariance.shape[0])
    if rows.size == 0:
        return True
    limits = COVARIANCE_CORRELATION_LIMIT * np.sqrt(
        diagonal[rows] * diagonal[columns]
    )
    return bool(
        np.all(np.abs(covariance[rows, columns]) <= limits)
    )


def _strict_upper_indices(dimension: int) -> tuple[np.ndarray, np.ndarray]:
    if dimension < len(_COVARIANCE_STRICT_UPPER_INDICES):
        return _COVARIANCE_STRICT_UPPER_INDICES[dimension]
    return np.triu_indices(dimension, k=1)


def _increment_operation_count(
    operation_counts: Counter[str] | None,
    name: str,
    count: int,
) -> None:
    if operation_counts is not None and count > 0:
        operation_counts[str(name)] += int(count)


def _metadata_reasons(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(str(key) for key, count in value.items() if int(count) > 0)
    return tuple(str(item) for item in value)


def _metadata_operation_counts(value: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not isinstance(value, Mapping):
        return counts
    for name, raw_count in value.items():
        count = int(raw_count)
        if count > 0:
            counts[str(name)] += count
    return counts


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


def _update_metadata_covariance_operation_counts(
    metadata: dict,
    operation_counts: Mapping[str, int],
) -> None:
    incoming = _metadata_operation_counts(operation_counts)
    if not incoming:
        return
    merged = _metadata_operation_counts(
        metadata.get("covariance_limit_operation_counts")
    )
    merged.update(incoming)
    serialized = dict(sorted(merged.items()))
    metadata["covariance_limit_operation_counts"] = serialized
    metadata["covariance_limit_operation_count"] = int(
        sum(serialized.values())
    )


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


def _opaque_structural_digest(prefix: str, value: Any) -> str:
    canonical = _canonical_structural_value(value)
    payload = json.dumps(
        canonical,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return f"{prefix}{hashlib.sha256(payload).hexdigest()}"


def _canonical_structural_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _canonical_structural_value(value.tolist())
    if isinstance(value, np.generic):
        return _canonical_structural_value(value.item())
    if isinstance(value, dict):
        return {
            str(key): _canonical_structural_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_structural_value(item) for item in value]
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("structural ambiguity digest values must be finite")
        return float(value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)
