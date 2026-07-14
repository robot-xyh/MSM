from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    Assignment,
    CameraLocalTrackBatch,
    CameraModel,
    GlobalTrack,
    GlobalTrackBinding,
    LocalVisualTrack,
    RegistrationStabilityConfig,
    STABILITY_WINDOW_FAILED_REASON,
    adaptive_pixel_covariance_px,
    binding_from_assignment,
    register_local_visual_tracks_to_global_tracks,
    summarize_secondary_visual_coverage_funnel,
)


def test_assignment_to_registration_binding_preserves_per_primary_contract() -> None:
    assignment = Assignment(
        "G1",
        assignment_version=7,
        resource_id="INT-1",
        plan_id="plan-7",
        plan_version=7,
        coalition_id="coalition-G1",
        coalition_version=3,
        member_role="primary",
        required_resource_count=2,
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
    )

    binding = binding_from_assignment(assignment, camera_id="front_rgb")

    assert binding.global_track_id == assignment.assigned_global_track_id
    assert binding.terminal_authorization_scope == "per_primary"
    assert binding.arrival_coordination_required is False


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
        measurement_cov=np.diag([2.0, 2.0]),
    )


def _track(global_id: str, x_m: float, *, timestamp: float = 10.0) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_id,
        position=np.array([x_m, 0.0, 20.0], dtype=float),
        covariance=np.diag([0.01, 0.01, 0.01]),
        category="uav",
        timestamp=timestamp,
        track_version=4,
    )


def _local(
    local_id: str,
    center: tuple[float, float],
    *,
    timestamp: float = 10.0,
    bbox_size_px: float | None = 10.0,
) -> LocalVisualTrack:
    u, v = center
    bbox = None
    if bbox_size_px is not None:
        half = bbox_size_px * 0.5
        bbox = (u - half, v - half, u + half, v + half)
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array([u, v], dtype=float),
        bbox=bbox,
        category="uav",
        quality=0.95,
        mot_history_length=5,
        timestamp=timestamp,
    )


def _binding(global_id: str, *, timestamp: float = 10.0) -> GlobalTrackBinding:
    return GlobalTrackBinding(
        global_track_id=global_id,
        binding_source="d2_d3_current_binding",
        timestamp=timestamp,
        assignment_version=4,
    )


def test_secondary_detect_registers_to_existing_global_track_and_adds_cross_view_support() -> None:
    tracks = [_track("G1", 0.0), _track("G2", 4.0)]
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=tracks,
        bindings=[_binding("G1"), _binding("G2")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="INT-1",
                camera_id="front_rgb",
                camera=_camera(),
                local_tracks=(_local("front-L1", (320.0, 240.0)),),
                timestamp=10.0,
                source_node_id="INT-1",
                link_type="interceptor_peer",
            ),
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("recon-L1", (320.0, 240.0)),),
                timestamp=10.0,
                source_node_id="mobile-recon-1",
                link_type="secondary_relay",
            ),
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    registered = [candidate for candidate in result.candidates if candidate.selected]
    assert [candidate.global_track_id for candidate in registered] == ["G1", "G1"]
    assert all(candidate.reject_reasons == ("registered_to_global_track",) for candidate in registered)
    assert result.rejection_reason_counts["registered_to_global_track"] == 2

    by_global_id = {item.global_track_id: item for item in result.cross_view_associations}
    assert by_global_id["G1"].supporting_resource_ids == ("INT-1", "mobile-recon-1")
    assert by_global_id["G1"].decision_states == ("registered", "registered")
    assert by_global_id["G1"].duplicate_terminal_lock_risk is False
    assert result.stable_cross_view_associations
    assert all(candidate.stable_cross_view_support for candidate in registered)


def test_registration_logs_pose_source_bbox_area_and_offline_truth_without_using_truth_for_binding() -> None:
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G-assigned", 0.0)],
        bindings=[_binding("G-assigned")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("local-1", (320.0, 240.0), bbox_size_px=40.0),),
                timestamp=10.0,
                metadata={
                    "airsim_camera_pose": {
                        "position_ned": [0.0, 0.0, -200.0],
                        "orientation_quat_xyzw": [0.0, 0.0, 0.0, 1.0],
                    },
                    "truth_global_track_id_by_local_track_id": {"local-1": "G-truth-other"},
                },
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    candidate = next(candidate for candidate in result.candidates if candidate.selected)
    assert candidate.global_track_id == "G-assigned"
    assert candidate.offline_truth_global_id == "G-truth-other"
    assert candidate.camera_pose_source == "airsim_camera_pose"
    assert candidate.bbox_area_px == 1600.0
    assert candidate.metadata["gate_pass"] is True
    assert candidate.outcome == "registered_to_global_track"
    assert candidate.metadata["detect_to_global_candidate"] is True
    assert candidate.metadata["detect_registration_outcome"] == "registered_to_global_track"
    assert candidate.metadata["projection_valid"] is True
    assert candidate.metadata["reprojection_error"] == 0.0
    assert candidate.metadata["measurement_timestamp"] == 10.0
    assert candidate.metadata["measurement_age_s"] == 0.0
    assert candidate.metadata["covariance_px"] is not None
    assert candidate.metadata["calibration_health"] == "healthy"
    assert candidate.metadata["drift_warning"] is False
    assert candidate.metadata["offline_truth_global_id"] == "G-truth-other"
    assert result.observations[0].terminal_association.assigned_global_track_id == "G-assigned"
    assert (
        result.observations[0].terminal_association.metadata["detect_registration_outcome"]
        == "registered_to_global_track"
    )
    assert result.observations[0].terminal_association.metadata["reprojection_error"] == 0.0
    assert result.observations[0].terminal_association.metadata["calibration_health"] == "healthy"
    assert result.metadata["calibration_health_counts"]["healthy"] == 1
    assert result.metadata["projection_valid_count"] == 1
    assert result.metadata["drift_warning_count"] == 0
    assert "G-truth-other" not in str(result.observations[0].terminal_association.metadata)


def test_adaptive_pixel_covariance_uses_bbox_area_and_relaxes_secondary_gate() -> None:
    covariance = adaptive_pixel_covariance_px(40000.0, (640, 480))
    assert np.allclose(np.diag(covariance), [8100.0, 8100.0])

    with_area = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G1", 0.0)],
        bindings=[_binding("G1")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("wide-bbox", (340.0, 240.0), bbox_size_px=20.0),),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )
    without_area = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G1", 0.0)],
        bindings=[_binding("G1")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("no-bbox", (340.0, 240.0), bbox_size_px=None),),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    assert any(candidate.selected for candidate in with_area.candidates)
    assert with_area.candidates[0].covariance_px is not None
    assert with_area.candidates[0].covariance_px[0, 0] > 600.0
    assert all(not candidate.selected for candidate in without_area.candidates)


def test_adaptive_pixel_covariance_preserves_scale_between_1080p_and_4k() -> None:
    covariance_1080p = adaptive_pixel_covariance_px(120.0 * 60.0, (1920, 1080))
    covariance_4k = adaptive_pixel_covariance_px(240.0 * 120.0, (3840, 2160))

    np.testing.assert_allclose(covariance_4k, covariance_1080p * 4.0)


def test_default_registration_requires_two_gate_passes_in_three_frame_window_for_stable_support() -> None:
    batches = [
        CameraLocalTrackBatch(
            resource_id="mobile-recon-1",
            camera_id="eo_rgb",
            camera=_camera(),
            local_tracks=(_local("tracklet-1", (320.0, 240.0), timestamp=float(timestamp)),),
            frame_id=f"frame-{timestamp}",
            timestamp=float(timestamp),
        )
        for timestamp in (10, 11, 12)
    ]
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G1", 0.0, timestamp=10.0)],
        bindings=[_binding("G1", timestamp=10.0)],
        camera_batches=batches,
        current_time=None,
        max_binding_age_s=None,
    )

    selected = [candidate for candidate in result.candidates if candidate.selected]
    assert len(selected) == 3
    assert [candidate.stable_cross_view_support for candidate in selected] == [False, True, True]
    assert [candidate.decision_state for candidate in selected] == ["candidate", "registered", "registered"]
    assert result.rejection_reason_counts[STABILITY_WINDOW_FAILED_REASON] == 1
    assert result.rejection_reason_counts["registered_to_global_track"] == 2
    assert result.metadata["stable_registered_candidate_count"] == 2
    assert result.stable_cross_view_associations


def test_missing_binding_reports_no_global_binding_and_offline_truth_only() -> None:
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G1", 0.0)],
        bindings=[],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("offline-local", (320.0, 240.0)),),
                timestamp=10.0,
                metadata={"truth_global_track_id_by_local_track_id": {"offline-local": "G1"}},
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    assert result.cross_view_associations == ()
    assert result.candidates[0].global_track_id is None
    assert result.candidates[0].reject_reasons == (
        "no_global_binding",
        "secondary_detect_offline_only",
    )
    assert result.rejection_reason_counts["no_global_binding"] == 1
    assert result.rejection_reason_counts["secondary_detect_offline_only"] == 1

    funnel = summarize_secondary_visual_coverage_funnel(observations=result.observations)
    assert funnel.rejection_reason_counts["no_global_binding"] == 1
    assert funnel.rejection_reason_counts["secondary_detect_offline_only"] == 1


def test_stale_binding_and_geometry_gate_rejections_are_separate_reasons() -> None:
    stale = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G1", 0.0)],
        bindings=[_binding("G1", timestamp=1.0)],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("stale-local", (320.0, 240.0)),),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        max_binding_age_s=1.0,
    )
    gated = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G1", 0.0)],
        bindings=[_binding("G1")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("far-local", (500.0, 240.0)),),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    assert stale.candidates[0].reject_reasons == ("stale_or_missing_recon_cue",)
    assert stale.rejection_reason_counts["stale_or_missing_recon_cue"] == 1
    assert all(not candidate.selected for candidate in gated.candidates)
    assert gated.rejection_reason_counts["geometry_gate_rejected"] == 1

    funnel = summarize_secondary_visual_coverage_funnel(observations=gated.observations)
    assert funnel.rejection_reason_counts["geometry_gate_rejected"] == 1
    assert funnel.rejection_reason_counts["no_global_binding"] == 0


def test_projection_invalid_is_reported_separately_from_geometry_gate_rejection() -> None:
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G-outside", 200.0)],
        bindings=[_binding("G-outside")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("outside-local", (320.0, 240.0)),),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    candidate = result.candidates[0]
    assert candidate.selected is False
    assert candidate.projection_valid is False
    assert candidate.reject_reasons == ("projection_invalid",)
    assert candidate.outcome == "projection_invalid"
    assert candidate.metadata["projection_reason"] == "outside_image"
    assert result.rejection_reason_counts["projection_invalid"] == 1
    assert result.rejection_reason_counts["geometry_gate_rejected"] == 0

    funnel = summarize_secondary_visual_coverage_funnel(observations=result.observations)
    assert funnel.rejection_reason_counts["projection_invalid"] == 1
    assert funnel.rejection_reason_counts["geometry_gate_rejected"] == 0


def test_truth_metadata_and_tracker_like_ids_do_not_replace_global_binding() -> None:
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=[_track("G-assigned", 0.0)],
        bindings=[_binding("G-assigned")],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="mobile-recon-1",
                camera_id="eo_rgb",
                camera=_camera(),
                local_tracks=(_local("G-other-looking-tracker-id", (320.0, 240.0)),),
                timestamp=10.0,
                metadata={
                    "object_id": "TargetActor_99",
                    "truth_global_track_id_by_local_track_id": {
                        "G-other-looking-tracker-id": "G-other"
                    },
                },
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    registered = [candidate for candidate in result.candidates if candidate.selected]
    assert len(registered) == 1
    assert registered[0].global_track_id == "G-assigned"
    assert result.observations[0].terminal_association.assigned_global_track_id == "G-assigned"
    assert "G-other" not in str(result.observations[0].metadata)
    assert "TargetActor_99" not in str(result.observations[0].terminal_association.metadata)


def test_registration_scales_with_input_counts_not_2v2_or_5v5() -> None:
    x_positions = (-4.0, 0.0, 4.0)
    centers = ((300.0, 240.0), (320.0, 240.0), (340.0, 240.0))
    tracks = [_track(f"G{index}", x_m) for index, x_m in enumerate(x_positions, start=1)]
    batches = []
    for resource_index in range(1, 4):
        batches.append(
            CameraLocalTrackBatch(
                resource_id=f"R{resource_index}",
                camera_id="front_rgb",
                camera=_camera(),
                local_tracks=tuple(
                    _local(f"R{resource_index}-L{target_index}", center)
                    for target_index, center in enumerate(centers, start=1)
                ),
                timestamp=10.0,
            )
        )

    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=tracks,
        bindings=[_binding(track.global_track_id) for track in tracks],
        camera_batches=batches,
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    registered = [candidate for candidate in result.candidates if candidate.selected]
    assert len(registered) == 9
    by_global_id = {item.global_track_id: item for item in result.cross_view_associations}
    assert set(by_global_id) == {"G1", "G2", "G3"}
    assert all(item.support_count == 3 for item in by_global_id.values())
