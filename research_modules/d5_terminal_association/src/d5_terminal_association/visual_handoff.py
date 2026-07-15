"""Advisory visual-PNG handoff signals for D7/main consumers.

D5 does not choose a guidance law.  This module only annotates an existing
terminal association with conservative evidence that D7/main may use when
deciding whether to try visual terminal PNG/LOS guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import inf
from typing import Iterable

import numpy as np

from .models import CameraModel, LocalVisualTrack, TerminalAssociation


@dataclass(frozen=True)
class VisualPngHandoffConfig:
    """Configurable gates for advisory visual terminal handoff.

    The default ranges are tuned for the current AirSim Blocks large-actor
    stress baseline. They are not universal constants and should be changed
    when target size, camera FOV, resolution, detector latency, or interceptor
    dynamics change.
    """

    far_prepare_range_m: tuple[float, float] = (30.0, 50.0)
    middle_handoff_range_m: tuple[float, float] = (15.0, 30.0)
    near_priority_range_m: tuple[float, float] = (5.0, 15.0)
    min_stable_frames: int = 4
    max_bbox_area_cv: float = 0.30
    min_bbox_area_ratio: float = 0.0008
    max_detection_latency_s: float = 0.35
    max_measurement_age_s: float = 0.35
    require_los_rate: bool = True
    max_los_rate_px_s: float | None = None
    min_time_to_go_s: float = 0.60
    min_d7_maneuver_margin: float = 0.0
    stable_confidence: float = 0.60
    max_ambiguity: float = 0.50

    @property
    def handoff_candidate_range_m(self) -> tuple[float, float]:
        """Default direct handoff range, exclusive of far pre-locking."""

        return (self.near_priority_range_m[0], self.middle_handoff_range_m[1])


@dataclass(frozen=True)
class BBoxStability:
    """Area-ratio stability summary for one local or assigned track window."""

    visible_frame_count: int
    required_frame_count: int
    bbox_area_ratio: float
    mean_bbox_area_ratio: float
    bbox_area_cv: float
    bbox_stability_score: float
    stable: bool
    reason: str


def annotate_visual_png_handoff(
    association: TerminalAssociation,
    *,
    local_track_history: Iterable[LocalVisualTrack],
    image_size: tuple[int, int],
    range_to_assigned_track_m: float | None = None,
    closing_speed_mps: float | None = None,
    detection_latency_s: float | None = None,
    measurement_age_s: float | None = None,
    los_rate_px_s: Iterable[float] | np.ndarray | None = None,
    current_time: float | None = None,
    d7_maneuver_margin: float | None = None,
    assignment_consistent: bool = True,
    current_assigned_global_track_id: str | None = None,
    duplicate_terminal_lock_risk: bool = False,
    config: VisualPngHandoffConfig | None = None,
) -> TerminalAssociation:
    """Return `association` with advisory handoff metadata merged in.

    The returned association keeps the original `assigned_global_track_id` and
    `decision_state`.  A positive recommendation means only that D5 evidence is
    sufficient for D7/main to *try* visual terminal gating; D7 must still check
    camera, LOS, maneuver, and guidance constraints.
    """

    cfg = config or VisualPngHandoffConfig()
    history = tuple(local_track_history)
    if current_assigned_global_track_id is not None:
        assignment_consistent = (
            assignment_consistent
            and current_assigned_global_track_id == association.assigned_global_track_id
        )
    scoped_history = history if association.local_track_id is not None else ()
    association_measurement_age_s = _association_measurement_age_s(
        association,
        current_time=current_time,
    )
    measurement_age_s = _resolved_measurement_age_s(
        scoped_history,
        association.local_track_id,
        current_time=current_time,
        measurement_age_s=(
            measurement_age_s
            if measurement_age_s is not None
            else association_measurement_age_s
        ),
        detection_latency_s=detection_latency_s,
    )
    los_rate_tuple = _resolved_los_rate_px_s(
        scoped_history,
        association.local_track_id,
        los_rate_px_s,
    )
    los_rate_norm = _los_rate_norm(los_rate_tuple)
    handoff_blockers = _handoff_blockers(
        association=association,
        assignment_consistent=assignment_consistent,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
        measurement_age_s=measurement_age_s,
        los_rate_norm_px_s=los_rate_norm,
        config=cfg,
    )
    supplied_stability = bbox_area_stability(
        scoped_history,
        image_size=image_size,
        local_track_id=association.local_track_id,
        config=cfg,
    )
    audited_stability = _audited_bbox_stability(association, config=cfg)
    stability = (
        audited_stability
        if audited_stability is not None
        and (
            len(scoped_history) <= 1
            or audited_stability.visible_frame_count
            >= supplied_stability.visible_frame_count
        )
        else supplied_stability
    )
    bbox_history_reset_reason = association.metadata.get("bbox_history_reset_reason")
    if duplicate_terminal_lock_risk:
        stability = replace(
            stability,
            visible_frame_count=0,
            bbox_area_cv=inf,
            bbox_stability_score=0.0,
            stable=False,
            reason="duplicate_terminal_lock_risk",
        )
        bbox_history_reset_reason = "duplicate_terminal_lock_risk"
    range_band = range_band_for_handoff(range_to_assigned_track_m, cfg)
    time_to_go_s = _time_to_go(range_to_assigned_track_m, closing_speed_mps)

    timing_ok = _timing_ok(
        time_to_go_s=time_to_go_s,
        detection_latency_s=detection_latency_s,
        d7_maneuver_margin=d7_maneuver_margin,
        config=cfg,
    )

    handoff_recommended = False
    prelock_recommended = False
    reason = handoff_blockers[0] if handoff_blockers else stability.reason

    if not handoff_blockers and stability.stable:
        if range_band == "far_prepare":
            prelock_recommended = True
            reason = "far_range_bbox_area_stable_prepare"
        elif range_band == "middle_handoff":
            handoff_recommended = timing_ok
            prelock_recommended = not timing_ok
            reason = "bbox_area_stable_middle_range" if timing_ok else "middle_range_timing_or_maneuver_not_ready"
        elif range_band == "near_priority":
            handoff_recommended = timing_ok
            prelock_recommended = not timing_ok
            reason = "near_range_bbox_area_stable" if timing_ok else "near_range_timing_or_maneuver_not_ready"
        elif range_band == "inside_min_range":
            handoff_recommended = timing_ok
            reason = "inside_min_range_stable_evaluate_immediately" if timing_ok else "inside_min_range_timing_not_ready"
        else:
            reason = "range_outside_visual_handoff_window"
    elif not handoff_blockers and range_band == "near_priority":
        reason = "near_range_bbox_unstable_keep_radar_pn"

    live_funnel = _handoff_live_visual_funnel(
        association,
        handoff_recommended=handoff_recommended,
        prelock_recommended=prelock_recommended,
        handoff_reason=reason,
        handoff_blockers=handoff_blockers,
        range_band=range_band,
        range_to_assigned_track_m=range_to_assigned_track_m,
        closing_speed_mps=closing_speed_mps,
        measurement_age_s=measurement_age_s,
        bbox_stable=stability.stable,
        bbox_area_ratio=stability.bbox_area_ratio,
        timing_gate_pass=timing_ok,
    )
    metadata = {
        **association.metadata,
        "handoff_recommended": handoff_recommended,
        "visual_png_handoff_recommended": handoff_recommended,
        "visual_png_prelock_recommended": prelock_recommended,
        "handoff_reason": reason,
        "visual_png_gate_pass": handoff_recommended,
        "visual_png_handoff_blockers": list(handoff_blockers),
        "recommended_range_band": range_band,
        "bbox_stability_score": stability.bbox_stability_score,
        "bbox_area_stability_score": stability.bbox_stability_score,
        "bbox_area_cv": stability.bbox_area_cv,
        "bbox_area_ratio": stability.bbox_area_ratio,
        "bbox_area_ratio_mean": stability.mean_bbox_area_ratio,
        "bbox_stable": stability.stable,
        "visible_frame_count": stability.visible_frame_count,
        "required_visible_frame_count": stability.required_frame_count,
        "bbox_history_length": stability.visible_frame_count,
        "bbox_history_measured_length": stability.visible_frame_count,
        "bbox_history_predicted_length": 0,
        "bbox_history_reset_reason": bbox_history_reset_reason,
        "bbox_history_evidence_source": association.metadata.get(
            "bbox_history_evidence_source",
            _history_evidence_source(scoped_history),
        ),
        "range_to_assigned_track_m": range_to_assigned_track_m,
        "handoff_candidate_range_m": cfg.handoff_candidate_range_m,
        "range_band_edges_m": {
            "far_prepare": cfg.far_prepare_range_m,
            "middle_handoff": cfg.middle_handoff_range_m,
            "near_priority": cfg.near_priority_range_m,
        },
        "closing_speed_mps": closing_speed_mps,
        "time_to_go_s": time_to_go_s,
        "detection_latency_s": detection_latency_s,
        "measurement_age_s": measurement_age_s,
        "measurement_age_ok": _measurement_age_ok(measurement_age_s, cfg),
        "los_rate_px_s": list(los_rate_tuple) if los_rate_tuple is not None else None,
        "los_rate_norm_px_s": los_rate_norm,
        "los_rate_available": los_rate_tuple is not None,
        "los_rate_ok": _los_rate_ok(los_rate_norm, cfg),
        "bbox_gate_pass": stability.stable,
        "decision_locked_gate_pass": association.decision_state == "locked",
        "assignment_consistency_gate_pass": assignment_consistent,
        "friend_conflict_gate_pass": association.friend_conflict_state == "none",
        "duplicate_risk_gate_pass": not duplicate_terminal_lock_risk,
        "timing_gate_pass": timing_ok,
        "d7_maneuver_margin": d7_maneuver_margin,
        "current_assigned_global_track_id": current_assigned_global_track_id,
        "assignment_consistent": assignment_consistent,
        "duplicate_terminal_lock_risk": duplicate_terminal_lock_risk,
        "d5_live_visual_funnel": live_funnel,
    }
    return replace(association, measurement_age_s=measurement_age_s, metadata=metadata)


def bbox_area_stability(
    local_track_history: Iterable[LocalVisualTrack],
    *,
    image_size: tuple[int, int],
    local_track_id: str | None = None,
    config: VisualPngHandoffConfig | None = None,
) -> BBoxStability:
    """Compute coefficient-of-variation stability for bbox area ratio."""

    cfg = config or VisualPngHandoffConfig()
    width, height = image_size
    image_area = max(float(width * height), 1.0)
    tracks = [
        track
        for track in local_track_history
        if track.bbox is not None and (local_track_id is None or track.local_track_id == local_track_id)
    ]
    ratios = np.asarray([_bbox_area(track.bbox) / image_area for track in tracks], dtype=float)
    visible = int(ratios.size)
    if visible < cfg.min_stable_frames:
        return BBoxStability(
            visible_frame_count=visible,
            required_frame_count=cfg.min_stable_frames,
            bbox_area_ratio=float(ratios[-1]) if visible else 0.0,
            mean_bbox_area_ratio=float(np.mean(ratios)) if visible else 0.0,
            bbox_area_cv=inf,
            bbox_stability_score=0.0,
            stable=False,
            reason="insufficient_visible_frames",
        )
    mean = float(np.mean(ratios))
    current = float(ratios[-1])
    if mean <= 0.0:
        cv = inf
    else:
        cv = float(np.std(ratios) / mean)
    score = float(np.clip(1.0 - cv / max(cfg.max_bbox_area_cv, 1e-9), 0.0, 1.0))
    stable = cv <= cfg.max_bbox_area_cv and current >= cfg.min_bbox_area_ratio
    reason = "bbox_area_stable" if stable else "bbox_area_unstable_or_too_small"
    return BBoxStability(
        visible_frame_count=visible,
        required_frame_count=cfg.min_stable_frames,
        bbox_area_ratio=current,
        mean_bbox_area_ratio=mean,
        bbox_area_cv=cv,
        bbox_stability_score=score,
        stable=stable,
        reason=reason,
    )


def _audited_bbox_stability(
    association: TerminalAssociation,
    *,
    config: VisualPngHandoffConfig,
) -> BBoxStability | None:
    metadata = association.metadata
    if "bbox_history_length" not in metadata:
        return None
    raw_ratios = metadata.get("bbox_history_area_ratios")
    ratios: tuple[float, ...] = ()
    if isinstance(raw_ratios, (list, tuple)):
        ratios = tuple(
            float(value)
            for value in raw_ratios
            if value is not None and np.isfinite(float(value)) and float(value) >= 0.0
        )
    if ratios:
        return _bbox_stability_from_area_ratios(ratios, config=config)

    visible = max(0, int(metadata.get("bbox_history_length", 0) or 0))
    raw_cv = metadata.get("bbox_area_cv")
    cv = float(raw_cv) if raw_cv is not None and np.isfinite(float(raw_cv)) else inf
    stable = bool(
        metadata.get("bbox_history_contract_complete", True)
        and metadata.get("bbox_stable", False)
        and visible >= config.min_stable_frames
    )
    return BBoxStability(
        visible_frame_count=visible,
        required_frame_count=config.min_stable_frames,
        bbox_area_ratio=float(metadata.get("bbox_area_ratio", 0.0) or 0.0),
        mean_bbox_area_ratio=float(metadata.get("bbox_area_ratio_mean", 0.0) or 0.0),
        bbox_area_cv=cv,
        bbox_stability_score=float(metadata.get("bbox_stability_score", 0.0) or 0.0),
        stable=stable,
        reason=str(metadata.get("bbox_history_reason") or "bbox_history_not_eligible"),
    )


def _bbox_stability_from_area_ratios(
    ratios: tuple[float, ...],
    *,
    config: VisualPngHandoffConfig,
) -> BBoxStability:
    visible = len(ratios)
    current = float(ratios[-1]) if ratios else 0.0
    mean = float(np.mean(ratios)) if ratios else 0.0
    if visible < config.min_stable_frames or mean <= 0.0:
        return BBoxStability(
            visible_frame_count=visible,
            required_frame_count=config.min_stable_frames,
            bbox_area_ratio=current,
            mean_bbox_area_ratio=mean,
            bbox_area_cv=inf,
            bbox_stability_score=0.0,
            stable=False,
            reason="insufficient_visible_frames",
        )
    cv = float(np.std(np.asarray(ratios, dtype=float)) / mean)
    score = float(np.clip(1.0 - cv / max(config.max_bbox_area_cv, 1e-9), 0.0, 1.0))
    stable = bool(cv <= config.max_bbox_area_cv and current >= config.min_bbox_area_ratio)
    return BBoxStability(
        visible_frame_count=visible,
        required_frame_count=config.min_stable_frames,
        bbox_area_ratio=current,
        mean_bbox_area_ratio=mean,
        bbox_area_cv=cv,
        bbox_stability_score=score,
        stable=stable,
        reason="bbox_area_stable" if stable else "bbox_area_unstable_or_too_small",
    )


def _history_evidence_source(history: tuple[LocalVisualTrack, ...]) -> str:
    if not history:
        return "lost"
    states = tuple(dict.fromkeys(track.local_track_state for track in history))
    return states[0] if len(states) == 1 else "mixed"


def _handoff_live_visual_funnel(
    association: TerminalAssociation,
    *,
    handoff_recommended: bool,
    prelock_recommended: bool,
    handoff_reason: str,
    handoff_blockers: tuple[str, ...] | list[str],
    range_band: str,
    range_to_assigned_track_m: float | None,
    closing_speed_mps: float | None,
    measurement_age_s: float | None,
    bbox_stable: bool,
    bbox_area_ratio: float,
    timing_gate_pass: bool,
) -> dict[str, object]:
    diagnostic = dict(association.metadata.get("d5_live_visual_funnel", {}))
    local_visual_evidence = dict(
        association.metadata.get("local_visual_evidence") or {}
    )
    if not diagnostic:
        diagnostic = {
            "schema_version": "d5_live_visual_funnel_v1",
            "resource_id": association.resource_id,
            "assigned_global_track_id": association.assigned_global_track_id,
            "plan_id": association.plan_id,
            "plan_version": association.plan_version,
            "local_track_id": association.local_track_id,
            "local_track_state": association.local_track_state,
            "measurement_timestamp": association.measurement_timestamp,
            "arrival_timestamp": association.arrival_timestamp,
            "detection_source": association.detection_source,
            "first_failure_stage": "association",
            "first_failure_reason": association.reason,
            "failure_domain": "d5_association",
            "truth_identity_used": False,
            "global_track_id_policy": "existing_assigned_global_track_id_only",
        }

    previous_stage = str(diagnostic.get("first_failure_stage") or "")
    if previous_stage == "handoff_evaluation":
        if handoff_recommended:
            first_failure_stage = "complete"
            first_failure_reason = "d5_visual_handoff_evidence_ready"
            failure_domain = "none"
        else:
            first_failure_stage = "handoff_gate"
            first_failure_reason = handoff_reason
            failure_domain = "d5_handoff_gate"
    else:
        first_failure_stage = previous_stage or "association"
        first_failure_reason = str(
            diagnostic.get("first_failure_reason") or association.reason
        )
        failure_domain = str(
            diagnostic.get("failure_domain") or "d5_association"
        )

    own_camera_measured_bbox_available = bool(
        diagnostic.get("own_camera_measured_bbox_available", False)
    )
    execution_lock_allowed = bool(
        diagnostic.get("execution_lock_allowed", False)
    )
    d7_handoff_input_ready = bool(
        handoff_recommended
        and execution_lock_allowed
        and own_camera_measured_bbox_available
    )
    if handoff_recommended and not d7_handoff_input_ready:
        first_failure_stage = "handoff_contract"
        first_failure_reason = "own_camera_executable_bbox_contract_incomplete"
        failure_domain = "d5_handoff_contract"

    diagnostic.update(
        {
            "bbox_stable": bool(bbox_stable),
            "bbox_area_ratio": float(bbox_area_ratio),
            "handoff_evaluated": True,
            "handoff_recommended": bool(handoff_recommended),
            "prelock_recommended": bool(prelock_recommended),
            "handoff_reason": handoff_reason,
            "handoff_blockers": list(handoff_blockers),
            "range_band": range_band,
            "range_to_assigned_track_m": range_to_assigned_track_m,
            "closing_speed_mps": closing_speed_mps,
            "measurement_age_s": measurement_age_s,
            "timing_gate_pass": bool(timing_gate_pass),
            "d7_handoff_input_ready": d7_handoff_input_ready,
            "d7_handoff_input": {
                "assigned_global_track_id": association.assigned_global_track_id,
                "local_track_id": association.local_track_id,
                "local_track_state": association.local_track_state,
                "camera_id": local_visual_evidence.get("camera_id"),
                "resource_id": association.resource_id,
                "stream_id": local_visual_evidence.get("stream_id"),
                "detector_backend": local_visual_evidence.get(
                    "detector_backend"
                ),
                "tracker_backend": local_visual_evidence.get(
                    "tracker_backend"
                ),
                "image_size": local_visual_evidence.get("image_size"),
                "center_px": local_visual_evidence.get("center_px"),
                "bbox_xyxy": local_visual_evidence.get("bbox_xyxy"),
                "detection_source": association.detection_source,
                "decision_state": association.decision_state,
                "association_confidence": association.association_confidence,
                "measurement_timestamp": association.measurement_timestamp,
                "arrival_timestamp": association.arrival_timestamp,
                "measurement_age_s": measurement_age_s,
                "bbox_area_ratio": float(bbox_area_ratio),
                "bbox_stable": bool(bbox_stable),
                "range_to_assigned_track_m": range_to_assigned_track_m,
                "closing_speed_mps": closing_speed_mps,
                "friend_conflict_state": association.friend_conflict_state,
                "duplicate_terminal_lock_risk": (
                    association.duplicate_terminal_lock_risk
                ),
                "plan_id": association.plan_id,
                "plan_version": association.plan_version,
                "terminal_authorization_scope": (
                    association.terminal_authorization_scope
                ),
                "local_visual_scope_consistent": diagnostic.get(
                    "local_visual_scope_consistent", False
                ),
                "local_visual_scope_evidence_complete": diagnostic.get(
                    "local_visual_scope_evidence_complete", False
                ),
                "measured_detection_available": diagnostic.get(
                    "measured_detection_available", False
                ),
                "measured_bbox_available": diagnostic.get(
                    "measured_bbox_available", False
                ),
                "own_camera_measured_bbox_available": (
                    own_camera_measured_bbox_available
                ),
                "measured_lock_streak_count": diagnostic.get(
                    "measured_lock_streak_count", 0
                ),
                "measured_lock_required_frames": diagnostic.get(
                    "measured_lock_required_frames", 0
                ),
                "measured_stable_lock": diagnostic.get(
                    "measured_stable_lock", False
                ),
                "bbox_history_length": diagnostic.get(
                    "bbox_history_length", 0
                ),
                "bbox_stable": bool(bbox_stable),
                "association_lock_only": diagnostic.get(
                    "association_lock_only", False
                ),
                "execution_lock_allowed": execution_lock_allowed,
            },
            "first_failure_stage": first_failure_stage,
            "first_failure_reason": first_failure_reason,
            "failure_domain": failure_domain,
        }
    )
    return diagnostic


def range_band_for_handoff(
    range_to_assigned_track_m: float | None,
    config: VisualPngHandoffConfig | None = None,
) -> str:
    """Classify current range into configurable visual-handoff bands."""

    cfg = config or VisualPngHandoffConfig()
    if range_to_assigned_track_m is None or not np.isfinite(range_to_assigned_track_m):
        return "range_unknown"
    distance = float(range_to_assigned_track_m)
    near_min, near_max = cfg.near_priority_range_m
    mid_min, mid_max = cfg.middle_handoff_range_m
    far_min, far_max = cfg.far_prepare_range_m
    if distance < near_min:
        return "inside_min_range"
    if near_min <= distance <= near_max:
        return "near_priority"
    if mid_min < distance <= mid_max:
        return "middle_handoff"
    if far_min < distance <= far_max:
        return "far_prepare"
    return "outside_visual_window"


def expected_bbox_area_ratio(
    *,
    range_m: float,
    target_size_m: tuple[float, float],
    camera: CameraModel,
) -> float:
    """Approximate expected bbox area ratio from target size and camera intrinsics."""

    if range_m <= 0.0:
        return 1.0
    width_m, height_m = target_size_m
    image_width, image_height = camera.image_size
    fx = float(camera.K[0, 0])
    fy = float(camera.K[1, 1])
    width_px = fx * float(width_m) / float(range_m)
    height_px = fy * float(height_m) / float(range_m)
    return float(max(width_px * height_px, 0.0) / max(float(image_width * image_height), 1.0))


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))


def _time_to_go(
    range_to_assigned_track_m: float | None,
    closing_speed_mps: float | None,
) -> float | None:
    if (
        range_to_assigned_track_m is None
        or closing_speed_mps is None
        or not np.isfinite(range_to_assigned_track_m)
        or not np.isfinite(closing_speed_mps)
        or closing_speed_mps <= 0.0
    ):
        return None
    return float(range_to_assigned_track_m) / float(closing_speed_mps)


def _handoff_blockers(
    *,
    association: TerminalAssociation,
    assignment_consistent: bool,
    duplicate_terminal_lock_risk: bool,
    measurement_age_s: float | None,
    los_rate_norm_px_s: float | None,
    config: VisualPngHandoffConfig,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not bool(association.metadata.get("execution_gate_pass", True)):
        gate_reason = association.metadata.get("execution_gate_reason") or "not_authorized"
        blockers.append(f"execution_gate:{gate_reason}")
    if association.decision_state != "locked":
        blockers.append(f"decision_not_locked:{association.decision_state}")
    if association.friend_conflict_state != "none":
        blockers.append(f"friend_conflict:{association.friend_conflict_state}")
    if not assignment_consistent:
        blockers.append("assignment_mismatch")
    if duplicate_terminal_lock_risk:
        blockers.append("duplicate_terminal_lock_risk")
    if association.local_track_id is None:
        blockers.append("no_local_track")
    if not _measurement_age_ok(measurement_age_s, config):
        if measurement_age_s is None:
            blockers.append("measurement_age_unknown")
        elif measurement_age_s < 0.0:
            blockers.append("measurement_timestamp_in_future")
        else:
            blockers.append("measurement_age_stale")
    if not _los_rate_ok(los_rate_norm_px_s, config):
        if los_rate_norm_px_s is None:
            blockers.append("los_rate_unavailable")
        else:
            blockers.append("los_rate_exceeds_limit")
    return tuple(blockers)


def _resolved_measurement_age_s(
    local_track_history: Iterable[LocalVisualTrack],
    local_track_id: str | None,
    *,
    current_time: float | None,
    measurement_age_s: float | None,
    detection_latency_s: float | None,
) -> float | None:
    if measurement_age_s is not None:
        return float(measurement_age_s)
    if current_time is not None:
        matching_timestamps = [
            float(track.timestamp)
            for track in local_track_history
            if local_track_id is None or track.local_track_id == local_track_id
        ]
        if matching_timestamps:
            return float(current_time) - max(matching_timestamps)
    if detection_latency_s is not None:
        return float(detection_latency_s)
    return None


def _association_measurement_age_s(
    association: TerminalAssociation,
    *,
    current_time: float | None,
) -> float | None:
    if association.local_track_id is not None:
        return None
    if association.measurement_age_s is not None:
        return float(association.measurement_age_s)
    if association.prediction_age_s is not None:
        return float(association.prediction_age_s)
    if current_time is not None and association.measurement_timestamp is not None:
        return float(current_time) - float(association.measurement_timestamp)
    return None


def _resolved_los_rate_px_s(
    local_track_history: Iterable[LocalVisualTrack],
    local_track_id: str | None,
    los_rate_px_s: Iterable[float] | np.ndarray | None,
) -> tuple[float, float] | None:
    if los_rate_px_s is not None:
        values = np.asarray(tuple(los_rate_px_s), dtype=float).reshape(-1)
        if values.shape != (2,):
            raise ValueError("los_rate_px_s must have shape (2,)")
        return (float(values[0]), float(values[1]))
    matching = [
        track
        for track in local_track_history
        if local_track_id is None or track.local_track_id == local_track_id
    ]
    if not matching:
        return None
    latest = max(matching, key=lambda track: track.timestamp)
    return (float(latest.bearing_rate[0]), float(latest.bearing_rate[1]))


def _los_rate_norm(los_rate_px_s: tuple[float, float] | None) -> float | None:
    if los_rate_px_s is None:
        return None
    value = float(np.linalg.norm(np.asarray(los_rate_px_s, dtype=float)))
    if not np.isfinite(value):
        return None
    return value


def _measurement_age_ok(
    measurement_age_s: float | None,
    config: VisualPngHandoffConfig,
) -> bool:
    if measurement_age_s is None:
        return False
    if not np.isfinite(measurement_age_s):
        return False
    return 0.0 <= float(measurement_age_s) <= config.max_measurement_age_s


def _los_rate_ok(
    los_rate_norm_px_s: float | None,
    config: VisualPngHandoffConfig,
) -> bool:
    if los_rate_norm_px_s is None:
        return not config.require_los_rate
    if not np.isfinite(los_rate_norm_px_s):
        return False
    if config.max_los_rate_px_s is None:
        return True
    return float(los_rate_norm_px_s) <= config.max_los_rate_px_s


def _timing_ok(
    *,
    time_to_go_s: float | None,
    detection_latency_s: float | None,
    d7_maneuver_margin: float | None,
    config: VisualPngHandoffConfig,
) -> bool:
    if time_to_go_s is not None and time_to_go_s < config.min_time_to_go_s:
        return False
    if detection_latency_s is not None and detection_latency_s > config.max_detection_latency_s:
        return False
    if d7_maneuver_margin is not None and d7_maneuver_margin < config.min_d7_maneuver_margin:
        return False
    return True
