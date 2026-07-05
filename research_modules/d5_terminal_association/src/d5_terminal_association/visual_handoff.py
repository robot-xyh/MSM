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
    d7_maneuver_margin: float | None = None,
    assignment_consistent: bool = True,
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
    stability = bbox_area_stability(
        local_track_history,
        image_size=image_size,
        local_track_id=association.local_track_id,
        config=cfg,
    )
    range_band = range_band_for_handoff(range_to_assigned_track_m, cfg)
    time_to_go_s = _time_to_go(range_to_assigned_track_m, closing_speed_mps)

    blocked_reason = _blocked_reason(
        association=association,
        assignment_consistent=assignment_consistent,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
    )
    timing_ok = _timing_ok(
        time_to_go_s=time_to_go_s,
        detection_latency_s=detection_latency_s,
        d7_maneuver_margin=d7_maneuver_margin,
        config=cfg,
    )

    handoff_recommended = False
    prelock_recommended = False
    reason = blocked_reason or stability.reason

    if blocked_reason is None and stability.stable:
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
    elif blocked_reason is None and range_band == "near_priority":
        reason = "near_range_bbox_unstable_keep_radar_pn"

    metadata = {
        **association.metadata,
        "handoff_recommended": handoff_recommended,
        "visual_png_handoff_recommended": handoff_recommended,
        "visual_png_prelock_recommended": prelock_recommended,
        "handoff_reason": reason,
        "recommended_range_band": range_band,
        "bbox_stability_score": stability.bbox_stability_score,
        "bbox_area_stability_score": stability.bbox_stability_score,
        "bbox_area_cv": stability.bbox_area_cv,
        "bbox_area_ratio": stability.bbox_area_ratio,
        "bbox_area_ratio_mean": stability.mean_bbox_area_ratio,
        "bbox_stable": stability.stable,
        "visible_frame_count": stability.visible_frame_count,
        "required_visible_frame_count": stability.required_frame_count,
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
        "d7_maneuver_margin": d7_maneuver_margin,
        "assignment_consistent": assignment_consistent,
        "duplicate_terminal_lock_risk": duplicate_terminal_lock_risk,
    }
    return replace(association, metadata=metadata)


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


def _blocked_reason(
    *,
    association: TerminalAssociation,
    assignment_consistent: bool,
    duplicate_terminal_lock_risk: bool,
) -> str | None:
    if association.decision_state != "locked":
        return f"decision_not_locked:{association.decision_state}"
    if association.friend_conflict_state != "none":
        return f"friend_conflict:{association.friend_conflict_state}"
    if not assignment_consistent:
        return "assignment_mismatch"
    if duplicate_terminal_lock_risk:
        return "duplicate_terminal_lock_risk"
    if association.local_track_id is None:
        return "no_local_track"
    return None


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
