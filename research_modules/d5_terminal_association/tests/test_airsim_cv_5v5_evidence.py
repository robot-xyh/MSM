from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    AirSimCVScenarioSpec,
    Assignment,
    CameraModel,
    FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE,
    GlobalTrack,
    LocalVisualTrack,
    MOBILE_HIGH_RECON_CAPABILITY_CLASS,
    MOBILE_RECON_GIMBAL_COVERAGE_MODE,
    ReconImageCue,
    TerminalAssociation,
    TerminalAssociator,
    TerminalObservationBus,
    compute_terminal_stress_metrics,
    local_visual_tracks_from_offline_yolo_bytetrack,
    local_visual_tracks_from_sim_detections,
    publish_sim_detections_as_local_observations,
    summarize_degradation_case,
    summarize_multiseed_calibration_readiness,
    summarize_secondary_visual_coverage_funnel,
)


def _detections(count: int, *, x0: float = 100.0) -> list[dict]:
    return [
        {
            "bbox": (x0 + index * 42.0, 180.0, x0 + index * 42.0 + 24.0, 204.0),
            "category": "uav",
            "confidence": 0.9,
            "mot_history_length": 4,
        }
        for index in range(count)
    ]


def _local(local_id: str) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array([320.0, 240.0], dtype=float),
        bbox=(312.0, 232.0, 328.0, 248.0),
        category="uav",
        quality=0.9,
        mot_history_length=4,
    )


def _association(
    global_id: str,
    local_id: str | None,
    *,
    decision: str = "locked",
    confidence: float = 0.9,
    ambiguity: float = 0.1,
    friend_state: str = "none",
    cue_used: bool = False,
) -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id=global_id,
        local_track_id=local_id,
        association_confidence=confidence,
        ambiguity_score=ambiguity,
        friend_conflict_state=friend_state,
        decision_state=decision,
        assignment_version=1,
        reason="5v5_fixture",
        recon_cue_used=cue_used,
    )


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [160.0, 0.0, 320.0],
                [0.0, 160.0, 240.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _global_track(global_id: str, position: tuple[float, float, float] = (0.0, 0.0, 20.0)) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_id,
        position=np.array(position, dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        category="uav",
        timestamp=5.0,
    )


def _secondary_cue(global_id: str, *, timestamp: float = 10.0, expired: bool = False) -> ReconImageCue:
    return ReconImageCue(
        cue_id=f"cue-{global_id}",
        producer_node_id="Tethered_Recon_1",
        timestamp=timestamp,
        image_frame_id="Interceptor_Cam_1/front_rgb",
        global_track_id=global_id,
        center_px=np.array([320.0, 240.0], dtype=float),
        confidence=0.85,
        scoped_resource_ids=("Interceptor_Cam_1", "Interceptor_Cam_2"),
        metadata={
            "source_image_frame_id": "Tethered_Recon_1/high_res_global",
            "reprojected_to_local_camera": True,
            "expired": expired,
        },
    )


def test_airsim_cv_scenario_defaults_are_stress_baseline_not_runtime_limit() -> None:
    spec = AirSimCVScenarioSpec()
    assert spec.interceptor_count == 5
    assert spec.target_count == 5
    assert spec.nominal_target_distance_m == 50.0
    assert spec.target_spacing_m == 20.0
    assert spec.interceptor_camera_spacing_m == 20.0
    assert spec.secondary_recon_height_offset_m == 200.0

    runtime_spec = AirSimCVScenarioSpec(interceptor_count=7, target_count=7)
    assert runtime_spec.interceptor_count == 7
    assert runtime_spec.target_count == 7


def test_airsim_cv_detection_fixtures_follow_runtime_camera_count() -> None:
    spec = AirSimCVScenarioSpec(interceptor_count=7, target_count=7)
    bus = TerminalObservationBus()
    for index in range(1, spec.interceptor_count + 1):
        resource_id = f"Interceptor_Cam_{index}"
        tracks = publish_sim_detections_as_local_observations(
            bus,
            _detections(3, x0=80.0 + index * 5.0),
            resource_id=resource_id,
            camera_id="front_rgb",
            frame_id=f"{resource_id}/front_rgb",
            timestamp=10.0,
            arrival_timestamp=10.05,
        )
        assert len(tracks) == 3
        assert all(track.category == "uav" for track in tracks)

    metrics = compute_terminal_stress_metrics(bus.observations(), bus.cross_view_associations())

    assert len(metrics.per_camera_detection_count) == spec.interceptor_count
    assert all(count == 3 for count in metrics.per_camera_detection_count.values())
    assert metrics.multi_target_fov_rate == 1.0
    assert metrics.cross_view_overlap_count == 0


def test_detection_parser_accepts_airsim_box2d_shape_without_airsim_import() -> None:
    detections = [
        {
            "box2D": {
                "min": {"x_val": 10.0, "y_val": 20.0},
                "max": {"x_val": 30.0, "y_val": 50.0},
            },
            "label": "uav",
            "score": 0.75,
        }
    ]

    tracks = local_visual_tracks_from_sim_detections(
        detections,
        resource_id="Interceptor_Cam_1",
        camera_id="front_rgb",
        timestamp=2.0,
    )

    assert tracks[0].bbox == (10.0, 20.0, 30.0, 50.0)
    np.testing.assert_allclose(tracks[0].center_px, np.array([20.0, 35.0]))
    assert tracks[0].quality == 0.75


def test_detection_parser_accepts_runtime_bbox_xyxy_and_yolo_xyxy_schema() -> None:
    detections = [
        {
            "bbox_xyxy": (12.0, 24.0, 52.0, 64.0),
            "classification_hint": "uav",
            "confidence": 0.88,
            "local_track_id": "airsim-det-1",
        },
        {
            "xyxy": (100.0, 120.0, 140.0, 160.0),
            "class_name": "uav",
            "score": 0.91,
            "track_id": "yolo-track-1",
        },
    ]

    tracks = local_visual_tracks_from_sim_detections(
        detections,
        resource_id="Interceptor_Cam_1",
        camera_id="front_rgb",
        timestamp=3.0,
    )

    assert tracks[0].local_track_id == "airsim-det-1"
    assert tracks[0].bbox == (12.0, 24.0, 52.0, 64.0)
    np.testing.assert_allclose(tracks[0].center_px, np.array([32.0, 44.0]))
    assert tracks[1].local_track_id == "yolo-track-1"
    assert tracks[1].bbox == (100.0, 120.0, 140.0, 160.0)
    np.testing.assert_allclose(tracks[1].center_px, np.array([120.0, 140.0]))


def test_detection_parser_ignores_airsim_truth_identity_fields_online() -> None:
    detections = [
        {
            "bbox_xyxy": (12.0, 24.0, 52.0, 64.0),
            "object_id": "TGT_TRUE_1",
            "actor_name": "TargetActor_1",
            "confidence": 0.88,
        },
        {
            "bbox_xyxy": (100.0, 120.0, 140.0, 160.0),
            "object_id": "TGT_TRUE_2",
            "actor_name": "TargetActor_2",
            "confidence": 0.91,
        },
    ]

    tracks = local_visual_tracks_from_sim_detections(
        detections,
        resource_id="Interceptor_Cam_1",
        camera_id="front_rgb",
        timestamp=3.0,
    )

    assert [track.local_track_id for track in tracks] == ["front_rgb_det_0", "front_rgb_det_1"]
    assert all("TGT_TRUE" not in track.local_track_id for track in tracks)
    np.testing.assert_allclose(tracks[0].center_px, np.array([32.0, 44.0]))


def test_secondary_node_sim_detections_do_not_use_actor_truth_as_local_identity() -> None:
    detections = [
        {
            "box2D": {
                "min": {"x_val": 300.0, "y_val": 220.0},
                "max": {"x_val": 340.0, "y_val": 260.0},
            },
            "track_id": "TargetActor_7",
            "object_id": "TargetActor_7",
            "actor_name": "TargetActor_7",
            "name": "TargetActor_7",
            "truth_id": "G-other",
            "global_track_id": "G-other",
            "label": "uav",
            "score": 0.93,
            "mot_history_length": 4,
        }
    ]
    bus = TerminalObservationBus()

    tracks = publish_sim_detections_as_local_observations(
        bus,
        detections,
        resource_id="Tethered_Recon_1",
        camera_id="wide_rgb",
        frame_id="Tethered_Recon_1/wide_rgb",
        timestamp=5.0,
        arrival_timestamp=5.02,
        source_node_id="secondary-node-1",
    )

    assert tracks[0].local_track_id == "wide_rgb_det_0"
    assert "TargetActor" not in tracks[0].local_track_id
    assert not hasattr(tracks[0], "global_track_id")
    assert bus.observations()[0].metadata == {"source": "simGetDetections"}
    assert "TargetActor_7" not in str(bus.observations()[0].metadata)
    assert "G-other" not in str(bus.observations()[0].metadata)
    assert bus.cross_view_associations() == []


def test_secondary_coverage_distinguishes_single_camera_from_network_union() -> None:
    active_targets = tuple(f"G{index}" for index in range(1, 6))

    summary = summarize_secondary_visual_coverage_funnel(
        secondary_frames=[
            {
                "frame_id": "frame-1",
                "camera_id": "secondary-wide-A",
                "active_target_ids": active_targets,
                "visible_target_ids": ("G1", "G2", "G3", "G4"),
            },
            {
                "frame_id": "frame-1",
                "camera_id": "secondary-wide-B",
                "active_target_ids": active_targets,
                "visible_target_ids": ("G2", "G3", "G4", "G5"),
            },
        ],
        active_target_ids=active_targets,
        secondary_camera_ids=("secondary-wide-A", "secondary-wide-B"),
    )

    assert summary.secondary_single_camera_full_view_frame_rate == 0.0
    assert summary.secondary_network_joint_full_view_frame_rate == 1.0
    assert summary.secondary_camera_frame_visible_target_counts == {
        "secondary-wide-A": {"frame-1": 4},
        "secondary-wide-B": {"frame-1": 4},
    }
    assert summary.secondary_network_frame_joint_visible_target_counts == {"frame-1": 5}
    assert summary.secondary_single_camera_coverage_ratio_mean == 0.8
    assert summary.secondary_single_camera_coverage_ratio_min == 0.8
    assert summary.secondary_network_joint_coverage_ratio_mean == 1.0
    assert summary.secondary_network_joint_coverage_ratio_min == 1.0
    assert summary.rejection_reason_counts["not_all_targets_visible"] == 2
    assert summary.rejection_reason_counts["network_union_incomplete"] == 0


def test_mobile_recon_gimbal_cue_improves_secondary_coverage_and_cross_view_evidence() -> None:
    active_targets = ("G1", "G2", "G3", "G4")
    cue_position_ned = (0.0, -40.0, -180.0)
    look_at_ned = (260.0, 20.0, -20.0)

    summary = summarize_secondary_visual_coverage_funnel(
        secondary_frames=[
            {
                "frame_id": "frame-cue-1",
                "active_target_ids": active_targets,
                "secondary_cameras": {
                    "secondary-fixed-downlook": {
                        "camera_id": "secondary-fixed-downlook",
                        "coverage_mode": FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE,
                        "visible_target_ids": ("G1", "G2"),
                    },
                    "mobile-recon-gimbal-1": {
                        "camera_id": "mobile-recon-gimbal-1",
                        "coverage_mode": MOBILE_RECON_GIMBAL_COVERAGE_MODE,
                        "capability_class": MOBILE_HIGH_RECON_CAPABILITY_CLASS,
                        "cue_source": "radar_global_track_cue",
                        "cue_position_ned": cue_position_ned,
                        "look_at_ned": look_at_ned,
                        "gimbal_pointing_metadata": {
                            "yaw_rad": 0.18,
                            "pitch_rad": -0.42,
                            "target_subcluster_id": "cluster-east",
                        },
                        "cue_pointing_error_m": 2.5,
                        "cue_pointing_error_rad": 0.012,
                        "gimbal_track_error_px": 3.75,
                        "visible_target_ids": ("G3", "G4"),
                    },
                },
            }
        ],
        active_target_ids=active_targets,
        secondary_camera_ids=("secondary-fixed-downlook", "mobile-recon-gimbal-1"),
    )

    fixed_frame = {
        frame.camera_id: frame
        for frame in summary.camera_frames
    }["secondary-fixed-downlook"]
    mobile_frame = {
        frame.camera_id: frame
        for frame in summary.camera_frames
    }["mobile-recon-gimbal-1"]
    network_frame = summary.network_frames[0]

    assert summary.secondary_single_camera_full_view_frame_rate == 0.0
    assert summary.secondary_network_joint_full_view_frame_rate == 1.0
    assert fixed_frame.coverage_mode == FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE
    assert mobile_frame.coverage_mode == MOBILE_RECON_GIMBAL_COVERAGE_MODE
    assert mobile_frame.capability_class == MOBILE_HIGH_RECON_CAPABILITY_CLASS
    assert mobile_frame.cue_source == "radar_global_track_cue"
    assert mobile_frame.cue_position_ned == cue_position_ned
    assert mobile_frame.look_at_ned == look_at_ned
    assert mobile_frame.gimbal_pointing_metadata["target_subcluster_id"] == "cluster-east"
    assert mobile_frame.cue_pointing_error_m == 2.5
    assert mobile_frame.cue_pointing_error_rad == 0.012
    assert mobile_frame.gimbal_track_error_px == 3.75
    assert network_frame.metadata["fixed_downlook_secondary_joint_full_view"] is False
    assert network_frame.metadata["mobile_recon_gimbal_improved_joint_coverage"] is True
    assert network_frame.metadata["mobile_recon_gimbal_added_target_ids"] == ("G3", "G4")
    assert summary.metadata["mobile_recon_gimbal_improved_joint_coverage_frame_count"] == 1
    assert summary.metadata["mobile_recon_gimbal_added_target_ids_by_frame"] == {
        "frame-cue-1": ("G3", "G4")
    }
    assert summary.metadata["cue_pointing_error_m_by_camera_frame"] == {
        "frame-cue-1/mobile-recon-gimbal-1": 2.5
    }
    assert summary.metadata["gimbal_track_error_px_by_camera_frame"] == {
        "frame-cue-1/mobile-recon-gimbal-1": 3.75
    }

    cue = ReconImageCue(
        cue_id="cue-mobile-recon-G3",
        producer_node_id="mobile-recon-gimbal-1",
        timestamp=10.0,
        image_frame_id="Interceptor_Cam_1/front_rgb",
        global_track_id="G3",
        center_px=np.array([320.0, 240.0], dtype=float),
        confidence=0.86,
        scoped_resource_ids=("Interceptor_Cam_1",),
        source_type="secondary_recon",
        cue_position_ned=np.array(cue_position_ned, dtype=float),
        look_at_ned=np.array(look_at_ned, dtype=float),
        gimbal_pointing_metadata={
            "yaw_rad": 0.18,
            "pitch_rad": -0.42,
            "target_subcluster_id": "cluster-east",
        },
        cue_pointing_error_m=2.5,
        cue_pointing_error_rad=0.012,
        gimbal_track_error_px=3.75,
        cue_source="radar_global_track_cue",
        capability_class=MOBILE_HIGH_RECON_CAPABILITY_CLASS,
        coverage_mode=MOBILE_RECON_GIMBAL_COVERAGE_MODE,
        metadata={
            "source_image_frame_id": "mobile-recon-gimbal-1/eo_rgb",
            "reprojected_to_local_camera": True,
        },
    )
    bus = TerminalObservationBus()
    bus.publish_terminal_association(
        resource_id="Interceptor_Cam_1",
        source_node_id="mobile-recon-gimbal-1",
        link_type="secondary_relay",
        timestamp=10.0,
        terminal_association=_association("G3", "L3", cue_used=True),
        local_track=_local("L3"),
        recon_image_cues=[cue],
        camera_id="front_rgb",
        frame_id="Interceptor_Cam_1/front_rgb",
    )
    bus.publish_terminal_association(
        resource_id="Interceptor_Cam_2",
        source_node_id="Interceptor_Cam_2",
        link_type="interceptor_peer",
        timestamp=10.0,
        terminal_association=_association("G3", "L7"),
        local_track=_local("L7"),
        camera_id="front_rgb",
        frame_id="Interceptor_Cam_2/front_rgb",
    )

    cross_view = bus.cross_view_associations()[0]
    cue_evidence = cross_view.metadata["recon_cue_evidence"][0]

    assert cross_view.global_track_id == "G3"
    assert cross_view.supporting_resource_ids == ("Interceptor_Cam_1", "Interceptor_Cam_2")
    assert cross_view.metadata["coverage_modes"] == (MOBILE_RECON_GIMBAL_COVERAGE_MODE,)
    assert cross_view.metadata["capability_classes"] == (MOBILE_HIGH_RECON_CAPABILITY_CLASS,)
    assert cross_view.metadata["cue_sources"] == ("radar_global_track_cue",)
    assert cross_view.metadata["mobile_recon_gimbal_support_count"] == 1
    assert cue_evidence["cue_position_ned"] == [0.0, -40.0, -180.0]
    assert cue_evidence["look_at_ned"] == [260.0, 20.0, -20.0]
    assert cue_evidence["gimbal_pointing_metadata"]["target_subcluster_id"] == "cluster-east"
    assert cue_evidence["cue_pointing_error_m"] == 2.5
    assert cue_evidence["cue_pointing_error_rad"] == 0.012
    assert cue_evidence["gimbal_track_error_px"] == 3.75
    assert cue_evidence["cue_source"] == "radar_global_track_cue"
    assert cue_evidence["capability_class"] == MOBILE_HIGH_RECON_CAPABILITY_CLASS
    assert cue_evidence["coverage_mode"] == MOBILE_RECON_GIMBAL_COVERAGE_MODE


def test_secondary_detect_offline_only_without_global_binding_stops_before_cross_view() -> None:
    bus = TerminalObservationBus()
    bus.publish_local_track(
        resource_id="Tethered_Recon_1",
        source_node_id="secondary-node-1",
        link_type="airsim_cv_detection",
        timestamp=10.0,
        local_track=_local("offline-local-G1"),
        camera_id="wide_rgb",
        frame_id="Tethered_Recon_1/wide_rgb",
        metadata={
            "source": "simGetDetections",
            "truth_global_track_id": "G1",
        },
    )

    summary = summarize_secondary_visual_coverage_funnel(
        observations=bus.observations(),
        active_target_ids=("G1",),
    )

    assert summary.funnel_counts.detect_count == 1
    assert summary.funnel_counts.local_or_recon_cue_count == 1
    assert summary.funnel_counts.terminal_association_count == 0
    assert summary.funnel_counts.cross_view_association_count == 0
    assert summary.funnel_counts.multi_support_count == 0
    assert summary.rejection_reason_counts["no_global_binding"] == 1
    assert summary.rejection_reason_counts["secondary_detect_offline_only"] == 1
    assert "no_global_binding" in summary.funnel_counts.breakpoint_reasons


def test_terminal_association_uses_sim_detection_geometry_not_actor_truth_id() -> None:
    local_tracks = local_visual_tracks_from_sim_detections(
        [
            {
                "bbox_xyxy": (312.0, 232.0, 328.0, 248.0),
                "track_id": "TargetActor_99",
                "object_id": "TargetActor_99",
                "actor_name": "TargetActor_99",
                "truth_id": "G-other",
                "global_track_id": "G-other",
                "category": "uav",
                "confidence": 0.94,
                "mot_history_length": 4,
            }
        ],
        resource_id="INT-1",
        camera_id="front_rgb",
        timestamp=5.0,
    )

    decision = TerminalAssociator().decide(
        Assignment("G-assigned", resource_id="INT-1"),
        [_global_track("G-assigned")],
        local_tracks,
        camera=_camera(),
        current_time=5.0,
    )

    assert local_tracks[0].local_track_id == "front_rgb_det_0"
    assert decision.decision_state == "locked"
    assert decision.assigned_global_track_id == "G-assigned"
    assert decision.local_track_id == "front_rgb_det_0"
    assert "TargetActor_99" not in str(decision.metadata)
    assert "G-other" not in str(decision.metadata)
    assert "object_id" not in str(decision.metadata)
    assert "actor_name" not in str(decision.metadata)


def test_offline_yolo_bytetrack_adapter_outputs_only_local_visual_track_schema() -> None:
    tracks = local_visual_tracks_from_offline_yolo_bytetrack(
        [
            {
                "xyxy": (10.0, 20.0, 50.0, 60.0),
                "track_id": "G-truth-looking-id",
                "class_name": "uav",
                "confidence": 0.92,
                "truth_id": "G1",
                "global_track_id": "G1",
                "object_id": "TargetActor_1",
                "actor_name": "TargetActor_1",
                "timestamp": 4.0,
                "track_age": 6,
            },
            {
                "bbox_xyxy": (80.0, 100.0, 110.0, 130.0),
                "tracker_id": "G-truth-looking-id",
                "label": "uav",
                "score": 0.18,
                "true_global_track_id": "G2",
                "timestamp": 4.0,
                "track_age": 1,
            },
        ],
        resource_id="INT-1",
        camera_id="front_rgb",
    )

    assert [track.local_track_id for track in tracks] == [
        "front_rgb/offline_yolo_bytetrack:track:G-truth-looking-id",
        "front_rgb/offline_yolo_bytetrack:track:G-truth-looking-id#dup1",
    ]
    assert all(not hasattr(track, "global_track_id") for track in tracks)
    assert tracks[0].quality == 0.92
    assert tracks[1].quality == 0.18
    assert tracks[0].mot_history_length == 6
    assert tracks[1].mot_history_length == 1
    np.testing.assert_allclose(tracks[0].center_px, np.array([30.0, 40.0]))


def test_offline_tracker_id_cannot_replace_assigned_global_track_id() -> None:
    from d5_terminal_association import Assignment, CameraModel, GlobalTrack, TerminalAssociator

    camera = CameraModel(
        K=np.array(
            [
                [160.0, 0.0, 320.0],
                [0.0, 160.0, 240.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )
    assigned = GlobalTrack(
        global_track_id="G-assigned",
        position=np.array([0.0, 0.0, 20.0], dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        category="uav",
        timestamp=5.0,
    )
    local_tracks = local_visual_tracks_from_offline_yolo_bytetrack(
        [
            {
                "xyxy": (312.0, 232.0, 328.0, 248.0),
                "track_id": "G-wrong-tracker-id",
                "confidence": 0.94,
                "track_age": 5,
                "truth_id": "G-other",
            }
        ],
        resource_id="INT-1",
        camera_id="front_rgb",
        timestamp=5.0,
    )

    decision = TerminalAssociator().decide(
        Assignment("G-assigned", resource_id="INT-1"),
        [assigned],
        local_tracks,
        camera=camera,
        current_time=5.0,
    )

    assert decision.decision_state == "locked"
    assert decision.assigned_global_track_id == "G-assigned"
    assert decision.local_track_id == "front_rgb/offline_yolo_bytetrack:track:G-wrong-tracker-id"


def test_5v5_overlap_bus_metrics_duplicate_risk_and_lock_accuracy() -> None:
    bus = TerminalObservationBus()
    fixtures = [
        ("Interceptor_Cam_1", "G1", "L1"),
        ("Interceptor_Cam_1", "G2", "L2"),
        ("Interceptor_Cam_1", "G3", "L3"),
        ("Interceptor_Cam_2", "G2", "L1"),
        ("Interceptor_Cam_2", "G3", "L2"),
        ("Interceptor_Cam_2", "G4", "L3"),
    ]
    for resource_id, global_id, local_id in fixtures:
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id=resource_id,
            link_type="interceptor_peer",
            timestamp=10.0,
            terminal_association=_association(global_id, local_id),
            local_track=_local(local_id),
            camera_id="front_rgb",
            frame_id=f"{resource_id}/front_rgb",
            metadata={"truth_global_track_id": global_id},
        )

    summaries = bus.cross_view_associations()
    metrics = compute_terminal_stress_metrics(bus.observations(), summaries)
    by_global = {summary.global_track_id: summary for summary in summaries}

    assert by_global["G2"].supporting_resource_ids == ("Interceptor_Cam_1", "Interceptor_Cam_2")
    assert by_global["G3"].supporting_resource_ids == ("Interceptor_Cam_1", "Interceptor_Cam_2")
    assert metrics.cross_view_overlap_count == 2
    assert metrics.duplicate_terminal_lock_risk is True
    assert metrics.terminal_lock_accuracy == 1.0


def test_degradation_case_outputs_no_secondary_and_distributed_evidence() -> None:
    no_degradation_bus = TerminalObservationBus()
    for index in range(1, 6):
        resource_id = f"Interceptor_Cam_{index}"
        global_id = f"G{index}"
        no_degradation_bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id=resource_id,
            link_type="interceptor_peer",
            timestamp=10.0,
            terminal_association=_association(global_id, f"L{index}"),
            local_track=_local(f"L{index}"),
            camera_id="front_rgb",
            metadata={"truth_global_track_id": global_id},
        )

    no_degradation = summarize_degradation_case(
        no_degradation_bus.observations(),
        no_degradation_bus.cross_view_associations(),
        current_time=10.0,
    )
    assert no_degradation.case_name == "no_degradation"
    assert no_degradation.metrics.terminal_lock_accuracy == 1.0

    secondary_bus = TerminalObservationBus()
    for index in range(2):
        secondary_bus.publish_terminal_association(
            resource_id=f"Interceptor_Cam_{index + 1}",
            source_node_id=f"Interceptor_Cam_{index + 1}",
            link_type="secondary_relay",
            timestamp=10.0,
            terminal_association=_association(
                "G1",
                f"L{index}",
                decision="ambiguous",
                confidence=0.4,
                ambiguity=0.8,
                cue_used=True,
            ),
            local_track=_local(f"L{index}"),
            recon_image_cues=[_secondary_cue("G1", timestamp=9.8)],
            camera_id="front_rgb",
            metadata={"truth_global_track_id": "G2"},
        )

    secondary = summarize_degradation_case(
        secondary_bus.observations(),
        secondary_bus.cross_view_associations(),
        current_time=10.0,
    )
    assert secondary.case_name == "degrade_to_secondary"
    assert secondary.secondary_evidence_available is True
    assert secondary.metrics.ambiguous_fov_event_count == 2

    distributed_bus = TerminalObservationBus()
    for index in range(2):
        distributed_bus.publish_terminal_association(
            resource_id=f"Interceptor_Cam_{index + 1}",
            source_node_id=f"Interceptor_Cam_{index + 1}",
            link_type="interceptor_peer",
            timestamp=10.0,
            terminal_association=_association(
                "G1",
                f"L{index}",
                decision="reacquire",
                confidence=0.0,
                ambiguity=1.0,
            ),
            local_track=_local(f"L{index}"),
            recon_image_cues=[_secondary_cue("G1", timestamp=6.0, expired=True)],
            camera_id="front_rgb",
        )

    distributed = summarize_degradation_case(
        distributed_bus.observations(),
        distributed_bus.cross_view_associations(),
        current_time=10.0,
        max_secondary_cue_age_s=1.0,
    )
    assert distributed.case_name == "degrade_to_distributed"
    assert distributed.secondary_evidence_available is False
    assert distributed.problem_observation_count == 2


def test_multiseed_calibration_readiness_reports_required_and_recommended_fields() -> None:
    selected_pair = {
        "global_track_id": "G1",
        "local_track_id": "L1",
        "projected_px": [320.0, 240.0],
        "bbox_center_px": [320.0, 240.0],
        "pixel_error_px": 0.0,
        "mahalanobis_d2": 0.0,
        "gate_pass": True,
        "measurement_age_s": 0.08,
    }
    ready_bus = TerminalObservationBus()
    ready_bus.publish_terminal_association(
        resource_id="Interceptor_Cam_1",
        source_node_id="Interceptor_Cam_1",
        link_type="airsim_cv_detection",
        timestamp=10.0,
        terminal_association=TerminalAssociation(
            assigned_global_track_id="G1",
            local_track_id="L1",
            association_confidence=0.9,
            ambiguity_score=0.1,
            friend_conflict_state="none",
            decision_state="locked",
            assignment_version=1,
            reason="ready_seed_fixture",
            metadata={
                "selected_pair": selected_pair,
                "candidate_pair_logs": [selected_pair],
                "detector_backend": "ultralytics_yolov8",
                "tracker_backend": "iou_fallback",
                "visual_png_handoff_recommended": False,
                "visual_png_gate_pass": False,
                "visual_png_handoff_blockers": ["duplicate_terminal_lock_risk"],
                "bbox_area_cv": 0.12,
                "bbox_stable": True,
                "duplicate_terminal_lock_risk": True,
            },
        ),
        local_track=_local("L1"),
        camera_id="front_rgb",
        frame_id="Interceptor_Cam_1/front_rgb",
        metadata={
            "source": "simGetDetections",
            "truth_global_track_id": "G1",
        },
    )

    incomplete_bus = TerminalObservationBus()
    incomplete_bus.publish_local_track(
        resource_id="Interceptor_Cam_2",
        source_node_id="Interceptor_Cam_2",
        link_type="airsim_cv_detection",
        timestamp=10.0,
        local_track=LocalVisualTrack(
            local_track_id="L2",
            center_px=np.array([100.0, 120.0], dtype=float),
            bbox=None,
            category="uav",
            quality=0.7,
            mot_history_length=1,
            timestamp=10.0,
        ),
        camera_id="front_rgb",
    )

    readiness = summarize_multiseed_calibration_readiness(
        {
            "seed-ready": ready_bus.observations(),
            "seed-incomplete": incomplete_bus.observations(),
        }
    )
    by_seed = {seed.seed_id: seed for seed in readiness.seeds}

    assert readiness.seed_count == 2
    assert readiness.ready_seed_count == 1
    assert readiness.ready is False
    assert by_seed["seed-ready"].ready is True
    assert by_seed["seed-ready"].geometry_log_count == 1
    assert by_seed["seed-ready"].measurement_age_count == 1
    assert by_seed["seed-ready"].truth_label_count == 1
    assert by_seed["seed-ready"].source_counts["simGetDetections"] == 1
    assert by_seed["seed-ready"].detector_backend_counts["ultralytics_yolov8"] == 1
    assert by_seed["seed-ready"].tracker_backend_counts["iou_fallback"] == 1
    assert by_seed["seed-ready"].handoff_advisory_count == 1
    assert by_seed["seed-ready"].bbox_stability_count == 1
    assert by_seed["seed-ready"].duplicate_terminal_lock_risk_count == 1

    assert by_seed["seed-incomplete"].ready is False
    assert by_seed["seed-incomplete"].missing_required_fields == (
        "local_track_bbox",
        "terminal_association",
        "geometry_gate_log",
        "measurement_age_s",
    )
    assert readiness.missing_required_fields_by_seed["seed-incomplete"] == (
        "local_track_bbox",
        "terminal_association",
        "geometry_gate_log",
        "measurement_age_s",
    )
    assert readiness.metadata["truth_label_scope"] == "offline_metadata_only"
