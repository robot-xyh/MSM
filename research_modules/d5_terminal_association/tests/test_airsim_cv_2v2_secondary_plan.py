from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    Assignment,
    CameraModel,
    GlobalTrack,
    IdentityChecker,
    ReconImageCue,
    TerminalAssociator,
    annotate_visual_png_handoff,
    compute_terminal_stress_metrics,
    local_visual_tracks_from_sim_detections,
    summarize_degradation_case,
    TerminalObservationBus,
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


def _global_track(global_id: str, x_m: float) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_id,
        position=np.array([x_m, 0.0, 10.0], dtype=float),
        covariance=np.diag([0.01, 0.01, 0.01]),
        category="uav",
        timestamp=20.0,
        track_version=7,
    )


def _box(center_u: float, side_px: float = 22.0) -> tuple[float, float, float, float]:
    half = side_px * 0.5
    return (center_u - half, 240.0 - half, center_u + half, 240.0 + half)


def _detections() -> list[dict]:
    return [
        {
            "box2D": {
                "min": {"x_val": 279.0, "y_val": 229.0},
                "max": {"x_val": 301.0, "y_val": 251.0},
            },
            "label": "uav",
            "score": 0.92,
            "local_track_id": "det-G1",
            "mot_history_length": 5,
            "truth_global_track_id": "G1",
        },
        {
            "box2D": {
                "min": {"x_val": 339.0, "y_val": 229.0},
                "max": {"x_val": 361.0, "y_val": 251.0},
            },
            "label": "uav",
            "score": 0.94,
            "local_track_id": "det-G2",
            "mot_history_length": 5,
            "truth_global_track_id": "G2",
        },
    ]


def _secondary_cue() -> ReconImageCue:
    return ReconImageCue(
        cue_id="secondary-2v2-cue-G2",
        producer_node_id="secondary-node-A",
        timestamp=20.0,
        image_frame_id="INT-1/front_rgb",
        global_track_id="G2",
        center_px=np.array([350.0, 240.0], dtype=float),
        confidence=0.9,
        scoped_resource_ids=("INT-1",),
        metadata={
            "source_image_frame_id": "secondary-node-A/wide_rgb",
            "target_frame_id": "INT-1/front_rgb",
            "reprojected_to_local_camera": True,
            "plan_source": "secondary_2v2",
        },
    )


def test_2v2_secondary_plan_locks_only_assigned_truth_stable_no_friend_conflict() -> None:
    camera = _camera()
    tracks = [_global_track("G1", -3.0), _global_track("G2", 3.0)]
    local_tracks = local_visual_tracks_from_sim_detections(
        _detections(),
        resource_id="INT-1",
        camera_id="front_rgb",
        timestamp=20.0,
    )
    input_global_ids = tuple(track.global_track_id for track in tracks)
    assignment = Assignment(
        assigned_global_track_id="G2",
        assignment_version=7,
        plan_id="secondary-plan-2v2",
        plan_version=3,
        authorization_state="authorized",
        resource_id="INT-1",
        timestamp=20.0,
    )

    decision = TerminalAssociator().decide(
        assignment,
        tracks,
        local_tracks,
        camera=camera,
        current_time=20.0,
        recon_image_cues=[_secondary_cue()],
        frame_id="INT-1/front_rgb",
    )
    stable_history = [
        local_tracks[1],
        local_tracks[1],
        local_tracks[1],
        local_tracks[1],
    ]
    handoff = annotate_visual_png_handoff(
        decision,
        local_track_history=stable_history,
        image_size=camera.image_size,
        range_to_assigned_track_m=20.0,
        closing_speed_mps=8.0,
        detection_latency_s=0.08,
        d7_maneuver_margin=0.2,
        assignment_consistent=True,
    )

    assert tuple(track.global_track_id for track in tracks) == input_global_ids
    assert decision.decision_state == "locked"
    assert decision.assigned_global_track_id == "G2"
    assert decision.local_track_id == "det-G2"
    assert decision.friend_conflict_state == "none"
    assert decision.recon_cue_used is True
    assert handoff.metadata["bbox_stable"] is True
    assert handoff.metadata["handoff_recommended"] is True


def test_2v2_secondary_plan_reports_locked_mismatch_as_problem_not_rewrite() -> None:
    association = TerminalAssociator().decide(
        Assignment(
            assigned_global_track_id="G2",
            assignment_version=7,
            plan_id="secondary-plan-2v2",
            plan_version=3,
            resource_id="INT-1",
        ),
        [_global_track("G1", -3.0), _global_track("G2", 3.0)],
        local_visual_tracks_from_sim_detections(
            [_detections()[1]],
            resource_id="INT-1",
            camera_id="front_rgb",
            timestamp=20.0,
        ),
        camera=_camera(),
        current_time=20.0,
    )
    bus = TerminalObservationBus()
    bus.publish_terminal_association(
        resource_id="INT-1",
        source_node_id="INT-1",
        link_type="secondary_relay",
        timestamp=20.0,
        terminal_association=association,
        camera_id="front_rgb",
        frame_id="INT-1/front_rgb",
        metadata={"truth_global_track_id": "G1"},
    )

    summary = summarize_degradation_case(
        bus.observations(),
        bus.cross_view_associations(),
        current_time=20.0,
        min_problem_observations=1,
    )
    metrics = compute_terminal_stress_metrics(bus.observations(), bus.cross_view_associations())
    handoff = annotate_visual_png_handoff(
        association,
        local_track_history=[],
        image_size=_camera().image_size,
        range_to_assigned_track_m=20.0,
        closing_speed_mps=8.0,
        assignment_consistent=False,
    )

    assert association.decision_state == "locked"
    assert association.assigned_global_track_id == "G2"
    assert summary.reasons == ("INT-1:locked_mismatch",)
    assert metrics.terminal_lock_accuracy == 0.0
    assert handoff.metadata["handoff_recommended"] is False
    assert handoff.metadata["handoff_reason"] == "assignment_mismatch"


def test_2v2_secondary_plan_close_airsim_boxes_are_ambiguous() -> None:
    local_tracks = local_visual_tracks_from_sim_detections(
        [
            {
                "bbox": _box(349.0),
                "local_track_id": "det-G2-left",
                "category": "uav",
                "confidence": 0.94,
                "mot_history_length": 5,
            },
            {
                "bbox": _box(351.0),
                "local_track_id": "det-G2-right",
                "category": "uav",
                "confidence": 0.94,
                "mot_history_length": 5,
            },
        ],
        resource_id="INT-1",
        camera_id="front_rgb",
        timestamp=20.0,
    )

    decision = TerminalAssociator().decide(
        Assignment("G2", assignment_version=7, resource_id="INT-1"),
        [_global_track("G2", 3.0)],
        local_tracks,
        camera=_camera(),
        current_time=20.0,
    )

    assert decision.decision_state == "ambiguous"
    assert decision.reason == "insufficient_best_second_margin"
    assert decision.assigned_global_track_id == "G2"
    assert decision.local_track_id in {"det-G2-left", "det-G2-right"}


def test_2v2_secondary_plan_unstable_bbox_or_friend_conflict_blocks_effective_lock() -> None:
    camera = _camera()
    association = TerminalAssociator().decide(
        Assignment("G2", assignment_version=7, resource_id="INT-1"),
        [_global_track("G2", 3.0)],
        local_visual_tracks_from_sim_detections(
            [_detections()[1]],
            resource_id="INT-1",
            camera_id="front_rgb",
            timestamp=20.0,
        ),
        camera=camera,
        current_time=20.0,
    )
    unstable_history = local_visual_tracks_from_sim_detections(
        [
            {"bbox": _box(350.0, 14.0), "local_track_id": "det-G2", "mot_history_length": 5},
            {"bbox": _box(350.0, 34.0), "local_track_id": "det-G2", "mot_history_length": 5},
            {"bbox": _box(350.0, 16.0), "local_track_id": "det-G2", "mot_history_length": 5},
            {"bbox": _box(350.0, 36.0), "local_track_id": "det-G2", "mot_history_length": 5},
        ],
        resource_id="INT-1",
        camera_id="front_rgb",
        timestamp=20.0,
    )
    unstable = annotate_visual_png_handoff(
        association,
        local_track_history=unstable_history,
        image_size=camera.image_size,
        range_to_assigned_track_m=10.0,
        closing_speed_mps=8.0,
        detection_latency_s=0.08,
        assignment_consistent=True,
    )

    checker = IdentityChecker(friendly_platform_ids={"FRIEND-1"})
    friend_claims = checker.parse_claims(
        [
            {
                "protocol": "OpenDroneID",
                "platform_id": "FRIEND-1",
                "local_track_id": "det-G2",
                "timestamp": 20.0,
                "is_friend": True,
                "signature_valid": True,
            }
        ],
        current_time=20.0,
    )
    hold = TerminalAssociator(identity_checker=checker).decide(
        Assignment("G2", assignment_version=7, resource_id="INT-1"),
        [_global_track("G2", 3.0)],
        local_visual_tracks_from_sim_detections(
            [_detections()[1]],
            resource_id="INT-1",
            camera_id="front_rgb",
            timestamp=20.0,
        ),
        identity_claims=friend_claims,
        camera=camera,
        current_time=20.0,
    )

    assert association.decision_state == "locked"
    assert unstable.metadata["bbox_stable"] is False
    assert unstable.metadata["handoff_recommended"] is False
    assert unstable.metadata["handoff_reason"] == "near_range_bbox_unstable_keep_radar_pn"
    assert hold.decision_state == "hold"
    assert hold.friend_conflict_state == "verified_friend_overlap"
    assert hold.assigned_global_track_id == "G2"
