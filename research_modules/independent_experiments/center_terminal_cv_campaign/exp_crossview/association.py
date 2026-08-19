"""Geometry-first anonymous association and multi-camera aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
from itertools import combinations
import math
from typing import Mapping, Protocol, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..common.contracts import LocalVisualTrackRecord
from .config import CameraCalibration, CrossViewConfig
from .contracts import (
    AssociationAudit,
    CandidateEdge,
    CrossViewMetrics,
    CrossViewResult,
    PairMatch,
    UnifiedTargetCluster,
    assert_online_anonymous,
    split_track_key,
    track_key,
)
from .camera_pairs import CameraPairPlan, full_camera_pair_plan
from .geometry import (
    align_track_histories,
    closest_ray_intersection,
    motion_fit_quality,
    normalize,
    recognition_extent,
)


class CandidateEdgeScorer(Protocol):
    """Optional learned scorer. Geometry decides which edges it may see."""

    def score(
        self,
        histories_a: Mapping[str, Sequence[LocalVisualTrackRecord]],
        histories_b: Mapping[str, Sequence[LocalVisualTrackRecord]],
        candidates: Sequence[CandidateEdge],
        calibration_a: CameraCalibration,
        calibration_b: CameraCalibration,
    ) -> Mapping[tuple[str, str], float]: ...


def _angular_pixel_error(
    midpoint: np.ndarray,
    origin: np.ndarray,
    direction: np.ndarray,
    focal_length_px: float,
) -> float:
    predicted = normalize(midpoint - origin)
    angle = math.acos(float(np.clip(np.dot(predicted, direction), -1.0, 1.0)))
    return float(focal_length_px * math.tan(min(angle, math.radians(80.0))))


def _candidate_edge(
    history_a: Sequence[LocalVisualTrackRecord],
    history_b: Sequence[LocalVisualTrackRecord],
    calibration_a: CameraCalibration,
    calibration_b: CameraCalibration,
    config: CrossViewConfig,
) -> CandidateEdge:
    first_a, first_b = history_a[0], history_b[0]
    if first_a.camera_id == first_b.camera_id:
        raise ValueError("cross-view candidates require two different cameras")
    aligned = align_track_histories(
        history_a, history_b, calibration_a, calibration_b, config
    )
    latest_offset = abs(
        float(history_a[-1].measurement_timestamp)
        - float(history_b[-1].measurement_timestamp)
    )
    intersections = []
    reprojection_errors: list[float] = []
    valid_times: list[float] = []
    valid_points: list[np.ndarray] = []
    bbox_log_differences: list[float] = []
    reject_reasons: list[str] = []
    for sample in aligned:
        intersection = closest_ray_intersection(
            sample.origin_a_ned_m,
            sample.direction_a_ned,
            sample.origin_b_ned_m,
            sample.direction_b_ned,
        )
        intersections.append(intersection)
        if intersection.depth_a_m <= 0.0 or intersection.depth_b_m <= 0.0:
            continue
        error_a = _angular_pixel_error(
            intersection.midpoint_ned_m,
            sample.origin_a_ned_m,
            sample.direction_a_ned,
            calibration_a.fx_px,
        )
        error_b = _angular_pixel_error(
            intersection.midpoint_ned_m,
            sample.origin_b_ned_m,
            sample.direction_b_ned,
            calibration_b.fx_px,
        )
        reprojection_errors.append(max(error_a, error_b))
        valid_times.append(sample.timestamp)
        valid_points.append(intersection.midpoint_ned_m)
        inferred_size_a = sample.extent_a_px * intersection.depth_a_m / calibration_a.fx_px
        inferred_size_b = sample.extent_b_px * intersection.depth_b_m / calibration_b.fx_px
        bbox_log_differences.append(
            abs(math.log(max(inferred_size_a, 1.0e-3) / max(inferred_size_b, 1.0e-3)))
        )

    sample_count = len(valid_points)
    separation_values = [
        item.separation_m
        for item in intersections
        if item.depth_a_m > 0.0 and item.depth_b_m > 0.0
    ]
    angle_values = [
        item.angle_deg
        for item in intersections
        if item.depth_a_m > 0.0 and item.depth_b_m > 0.0
    ]
    median_separation = (
        float(np.median(separation_values))
        if separation_values
        else config.maximum_ray_separation_m * 10.0
    )
    median_reprojection = (
        float(np.median(reprojection_errors))
        if reprojection_errors
        else config.maximum_reprojection_error_px * 10.0
    )
    intersection_angle = float(np.median(angle_values)) if angle_values else 0.0
    bbox_difference = (
        float(np.median(bbox_log_differences)) if bbox_log_differences else 10.0
    )
    motion_error, motion_turn = motion_fit_quality(valid_times, valid_points)
    midpoint = tuple(float(value) for value in valid_points[-1]) if valid_points else None

    if not aligned:
        reject_reasons.append("no_time_aligned_observation")
    if latest_offset > config.maximum_handoff_gap_s:
        reject_reasons.append("handoff_gap_exceeded")
    if sample_count < config.minimum_geometry_samples:
        reject_reasons.append("insufficient_geometry_samples")
    if intersection_angle < config.minimum_intersection_angle_deg:
        reject_reasons.append("intersection_angle_too_small")
    if median_separation > config.maximum_ray_separation_m:
        reject_reasons.append("ray_separation_exceeded")
    if median_reprojection > config.maximum_reprojection_error_px:
        reject_reasons.append("reprojection_error_exceeded")
    if motion_error > config.maximum_motion_fit_error_m:
        reject_reasons.append("motion_fit_error_exceeded")
    if motion_turn > config.maximum_motion_turn_deg:
        reject_reasons.append("motion_direction_inconsistent")
    if bbox_difference > config.maximum_scale_geometry_log_error:
        reject_reasons.append("bbox_scale_geometry_inconsistent")

    confidence = math.sqrt(calibration_a.confidence * calibration_b.confidence)
    normalized_terms = (
        min(median_separation / config.maximum_ray_separation_m, 3.0),
        min(median_reprojection / config.maximum_reprojection_error_px, 3.0),
        min(latest_offset / config.maximum_handoff_gap_s, 3.0),
        min(motion_error / config.maximum_motion_fit_error_m, 3.0),
        min(motion_turn / config.maximum_motion_turn_deg, 3.0),
        min(bbox_difference / config.maximum_scale_geometry_log_error, 3.0),
        1.0 - confidence,
    )
    weights = np.asarray((0.24, 0.20, 0.10, 0.18, 0.12, 0.08, 0.08))
    geometry_cost = float(np.dot(weights, np.asarray(normalized_terms)))
    edge_features = (
        min(latest_offset / config.maximum_handoff_gap_s, 4.0),
        min(median_separation / config.maximum_ray_separation_m, 4.0),
        min(median_reprojection / config.maximum_reprojection_error_px, 4.0),
        min(intersection_angle / 20.0, 4.0),
        min(motion_error / config.maximum_motion_fit_error_m, 4.0),
        min(motion_turn / config.maximum_motion_turn_deg, 4.0),
        min(bbox_difference / config.maximum_scale_geometry_log_error, 4.0),
        confidence,
        min(sample_count / 6.0, 2.0),
    )
    return CandidateEdge(
        camera_a_id=first_a.camera_id,
        track_a_id=first_a.local_track_id,
        camera_b_id=first_b.camera_id,
        track_b_id=first_b.local_track_id,
        reference_timestamp=max(
            float(history_a[-1].measurement_timestamp),
            float(history_b[-1].measurement_timestamp),
        ),
        aligned_sample_count=sample_count,
        latest_time_offset_s=latest_offset,
        median_ray_separation_m=median_separation,
        median_reprojection_error_px=median_reprojection,
        intersection_angle_deg=intersection_angle,
        motion_fit_error_m=motion_error,
        motion_turn_deg=motion_turn,
        bbox_log_scale_difference=bbox_difference,
        camera_confidence=confidence,
        geometry_cost=geometry_cost,
        gate_passed=not reject_reasons,
        reject_reasons=tuple(reject_reasons),
        midpoint_ned_m=midpoint,
        edge_features=edge_features,
    )


def build_pair_candidates(
    histories_a: Mapping[str, Sequence[LocalVisualTrackRecord]],
    histories_b: Mapping[str, Sequence[LocalVisualTrackRecord]],
    calibration_a: CameraCalibration,
    calibration_b: CameraCalibration,
    config: CrossViewConfig,
) -> tuple[CandidateEdge, ...]:
    return tuple(
        _candidate_edge(
            histories_a[track_a],
            histories_b[track_b],
            calibration_a,
            calibration_b,
            config,
        )
        for track_a in sorted(histories_a)
        for track_b in sorted(histories_b)
    )


def _solve_pair_assignment(
    candidates: Sequence[CandidateEdge],
    track_ids_a: Sequence[str],
    track_ids_b: Sequence[str],
    config: CrossViewConfig,
    *,
    backend: str,
    scorer: CandidateEdgeScorer | None,
    histories_a: Mapping[str, Sequence[LocalVisualTrackRecord]],
    histories_b: Mapping[str, Sequence[LocalVisualTrackRecord]],
    calibration_a: CameraCalibration,
    calibration_b: CameraCalibration,
    locked_a_to_b: Mapping[str, str],
) -> tuple[tuple[CandidateEdge, ...], tuple[CandidateEdge, ...]]:
    if backend not in {"geometry", "gnn"}:
        raise ValueError(f"unsupported association backend: {backend}")
    passed = [item for item in candidates if item.gate_passed]
    learned: Mapping[tuple[str, str], float] = {}
    if backend == "gnn":
        if scorer is None:
            raise ValueError("gnn backend requires a loaded candidate scorer")
        # The model receives only the hard geometry whitelist.
        learned = scorer.score(
            histories_a,
            histories_b,
            passed,
            calibration_a,
            calibration_b,
        )

    index_a = {value: index for index, value in enumerate(track_ids_a)}
    index_b = {value: index for index, value in enumerate(track_ids_b)}
    size = len(track_ids_a) + len(track_ids_b)
    blocked = 1.0e6
    matrix = np.full((size, size), blocked, dtype=float)
    by_index: dict[tuple[int, int], CandidateEdge] = {}
    enriched: list[CandidateEdge] = []
    locked_b_to_a = {right: left for left, right in locked_a_to_b.items()}
    for candidate in candidates:
        probability = None
        final_cost = None
        reasons = list(candidate.reject_reasons)
        if candidate.gate_passed:
            if (
                candidate.track_a_id in locked_a_to_b
                and locked_a_to_b[candidate.track_a_id] != candidate.track_b_id
            ) or (
                candidate.track_b_id in locked_b_to_a
                and locked_b_to_a[candidate.track_b_id] != candidate.track_a_id
            ):
                reasons.append("confirmed_relation_conflict")
            else:
                if backend == "gnn":
                    probability = float(
                        learned.get((candidate.track_a_id, candidate.track_b_id), 0.0)
                    )
                    if not 0.0 <= probability <= 1.0:
                        raise ValueError("GNN probabilities must be within [0, 1]")
                    final_cost = (
                        (1.0 - config.gnn_probability_weight) * candidate.geometry_cost
                        + config.gnn_probability_weight * (1.0 - probability)
                    )
                else:
                    final_cost = candidate.geometry_cost
                if locked_a_to_b.get(candidate.track_a_id) == candidate.track_b_id:
                    final_cost = max(0.0, final_cost - config.confirmed_pair_cost_bonus)
        enriched_candidate = replace(
            candidate,
            gate_passed=candidate.gate_passed and not reasons,
            reject_reasons=tuple(reasons),
            learned_probability=probability,
            final_cost=final_cost,
        )
        enriched.append(enriched_candidate)
        if not enriched_candidate.gate_passed or final_cost is None:
            continue
        if final_cost >= config.unmatched_cost:
            continue
        row = index_a[candidate.track_a_id]
        column = index_b[candidate.track_b_id]
        matrix[row, column] = final_cost
        by_index[(row, column)] = enriched_candidate
    for row in range(len(track_ids_a)):
        matrix[row, len(track_ids_b) + row] = config.unmatched_cost
    for column in range(len(track_ids_b)):
        matrix[len(track_ids_a) + column, column] = config.unmatched_cost
    matrix[len(track_ids_a) :, len(track_ids_b) :] = 0.0
    rows, columns = linear_sum_assignment(matrix)
    selected = tuple(
        by_index[(int(row), int(column))]
        for row, column in zip(rows, columns)
        if (int(row), int(column)) in by_index
        and matrix[int(row), int(column)] < config.unmatched_cost
    )
    return tuple(enriched), selected


class _UnionFind:
    def __init__(self, values: Sequence[str]) -> None:
        self.parent = {value: value for value in values}
        self.cameras = {value: {split_track_key(value)[0]} for value in values}
        self.members = {value: {value} for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union_if_camera_unique(self, left: str, right: str) -> bool:
        root_left, root_right = self.find(left), self.find(right)
        if root_left == root_right:
            return True
        if self.cameras[root_left] & self.cameras[root_right]:
            return False
        if root_right < root_left:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        self.cameras[root_left] |= self.cameras.pop(root_right)
        self.members[root_left] |= self.members.pop(root_right)
        return True

    def component_members(self, value: str) -> frozenset[str]:
        return frozenset(self.members[self.find(value)])


def _match_camera_pair(match: PairMatch) -> tuple[str, str]:
    return tuple(sorted((match.camera_a_id, match.camera_b_id)))  # type: ignore[return-value]


def _cross_component_matches(
    matches: Sequence[PairMatch],
    left_members: frozenset[str],
    right_members: frozenset[str],
) -> tuple[PairMatch, ...]:
    return tuple(
        match
        for match in matches
        if (
            match.key_a in left_members
            and match.key_b in right_members
        )
        or (
            match.key_b in left_members
            and match.key_a in right_members
        )
    )


def _cluster_confirmed_links(
    track_keys: Sequence[str],
    matches: Sequence[PairMatch],
    config: CrossViewConfig,
) -> tuple[_UnionFind, tuple[PairMatch, ...], tuple[PairMatch, ...]]:
    """Aggregate confirmed pair links without accepting a one-edge mature bridge."""

    union_find = _UnionFind(track_keys)
    accepted: list[PairMatch] = []
    rejected_bridges: list[PairMatch] = []
    ordered = tuple(sorted(matches, key=lambda item: (item.cost, item.key_a, item.key_b)))
    for match in ordered:
        root_left = union_find.find(match.key_a)
        root_right = union_find.find(match.key_b)
        if root_left == root_right:
            accepted.append(match)
            continue
        left_members = union_find.component_members(root_left)
        right_members = union_find.component_members(root_right)
        if union_find.cameras[root_left] & union_find.cameras[root_right]:
            continue
        if (
            len(left_members) >= config.mature_cluster_min_size
            and len(right_members) >= config.mature_cluster_min_size
        ):
            cross_support = _cross_component_matches(
                ordered,
                left_members,
                right_members,
            )
            camera_pairs = {_match_camera_pair(item) for item in cross_support}
            if len(camera_pairs) < config.mature_cluster_min_cross_camera_pairs:
                rejected_bridges.append(match)
                continue
        if union_find.union_if_camera_unique(match.key_a, match.key_b):
            accepted.append(match)
    return union_find, tuple(accepted), tuple(rejected_bridges)


@dataclass(frozen=True)
class _ShortTrackProposal:
    short_track_key: str
    anchor_track_key: str
    support_edges: tuple[CandidateEdge, ...]
    weighted_cost: float


def _best_short_edge_by_relation(
    candidates: Sequence[CandidateEdge],
    config: CrossViewConfig,
) -> dict[tuple[str, str], CandidateEdge]:
    best: dict[tuple[str, str], CandidateEdge] = {}
    for candidate in candidates:
        if set(candidate.reject_reasons) != {"insufficient_geometry_samples"}:
            continue
        if candidate.aligned_sample_count <= 0:
            continue
        relation = tuple(sorted((candidate.key_a, candidate.key_b)))
        current = best.get(relation)
        rank = (
            candidate.aligned_sample_count,
            -candidate.geometry_cost,
            candidate.reference_timestamp,
        )
        if current is None or rank > (
            current.aligned_sample_count,
            -current.geometry_cost,
            current.reference_timestamp,
        ):
            best[relation] = candidate
    return {
        relation: candidate
        for relation, candidate in best.items()
        if candidate.geometry_cost <= config.short_track_cluster_max_geometry_cost
    }


def _attach_short_tracks_by_cluster_consensus(
    union_find: _UnionFind,
    track_observation_counts: Mapping[str, int],
    candidates: Sequence[CandidateEdge],
    config: CrossViewConfig,
    *,
    backend: str,
) -> tuple[PairMatch, ...]:
    """Attach a short singleton only when several cameras support one mature cluster."""

    best_edges = _best_short_edge_by_relation(candidates, config)
    initial_groups: dict[str, frozenset[str]] = {}
    for track_key_value in sorted(track_observation_counts):
        root = union_find.find(track_key_value)
        initial_groups[root] = union_find.component_members(root)
    mature_groups = tuple(
        members
        for members in initial_groups.values()
        if len(members) >= config.mature_cluster_min_size
    )
    proposals: list[_ShortTrackProposal] = []
    for short_key, observation_count in sorted(track_observation_counts.items()):
        if not (
            config.short_track_min_observations
            <= observation_count
            < config.minimum_geometry_samples
        ):
            continue
        if len(union_find.component_members(short_key)) != 1:
            continue
        short_camera, _ = split_track_key(short_key)
        options: list[_ShortTrackProposal] = []
        for members in mature_groups:
            member_cameras = {split_track_key(member)[0] for member in members}
            if short_camera in member_cameras:
                continue
            support_edges = tuple(
                edge
                for member in sorted(members)
                if (
                    edge := best_edges.get(tuple(sorted((short_key, member))))
                )
                is not None
            )
            support_cameras = {
                split_track_key(
                    edge.key_b if edge.key_a == short_key else edge.key_a
                )[0]
                for edge in support_edges
            }
            total_samples = sum(edge.aligned_sample_count for edge in support_edges)
            peak_samples = max(
                (edge.aligned_sample_count for edge in support_edges),
                default=0,
            )
            if len(support_cameras) < config.short_track_cluster_min_support_cameras:
                continue
            if total_samples < config.short_track_cluster_min_total_aligned_samples:
                continue
            if peak_samples < config.short_track_cluster_min_peak_samples:
                continue
            weighted_cost = sum(
                edge.geometry_cost * edge.aligned_sample_count
                for edge in support_edges
            ) / total_samples
            options.append(
                _ShortTrackProposal(
                    short_track_key=short_key,
                    anchor_track_key=min(members),
                    support_edges=support_edges,
                    weighted_cost=weighted_cost,
                )
            )
        options.sort(
            key=lambda item: (
                item.weighted_cost,
                item.anchor_track_key,
            )
        )
        if not options:
            continue
        if (
            len(options) > 1
            and options[1].weighted_cost - options[0].weighted_cost
            < config.short_track_cluster_min_cost_margin
        ):
            continue
        proposals.append(options[0])

    accepted: list[PairMatch] = []
    for proposal in sorted(
        proposals,
        key=lambda item: (
            item.weighted_cost,
            item.short_track_key,
            item.anchor_track_key,
        ),
    ):
        if len(union_find.component_members(proposal.short_track_key)) != 1:
            continue
        anchor_root = union_find.find(proposal.anchor_track_key)
        short_camera, _ = split_track_key(proposal.short_track_key)
        if short_camera in union_find.cameras[anchor_root]:
            continue
        if not union_find.union_if_camera_unique(
            proposal.short_track_key,
            proposal.anchor_track_key,
        ):
            continue
        for edge in proposal.support_edges:
            accepted.append(
                PairMatch(
                    camera_a_id=edge.camera_a_id,
                    track_a_id=edge.track_a_id,
                    camera_b_id=edge.camera_b_id,
                    track_b_id=edge.track_b_id,
                    timestamp=edge.reference_timestamp,
                    cost=edge.geometry_cost,
                    decision_state="cluster_confirmed",
                    confirmation_count=edge.aligned_sample_count,
                    backend=backend,
                )
            )
    return tuple(accepted)


class CrossViewAssociator:
    def __init__(
        self,
        calibrations: Mapping[str, CameraCalibration],
        *,
        config: CrossViewConfig | None = None,
        backend: str = "geometry",
        scorer: CandidateEdgeScorer | None = None,
        camera_pair_plan: CameraPairPlan | None = None,
        output_mode: str = "detailed",
        candidate_sample_limit: int = 200,
    ) -> None:
        self.calibrations = dict(calibrations)
        self.config = config or CrossViewConfig()
        self.backend = backend
        self.scorer = scorer
        self.camera_pair_plan = camera_pair_plan or full_camera_pair_plan(
            tuple(self.calibrations)
        )
        self.output_mode = output_mode
        self.candidate_sample_limit = int(candidate_sample_limit)
        if backend == "gnn" and scorer is None:
            raise ValueError("gnn backend requires a scorer")
        if output_mode not in {"detailed", "audit"}:
            raise ValueError("output_mode must be detailed or audit")
        if self.candidate_sample_limit < 0:
            raise ValueError("candidate_sample_limit cannot be negative")
        expected_pairs = full_camera_pair_plan(tuple(self.calibrations)).all_pairs
        if self.camera_pair_plan.all_pairs != expected_pairs:
            raise ValueError("camera pair plan does not match supplied calibrations")

    def run(self, records: Sequence[LocalVisualTrackRecord]) -> CrossViewResult:
        for record in records:
            assert_online_anonymous(record.to_online_dict())
            if record.camera_id not in self.calibrations:
                raise ValueError(f"missing calibration for {record.camera_id}")
        recognized = [
            record
            for record in records
            if record.recognized
            and recognition_extent(record) >= self.config.recognition_extent_px
            and record.recognition_extent_px >= self.config.recognition_extent_px
        ]
        frames: dict[float, list[LocalVisualTrackRecord]] = defaultdict(list)
        for record in recognized:
            frames[float(record.measurement_timestamp)].append(record)
        histories: dict[str, dict[str, list[LocalVisualTrackRecord]]] = defaultdict(
            lambda: defaultdict(list)
        )
        confirmation_frames: dict[tuple[str, str], deque[int]] = defaultdict(deque)
        confirmed_links: dict[tuple[str, str], PairMatch] = {}
        locked_by_camera_pair: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
        all_candidates: list[CandidateEdge] = []
        candidate_samples_passed: list[CandidateEdge] = []
        candidate_samples_rejected: list[CandidateEdge] = []
        short_candidate_evidence: dict[tuple[str, str], CandidateEdge] = {}
        candidate_generated_count = 0
        geometry_hard_gate_passed_count = 0
        post_constraint_gate_passed_count = 0
        assignment_selected_count = 0
        camera_pair_evaluation_count = 0
        reject_reason_counts: Counter[str] = Counter()
        latest_tentative: dict[tuple[str, str], PairMatch] = {}

        passed_sample_capacity = (self.candidate_sample_limit + 1) // 2
        rejected_sample_capacity = self.candidate_sample_limit // 2

        for frame_index, timestamp in enumerate(sorted(frames), start=1):
            for record in sorted(
                frames[timestamp], key=lambda item: (item.camera_id, item.local_track_id)
            ):
                histories[record.camera_id][record.local_track_id].append(record)
            active: dict[str, dict[str, Sequence[LocalVisualTrackRecord]]] = {}
            for camera_id, camera_histories in histories.items():
                active_tracks = {
                    local_id: tuple(history)
                    for local_id, history in camera_histories.items()
                    if timestamp - history[-1].measurement_timestamp
                    <= self.config.maximum_handoff_gap_s
                }
                if active_tracks:
                    active[camera_id] = active_tracks
            for camera_a, camera_b in combinations(sorted(active), 2):
                if not self.camera_pair_plan.allows(camera_a, camera_b):
                    continue
                camera_pair_evaluation_count += 1
                candidates = build_pair_candidates(
                    active[camera_a],
                    active[camera_b],
                    self.calibrations[camera_a],
                    self.calibrations[camera_b],
                    self.config,
                )
                candidate_generated_count += len(candidates)
                geometry_hard_gate_passed_count += sum(
                    item.gate_passed for item in candidates
                )
                pair_key = (camera_a, camera_b)
                enriched, selected = _solve_pair_assignment(
                    candidates,
                    tuple(sorted(active[camera_a])),
                    tuple(sorted(active[camera_b])),
                    self.config,
                    backend=self.backend,
                    scorer=self.scorer,
                    histories_a=active[camera_a],
                    histories_b=active[camera_b],
                    calibration_a=self.calibrations[camera_a],
                    calibration_b=self.calibrations[camera_b],
                    locked_a_to_b=locked_by_camera_pair[pair_key],
                )
                post_constraint_gate_passed_count += sum(
                    item.gate_passed for item in enriched
                )
                assignment_selected_count += len(selected)
                for candidate in enriched:
                    reject_reason_counts.update(candidate.reject_reasons)
                    if self.output_mode == "detailed":
                        all_candidates.append(candidate)
                    elif candidate.gate_passed:
                        if len(candidate_samples_passed) < passed_sample_capacity:
                            candidate_samples_passed.append(candidate)
                    elif len(candidate_samples_rejected) < rejected_sample_capacity:
                        candidate_samples_rejected.append(candidate)
                    if set(candidate.reject_reasons) == {"insufficient_geometry_samples"}:
                        relation = tuple(sorted((candidate.key_a, candidate.key_b)))
                        previous = short_candidate_evidence.get(relation)
                        rank = (
                            candidate.aligned_sample_count,
                            -candidate.geometry_cost,
                            candidate.reference_timestamp,
                        )
                        previous_rank = (
                            previous.aligned_sample_count,
                            -previous.geometry_cost,
                            previous.reference_timestamp,
                        ) if previous is not None else None
                        if previous_rank is None or rank > previous_rank:
                            short_candidate_evidence[relation] = candidate
                selected_keys: set[tuple[str, str]] = set()
                for candidate in selected:
                    relation = (candidate.key_a, candidate.key_b)
                    selected_keys.add(relation)
                    hits = confirmation_frames[relation]
                    while hits and frame_index - hits[0] >= self.config.confirmation_window_frames:
                        hits.popleft()
                    hits.append(frame_index)
                    count = len(hits)
                    state = (
                        "confirmed"
                        if count >= self.config.confirmation_hits
                        else "tentative"
                    )
                    match = PairMatch(
                        camera_a_id=candidate.camera_a_id,
                        track_a_id=candidate.track_a_id,
                        camera_b_id=candidate.camera_b_id,
                        track_b_id=candidate.track_b_id,
                        timestamp=timestamp,
                        cost=float(candidate.final_cost or 0.0),
                        decision_state=state,
                        confirmation_count=count,
                        backend=self.backend,
                    )
                    if state == "confirmed":
                        previous = confirmed_links.get(relation)
                        if previous is None or match.cost < previous.cost:
                            confirmed_links[relation] = match
                        locked_by_camera_pair[pair_key][candidate.track_a_id] = (
                            candidate.track_b_id
                        )
                        latest_tentative.pop(relation, None)
                    elif relation not in confirmed_links:
                        latest_tentative[relation] = match
                for relation in list(latest_tentative):
                    left_camera, _ = split_track_key(relation[0])
                    right_camera, _ = split_track_key(relation[1])
                    if (left_camera, right_camera) == pair_key and relation not in selected_keys:
                        latest_tentative.pop(relation, None)

        all_track_keys = sorted(
            track_key(camera_id, local_id)
            for camera_id, camera_histories in histories.items()
            for local_id in camera_histories
        )
        union_find, primary_matches, _rejected_bridges = _cluster_confirmed_links(
            all_track_keys,
            tuple(confirmed_links.values()),
            self.config,
        )
        track_observation_counts = {
            track_key(camera_id, local_id): len(history)
            for camera_id, camera_histories in histories.items()
            for local_id, history in camera_histories.items()
        }
        short_track_matches = _attach_short_tracks_by_cluster_consensus(
            union_find,
            track_observation_counts,
            all_candidates
            if self.output_mode == "detailed"
            else tuple(short_candidate_evidence.values()),
            self.config,
            backend=self.backend,
        )
        accepted_matches = list(primary_matches + short_track_matches)
        groups: dict[str, list[str]] = defaultdict(list)
        for value in all_track_keys:
            groups[union_find.find(value)].append(value)
        clusters: list[UnifiedTargetCluster] = []
        clustered: set[str] = set()
        for sequence, members in enumerate(
            sorted((sorted(values) for values in groups.values() if len(values) >= 2)),
            start=1,
        ):
            camera_ids = tuple(split_track_key(value)[0] for value in members)
            cluster = UnifiedTargetCluster(
                cluster_id=f"XVIEW-{sequence:03d}",
                member_track_keys=tuple(members),
                camera_ids=camera_ids,
            )
            clusters.append(cluster)
            clustered.update(members)
        unresolved = tuple(value for value in all_track_keys if value not in clustered)
        camera_violations = sum(
            len(cluster.camera_ids) - len(set(cluster.camera_ids)) for cluster in clusters
        )
        metrics = CrossViewMetrics(
            recognized_track_count=len(all_track_keys),
            candidate_edge_count=candidate_generated_count,
            geometry_passed_edge_count=post_constraint_gate_passed_count,
            confirmed_relation_count=len(accepted_matches),
            tentative_relation_count=len(latest_tentative),
            unresolved_track_count=len(unresolved),
            cluster_count=len(clusters),
            camera_uniqueness_violation_count=camera_violations,
            truth_leakage_count=0,
            availability={
                "truth_metrics": False,
                "gnn_backend": self.backend == "gnn",
            },
        )
        retained_candidates = (
            tuple(all_candidates)
            if self.output_mode == "detailed"
            else tuple(candidate_samples_passed + candidate_samples_rejected)
        )
        audit = AssociationAudit(
            output_mode=self.output_mode,
            camera_pair_policy=self.camera_pair_plan.policy,
            camera_pair_total_count=self.camera_pair_plan.total_count,
            camera_pair_retained_count=self.camera_pair_plan.retained_count,
            camera_pair_pruned_count=self.camera_pair_plan.pruned_count,
            camera_pair_evaluation_count=camera_pair_evaluation_count,
            candidate_stage_counts={
                "generated": candidate_generated_count,
                "geometry_hard_gate_passed": geometry_hard_gate_passed_count,
                "post_constraint_gate_passed": post_constraint_gate_passed_count,
                "assignment_selected": assignment_selected_count,
                "confirmed_relations": len(accepted_matches),
                "tentative_relations": len(latest_tentative),
            },
            candidate_reject_reason_counts=dict(sorted(reject_reason_counts.items())),
            camera_pair_reject_reason_counts=dict(
                self.camera_pair_plan.rejection_reason_counts
            ),
            candidate_sample_limit=(
                self.candidate_sample_limit
                if self.output_mode == "audit"
                else candidate_generated_count
            ),
            retained_candidate_sample_count=len(retained_candidates),
            omitted_candidate_count=max(
                0, candidate_generated_count - len(retained_candidates)
            ),
        )
        result = CrossViewResult(
            backend=self.backend,
            candidates=retained_candidates,
            matches=tuple(accepted_matches),
            clusters=tuple(clusters),
            pending_relations=tuple(
                sorted(latest_tentative.values(), key=lambda item: (item.key_a, item.key_b))
            ),
            unresolved_track_keys=unresolved,
            metrics=metrics,
            audit=audit,
        )
        result.to_online_dict()
        return result


def associate_crossview_tracks(
    records: Sequence[LocalVisualTrackRecord],
    calibrations: Mapping[str, CameraCalibration],
    *,
    config: CrossViewConfig | None = None,
    backend: str = "geometry",
    scorer: CandidateEdgeScorer | None = None,
    camera_pair_plan: CameraPairPlan | None = None,
    output_mode: str = "detailed",
    candidate_sample_limit: int = 200,
) -> CrossViewResult:
    return CrossViewAssociator(
        calibrations,
        config=config,
        backend=backend,
        scorer=scorer,
        camera_pair_plan=camera_pair_plan,
        output_mode=output_mode,
        candidate_sample_limit=candidate_sample_limit,
    ).run(records)
