"""Terminal association logic for offline research evaluation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import exp, hypot, isfinite, sqrt
from typing import Any, Iterable, Mapping

import numpy as np

from .geometry import mahalanobis_d2, project_track
from .identity import IdentityChecker
from .models import (
    Assignment,
    CameraModel,
    CostBreakdown,
    CostMatrixResult,
    GlobalTrack,
    IdentityClaim,
    LocalVisualTrack,
    ProjectionResult,
    ReconImageCue,
    TerminalAssociation,
)


AUTHORIZED_ASSIGNMENT_STATES = {
    "authorized",
    "approved",
    "human_approved",
    "operator_approved",
    "recorded",
}


@dataclass(frozen=True)
class AssociationConfig:
    """Tunable conservative association parameters."""

    gate_chi2: float = 9.21
    min_lock_margin: float = 3.0
    max_lock_cost: float = 14.0
    rate_sigma_px_s: float = 40.0
    rate_cost_weight: float = 1.0
    category_mismatch_penalty: float = 16.0
    unverified_identity_penalty: float = 6.0
    friend_conflict_penalty: float = 1_000_000.0
    min_mot_history: int = 2
    min_lock_quality: float = 0.6
    mot_history_penalty: float = 0.5
    quality_penalty_weight: float = 2.0
    recon_cue_bonus: float = 2.0
    recon_cue_center_threshold_px: float = 30.0
    max_recon_cue_age_s: float | None = 1.0
    allow_broadcast_recon_cue: bool = True
    friend_center_threshold_px: float = 20.0
    friend_iou_threshold: float = 0.05
    projection_regularization: float = 1e-6
    image_margin_px: float = 0.0
    cost_inf: float = 1e12
    max_measurement_age_s: float | None = None
    stable_window_frames: int = 3
    stable_required_observations: int = 2
    stable_window_max_age_s: float | None = 1.0
    reacquire_search_enabled: bool = True
    reacquire_search_radius_px: float = 45.0
    reacquire_search_sigma_scale: float = 3.0
    reacquire_min_margin: float = 1.0
    reacquire_min_lock_margin: float = 4.0
    reacquire_min_mot_history: int = 2
    reacquire_min_quality: float = 0.55
    reacquire_bbox_area_ratio_min: float = 0.25
    reacquire_bbox_area_ratio_max: float = 4.0
    reacquire_history_timeout_s: float | None = 2.0
    calibration_good_reprojection_error_px: float = 8.0
    calibration_warn_reprojection_error_px: float = 20.0
    calibration_drift_reprojection_error_px: float = 30.0
    trusted_camera_pose_sources: tuple[str, ...] = (
        "airsim_camera_pose",
        "runtime_guidance_pose",
        "calibrated_camera_pose",
    )


@dataclass(frozen=True)
class _CandidateHistoryEntry:
    local_track_id: str
    timestamp: float | None
    bbox: tuple[float, float, float, float] | None
    lockable: bool


@dataclass
class _AssociationHistory:
    candidate_history: deque[_CandidateHistoryEntry] = field(default_factory=lambda: deque(maxlen=32))
    last_decision_state: str | None = None
    last_locked_local_track_id: str | None = None
    last_locked_bbox: tuple[float, float, float, float] | None = None
    last_locked_center_px: tuple[float, float] | None = None
    last_locked_timestamp: float | None = None


@dataclass(frozen=True)
class _ReacquireCandidate:
    local_index: int
    local_track: LocalVisualTrack
    score: float
    distance_px: float
    search_radius_px: float
    same_local_track_id: bool
    bbox_area_ratio: float | None
    bbox_consistent: bool
    stability_count: int
    friend_conflict_state: str = "none"
    reason: str = "reacquire_search_candidate"


@dataclass(frozen=True)
class _ReacquireSearchResult:
    candidates: tuple[_ReacquireCandidate, ...]
    search_center_px: tuple[float, float] | None
    search_radius_px: float | None
    selected: _ReacquireCandidate | None = None
    decision: str = "reacquire"
    reason: str = "no_reacquire_candidate_inside_search_window"


class TerminalAssociator:
    """Associate local visual tracks with center-assigned global tracks."""

    def __init__(
        self,
        config: AssociationConfig | None = None,
        identity_checker: IdentityChecker | None = None,
    ) -> None:
        self.config = config or AssociationConfig()
        self.identity_checker = identity_checker or IdentityChecker()
        self._histories: dict[tuple[str, str], _AssociationHistory] = {}

    def clear_history(self) -> None:
        """Drop retained temporal association state."""

        self._histories.clear()

    def project_tracks_to_image(
        self,
        global_tracks: Iterable[GlobalTrack],
        camera: CameraModel,
        timestamp: float | None = None,
    ) -> dict[str, ProjectionResult]:
        """Project global tracks into the image.

        The returned dictionary is keyed by existing `global_track_id` values.
        No IDs are created, rewritten, or normalized.
        """

        projections: dict[str, ProjectionResult] = {}
        for track in global_tracks:
            projected_track = self._predict_track(track, timestamp)
            projections[track.global_track_id] = project_track(
                projected_track,
                camera,
                regularization=self.config.projection_regularization,
                image_margin_px=self.config.image_margin_px,
            )
        return projections

    def build_cost_matrix(
        self,
        projections: Mapping[str, ProjectionResult],
        local_tracks: Iterable[LocalVisualTrack],
        identity_claims: Iterable[IdentityClaim] = (),
        recon_image_cues: Iterable[ReconImageCue] = (),
        resource_id: str | None = None,
        current_time: float | None = None,
        frame_id: str | None = None,
    ) -> CostMatrixResult:
        """Build a gated association cost matrix.

        Costs outside the Mahalanobis gate are set to `config.cost_inf`.
        """

        global_ids = list(projections.keys())
        locals_list = list(local_tracks)
        local_ids = [track.local_track_id for track in locals_list]
        claims = list(identity_claims)
        cues = list(recon_image_cues)
        costs = np.full((len(global_ids), len(local_ids)), self.config.cost_inf, dtype=float)
        breakdowns: dict[tuple[str, str], CostBreakdown] = {}

        for row, global_id in enumerate(global_ids):
            projection = projections[global_id]
            for col, local in enumerate(locals_list):
                breakdown = self._pair_cost(
                    projection,
                    local,
                    claims,
                    cues,
                    resource_id,
                    current_time,
                    frame_id,
                )
                costs[row, col] = breakdown.total_cost
                breakdowns[(global_id, local.local_track_id)] = breakdown

        return CostMatrixResult(
            global_track_ids=global_ids,
            local_track_ids=local_ids,
            costs=costs,
            breakdowns=breakdowns,
        )

    def decide(
        self,
        assignment: Assignment,
        global_tracks: Iterable[GlobalTrack],
        local_tracks: Iterable[LocalVisualTrack],
        identity_claims: Iterable[IdentityClaim] = (),
        camera: CameraModel | None = None,
        current_time: float | None = None,
        recon_image_cues: Iterable[ReconImageCue] = (),
        frame_id: str | None = None,
        camera_pose_source: str | None = None,
    ) -> TerminalAssociation:
        """Return a conservative terminal association decision.

        The method only evaluates the center-assigned global track. It never
        lets local evidence switch the assignment to another `global_track_id`.
        """

        if camera is None:
            raise ValueError("camera is required for terminal association")

        global_list = list(global_tracks)
        input_global_ids = tuple(track.global_track_id for track in global_list)
        local_list = list(local_tracks)
        local_by_id = {track.local_track_id: track for track in local_list}
        claims = list(identity_claims)
        cues = list(recon_image_cues)
        pose_source = _camera_pose_source_value(camera_pose_source)
        history = self._history_for(assignment)
        assigned = self._find_assigned_track(assignment, global_list)
        projection_time = self._projection_time(assignment, assigned, local_list, current_time)

        if assignment.authorization_state.lower() not in AUTHORIZED_ASSIGNMENT_STATES:
            association = self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="hold",
                reason="assignment_not_authorized",
                metadata=self._base_metadata(assignment, pose_source)
                | {
                    "authorization_state": assignment.authorization_state,
                    "gate_pass_count": 0,
                    "candidate_pair_logs": [],
                },
            )
            return self._finalize_association(history, association, local_by_id, projection_time, lockable=False)

        if assigned is None:
            association = self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="reacquire",
                reason="assigned_global_track_not_available",
                metadata=self._base_metadata(assignment, pose_source)
                | {
                    "available_global_track_ids": list(input_global_ids),
                    "gate_pass_count": 0,
                    "candidate_pair_logs": [],
                },
            )
            return self._finalize_association(history, association, local_by_id, projection_time, lockable=False)

        if assignment.require_version_match and assigned.track_version != assignment.assignment_version:
            association = self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="hold",
                reason="assignment_version_mismatch",
                metadata=self._base_metadata(assignment, pose_source)
                | {
                    "global_track_version": assigned.track_version,
                    "gate_pass_count": 0,
                    "candidate_pair_logs": [],
                },
            )
            return self._finalize_association(history, association, local_by_id, projection_time, lockable=False)

        projections = self.project_tracks_to_image([assigned], camera, timestamp=projection_time)
        projection = projections[assignment.assigned_global_track_id]
        if not projection.valid:
            association = self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="reacquire",
                reason=f"projection_invalid:{projection.reason}",
                metadata=self._projection_metadata(
                    assignment=assignment,
                    projection=projection,
                    projection_time=projection_time,
                    camera_pose_source=pose_source,
                )
                | {"gate_pass_count": 0, "candidate_pair_logs": []},
            )
            return self._finalize_association(history, association, local_by_id, projection_time, lockable=False)

        cost_result = self.build_cost_matrix(
            projections,
            local_list,
            claims,
            recon_image_cues=cues,
            resource_id=assignment.resource_id,
            current_time=projection_time,
            frame_id=frame_id,
        )
        row = cost_result.costs[0] if cost_result.costs.shape[0] else np.array([])
        feasible_indices = [
            index
            for index, value in enumerate(row)
            if np.isfinite(value) and value < self.config.cost_inf
        ]
        decision_metadata = self._decision_metadata(
            assignment=assignment,
            projection=projection,
            projection_time=projection_time,
            cost_result=cost_result,
            feasible_indices=feasible_indices,
            camera_pose_source=pose_source,
        )

        if not feasible_indices:
            reacquire_result = self._search_reacquire_candidates(
                assignment=assignment,
                projection=projection,
                local_tracks=local_list,
                identity_claims=claims,
                history=history,
                timestamp=projection_time,
            )
            if reacquire_result.selected is not None:
                selected = reacquire_result.selected
                selected_local = selected.local_track
                margin = _reacquire_margin(reacquire_result.candidates)
                ambiguity = 0.0 if not isfinite(margin) else 1.0 / (1.0 + max(0.0, margin))
                confidence = self._reacquire_confidence(selected)
                friend_state = selected.friend_conflict_state
                decision = reacquire_result.decision
                reason = reacquire_result.reason
                if friend_state != "none":
                    decision = "hold"
                    reason = f"active_reacquire_blocked_by_{friend_state}"
                metadata = decision_metadata | self._reacquire_metadata(
                    reacquire_result,
                    decision=decision,
                    reason=reason,
                    friend_conflict_state=friend_state,
                )
                self._assert_global_ids_unchanged(input_global_ids, global_list)
                association = self._association(
                    assignment,
                    local_track_id=selected_local.local_track_id,
                    confidence=confidence if decision == "locked" else min(confidence, 0.5),
                    ambiguity=ambiguity if decision == "locked" else max(ambiguity, 0.5),
                    friend_state=friend_state,
                    decision=decision,
                    reason=reason,
                    candidate_costs=[
                        (candidate.local_track.local_track_id, candidate.score)
                        for candidate in reacquire_result.candidates
                    ],
                    metadata=metadata,
                )
                return self._finalize_association(
                    history,
                    association,
                    local_by_id,
                    projection_time,
                    lockable=decision != "hold",
                )

            self._assert_global_ids_unchanged(input_global_ids, global_list)
            association = self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="reacquire",
                reason="no_local_track_inside_projection_gate",
                metadata=decision_metadata | self._reacquire_metadata(reacquire_result),
            )
            return self._finalize_association(history, association, local_by_id, projection_time, lockable=False)

        # A verified friend overlapping any gated candidate forces hold.
        friend_conflicts = []
        for index in feasible_indices:
            local_id = cost_result.local_track_ids[index]
            breakdown = cost_result.breakdowns[(assignment.assigned_global_track_id, local_id)]
            if breakdown.friend_conflict_state == "verified_friend_overlap":
                friend_conflicts.append((index, breakdown.total_cost))
        if friend_conflicts:
            friend_conflicts.sort(key=lambda item: item[1])
            local_id = cost_result.local_track_ids[friend_conflicts[0][0]]
            self._assert_global_ids_unchanged(input_global_ids, global_list)
            association = self._association(
                assignment,
                local_track_id=local_id,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="verified_friend_overlap",
                decision="hold",
                reason="verified_friend_overlap_inside_gate",
                candidate_costs=self._candidate_costs(cost_result, feasible_indices),
                metadata=self._decision_metadata(
                    assignment=assignment,
                    projection=projection,
                    projection_time=projection_time,
                    cost_result=cost_result,
                    feasible_indices=feasible_indices,
                    selected_local_track_id=local_id,
                    camera_pose_source=pose_source,
                ),
            )
            return self._finalize_association(history, association, local_by_id, projection_time, lockable=False)

        ordered = sorted(feasible_indices, key=lambda index: row[index])
        best_index = ordered[0]
        best_local_id = cost_result.local_track_ids[best_index]
        best_breakdown = cost_result.breakdowns[(assignment.assigned_global_track_id, best_local_id)]
        best_cost = float(row[best_index])
        second_cost = float(row[ordered[1]]) if len(ordered) > 1 else float("inf")
        margin = second_cost - best_cost if isfinite(second_cost) else float("inf")
        confidence = self._confidence(best_breakdown, local_list[best_index])
        ambiguity = 0.0 if not isfinite(margin) else 1.0 / (1.0 + max(0.0, margin))
        selected_local = local_list[best_index]
        temporal_reason = self._temporal_lock_block_reason(
            history=history,
            local_track=selected_local,
            timestamp=projection_time,
        )
        stale_reason = self._stale_measurement_reason(selected_local, projection_time)
        required_margin = self._required_lock_margin(history)

        nonverified_identity_overlap = best_breakdown.friend_conflict_state in {
            "spoof_suspected_overlap",
            "stale_friend_overlap",
            "unverified_friend_overlap",
        }
        if nonverified_identity_overlap:
            decision = "ambiguous"
            reason = best_breakdown.friend_conflict_state
        elif best_cost > self.config.max_lock_cost:
            decision = "ambiguous"
            reason = "best_cost_exceeds_lock_threshold"
        elif isfinite(margin) and margin < required_margin:
            decision = "ambiguous"
            reason = "insufficient_best_second_margin"
        elif selected_local.mot_history_length < self.config.min_mot_history:
            decision = "ambiguous"
            reason = "mot_history_too_short"
        elif selected_local.quality < self.config.min_lock_quality:
            decision = "ambiguous"
            reason = "local_track_quality_too_low"
        elif stale_reason is not None:
            decision = "ambiguous"
            reason = stale_reason
        elif temporal_reason is not None:
            decision = "ambiguous"
            reason = temporal_reason
        else:
            decision = "locked"
            reason = "unique_candidate_inside_gate"

        self._assert_global_ids_unchanged(input_global_ids, global_list)
        association = self._association(
            assignment,
            local_track_id=best_local_id,
            confidence=confidence if decision == "locked" else min(confidence, 0.5),
            ambiguity=ambiguity if decision == "locked" else max(ambiguity, 0.5),
            friend_state=best_breakdown.friend_conflict_state,
            decision=decision,
            reason=reason,
            candidate_costs=self._candidate_costs(cost_result, feasible_indices),
            recon_cue_used=best_breakdown.recon_cue_cost < 0.0,
            metadata=self._decision_metadata(
                assignment=assignment,
                projection=projection,
                projection_time=projection_time,
                cost_result=cost_result,
                feasible_indices=feasible_indices,
                selected_local_track_id=best_local_id,
                camera_pose_source=pose_source,
            ),
        )
        association.metadata.update(
            self._temporal_metadata(
                history=history,
                local_track=selected_local,
                timestamp=projection_time,
                required_margin=required_margin,
                candidate_margin=margin,
            )
        )
        return self._finalize_association(
            history,
            association,
            local_by_id,
            projection_time,
            lockable=decision in {"locked", "ambiguous"},
        )

    def _pair_cost(
        self,
        projection: ProjectionResult,
        local_track: LocalVisualTrack,
        identity_claims: list[IdentityClaim],
        recon_image_cues: list[ReconImageCue],
        resource_id: str | None,
        current_time: float | None,
        frame_id: str | None,
    ) -> CostBreakdown:
        projected_px = _projection_pixel_tuple(projection)
        bbox_center_px = (float(local_track.center_px[0]), float(local_track.center_px[1]))
        pixel_error_px = _pixel_error_px(projection, local_track)
        measurement_age_s = _measurement_age_s(local_track, current_time)
        if not projection.valid:
            return self._blocked_breakdown(
                projection.global_track_id,
                local_track.local_track_id,
                "none",
                projected_px=projected_px,
                bbox_center_px=bbox_center_px,
                pixel_error_px=pixel_error_px,
                measurement_age_s=measurement_age_s,
            )

        d2 = mahalanobis_d2(local_track.center_px, projection)
        if d2 > self.config.gate_chi2:
            return CostBreakdown(
                global_track_id=projection.global_track_id,
                local_track_id=local_track.local_track_id,
                total_cost=self.config.cost_inf,
                mahalanobis_d2=d2,
                rate_cost=0.0,
                category_cost=0.0,
                friend_cost=0.0,
                quality_cost=0.0,
                gated=False,
                friend_conflict_state="none",
                projected_px=projected_px,
                bbox_center_px=bbox_center_px,
                pixel_error_px=pixel_error_px,
                measurement_age_s=measurement_age_s,
            )

        rate_cost = self._rate_cost(projection, local_track)
        category_cost = self._category_cost(projection, local_track)
        quality_cost = self._quality_cost(local_track)
        recon_cue_cost = self._recon_cue_cost(
            projection,
            local_track,
            recon_image_cues,
            resource_id,
            current_time,
            frame_id,
        )
        friend_state = self.identity_checker.friend_conflict_state(
            local_track,
            identity_claims,
            center_threshold_px=self.config.friend_center_threshold_px,
            iou_threshold=self.config.friend_iou_threshold,
        )
        friend_cost = self._friend_cost(friend_state)
        total_cost = d2 + rate_cost + category_cost + quality_cost + friend_cost + recon_cue_cost
        return CostBreakdown(
            global_track_id=projection.global_track_id,
            local_track_id=local_track.local_track_id,
            total_cost=float(total_cost),
            mahalanobis_d2=float(d2),
            rate_cost=float(rate_cost),
            category_cost=float(category_cost),
            friend_cost=float(friend_cost),
            quality_cost=float(quality_cost),
            gated=True,
            friend_conflict_state=friend_state,
            recon_cue_cost=float(recon_cue_cost),
            projected_px=projected_px,
            bbox_center_px=bbox_center_px,
            pixel_error_px=pixel_error_px,
            measurement_age_s=measurement_age_s,
        )

    def _blocked_breakdown(
        self,
        global_track_id: str,
        local_track_id: str,
        friend_state: str,
        *,
        projected_px: tuple[float, float] | None = None,
        bbox_center_px: tuple[float, float] | None = None,
        pixel_error_px: float | None = None,
        measurement_age_s: float | None = None,
    ) -> CostBreakdown:
        return CostBreakdown(
            global_track_id=global_track_id,
            local_track_id=local_track_id,
            total_cost=self.config.cost_inf,
            mahalanobis_d2=float("inf"),
            rate_cost=0.0,
            category_cost=0.0,
            friend_cost=0.0,
            quality_cost=0.0,
            gated=False,
            friend_conflict_state=friend_state,
            projected_px=projected_px,
            bbox_center_px=bbox_center_px,
            pixel_error_px=pixel_error_px,
            measurement_age_s=measurement_age_s,
        )

    def _rate_cost(self, projection: ProjectionResult, local_track: LocalVisualTrack) -> float:
        if self.config.rate_sigma_px_s <= 0:
            return 0.0
        delta = local_track.bearing_rate - projection.predicted_px_velocity
        normalized = float(np.linalg.norm(delta) / self.config.rate_sigma_px_s)
        if not np.isfinite(normalized):
            return self.config.cost_inf
        return self.config.rate_cost_weight * normalized * normalized

    def _category_cost(self, projection: ProjectionResult, local_track: LocalVisualTrack) -> float:
        # Unknown categories are intentionally neutral; positive friend evidence
        # is handled by the identity checker and can force hold.
        if projection.category == "unknown" or local_track.category == "unknown":
            return 0.0
        if projection.category != local_track.category:
            return self.config.category_mismatch_penalty
        return 0.0

    def _quality_cost(self, local_track: LocalVisualTrack) -> float:
        quality_term = (1.0 - local_track.quality) * self.config.quality_penalty_weight
        history_deficit = max(0, self.config.min_mot_history - local_track.mot_history_length)
        return quality_term + history_deficit * self.config.mot_history_penalty

    def _friend_cost(self, friend_state: str) -> float:
        if friend_state == "verified_friend_overlap":
            return self.config.friend_conflict_penalty
        if friend_state in {
            "spoof_suspected_overlap",
            "stale_friend_overlap",
            "unverified_friend_overlap",
        }:
            return self.config.unverified_identity_penalty
        return 0.0

    def _recon_cue_cost(
        self,
        projection: ProjectionResult,
        local_track: LocalVisualTrack,
        recon_image_cues: list[ReconImageCue],
        resource_id: str | None,
        current_time: float | None,
        frame_id: str | None,
    ) -> float:
        for cue in recon_image_cues:
            if not self._recon_cue_is_applicable(cue, projection, resource_id, current_time, frame_id):
                continue
            if cue.center_px is None:
                continue
            distance = float(np.linalg.norm(local_track.center_px - cue.center_px))
            if distance <= self.config.recon_cue_center_threshold_px:
                return -self.config.recon_cue_bonus * cue.confidence
        return 0.0

    def _recon_cue_is_applicable(
        self,
        cue: ReconImageCue,
        projection: ProjectionResult,
        resource_id: str | None,
        current_time: float | None,
        frame_id: str | None,
    ) -> bool:
        if cue.confidence <= 0.0 or cue.metadata.get("expired") is True:
            return False
        if cue.global_track_id is not None and cue.global_track_id != projection.global_track_id:
            return False
        if cue.scoped_resource_ids:
            if resource_id is None or resource_id not in cue.scoped_resource_ids:
                return False
        elif not self.config.allow_broadcast_recon_cue:
            return False
        if self.config.max_recon_cue_age_s is not None and current_time is not None:
            age_s = float(current_time) - cue.timestamp
            if age_s < 0.0 or age_s > self.config.max_recon_cue_age_s:
                return False
        if frame_id is not None and not self._recon_cue_matches_frame(cue, frame_id):
            return False
        return True

    @staticmethod
    def _recon_cue_matches_frame(cue: ReconImageCue, frame_id: str) -> bool:
        target_frame_id = cue.metadata.get("target_frame_id")
        source_frame_id = cue.metadata.get("source_image_frame_id")
        reprojected = cue.metadata.get("reprojected_to_local_camera") is True

        if cue.image_frame_id == frame_id:
            if source_frame_id is not None and source_frame_id != frame_id:
                return reprojected
            return True
        if target_frame_id == frame_id:
            return reprojected
        return False

    def _confidence(self, breakdown: CostBreakdown, local_track: LocalVisualTrack) -> float:
        if not np.isfinite(breakdown.mahalanobis_d2):
            return 0.0
        geometry_score = exp(-0.5 * min(100.0, breakdown.mahalanobis_d2))
        history_score = min(1.0, max(0.0, local_track.mot_history_length / 5.0))
        confidence = geometry_score * local_track.quality * history_score
        return float(np.clip(confidence, 0.0, 1.0))

    def _find_assigned_track(
        self,
        assignment: Assignment,
        global_tracks: list[GlobalTrack],
    ) -> GlobalTrack | None:
        for track in global_tracks:
            if track.global_track_id == assignment.assigned_global_track_id:
                return track
        return None

    @staticmethod
    def _projection_time(
        assignment: Assignment,
        assigned: GlobalTrack | None,
        local_tracks: list[LocalVisualTrack],
        current_time: float | None,
    ) -> float | None:
        if current_time is not None:
            return float(current_time)
        if local_tracks:
            return max(track.timestamp for track in local_tracks)
        if assignment.timestamp > 0.0:
            return assignment.timestamp
        if assigned is not None:
            return assigned.timestamp
        return None

    @staticmethod
    def _predict_track(track: GlobalTrack, timestamp: float | None) -> GlobalTrack:
        if timestamp is None:
            return track
        dt = float(timestamp) - track.timestamp
        if abs(dt) <= 1e-12:
            return track
        covariance = track.covariance.copy()
        if dt > 0.0:
            covariance = covariance + np.eye(3) * min(dt * dt * 0.05, 25.0)
        return GlobalTrack(
            global_track_id=track.global_track_id,
            position=track.position + track.velocity * dt,
            covariance=covariance,
            velocity=track.velocity,
            category=track.category,
            timestamp=float(timestamp),
            track_version=track.track_version,
        )

    def _association(
        self,
        assignment: Assignment,
        local_track_id: str | None,
        confidence: float,
        ambiguity: float,
        friend_state: str,
        decision: str,
        reason: str,
        candidate_costs: list[tuple[str, float]] | None = None,
        recon_cue_used: bool = False,
        metadata: dict | None = None,
    ) -> TerminalAssociation:
        return TerminalAssociation(
            assigned_global_track_id=assignment.assigned_global_track_id,
            local_track_id=local_track_id,
            association_confidence=float(np.clip(confidence, 0.0, 1.0)),
            ambiguity_score=float(np.clip(ambiguity, 0.0, 1.0)),
            friend_conflict_state=friend_state,
            decision_state=decision,
            assignment_version=assignment.assignment_version,
            reason=reason,
            candidate_costs=candidate_costs or [],
            recon_cue_used=recon_cue_used,
            metadata=metadata or {},
        )

    def _candidate_costs(
        self,
        cost_result: CostMatrixResult,
        indices: list[int],
    ) -> list[tuple[str, float]]:
        row = cost_result.costs[0]
        return sorted(
            [(cost_result.local_track_ids[index], float(row[index])) for index in indices],
            key=lambda item: item[1],
        )

    def _assert_global_ids_unchanged(
        self,
        expected_ids: tuple[str, ...],
        global_tracks: list[GlobalTrack],
    ) -> None:
        observed_ids = tuple(track.global_track_id for track in global_tracks)
        if observed_ids != expected_ids:
            raise RuntimeError("terminal association attempted to alter global_track_id values")

    def _history_for(self, assignment: Assignment) -> _AssociationHistory:
        key = (str(assignment.resource_id or ""), assignment.assigned_global_track_id)
        return self._histories.setdefault(key, _AssociationHistory())

    def _finalize_association(
        self,
        history: _AssociationHistory,
        association: TerminalAssociation,
        local_tracks_by_id: Mapping[str, LocalVisualTrack],
        timestamp: float | None,
        *,
        lockable: bool,
    ) -> TerminalAssociation:
        local_track = (
            local_tracks_by_id.get(association.local_track_id)
            if association.local_track_id is not None
            else None
        )
        if local_track is not None:
            history.candidate_history.append(
                _CandidateHistoryEntry(
                    local_track_id=local_track.local_track_id,
                    timestamp=timestamp,
                    bbox=local_track.bbox,
                    lockable=lockable or association.decision_state == "locked",
                )
            )
        if association.decision_state == "locked" and local_track is not None:
            history.last_locked_local_track_id = local_track.local_track_id
            history.last_locked_bbox = local_track.bbox
            history.last_locked_center_px = (
                float(local_track.center_px[0]),
                float(local_track.center_px[1]),
            )
            history.last_locked_timestamp = timestamp
        history.last_decision_state = association.decision_state
        return association

    def _base_metadata(self, assignment: Assignment, camera_pose_source: str) -> dict[str, Any]:
        metadata = {
            "assigned_global_track_id": assignment.assigned_global_track_id,
            "assignment_version": assignment.assignment_version,
            "resource_id": assignment.resource_id,
            "global_id_policy": "existing_assigned_global_track_id_only",
            "truth_id_online_use": "ignored",
        }
        metadata.update(
            calibration_health_metadata(
                projection_valid=None,
                reprojection_error=None,
                camera_pose_source=camera_pose_source,
                good_error_px=self.config.calibration_good_reprojection_error_px,
                warn_error_px=self.config.calibration_warn_reprojection_error_px,
                drift_error_px=self.config.calibration_drift_reprojection_error_px,
                trusted_camera_pose_sources=self.config.trusted_camera_pose_sources,
            )
        )
        return metadata

    def _projection_metadata(
        self,
        *,
        assignment: Assignment,
        projection: ProjectionResult,
        projection_time: float | None,
        camera_pose_source: str,
        reprojection_error: float | None = None,
    ) -> dict:
        metadata = self._base_metadata(assignment, camera_pose_source)
        metadata.update(
            {
            "projection_timestamp": projection_time,
            "projection_valid": projection.valid,
            "projection_reason": projection.reason,
            "projection_depth_m": float(projection.depth),
            "projected_px": (
                [float(projection.pixel[0]), float(projection.pixel[1])]
                if projection.pixel is not None
                else None
            ),
            "projection_covariance_px": (
                np.asarray(projection.covariance_px, dtype=float).tolist()
                if projection.covariance_px is not None
                else None
            ),
            }
        )
        metadata.update(
            calibration_health_metadata(
                projection_valid=projection.valid,
                reprojection_error=reprojection_error,
                camera_pose_source=camera_pose_source,
                good_error_px=self.config.calibration_good_reprojection_error_px,
                warn_error_px=self.config.calibration_warn_reprojection_error_px,
                drift_error_px=self.config.calibration_drift_reprojection_error_px,
                trusted_camera_pose_sources=self.config.trusted_camera_pose_sources,
            )
        )
        return metadata

    def _decision_metadata(
        self,
        *,
        assignment: Assignment,
        projection: ProjectionResult,
        projection_time: float | None,
        cost_result: CostMatrixResult,
        feasible_indices: list[int],
        selected_local_track_id: str | None = None,
        camera_pose_source: str,
    ) -> dict:
        pair_logs = [
            cost_result.breakdowns[(assignment.assigned_global_track_id, local_id)].to_log_record()
            for local_id in cost_result.local_track_ids
        ]
        selected_pair = None
        if selected_local_track_id is not None:
            selected_pair = cost_result.breakdowns[
                (assignment.assigned_global_track_id, selected_local_track_id)
            ].to_log_record()
        reprojection_error = _representative_reprojection_error(pair_logs, selected_pair)
        metadata = self._projection_metadata(
            assignment=assignment,
            projection=projection,
            projection_time=projection_time,
            camera_pose_source=camera_pose_source,
            reprojection_error=reprojection_error,
        )
        metadata.update(
            {
                "gate_chi2": self.config.gate_chi2,
                "gate_pass_count": len(feasible_indices),
                "gate_pass_local_track_ids": [
                    cost_result.local_track_ids[index] for index in feasible_indices
                ],
                "selected_local_track_id": selected_local_track_id,
                "selected_pair": selected_pair,
                "candidate_pair_logs": pair_logs,
                "candidate_cost_margin": _candidate_margin_for_indices(
                    cost_result.costs[0] if cost_result.costs.shape[0] else np.array([]),
                    feasible_indices,
                ),
                "duplicate_terminal_lock_risk": False,
            }
        )
        return metadata

    def _stale_measurement_reason(
        self,
        local_track: LocalVisualTrack,
        current_time: float | None,
    ) -> str | None:
        if self.config.max_measurement_age_s is None or current_time is None:
            return None
        age_s = float(current_time) - float(local_track.timestamp)
        if age_s < 0.0:
            return "measurement_timestamp_out_of_sequence"
        if age_s > self.config.max_measurement_age_s:
            return "measurement_timestamp_stale"
        return None

    def _required_lock_margin(self, history: _AssociationHistory) -> float:
        if history.last_decision_state == "reacquire":
            return max(self.config.min_lock_margin, self.config.reacquire_min_lock_margin)
        return self.config.min_lock_margin

    def _temporal_lock_block_reason(
        self,
        *,
        history: _AssociationHistory,
        local_track: LocalVisualTrack,
        timestamp: float | None,
    ) -> str | None:
        if history.last_decision_state != "reacquire":
            return None
        same_local_track = local_track.local_track_id == history.last_locked_local_track_id
        stability_count = self._candidate_stability_count(history, local_track.local_track_id, timestamp)
        if same_local_track:
            return None
        if history.last_locked_bbox is not None and not _bbox_area_ratio_ok(
            history.last_locked_bbox,
            local_track.bbox,
            self.config.reacquire_bbox_area_ratio_min,
            self.config.reacquire_bbox_area_ratio_max,
        ):
            return "bbox_history_inconsistent_after_reacquire"
        if stability_count < self.config.stable_required_observations:
            return "reacquire_candidate_not_temporally_stable"
        return None

    def _temporal_metadata(
        self,
        *,
        history: _AssociationHistory,
        local_track: LocalVisualTrack,
        timestamp: float | None,
        required_margin: float,
        candidate_margin: float,
    ) -> dict[str, Any]:
        return {
            "temporal_consistency": {
                "previous_decision_state": history.last_decision_state,
                "last_locked_local_track_id": history.last_locked_local_track_id,
                "same_as_last_locked_local_track": (
                    local_track.local_track_id == history.last_locked_local_track_id
                ),
                "candidate_stability_count": self._candidate_stability_count(
                    history,
                    local_track.local_track_id,
                    timestamp,
                ),
                "stable_window_frames": self.config.stable_window_frames,
                "stable_required_observations": self.config.stable_required_observations,
                "candidate_cost_margin": (
                    float(candidate_margin) if isfinite(candidate_margin) else None
                ),
                "candidate_cost_margin_is_infinite": not isfinite(candidate_margin),
                "required_lock_margin": float(required_margin),
                "bbox_area_ratio_to_last_lock": _bbox_area_ratio(
                    history.last_locked_bbox,
                    local_track.bbox,
                ),
                "mot_history_length": local_track.mot_history_length,
            }
        }

    def _candidate_stability_count(
        self,
        history: _AssociationHistory,
        local_track_id: str,
        timestamp: float | None,
    ) -> int:
        count = 1
        inspected = 1
        for entry in reversed(history.candidate_history):
            if inspected >= self.config.stable_window_frames:
                break
            if entry.local_track_id != local_track_id or not entry.lockable:
                break
            if (
                timestamp is not None
                and entry.timestamp is not None
                and self.config.stable_window_max_age_s is not None
                and float(timestamp) - float(entry.timestamp) > self.config.stable_window_max_age_s
            ):
                break
            count += 1
            inspected += 1
        return count

    def _search_reacquire_candidates(
        self,
        *,
        assignment: Assignment,
        projection: ProjectionResult,
        local_tracks: list[LocalVisualTrack],
        identity_claims: list[IdentityClaim],
        history: _AssociationHistory,
        timestamp: float | None,
    ) -> _ReacquireSearchResult:
        if not self.config.reacquire_search_enabled or projection.pixel is None:
            return _ReacquireSearchResult(
                candidates=(),
                search_center_px=_projection_pixel_tuple(projection),
                search_radius_px=None,
                reason="reacquire_search_disabled_or_projection_unavailable",
            )

        radius = self._reacquire_search_radius(projection, history, timestamp)
        candidates: list[_ReacquireCandidate] = []
        for index, local_track in enumerate(local_tracks):
            distance_px = float(np.linalg.norm(local_track.center_px - projection.pixel))
            if distance_px > radius:
                continue
            if local_track.quality < self.config.reacquire_min_quality:
                continue
            if local_track.mot_history_length < self.config.reacquire_min_mot_history:
                continue
            if not self._history_recent_enough(history, timestamp):
                continue

            same_local_track = local_track.local_track_id == history.last_locked_local_track_id
            bbox_area_ratio = _bbox_area_ratio(history.last_locked_bbox, local_track.bbox)
            bbox_consistent = (
                history.last_locked_bbox is None
                or _bbox_area_ratio_ok(
                    history.last_locked_bbox,
                    local_track.bbox,
                    self.config.reacquire_bbox_area_ratio_min,
                    self.config.reacquire_bbox_area_ratio_max,
                )
            )
            if not same_local_track and not bbox_consistent:
                continue

            stability_count = self._candidate_stability_count(history, local_track.local_track_id, timestamp)
            score = _reacquire_score(
                distance_px=distance_px,
                radius_px=radius,
                local_track=local_track,
                same_local_track_id=same_local_track,
                bbox_consistent=bbox_consistent,
            )
            candidates.append(
                _ReacquireCandidate(
                    local_index=index,
                    local_track=local_track,
                    score=score,
                    distance_px=distance_px,
                    search_radius_px=radius,
                    same_local_track_id=same_local_track,
                    bbox_area_ratio=bbox_area_ratio,
                    bbox_consistent=bbox_consistent,
                    stability_count=stability_count,
                    friend_conflict_state=self.identity_checker.friend_conflict_state(
                        local_track,
                        identity_claims,
                        center_threshold_px=self.config.friend_center_threshold_px,
                        iou_threshold=self.config.friend_iou_threshold,
                    ),
                )
            )

        candidates.sort(key=lambda candidate: candidate.score)
        if not candidates:
            return _ReacquireSearchResult(
                candidates=(),
                search_center_px=_projection_pixel_tuple(projection),
                search_radius_px=radius,
            )

        best = candidates[0]
        margin = _reacquire_margin(tuple(candidates))
        if isfinite(margin) and margin < self.config.reacquire_min_margin:
            return _ReacquireSearchResult(
                candidates=tuple(candidates),
                search_center_px=_projection_pixel_tuple(projection),
                search_radius_px=radius,
                selected=best,
                decision="ambiguous",
                reason="reacquire_search_ambiguous",
            )
        if (
            not best.same_local_track_id
            and best.stability_count < self.config.stable_required_observations
        ):
            return _ReacquireSearchResult(
                candidates=tuple(candidates),
                search_center_px=_projection_pixel_tuple(projection),
                search_radius_px=radius,
                selected=best,
                decision="ambiguous",
                reason="reacquire_candidate_not_temporally_stable",
            )
        if assignment.assigned_global_track_id != projection.global_track_id:
            return _ReacquireSearchResult(
                candidates=tuple(candidates),
                search_center_px=_projection_pixel_tuple(projection),
                search_radius_px=radius,
                selected=best,
                decision="hold",
                reason="assigned_global_track_projection_mismatch",
            )
        return _ReacquireSearchResult(
            candidates=tuple(candidates),
            search_center_px=_projection_pixel_tuple(projection),
            search_radius_px=radius,
            selected=best,
            decision="locked",
            reason="reacquired_assigned_track_in_search_window",
        )

    def _reacquire_search_radius(
        self,
        projection: ProjectionResult,
        history: _AssociationHistory,
        timestamp: float | None,
    ) -> float:
        radius = float(self.config.reacquire_search_radius_px)
        if projection.covariance_px is not None:
            eigvals = np.linalg.eigvalsh(projection.covariance_px)
            max_sigma = sqrt(max(0.0, float(np.max(eigvals))))
            radius = max(radius, self.config.reacquire_search_sigma_scale * max_sigma)
        if history.last_locked_bbox is not None:
            x1, y1, x2, y2 = history.last_locked_bbox
            radius = max(radius, 0.75 * hypot(x2 - x1, y2 - y1))
        if (
            timestamp is not None
            and history.last_locked_timestamp is not None
            and projection.predicted_px_velocity is not None
        ):
            dt = max(0.0, float(timestamp) - float(history.last_locked_timestamp))
            radius += min(60.0, float(np.linalg.norm(projection.predicted_px_velocity)) * dt)
        return float(radius)

    def _history_recent_enough(
        self,
        history: _AssociationHistory,
        timestamp: float | None,
    ) -> bool:
        if self.config.reacquire_history_timeout_s is None:
            return True
        if timestamp is None or history.last_locked_timestamp is None:
            return history.last_locked_local_track_id is not None
        return float(timestamp) - float(history.last_locked_timestamp) <= self.config.reacquire_history_timeout_s

    def _reacquire_confidence(self, candidate: _ReacquireCandidate) -> float:
        geometry_score = exp(-0.5 * min(25.0, (candidate.distance_px / max(candidate.search_radius_px, 1e-6)) ** 2))
        history_score = min(1.0, max(0.0, candidate.stability_count / self.config.stable_required_observations))
        if candidate.same_local_track_id:
            history_score = max(history_score, 0.9)
        bbox_score = 1.0 if candidate.bbox_consistent else 0.5
        confidence = geometry_score * candidate.local_track.quality * history_score * bbox_score
        return float(np.clip(confidence, 0.0, 1.0))

    def _reacquire_metadata(
        self,
        result: _ReacquireSearchResult,
        *,
        decision: str | None = None,
        reason: str | None = None,
        friend_conflict_state: str = "none",
    ) -> dict[str, Any]:
        return {
            "active_reacquire": True,
            "reacquire_search_window": {
                "source": "global_track_prediction_bbox_mot_history",
                "center_px": list(result.search_center_px) if result.search_center_px is not None else None,
                "radius_px": result.search_radius_px,
                "candidate_count": len(result.candidates),
                "selected_local_track_id": (
                    result.selected.local_track.local_track_id if result.selected is not None else None
                ),
                "decision": decision or result.decision,
                "reason": reason or result.reason,
                "friend_conflict_state": friend_conflict_state,
            },
            "reacquire_candidates": [
                {
                    "local_track_id": candidate.local_track.local_track_id,
                    "score": float(candidate.score),
                    "distance_px": float(candidate.distance_px),
                    "search_radius_px": float(candidate.search_radius_px),
                    "same_local_track_id": candidate.same_local_track_id,
                    "bbox_area_ratio_to_last_lock": candidate.bbox_area_ratio,
                    "bbox_consistent_with_last_lock": candidate.bbox_consistent,
                    "stability_count": candidate.stability_count,
                    "mot_history_length": candidate.local_track.mot_history_length,
                    "quality": candidate.local_track.quality,
                    "friend_conflict_state": candidate.friend_conflict_state,
                }
                for candidate in result.candidates
            ],
        }


def _projection_pixel_tuple(projection: ProjectionResult) -> tuple[float, float] | None:
    if projection.pixel is None:
        return None
    return (float(projection.pixel[0]), float(projection.pixel[1]))


def _pixel_error_px(projection: ProjectionResult, local_track: LocalVisualTrack) -> float | None:
    if projection.pixel is None:
        return None
    return float(np.linalg.norm(local_track.center_px - projection.pixel))


def _measurement_age_s(local_track: LocalVisualTrack, current_time: float | None) -> float | None:
    if current_time is None:
        return None
    return float(current_time) - float(local_track.timestamp)


def calibration_health_metadata(
    *,
    projection_valid: bool | None,
    reprojection_error: float | None,
    camera_pose_source: str | None,
    good_error_px: float = 8.0,
    warn_error_px: float = 20.0,
    drift_error_px: float = 30.0,
    trusted_camera_pose_sources: tuple[str, ...] = (
        "airsim_camera_pose",
        "runtime_guidance_pose",
        "calibrated_camera_pose",
    ),
) -> dict[str, Any]:
    """Return D6/main-readable calibration health metadata."""

    source = _camera_pose_source_value(camera_pose_source)
    error = _finite_float_or_none(reprojection_error)
    source_trusted = source in trusted_camera_pose_sources
    if projection_valid is None:
        health = "not_evaluated"
        reason = "projection_not_evaluated"
        drift_warning = False
    elif not projection_valid:
        health = "projection_invalid"
        reason = "projection_invalid"
        drift_warning = False
    elif error is None:
        health = "unknown"
        reason = "no_reprojection_error_available"
        drift_warning = False
    elif error <= good_error_px:
        health = "healthy"
        reason = "reprojection_error_within_good_threshold"
        drift_warning = False
    elif error <= warn_error_px:
        health = "degraded"
        reason = "reprojection_error_within_warn_threshold"
        drift_warning = False
    else:
        health = "drift_warning"
        reason = "reprojection_error_exceeds_warn_threshold"
        drift_warning = error >= drift_error_px or error > warn_error_px

    return {
        "projection_valid": projection_valid,
        "reprojection_error": error,
        "reprojection_error_px": error,
        "camera_pose_source": source,
        "camera_pose_source_trusted": source_trusted,
        "calibration_health": health,
        "calibration_health_reason": reason,
        "drift_warning": drift_warning,
    }


def _camera_pose_source_value(value: str | None) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text if text else "unknown"


def _finite_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _representative_reprojection_error(
    pair_logs: list[dict[str, Any]],
    selected_pair: dict[str, Any] | None,
) -> float | None:
    if selected_pair is not None:
        error = _finite_float_or_none(
            selected_pair.get("reprojection_error", selected_pair.get("pixel_error_px"))
        )
        if error is not None:
            return error
    errors = [
        error
        for error in (
            _finite_float_or_none(log.get("reprojection_error", log.get("pixel_error_px")))
            for log in pair_logs
        )
        if error is not None
    ]
    return min(errors) if errors else None


def _candidate_margin_for_indices(row: np.ndarray, indices: list[int]) -> float | None:
    if len(indices) < 2:
        return None
    ordered = sorted(float(row[index]) for index in indices if np.isfinite(float(row[index])))
    if len(ordered) < 2:
        return None
    return ordered[1] - ordered[0]


def _bbox_area(bbox: tuple[float, float, float, float] | None) -> float | None:
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return float(area) if np.isfinite(area) else None


def _bbox_area_ratio(
    previous_bbox: tuple[float, float, float, float] | None,
    current_bbox: tuple[float, float, float, float] | None,
) -> float | None:
    previous_area = _bbox_area(previous_bbox)
    current_area = _bbox_area(current_bbox)
    if previous_area is None or current_area is None or previous_area <= 0.0 or current_area <= 0.0:
        return None
    return float(current_area / previous_area)


def _bbox_area_ratio_ok(
    previous_bbox: tuple[float, float, float, float] | None,
    current_bbox: tuple[float, float, float, float] | None,
    min_ratio: float,
    max_ratio: float,
) -> bool:
    ratio = _bbox_area_ratio(previous_bbox, current_bbox)
    if ratio is None:
        return False
    return float(min_ratio) <= ratio <= float(max_ratio)


def _reacquire_score(
    *,
    distance_px: float,
    radius_px: float,
    local_track: LocalVisualTrack,
    same_local_track_id: bool,
    bbox_consistent: bool,
) -> float:
    normalized_distance = distance_px / max(radius_px, 1e-6)
    history_penalty = 0.0 if same_local_track_id else 0.75
    bbox_penalty = 0.0 if bbox_consistent else 2.0
    quality_penalty = 1.0 - local_track.quality
    mot_penalty = 1.0 / max(1, local_track.mot_history_length)
    return float(normalized_distance * normalized_distance + history_penalty + bbox_penalty + quality_penalty + mot_penalty)


def _reacquire_margin(candidates: tuple[_ReacquireCandidate, ...]) -> float:
    if len(candidates) < 2:
        return float("inf")
    return float(candidates[1].score - candidates[0].score)
