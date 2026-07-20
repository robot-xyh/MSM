"""Sparse global-nearest-neighbor association for six-state NED tracks."""

from __future__ import annotations

from collections import defaultdict, deque
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


@dataclass(frozen=True, slots=True)
class _SparseEdge:
    track_index: int
    detection_index: int
    cost: float
    mahalanobis_squared: float
    velocity_mahalanobis_squared: float | None


@dataclass(slots=True)
class Sparse3DGNNHungarianAssociator:
    """Global nearest-neighbor association on a KD-tree candidate graph.

    ``GNN`` retains its established tracking meaning: global nearest neighbor.
    This class is deterministic optimization code and contains no graph neural
    network or learned edge scorer.
    """

    gate_threshold: float = CHI2_GATE_3D_99_PERCENT
    velocity_weight: float = 0.25
    source_continuity_bias: float = 2.0
    minimum_query_radius_m: float = 0.0
    large_cost: float = LARGE_SPARSE_COST

    def __post_init__(self) -> None:
        for name in ("gate_threshold", "large_cost"):
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
        tree = (
            cKDTree(np.asarray([item.position_ned for item in detection_list]))
            if detection_list
            else None
        )
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

        if tree is not None:
            for track_index, track in enumerate(track_list):
                query_radius = self._conservative_query_radius(
                    track,
                    maximum_detection_variance,
                )
                query_radius_by_track[track.global_track_id] = query_radius
                candidate_indices = sorted(
                    int(index)
                    for index in tree.query_ball_point(
                        track.position_ned,
                        r=query_radius,
                    )
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
                    if velocity_distance is not None:
                        cost += self.velocity_weight * velocity_distance
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
        component_matrix_pair_count = 0
        peak_component_pair_count = 0

        for track_indices, detection_indices in components:
            pair_count = len(track_indices) * len(detection_indices)
            component_matrix_pair_count += pair_count
            peak_component_pair_count = max(peak_component_pair_count, pair_count)
            local_costs = np.full(
                (len(track_indices), len(detection_indices)),
                self.large_cost,
                dtype=float,
            )
            for local_row, track_index in enumerate(track_indices):
                for local_column, detection_index in enumerate(detection_indices):
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
        candidate_density = _rate(candidate_edge_count, dense_pair_count)
        metadata: dict[str, Any] = {
            "state_order": list(STATE_ORDER_3D),
            "working_frame": "NED",
            "innovation_dimension": 3,
            "gate_metric": "3d_position_mahalanobis_squared",
            "gate_threshold": self.gate_threshold,
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
        return AssociationResult(
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
    confirmation_hits: int = 2
    engageable_hits: int = 4
    lost_miss_threshold: int = 2
    drop_miss_threshold: int = 5
    engageable_position_covariance_trace: float = 30.0
    create_tracks_from_unmatched_detections: bool = True
    track_history_limit: int = 32
    frame_log_limit: int = 256
    global_track_id_prefix: str = "GT3D-"
    tracks: dict[str, GlobalTrack3D] = field(default_factory=dict, init=False)
    _next_track_number: int = field(default=1, init=False)
    _last_timestamp: float | None = field(default=None, init=False)
    _source_bindings: dict[str, str] = field(default_factory=dict, init=False)
    _frame_logs: deque[dict[str, Any]] = field(init=False)
    _runtime_seconds: deque[float] = field(init=False)
    _frame_count: int = field(default=0, init=False)
    _birth_count: int = field(default=0, init=False)
    _lost_count: int = field(default=0, init=False)
    _drop_count: int = field(default=0, init=False)
    _total_candidate_edges: int = field(default=0, init=False)
    _total_dense_pairs: int = field(default=0, init=False)
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
        for name in (
            "confirmation_hits",
            "engageable_hits",
            "lost_miss_threshold",
            "drop_miss_threshold",
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

        self.predict_all(timestamp)
        result = self.associator.associate(
            self.active_tracks(),
            detection_list,
            timestamp,
        )
        detections_by_id = {item.detection_id: item for item in detection_list}
        detection_to_track: dict[str, str] = {}
        source_binding_conflicts: list[dict[str, str]] = []

        for pair in result.matched_pairs:
            track = self.tracks[pair.track_id]
            detection = detections_by_id[pair.detection_id]
            self._kalman_update(track, detection)
            detection_to_track[detection.detection_id] = track.global_track_id
            conflict = self._bind_source(track, detection)
            if conflict is not None:
                source_binding_conflicts.append(conflict)
            self._advance_after_hit(track)

        for track_id in result.unmatched_track_ids:
            track = self.tracks.get(track_id)
            if track is not None and track.lifecycle_state != TrackLifecycleState.DROPPED:
                self._mark_missed(track)

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

        self._refresh_track_quality(result, set(created_track_ids_by_detection.values()))
        tracker_runtime = perf_counter() - started
        result.metadata.update(
            {
                "detection_to_track": dict(sorted(detection_to_track.items())),
                "created_track_ids_by_detection": dict(
                    sorted(created_track_ids_by_detection.items())
                ),
                "source_track_bindings": dict(sorted(self._source_bindings.items())),
                "source_binding_conflicts": source_binding_conflicts,
                "active_track_count": len(self.active_tracks()),
                "tracker_runtime_seconds": tracker_runtime,
                "track_history_limit": self.track_history_limit,
                "frame_log_limit": self.frame_log_limit,
                "global_track_id_owner": "D2_center",
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
                    "source_binding_conflict_count": len(source_binding_conflicts),
                    "global_track_id_owner": "D2_center",
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
                "unmatched_track_count": len(result.unmatched_track_ids),
                "candidate_edge_count": int(result.metadata["candidate_edge_count"]),
                "dense_pair_count": int(result.metadata["dense_pair_count"]),
                "risk_score": float(result.metadata["risk_score"]),
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

    def _kalman_update(self, track: GlobalTrack3D, detection: Detection3D) -> None:
        residual = detection.position_ned - POSITION_H_3D @ track.state
        innovation = (
            POSITION_H_3D @ track.covariance @ POSITION_H_3D.T
            + detection.covariance
        )
        try:
            gain = track.covariance @ POSITION_H_3D.T @ np.linalg.inv(innovation)
        except np.linalg.LinAlgError:
            gain = track.covariance @ POSITION_H_3D.T @ np.linalg.pinv(innovation)
        identity = np.eye(6, dtype=float)
        track.state = track.state + gain @ residual
        joseph = identity - gain @ POSITION_H_3D
        track.covariance = (
            joseph @ track.covariance @ joseph.T
            + gain @ detection.covariance @ gain.T
        )
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
        if track.misses >= self.drop_miss_threshold:
            track.lifecycle_state = TrackLifecycleState.DROPPED
        elif track.misses >= self.lost_miss_threshold:
            track.lifecycle_state = TrackLifecycleState.LOST
        track.append_history("miss")
        if old_state != TrackLifecycleState.LOST and track.lifecycle_state == TrackLifecycleState.LOST:
            self._lost_count += 1
        if old_state != TrackLifecycleState.DROPPED and track.lifecycle_state == TrackLifecycleState.DROPPED:
            self._drop_count += 1
            for source_key in tuple(track.source_track_keys):
                if self._source_bindings.get(source_key) == track.global_track_id:
                    self._source_bindings.pop(source_key, None)

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
    return max(
        max(0.0, float(np.linalg.eigvalsh(item.covariance)[-1]))
        for item in detections
    )


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
