from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    CameraModel,
    LocalVisualTrack,
    TerminalAssociation,
    VisualPngHandoffConfig,
    annotate_visual_png_handoff,
    expected_bbox_area_ratio,
    range_band_for_handoff,
    summarize_terminal_consistency,
)


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [100.0, 0.0, 320.0],
                [0.0, 100.0, 240.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _locked(
    *,
    friend_state: str = "none",
    local_id: str = "L-assigned",
) -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id="G-assigned",
        local_track_id=local_id,
        association_confidence=0.92,
        ambiguity_score=0.08,
        friend_conflict_state=friend_state,
        decision_state="locked",
        assignment_version=1,
        reason="unique_candidate_inside_gate",
    )


def _history(
    *,
    local_id: str = "L-assigned",
    side_px: tuple[float, ...] = (36.0, 37.0, 36.5, 37.5),
) -> list[LocalVisualTrack]:
    tracks: list[LocalVisualTrack] = []
    for index, side in enumerate(side_px):
        center = np.array([320.0 + index * 0.2, 240.0], dtype=float)
        half = side * 0.5
        tracks.append(
            LocalVisualTrack(
                local_track_id=local_id,
                center_px=center,
                bbox=(center[0] - half, center[1] - half, center[0] + half, center[1] + half),
                category="uav",
                quality=0.95,
                mot_history_length=index + 1,
                timestamp=float(index) * 0.1,
            )
        )
    return tracks


def test_middle_range_stable_locked_recommends_visual_png_handoff() -> None:
    decision = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(),
        image_size=(640, 480),
        range_to_assigned_track_m=24.0,
        closing_speed_mps=8.0,
        detection_latency_s=0.08,
        d7_maneuver_margin=0.25,
        current_assigned_global_track_id="G-assigned",
    )

    assert decision.metadata["recommended_range_band"] == "middle_handoff"
    assert decision.metadata["handoff_recommended"] is True
    assert decision.metadata["visual_png_handoff_recommended"] is True
    assert decision.metadata["handoff_reason"] == "bbox_area_stable_middle_range"
    assert decision.metadata["bbox_area_cv"] <= VisualPngHandoffConfig().max_bbox_area_cv
    assert decision.metadata["time_to_go_s"] == 3.0
    assert decision.metadata["visual_png_gate_pass"] is True
    assert decision.metadata["visual_png_handoff_blockers"] == []
    assert decision.metadata["measurement_age_s"] == 0.08
    assert decision.metadata["measurement_age_ok"] is True
    assert decision.metadata["los_rate_available"] is True
    assert decision.metadata["los_rate_ok"] is True
    assert decision.metadata["assignment_consistency_gate_pass"] is True

    summary = summarize_terminal_consistency(
        resource_id="INT-01",
        timestamp=1.0,
        association=decision,
    )
    assert summary.metadata["handoff_recommended"] is True
    assert summary.metadata["recommended_range_band"] == "middle_handoff"


def test_far_range_stable_bbox_only_prelocks_not_direct_handoff() -> None:
    decision = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(side_px=(24.0, 24.5, 25.0, 24.8)),
        image_size=(640, 480),
        range_to_assigned_track_m=42.0,
        closing_speed_mps=8.0,
        detection_latency_s=0.08,
        d7_maneuver_margin=0.25,
    )

    assert decision.metadata["recommended_range_band"] == "far_prepare"
    assert decision.metadata["visual_png_prelock_recommended"] is True
    assert decision.metadata["handoff_recommended"] is False
    assert decision.metadata["handoff_reason"] == "far_range_bbox_area_stable_prepare"


def test_handoff_distance_bands_are_configurable_not_fixed_30m() -> None:
    default_decision = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(side_px=(28.0, 28.5, 28.3, 28.4)),
        image_size=(640, 480),
        range_to_assigned_track_m=36.0,
        closing_speed_mps=9.0,
        detection_latency_s=0.08,
    )

    custom_config = VisualPngHandoffConfig(
        far_prepare_range_m=(50.0, 70.0),
        middle_handoff_range_m=(25.0, 50.0),
        near_priority_range_m=(8.0, 25.0),
        min_stable_frames=4,
        max_bbox_area_cv=0.30,
        min_bbox_area_ratio=0.0008,
    )
    custom_decision = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(side_px=(28.0, 28.5, 28.3, 28.4)),
        image_size=(640, 480),
        range_to_assigned_track_m=36.0,
        closing_speed_mps=9.0,
        detection_latency_s=0.08,
        config=custom_config,
    )

    assert range_band_for_handoff(36.0) == "far_prepare"
    assert default_decision.metadata["handoff_recommended"] is False
    assert default_decision.metadata["visual_png_prelock_recommended"] is True
    assert range_band_for_handoff(36.0, custom_config) == "middle_handoff"
    assert custom_decision.metadata["handoff_recommended"] is True
    assert custom_decision.metadata["handoff_candidate_range_m"] == (8.0, 50.0)


def test_friend_conflict_and_assignment_mismatch_block_handoff() -> None:
    friend_blocked = annotate_visual_png_handoff(
        _locked(friend_state="verified_friend_overlap"),
        local_track_history=_history(),
        image_size=(640, 480),
        range_to_assigned_track_m=12.0,
        closing_speed_mps=6.0,
        detection_latency_s=0.05,
    )
    mismatch_blocked = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(),
        image_size=(640, 480),
        range_to_assigned_track_m=24.0,
        closing_speed_mps=8.0,
        detection_latency_s=0.05,
        assignment_consistent=False,
    )

    assert friend_blocked.metadata["handoff_recommended"] is False
    assert friend_blocked.metadata["handoff_reason"] == "friend_conflict:verified_friend_overlap"
    assert mismatch_blocked.metadata["handoff_recommended"] is False
    assert mismatch_blocked.metadata["handoff_reason"] == "assignment_mismatch"


def test_stale_measurement_age_and_missing_los_block_handoff() -> None:
    stale = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(),
        image_size=(640, 480),
        range_to_assigned_track_m=24.0,
        closing_speed_mps=8.0,
        measurement_age_s=0.9,
        los_rate_px_s=(0.0, 0.0),
    )
    no_los = annotate_visual_png_handoff(
        _locked(),
        local_track_history=[],
        image_size=(640, 480),
        range_to_assigned_track_m=24.0,
        closing_speed_mps=8.0,
        measurement_age_s=0.05,
    )

    assert stale.metadata["handoff_recommended"] is False
    assert stale.metadata["measurement_age_ok"] is False
    assert "measurement_age_stale" in stale.metadata["visual_png_handoff_blockers"]
    assert no_los.metadata["handoff_recommended"] is False
    assert no_los.metadata["los_rate_available"] is False
    assert "los_rate_unavailable" in no_los.metadata["visual_png_handoff_blockers"]


def test_lost_reacquire_does_not_borrow_unrelated_local_track_evidence() -> None:
    lost = TerminalAssociation(
        assigned_global_track_id="G-assigned",
        local_track_id=None,
        association_confidence=0.0,
        ambiguity_score=1.0,
        friend_conflict_state="none",
        decision_state="reacquire",
        assignment_version=1,
        reason="projection_invalid:outside_image",
        measurement_timestamp=10.0,
        arrival_timestamp=10.6,
        measurement_age_s=0.6,
        prediction_age_s=0.6,
        local_track_state="lost",
    )
    unrelated_tracks = _history(local_id="L-other")

    decision = annotate_visual_png_handoff(
        lost,
        local_track_history=unrelated_tracks,
        image_size=(640, 480),
        range_to_assigned_track_m=8.0,
        closing_speed_mps=6.0,
        current_time=10.6,
    )

    assert decision.measurement_age_s == 0.6
    assert decision.prediction_age_s == 0.6
    assert decision.metadata["measurement_age_s"] == 0.6
    assert decision.metadata["measurement_age_ok"] is False
    assert decision.metadata["los_rate_available"] is False
    assert decision.metadata["visible_frame_count"] == 0
    assert decision.metadata["bbox_stable"] is False
    assert "no_local_track" in decision.metadata["visual_png_handoff_blockers"]
    assert "measurement_age_stale" in decision.metadata["visual_png_handoff_blockers"]
    assert "los_rate_unavailable" in decision.metadata["visual_png_handoff_blockers"]


def test_lost_reacquire_uses_prediction_age_when_measurement_age_is_missing() -> None:
    lost = TerminalAssociation(
        assigned_global_track_id="G-assigned",
        local_track_id=None,
        association_confidence=0.0,
        ambiguity_score=1.0,
        friend_conflict_state="none",
        decision_state="reacquire",
        assignment_version=1,
        reason="projection_invalid:outside_image",
        measurement_timestamp=4.1,
        arrival_timestamp=4.3,
        prediction_age_s=0.2,
        local_track_state="lost",
    )

    decision = annotate_visual_png_handoff(
        lost,
        local_track_history=[],
        image_size=(640, 480),
        current_time=4.3,
    )

    assert decision.measurement_age_s == 0.2
    assert decision.prediction_age_s == 0.2
    assert decision.metadata["measurement_age_s"] == 0.2
    assert decision.metadata["measurement_age_ok"] is True
    assert "measurement_age_unknown" not in decision.metadata["visual_png_handoff_blockers"]


def test_near_range_unstable_bbox_keeps_radar_pn_and_formula_estimates_area_ratio() -> None:
    decision = annotate_visual_png_handoff(
        _locked(),
        local_track_history=_history(side_px=(20.0, 42.0, 18.0, 45.0)),
        image_size=(640, 480),
        range_to_assigned_track_m=10.0,
        closing_speed_mps=6.0,
        detection_latency_s=0.05,
    )

    assert decision.metadata["recommended_range_band"] == "near_priority"
    assert decision.metadata["handoff_recommended"] is False
    assert decision.metadata["handoff_reason"] == "near_range_bbox_unstable_keep_radar_pn"

    ratio = expected_bbox_area_ratio(
        range_m=25.0,
        target_size_m=(2.0, 2.0),
        camera=_camera(),
    )
    assert ratio > 0.0
