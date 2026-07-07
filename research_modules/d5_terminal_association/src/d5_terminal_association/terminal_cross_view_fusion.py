"""Metadata-only distributed cross-view terminal association.

The fusion layer is advisory evidence for D4 fully distributed fallback. It
matches peer visual tracklets by time, bearing, scale, category, confidence,
and pose quality. It does not allocate targets, authorize locks, or create,
rewrite, or rebind center-owned global track IDs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import isfinite, log, pi
from typing import Iterable, Mapping, Sequence

import numpy as np

from .models import (
    CrossPeerAssociationHypothesis,
    DistributedTerminalAssociation,
    DistributedVisualObservation,
    PeerCameraState,
    VisualTrackletSummary,
)


@dataclass(frozen=True)
class TerminalCrossViewFusionConfig:
    """Tunable thresholds for metadata-only cross-peer association."""

    max_measurement_time_skew_s: float = 0.75
    max_arrival_time_skew_s: float = 2.0
    max_pair_cost: float = 18.0
    bearing_sigma: float = 0.08
    pixel_sigma: float = 50.0
    bearing_rate_sigma: float = 0.08
    bbox_log_area_sigma: float = 0.65
    scale_rate_sigma: float = 0.5
    category_mismatch_penalty: float = 10.0
    unknown_category_penalty: float = 1.5
    confidence_cost_weight: float = 1.0
    covariance_trace_weight: float = 0.001
    max_covariance_trace_px: float = 5_000.0
    pose_covariance_trace_weight: float = 0.01
    max_pose_covariance_trace: float = 1_000.0
    missing_geometry_penalty: float = 3.0
    min_support_count_for_lock: int = 2
    min_confidence_for_lock: float = 0.55
    max_ambiguity_for_lock: float = 0.55
    default_covariance_px: float = 25.0
    cost_inf: float = 1e12


class TerminalCrossViewFusion:
    """Build cross-peer terminal visual hypotheses for distributed D4 use."""

    def __init__(self, config: TerminalCrossViewFusionConfig | None = None) -> None:
        self.config = config or TerminalCrossViewFusionConfig()

    def associate(
        self,
        *,
        observations: Iterable[DistributedVisualObservation] = (),
        tracklet_summaries: Iterable[VisualTrackletSummary] = (),
        camera_states: Iterable[PeerCameraState] = (),
        current_assigned_global_track_ids: Iterable[str] = (),
        stale_assigned_global_track_ids: Iterable[str] = (),
        current_time: float | None = None,
    ) -> list[DistributedTerminalAssociation]:
        """Return conservative distributed terminal association summaries."""

        hypotheses = self.build_hypotheses(
            observations=observations,
            tracklet_summaries=tracklet_summaries,
            camera_states=camera_states,
            current_assigned_global_track_ids=current_assigned_global_track_ids,
            stale_assigned_global_track_ids=stale_assigned_global_track_ids,
            current_time=current_time,
        )
        return [self._association_from_hypothesis(hypothesis) for hypothesis in hypotheses]

    def build_hypotheses(
        self,
        *,
        observations: Iterable[DistributedVisualObservation] = (),
        tracklet_summaries: Iterable[VisualTrackletSummary] = (),
        camera_states: Iterable[PeerCameraState] = (),
        current_assigned_global_track_ids: Iterable[str] = (),
        stale_assigned_global_track_ids: Iterable[str] = (),
        current_time: float | None = None,
    ) -> list[CrossPeerAssociationHypothesis]:
        """Create cross-peer visual hypotheses without creating global IDs."""

        summaries = self._combined_summaries(observations, tracklet_summaries)
        if not summaries:
            return []

        current_ids = _string_set(current_assigned_global_track_ids)
        stale_ids = _string_set(stale_assigned_global_track_ids)
        camera_state_by_key = _camera_state_index(camera_states)
        local_conflict_keys = {
            summary.tracklet_key for summary in summaries if len(summary.assigned_global_track_ids) > 1
        }
        edge_costs = self._match_cross_resource_edges(summaries, camera_state_by_key)
        components = _connected_components(summaries, edge_costs)
        hypotheses = [
            self._build_hypothesis(
                component,
                edge_costs=edge_costs,
                current_ids=current_ids,
                stale_ids=stale_ids,
                local_conflict_keys=local_conflict_keys,
                current_time=current_time,
            )
            for component in components
        ]
        return sorted(hypotheses, key=lambda item: (item.resource_id, item.local_track_id, item.hypothesis_id))

    def summarize_observations(
        self,
        observations: Iterable[DistributedVisualObservation],
    ) -> list[VisualTrackletSummary]:
        """Build one summary per resource/camera/local-track namespace."""

        grouped: dict[str, list[DistributedVisualObservation]] = defaultdict(list)
        for observation in observations:
            grouped[observation.tracklet_key].append(observation)

        summaries: list[VisualTrackletSummary] = []
        for tracklet_key, group in grouped.items():
            ordered = sorted(group, key=lambda item: (item.measurement_timestamp, item.arrival_timestamp))
            first = ordered[0]
            latest = ordered[-1]
            dt = max(0.0, latest.measurement_timestamp - first.measurement_timestamp)
            bearing_rate = latest.bearing_rate
            if bearing_rate is None and dt > 1e-9 and latest.bearing is not None and first.bearing is not None:
                bearing_rate = _bearing_delta(latest.bearing, first.bearing) / dt
            if bearing_rate is None and dt > 1e-9 and latest.center_px is not None and first.center_px is not None:
                bearing_rate = (latest.center_px - first.center_px) / dt

            first_area = _bbox_area(first.bbox)
            latest_area = _bbox_area(latest.bbox)
            scale_rate = 0.0
            if dt > 1e-9 and first_area > 0.0 and latest_area > 0.0:
                scale_rate = log(latest_area / first_area) / dt

            assigned_ids = _unique(
                observation.assigned_global_track_id
                for observation in ordered
                if observation.assigned_global_track_id is not None
            )
            stale_ids = _unique(
                observation.assigned_global_track_id
                for observation in ordered
                if observation.assigned_global_track_id is not None
                and observation.assigned_global_track_stale
            )
            metadata = dict(latest.metadata)
            metadata["tracklet_key"] = tracklet_key
            summaries.append(
                VisualTrackletSummary(
                    resource_id=latest.resource_id,
                    camera_id=latest.camera_id,
                    frame_id=latest.frame_id,
                    local_track_id=latest.local_track_id,
                    measurement_timestamp=latest.measurement_timestamp,
                    arrival_timestamp=latest.arrival_timestamp,
                    center_px=latest.center_px,
                    bbox=latest.bbox,
                    bearing=latest.bearing,
                    bearing_rate=bearing_rate,
                    covariance_px=latest.covariance_px,
                    covariance=latest.covariance,
                    category=latest.category,
                    confidence=latest.confidence,
                    bbox_area=latest_area,
                    scale_rate=scale_rate,
                    observation_count=len(ordered),
                    first_measurement_timestamp=first.measurement_timestamp,
                    assigned_global_track_ids=assigned_ids,
                    stale_assigned_global_track_ids=stale_ids,
                    assigned_global_track_stale=bool(stale_ids),
                    source_observation_ids=tuple(
                        str(observation.metadata.get("observation_id", f"{tracklet_key}@{observation.measurement_timestamp}"))
                        for observation in ordered
                    ),
                    friend_conflict_state=_strongest_friend_state(
                        observation.friend_conflict_state for observation in ordered
                    ),
                    metadata=metadata,
                )
            )

        return sorted(summaries, key=lambda item: item.tracklet_key)

    def _combined_summaries(
        self,
        observations: Iterable[DistributedVisualObservation],
        tracklet_summaries: Iterable[VisualTrackletSummary],
    ) -> list[VisualTrackletSummary]:
        combined: dict[str, VisualTrackletSummary] = {
            summary.tracklet_key: summary for summary in self.summarize_observations(observations)
        }
        for summary in tracklet_summaries:
            previous = combined.get(summary.tracklet_key)
            if previous is None or summary.measurement_timestamp >= previous.measurement_timestamp:
                combined[summary.tracklet_key] = summary
        return sorted(combined.values(), key=lambda item: item.tracklet_key)

    def _match_cross_resource_edges(
        self,
        summaries: Sequence[VisualTrackletSummary],
        camera_state_by_key: Mapping[tuple[str, str | None], PeerCameraState],
    ) -> dict[tuple[str, str], float]:
        by_resource: dict[str, list[VisualTrackletSummary]] = defaultdict(list)
        for summary in summaries:
            by_resource[summary.resource_id].append(summary)

        edge_costs: dict[tuple[str, str], float] = {}
        for left_resource, right_resource in combinations(sorted(by_resource), 2):
            left_items = sorted(by_resource[left_resource], key=lambda item: item.tracklet_key)
            right_items = sorted(by_resource[right_resource], key=lambda item: item.tracklet_key)
            if not left_items or not right_items:
                continue
            costs = np.full((len(left_items), len(right_items)), self.config.cost_inf, dtype=float)
            for row, left in enumerate(left_items):
                for col, right in enumerate(right_items):
                    costs[row, col] = self._pair_cost(left, right, camera_state_by_key)
            for row, col in _unique_assignment(costs, self.config.cost_inf):
                cost = float(costs[row, col])
                if isfinite(cost) and cost <= self.config.max_pair_cost:
                    edge_costs[_edge_key(left_items[row].tracklet_key, right_items[col].tracklet_key)] = cost

        return edge_costs

    def _pair_cost(
        self,
        left: VisualTrackletSummary,
        right: VisualTrackletSummary,
        camera_state_by_key: Mapping[tuple[str, str | None], PeerCameraState],
    ) -> float:
        cfg = self.config
        if left.tracklet_key == right.tracklet_key or left.resource_id == right.resource_id:
            return cfg.cost_inf

        measurement_skew = abs(left.measurement_timestamp - right.measurement_timestamp)
        if measurement_skew > cfg.max_measurement_time_skew_s:
            return cfg.cost_inf
        arrival_skew = abs(left.arrival_timestamp - right.arrival_timestamp)
        if arrival_skew > cfg.max_arrival_time_skew_s:
            return cfg.cost_inf

        left_cov_trace = _covariance_trace_px(left, cfg.default_covariance_px)
        right_cov_trace = _covariance_trace_px(right, cfg.default_covariance_px)
        if left_cov_trace + right_cov_trace > cfg.max_covariance_trace_px:
            return cfg.cost_inf

        pose_trace = self._pose_covariance_trace(left, camera_state_by_key)
        pose_trace += self._pose_covariance_trace(right, camera_state_by_key)
        if pose_trace > cfg.max_pose_covariance_trace:
            return cfg.cost_inf

        cost = 0.0
        if left.bearing is not None and right.bearing is not None:
            bearing_delta = float(np.linalg.norm(_bearing_delta(left.bearing, right.bearing)))
            cost += (bearing_delta / max(cfg.bearing_sigma, 1e-9)) ** 2
        elif left.center_px is not None and right.center_px is not None:
            pixel_delta = float(np.linalg.norm(left.center_px - right.center_px))
            cost += (pixel_delta / max(cfg.pixel_sigma, 1e-9)) ** 2
        else:
            cost += cfg.missing_geometry_penalty

        if left.bearing_rate is not None and right.bearing_rate is not None:
            rate_delta = float(np.linalg.norm(left.bearing_rate - right.bearing_rate))
            cost += (rate_delta / max(cfg.bearing_rate_sigma, 1e-9)) ** 2

        if left.bbox_area > 0.0 and right.bbox_area > 0.0:
            area_delta = abs(log(left.bbox_area / right.bbox_area))
            cost += (area_delta / max(cfg.bbox_log_area_sigma, 1e-9)) ** 2
            scale_delta = abs(left.scale_rate - right.scale_rate)
            cost += (scale_delta / max(cfg.scale_rate_sigma, 1e-9)) ** 2

        left_category = left.category.lower()
        right_category = right.category.lower()
        if left_category == "unknown" or right_category == "unknown":
            cost += cfg.unknown_category_penalty
        elif left_category != right_category:
            cost += cfg.category_mismatch_penalty

        cost += (2.0 - left.confidence - right.confidence) * cfg.confidence_cost_weight
        cost += (left_cov_trace + right_cov_trace) * cfg.covariance_trace_weight
        cost += pose_trace * cfg.pose_covariance_trace_weight
        return float(cost) if isfinite(cost) else cfg.cost_inf

    def _pose_covariance_trace(
        self,
        summary: VisualTrackletSummary,
        camera_state_by_key: Mapping[tuple[str, str | None], PeerCameraState],
    ) -> float:
        state = camera_state_by_key.get((summary.resource_id, summary.camera_id))
        if state is None:
            state = camera_state_by_key.get((summary.resource_id, None))
        if state is None:
            return 0.0
        return float(np.trace(state.pose_covariance))

    def _build_hypothesis(
        self,
        component: Sequence[VisualTrackletSummary],
        *,
        edge_costs: Mapping[tuple[str, str], float],
        current_ids: set[str],
        stale_ids: set[str],
        local_conflict_keys: set[str],
        current_time: float | None,
    ) -> CrossPeerAssociationHypothesis:
        ordered = sorted(component, key=lambda item: item.tracklet_key)
        primary = ordered[0]
        resources = _unique(summary.resource_id for summary in ordered)
        local_track_ids = tuple(summary.tracklet_key for summary in ordered)
        frame_ids = _unique(summary.frame_id for summary in ordered)
        assigned_ids = _unique(track_id for summary in ordered for track_id in summary.assigned_global_track_ids)
        stale_assigned_ids = _unique(
            track_id
            for summary in ordered
            for track_id in self._stale_ids_for_summary(summary, current_ids, stale_ids)
        )
        assigned_id = assigned_ids[0] if len(assigned_ids) == 1 else None
        global_conflict = len(assigned_ids) > 1
        local_conflict = any(summary.tracklet_key in local_conflict_keys for summary in ordered)
        duplicate_resources = self._duplicate_lock_resources(ordered, assigned_id, current_ids, stale_assigned_ids)
        duplicate_risk = bool(duplicate_resources)
        friend_state = _strongest_friend_state(summary.friend_conflict_state for summary in ordered)
        pair_costs = [
            cost
            for left, right in combinations(ordered, 2)
            for cost in [edge_costs.get(_edge_key(left.tracklet_key, right.tracklet_key))]
            if cost is not None
        ]
        total_cost = float(sum(pair_costs) / len(pair_costs)) if pair_costs else 0.0
        support_count = len(resources)
        avg_confidence = float(np.mean([summary.confidence for summary in ordered]))
        if support_count > 1:
            geometry_score = max(0.0, 1.0 - min(total_cost, self.config.max_pair_cost) / self.config.max_pair_cost)
            confidence = avg_confidence * geometry_score
            ambiguity = 1.0 - confidence
        else:
            confidence = avg_confidence * 0.5
            ambiguity = 1.0
        max_time_skew = max(summary.measurement_timestamp for summary in ordered) - min(
            summary.measurement_timestamp for summary in ordered
        )
        category = _category_summary(summary.category for summary in ordered)
        support_state = "supported" if support_count > 1 else "single_view"
        reason = "multi_peer_visual_support" if support_count > 1 else "single_view_support"
        if assigned_id is None:
            reason = "metadata_only_supported_hypothesis" if support_count > 1 else reason
        if stale_assigned_ids:
            support_state = "hold"
            reason = "stale_assigned_global_track_id"
        if friend_state == "verified_friend_overlap":
            support_state = "hold"
            reason = "verified_friend_overlap"
        if global_conflict:
            support_state = "ambiguous"
            reason = "conflicting_assigned_global_track_ids"
        if local_conflict:
            support_state = "ambiguous"
            reason = "local_track_id_conflict"
        if duplicate_risk:
            support_state = "hold"
            reason = "duplicate_terminal_lock_risk"

        covariance_px = _aggregate_covariance_px(ordered, self.config.default_covariance_px)
        hypothesis_id = f"H:{'|'.join(local_track_ids)}"
        metadata = {
            "pair_costs": {
                f"{left}->{right}": float(cost)
                for (left, right), cost in sorted(edge_costs.items())
                if left in local_track_ids and right in local_track_ids
            },
            "current_time": current_time,
            "duplicate_lock_resource_ids": duplicate_resources,
        }
        return CrossPeerAssociationHypothesis(
            hypothesis_id=hypothesis_id,
            resource_id=primary.resource_id,
            local_track_id=primary.local_track_id,
            measurement_timestamp=max(summary.measurement_timestamp for summary in ordered),
            arrival_timestamp=max(summary.arrival_timestamp for summary in ordered),
            frame_id=primary.frame_id,
            covariance_px=covariance_px,
            participant_tracklet_keys=local_track_ids,
            supporting_resource_ids=resources,
            local_track_ids=local_track_ids,
            frame_ids=frame_ids,
            assigned_global_track_id=assigned_id,
            assigned_global_track_ids=assigned_ids,
            stale_assigned_global_track_ids=stale_assigned_ids,
            support_count=support_count,
            total_cost=total_cost,
            confidence=confidence,
            ambiguity_score=ambiguity,
            max_time_skew_s=max_time_skew,
            category=category,
            support_state=support_state,
            duplicate_terminal_lock_risk=duplicate_risk,
            global_track_id_conflict=global_conflict,
            local_id_conflict=local_conflict,
            friend_conflict_state=friend_state,
            reason=reason,
            metadata=metadata,
        )

    def _stale_ids_for_summary(
        self,
        summary: VisualTrackletSummary,
        current_ids: set[str],
        stale_ids: set[str],
    ) -> tuple[str, ...]:
        stale: list[str] = []
        for track_id in summary.assigned_global_track_ids:
            if summary.assigned_global_track_stale or track_id in stale_ids:
                stale.append(track_id)
            elif current_ids and track_id not in current_ids:
                stale.append(track_id)
        return _unique(stale)

    def _duplicate_lock_resources(
        self,
        summaries: Sequence[VisualTrackletSummary],
        assigned_id: str | None,
        current_ids: set[str],
        stale_assigned_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if assigned_id is None or assigned_id in stale_assigned_ids:
            return ()
        if current_ids and assigned_id not in current_ids:
            return ()
        resources = _unique(
            summary.resource_id for summary in summaries if assigned_id in summary.assigned_global_track_ids
        )
        return resources if len(resources) > 1 else ()

    def _association_from_hypothesis(
        self,
        hypothesis: CrossPeerAssociationHypothesis,
    ) -> DistributedTerminalAssociation:
        decision, d4_action, reason = self._decision_state(hypothesis)
        duplicate_local_ids = hypothesis.local_track_ids if hypothesis.local_id_conflict else ()
        duplicate_lock_resources = tuple(hypothesis.metadata.get("duplicate_lock_resource_ids", ()))
        return DistributedTerminalAssociation(
            association_id=f"A:{hypothesis.hypothesis_id}",
            resource_id=hypothesis.resource_id,
            local_track_id=hypothesis.local_track_id,
            measurement_timestamp=hypothesis.measurement_timestamp,
            arrival_timestamp=hypothesis.arrival_timestamp,
            frame_id=hypothesis.frame_id,
            covariance_px=hypothesis.covariance_px,
            decision_state=decision,
            assigned_global_track_id=hypothesis.assigned_global_track_id,
            participant_tracklet_keys=hypothesis.participant_tracklet_keys,
            supporting_resource_ids=hypothesis.supporting_resource_ids,
            local_track_ids=hypothesis.local_track_ids,
            hypotheses=(hypothesis,),
            selected_hypothesis_id=hypothesis.hypothesis_id,
            association_confidence=hypothesis.confidence,
            ambiguity_score=hypothesis.ambiguity_score,
            duplicate_terminal_lock_risk=hypothesis.duplicate_terminal_lock_risk,
            duplicate_lock_resource_ids=duplicate_lock_resources,
            duplicate_local_track_ids=duplicate_local_ids,
            global_track_id_conflict=hypothesis.global_track_id_conflict,
            local_id_conflict=hypothesis.local_id_conflict,
            friend_conflict_state=hypothesis.friend_conflict_state,
            recommended_d4_action=d4_action,
            reason=reason,
            metadata={
                "hypothesis_reason": hypothesis.reason,
                "support_state": hypothesis.support_state,
                "assigned_global_track_ids": hypothesis.assigned_global_track_ids,
                "stale_assigned_global_track_ids": hypothesis.stale_assigned_global_track_ids,
            },
        )

    def _decision_state(self, hypothesis: CrossPeerAssociationHypothesis) -> tuple[str, str, str]:
        if hypothesis.friend_conflict_state == "verified_friend_overlap":
            return "hold", "report_conflict", "verified_friend_overlap"
        if hypothesis.local_id_conflict:
            return "ambiguous", "arbitrate", "local_track_id_conflict"
        if hypothesis.global_track_id_conflict:
            return "ambiguous", "arbitrate", "conflicting_assigned_global_track_ids"
        if hypothesis.stale_assigned_global_track_ids:
            return "hold", "arbitrate", "stale_assigned_global_track_id"
        if hypothesis.assigned_global_track_id is None:
            return "hypothesis_only", "observe", hypothesis.reason
        if hypothesis.duplicate_terminal_lock_risk:
            return "hold", "arbitrate", "duplicate_terminal_lock_risk"
        if hypothesis.support_count < self.config.min_support_count_for_lock:
            return "hypothesis_only", "observe", "single_view_support"
        if hypothesis.category == "unknown":
            return "ambiguous", "observe", "unknown_category_requires_confirmation"
        if hypothesis.confidence < self.config.min_confidence_for_lock:
            return "ambiguous", "observe", "cross_peer_confidence_too_low"
        if hypothesis.ambiguity_score > self.config.max_ambiguity_for_lock:
            return "ambiguous", "observe", "cross_peer_ambiguity_too_high"
        return "locked", "observe", "current_global_track_supported_by_peer_views"


def _string_set(values: Iterable[str]) -> set[str]:
    return {str(value) for value in values if value is not None and str(value)}


def _unique(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value is not None and str(value)))


def _bbox_area(bbox: tuple[float, float, float, float] | None) -> float:
    if bbox is None:
        return 0.0
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _edge_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _bearing_delta(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    delta = np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
    return (delta + pi) % (2.0 * pi) - pi


def _camera_state_index(
    camera_states: Iterable[PeerCameraState],
) -> dict[tuple[str, str | None], PeerCameraState]:
    indexed: dict[tuple[str, str | None], PeerCameraState] = {}
    for state in camera_states:
        indexed[(state.resource_id, state.camera_id)] = state
        indexed.setdefault((state.resource_id, None), state)
    return indexed


def _covariance_trace_px(summary: VisualTrackletSummary, default_covariance_px: float) -> float:
    if summary.covariance_px is not None:
        return float(np.trace(summary.covariance_px))
    if summary.covariance is not None and summary.covariance.shape[0] >= 2:
        return float(np.trace(summary.covariance[:2, :2]))
    return float(default_covariance_px * 2.0)


def _covariance_px(summary: VisualTrackletSummary, default_covariance_px: float) -> np.ndarray:
    if summary.covariance_px is not None:
        return summary.covariance_px
    if summary.covariance is not None and summary.covariance.shape[0] >= 2:
        return summary.covariance[:2, :2].copy()
    return np.eye(2, dtype=float) * default_covariance_px


def _aggregate_covariance_px(
    summaries: Sequence[VisualTrackletSummary],
    default_covariance_px: float,
) -> np.ndarray:
    matrices = [_covariance_px(summary, default_covariance_px) for summary in summaries]
    return np.mean(np.stack(matrices, axis=0), axis=0)


def _category_summary(categories: Iterable[str]) -> str:
    known = [str(category).lower() for category in categories if str(category).lower() != "unknown"]
    if not known:
        return "unknown"
    unique = _unique(known)
    return unique[0] if len(unique) == 1 else "mixed"


def _strongest_friend_state(states: Iterable[str]) -> str:
    ordered = tuple(str(state) for state in states if str(state) and str(state) != "none")
    if "verified_friend_overlap" in ordered:
        return "verified_friend_overlap"
    if "spoof_suspected_overlap" in ordered:
        return "spoof_suspected_overlap"
    if "unverified_friend_overlap" in ordered:
        return "unverified_friend_overlap"
    return ordered[0] if ordered else "none"


def _connected_components(
    summaries: Sequence[VisualTrackletSummary],
    edge_costs: Mapping[tuple[str, str], float],
) -> list[list[VisualTrackletSummary]]:
    parent = {summary.tracklet_key: summary.tracklet_key for summary in summaries}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left, right in edge_costs:
        union(left, right)

    by_root: dict[str, list[VisualTrackletSummary]] = defaultdict(list)
    for summary in summaries:
        by_root[find(summary.tracklet_key)].append(summary)
    return [sorted(component, key=lambda item: item.tracklet_key) for component in by_root.values()]


def _unique_assignment(costs: np.ndarray, cost_inf: float) -> list[tuple[int, int]]:
    if costs.size == 0:
        return []
    try:
        from scipy.optimize import linear_sum_assignment  # type: ignore

        rows, cols = linear_sum_assignment(costs)
        return [
            (int(row), int(col))
            for row, col in zip(rows, cols)
            if isfinite(float(costs[row, col])) and float(costs[row, col]) < cost_inf
        ]
    except Exception:
        return _greedy_unique_assignment(costs, cost_inf)


def _greedy_unique_assignment(costs: np.ndarray, cost_inf: float) -> list[tuple[int, int]]:
    candidates: list[tuple[float, int, int]] = []
    for row in range(costs.shape[0]):
        for col in range(costs.shape[1]):
            value = float(costs[row, col])
            if isfinite(value) and value < cost_inf:
                candidates.append((value, row, col))
    assigned_rows: set[int] = set()
    assigned_cols: set[int] = set()
    matches: list[tuple[int, int]] = []
    for _, row, col in sorted(candidates):
        if row in assigned_rows or col in assigned_cols:
            continue
        assigned_rows.add(row)
        assigned_cols.add(col)
        matches.append((row, col))
    return matches
