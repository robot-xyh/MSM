"""Sparse global-nearest-neighbor association for six-state NED tracks."""

from __future__ import annotations

import heapq
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from math import exp, sqrt
from time import perf_counter
from typing import Any, Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from .models import (
    AssociationResult,
    AssociationRiskSummary,
    MatchedPair,
    RejectedPair,
    TrackLifecycleState,
    govern_covariance,
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


@dataclass(slots=True)
class _ObservationClaim:
    """First-consumption record for one D1 observation lineage token."""

    evidence: _ObservationEvidence
    first_detection_id: str
    first_state_timestamp: float
    global_track_id: str | None = None
    replay_count: int = 0
    last_replay_state_timestamp: float | None = None


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
    ) -> AssociationResult:
        """Solve sparse GNN/Hungarian without allocating a full pair matrix."""

        started = perf_counter()
        track_list = sorted(tracks, key=lambda item: item.global_track_id)
        detection_list = sorted(detections, key=lambda item: item.detection_id)
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

    def step(
        self,
        detections: Iterable[Detection3D],
        timestamp: float | None = None,
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

        (
            fresh_detections,
            replay_quarantine_events,
            observation_evidence_by_detection,
        ) = self._partition_observation_freshness(detection_list, timestamp)
        frame_rejection_reason_counts = Counter(
            str(item["reason"]) for item in replay_quarantine_events
        )

        self.predict_all(timestamp)
        result = self.associator.associate(
            self.active_tracks(),
            fresh_detections,
            timestamp,
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

        replay_coast_events: list[dict[str, Any]] = []
        missed_track_ids: list[str] = []
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
        if self.create_tracks_from_unmatched_detections:
            for detection_id in result.unmatched_detection_ids:
                detection = detections_by_id[detection_id]
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

        self._refresh_track_quality(result, set(created_track_ids_by_detection.values()))
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
        result.metadata.update(
            {
                "detection_to_track": dict(sorted(detection_to_track.items())),
                "input_detection_count": len(detection_list),
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
                "observation_claim_ledger": self._observation_claim_ledger_summary(),
                "observation_claim_eviction_count": len(claim_eviction_events),
                "observation_claim_eviction_events": claim_eviction_events,
                "created_track_ids_by_detection": dict(
                    sorted(created_track_ids_by_detection.items())
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
                    "observation_claim_ledger": (
                        self._observation_claim_ledger_summary()
                    ),
                    "duplicate_coalescence_count": len(coalescence_events),
                    "source_binding_conflict_count": len(source_binding_conflicts),
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
                "state_update_mode_counts": dict(sorted(update_mode_counts.items())),
                "velocity_innovation_gate_count": velocity_gate_count,
                "tracker_runtime_seconds": tracker_runtime,
            }
        )
        self._last_timestamp = timestamp
        return result

    def predict_all(self, timestamp: float) -> None:
        for track in self.active_tracks():
            dt = max(float(timestamp) - track.timestamp, 0.0)
            if dt <= 0.0:
                continue
            transition, process = _cv_transition_and_process_noise(
                dt,
                self.process_noise_acceleration,
            )
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
                    reason = self._replay_reason(existing.evidence, evidence)
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
        source_timestamp: float | None = None
        if raw_timestamp is not None:
            candidate = float(raw_timestamp)
            if np.isfinite(candidate) and candidate >= 0.0:
                source_timestamp = candidate
        return _ObservationEvidence(
            key=f"{source_namespace}::{observation_id}",
            observation_id=observation_id,
            source_namespace=source_namespace,
            source_measurement_timestamp=source_timestamp,
        )

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
        self._observation_claims[claim.evidence.key] = claim
        if claim.evidence.source_measurement_timestamp is not None:
            heapq.heappush(
                self._observation_claim_eviction_heap,
                (
                    claim.evidence.source_measurement_timestamp,
                    claim.evidence.key,
                ),
            )
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
            if claim.evidence.source_measurement_timestamp != source_timestamp:
                continue
            self._observation_claims.pop(key)
            if claim.global_track_id is not None:
                track_keys = self._track_observation_keys.get(claim.global_track_id)
                if track_keys is not None:
                    track_keys.discard(key)
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
        undated_count = sum(
            claim.evidence.source_measurement_timestamp is None
            for claim in self._observation_claims.values()
        )
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
            "undated_non_evictable_count": int(undated_count),
            "eviction_index_count": len(self._observation_claim_eviction_heap),
            "track_observation_key_count": sum(
                len(keys) for keys in self._track_observation_keys.values()
            ),
            "track_observation_index_track_count": len(
                self._track_observation_keys
            ),
            "tombstone_count": 0,
            "anti_replay_mode": "trusted_measurement_time_safe_watermark",
            "online_truth_used": False,
        }

    def _assign_observation_claim(
        self,
        evidence: _ObservationEvidence,
        global_track_id: str,
    ) -> None:
        claim = self._observation_claims[evidence.key]
        claim.global_track_id = str(global_track_id)
        self._track_observation_keys[str(global_track_id)].add(evidence.key)

    def _coalesce_duplicate_tracks(
        self,
        timestamp: float,
        *,
        updated_track_ids: set[str],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Merge only provenance-linked, statistically compatible duplicates."""

        events: list[dict[str, Any]] = []
        aliases: dict[str, str] = {}
        active = self.active_tracks()
        for left_index, left in enumerate(active):
            if left.lifecycle_state == TrackLifecycleState.DROPPED:
                continue
            for right in active[left_index + 1 :]:
                if left.lifecycle_state == TrackLifecycleState.DROPPED:
                    break
                if right.lifecycle_state == TrackLifecycleState.DROPPED:
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
        self._track_observation_keys[survivor.global_track_id].update(
            duplicate_keys
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
