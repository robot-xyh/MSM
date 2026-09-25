"""Geometry-gated Hungarian association with explicit unmatched decisions."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
import math
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..common import AssociationRecord, LocalVisualTrackRecord, SourceCueRecord
from ..common.recognition import DEFAULT_RECOGNITION_EXTENT_PX
from .geometry import (
    CameraModel,
    ProjectedSourceCue,
    ProjectionError,
    ProjectionUncertainty,
    camera_for_observation,
    project_source_cue,
    projection_support_intersects_image,
)


@dataclass(frozen=True)
class AssociationConfig:
    recognition_extent_px: float = DEFAULT_RECOGNITION_EXTENT_PX
    mahalanobis_gate_d2: float = 9.210340371976184
    maximum_motion_residual_px_s: float = 80.0
    local_measurement_sigma_px: float = 1.5
    projection_noise_px: float = 1.0
    acceleration_sigma_mps2: float = 0.5
    dummy_cost: float = 12.0
    forbidden_cost: float = 1.0e6
    motion_cost_weight: float = 1.0
    switch_penalty: float = 4.0
    confirmation_window_frames: int = 3
    confirmation_required_frames: int = 2
    projection_support_sigma: float = 2.447746830680816
    projection_uncertainty_method: str = "numerical"
    coarse_hint_validation_d2: float = 9.210340371976184
    coarse_hint_bonus: float = 2.0

    def __post_init__(self) -> None:
        positive = (
            self.recognition_extent_px,
            self.mahalanobis_gate_d2,
            self.maximum_motion_residual_px_s,
            self.local_measurement_sigma_px,
            self.projection_noise_px,
            self.dummy_cost,
            self.forbidden_cost,
            self.projection_support_sigma,
            self.coarse_hint_validation_d2,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("association thresholds and costs must be positive")
        if not 1 <= self.confirmation_required_frames <= self.confirmation_window_frames:
            raise ValueError("confirmation count must fit within the confirmation window")
        if self.dummy_cost >= self.forbidden_cost:
            raise ValueError("dummy_cost must be lower than forbidden_cost")
        if self.coarse_hint_bonus < 0.0:
            raise ValueError("coarse_hint_bonus cannot be negative")
        if self.projection_uncertainty_method not in {"numerical", "linearized"}:
            raise ValueError(
                "projection_uncertainty_method must be numerical or linearized"
            )


@dataclass
class CandidateEvaluation:
    candidate_id: str
    source_index: int
    local_index: int
    source_track_id: str
    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    projected_center_px: tuple[float, float] | None
    projection_covariance_px2: tuple[tuple[float, float], tuple[float, float]] | None
    observed_center_px: tuple[float, float]
    residual_px: tuple[float, float] | None
    mahalanobis_d2: float | None
    prediction_age_s: float
    motion_residual_px_s: float | None
    baseline_cost: float
    assignment_cost: float
    geometry_passed: bool
    time_passed: bool
    motion_passed: bool
    recognition_passed: bool
    eligible: bool
    reject_reasons: tuple[str, ...]
    gnn_probability: float | None = None
    projection_mean_in_frame: bool = False
    projection_support_intersects_frame: bool = False
    coarse_hint_relation: bool = False
    coarse_hint_validated: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FrameAssociationResult:
    frame_index: int
    measurement_timestamp: float
    candidates: tuple[CandidateEvaluation, ...]
    decisions: tuple[AssociationRecord, ...]
    selected_pairs: tuple[tuple[str, str], ...]
    confirmed_pairs: tuple[tuple[str, str], ...]
    unregistered_local_track_ids: tuple[str, ...]
    coarse_hint_count: int = 0
    validated_coarse_hint_count: int = 0
    fallback_coarse_hint_count: int = 0


CandidateScorer = Callable[
    [Sequence[CandidateEvaluation], Sequence[SourceCueRecord], Sequence[LocalVisualTrackRecord]],
    Mapping[str, float],
]


class CenterHandoverAssociator:
    """Stateful center-source to camera-local association experiment."""

    def __init__(
        self,
        camera_models: Mapping[str, CameraModel],
        *,
        config: AssociationConfig | None = None,
        candidate_scorer: CandidateScorer | None = None,
        use_coarse_hints: bool = False,
        projection_cache: MutableMapping[tuple[object, ...], ProjectedSourceCue] | None = None,
    ) -> None:
        self.camera_models = dict(camera_models)
        if not self.camera_models:
            raise ValueError("at least one camera model is required")
        self.config = config or AssociationConfig()
        self.candidate_scorer = candidate_scorer
        self.use_coarse_hints = bool(use_coarse_hints)
        self._projection_cache = projection_cache if projection_cache is not None else {}
        self._frame_index = 0
        self._local_history: dict[tuple[str, str], tuple[float, np.ndarray]] = {}
        self._confirmation_history: dict[tuple[str, str], deque[bool]] = {}
        self._confirmed_source_to_local: dict[str, str] = {}

    def process_frame(
        self,
        source_cues: Sequence[SourceCueRecord],
        local_tracks: Sequence[LocalVisualTrackRecord],
    ) -> FrameAssociationResult:
        if not local_tracks:
            timestamp = max((cue.measurement_timestamp for cue in source_cues), default=0.0)
        else:
            timestamps = {round(float(track.measurement_timestamp), 9) for track in local_tracks}
            if len(timestamps) != 1:
                raise ValueError("one process_frame call must contain one measurement timestamp")
            timestamp = float(local_tracks[0].measurement_timestamp)

        local_velocities = self._local_pixel_velocities(local_tracks)
        candidates = self._evaluate_candidates(source_cues, local_tracks, local_velocities)
        if self.candidate_scorer is not None:
            probabilities = self.candidate_scorer(candidates, source_cues, local_tracks)
            for candidate in candidates:
                if not candidate.eligible:
                    candidate.gnn_probability = None
                    candidate.assignment_cost = self.config.forbidden_cost
                    continue
                probability = min(max(float(probabilities.get(candidate.candidate_id, 0.0)), 1.0e-6), 1.0 - 1.0e-6)
                candidate.gnn_probability = probability
                candidate.assignment_cost = candidate.baseline_cost - 2.0 * math.log(probability)

        hint_count = validated_hint_count = 0
        if self.use_coarse_hints:
            hint_count, validated_hint_count = self._apply_coarse_hint_prior(
                candidates,
                source_cues,
                local_tracks,
            )

        selected_indices, unmatched_source_indices, unmatched_local_indices = self._assign(
            len(source_cues), len(local_tracks), candidates
        )
        selected_pairs = {
            (source_cues[source_index].source_track_id, local_tracks[local_index].local_track_id)
            for source_index, local_index in selected_indices
        }
        confirmation_counts = self._update_confirmation(selected_pairs)
        candidate_lookup = {(item.source_index, item.local_index): item for item in candidates}
        decisions: list[AssociationRecord] = []
        confirmed_pairs: list[tuple[str, str]] = []

        for source_index, local_index in selected_indices:
            source = source_cues[source_index]
            local = local_tracks[local_index]
            pair = (source.source_track_id, local.local_track_id)
            confirmation_count = confirmation_counts[pair]
            confirmed = confirmation_count >= self.config.confirmation_required_frames
            state = "confirmed" if confirmed else "selected_pending"
            if confirmed:
                self._confirmed_source_to_local[source.source_track_id] = local.local_track_id
                confirmed_pairs.append(pair)
            candidate = candidate_lookup[(source_index, local_index)]
            decisions.append(
                AssociationRecord(
                    association_id=f"HND-F{self._frame_index:04d}-S{source_index:03d}",
                    association_type="center_source_to_terminal_local",
                    left_track_id=source.source_track_id,
                    right_track_id=local.local_track_id,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=max(source.arrival_timestamp, local.arrival_timestamp),
                    score=float(candidate.assignment_cost),
                    decision_state=state,
                    geometry_residual=candidate.mahalanobis_d2,
                    confirmation_count=confirmation_count,
                    metadata={
                        "camera_id": local.camera_id,
                        "association_backend": "gnn" if self.candidate_scorer else "geometry",
                    },
                )
            )

        candidate_sources = defaultdict(list)
        for candidate in candidates:
            candidate_sources[candidate.source_index].append(candidate)
        for source_index in unmatched_source_indices:
            source = source_cues[source_index]
            reasons = _aggregate_reject_reasons(candidate_sources[source_index])
            decisions.append(
                AssociationRecord(
                    association_id=f"HND-F{self._frame_index:04d}-D{source_index:03d}",
                    association_type="center_source_to_terminal_local",
                    left_track_id=source.source_track_id,
                    right_track_id=None,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=max(timestamp, source.arrival_timestamp),
                    score=self.config.dummy_cost,
                    decision_state="source_unmatched",
                    reject_reasons=reasons or ("assignment_dummy",),
                )
            )

        for local_index in unmatched_local_indices:
            local = local_tracks[local_index]
            decisions.append(
                AssociationRecord(
                    association_id=f"HND-F{self._frame_index:04d}-U{local_index:03d}",
                    association_type="terminal_local_unregistered",
                    left_track_id=local.local_track_id,
                    right_track_id=None,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=local.arrival_timestamp,
                    score=self.config.dummy_cost,
                    decision_state="unregistered_candidate",
                    reject_reasons=("no_selected_source_cue",),
                    metadata={"camera_id": local.camera_id},
                )
            )

        self._update_local_history(local_tracks)
        result = FrameAssociationResult(
            frame_index=self._frame_index,
            measurement_timestamp=timestamp,
            candidates=tuple(candidates),
            decisions=tuple(decisions),
            selected_pairs=tuple(sorted(selected_pairs)),
            confirmed_pairs=tuple(sorted(confirmed_pairs)),
            unregistered_local_track_ids=tuple(
                sorted(local_tracks[index].local_track_id for index in unmatched_local_indices)
            ),
            coarse_hint_count=hint_count,
            validated_coarse_hint_count=validated_hint_count,
            fallback_coarse_hint_count=hint_count - validated_hint_count,
        )
        self._frame_index += 1
        return result

    def _apply_coarse_hint_prior(
        self,
        candidates: Sequence[CandidateEvaluation],
        sources: Sequence[SourceCueRecord],
        locals_: Sequence[LocalVisualTrackRecord],
    ) -> tuple[int, int]:
        """Validate search cue IDs and use them only as a soft assignment prior.

        All candidate edges remain available to the Hungarian assignment. An
        absent, stale, geometrically inconsistent, or duplicate hint receives
        no bonus and therefore falls back to the same global N-to-N problem as
        the no-hint mode.
        """

        source_ids = {source.source_track_id for source in sources}
        hints: dict[int, str] = {}
        for local_index, local in enumerate(locals_):
            raw = local.metadata.get("coarse_source_track_id")
            if raw is None:
                continue
            hint = str(raw).strip()
            if hint:
                hints[local_index] = hint
        if not hints:
            return 0, 0

        hint_multiplicity: dict[str, int] = defaultdict(int)
        for hint in hints.values():
            hint_multiplicity[hint] += 1
        by_pair = {
            (candidate.source_track_id, candidate.local_index): candidate
            for candidate in candidates
        }
        validated = 0
        for local_index, hint in hints.items():
            candidate = by_pair.get((hint, local_index))
            if candidate is not None:
                candidate.coarse_hint_relation = True
            if (
                hint not in source_ids
                or hint_multiplicity[hint] != 1
                or candidate is None
                or not candidate.eligible
                or candidate.mahalanobis_d2 is None
                or candidate.mahalanobis_d2 > self.config.coarse_hint_validation_d2
            ):
                continue
            candidate.coarse_hint_validated = True
            candidate.assignment_cost = max(
                0.0,
                candidate.assignment_cost - self.config.coarse_hint_bonus,
            )
            validated += 1
        return len(hints), validated

    def _evaluate_candidates(
        self,
        sources: Sequence[SourceCueRecord],
        locals_: Sequence[LocalVisualTrackRecord],
        local_velocities: Mapping[tuple[str, str], np.ndarray | None],
    ) -> list[CandidateEvaluation]:
        candidates: list[CandidateEvaluation] = []
        camera_contexts: dict[
            int,
            tuple[CameraModel | None, ProjectionUncertainty | None],
        ] = {}
        for local_index, local in enumerate(locals_):
            base_camera = self.camera_models.get(local.camera_id)
            if base_camera is None:
                camera_contexts[local_index] = (None, None)
            else:
                camera_contexts[local_index] = _camera_and_uncertainty_for_local(
                    base_camera,
                    local,
                )
        for source_index, source in enumerate(sources):
            for local_index, local in enumerate(locals_):
                candidate_id = f"F{self._frame_index:04d}-S{source_index:03d}-L{local_index:03d}"
                reasons: list[str] = []
                recognized = bool(local.recognized) and (
                    float(local.recognition_extent_px) >= self.config.recognition_extent_px
                )
                if not recognized:
                    reasons.append("bbox_below_recognition_threshold")
                age = float(local.measurement_timestamp) - float(source.measurement_timestamp)
                available = float(local.arrival_timestamp) >= float(source.arrival_timestamp)
                valid = (
                    age >= -1.0e-9
                    and float(local.measurement_timestamp) <= float(source.valid_until)
                )
                time_passed = available and valid
                if not available:
                    reasons.append("source_not_arrived")
                if not valid:
                    reasons.append("source_time_invalid")

                projected_center: tuple[float, float] | None = None
                projection_covariance: tuple[tuple[float, float], tuple[float, float]] | None = None
                residual_tuple: tuple[float, float] | None = None
                mahalanobis_d2: float | None = None
                motion_residual: float | None = None
                geometry_passed = False
                motion_passed = True
                projection_mean_in_frame = False
                projection_support_intersects_frame = False
                baseline_cost = self.config.forbidden_cost
                observed_camera, projection_uncertainty = camera_contexts[local_index]
                if observed_camera is None:
                    reasons.append("camera_model_missing")
                elif age >= -1.0e-9:
                    try:
                        cache_key = (
                            source.source_track_id,
                            local.camera_id,
                            float(local.measurement_timestamp),
                            self.config.acceleration_sigma_mps2,
                            self.config.projection_noise_px,
                            self.config.projection_uncertainty_method,
                        )
                        projection = self._projection_cache.get(cache_key)
                        if projection is None:
                            projection = project_source_cue(
                                source,
                                observed_camera,
                                local.measurement_timestamp,
                                acceleration_sigma_mps2=self.config.acceleration_sigma_mps2,
                                projection_noise_px=self.config.projection_noise_px,
                                uncertainty=projection_uncertainty,
                                require_in_frame=False,
                                uncertainty_method=self.config.projection_uncertainty_method,
                            )
                            self._projection_cache[cache_key] = projection
                        projected_center = projection.center_px
                        prediction_covariance = np.asarray(projection.covariance_px2, dtype=float)
                        projection_mean_in_frame = _point_in_image(
                            projected_center,
                            observed_camera,
                        )
                        projection_support_intersects_frame = (
                            projection_mean_in_frame
                            or projection_support_intersects_image(
                                projected_center,
                                prediction_covariance,
                                observed_camera.intrinsics,
                                sigma_scale=self.config.projection_support_sigma,
                            )
                        )
                        if not projection_support_intersects_frame:
                            reasons.append("projection_support_outside_image")
                        local_covariance = _local_covariance(local, self.config.local_measurement_sigma_px)
                        innovation_covariance = prediction_covariance + local_covariance
                        residual = np.asarray(local.center_px, dtype=float) - np.asarray(projected_center, dtype=float)
                        mahalanobis_d2 = float(residual @ np.linalg.pinv(innovation_covariance) @ residual)
                        projection_covariance = tuple(
                            tuple(float(value) for value in row) for row in prediction_covariance
                        )  # type: ignore[assignment]
                        residual_tuple = tuple(float(value) for value in residual)
                        geometry_passed = (
                            projection_support_intersects_frame
                            and mahalanobis_d2 <= self.config.mahalanobis_gate_d2
                        )
                        if not geometry_passed:
                            reasons.append("mahalanobis_gate_rejected")
                        local_velocity = local_velocities[(local.camera_id, local.local_track_id)]
                        if local_velocity is not None:
                            motion_residual = float(
                                np.linalg.norm(local_velocity - np.asarray(projection.velocity_px_s, dtype=float))
                            )
                            motion_passed = motion_residual <= self.config.maximum_motion_residual_px_s
                            if not motion_passed:
                                reasons.append("motion_continuity_rejected")
                        motion_cost = (
                            0.0
                            if motion_residual is None
                            else self.config.motion_cost_weight
                            * (motion_residual / self.config.maximum_motion_residual_px_s) ** 2
                        )
                        baseline_cost = mahalanobis_d2 + motion_cost
                        confirmed_local = self._confirmed_source_to_local.get(source.source_track_id)
                        if confirmed_local is not None and confirmed_local != local.local_track_id:
                            baseline_cost += self.config.switch_penalty
                    except ProjectionError:
                        reasons.append("projection_outside_image")

                eligible = recognized and time_passed and geometry_passed and motion_passed
                candidates.append(
                    CandidateEvaluation(
                        candidate_id=candidate_id,
                        source_index=source_index,
                        local_index=local_index,
                        source_track_id=source.source_track_id,
                        camera_id=local.camera_id,
                        local_track_id=local.local_track_id,
                        measurement_timestamp=float(local.measurement_timestamp),
                        projected_center_px=projected_center,
                        projection_covariance_px2=projection_covariance,
                        observed_center_px=tuple(float(value) for value in local.center_px),
                        residual_px=residual_tuple,
                        mahalanobis_d2=mahalanobis_d2,
                        prediction_age_s=age,
                        motion_residual_px_s=motion_residual,
                        baseline_cost=baseline_cost,
                        assignment_cost=baseline_cost if eligible else self.config.forbidden_cost,
                        geometry_passed=geometry_passed,
                        time_passed=time_passed,
                        motion_passed=motion_passed,
                        recognition_passed=recognized,
                        eligible=eligible,
                        reject_reasons=tuple(dict.fromkeys(reasons)),
                        projection_mean_in_frame=projection_mean_in_frame,
                        projection_support_intersects_frame=projection_support_intersects_frame,
                    )
                )
        return candidates

    def _assign(
        self,
        source_count: int,
        local_count: int,
        candidates: Iterable[CandidateEvaluation],
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        if source_count == 0:
            return [], [], list(range(local_count))
        matrix = np.full(
            (source_count, local_count + source_count),
            self.config.forbidden_cost,
            dtype=float,
        )
        for candidate in candidates:
            if candidate.eligible:
                matrix[candidate.source_index, candidate.local_index] = min(
                    matrix[candidate.source_index, candidate.local_index],
                    candidate.assignment_cost,
                )
        for source_index in range(source_count):
            matrix[source_index, local_count + source_index] = self.config.dummy_cost
        row_indices, column_indices = linear_sum_assignment(matrix)
        selected: list[tuple[int, int]] = []
        unmatched_sources: list[int] = []
        selected_locals: set[int] = set()
        for row, column in zip(row_indices, column_indices, strict=True):
            if column < local_count and matrix[row, column] < self.config.dummy_cost:
                selected.append((int(row), int(column)))
                selected_locals.add(int(column))
            else:
                unmatched_sources.append(int(row))
        unmatched_locals = [index for index in range(local_count) if index not in selected_locals]
        return selected, unmatched_sources, unmatched_locals

    def _local_pixel_velocities(
        self, local_tracks: Sequence[LocalVisualTrackRecord]
    ) -> dict[tuple[str, str], np.ndarray | None]:
        velocities: dict[tuple[str, str], np.ndarray | None] = {}
        for local in local_tracks:
            key = (local.camera_id, local.local_track_id)
            previous = self._local_history.get(key)
            velocity: np.ndarray | None = None
            if previous is not None:
                previous_time, previous_center = previous
                dt = float(local.measurement_timestamp) - previous_time
                if dt > 1.0e-9:
                    velocity = (np.asarray(local.center_px, dtype=float) - previous_center) / dt
            velocities[key] = velocity
        return velocities

    def _update_local_history(self, local_tracks: Sequence[LocalVisualTrackRecord]) -> None:
        for local in local_tracks:
            self._local_history[(local.camera_id, local.local_track_id)] = (
                float(local.measurement_timestamp),
                np.asarray(local.center_px, dtype=float),
            )

    def _update_confirmation(self, selected_pairs: set[tuple[str, str]]) -> dict[tuple[str, str], int]:
        all_pairs = set(self._confirmation_history) | selected_pairs
        counts: dict[tuple[str, str], int] = {}
        for pair in all_pairs:
            history = self._confirmation_history.setdefault(
                pair, deque(maxlen=self.config.confirmation_window_frames)
            )
            history.append(pair in selected_pairs)
            counts[pair] = int(sum(history))
        return counts


def _local_covariance(local: LocalVisualTrackRecord, fallback_sigma_px: float) -> np.ndarray:
    raw = local.metadata.get("center_covariance_px2")
    if raw is None:
        return np.eye(2, dtype=float) * float(fallback_sigma_px) ** 2
    covariance = np.asarray(raw, dtype=float)
    if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
        raise ValueError("center_covariance_px2 must be a finite 2 by 2 matrix")
    return (covariance + covariance.T) / 2.0


def _camera_and_uncertainty_for_local(
    base: CameraModel,
    local: LocalVisualTrackRecord,
) -> tuple[CameraModel, ProjectionUncertainty | None]:
    pose_raw = local.metadata.get("reported_camera_pose")
    uncertainty_raw = local.metadata.get("projection_uncertainty")
    if not isinstance(pose_raw, Mapping):
        return (
            camera_for_observation(
                base,
                local.ray_origin_ned_m,
                local.camera_yaw_pitch_roll_deg,
            ),
            None,
        )
    camera = CameraModel(
        camera_id=base.camera_id,
        intrinsics=base.intrinsics,
        body_position_ned_m=_vector3(pose_raw, "body_position_ned_m"),
        body_yaw_pitch_roll_deg=_vector3(pose_raw, "body_yaw_pitch_roll_deg"),
        gimbal_yaw_pitch_roll_deg=_vector3(
            pose_raw,
            "gimbal_yaw_pitch_roll_deg",
            default=(0.0, 0.0, 0.0),
        ),
        camera_yaw_pitch_roll_gimbal_deg=base.camera_yaw_pitch_roll_gimbal_deg,
        gimbal_pivot_offset_body_m=base.gimbal_pivot_offset_body_m,
        camera_offset_gimbal_m=base.camera_offset_gimbal_m,
        camera_offset_body_m=base.camera_offset_body_m,
        pose_representation="decomposed_mount",
    )
    if uncertainty_raw is None:
        return camera, None
    if not isinstance(uncertainty_raw, Mapping):
        raise ValueError("projection_uncertainty metadata must be a mapping")
    uncertainty = ProjectionUncertainty(
        navigation_position_covariance_m2=_matrix_tuple(
            uncertainty_raw.get("navigation_position_covariance_m2"),
            size=3,
        ),
        body_attitude_covariance_rad2=_matrix_tuple(
            uncertainty_raw.get("body_attitude_covariance_rad2"),
            size=3,
        ),
        gimbal_angle_covariance_rad2=_matrix_tuple(
            uncertainty_raw.get("gimbal_angle_covariance_rad2"),
            size=3,
        ),
        pixel_center_covariance_px2=_matrix_tuple(
            uncertainty_raw.get("pixel_center_covariance_px2"),
            size=2,
        ),
    )
    return camera, uncertainty


def _vector3(
    value: Mapping[str, object],
    key: str,
    *,
    default: tuple[float, float, float] | None = None,
) -> tuple[float, float, float]:
    raw = value.get(key, default)
    if raw is None:
        raise ValueError(f"reported camera pose is missing {key}")
    result = tuple(float(item) for item in raw)  # type: ignore[arg-type]
    if len(result) != 3 or not np.all(np.isfinite(result)):
        raise ValueError(f"reported camera pose {key} must contain three finite values")
    return result  # type: ignore[return-value]


def _matrix_tuple(raw: object, *, size: int) -> tuple[tuple[float, ...], ...]:
    if raw is None:
        return tuple(tuple(0.0 for _ in range(size)) for _ in range(size))
    matrix = np.asarray(raw, dtype=float)
    if matrix.shape != (size, size) or not np.all(np.isfinite(matrix)):
        raise ValueError(f"uncertainty covariance must be {size} by {size}")
    return tuple(tuple(float(item) for item in row) for row in matrix)


def _point_in_image(center_px: Sequence[float], camera: CameraModel) -> bool:
    u, v = (float(value) for value in center_px)
    return bool(
        0.0 <= u < camera.intrinsics.width_px
        and 0.0 <= v < camera.intrinsics.height_px
    )


def _aggregate_reject_reasons(candidates: Sequence[CandidateEvaluation]) -> tuple[str, ...]:
    if any(candidate.eligible for candidate in candidates):
        return ("assignment_dummy",)
    reasons: list[str] = []
    for candidate in candidates:
        reasons.extend(candidate.reject_reasons)
    return tuple(dict.fromkeys(reasons))
