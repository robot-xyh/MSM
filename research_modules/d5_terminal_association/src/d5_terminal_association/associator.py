"""Terminal association logic for offline research evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite
from typing import Iterable, Mapping

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


class TerminalAssociator:
    """Associate local visual tracks with center-assigned global tracks."""

    def __init__(
        self,
        config: AssociationConfig | None = None,
        identity_checker: IdentityChecker | None = None,
    ) -> None:
        self.config = config or AssociationConfig()
        self.identity_checker = identity_checker or IdentityChecker()

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
        claims = list(identity_claims)
        cues = list(recon_image_cues)
        assigned = self._find_assigned_track(assignment, global_list)
        projection_time = self._projection_time(assignment, assigned, local_list, current_time)

        if assignment.authorization_state.lower() not in AUTHORIZED_ASSIGNMENT_STATES:
            return self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="hold",
                reason="assignment_not_authorized",
                metadata={
                    "assigned_global_track_id": assignment.assigned_global_track_id,
                    "assignment_version": assignment.assignment_version,
                    "authorization_state": assignment.authorization_state,
                    "gate_pass_count": 0,
                    "candidate_pair_logs": [],
                },
            )

        if assigned is None:
            return self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="reacquire",
                reason="assigned_global_track_not_available",
                metadata={
                    "assigned_global_track_id": assignment.assigned_global_track_id,
                    "assignment_version": assignment.assignment_version,
                    "available_global_track_ids": list(input_global_ids),
                    "gate_pass_count": 0,
                    "candidate_pair_logs": [],
                },
            )

        if assignment.require_version_match and assigned.track_version != assignment.assignment_version:
            return self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="hold",
                reason="assignment_version_mismatch",
                metadata={
                    "assigned_global_track_id": assignment.assigned_global_track_id,
                    "assignment_version": assignment.assignment_version,
                    "global_track_version": assigned.track_version,
                    "gate_pass_count": 0,
                    "candidate_pair_logs": [],
                },
            )

        projections = self.project_tracks_to_image([assigned], camera, timestamp=projection_time)
        projection = projections[assignment.assigned_global_track_id]
        if not projection.valid:
            return self._association(
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
                )
                | {"gate_pass_count": 0, "candidate_pair_logs": []},
            )

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
        )

        if not feasible_indices:
            self._assert_global_ids_unchanged(input_global_ids, global_list)
            return self._association(
                assignment,
                local_track_id=None,
                confidence=0.0,
                ambiguity=1.0,
                friend_state="none",
                decision="reacquire",
                reason="no_local_track_inside_projection_gate",
                metadata=decision_metadata,
            )

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
            return self._association(
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
                ),
            )

        ordered = sorted(feasible_indices, key=lambda index: row[index])
        best_index = ordered[0]
        best_local_id = cost_result.local_track_ids[best_index]
        best_breakdown = cost_result.breakdowns[(assignment.assigned_global_track_id, best_local_id)]
        best_cost = float(row[best_index])
        second_cost = float(row[ordered[1]]) if len(ordered) > 1 else float("inf")
        margin = second_cost - best_cost if isfinite(second_cost) else float("inf")
        confidence = self._confidence(best_breakdown, local_list[best_index])
        ambiguity = 0.0 if not isfinite(margin) else 1.0 / (1.0 + max(0.0, margin))

        nonverified_identity_overlap = best_breakdown.friend_conflict_state in {
            "spoof_suspected_overlap",
            "unverified_friend_overlap",
        }
        if nonverified_identity_overlap:
            decision = "ambiguous"
            reason = best_breakdown.friend_conflict_state
        elif best_cost > self.config.max_lock_cost:
            decision = "ambiguous"
            reason = "best_cost_exceeds_lock_threshold"
        elif isfinite(margin) and margin < self.config.min_lock_margin:
            decision = "ambiguous"
            reason = "insufficient_best_second_margin"
        elif local_list[best_index].mot_history_length < self.config.min_mot_history:
            decision = "ambiguous"
            reason = "mot_history_too_short"
        elif local_list[best_index].quality < self.config.min_lock_quality:
            decision = "ambiguous"
            reason = "local_track_quality_too_low"
        else:
            decision = "locked"
            reason = "unique_candidate_inside_gate"

        self._assert_global_ids_unchanged(input_global_ids, global_list)
        return self._association(
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
            ),
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
        if friend_state in {"spoof_suspected_overlap", "unverified_friend_overlap"}:
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

    def _projection_metadata(
        self,
        *,
        assignment: Assignment,
        projection: ProjectionResult,
        projection_time: float | None,
    ) -> dict:
        return {
            "assigned_global_track_id": assignment.assigned_global_track_id,
            "assignment_version": assignment.assignment_version,
            "resource_id": assignment.resource_id,
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

    def _decision_metadata(
        self,
        *,
        assignment: Assignment,
        projection: ProjectionResult,
        projection_time: float | None,
        cost_result: CostMatrixResult,
        feasible_indices: list[int],
        selected_local_track_id: str | None = None,
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
        metadata = self._projection_metadata(
            assignment=assignment,
            projection=projection,
            projection_time=projection_time,
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
                "duplicate_terminal_lock_risk": False,
            }
        )
        return metadata


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
