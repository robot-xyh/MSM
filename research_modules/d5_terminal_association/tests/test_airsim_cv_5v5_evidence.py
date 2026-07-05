from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    AirSimCVScenarioSpec,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociation,
    TerminalObservationBus,
    compute_terminal_stress_metrics,
    local_visual_tracks_from_sim_detections,
    publish_sim_detections_as_local_observations,
    summarize_degradation_case,
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
