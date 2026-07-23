"""Sparse global-nearest-neighbor association for six-state NED tracks."""

from __future__ import annotations

import heapq
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from math import exp, sqrt
from time import perf_counter
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from .ambiguity_hold import (
    AmbiguityComponent3D,
    AmbiguityComponentValidationError,
    AmbiguityHoldLeaseConfig,
)
from .models import (
    AssociationResult,
    AssociationRiskSummary,
    MatchedPair,
    RejectedPair,
    TrackLifecycleState,
    govern_covariance,
)
from .identity_commitment import (
    D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION,
    D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION,
    IdentityCommitmentState,
    IdentityCommitmentRecoveryConfig,
    IdentityEvidenceCommitment,
)
from .observation_governance import (
    OBSERVATION_CLAIM_LEDGER_SCHEMA_VERSION,
    ObservationClaimLedgerConfig,
    ReplayCoastConfig,
)
from .scalable_3d_models import (
    POSITION_H_3D,
    STATE_ORDER_3D,
    Detection3D,
    GlobalTrack3D,
    assert_online_metadata_truth_free,
)


CHI2_GATE_3D_99_PERCENT = 11.344866730144373
LARGE_SPARSE_COST = 1.0e12
_NO_PRECOMPUTED_NIS = object()


@dataclass(frozen=True, slots=True)
class _SparseEdge:
    track_index: int
    detection_index: int
    cost: float
    mahalanobis_squared: float
    velocity_mahalanobis_squared: float | None
    velocity_cost_gated: bool


@dataclass(slots=True)
class _SparseAssociationResult(AssociationResult):
    """Association result with tracker-only edge diagnostics.

    The inherited public serializer intentionally excludes this transient map.
    It only avoids solving the same matched velocity innovation again during
    the immediately following track update.
    """

    matched_velocity_nis: dict[tuple[str, str], float | None] = field(
        default_factory=dict,
        repr=False,
    )


@dataclass(frozen=True, slots=True)
class _ObservationEvidence:
    """Opaque online observation identity used only for replay governance."""

    key: str
    observation_id: str
    source_namespace: str
    source_measurement_timestamp: float | None
    identity_evidence_disposition: str = "target_candidate"

    @property
    def identity_commitment_eligible(self) -> bool:
        return self.identity_evidence_disposition == "target_candidate"


@dataclass(slots=True)
class _ObservationClaim:
    """First-consumption record for one D1 observation lineage token."""

    evidence: _ObservationEvidence
    first_detection_id: str
    first_state_timestamp: float
    status: str = "unseen"
    global_track_id: str | None = None
    ambiguity_component_key: str | None = None
    replay_count: int = 0
    last_replay_state_timestamp: float | None = None


@dataclass(slots=True)
class _AmbiguityLease:
    """One bounded prediction-only hold over a complete D1 component."""

    component_key: str
    component_id: str
    evidence_id: str
    generation: int
    publisher_node_id: str
    publisher_epoch: str
    measurement_timestamp: float
    arrival_timestamp: float
    first_seen_timestamp: float
    last_new_evidence_timestamp: float
    soft_deadline: float
    hard_deadline: float
    member_source_keys: set[str]
    observation_evidence_keys: set[str]
    track_ids: set[str]
    latest_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_key": self.component_key,
            "component_id": self.component_id,
            "evidence_id": self.evidence_id,
            "generation": self.generation,
            "publisher_node_id": self.publisher_node_id,
            "publisher_epoch": self.publisher_epoch,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "first_seen_timestamp": self.first_seen_timestamp,
            "last_new_evidence_timestamp": self.last_new_evidence_timestamp,
            "soft_deadline": self.soft_deadline,
            "hard_deadline": self.hard_deadline,
            "member_source_keys": sorted(self.member_source_keys),
            "observation_evidence_keys": sorted(
                self.observation_evidence_keys
            ),
            "track_ids": sorted(self.track_ids),
            "latest_reason": self.latest_reason,
        }


@dataclass(slots=True)
class _IdentityRecoveryBlockers:
    """Private irreversible evidence barrier for one uncommitted D2 track."""

    evidence_keys: set[str] = field(default_factory=set)
    recovery_not_before_measurement_timestamp: float = 0.0
    overflow: bool = False


@dataclass(slots=True)
class Sparse3DGNNHungarianAssociator:
    """Global nearest-neighbor association on a KD-tree candidate graph.

    ``GNN`` retains its established tracking meaning: global nearest neighbor.
    This class is deterministic optimization code and contains no graph neural
    network or learned edge scorer.
    """

    gate_threshold: float = CHI2_GATE_3D_99_PERCENT
    velocity_weight: float = 0.25
    velocity_cost_gate_threshold: float = CHI2_GATE_3D_99_PERCENT
    source_continuity_bias: float = 2.0
    minimum_query_radius_m: float = 0.0
    large_cost: float = LARGE_SPARSE_COST

    def __post_init__(self) -> None:
        for name in (
            "gate_threshold",
            "velocity_cost_gate_threshold",
            "large_cost",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        for name in (
            "velocity_weight",
            "source_continuity_bias",
            "minimum_query_radius_m",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")

    def associate(
        self,
        tracks: Iterable[GlobalTrack3D],
        detections: Iterable[Detection3D],
        timestamp: float,
        *,
        authoritative_source_bindings: Mapping[str, str] | None = None,
    ) -> AssociationResult:
        """Solve sparse GNN/Hungarian without allocating a full pair matrix."""

        started = perf_counter()
        track_list = sorted(tracks, key=lambda item: item.global_track_id)
        detection_list = sorted(detections, key=lambda item: item.detection_id)
        source_bindings = {
            str(source_key): str(track_id)
            for source_key, track_id in (
                {} if authoritative_source_bindings is None
                else authoritative_source_bindings
            ).items()
        }
        timestamp = float(timestamp)
        self._validate_epoch(track_list, detection_list, timestamp)
        dense_pair_count = len(track_list) * len(detection_list)

        index_started = perf_counter()
        detection_positions = (
            np.asarray([item.position_ned for item in detection_list])
            if detection_list
            else np.empty((0, 3), dtype=float)
        )
        tree = cKDTree(detection_positions) if detection_list else None
        index_seconds = perf_counter() - index_started

        candidate_started = perf_counter()
        edges: dict[tuple[int, int], _SparseEdge] = {}
        queried_pair_count = 0
        rejected_pairs: list[RejectedPair] = []
        candidate_counts_by_track = {
            track.global_track_id: 0 for track in track_list
        }
        candidate_counts_by_detection = {
            detection.detection_id: 0 for detection in detection_list
        }
        query_radius_by_track: dict[str, float] = {}
        maximum_detection_variance = _maximum_position_variance(detection_list)

        if tree is not None and track_list:
            query_radii = self._conservative_query_radii(
                track_list,
                maximum_detection_variance,
            )
            queried_detection_indices = tree.query_ball_point(
                np.asarray([item.position_ned for item in track_list]),
                r=query_radii,
            )
            for track_index, track in enumerate(track_list):
                query_radius = float(query_radii[track_index])
                query_radius_by_track[track.global_track_id] = query_radius
                candidate_indices = sorted(
                    int(index) for index in queried_detection_indices[track_index]
                )
                queried_pair_count += len(candidate_indices)
                for detection_index in candidate_indices:
                    detection = detection_list[detection_index]
                    bound_track_id = (
                        None
                        if detection.source_key is None
                        else source_bindings.get(detection.source_key)
                    )
                    if (
                        bound_track_id is not None
                        and bound_track_id != track.global_track_id
                    ):
                        rejected_pairs.append(
                            RejectedPair(
                                track_id=track.global_track_id,
                                detection_id=detection.detection_id,
                                reason="source_binding_pre_update",
                                value=0.0,
                            )
                        )
                        continue
                    distance = mahalanobis_squared_3d(track, detection)
                    if distance > self.gate_threshold:
                        rejected_pairs.append(
                            RejectedPair(
                                track_id=track.global_track_id,
                                detection_id=detection.detection_id,
                                reason="mahalanobis_gate_3d",
                                value=distance,
                            )
                        )
                        continue
                    velocity_distance = _velocity_mahalanobis_squared(
                        track,
                        detection,
                    )
                    cost = distance
                    velocity_cost_gated = False
                    if velocity_distance is not None:
                        velocity_cost_gated = (
                            velocity_distance > self.velocity_cost_gate_threshold
                        )
                        cost += self.velocity_weight * min(
                            velocity_distance,
                            self.velocity_cost_gate_threshold,
                        )
                    if (
                        detection.source_key is not None
                        and detection.source_key in track.source_track_keys
                    ):
                        cost = max(0.0, cost - self.source_continuity_bias)
                    edge = _SparseEdge(
                        track_index=track_index,
                        detection_index=detection_index,
                        cost=float(cost),
                        mahalanobis_squared=distance,
                        velocity_mahalanobis_squared=velocity_distance,
                        velocity_cost_gated=velocity_cost_gated,
                    )
                    edges[(track_index, detection_index)] = edge
                    candidate_counts_by_track[track.global_track_id] += 1
                    candidate_counts_by_detection[detection.detection_id] += 1
        candidate_seconds = perf_counter() - candidate_started

        assignment_started = perf_counter()
        components = _candidate_components(
            len(track_list),
            len(detection_list),
            edges,
        )
        matched_pairs: list[MatchedPair] = []
        matched_track_indices: set[int] = set()
        matched_detection_indices: set[int] = set()
        matched_velocity_nis: dict[tuple[str, str], float | None] = {}
        component_matrix_pair_count = 0
        peak_component_pair_count = 0

        for track_indices, detection_indices in components:
            pair_count = len(track_indices) * len(detection_indices)
            component_matrix_pair_count += pair_count
            peak_component_pair_count = max(peak_component_pair_count, pair_count)
            if len(track_indices) == 1 and len(detection_indices) == 1:
                rows = (0,)
                columns = (0,)
            else:
                local_costs = np.full(
                    (len(track_indices), len(detection_indices)),
                    self.large_cost,
                    dtype=float,
                )
                for local_row, track_index in enumerate(track_indices):
                    for local_column, detection_index in enumerate(
                        detection_indices
                    ):
                        edge = edges.get((track_index, detection_index))
                        if edge is not None:
                            local_costs[local_row, local_column] = edge.cost
                rows, columns = linear_sum_assignment(local_costs)
            for local_row, local_column in zip(rows, columns, strict=True):
                track_index = track_indices[int(local_row)]
                detection_index = detection_indices[int(local_column)]
                edge = edges.get((track_index, detection_index))
                if edge is None or edge.cost >= self.large_cost:
                    continue
                matched_pairs.append(
                    MatchedPair(
                        track_id=track_list[track_index].global_track_id,
                        detection_id=detection_list[detection_index].detection_id,
                        cost=edge.cost,
                        probability=1.0,
                    )
                )
                pair_key = (
                    track_list[track_index].global_track_id,
                    detection_list[detection_index].detection_id,
                )
                matched_velocity_nis[pair_key] = (
                    edge.velocity_mahalanobis_squared
                )
                matched_track_indices.add(track_index)
                matched_detection_indices.add(detection_index)
        assignment_seconds = perf_counter() - assignment_started

        matched_pairs.sort(key=lambda pair: pair.track_id)
        unmatched_track_ids = [
            track.global_track_id
            for index, track in enumerate(track_list)
            if index not in matched_track_indices
        ]
        unmatched_detection_ids = [
            detection.detection_id
            for index, detection in enumerate(detection_list)
            if index not in matched_detection_indices
        ]
        ambiguity_score, minimum_cost_margin = _ambiguity_from_sparse_edges(
            len(track_list), edges
        )
        track_overlap_rate = _overlap_rate(candidate_counts_by_track.values())
        detection_overlap_rate = _overlap_rate(
            candidate_counts_by_detection.values()
        )
        covariance_overlap_rate = 0.5 * (
            track_overlap_rate + detection_overlap_rate
        )
        unmatched_track_rate = _rate(len(unmatched_track_ids), len(track_list))
        unmatched_detection_rate = _rate(
            len(unmatched_detection_ids), len(detection_list)
        )
        risk_score = float(
            np.clip(
                0.45 * ambiguity_score
                + 0.25 * covariance_overlap_rate
                + 0.15 * unmatched_track_rate
                + 0.15 * unmatched_detection_rate,
                0.0,
                1.0,
            )
        )
        runtime_seconds = perf_counter() - started
        candidate_edge_count = len(edges)
        velocity_cost_gated_edge_count = sum(
            int(edge.velocity_cost_gated) for edge in edges.values()
        )
        binding_pre_update_rejection_count = sum(
            item.reason == "source_binding_pre_update"
            for item in rejected_pairs
        )
        candidate_density = _rate(candidate_edge_count, dense_pair_count)
        metadata: dict[str, Any] = {
            "state_order": list(STATE_ORDER_3D),
            "working_frame": "NED",
            "innovation_dimension": 3,
            "gate_metric": "3d_position_mahalanobis_squared",
            "gate_threshold": self.gate_threshold,
            "velocity_cost_gate_threshold": self.velocity_cost_gate_threshold,
            "velocity_cost_gated_edge_count": velocity_cost_gated_edge_count,
            "candidate_generation": "scipy.spatial.cKDTree",
            "solver": "componentwise_scipy.optimize.linear_sum_assignment",
            "gnn_meaning": "global_nearest_neighbor",
            "graph_neural_network_used": False,
            "unconditional_dense_matrix_allocated": False,
            "track_count": len(track_list),
            "detection_count": len(detection_list),
            "dense_pair_count": dense_pair_count,
            "spatial_query_pair_count": queried_pair_count,
            "spatial_pruned_pair_count": max(0, dense_pair_count - queried_pair_count),
            "candidate_edge_count": candidate_edge_count,
            "candidate_density": candidate_density,
            "candidate_pruning_ratio": 1.0 - candidate_density,
            "rejected_spatial_candidate_count": len(rejected_pairs),
            "binding_pre_update_rejection_count": (
                binding_pre_update_rejection_count
            ),
            "source_binding_mode": "authoritative_pre_update_hard_mask",
            "component_count": len(components),
            "component_matrix_pair_count": component_matrix_pair_count,
            "peak_component_pair_count": peak_component_pair_count,
            "candidate_counts_by_track": candidate_counts_by_track,
            "candidate_counts_by_detection": candidate_counts_by_detection,
            "query_radius_by_track": query_radius_by_track,
            "track_candidate_overlap_rate": track_overlap_rate,
            "detection_candidate_overlap_rate": detection_overlap_rate,
            "minimum_cost_margin": minimum_cost_margin,
            "unmatched_track_rate": unmatched_track_rate,
            "unmatched_detection_rate": unmatched_detection_rate,
            "risk_score": risk_score,
            "risk_level": _risk_level(risk_score),
            "index_build_seconds": index_seconds,
            "candidate_generation_seconds": candidate_seconds,
            "assignment_seconds": assignment_seconds,
            "association_runtime_seconds": runtime_seconds,
            "id_switch_count": None,
            "id_switch_count_available": False,
            "id_switch_count_reason": "offline_truth_evaluator_required",
            "track_continuity": None,
            "track_continuity_available": False,
            "track_continuity_reason": "offline_truth_evaluator_required",
            "identity_continuity": None,
            "coverage_continuity": None,
            "continuity_available": False,
            "truth_metrics_available": False,
            "truth_metrics_reason": "offline_truth_evaluator_required",
        }
        risk_summary = AssociationRiskSummary(
            timestamp=timestamp,
            source_node_id=_single_source_node(detection_list),
            link_type="scalable_3d_sparse",
            duplicate_track_risk=detection_overlap_rate,
            association_ambiguity=ambiguity_score,
            covariance_overlap_rate=covariance_overlap_rate,
            truth_metrics_available=False,
            continuity_available=False,
            metadata={
                "risk_score": risk_score,
                "risk_level": _risk_level(risk_score),
                "candidate_edge_count": candidate_edge_count,
                "dense_pair_count": dense_pair_count,
                "candidate_density": candidate_density,
                "unmatched_track_rate": unmatched_track_rate,
                "unmatched_detection_rate": unmatched_detection_rate,
                "graph_neural_network_used": False,
            },
        )
        return _SparseAssociationResult(
            timestamp=timestamp,
            matched_pairs=matched_pairs,
            unmatched_track_ids=unmatched_track_ids,
            unmatched_detection_ids=unmatched_detection_ids,
            ambiguity_score=ambiguity_score,
            associator_type=type(self).__name__,
            rejected_pairs=rejected_pairs,
            cost_matrix=None,
            distance_matrix=None,
            metadata=metadata,
            source_node_id=risk_summary.source_node_id,
            link_type=risk_summary.link_type,
            risk_summary=risk_summary,
            matched_velocity_nis=matched_velocity_nis,
        )

    def _conservative_query_radius(
        self,
        track: GlobalTrack3D,
        maximum_detection_variance: float,
    ) -> float:
        track_variance = float(np.linalg.eigvalsh(track.covariance[:3, :3])[-1])
        covariance_bound = max(0.0, track_variance + maximum_detection_variance)
        return max(
            self.minimum_query_radius_m,
            sqrt(self.gate_threshold * covariance_bound),
        )

    def _conservative_query_radii(
        self,
        tracks: list[GlobalTrack3D],
        maximum_detection_variance: float,
    ) -> np.ndarray:
        position_covariances = np.asarray(
            [track.covariance[:3, :3] for track in tracks]
        )
        track_variances = np.linalg.eigvalsh(position_covariances)[:, -1]
        return np.asarray(
            [
                max(
                    self.minimum_query_radius_m,
                    sqrt(
                        self.gate_threshold
                        * max(
                            0.0,
                            float(track_variance)
                            + maximum_detection_variance,
                        )
                    ),
                )
                for track_variance in track_variances
            ],
            dtype=float,
        )

    @staticmethod
    def _validate_epoch(
        tracks: list[GlobalTrack3D],
        detections: list[Detection3D],
        timestamp: float,
    ) -> None:
        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("association timestamp must be finite and non-negative")
        for track in tracks:
            if abs(track.timestamp - timestamp) > 1.0e-9:
                raise ValueError("tracks must be predicted to the association timestamp")
        for detection in detections:
            if abs(detection.measurement_timestamp - timestamp) > 1.0e-9:
                raise ValueError(
                    "detections in one sparse association scan must share the epoch"
                )


@dataclass(slots=True)
class Scalable3DTracker:
    """Truth-free six-state tracker that owns canonical ``global_track_id``."""

    associator: Sparse3DGNNHungarianAssociator = field(
        default_factory=Sparse3DGNNHungarianAssociator
    )
    process_noise_acceleration: float = 1.0
    initial_velocity_variance: float = 25.0
    correlated_state_ci_track_weight: float = 0.5
    velocity_innovation_gate_threshold: float = CHI2_GATE_3D_99_PERCENT
    confirmation_hits: int = 2
    engageable_hits: int = 4
    lost_miss_threshold: int = 2
    drop_miss_threshold: int = 5
    tentative_drop_miss_threshold: int = 2
    engageable_position_covariance_trace: float = 30.0
    duplicate_coalescence_position_gate_threshold: float = (
        CHI2_GATE_3D_99_PERCENT
    )
    duplicate_coalescence_velocity_gate_threshold: float = (
        CHI2_GATE_3D_99_PERCENT
    )
    observation_timestamp_tolerance_s: float = 1.0e-6
    observation_claim_config: ObservationClaimLedgerConfig = field(
        default_factory=ObservationClaimLedgerConfig
    )
    replay_coast_config: ReplayCoastConfig = field(
        default_factory=ReplayCoastConfig
    )
    ambiguity_hold_config: AmbiguityHoldLeaseConfig = field(
        default_factory=AmbiguityHoldLeaseConfig
    )
    identity_commitment_recovery_config: IdentityCommitmentRecoveryConfig = (
        field(default_factory=IdentityCommitmentRecoveryConfig)
    )
    create_tracks_from_unmatched_detections: bool = True
    track_history_limit: int = 32
    frame_log_limit: int = 256
    global_track_id_prefix: str = "GT3D-"
    tracks: dict[str, GlobalTrack3D] = field(default_factory=dict, init=False)
    _next_track_number: int = field(default=1, init=False)
    _last_timestamp: float | None = field(default=None, init=False)
    _source_bindings: dict[str, str] = field(default_factory=dict, init=False)
    _observation_claims: dict[str, _ObservationClaim] = field(
        default_factory=dict, init=False
    )
    _track_observation_keys: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set), init=False
    )
    _observation_claim_eviction_heap: list[tuple[float, str]] = field(
        default_factory=list, init=False
    )
    _frame_logs: deque[dict[str, Any]] = field(init=False)
    _runtime_seconds: deque[float] = field(init=False)
    _frame_count: int = field(default=0, init=False)
    _birth_count: int = field(default=0, init=False)
    _lost_count: int = field(default=0, init=False)
    _drop_count: int = field(default=0, init=False)
    _total_candidate_edges: int = field(default=0, init=False)
    _total_dense_pairs: int = field(default=0, init=False)
    _state_update_mode_counts: Counter[str] = field(
        default_factory=Counter, init=False
    )
    _velocity_innovation_gate_count: int = field(default=0, init=False)
    _replay_quarantine_count: int = field(default=0, init=False)
    _observation_timestamp_conflict_count: int = field(default=0, init=False)
    _observation_measurement_too_old_count: int = field(default=0, init=False)
    _observation_claim_overflow_count: int = field(default=0, init=False)
    _observation_claim_evicted_count: int = field(default=0, init=False)
    _observation_claim_peak_count: int = field(default=0, init=False)
    _observation_claim_undated_count: int = field(default=0, init=False)
    _observation_claim_status_counts: Counter[str] = field(
        default_factory=Counter,
        init=False,
    )
    _track_observation_key_count: int = field(default=0, init=False)
    _observation_rejection_reason_counts: Counter[str] = field(
        default_factory=Counter, init=False
    )
    _replay_coast_count: int = field(default=0, init=False)
    _replay_coast_reason_counts: Counter[str] = field(
        default_factory=Counter, init=False
    )
    _observation_claim_safe_watermark: float | None = field(
        default=None, init=False
    )
    _observation_admission_watermark: float | None = field(
        default=None, init=False
    )
    _duplicate_coalescence_count: int = field(default=0, init=False)
    _tentative_stale_drop_count: int = field(default=0, init=False)
    _latest_risk_summary: AssociationRiskSummary | None = field(
        default=None, init=False
    )
    _ambiguity_leases: dict[str, _AmbiguityLease] = field(
        default_factory=dict,
        init=False,
    )
    _ambiguity_component_generations: dict[str, int] = field(
        default_factory=dict,
        init=False,
    )
    _ambiguity_component_hard_deadlines: dict[str, float] = field(
        default_factory=dict,
        init=False,
    )
    _ambiguity_component_history_order: deque[str] = field(
        init=False,
    )
    _ambiguity_evidence_history: set[str] = field(
        default_factory=set,
        init=False,
    )
    _ambiguity_evidence_history_order: deque[str] = field(init=False)
    _ambiguity_publisher_current_epochs: dict[str, str] = field(
        default_factory=dict,
        init=False,
    )
    _ambiguity_publisher_retired_epochs: set[tuple[str, str]] = field(
        default_factory=set,
        init=False,
    )
    _ambiguity_retired_epoch_order: deque[tuple[str, str]] = field(
        init=False,
    )
    _ambiguity_component_event_counts: Counter[str] = field(
        default_factory=Counter,
        init=False,
    )
    _ambiguity_prevented_counts: Counter[str] = field(
        default_factory=Counter,
        init=False,
    )
    _binding_pre_update_rejection_count: int = field(
        default=0,
        init=False,
    )
    _identity_commitments: dict[str, IdentityEvidenceCommitment] = field(
        default_factory=dict,
        init=False,
    )
    _identity_commitment_transition_counts: Counter[str] = field(
        default_factory=Counter,
        init=False,
    )
    _identity_commitment_blocked_recovery_counts: Counter[str] = field(
        default_factory=Counter,
        init=False,
    )
    _identity_recovery_blockers: dict[
        str,
        _IdentityRecoveryBlockers,
    ] = field(default_factory=dict, init=False)
    _identity_recovery_blocked_key_count: int = field(default=0, init=False)
    _identity_recovery_blocked_key_peak_count: int = field(
        default=0,
        init=False,
    )
    _identity_recovery_capacity_overflow_count: int = field(
        default=0,
        init=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "process_noise_acceleration",
            "initial_velocity_variance",
            "engageable_position_covariance_trace",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not 0.0 < float(self.correlated_state_ci_track_weight) < 1.0:
            raise ValueError(
                "correlated_state_ci_track_weight must be strictly within (0, 1)"
            )
        if (
            not np.isfinite(self.velocity_innovation_gate_threshold)
            or self.velocity_innovation_gate_threshold <= 0.0
        ):
            raise ValueError(
                "velocity_innovation_gate_threshold must be positive and finite"
            )
        for name in (
            "duplicate_coalescence_position_gate_threshold",
            "duplicate_coalescence_velocity_gate_threshold",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        if (
            not np.isfinite(self.observation_timestamp_tolerance_s)
            or self.observation_timestamp_tolerance_s < 0.0
        ):
            raise ValueError(
                "observation_timestamp_tolerance_s must be finite and non-negative"
            )
        if not isinstance(
            self.observation_claim_config,
            ObservationClaimLedgerConfig,
        ):
            raise TypeError(
                "observation_claim_config must be ObservationClaimLedgerConfig"
            )
        if not isinstance(self.replay_coast_config, ReplayCoastConfig):
            raise TypeError("replay_coast_config must be ReplayCoastConfig")
        if not isinstance(self.ambiguity_hold_config, AmbiguityHoldLeaseConfig):
            raise TypeError(
                "ambiguity_hold_config must be AmbiguityHoldLeaseConfig"
            )
        if not isinstance(
            self.identity_commitment_recovery_config,
            IdentityCommitmentRecoveryConfig,
        ):
            raise TypeError(
                "identity_commitment_recovery_config must be "
                "IdentityCommitmentRecoveryConfig"
            )
        for name in (
            "confirmation_hits",
            "engageable_hits",
            "lost_miss_threshold",
            "drop_miss_threshold",
            "tentative_drop_miss_threshold",
            "track_history_limit",
            "frame_log_limit",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.drop_miss_threshold < self.lost_miss_threshold:
            raise ValueError("drop_miss_threshold cannot be below lost_miss_threshold")
        self.global_track_id_prefix = str(self.global_track_id_prefix)
        if not self.global_track_id_prefix:
            raise ValueError("global_track_id_prefix must be non-empty")
        self._frame_logs = deque(maxlen=self.frame_log_limit)
        self._runtime_seconds = deque(maxlen=self.frame_log_limit)
        self._ambiguity_component_history_order = deque()
        self._ambiguity_evidence_history_order = deque()
        self._ambiguity_retired_epoch_order = deque()

    def active_tracks(self) -> list[GlobalTrack3D]:
        return sorted(
            (
                track
                for track in self.tracks.values()
                if track.lifecycle_state != TrackLifecycleState.DROPPED
            ),
            key=lambda item: item.global_track_id,
        )

    @property
    def state_timestamp(self) -> float | None:
        """Latest common scan epoch consumed by the monotonic tracker."""

        return self._last_timestamp

    def identity_commitments(self) -> dict[str, IdentityEvidenceCommitment]:
        """Return current truth-free identity commitment by active D2 track."""

        active_ids = {
            track.global_track_id for track in self.active_tracks()
        }
        return {
            track_id: self._identity_commitments[track_id]
            for track_id in sorted(active_ids)
            if track_id in self._identity_commitments
        }

    def step(
        self,
        detections: Iterable[Detection3D],
        timestamp: float | None = None,
        *,
        ambiguity_components: Iterable[
            AmbiguityComponent3D | Mapping[str, Any]
        ] = (),
    ) -> AssociationResult:
        """Process one common-epoch scan; no truth labels are accepted here."""

        started = perf_counter()
        detection_list = list(detections)
        if not all(isinstance(item, Detection3D) for item in detection_list):
            raise TypeError("Scalable3DTracker accepts only Detection3D online inputs")
        for detection in detection_list:
            assert_online_metadata_truth_free(detection.metadata)
        detection_ids = [item.detection_id for item in detection_list]
        if len(set(detection_ids)) != len(detection_ids):
            raise ValueError("detection_id values must be unique within a scan")
        timestamp = _scan_timestamp(detection_list, timestamp)
        if self._last_timestamp is not None and timestamp + 1.0e-12 < self._last_timestamp:
            raise ValueError("out-of-sequence scans require an explicit OOSM adapter")

        claim_eviction_events = self._advance_observation_claim_watermark(timestamp)
        ambiguity_diagnostics = self._process_ambiguity_components(
            ambiguity_components,
            timestamp,
        )
        held_track_ids = set(ambiguity_diagnostics["hold_track_ids"])
        held_source_keys = set(ambiguity_diagnostics["hold_source_keys"])
        self._reconcile_identity_commitment_holds(
            timestamp,
            ambiguity_diagnostics["component_events"],
        )
        (
            association_input_detections,
            held_member_detection_events,
        ) = self._partition_ambiguity_member_detections(
            detection_list,
            held_source_keys=held_source_keys,
            held_track_ids=held_track_ids,
            timestamp=timestamp,
        )
        for event in held_member_detection_events:
            counter_name = str(event["prevented_action"])
            ambiguity_diagnostics["prevented_counts"][counter_name] += 1
            self._ambiguity_prevented_counts[counter_name] += 1

        (
            fresh_detections,
            replay_quarantine_events,
            observation_evidence_by_detection,
        ) = self._partition_observation_freshness(
            association_input_detections,
            timestamp,
        )
        frame_rejection_reason_counts = Counter(
            str(item["reason"]) for item in replay_quarantine_events
        )

        self.predict_all(timestamp)
        associable_tracks = [
            track
            for track in self.active_tracks()
            if track.global_track_id not in held_track_ids
        ]
        authoritative_bindings = self._active_source_bindings()
        result = self.associator.associate(
            associable_tracks,
            fresh_detections,
            timestamp,
            authoritative_source_bindings=authoritative_bindings,
        )
        frame_binding_pre_update_rejections = int(
            result.metadata.get("binding_pre_update_rejection_count", 0)
        )
        self._binding_pre_update_rejection_count += (
            frame_binding_pre_update_rejections
        )
        eligible_replay_coasts = self._eligible_replay_coasts(
            replay_quarantine_events,
            timestamp,
        )
        detections_by_id = {item.detection_id: item for item in fresh_detections}
        detection_to_track: dict[str, str] = {}
        source_binding_conflicts: list[dict[str, str]] = []
        state_update_diagnostics: list[dict[str, Any]] = []
        matched_velocity_nis = (
            result.matched_velocity_nis
            if isinstance(result, _SparseAssociationResult)
            else {}
        )
        identity_suppressed_association_reasons: dict[str, str] = {}
        accepted_pairs: list[MatchedPair] = []
        suppressed_track_ids: set[str] = set()
        suppressed_detection_ids: set[str] = set()
        for pair in result.matched_pairs:
            track = self.tracks[pair.track_id]
            detection = detections_by_id[pair.detection_id]
            evidence = observation_evidence_by_detection.get(
                detection.detection_id
            )
            block_reason = self._identity_observation_acceptance_block_reason(
                track,
                detection,
                evidence,
                tracker_frame_timestamp=timestamp,
            )
            if block_reason is None:
                accepted_pairs.append(pair)
                continue
            suppressed_track_ids.add(pair.track_id)
            suppressed_detection_ids.add(pair.detection_id)
            identity_suppressed_association_reasons[
                pair.detection_id
            ] = block_reason
            self._record_identity_recovery_block(
                track,
                timestamp,
                block_reason,
            )
        if suppressed_track_ids or suppressed_detection_ids:
            result.matched_pairs = accepted_pairs
            result.unmatched_track_ids = sorted(
                set(result.unmatched_track_ids) | suppressed_track_ids
            )
            result.unmatched_detection_ids = sorted(
                set(result.unmatched_detection_ids)
                | suppressed_detection_ids
            )

        for pair in result.matched_pairs:
            track = self.tracks[pair.track_id]
            detection = detections_by_id[pair.detection_id]
            state_update_diagnostics.append(
                self._update_track(
                    track,
                    detection,
                    precomputed_velocity_nis=matched_velocity_nis.get(
                        (pair.track_id, pair.detection_id),
                        _NO_PRECOMPUTED_NIS,
                    ),
                )
            )
            detection_to_track[detection.detection_id] = track.global_track_id
            conflict = self._bind_source(track, detection)
            if conflict is not None:
                source_binding_conflicts.append(conflict)
            self._advance_after_hit(track)
            evidence = observation_evidence_by_detection.get(
                detection.detection_id
            )
            if evidence is not None:
                self._recover_identity_commitment(
                    track,
                    detection,
                    evidence,
                    association_state="matched",
                    tracker_frame_timestamp=timestamp,
                )

        replay_coast_events: list[dict[str, Any]] = []
        missed_track_ids: list[str] = []
        if held_track_ids:
            ambiguity_diagnostics["prevented_counts"]["miss"] += len(
                held_track_ids
            )
            self._ambiguity_prevented_counts["miss"] += len(held_track_ids)
        for track_id in result.unmatched_track_ids:
            track = self.tracks.get(track_id)
            if track is not None and track.lifecycle_state != TrackLifecycleState.DROPPED:
                coast_event = eligible_replay_coasts.get(track_id)
                if coast_event is not None:
                    replay_coast_events.append(coast_event)
                    continue
                self._mark_missed(track)
                missed_track_ids.append(track_id)

        frame_replay_coast_reason_counts = Counter(
            str(item["reason"]) for item in replay_coast_events
        )
        self._replay_coast_count += len(replay_coast_events)
        self._replay_coast_reason_counts.update(
            frame_replay_coast_reason_counts
        )

        created_track_ids_by_detection: dict[str, str] = {}
        binding_suppressed_births: dict[str, str] = {}
        identity_suppressed_births: dict[str, str] = {}
        if self.create_tracks_from_unmatched_detections:
            for detection_id in result.unmatched_detection_ids:
                detection = detections_by_id[detection_id]
                evidence = observation_evidence_by_detection.get(detection_id)
                if detection_id in identity_suppressed_association_reasons:
                    identity_suppressed_births[detection_id] = (
                        identity_suppressed_association_reasons[detection_id]
                    )
                    continue
                birth_block_reason = (
                    self._first_accepted_original_evidence_block_reason(
                        detection,
                        evidence,
                    )
                )
                if birth_block_reason is not None:
                    identity_suppressed_births[
                        detection_id
                    ] = birth_block_reason
                    self._identity_commitment_blocked_recovery_counts[
                        birth_block_reason
                    ] += 1
                    continue
                bound_track_id = (
                    None
                    if detection.source_key is None
                    else authoritative_bindings.get(detection.source_key)
                )
                if bound_track_id is not None:
                    binding_suppressed_births[detection_id] = bound_track_id
                    continue
                track = self._create_track(detection)
                detection_to_track[detection_id] = track.global_track_id
                created_track_ids_by_detection[detection_id] = track.global_track_id
                conflict = self._bind_source(track, detection)
                if conflict is not None:
                    source_binding_conflicts.append(conflict)

        for detection_id, track_id in detection_to_track.items():
            evidence = observation_evidence_by_detection.get(detection_id)
            if evidence is not None:
                self._assign_observation_claim(evidence, track_id)

        updated_track_ids = set(detection_to_track.values())
        coalescence_events, track_aliases = self._coalesce_duplicate_tracks(
            timestamp,
            updated_track_ids=updated_track_ids,
            protected_track_ids=held_track_ids,
        )
        suppressed_births_by_detection: dict[str, str] = {}
        if track_aliases:
            def resolved_track_id(track_id: str) -> str:
                while track_id in track_aliases:
                    track_id = track_aliases[track_id]
                return track_id

            detection_to_track = {
                detection_id: resolved_track_id(track_id)
                for detection_id, track_id in detection_to_track.items()
            }
            for detection_id, track_id in tuple(
                created_track_ids_by_detection.items()
            ):
                survivor_id = track_aliases.get(track_id)
                if survivor_id is not None:
                    suppressed_births_by_detection[detection_id] = track_id
                    created_track_ids_by_detection.pop(detection_id)
            self._merge_identity_commitments_for_aliases(
                track_aliases,
                timestamp,
            )

        self._refresh_track_quality(result, set(created_track_ids_by_detection.values()))
        frame_identity_commitments = self._identity_commitment_frame_payloads(
            timestamp,
            created_track_ids=set(created_track_ids_by_detection.values()),
            updated_track_ids=set(detection_to_track.values()),
        )
        update_mode_counts = Counter(
            str(item["mode"]) for item in state_update_diagnostics
        )
        velocity_gate_count = sum(
            int(bool(item["velocity_innovation_gated"]))
            for item in state_update_diagnostics
        )
        self._state_update_mode_counts.update(update_mode_counts)
        self._velocity_innovation_gate_count += velocity_gate_count
        tracker_runtime = perf_counter() - started
        observation_claim_ledger = self._observation_claim_ledger_summary()
        result.metadata.update(
            {
                "detection_to_track": dict(sorted(detection_to_track.items())),
                "input_detection_count": len(detection_list),
                "association_input_detection_count": len(
                    association_input_detections
                ),
                "ambiguity_held_member_detection_count": len(
                    held_member_detection_events
                ),
                "ambiguity_held_member_detection_events": (
                    held_member_detection_events
                ),
                "fresh_detection_count": len(fresh_detections),
                "observation_freshness_available_count": (
                    len(observation_evidence_by_detection)
                    + len(replay_quarantine_events)
                ),
                "observation_freshness_unavailable_count": (
                    len(detection_list)
                    - len(observation_evidence_by_detection)
                    - len(replay_quarantine_events)
                ),
                "replay_quarantined_detection_count": len(
                    replay_quarantine_events
                ),
                "replay_quarantine_events": replay_quarantine_events,
                "replay_coast_count": len(replay_coast_events),
                "replay_coast_events": replay_coast_events,
                "replay_coast_track_ids": sorted(
                    item["global_track_id"] for item in replay_coast_events
                ),
                "replay_coast_reason_counts": dict(
                    sorted(frame_replay_coast_reason_counts.items())
                ),
                "replay_coast_reason_counts_cumulative": dict(
                    sorted(self._replay_coast_reason_counts.items())
                ),
                "replay_coast_config": self.replay_coast_config.to_dict(),
                "missed_track_ids": sorted(missed_track_ids),
                "observation_rejection_reason_counts": dict(
                    sorted(frame_rejection_reason_counts.items())
                ),
                "observation_rejection_reason_counts_cumulative": dict(
                    sorted(self._observation_rejection_reason_counts.items())
                ),
                "observation_claim_ledger": observation_claim_ledger,
                "observation_claim_eviction_count": len(claim_eviction_events),
                "observation_claim_eviction_events": claim_eviction_events,
                "created_track_ids_by_detection": dict(
                    sorted(created_track_ids_by_detection.items())
                ),
                "binding_suppressed_births": dict(
                    sorted(binding_suppressed_births.items())
                ),
                "identity_commitment_suppressed_births": dict(
                    sorted(identity_suppressed_births.items())
                ),
                "identity_commitment_suppressed_association_count": len(
                    identity_suppressed_association_reasons
                ),
                "identity_commitment_suppressed_association_reason_counts": dict(
                    sorted(
                        Counter(
                            identity_suppressed_association_reasons.values()
                        ).items()
                    )
                ),
                "suppressed_births_by_detection": dict(
                    sorted(suppressed_births_by_detection.items())
                ),
                "duplicate_coalescence_count": len(coalescence_events),
                "duplicate_coalescence_events": coalescence_events,
                "duplicate_survivor_policy": (
                    "lifecycle_maturity_then_oldest_creation_then_hits_then_id"
                ),
                "source_track_bindings": dict(sorted(self._source_bindings.items())),
                "source_binding_conflicts": source_binding_conflicts,
                "binding_pre_update_rejection_count": (
                    frame_binding_pre_update_rejections
                ),
                "binding_pre_update_rejection_count_cumulative": (
                    self._binding_pre_update_rejection_count
                ),
                "ambiguity_hold": self._finalize_ambiguity_diagnostics(
                    ambiguity_diagnostics
                ),
                "identity_commitment_schema_version": (
                    D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION
                ),
                "identity_commitment_policy_version": (
                    D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION
                ),
                "identity_commitment_by_track": frame_identity_commitments,
                "identity_commitment_state_counts": dict(
                    sorted(
                        Counter(
                            item["identity_commitment_state"]
                            for item in frame_identity_commitments.values()
                        ).items()
                    )
                ),
                "identity_commitment_transition_counts_cumulative": dict(
                    sorted(self._identity_commitment_transition_counts.items())
                ),
                "identity_commitment_blocked_recovery_counts_cumulative": dict(
                    sorted(
                        self._identity_commitment_blocked_recovery_counts.items()
                    )
                ),
                "identity_commitment_recovery_config": (
                    self.identity_commitment_recovery_config.to_dict()
                ),
                "identity_commitment_recovery_barrier": (
                    self._identity_recovery_barrier_summary()
                ),
                "active_track_count": len(self.active_tracks()),
                "tracker_runtime_seconds": tracker_runtime,
                "track_history_limit": self.track_history_limit,
                "frame_log_limit": self.frame_log_limit,
                "tentative_drop_miss_threshold": (
                    self.tentative_drop_miss_threshold
                ),
                "global_track_id_owner": "D2_center",
                "state_update_mode_counts": dict(sorted(update_mode_counts.items())),
                "velocity_innovation_gate_count": velocity_gate_count,
                "velocity_innovation_nis_summary": _finite_value_summary(
                    item["velocity_innovation_nis"]
                    for item in state_update_diagnostics
                ),
                "velocity_covariance_inflation_summary": _finite_value_summary(
                    item["velocity_covariance_inflation"]
                    for item in state_update_diagnostics
                ),
                "input_velocity_speed_summary_mps": _finite_value_summary(
                    float(np.linalg.norm(item.velocity_ned))
                    for item in detection_list
                    if item.velocity_ned is not None
                ),
                "active_track_speed_summary_mps": _finite_value_summary(
                    float(np.linalg.norm(item.velocity_ned))
                    for item in self.active_tracks()
                ),
                "active_track_velocity_covariance_trace_summary": (
                    _finite_value_summary(
                        float(np.trace(item.covariance[3:, 3:]))
                        for item in self.active_tracks()
                    )
                ),
                "id_switch_count": None,
                "id_switch_count_available": False,
                "track_continuity": None,
                "track_continuity_available": False,
                "track_continuity_reason": "offline_truth_evaluator_required",
                "identity_continuity": None,
                "coverage_continuity": None,
                "continuity_available": False,
                "truth_metrics_available": False,
                "truth_metrics_reason": "online_path_is_truth_free",
            }
        )
        if result.risk_summary is not None:
            result.risk_summary.source_binding_conflict_count = len(
                source_binding_conflicts
            )
            result.risk_summary.metadata.update(
                {
                    "active_track_count": len(self.active_tracks()),
                    "created_track_count": len(created_track_ids_by_detection),
                    "replay_quarantined_detection_count": len(
                        replay_quarantine_events
                    ),
                    "replay_coast_count": len(replay_coast_events),
                    "replay_coast_reason_counts": dict(
                        sorted(frame_replay_coast_reason_counts.items())
                    ),
                    "replay_coast_config": self.replay_coast_config.to_dict(),
                    "missed_track_count": len(missed_track_ids),
                    "observation_rejection_reason_counts": dict(
                        sorted(frame_rejection_reason_counts.items())
                    ),
                    "observation_claim_ledger": dict(observation_claim_ledger),
                    "duplicate_coalescence_count": len(coalescence_events),
                    "source_binding_conflict_count": len(source_binding_conflicts),
                    "binding_pre_update_rejection_count": (
                        frame_binding_pre_update_rejections
                    ),
                    "ambiguity_hold": self._finalize_ambiguity_diagnostics(
                        ambiguity_diagnostics
                    ),
                    "global_track_id_owner": "D2_center",
                    "state_update_mode_counts": dict(
                        sorted(update_mode_counts.items())
                    ),
                    "velocity_innovation_gate_count": velocity_gate_count,
                    "id_switch_count": None,
                    "track_continuity": None,
                    "identity_continuity": None,
                    "coverage_continuity": None,
                    "continuity_available": False,
                }
            )
            if ambiguity_diagnostics["active_component_count"]:
                result.risk_summary.association_ambiguity = max(
                    result.risk_summary.association_ambiguity,
                    1.0,
                )
                result.risk_summary.metadata["risk_level"] = "high"
                result.risk_summary.metadata["risk_score"] = max(
                    0.85,
                    float(
                        result.risk_summary.metadata.get(
                            "risk_score",
                            0.0,
                        )
                    ),
                )
                result.risk_summary.metadata["risk_reason"] = (
                    "active_structural_ambiguity_hold"
                )
        if ambiguity_diagnostics["active_component_count"]:
            ambiguity_score_before_hold = float(result.ambiguity_score)
            result.ambiguity_score = max(result.ambiguity_score, 1.0)
            result.metadata["ambiguity_score_before_hold_override"] = float(
                ambiguity_score_before_hold
            )
            result.metadata["risk_score"] = max(
                0.85,
                float(result.metadata.get("risk_score", 0.0)),
            )
            result.metadata["risk_level"] = "high"
            result.metadata["risk_reason"] = (
                "active_structural_ambiguity_hold"
            )
        self._frame_count += 1
        self._birth_count += len(created_track_ids_by_detection)
        self._total_candidate_edges += int(result.metadata["candidate_edge_count"])
        self._total_dense_pairs += int(result.metadata["dense_pair_count"])
        self._runtime_seconds.append(tracker_runtime)
        self._latest_risk_summary = result.risk_summary
        self._frame_logs.append(
            {
                "timestamp": timestamp,
                "matched_count": len(result.matched_pairs),
                "created_track_count": len(created_track_ids_by_detection),
                "replay_quarantined_detection_count": len(
                    replay_quarantine_events
                ),
                "replay_coast_count": len(replay_coast_events),
                "replay_coast_reason_counts": dict(
                    sorted(frame_replay_coast_reason_counts.items())
                ),
                "missed_track_count": len(missed_track_ids),
                "observation_rejection_reason_counts": dict(
                    sorted(frame_rejection_reason_counts.items())
                ),
                "observation_claim_eviction_count": len(claim_eviction_events),
                "duplicate_coalescence_count": len(coalescence_events),
                "unmatched_track_count": len(result.unmatched_track_ids),
                "candidate_edge_count": int(result.metadata["candidate_edge_count"]),
                "dense_pair_count": int(result.metadata["dense_pair_count"]),
                "risk_score": float(result.metadata["risk_score"]),
                "ambiguity_hold_track_count": len(held_track_ids),
                "ambiguity_hold_component_count": int(
                    ambiguity_diagnostics["active_component_count"]
                ),
                "ambiguity_reserved_evidence_count": int(
                    ambiguity_diagnostics["reserved_evidence_count"]
                ),
                "identity_commitment_state_counts": dict(
                    sorted(
                        Counter(
                            item["identity_commitment_state"]
                            for item in frame_identity_commitments.values()
                        ).items()
                    )
                ),
                "binding_pre_update_rejection_count": (
                    frame_binding_pre_update_rejections
                ),
                "state_update_mode_counts": dict(sorted(update_mode_counts.items())),
                "velocity_innovation_gate_count": velocity_gate_count,
                "tracker_runtime_seconds": tracker_runtime,
            }
        )
        self._last_timestamp = timestamp
        return result

    def predict_all(self, timestamp: float) -> None:
        models_by_dt: dict[float, tuple[np.ndarray, np.ndarray]] = {}
        for track in self.active_tracks():
            dt = max(float(timestamp) - track.timestamp, 0.0)
            if dt <= 0.0:
                continue
            model = models_by_dt.get(dt)
            if model is None:
                model = _cv_transition_and_process_noise(
                    dt,
                    self.process_noise_acceleration,
                )
                models_by_dt[dt] = model
            transition, process = model
            track.state = transition @ track.state
            track.covariance = (
                transition @ track.covariance @ transition.T + process
            )
            track.ensure_covariance_consistency()
            track.timestamp = float(timestamp)
            track.age += 1

    def summary(self) -> dict[str, Any]:
        runtimes = np.asarray(self._runtime_seconds, dtype=float)
        candidate_density = _rate(
            self._total_candidate_edges,
            self._total_dense_pairs,
        )
        return {
            "frame_count": self._frame_count,
            "active_track_count": len(self.active_tracks()),
            "total_track_count": len(self.tracks),
            "birth_count": self._birth_count,
            "lost_count": self._lost_count,
            "drop_count": self._drop_count,
            "tentative_stale_drop_count": self._tentative_stale_drop_count,
            "replay_quarantine_count": self._replay_quarantine_count,
            "replay_coast_count": self._replay_coast_count,
            "replay_coast_reason_counts": dict(
                sorted(self._replay_coast_reason_counts.items())
            ),
            "replay_coast_config": self.replay_coast_config.to_dict(),
            "ambiguity_hold_config": self.ambiguity_hold_config.to_dict(),
            "ambiguity_hold_active_component_count": len(
                self._ambiguity_leases
            ),
            "ambiguity_hold_active_track_count": len(
                self._active_ambiguity_hold_track_ids()
            ),
            "ambiguity_hold_reserved_evidence_count": (
                self._observation_claim_status_counts.get(
                    "reserved_ambiguous",
                    0,
                )
            ),
            "ambiguity_hold_component_event_counts": dict(
                sorted(self._ambiguity_component_event_counts.items())
            ),
            "ambiguity_hold_prevented_counts": dict(
                sorted(self._ambiguity_prevented_counts.items())
            ),
            "binding_pre_update_rejection_count": (
                self._binding_pre_update_rejection_count
            ),
            "ambiguity_hold_resolution_mode": "lease_expiry_only_v1",
            "ambiguity_hold_online_truth_used": False,
            "identity_commitment_schema_version": (
                D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION
            ),
            "identity_commitment_policy_version": (
                D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION
            ),
            "identity_commitment_by_track": {
                track_id: item.to_dict()
                for track_id, item in self.identity_commitments().items()
            },
            "identity_commitment_state_counts": dict(
                sorted(
                    Counter(
                        item.identity_commitment_state.value
                        for item in self.identity_commitments().values()
                    ).items()
                )
            ),
            "identity_commitment_transition_counts": dict(
                sorted(self._identity_commitment_transition_counts.items())
            ),
            "identity_commitment_blocked_recovery_counts": dict(
                sorted(
                    self._identity_commitment_blocked_recovery_counts.items()
                )
            ),
            "identity_commitment_recovery_config": (
                self.identity_commitment_recovery_config.to_dict()
            ),
            "identity_commitment_recovery_barrier": (
                self._identity_recovery_barrier_summary()
            ),
            "observation_timestamp_conflict_count": (
                self._observation_timestamp_conflict_count
            ),
            "observation_measurement_too_old_count": (
                self._observation_measurement_too_old_count
            ),
            "observation_claim_overflow_count": (
                self._observation_claim_overflow_count
            ),
            "observation_claim_count": len(self._observation_claims),
            "observation_claim_peak_count": self._observation_claim_peak_count,
            "observation_claim_evicted_count": self._observation_claim_evicted_count,
            "observation_rejection_reason_counts": dict(
                sorted(self._observation_rejection_reason_counts.items())
            ),
            "observation_claim_ledger": self._observation_claim_ledger_summary(),
            "duplicate_coalescence_count": self._duplicate_coalescence_count,
            "tentative_drop_miss_threshold": self.tentative_drop_miss_threshold,
            "duplicate_coalescence_position_gate_threshold": (
                self.duplicate_coalescence_position_gate_threshold
            ),
            "duplicate_coalescence_velocity_gate_threshold": (
                self.duplicate_coalescence_velocity_gate_threshold
            ),
            "duplicate_survivor_policy": (
                "lifecycle_maturity_then_oldest_creation_then_hits_then_id"
            ),
            "id_switch_count": None,
            "id_switch_count_available": False,
            "id_switch_count_reason": "offline_truth_evaluator_required",
            "track_continuity": None,
            "track_continuity_available": False,
            "track_continuity_reason": "offline_truth_evaluator_required",
            "identity_continuity": None,
            "coverage_continuity": None,
            "continuity_available": False,
            "truth_metrics_available": False,
            "truth_metrics_reason": "online_path_is_truth_free",
            "duplicate_assignment_count": 0,
            "global_track_id_owner": "D2_center",
            "state_order": list(STATE_ORDER_3D),
            "innovation_dimension": 3,
            "state_update_mode_counts": dict(
                sorted(self._state_update_mode_counts.items())
            ),
            "velocity_innovation_gate_count": (
                self._velocity_innovation_gate_count
            ),
            "active_track_speed_summary_mps": _finite_value_summary(
                float(np.linalg.norm(item.velocity_ned))
                for item in self.active_tracks()
            ),
            "active_track_velocity_covariance_trace_summary": (
                _finite_value_summary(
                    float(np.trace(item.covariance[3:, 3:]))
                    for item in self.active_tracks()
                )
            ),
            "candidate_edge_count": self._total_candidate_edges,
            "dense_pair_count": self._total_dense_pairs,
            "candidate_density": candidate_density,
            "candidate_pruning_ratio": 1.0 - candidate_density,
            "runtime_seconds": float(np.sum(runtimes)) if runtimes.size else 0.0,
            "mean_frame_runtime_seconds": (
                float(np.mean(runtimes)) if runtimes.size else 0.0
            ),
            "p95_frame_runtime_seconds": (
                float(np.percentile(runtimes, 95.0)) if runtimes.size else 0.0
            ),
            "risk_summary": (
                None
                if self._latest_risk_summary is None
                else self._latest_risk_summary.to_dict()
            ),
            "frame_logs": list(self._frame_logs),
            "frame_log_limit": self.frame_log_limit,
            "track_history_limit": self.track_history_limit,
        }

    def _register_identity_recovery_blockers(
        self,
        track_id: str,
        evidence_keys: Iterable[str],
        measurement_timestamp: float,
    ) -> None:
        """Persist hold evidence independently from the expiring claim ledger."""

        track = self.tracks.get(track_id)
        if track is None or track.lifecycle_state == TrackLifecycleState.DROPPED:
            return
        barrier = self._identity_recovery_blockers.get(track_id)
        if barrier is None:
            barrier = _IdentityRecoveryBlockers(
                recovery_not_before_measurement_timestamp=float(
                    measurement_timestamp
                )
            )
            self._identity_recovery_blockers[track_id] = barrier
        else:
            barrier.recovery_not_before_measurement_timestamp = max(
                barrier.recovery_not_before_measurement_timestamp,
                float(measurement_timestamp),
            )

        config = self.identity_commitment_recovery_config
        if not barrier.overflow:
            for evidence_key in sorted(set(evidence_keys)):
                if evidence_key in barrier.evidence_keys:
                    continue
                if (
                    len(barrier.evidence_keys)
                    >= config.max_blocked_keys_per_track
                    or self._identity_recovery_blocked_key_count
                    >= config.max_total_blocked_keys
                ):
                    barrier.overflow = True
                    self._identity_recovery_capacity_overflow_count += 1
                    break
                barrier.evidence_keys.add(evidence_key)
                self._identity_recovery_blocked_key_count += 1
        self._identity_recovery_blocked_key_peak_count = max(
            self._identity_recovery_blocked_key_peak_count,
            self._identity_recovery_blocked_key_count,
        )

    def _register_identity_recovery_lease(
        self,
        lease: _AmbiguityLease,
    ) -> None:
        lease.track_ids.update(
            self._bound_track_ids(lease.member_source_keys)
        )
        for track_id in sorted(lease.track_ids):
            self._register_identity_recovery_blockers(
                track_id,
                lease.observation_evidence_keys,
                lease.measurement_timestamp,
            )

    def _clear_identity_recovery_blockers(self, track_id: str) -> None:
        barrier = self._identity_recovery_blockers.pop(track_id, None)
        if barrier is None:
            return
        self._identity_recovery_blocked_key_count -= len(
            barrier.evidence_keys
        )
        if self._identity_recovery_blocked_key_count < 0:
            raise RuntimeError("identity recovery blocker count underflow")

    def _merge_identity_recovery_blockers(
        self,
        duplicate_id: str,
        survivor_id: str,
    ) -> None:
        duplicate = self._identity_recovery_blockers.get(duplicate_id)
        survivor = self._identity_recovery_blockers.get(survivor_id)
        if duplicate is None:
            return
        combined_keys = set(duplicate.evidence_keys)
        watermarks = [
            duplicate.recovery_not_before_measurement_timestamp
        ]
        overflow = duplicate.overflow
        if survivor is not None:
            combined_keys.update(survivor.evidence_keys)
            watermarks.append(
                survivor.recovery_not_before_measurement_timestamp
            )
            overflow = overflow or survivor.overflow
        self._clear_identity_recovery_blockers(duplicate_id)
        self._clear_identity_recovery_blockers(survivor_id)
        self._register_identity_recovery_blockers(
            survivor_id,
            combined_keys,
            max(watermarks),
        )
        merged = self._identity_recovery_blockers[survivor_id]
        if overflow and not merged.overflow:
            merged.overflow = True
            self._identity_recovery_capacity_overflow_count += 1

    def _identity_recovery_public_fields(
        self,
        track_id: str,
    ) -> dict[str, Any]:
        barrier = self._identity_recovery_blockers.get(track_id)
        if barrier is None:
            return {
                "recovery_blocker_count": 0,
                "recovery_not_before_measurement_timestamp": None,
                "recovery_blocker_overflow": False,
            }
        return {
            "recovery_blocker_count": len(barrier.evidence_keys),
            "recovery_not_before_measurement_timestamp": (
                barrier.recovery_not_before_measurement_timestamp
            ),
            "recovery_blocker_overflow": barrier.overflow,
        }

    def _identity_recovery_barrier_summary(self) -> dict[str, Any]:
        return {
            **self.identity_commitment_recovery_config.to_dict(),
            "active_track_count": len(self._identity_recovery_blockers),
            "stored_blocked_key_count": (
                self._identity_recovery_blocked_key_count
            ),
            "peak_stored_blocked_key_count": (
                self._identity_recovery_blocked_key_peak_count
            ),
            "overflow_track_count": sum(
                int(item.overflow)
                for item in self._identity_recovery_blockers.values()
            ),
            "capacity_overflow_count": (
                self._identity_recovery_capacity_overflow_count
            ),
            "blocked_keys_publicly_exposed": False,
            "online_truth_used": False,
        }

    def _identity_observation_acceptance_block_reason(
        self,
        track: GlobalTrack3D,
        detection: Detection3D,
        evidence: _ObservationEvidence | None,
        *,
        tracker_frame_timestamp: float,
    ) -> str | None:
        previous = self._identity_commitments.get(track.global_track_id)
        barrier = self._identity_recovery_blockers.get(
            track.global_track_id
        )
        recovery_required = bool(
            barrier is not None
            or (
                previous is not None
                and previous.identity_commitment_state
                != IdentityCommitmentState.COMMITTED
            )
        )
        if evidence is None:
            return (
                "original_observation_evidence_unavailable"
                if recovery_required
                else None
            )
        admission_block = (
            self._first_accepted_original_evidence_block_reason(
                detection,
                evidence,
            )
        )
        if admission_block is not None:
            return admission_block

        if not recovery_required:
            return None
        if any(
            track.global_track_id in lease.track_ids
            for lease in self._ambiguity_leases.values()
        ):
            return "active_ambiguity_lease"
        if barrier is None:
            return "identity_recovery_barrier_unavailable"
        if barrier.overflow:
            return "identity_recovery_blocker_capacity_overflow"
        if evidence.key in barrier.evidence_keys:
            return "blocked_ambiguity_evidence_key"
        source_timestamp = evidence.source_measurement_timestamp
        if source_timestamp is None:
            return "source_measurement_timestamp_unavailable"
        if (
            source_timestamp
            <= barrier.recovery_not_before_measurement_timestamp
            + self.observation_timestamp_tolerance_s
        ):
            return "source_measurement_not_after_ambiguity_watermark"
        recovery_config = self.identity_commitment_recovery_config
        if (
            recovery_config.publication_freshness_gate_enabled
            and tracker_frame_timestamp - source_timestamp
            > recovery_config.max_recovery_evidence_age_seconds
            + self.observation_timestamp_tolerance_s
        ):
            return (
                "source_observation_outside_recovery_publication_"
                "freshness_window"
            )
        return None

    def _first_accepted_original_evidence_block_reason(
        self,
        detection: Detection3D,
        evidence: _ObservationEvidence | None,
    ) -> str | None:
        if evidence is None:
            return None
        if not evidence.identity_commitment_eligible:
            return evidence.identity_evidence_disposition
        if (
            evidence.source_measurement_timestamp is not None
            and evidence.source_measurement_timestamp
            > detection.measurement_timestamp
            + self.observation_timestamp_tolerance_s
        ):
            return "source_measurement_timestamp_from_future"

        claim = self._observation_claims.get(evidence.key)
        if claim is None:
            return "first_acceptance_claim_unavailable"
        if claim.status != "unseen":
            return "evidence_claim_not_unseen"
        if claim.global_track_id is not None:
            return "evidence_claim_already_bound"
        if claim.ambiguity_component_key is not None:
            return "ambiguity_reserved_evidence"
        if claim.replay_count != 0:
            return "duplicate_or_replayed_evidence"
        if claim.first_detection_id != detection.detection_id:
            return "evidence_not_first_accepted_detection"
        if (
            abs(
                claim.first_state_timestamp
                - detection.measurement_timestamp
            )
            > self.observation_timestamp_tolerance_s
        ):
            return "evidence_not_first_accepted_in_current_scan"
        return None

    def _record_identity_recovery_block(
        self,
        track: GlobalTrack3D,
        timestamp: float,
        reason: str,
    ) -> None:
        self._identity_commitment_blocked_recovery_counts[reason] += 1
        previous = self._identity_commitments.get(track.global_track_id)
        if (
            previous is None
            or previous.identity_commitment_state
            == IdentityCommitmentState.COMMITTED
        ):
            return
        self._identity_commitments[track.global_track_id] = replace(
            previous,
            association_state="unmatched",
            reason=f"identity_recovery_blocked_{reason}",
            state_timestamp=float(timestamp),
            **self._identity_recovery_public_fields(
                track.global_track_id
            ),
        )

    def _reconcile_identity_commitment_holds(
        self,
        timestamp: float,
        component_events: Iterable[Mapping[str, Any]],
    ) -> None:
        """Persist uncommitted state beyond the lifetime of active leases."""

        expirations_by_track: dict[str, Mapping[str, Any]] = {}
        for event in component_events:
            if event.get("decision") != "expired":
                continue
            for raw_track_id in event.get("track_ids", ()):
                track_id = str(raw_track_id)
                previous = expirations_by_track.get(track_id)
                if previous is None or int(event.get("generation", 0)) >= int(
                    previous.get("generation", 0)
                ):
                    expirations_by_track[track_id] = event

        leases_by_track: dict[str, list[_AmbiguityLease]] = defaultdict(list)
        for lease in self._ambiguity_leases.values():
            self._register_identity_recovery_lease(lease)
            for track_id in lease.track_ids:
                track = self.tracks.get(track_id)
                if (
                    track is not None
                    and track.lifecycle_state != TrackLifecycleState.DROPPED
                ):
                    leases_by_track[track_id].append(lease)

        for track_id, leases in sorted(leases_by_track.items()):
            ordered = sorted(
                leases,
                key=lambda item: (
                    item.generation,
                    item.component_key,
                ),
            )
            primary = ordered[-1]
            previous = self._identity_commitments.get(track_id)
            old_state = (
                None
                if previous is None
                else previous.identity_commitment_state
            )
            generation = (
                1
                if previous is None
                else previous.commitment_generation
                + int(
                    old_state
                    != IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD
                )
            )
            commitment = IdentityEvidenceCommitment(
                global_track_id=track_id,
                association_state=(
                    "unmatched"
                    if previous is None
                    else previous.association_state
                ),
                identity_commitment_state=(
                    IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD
                ),
                reason="active_structural_ambiguity_hold",
                state_timestamp=timestamp,
                commitment_generation=generation,
                measurement_timestamp=primary.measurement_timestamp,
                arrival_timestamp=primary.arrival_timestamp,
                ambiguity_component_key=primary.component_key,
                ambiguity_evidence_id=primary.evidence_id,
                ambiguity_component_generation=primary.generation,
                publisher_node_id=primary.publisher_node_id,
                publisher_epoch=primary.publisher_epoch,
                active_lease_count=len(ordered),
                active_lease_keys=tuple(
                    lease.component_key for lease in ordered
                ),
                lease_first_seen_timestamp=primary.first_seen_timestamp,
                lease_soft_deadline=primary.soft_deadline,
                lease_hard_deadline=primary.hard_deadline,
                **self._identity_recovery_public_fields(track_id),
            )
            self._identity_commitments[track_id] = commitment
            self._record_identity_commitment_transition(
                old_state,
                commitment.identity_commitment_state,
            )

        for track_id, previous in tuple(self._identity_commitments.items()):
            if (
                previous.identity_commitment_state
                != IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD
                or track_id in leases_by_track
            ):
                continue
            expiration = expirations_by_track.get(track_id)
            expiry_reason = (
                "lease_no_longer_active"
                if expiration is None
                else str(expiration["reason"])
            )
            expiry_timestamp = (
                float(timestamp)
                if expiration is None
                else float(
                    expiration.get("d2_consumption_timestamp", timestamp)
                )
            )
            after_hold = IdentityEvidenceCommitment(
                global_track_id=track_id,
                association_state=previous.association_state,
                identity_commitment_state=(
                    IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD
                ),
                reason=(
                    "ambiguity_hold_released_without_fresh_original_observation"
                ),
                state_timestamp=timestamp,
                commitment_generation=previous.commitment_generation + 1,
                measurement_timestamp=previous.measurement_timestamp,
                arrival_timestamp=previous.arrival_timestamp,
                ambiguity_component_key=previous.ambiguity_component_key,
                ambiguity_evidence_id=previous.ambiguity_evidence_id,
                ambiguity_component_generation=(
                    previous.ambiguity_component_generation
                ),
                publisher_node_id=previous.publisher_node_id,
                publisher_epoch=previous.publisher_epoch,
                active_lease_count=0,
                active_lease_keys=(),
                lease_first_seen_timestamp=(
                    previous.lease_first_seen_timestamp
                ),
                lease_soft_deadline=previous.lease_soft_deadline,
                lease_hard_deadline=previous.lease_hard_deadline,
                lease_expired_timestamp=expiry_timestamp,
                lease_expiration_reason=expiry_reason,
                **self._identity_recovery_public_fields(track_id),
            )
            self._identity_commitments[track_id] = after_hold
            self._record_identity_commitment_transition(
                previous.identity_commitment_state,
                after_hold.identity_commitment_state,
            )

    def _initialize_normal_identity_commitment(
        self,
        track: GlobalTrack3D,
        detection: Detection3D,
    ) -> None:
        evidence = self._observation_evidence(detection)
        if evidence is None:
            commitment = IdentityEvidenceCommitment(
                global_track_id=track.global_track_id,
                association_state="created",
                identity_commitment_state=IdentityCommitmentState.COMMITTED,
                reason="normal_path_not_subject_to_ambiguity_hold",
                state_timestamp=detection.measurement_timestamp,
            )
        else:
            if not evidence.identity_commitment_eligible:
                raise RuntimeError(
                    "known false alarm or unknown evidence reached track birth"
                )
            commitment = IdentityEvidenceCommitment(
                global_track_id=track.global_track_id,
                association_state="created",
                identity_commitment_state=IdentityCommitmentState.COMMITTED,
                reason="track_created_from_fresh_original_observation",
                state_timestamp=detection.measurement_timestamp,
                measurement_timestamp=(
                    evidence.source_measurement_timestamp
                    if evidence.source_measurement_timestamp is not None
                    else detection.measurement_timestamp
                ),
                arrival_timestamp=detection.arrival_timestamp,
                source_observation_evidence_key=evidence.key,
                source_observation_evidence_generation=0,
                source_observation_disposition=(
                    evidence.identity_evidence_disposition
                ),
            )
        self._identity_commitments[track.global_track_id] = commitment
        self._identity_commitment_transition_counts[
            "initialized:committed"
        ] += 1

    def _recover_identity_commitment(
        self,
        track: GlobalTrack3D,
        detection: Detection3D,
        evidence: _ObservationEvidence,
        *,
        association_state: str,
        tracker_frame_timestamp: float,
    ) -> None:
        previous = self._identity_commitments.get(track.global_track_id)
        block_reason = self._identity_observation_acceptance_block_reason(
            track,
            detection,
            evidence,
            tracker_frame_timestamp=tracker_frame_timestamp,
        )
        if block_reason is not None:
            self._record_identity_recovery_block(
                track,
                detection.measurement_timestamp,
                block_reason,
            )
            return

        claim = self._observation_claims.get(evidence.key)
        if claim is None:
            raise RuntimeError(
                "accepted identity evidence lost its first-consumption claim"
            )
        evidence_generation = claim.replay_count
        old_state = (
            None
            if previous is None
            else previous.identity_commitment_state
        )
        commitment = IdentityEvidenceCommitment(
            global_track_id=track.global_track_id,
            association_state=association_state,
            identity_commitment_state=IdentityCommitmentState.COMMITTED,
            reason="fresh_original_observation_accepted",
            state_timestamp=detection.measurement_timestamp,
            commitment_generation=(
                0
                if previous is None
                else previous.commitment_generation + 1
            ),
            measurement_timestamp=(
                evidence.source_measurement_timestamp
                if evidence.source_measurement_timestamp is not None
                else detection.measurement_timestamp
            ),
            arrival_timestamp=detection.arrival_timestamp,
            source_observation_evidence_key=evidence.key,
            source_observation_evidence_generation=evidence_generation,
            source_observation_disposition=(
                evidence.identity_evidence_disposition
            ),
            ambiguity_component_key=(
                None if previous is None else previous.ambiguity_component_key
            ),
            ambiguity_evidence_id=(
                None if previous is None else previous.ambiguity_evidence_id
            ),
            ambiguity_component_generation=(
                None
                if previous is None
                else previous.ambiguity_component_generation
            ),
            publisher_node_id=(
                None if previous is None else previous.publisher_node_id
            ),
            publisher_epoch=(
                None if previous is None else previous.publisher_epoch
            ),
            lease_first_seen_timestamp=(
                None
                if previous is None
                else previous.lease_first_seen_timestamp
            ),
            lease_soft_deadline=(
                None if previous is None else previous.lease_soft_deadline
            ),
            lease_hard_deadline=(
                None if previous is None else previous.lease_hard_deadline
            ),
            lease_expired_timestamp=(
                None
                if previous is None
                else previous.lease_expired_timestamp
            ),
            lease_expiration_reason=(
                None
                if previous is None
                else previous.lease_expiration_reason
            ),
        )
        self._clear_identity_recovery_blockers(track.global_track_id)
        self._identity_commitments[track.global_track_id] = commitment
        if old_state == IdentityCommitmentState.COMMITTED:
            self._identity_commitment_transition_counts[
                "committed:fresh_original_observation_refresh"
            ] += 1
        else:
            self._record_identity_commitment_transition(
                old_state,
                commitment.identity_commitment_state,
            )

    def _identity_commitment_frame_payloads(
        self,
        timestamp: float,
        *,
        created_track_ids: set[str],
        updated_track_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}
        for track in self.active_tracks():
            track_id = track.global_track_id
            commitment = self._identity_commitments.get(track_id)
            if commitment is None:
                commitment = IdentityEvidenceCommitment(
                    global_track_id=track_id,
                    association_state="unmatched",
                    identity_commitment_state=(
                        IdentityCommitmentState.COMMITTED
                    ),
                    reason="legacy_normal_path_not_subject_to_ambiguity_hold",
                    state_timestamp=timestamp,
                )
                self._identity_commitments[track_id] = commitment
                self._identity_commitment_transition_counts[
                    "initialized:committed"
                ] += 1
            if track.lifecycle_state == TrackLifecycleState.LOST:
                association_state = "lost"
            elif track_id in created_track_ids:
                association_state = "created"
            elif track_id in updated_track_ids:
                association_state = "matched"
            else:
                association_state = "unmatched"
            commitment = replace(
                commitment,
                association_state=association_state,
                state_timestamp=timestamp,
            )
            self._identity_commitments[track_id] = commitment
            payloads[track_id] = commitment.to_dict()
        return payloads

    def _merge_identity_commitments_for_aliases(
        self,
        aliases: Mapping[str, str],
        timestamp: float,
    ) -> None:
        priority = {
            IdentityCommitmentState.COMMITTED: 0,
            IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD: 1,
            IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD: 2,
        }
        for duplicate_id, survivor_id in sorted(aliases.items()):
            duplicate = self._identity_commitments.get(duplicate_id)
            survivor = self._identity_commitments.get(survivor_id)
            self._merge_identity_recovery_blockers(
                duplicate_id,
                survivor_id,
            )
            if duplicate is None:
                continue
            if (
                survivor is None
                or priority[duplicate.identity_commitment_state]
                > priority[survivor.identity_commitment_state]
            ):
                self._identity_commitments[survivor_id] = replace(
                    duplicate,
                    global_track_id=survivor_id,
                    state_timestamp=timestamp,
                )
                self._identity_commitment_transition_counts[
                    "coalescence:conservative_uncommitted_transfer"
                ] += int(
                    duplicate.identity_commitment_state
                    != IdentityCommitmentState.COMMITTED
                )
            self._identity_commitments.pop(duplicate_id, None)
            merged = self._identity_commitments.get(survivor_id)
            if (
                merged is not None
                and merged.identity_commitment_state
                != IdentityCommitmentState.COMMITTED
            ):
                self._identity_commitments[survivor_id] = replace(
                    merged,
                    **self._identity_recovery_public_fields(survivor_id),
                )

    def _record_identity_commitment_transition(
        self,
        previous: IdentityCommitmentState | None,
        current: IdentityCommitmentState,
    ) -> None:
        if previous == current:
            return
        previous_value = "none" if previous is None else previous.value
        self._identity_commitment_transition_counts[
            f"{previous_value}->{current.value}"
        ] += 1

    def _update_track(
        self,
        track: GlobalTrack3D,
        detection: Detection3D,
        *,
        precomputed_velocity_nis: float | None | object = _NO_PRECOMPUTED_NIS,
    ) -> dict[str, Any]:
        velocity_nis, velocity_inflation = self._velocity_model_gate(
            track,
            detection,
            precomputed_velocity_nis=precomputed_velocity_nis,
        )
        if detection.state_estimate_covariance is not None:
            source_state = detection.state_estimate
            assert source_state is not None
            source_covariance = _inflate_velocity_covariance(
                detection.state_estimate_covariance,
                velocity_inflation,
            )
            (
                track.state,
                track.covariance,
                covariance_consistency,
            ) = _covariance_intersection(
                track.state,
                track.covariance,
                source_state,
                source_covariance,
                first_weight=self.correlated_state_ci_track_weight,
            )
            mode = "correlated_6d_covariance_intersection"
        elif detection.velocity_ned is not None:
            measurement_state = detection.state_estimate
            assert measurement_state is not None
            measurement_covariance = np.zeros((6, 6), dtype=float)
            measurement_covariance[:3, :3] = detection.covariance
            assert detection.velocity_covariance is not None
            measurement_covariance[3:, 3:] = detection.velocity_covariance
            measurement_covariance = _inflate_velocity_covariance(
                measurement_covariance,
                velocity_inflation,
            )
            track.state, track.covariance = _linear_joseph_update(
                track.state,
                track.covariance,
                measurement_state,
                np.eye(6, dtype=float),
                measurement_covariance,
            )
            mode = "independent_6d_joseph"
        else:
            track.state, track.covariance = _linear_joseph_update(
                track.state,
                track.covariance,
                detection.position_ned,
                POSITION_H_3D,
                detection.covariance,
            )
            mode = "position_3d_joseph"

        if detection.state_estimate_covariance is not None and (
            covariance_consistency is not None
        ):
            track.covariance_consistency = dict(covariance_consistency)
        else:
            track.ensure_covariance_consistency()
        track.timestamp = detection.measurement_timestamp
        track.last_update_time = detection.measurement_timestamp
        track.last_detection_id = detection.detection_id
        track.hits += 1
        track.consecutive_hits += 1
        track.misses = 0
        track.identity_confidence = min(
            1.0, track.consecutive_hits / max(self.engageable_hits, 1)
        )
        track.append_history("update", detection)
        return {
            "mode": mode,
            "velocity_innovation_nis": velocity_nis,
            "velocity_covariance_inflation": (
                velocity_inflation if velocity_nis is not None else None
            ),
            "velocity_innovation_gated": bool(
                velocity_nis is not None
                and velocity_nis > self.velocity_innovation_gate_threshold
            ),
        }

    def _velocity_model_gate(
        self,
        track: GlobalTrack3D,
        detection: Detection3D,
        *,
        precomputed_velocity_nis: float | None | object = _NO_PRECOMPUTED_NIS,
    ) -> tuple[float | None, float]:
        if detection.velocity_ned is None or detection.velocity_covariance is None:
            return None, 1.0
        if precomputed_velocity_nis is _NO_PRECOMPUTED_NIS:
            residual = detection.velocity_ned - track.velocity_ned
            innovation = track.covariance[3:, 3:] + detection.velocity_covariance
            nis = _quadratic_form(innovation, residual)
        else:
            if precomputed_velocity_nis is None:
                return None, 1.0
            nis = float(precomputed_velocity_nis)
        inflation = max(1.0, nis / self.velocity_innovation_gate_threshold)
        return nis, inflation

    def _create_track(self, detection: Detection3D) -> GlobalTrack3D:
        track_id = f"{self.global_track_id_prefix}{self._next_track_number:06d}"
        self._next_track_number += 1
        velocity = (
            np.zeros(3, dtype=float)
            if detection.velocity_ned is None
            else detection.velocity_ned.copy()
        )
        velocity_covariance = (
            np.eye(3, dtype=float) * self.initial_velocity_variance
            if detection.velocity_covariance is None
            else detection.velocity_covariance.copy()
        )
        if detection.state_estimate_covariance is not None:
            covariance = detection.state_estimate_covariance.copy()
        else:
            covariance = np.zeros((6, 6), dtype=float)
            covariance[:3, :3] = detection.covariance
            covariance[3:, 3:] = velocity_covariance
        track = GlobalTrack3D(
            global_track_id=track_id,
            state=np.concatenate((detection.position_ned, velocity)),
            covariance=covariance,
            timestamp=detection.measurement_timestamp,
            lifecycle_state=TrackLifecycleState.TENTATIVE,
            hits=1,
            consecutive_hits=1,
            misses=0,
            age=1,
            created_at=detection.measurement_timestamp,
            last_update_time=detection.measurement_timestamp,
            last_detection_id=detection.detection_id,
            identity_confidence=1.0 / max(self.engageable_hits, 1),
            source_track_keys=(
                set() if detection.source_key is None else {detection.source_key}
            ),
            history_limit=self.track_history_limit,
        )
        track.append_history("create", detection)
        self.tracks[track_id] = track
        self._initialize_normal_identity_commitment(track, detection)
        self._advance_after_hit(track)
        return track

    def _advance_after_hit(self, track: GlobalTrack3D) -> None:
        old_state = track.lifecycle_state
        if old_state == TrackLifecycleState.DROPPED:
            return
        if old_state == TrackLifecycleState.LOST:
            track.lifecycle_state = TrackLifecycleState.CONFIRMED
        if (
            track.lifecycle_state == TrackLifecycleState.TENTATIVE
            and track.consecutive_hits >= self.confirmation_hits
        ):
            track.lifecycle_state = TrackLifecycleState.CONFIRMED
        if (
            track.lifecycle_state == TrackLifecycleState.CONFIRMED
            and track.hits >= self.engageable_hits
            and float(np.trace(track.covariance[:3, :3]))
            <= self.engageable_position_covariance_trace
        ):
            track.lifecycle_state = TrackLifecycleState.ENGAGEABLE
        if track.lifecycle_state != old_state:
            track.append_history(f"transition:{old_state.value}->{track.lifecycle_state.value}")

    def _mark_missed(self, track: GlobalTrack3D) -> None:
        old_state = track.lifecycle_state
        track.misses += 1
        track.consecutive_hits = 0
        track.identity_confidence = max(0.0, track.identity_confidence - 0.20)
        tentative_stale_drop = bool(
            old_state == TrackLifecycleState.TENTATIVE
            and track.misses >= self.tentative_drop_miss_threshold
        )
        if tentative_stale_drop or track.misses >= self.drop_miss_threshold:
            track.lifecycle_state = TrackLifecycleState.DROPPED
        elif track.misses >= self.lost_miss_threshold:
            track.lifecycle_state = TrackLifecycleState.LOST
        track.append_history("miss")
        if old_state != TrackLifecycleState.LOST and track.lifecycle_state == TrackLifecycleState.LOST:
            self._lost_count += 1
        if old_state != TrackLifecycleState.DROPPED and track.lifecycle_state == TrackLifecycleState.DROPPED:
            self._drop_count += 1
            if tentative_stale_drop:
                self._tentative_stale_drop_count += 1
            self._clear_identity_recovery_blockers(track.global_track_id)
            for source_key in tuple(track.source_track_keys):
                if self._source_bindings.get(source_key) == track.global_track_id:
                    self._source_bindings.pop(source_key, None)

    def _partition_observation_freshness(
        self,
        detections: list[Detection3D],
        timestamp: float,
    ) -> tuple[
        list[Detection3D],
        list[dict[str, Any]],
        dict[str, _ObservationEvidence],
    ]:
        """Remove repeated D1 posterior evidence before association and hits."""

        without_evidence: list[Detection3D] = []
        grouped: dict[str, list[tuple[Detection3D, _ObservationEvidence]]] = (
            defaultdict(list)
        )
        for detection in detections:
            evidence = self._observation_evidence(detection)
            if evidence is None:
                without_evidence.append(detection)
            else:
                grouped[evidence.key].append((detection, evidence))

        accepted = list(without_evidence)
        evidence_by_detection: dict[str, _ObservationEvidence] = {}
        events: list[dict[str, Any]] = []
        for evidence_key in sorted(grouped):
            candidates = sorted(
                grouped[evidence_key],
                key=lambda item: (
                    float(np.trace(item[0].covariance)),
                    -float(item[0].confidence),
                    item[0].detection_id,
                ),
            )
            existing = self._observation_claims.get(evidence_key)
            if existing is not None:
                for detection, evidence in candidates:
                    reason = (
                        "observation_reserved_ambiguous"
                        if existing.status == "reserved_ambiguous"
                        else self._replay_reason(existing.evidence, evidence)
                    )
                    existing.replay_count += 1
                    existing.last_replay_state_timestamp = float(timestamp)
                    self._record_observation_rejection(reason)
                    events.append(
                        self._observation_rejection_event(
                            detection,
                            evidence,
                            existing,
                            reason=reason,
                        )
                    )
                continue

            measurement_timestamps = {
                item[1].source_measurement_timestamp for item in candidates
            }
            finite_timestamps = {
                value for value in measurement_timestamps if value is not None
            }
            if len(finite_timestamps) > 1 and (
                max(finite_timestamps) - min(finite_timestamps)
                > self.observation_timestamp_tolerance_s
            ):
                first_detection, first_evidence = max(
                    candidates,
                    key=lambda item: (
                        -1.0
                        if item[1].source_measurement_timestamp is None
                        else item[1].source_measurement_timestamp,
                        item[0].detection_id,
                    ),
                )
                claim = _ObservationClaim(
                    evidence=first_evidence,
                    first_detection_id=first_detection.detection_id,
                    first_state_timestamp=float(timestamp),
                )
                claim_requires_storage = any(
                    not self._observation_measurement_is_too_old(evidence)
                    for _, evidence in candidates
                )
                if claim_requires_storage and not self._store_observation_claim(claim):
                    for detection, evidence in candidates:
                        self._record_observation_rejection(
                            "observation_claim_ledger_overflow"
                        )
                        events.append(
                            self._observation_rejection_event(
                                detection,
                                evidence,
                                None,
                                reason="observation_claim_ledger_overflow",
                            )
                        )
                    continue
                for detection, evidence in candidates:
                    claim.replay_count += 1
                    claim.last_replay_state_timestamp = float(timestamp)
                    self._record_observation_rejection(
                        "observation_identity_timestamp_conflict"
                    )
                    events.append(
                        self._observation_rejection_event(
                            detection,
                            evidence,
                            claim,
                            reason="observation_identity_timestamp_conflict",
                        )
                    )
                continue

            if any(
                self._observation_measurement_is_too_old(evidence)
                for _, evidence in candidates
            ):
                for detection, evidence in candidates:
                    self._record_observation_rejection(
                        "observation_measurement_too_old"
                    )
                    events.append(
                        self._observation_rejection_event(
                            detection,
                            evidence,
                            None,
                            reason="observation_measurement_too_old",
                        )
                    )
                continue

            winner, evidence = candidates[0]
            accepted.append(winner)
            evidence_by_detection[winner.detection_id] = evidence
            claim = _ObservationClaim(
                evidence=evidence,
                first_detection_id=winner.detection_id,
                first_state_timestamp=float(timestamp),
            )
            if not self._store_observation_claim(claim):
                for detection, rejected_evidence in candidates:
                    self._record_observation_rejection(
                        "observation_claim_ledger_overflow"
                    )
                    events.append(
                        self._observation_rejection_event(
                            detection,
                            rejected_evidence,
                            None,
                            reason="observation_claim_ledger_overflow",
                        )
                    )
                accepted.pop()
                evidence_by_detection.pop(winner.detection_id, None)
                continue
            for detection, duplicate_evidence in candidates[1:]:
                claim.replay_count += 1
                claim.last_replay_state_timestamp = float(timestamp)
                self._record_observation_rejection(
                    "duplicate_observation_within_scan"
                )
                events.append(
                    self._observation_rejection_event(
                        detection,
                        duplicate_evidence,
                        claim,
                        reason="duplicate_observation_within_scan",
                    )
                )

        accepted.sort(key=lambda item: item.detection_id)
        events.sort(key=lambda item: item["detection_id"])
        return accepted, events, evidence_by_detection

    def _observation_evidence(
        self,
        detection: Detection3D,
    ) -> _ObservationEvidence | None:
        metadata = detection.metadata
        identity_disposition = self._identity_evidence_disposition(metadata)
        raw_opaque_evidence_key = metadata.get(
            "latest_observation_evidence_key",
            metadata.get("observation_evidence_key"),
        )
        if raw_opaque_evidence_key is not None:
            opaque_key = str(raw_opaque_evidence_key).strip()
            if not opaque_key.startswith("d1-observation-sha256:"):
                raise ValueError(
                    "D1 observation_evidence_key must use the frozen opaque prefix"
                )
            raw_timestamp = metadata.get(
                "source_measurement_timestamp",
                metadata.get("latest_measurement_timestamp"),
            )
            source_timestamp = _optional_nonnegative_timestamp(raw_timestamp)
            namespace = str(
                metadata.get(
                    "latest_sensor_id",
                    detection.source_node_id or "d1-online-observation",
                )
            ).strip()
            return _ObservationEvidence(
                key=opaque_key,
                observation_id=opaque_key,
                source_namespace=namespace,
                source_measurement_timestamp=source_timestamp,
                identity_evidence_disposition=identity_disposition,
            )
        raw_observation_id = metadata.get(
            "latest_observation_id",
            metadata.get("observation_id"),
        )
        if raw_observation_id is None or not str(raw_observation_id).strip():
            return None
        observation_id = str(raw_observation_id).strip()
        raw_namespace = metadata.get("latest_sensor_id")
        if raw_namespace is None:
            raw_namespace = detection.source_node_id
        if raw_namespace is None:
            nodes = metadata.get("source_node_ids")
            if isinstance(nodes, (list, tuple, set)) and nodes:
                raw_namespace = ",".join(sorted(str(item) for item in nodes))
        source_namespace = (
            "d1-online-observation"
            if raw_namespace is None or not str(raw_namespace).strip()
            else str(raw_namespace).strip()
        )
        raw_timestamp = metadata.get(
            "source_measurement_timestamp",
            metadata.get("latest_measurement_timestamp"),
        )
        source_timestamp = _optional_nonnegative_timestamp(raw_timestamp)
        return _ObservationEvidence(
            key=f"{source_namespace}::{observation_id}",
            observation_id=observation_id,
            source_namespace=source_namespace,
            source_measurement_timestamp=source_timestamp,
            identity_evidence_disposition=identity_disposition,
        )

    @staticmethod
    def _identity_evidence_disposition(
        metadata: Mapping[str, Any],
    ) -> str:
        raw = metadata.get(
            "identity_evidence_disposition",
            "target_candidate",
        )
        disposition = str(raw).strip().lower()
        if disposition not in {
            "target_candidate",
            "known_false_alarm",
            "unknown",
        }:
            raise ValueError(
                "identity_evidence_disposition must be target_candidate, "
                "known_false_alarm, or unknown"
            )
        return disposition

    def _replay_reason(
        self,
        original: _ObservationEvidence,
        replay: _ObservationEvidence,
    ) -> str:
        first = original.source_measurement_timestamp
        current = replay.source_measurement_timestamp
        if first is not None and current is not None and (
            abs(first - current) > self.observation_timestamp_tolerance_s
        ):
            return "observation_identity_timestamp_conflict"
        return "repeated_latest_observation_id"

    @staticmethod
    def _observation_rejection_event(
        detection: Detection3D,
        evidence: _ObservationEvidence,
        claim: _ObservationClaim | None,
        *,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "detection_id": detection.detection_id,
            "observation_id": evidence.observation_id,
            "source_namespace": evidence.source_namespace,
            "source_measurement_timestamp": (
                evidence.source_measurement_timestamp
            ),
            "state_valid_timestamp": detection.measurement_timestamp,
            "arrival_timestamp": detection.arrival_timestamp,
            "claimed_global_track_id": (
                None if claim is None else claim.global_track_id
            ),
            "claim_status": None if claim is None else claim.status,
            "ambiguity_component_key": (
                None if claim is None else claim.ambiguity_component_key
            ),
            "first_detection_id": (
                None if claim is None else claim.first_detection_id
            ),
            "replay_generation": 0 if claim is None else claim.replay_count,
            "reason": reason,
            "online_truth_used": False,
        }

    def _eligible_replay_coasts(
        self,
        replay_events: list[dict[str, Any]],
        timestamp: float,
    ) -> dict[str, dict[str, Any]]:
        """Return one bounded, prediction-only coast decision per track.

        Any non-replay rejection associated with a track disables coast for
        that track in the current frame. Eligibility is measured from the last
        fresh measurement update; replay processing never changes that time.
        """

        repeated_by_track: dict[str, list[dict[str, Any]]] = defaultdict(list)
        blocked_track_ids: set[str] = set()
        for event in replay_events:
            raw_track_id = event.get("claimed_global_track_id")
            if raw_track_id is None or not str(raw_track_id).strip():
                continue
            track_id = str(raw_track_id)
            if event.get("reason") == "repeated_latest_observation_id":
                repeated_by_track[track_id].append(event)
            else:
                blocked_track_ids.add(track_id)

        decisions: dict[str, dict[str, Any]] = {}
        grace = self.replay_coast_config.grace_seconds
        for track_id in sorted(repeated_by_track):
            if track_id in blocked_track_ids:
                continue
            track = self.tracks.get(track_id)
            if track is None or track.lifecycle_state == TrackLifecycleState.DROPPED:
                continue
            age = float(timestamp) - float(track.last_update_time)
            if age < -self.observation_timestamp_tolerance_s:
                continue
            if age > grace + self.observation_timestamp_tolerance_s:
                continue
            events = repeated_by_track[track_id]
            decisions[track_id] = {
                "global_track_id": track_id,
                "reason": "repeated_latest_observation_id",
                "decision": "prediction_only_replay_coast",
                "state_timestamp": float(timestamp),
                "last_fresh_update_time": float(track.last_update_time),
                "age_since_last_fresh_update_seconds": max(0.0, age),
                "grace_seconds": grace,
                "config_version": self.replay_coast_config.config_version,
                "detection_ids": sorted(
                    str(item["detection_id"]) for item in events
                ),
                "observation_ids": sorted(
                    {str(item["observation_id"]) for item in events}
                ),
                "measurement_update_applied": False,
                "hit_added": False,
                "miss_added": False,
                "birth_allowed": False,
                "grace_refreshed": False,
                "online_truth_used": False,
            }
        return decisions

    def _record_observation_rejection(self, reason: str) -> None:
        reason = str(reason)
        self._replay_quarantine_count += 1
        self._observation_rejection_reason_counts[reason] += 1
        if reason == "observation_identity_timestamp_conflict":
            self._observation_timestamp_conflict_count += 1
        elif reason == "observation_measurement_too_old":
            self._observation_measurement_too_old_count += 1
        elif reason == "observation_claim_ledger_overflow":
            self._observation_claim_overflow_count += 1

    def _store_observation_claim(self, claim: _ObservationClaim) -> bool:
        if len(self._observation_claims) >= self.observation_claim_config.max_count:
            return False
        if claim.status not in {"unseen", "reserved_ambiguous", "consumed"}:
            raise ValueError("unsupported observation claim status")
        self._observation_claims[claim.evidence.key] = claim
        self._observation_claim_status_counts[claim.status] += 1
        if (
            claim.status != "reserved_ambiguous"
            and claim.evidence.source_measurement_timestamp is not None
        ):
            heapq.heappush(
                self._observation_claim_eviction_heap,
                (
                    claim.evidence.source_measurement_timestamp,
                    claim.evidence.key,
                ),
            )
        elif (
            claim.status != "reserved_ambiguous"
            and claim.evidence.source_measurement_timestamp is None
        ):
            self._observation_claim_undated_count += 1
        self._observation_claim_peak_count = max(
            self._observation_claim_peak_count,
            len(self._observation_claims),
        )
        return True

    def _advance_observation_claim_watermark(
        self,
        tracker_timestamp: float,
    ) -> list[dict[str, Any]]:
        admission_watermark = self.observation_claim_config.admission_watermark(
            tracker_timestamp
        )
        if self._observation_admission_watermark is not None:
            admission_watermark = max(
                admission_watermark,
                self._observation_admission_watermark,
            )
        self._observation_admission_watermark = float(admission_watermark)

        watermark = self.observation_claim_config.safe_watermark(tracker_timestamp)
        if self._observation_claim_safe_watermark is not None:
            watermark = max(watermark, self._observation_claim_safe_watermark)
        self._observation_claim_safe_watermark = float(watermark)
        events: list[dict[str, Any]] = []
        retirement_boundary = watermark - self.observation_timestamp_tolerance_s
        while (
            self._observation_claim_eviction_heap
            and self._observation_claim_eviction_heap[0][0]
            < retirement_boundary
        ):
            source_timestamp, key = heapq.heappop(
                self._observation_claim_eviction_heap
            )
            claim = self._observation_claims.get(key)
            if claim is None:
                continue
            if claim.status == "reserved_ambiguous":
                continue
            if claim.evidence.source_measurement_timestamp != source_timestamp:
                continue
            self._observation_claims.pop(key)
            self._decrement_observation_claim_status(claim.status)
            if claim.global_track_id is not None:
                track_keys = self._track_observation_keys.get(claim.global_track_id)
                if track_keys is not None:
                    if key in track_keys:
                        track_keys.remove(key)
                        self._track_observation_key_count -= 1
                    if not track_keys:
                        self._track_observation_keys.pop(claim.global_track_id, None)
            self._observation_claim_evicted_count += 1
            events.append(
                {
                    "observation_id": claim.evidence.observation_id,
                    "source_namespace": claim.evidence.source_namespace,
                    "source_measurement_timestamp": (
                        claim.evidence.source_measurement_timestamp
                    ),
                    "safe_watermark": watermark,
                    "claimed_global_track_id": claim.global_track_id,
                    "reason": "claim_retired_after_safe_watermark",
                    "online_truth_used": False,
                }
            )
        return events

    def _observation_measurement_is_too_old(
        self,
        evidence: _ObservationEvidence,
    ) -> bool:
        source_timestamp = evidence.source_measurement_timestamp
        watermark = self._observation_admission_watermark
        return bool(
            source_timestamp is not None
            and watermark is not None
            and source_timestamp
            < watermark - self.observation_timestamp_tolerance_s
        )

    def _observation_claim_ledger_summary(self) -> dict[str, Any]:
        return {
            **self.observation_claim_config.to_dict(),
            "schema_version": OBSERVATION_CLAIM_LEDGER_SCHEMA_VERSION,
            "current_count": len(self._observation_claims),
            "peak_count": self._observation_claim_peak_count,
            "evicted_count": self._observation_claim_evicted_count,
            "overflow_rejection_count": self._observation_claim_overflow_count,
            "too_old_rejection_count": self._observation_measurement_too_old_count,
            "replay_rejection_count": (
                self._observation_rejection_reason_counts.get(
                    "repeated_latest_observation_id",
                    0,
                )
                + self._observation_rejection_reason_counts.get(
                    "duplicate_observation_within_scan",
                    0,
                )
            ),
            "total_rejection_count": self._replay_quarantine_count,
            "safe_watermark_measurement_timestamp": (
                self._observation_claim_safe_watermark
            ),
            "admission_watermark_measurement_timestamp": (
                self._observation_admission_watermark
            ),
            "undated_non_evictable_count": self._observation_claim_undated_count,
            "eviction_index_count": len(self._observation_claim_eviction_heap),
            "track_observation_key_count": self._track_observation_key_count,
            "track_observation_index_track_count": len(
                self._track_observation_keys
            ),
            "tombstone_count": 0,
            "anti_replay_mode": "trusted_measurement_time_safe_watermark",
            "claim_status_counts": {
                status: int(self._observation_claim_status_counts.get(status, 0))
                for status in (
                    "unseen",
                    "reserved_ambiguous",
                    "consumed",
                )
            },
            "online_truth_used": False,
        }

    def _assign_observation_claim(
        self,
        evidence: _ObservationEvidence,
        global_track_id: str,
    ) -> None:
        claim = self._observation_claims[evidence.key]
        self._transition_observation_claim_status(claim, "consumed")
        claim.global_track_id = str(global_track_id)
        track_keys = self._track_observation_keys[str(global_track_id)]
        before = len(track_keys)
        track_keys.add(evidence.key)
        self._track_observation_key_count += len(track_keys) - before

    def _process_ambiguity_components(
        self,
        components: Iterable[
            AmbiguityComponent3D | Mapping[str, Any]
        ],
        timestamp: float,
    ) -> dict[str, Any]:
        raw_components = list(components)
        diagnostics: dict[str, Any] = {
            "enabled": self.ambiguity_hold_config.enabled,
            "input_component_count": len(raw_components),
            "accepted_component_count": 0,
            "rejected_component_count": 0,
            "expired_component_count": 0,
            "component_events": [],
            "prevented_counts": Counter(
                {
                    "hit": 0,
                    "miss": 0,
                    "birth": 0,
                    "rebind": 0,
                }
            ),
        }
        if not self.ambiguity_hold_config.enabled:
            diagnostics.update(
                {
                    "ignored_component_count": len(raw_components),
                    "active_component_count": 0,
                    "hold_track_ids": [],
                    "hold_source_keys": [],
                    "reserved_evidence_count": 0,
                    "active_leases": [],
                }
            )
            return diagnostics

        expired_events = self._expire_ambiguity_leases(timestamp)
        diagnostics["component_events"].extend(expired_events)
        diagnostics["expired_component_count"] += len(expired_events)

        for raw_component in raw_components:
            try:
                component = AmbiguityComponent3D.from_mapping(
                    raw_component.to_dict()
                    if isinstance(raw_component, AmbiguityComponent3D)
                    else raw_component
                )
            except (AmbiguityComponentValidationError, TypeError, ValueError) as exc:
                event = {
                    "decision": "rejected",
                    "reason": "component_contract_rejected",
                    "detail": str(exc),
                    "measurement_timestamp": None,
                    "arrival_timestamp": None,
                    "state_valid_timestamp": None,
                    "published_at": None,
                    "d2_consumption_timestamp": float(timestamp),
                    "component_age_seconds": None,
                    "time_decision": "component_contract_unavailable",
                    "lease_extended": False,
                    "online_truth_used": False,
                }
                diagnostics["component_events"].append(event)
                diagnostics["rejected_component_count"] += 1
                self._ambiguity_component_event_counts[
                    "rejected:component_contract_rejected"
                ] += 1
                continue

            event, forced_expirations = self._admit_ambiguity_component(
                component,
                timestamp,
            )
            if forced_expirations:
                diagnostics["component_events"].extend(forced_expirations)
                diagnostics["expired_component_count"] += len(
                    forced_expirations
                )
            diagnostics["component_events"].append(event)
            decision = str(event["decision"])
            if decision == "accepted":
                diagnostics["accepted_component_count"] += 1
            else:
                diagnostics["rejected_component_count"] += 1

        hold_track_ids = self._active_ambiguity_hold_track_ids()
        hold_source_keys = {
            source_key
            for lease in self._ambiguity_leases.values()
            for source_key in lease.member_source_keys
        }
        diagnostics.update(
            {
                "ignored_component_count": 0,
                "active_component_count": len(self._ambiguity_leases),
                "hold_track_ids": sorted(hold_track_ids),
                "hold_source_keys": sorted(hold_source_keys),
                "reserved_evidence_count": int(
                    self._observation_claim_status_counts.get(
                        "reserved_ambiguous",
                        0,
                    )
                ),
                "active_leases": [
                    self._ambiguity_leases[key].to_dict()
                    for key in sorted(self._ambiguity_leases)
                ],
            }
        )
        return diagnostics

    def _admit_ambiguity_component(
        self,
        component: AmbiguityComponent3D,
        timestamp: float,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        config = self.ambiguity_hold_config
        _, _, rejection_reason = self._ambiguity_component_time_assessment(
            component,
            timestamp,
        )
        if (
            rejection_reason is None
            and len(component.members) > config.max_members_per_component
        ):
            rejection_reason = "component_member_capacity_exceeded"
        elif (
            rejection_reason is None
            and len(component.observations)
            > config.max_observations_per_component
        ):
            rejection_reason = "component_observation_capacity_exceeded"
        elif (
            rejection_reason is None
            and len(component.candidate_edges)
            > config.max_candidate_edges_per_component
        ):
            rejection_reason = "component_edge_capacity_exceeded"
        elif (
            rejection_reason is None
            and component.lease_key not in self._ambiguity_leases
            and len(self._ambiguity_leases) >= config.max_active_components
        ):
            rejection_reason = "active_component_capacity_exceeded"

        highest_generation = self._ambiguity_component_generations.get(
            component.lease_key,
            0,
        )
        active_lease = self._ambiguity_leases.get(component.lease_key)
        epoch_decision = self._ambiguity_epoch_decision(component)
        rotating_component_keys = {
            key
            for key, lease in self._ambiguity_leases.items()
            if epoch_decision == "rotate"
            and lease.publisher_node_id == component.publisher_node_id
            and lease.publisher_epoch != component.publisher_epoch
        }
        if rejection_reason is None and component.evidence_id in (
            self._ambiguity_evidence_history
        ):
            rejection_reason = "evidence_replay"
        elif (
            rejection_reason is None
            and component.generation <= highest_generation
        ):
            rejection_reason = "component_generation_replay_or_rollback"
        elif (
            rejection_reason is None
            and active_lease is None
            and component.lease_key
            in self._ambiguity_component_hard_deadlines
            and timestamp + self.observation_timestamp_tolerance_s
            >= self._ambiguity_component_hard_deadlines[
                component.lease_key
            ]
        ):
            rejection_reason = "component_hard_cap_exhausted"
        elif (
            rejection_reason is None
            and active_lease is not None
            and set(component.member_source_keys)
            != active_lease.member_source_keys
        ):
            rejection_reason = "component_membership_changed"

        for other_key, other_lease in self._ambiguity_leases.items():
            if rejection_reason is not None or other_key == component.lease_key:
                continue
            if other_key in rotating_component_keys:
                continue
            if (
                set(component.observation_evidence_keys)
                & other_lease.observation_evidence_keys
            ):
                rejection_reason = "observation_reserved_by_incompatible_component"
            elif (
                set(component.member_source_keys)
                & other_lease.member_source_keys
            ):
                rejection_reason = "member_held_by_incompatible_component"

        if rejection_reason is None and epoch_decision == "rollback":
            rejection_reason = "publisher_epoch_rollback"

        new_observation_keys = set(component.observation_evidence_keys)
        if active_lease is not None:
            new_observation_keys -= active_lease.observation_evidence_keys
        for evidence_key in new_observation_keys:
            if rejection_reason is not None:
                break
            existing_claim = self._observation_claims.get(evidence_key)
            if (
                existing_claim is not None
                and existing_claim.ambiguity_component_key
                not in rotating_component_keys
            ):
                rejection_reason = (
                    "observation_claim_conflicts_with_ambiguity_reservation"
                )

        rotating_reserved_count = sum(
            len(self._ambiguity_leases[key].observation_evidence_keys)
            for key in rotating_component_keys
        )
        reserved_count = max(
            0,
            int(
            self._observation_claim_status_counts.get(
                "reserved_ambiguous",
                0,
            )
            )
            - rotating_reserved_count,
        )
        if (
            rejection_reason is None
            and reserved_count + len(new_observation_keys)
            > config.max_reserved_evidence
        ):
            rejection_reason = "reserved_evidence_capacity_exceeded"
        if (
            rejection_reason is None
            and len(self._observation_claims)
            - rotating_reserved_count
            + len(new_observation_keys)
            > self.observation_claim_config.max_count
        ):
            rejection_reason = "observation_claim_ledger_capacity_exceeded"

        if rejection_reason is not None:
            self._ambiguity_component_event_counts[
                f"rejected:{rejection_reason}"
            ] += 1
            return (
                self._ambiguity_component_event(
                    component,
                    decision="rejected",
                    reason=rejection_reason,
                    timestamp=timestamp,
                    lease=None,
                    lease_extended=False,
                ),
                [],
            )

        forced_expirations: list[dict[str, Any]] = []
        if epoch_decision == "rotate":
            forced_expirations = self._rotate_ambiguity_publisher_epoch(
                component.publisher_node_id,
                component.publisher_epoch,
                timestamp,
            )
        elif epoch_decision == "initialize":
            self._ambiguity_publisher_current_epochs[
                component.publisher_node_id
            ] = component.publisher_epoch

        if active_lease is None:
            hard_deadline = self._ambiguity_component_hard_deadlines.get(
                component.lease_key,
                timestamp + config.effective_hard_seconds,
            )
            self._ambiguity_component_hard_deadlines[
                component.lease_key
            ] = hard_deadline
            soft_deadline = min(
                hard_deadline,
                timestamp + config.effective_gap_seconds,
            )
            track_ids = self._bound_track_ids(
                component.member_source_keys
            )
            lease = _AmbiguityLease(
                component_key=component.lease_key,
                component_id=component.component_id,
                evidence_id=component.evidence_id,
                generation=component.generation,
                publisher_node_id=component.publisher_node_id,
                publisher_epoch=component.publisher_epoch,
                measurement_timestamp=component.measurement_timestamp,
                arrival_timestamp=component.arrival_timestamp,
                first_seen_timestamp=timestamp,
                last_new_evidence_timestamp=timestamp,
                soft_deadline=soft_deadline,
                hard_deadline=hard_deadline,
                member_source_keys=set(component.member_source_keys),
                observation_evidence_keys=set(),
                track_ids=track_ids,
                latest_reason="new_component_with_original_evidence",
            )
            self._ambiguity_leases[component.lease_key] = lease
        else:
            lease = active_lease

        lease_extended = bool(new_observation_keys)
        for observation in component.observations:
            evidence_key = observation.observation_evidence_key
            if evidence_key not in new_observation_keys:
                continue
            claim = _ObservationClaim(
                evidence=_ObservationEvidence(
                    key=evidence_key,
                    observation_id=evidence_key,
                    source_namespace=component.sensor_id,
                    source_measurement_timestamp=(
                        component.measurement_timestamp
                    ),
                ),
                first_detection_id=f"ambiguity:{component.evidence_id}",
                first_state_timestamp=float(timestamp),
                status="reserved_ambiguous",
                ambiguity_component_key=component.lease_key,
            )
            if not self._store_observation_claim(claim):
                raise RuntimeError(
                    "ambiguity reservation capacity changed during admission"
                )
            lease.observation_evidence_keys.add(evidence_key)

        lease.evidence_id = component.evidence_id
        lease.generation = component.generation
        lease.measurement_timestamp = component.measurement_timestamp
        lease.arrival_timestamp = component.arrival_timestamp
        lease.track_ids.update(
            self._bound_track_ids(component.member_source_keys)
        )
        self._register_identity_recovery_lease(lease)
        if lease_extended:
            lease.last_new_evidence_timestamp = timestamp
            lease.soft_deadline = min(
                lease.hard_deadline,
                timestamp + config.effective_gap_seconds,
            )
            lease.latest_reason = "new_original_observation_evidence"
        else:
            lease.latest_reason = "new_generation_without_new_observation"

        self._remember_ambiguity_component_generation(
            component.lease_key,
            component.generation,
        )
        self._remember_ambiguity_evidence(component.evidence_id)
        self._ambiguity_component_event_counts["accepted"] += 1
        if lease_extended:
            self._ambiguity_component_event_counts[
                "accepted:lease_extended"
            ] += 1
        else:
            self._ambiguity_component_event_counts[
                "accepted:lease_not_extended"
            ] += 1
        return (
            self._ambiguity_component_event(
                component,
                decision="accepted",
                reason=lease.latest_reason,
                timestamp=timestamp,
                lease=lease,
                lease_extended=lease_extended,
            ),
            forced_expirations,
        )

    def _ambiguity_component_time_assessment(
        self,
        component: AmbiguityComponent3D,
        timestamp: float,
    ) -> tuple[float, str, str | None]:
        component_age_seconds = float(
            timestamp - component.state_valid_timestamp
        )
        tolerance = self.observation_timestamp_tolerance_s
        if component_age_seconds < -tolerance:
            return (
                component_age_seconds,
                "future_state_valid_timestamp_rejected",
                "component_from_future",
            )
        if (
            component_age_seconds
            > self.ambiguity_hold_config.max_component_age_seconds + tolerance
        ):
            return (
                component_age_seconds,
                "stale_component_age_rejected",
                "component_stale_age_exceeded",
            )
        if component_age_seconds > tolerance:
            time_decision = "bounded_delayed_component_within_age"
        else:
            time_decision = "same_epoch_component_within_age"
        return component_age_seconds, time_decision, None

    def _ambiguity_epoch_decision(
        self,
        component: AmbiguityComponent3D,
    ) -> str:
        node = component.publisher_node_id
        epoch = component.publisher_epoch
        current = self._ambiguity_publisher_current_epochs.get(node)
        if current is None:
            return "initialize"
        if current == epoch:
            return "current"
        if (node, epoch) in self._ambiguity_publisher_retired_epochs:
            return "rollback"
        return "rotate"

    def _rotate_ambiguity_publisher_epoch(
        self,
        publisher_node_id: str,
        publisher_epoch: str,
        timestamp: float,
    ) -> list[dict[str, Any]]:
        previous = self._ambiguity_publisher_current_epochs.get(
            publisher_node_id
        )
        if previous is not None:
            retired_epoch = (publisher_node_id, previous)
            if retired_epoch not in self._ambiguity_publisher_retired_epochs:
                self._ambiguity_publisher_retired_epochs.add(retired_epoch)
                self._ambiguity_retired_epoch_order.append(retired_epoch)
            capacity = self.ambiguity_hold_config.max_component_history
            while len(self._ambiguity_publisher_retired_epochs) > capacity:
                oldest = self._ambiguity_retired_epoch_order.popleft()
                self._ambiguity_publisher_retired_epochs.discard(oldest)
        self._ambiguity_publisher_current_epochs[
            publisher_node_id
        ] = publisher_epoch
        keys = [
            key
            for key, lease in self._ambiguity_leases.items()
            if lease.publisher_node_id == publisher_node_id
            and lease.publisher_epoch != publisher_epoch
        ]
        return [
            self._expire_one_ambiguity_lease(
                key,
                timestamp,
                reason="publisher_epoch_rotated",
            )
            for key in keys
        ]

    def _expire_ambiguity_leases(
        self,
        timestamp: float,
    ) -> list[dict[str, Any]]:
        expired: list[dict[str, Any]] = []
        tolerance = self.observation_timestamp_tolerance_s
        for key in sorted(tuple(self._ambiguity_leases)):
            lease = self._ambiguity_leases[key]
            deadline = min(lease.soft_deadline, lease.hard_deadline)
            if timestamp + tolerance < deadline:
                continue
            reason = (
                "hard_deadline_reached"
                if lease.hard_deadline <= lease.soft_deadline + tolerance
                else "soft_deadline_reached"
            )
            expired.append(
                self._expire_one_ambiguity_lease(
                    key,
                    timestamp,
                    reason=reason,
                )
            )
        return expired

    def _expire_one_ambiguity_lease(
        self,
        component_key: str,
        timestamp: float,
        *,
        reason: str,
    ) -> dict[str, Any]:
        lease = self._ambiguity_leases[component_key]
        self._register_identity_recovery_lease(lease)
        self._ambiguity_leases.pop(component_key)
        released = 0
        for evidence_key in lease.observation_evidence_keys:
            claim = self._observation_claims.get(evidence_key)
            if (
                claim is None
                or claim.status != "reserved_ambiguous"
                or claim.ambiguity_component_key != component_key
            ):
                continue
            self._observation_claims.pop(evidence_key)
            self._decrement_observation_claim_status(claim.status)
            released += 1
        self._ambiguity_component_event_counts["expired"] += 1
        self._ambiguity_component_event_counts[f"expired:{reason}"] += 1
        return {
            "decision": "expired",
            "reason": reason,
            "component_key": component_key,
            "component_id": lease.component_id,
            "evidence_id": lease.evidence_id,
            "generation": lease.generation,
            "publisher_node_id": lease.publisher_node_id,
            "publisher_epoch": lease.publisher_epoch,
            "measurement_timestamp": lease.measurement_timestamp,
            "arrival_timestamp": lease.arrival_timestamp,
            "state_valid_timestamp": float(timestamp),
            "d2_consumption_timestamp": float(timestamp),
            "soft_deadline": lease.soft_deadline,
            "hard_deadline": lease.hard_deadline,
            "first_seen_timestamp": lease.first_seen_timestamp,
            "track_ids": sorted(lease.track_ids),
            "released_reserved_evidence_count": released,
            "lease_extended": False,
            "online_truth_used": False,
        }

    def _ambiguity_component_event(
        self,
        component: AmbiguityComponent3D,
        *,
        decision: str,
        reason: str,
        timestamp: float,
        lease: _AmbiguityLease | None,
        lease_extended: bool,
    ) -> dict[str, Any]:
        (
            component_age_seconds,
            time_decision,
            _time_rejection_reason,
        ) = self._ambiguity_component_time_assessment(component, timestamp)
        return {
            "decision": decision,
            "reason": reason,
            "component_key": component.lease_key,
            "component_id": component.component_id,
            "evidence_id": component.evidence_id,
            "generation": component.generation,
            "publisher_node_id": component.publisher_node_id,
            "publisher_epoch": component.publisher_epoch,
            "state_valid_timestamp": component.state_valid_timestamp,
            "measurement_timestamp": component.measurement_timestamp,
            "arrival_timestamp": component.arrival_timestamp,
            "published_at": component.published_at,
            "d2_consumption_timestamp": float(timestamp),
            "component_age_seconds": component_age_seconds,
            "time_decision": time_decision,
            "max_component_age_seconds": (
                self.ambiguity_hold_config.max_component_age_seconds
            ),
            "member_count": len(component.members),
            "observation_count": len(component.observations),
            "lease_extended": bool(lease_extended),
            "soft_deadline": None if lease is None else lease.soft_deadline,
            "hard_deadline": None if lease is None else lease.hard_deadline,
            "online_truth_used": False,
        }

    def _remember_ambiguity_component_generation(
        self,
        component_key: str,
        generation: int,
    ) -> None:
        if component_key not in self._ambiguity_component_generations:
            self._ambiguity_component_history_order.append(component_key)
        self._ambiguity_component_generations[component_key] = generation
        capacity = self.ambiguity_hold_config.max_component_history
        while len(self._ambiguity_component_generations) > capacity:
            oldest = self._ambiguity_component_history_order.popleft()
            if oldest in self._ambiguity_leases:
                self._ambiguity_component_history_order.append(oldest)
                continue
            self._ambiguity_component_generations.pop(oldest, None)
            self._ambiguity_component_hard_deadlines.pop(oldest, None)

    def _remember_ambiguity_evidence(self, evidence_id: str) -> None:
        if evidence_id in self._ambiguity_evidence_history:
            return
        self._ambiguity_evidence_history.add(evidence_id)
        self._ambiguity_evidence_history_order.append(evidence_id)
        capacity = self.ambiguity_hold_config.max_component_history
        while len(self._ambiguity_evidence_history) > capacity:
            oldest = self._ambiguity_evidence_history_order.popleft()
            self._ambiguity_evidence_history.discard(oldest)

    def _bound_track_ids(
        self,
        source_keys: Iterable[str],
    ) -> set[str]:
        active_bindings = self._active_source_bindings()
        return {
            active_bindings[source_key]
            for source_key in source_keys
            if source_key in active_bindings
        }

    def _active_source_bindings(self) -> dict[str, str]:
        active_ids = {
            track.global_track_id for track in self.active_tracks()
        }
        return {
            source_key: track_id
            for source_key, track_id in self._source_bindings.items()
            if track_id in active_ids
        }

    def _active_ambiguity_hold_track_ids(self) -> set[str]:
        active_bindings = self._active_source_bindings()
        active_ids = set(active_bindings.values())
        held: set[str] = set()
        for lease in self._ambiguity_leases.values():
            lease.track_ids.update(
                active_bindings[source_key]
                for source_key in lease.member_source_keys
                if source_key in active_bindings
            )
            lease.track_ids.intersection_update(active_ids)
            held.update(lease.track_ids)
        return held

    def _partition_ambiguity_member_detections(
        self,
        detections: list[Detection3D],
        *,
        held_source_keys: set[str],
        held_track_ids: set[str],
        timestamp: float,
    ) -> tuple[list[Detection3D], list[dict[str, Any]]]:
        if not held_source_keys:
            return list(detections), []
        accepted: list[Detection3D] = []
        events: list[dict[str, Any]] = []
        active_bindings = self._active_source_bindings()
        for detection in detections:
            source_key = detection.source_key
            if source_key is None or source_key not in held_source_keys:
                accepted.append(detection)
                continue
            bound_track_id = active_bindings.get(source_key)
            if bound_track_id in held_track_ids:
                prevented_action = "hit"
            elif bound_track_id is None:
                prevented_action = "birth"
            else:
                prevented_action = "rebind"
            events.append(
                {
                    "detection_id": detection.detection_id,
                    "source_key": source_key,
                    "bound_global_track_id": bound_track_id,
                    "state_valid_timestamp": float(timestamp),
                    "decision": "prediction_only_ambiguity_hold",
                    "prevented_action": prevented_action,
                    "measurement_update_applied": False,
                    "hit_added": False,
                    "miss_added": False,
                    "birth_allowed": False,
                    "rebind_allowed": False,
                    "online_truth_used": False,
                }
            )
        return accepted, events

    def _transition_observation_claim_status(
        self,
        claim: _ObservationClaim,
        new_status: str,
    ) -> None:
        if claim.status == new_status:
            return
        self._decrement_observation_claim_status(claim.status)
        claim.status = new_status
        self._observation_claim_status_counts[new_status] += 1

    def _decrement_observation_claim_status(self, status: str) -> None:
        self._observation_claim_status_counts[status] -= 1
        if self._observation_claim_status_counts[status] <= 0:
            self._observation_claim_status_counts.pop(status, None)

    def _finalize_ambiguity_diagnostics(
        self,
        diagnostics: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = dict(diagnostics)
        result["prevented_counts"] = dict(
            sorted(dict(diagnostics["prevented_counts"]).items())
        )
        result["component_event_counts_cumulative"] = dict(
            sorted(self._ambiguity_component_event_counts.items())
        )
        result["prevented_counts_cumulative"] = dict(
            sorted(self._ambiguity_prevented_counts.items())
        )
        result["config"] = self.ambiguity_hold_config.to_dict()
        result["claim_states"] = [
            "unseen",
            "reserved_ambiguous",
            "consumed",
        ]
        result["resolution_mode"] = "lease_expiry_only_v1"
        result["online_truth_used"] = False
        return result

    def _coalesce_duplicate_tracks(
        self,
        timestamp: float,
        *,
        updated_track_ids: set[str],
        protected_track_ids: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Merge only provenance-linked, statistically compatible duplicates."""

        protected = set() if protected_track_ids is None else protected_track_ids
        events: list[dict[str, Any]] = []
        aliases: dict[str, str] = {}
        active = self.active_tracks()
        for left_index, left in enumerate(active):
            if left.lifecycle_state == TrackLifecycleState.DROPPED:
                continue
            if left.global_track_id in protected:
                continue
            for right in active[left_index + 1 :]:
                if left.lifecycle_state == TrackLifecycleState.DROPPED:
                    break
                if right.lifecycle_state == TrackLifecycleState.DROPPED:
                    continue
                if right.global_track_id in protected:
                    continue
                if (
                    left.global_track_id in updated_track_ids
                    and right.global_track_id in updated_track_ids
                ):
                    continue
                shared_observations = sorted(
                    self._track_observation_keys.get(left.global_track_id, set())
                    & self._track_observation_keys.get(right.global_track_id, set())
                )
                shared_sources = sorted(
                    left.source_track_keys & right.source_track_keys
                )
                if not shared_observations and not shared_sources:
                    continue
                position_distance = _quadratic_form(
                    left.covariance[:3, :3] + right.covariance[:3, :3],
                    left.position_ned - right.position_ned,
                )
                velocity_distance = _quadratic_form(
                    left.covariance[3:, 3:] + right.covariance[3:, 3:],
                    left.velocity_ned - right.velocity_ned,
                )
                if (
                    position_distance
                    > self.duplicate_coalescence_position_gate_threshold
                    or velocity_distance
                    > self.duplicate_coalescence_velocity_gate_threshold
                ):
                    continue
                survivor, duplicate = self._select_duplicate_survivor(left, right)
                self._merge_duplicate_into_survivor(survivor, duplicate)
                aliases[duplicate.global_track_id] = survivor.global_track_id
                event = {
                    "timestamp": float(timestamp),
                    "survivor_global_track_id": survivor.global_track_id,
                    "duplicate_global_track_id": duplicate.global_track_id,
                    "shared_observation_count": len(shared_observations),
                    "shared_source_track_count": len(shared_sources),
                    "position_mahalanobis_squared": float(position_distance),
                    "velocity_mahalanobis_squared": float(velocity_distance),
                    "survivor_policy": (
                        "lifecycle_maturity_then_oldest_creation_then_hits_then_id"
                    ),
                    "online_truth_used": False,
                }
                events.append(event)
                self._duplicate_coalescence_count += 1
        return events, aliases

    @staticmethod
    def _select_duplicate_survivor(
        left: GlobalTrack3D,
        right: GlobalTrack3D,
    ) -> tuple[GlobalTrack3D, GlobalTrack3D]:
        maturity = {
            TrackLifecycleState.ENGAGEABLE: 3,
            TrackLifecycleState.CONFIRMED: 2,
            TrackLifecycleState.TENTATIVE: 1,
            TrackLifecycleState.LOST: 0,
            TrackLifecycleState.DROPPED: -1,
        }

        def key(track: GlobalTrack3D) -> tuple[float | str, ...]:
            return (
                -float(maturity[track.lifecycle_state]),
                float(track.created_at),
                -float(track.hits),
                float(track.misses),
                track.global_track_id,
            )

        survivor, duplicate = sorted((left, right), key=key)
        return survivor, duplicate

    def _merge_duplicate_into_survivor(
        self,
        survivor: GlobalTrack3D,
        duplicate: GlobalTrack3D,
    ) -> None:
        (
            survivor.state,
            survivor.covariance,
            covariance_consistency,
        ) = _covariance_intersection(
            survivor.state,
            survivor.covariance,
            duplicate.state,
            duplicate.covariance,
            first_weight=0.5,
        )
        if covariance_consistency is None:
            survivor.ensure_covariance_consistency()
        else:
            survivor.covariance_consistency = dict(covariance_consistency)
        survivor.hits = max(survivor.hits, duplicate.hits)
        survivor.consecutive_hits = max(
            survivor.consecutive_hits,
            duplicate.consecutive_hits,
        )
        survivor.misses = min(survivor.misses, duplicate.misses)
        if duplicate.last_update_time > survivor.last_update_time:
            survivor.last_detection_id = duplicate.last_detection_id
        survivor.last_update_time = max(
            survivor.last_update_time, duplicate.last_update_time
        )
        survivor.age = max(survivor.age, duplicate.age)
        survivor.identity_confidence = max(
            survivor.identity_confidence,
            duplicate.identity_confidence,
        )
        survivor.source_track_keys.update(duplicate.source_track_keys)
        survivor.append_history(
            f"duplicate_survivor:{duplicate.global_track_id}"
        )

        duplicate.lifecycle_state = TrackLifecycleState.DROPPED
        duplicate.append_history(
            f"duplicate_coalesced_into:{survivor.global_track_id}"
        )
        self._drop_count += 1
        for source_key in tuple(duplicate.source_track_keys):
            self._source_bindings[source_key] = survivor.global_track_id
        duplicate_keys = self._track_observation_keys.pop(
            duplicate.global_track_id,
            set(),
        )
        survivor_keys = self._track_observation_keys[survivor.global_track_id]
        survivor_count_before = len(survivor_keys)
        survivor_keys.update(duplicate_keys)
        self._track_observation_key_count += (
            len(survivor_keys) - survivor_count_before - len(duplicate_keys)
        )
        for observation_key in duplicate_keys:
            claim = self._observation_claims.get(observation_key)
            if claim is not None:
                claim.global_track_id = survivor.global_track_id

    def _bind_source(
        self,
        track: GlobalTrack3D,
        detection: Detection3D,
    ) -> dict[str, str] | None:
        source_key = detection.source_key
        if source_key is None:
            return None
        existing_id = self._source_bindings.get(source_key)
        existing_track = self.tracks.get(existing_id) if existing_id is not None else None
        if (
            existing_track is not None
            and existing_track.lifecycle_state != TrackLifecycleState.DROPPED
            and existing_id != track.global_track_id
        ):
            return {
                "source_track_key": source_key,
                "bound_global_track_id": str(existing_id),
                "matched_global_track_id": track.global_track_id,
                "reason": "source_track_binding_conflict",
            }
        self._source_bindings[source_key] = track.global_track_id
        track.source_track_keys.add(source_key)
        return None

    def _refresh_track_quality(
        self,
        result: AssociationResult,
        created_track_ids: set[str],
    ) -> None:
        matched_track_ids = {pair.track_id for pair in result.matched_pairs}
        candidate_counts = result.metadata.get("candidate_counts_by_track", {})
        quality_by_track: dict[str, float] = {}
        risk_by_track: dict[str, float] = {}
        for track in self.active_tracks():
            covariance_trace = float(np.trace(track.covariance[:3, :3]))
            covariance_quality = 1.0 / (1.0 + covariance_trace / 30.0)
            hit_quality = min(1.0, track.hits / max(self.engageable_hits, 1))
            miss_quality = max(
                0.0, 1.0 - track.misses / max(self.drop_miss_threshold, 1)
            )
            quality = float(
                np.clip(
                    0.45 * covariance_quality + 0.35 * hit_quality + 0.20 * miss_quality,
                    0.0,
                    1.0,
                )
            )
            candidate_count = int(candidate_counts.get(track.global_track_id, 0))
            ambiguity_risk = min(0.4, max(0, candidate_count - 1) * 0.15)
            miss_risk = min(
                0.4,
                track.misses / max(self.drop_miss_threshold, 1) * 0.4,
            )
            unmatched_risk = (
                0.0
                if track.global_track_id in matched_track_ids
                or track.global_track_id in created_track_ids
                else 0.15
            )
            risk = float(
                np.clip(
                    0.35 * (1.0 - quality)
                    + ambiguity_risk
                    + miss_risk
                    + unmatched_risk,
                    0.0,
                    1.0,
                )
            )
            track.track_quality = quality
            track.association_risk = risk
            quality_by_track[track.global_track_id] = quality
            risk_by_track[track.global_track_id] = risk
        result.metadata["track_quality_by_track"] = quality_by_track
        result.metadata["association_risk_by_track"] = risk_by_track
        result.metadata["max_track_association_risk"] = (
            max(risk_by_track.values()) if risk_by_track else 0.0
        )


def _linear_joseph_update(
    state: np.ndarray,
    covariance: np.ndarray,
    measurement: np.ndarray,
    measurement_matrix: np.ndarray,
    measurement_covariance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    residual = measurement - measurement_matrix @ state
    innovation = (
        measurement_matrix @ covariance @ measurement_matrix.T
        + measurement_covariance
    )
    covariance_measurement_transpose = covariance @ measurement_matrix.T
    try:
        gain = np.linalg.solve(
            innovation,
            covariance_measurement_transpose.T,
        ).T
    except np.linalg.LinAlgError:
        gain = covariance_measurement_transpose @ np.linalg.pinv(innovation)
    identity = np.eye(covariance.shape[0], dtype=float)
    joseph = identity - gain @ measurement_matrix
    updated_state = state + gain @ residual
    updated_covariance = (
        joseph @ covariance @ joseph.T
        + gain @ measurement_covariance @ gain.T
    )
    return updated_state, updated_covariance


def _covariance_intersection(
    first_state: np.ndarray,
    first_covariance: np.ndarray,
    second_state: np.ndarray,
    second_covariance: np.ndarray,
    *,
    first_weight: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any] | None]:
    """Fuse correlated estimates without assuming independent information."""

    first_precision = _symmetric_inverse(first_covariance)
    second_precision = _symmetric_inverse(second_covariance)
    second_weight = 1.0 - first_weight
    combined_precision = (
        first_weight * first_precision + second_weight * second_precision
    )
    combined_covariance = _symmetric_inverse(combined_precision)
    information_state = (
        first_weight * first_precision @ first_state
        + second_weight * second_precision @ second_state
    )
    combined_state = combined_covariance @ information_state
    combined_covariance, consistency = govern_covariance(
        combined_covariance,
        (6, 6),
        "covariance-intersection posterior",
    )
    prevalidated_consistency = (
        consistency if not consistency["covariance_regularized"] else None
    )
    return combined_state, combined_covariance, prevalidated_consistency


def _inflate_velocity_covariance(
    covariance: np.ndarray,
    inflation: float,
) -> np.ndarray:
    if inflation <= 1.0:
        return covariance.copy()
    transform = np.eye(6, dtype=float)
    transform[3:, 3:] *= sqrt(inflation)
    inflated = transform @ covariance @ transform.T
    governed, _ = govern_covariance(
        inflated,
        (6, 6),
        "velocity-gated six-state covariance",
    )
    return governed


def _symmetric_inverse(covariance: np.ndarray) -> np.ndarray:
    symmetric = 0.5 * (covariance + covariance.T)
    try:
        inverse = np.linalg.inv(symmetric)
    except np.linalg.LinAlgError:
        inverse = np.linalg.pinv(symmetric)
    return 0.5 * (inverse + inverse.T)


def _quadratic_form(covariance: np.ndarray, residual: np.ndarray) -> float:
    try:
        solved = np.linalg.solve(covariance, residual)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(covariance) @ residual
    return float(max(0.0, residual.T @ solved))


def _finite_value_summary(values: Iterable[float | None]) -> dict[str, Any]:
    array = np.asarray(
        [float(value) for value in values if value is not None],
        dtype=float,
    )
    array = array[np.isfinite(array)]
    if not array.size:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "p90": None,
            "maximum": None,
        }
    return {
        "count": int(array.size),
        "minimum": float(np.min(array)),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90.0)),
        "maximum": float(np.max(array)),
    }


def _optional_nonnegative_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    candidate = float(value)
    if not np.isfinite(candidate) or candidate < 0.0:
        return None
    return candidate


def mahalanobis_squared_3d(
    track: GlobalTrack3D,
    detection: Detection3D,
) -> float:
    """Return the three-dimensional position innovation Mahalanobis distance."""

    residual = detection.position_ned - POSITION_H_3D @ track.state
    innovation = (
        POSITION_H_3D @ track.covariance @ POSITION_H_3D.T + detection.covariance
    )
    try:
        solved = np.linalg.solve(innovation, residual)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(innovation) @ residual
    return float(residual.T @ solved)


def _velocity_mahalanobis_squared(
    track: GlobalTrack3D,
    detection: Detection3D,
) -> float | None:
    if detection.velocity_ned is None or detection.velocity_covariance is None:
        return None
    residual = detection.velocity_ned - track.velocity_ned
    covariance = track.covariance[3:, 3:] + detection.velocity_covariance
    try:
        solved = np.linalg.solve(covariance, residual)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(covariance) @ residual
    return float(residual.T @ solved)


def _candidate_components(
    track_count: int,
    detection_count: int,
    edges: dict[tuple[int, int], _SparseEdge],
) -> list[tuple[list[int], list[int]]]:
    del track_count, detection_count
    detections_by_track: dict[int, set[int]] = defaultdict(set)
    tracks_by_detection: dict[int, set[int]] = defaultdict(set)
    for track_index, detection_index in edges:
        detections_by_track[track_index].add(detection_index)
        tracks_by_detection[detection_index].add(track_index)

    components: list[tuple[list[int], list[int]]] = []
    visited_tracks: set[int] = set()
    visited_detections: set[int] = set()
    for root_track in sorted(detections_by_track):
        if root_track in visited_tracks:
            continue
        component_tracks: set[int] = set()
        component_detections: set[int] = set()
        pending_tracks = [root_track]
        while pending_tracks:
            track_index = pending_tracks.pop()
            if track_index in component_tracks:
                continue
            component_tracks.add(track_index)
            visited_tracks.add(track_index)
            for detection_index in detections_by_track[track_index]:
                if detection_index not in component_detections:
                    component_detections.add(detection_index)
                    visited_detections.add(detection_index)
                    pending_tracks.extend(tracks_by_detection[detection_index])
        components.append((sorted(component_tracks), sorted(component_detections)))
    return components


def _maximum_position_variance(detections: list[Detection3D]) -> float:
    if not detections:
        return 0.0
    covariance_eigenvalues = np.linalg.eigvalsh(
        np.asarray([item.covariance for item in detections])
    )
    return max(0.0, float(np.max(covariance_eigenvalues[:, -1])))


def _ambiguity_from_sparse_edges(
    track_count: int,
    edges: dict[tuple[int, int], _SparseEdge],
) -> tuple[float, float | None]:
    costs_by_track: dict[int, list[float]] = defaultdict(list)
    for edge in edges.values():
        costs_by_track[edge.track_index].append(edge.cost)
    scores: list[float] = []
    margins: list[float] = []
    for track_index in range(track_count):
        costs = sorted(costs_by_track.get(track_index, ()))
        if len(costs) < 2:
            scores.append(0.0)
            continue
        margin = max(0.0, costs[1] - costs[0])
        margins.append(margin)
        scores.append(exp(-0.5 * margin))
    return (
        float(np.mean(scores)) if scores else 0.0,
        min(margins) if margins else None,
    )


def _cv_transition_and_process_noise(
    dt: float,
    acceleration_noise: float,
) -> tuple[np.ndarray, np.ndarray]:
    identity = np.eye(3, dtype=float)
    transition = np.block(
        [[identity, dt * identity], [np.zeros((3, 3), dtype=float), identity]]
    )
    dt2 = dt * dt
    dt3 = dt2 * dt
    dt4 = dt2 * dt2
    process = acceleration_noise * np.block(
        [
            [(dt4 / 4.0) * identity, (dt3 / 2.0) * identity],
            [(dt3 / 2.0) * identity, dt2 * identity],
        ]
    )
    return transition, process


def _scan_timestamp(
    detections: list[Detection3D],
    timestamp: float | None,
) -> float:
    if timestamp is None:
        if not detections:
            raise ValueError("timestamp is required for an empty detection scan")
        timestamp = detections[0].measurement_timestamp
    result = float(timestamp)
    if not np.isfinite(result) or result < 0.0:
        raise ValueError("scan timestamp must be finite and non-negative")
    if any(abs(item.measurement_timestamp - result) > 1.0e-9 for item in detections):
        raise ValueError("all detections in a scan must share measurement_timestamp")
    return result


def _overlap_rate(counts: Iterable[int]) -> float:
    values = [int(item) for item in counts]
    return _rate(sum(1 for item in values if item > 1), len(values))


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _risk_level(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _single_source_node(detections: list[Detection3D]) -> str | None:
    values = {item.source_node_id for item in detections if item.source_node_id}
    return next(iter(values)) if len(values) == 1 else None


# Compatibility aliases use explicit names and retain GNN's tracking meaning.
SparseGNNHungarianAssociator3D = Sparse3DGNNHungarianAssociator
Sparse3DTracker = Scalable3DTracker
