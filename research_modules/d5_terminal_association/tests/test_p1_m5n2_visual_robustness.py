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
    TerminalAssociator,
    associate_tracks_to_detections_geometrically,
    register_local_visual_tracks_to_global_tracks,
)


def _camera(*, translation_x_m: float = 0.0) -> CameraModel:
    return CameraModel(
        K=np.array(
            [[100.0, 0.0, 320.0], [0.0, 100.0, 240.0], [0.0, 0.0, 1.0]],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.array([translation_x_m, 0.0, 0.0], dtype=float),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _global(
    global_track_id: str,
    x_m: float = 0.0,
    *,
    velocity_x_m_s: float = 0.0,
    timestamp: float = 0.0,
) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_track_id,
        position=np.array([x_m, 0.0, 20.0], dtype=float),
        velocity=np.array([velocity_x_m_s, 0.0, 0.0], dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        category="uav",
        timestamp=timestamp,
    )


def _local(
    local_track_id: str,
    center_x_px: float,
    timestamp: float,
    *,
    state: str = "measured",
    prediction_age_s: float | None = None,
    camera_id: str = "front",
    bbox: bool = True,
) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_track_id,
        center_px=np.array([center_x_px, 240.0], dtype=float),
        bbox=(center_x_px - 5.0, 235.0, center_x_px + 5.0, 245.0) if bbox else None,
        category="uav",
        quality=0.95,
        mot_history_length=5,
        timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        local_track_state=state,
        prediction_age_s=prediction_age_s,
        detection_source="simGetDetections",
        metadata={"resource_id": "R1", "camera_id": camera_id},
    )


def _assignment(*, plan_version: int = 2) -> Assignment:
    return Assignment(
        "G1",
        resource_id="R1",
        plan_id="PLAN-A",
        plan_version=plan_version,
    )


def test_lock_dropout_one_to_five_frames_expires_and_requires_fresh_recovery() -> None:
    associator = TerminalAssociator()
    assignment = _assignment()
    track = _global("G1")

    locked = associator.decide(
        assignment,
        [track],
        [_local("front:mot-1", 320.0, 0.0)],
        camera=_camera(),
        current_time=0.0,
        arrival_timestamp=0.01,
        camera_id="front",
    )
    missing = [
        associator.decide(
            assignment,
            [track],
            [],
            camera=_camera(),
            current_time=frame * 0.1,
            arrival_timestamp=frame * 0.1,
            camera_id="front",
        )
        for frame in range(1, 6)
    ]

    assert locked.decision_state == "locked"
    assert [item.decision_state for item in missing] == ["reacquire"] * 5
    assert [item.metadata["visual_evidence_fresh"] for item in missing] == [
        True,
        True,
        False,
        False,
        False,
    ]
    assert [item.reason for item in missing[2:]] == ["terminal_visual_evidence_expired"] * 3
    assert all(item.local_track_state == "lost" for item in missing)
    assert all(item.truth_identity_used is False for item in missing)

    first_recovery = associator.decide(
        assignment,
        [track],
        [_local("front:mot-9", 320.5, 0.6)],
        camera=_camera(),
        current_time=0.6,
        arrival_timestamp=0.61,
        camera_id="front",
    )
    second_recovery = associator.decide(
        assignment,
        [track],
        [_local("front:mot-9", 320.0, 0.7)],
        camera=_camera(),
        current_time=0.7,
        arrival_timestamp=0.71,
        camera_id="front",
    )

    assert first_recovery.decision_state == "ambiguous"
    assert first_recovery.reason == "reacquire_candidate_not_temporally_stable"
    assert second_recovery.decision_state == "locked"
    assert second_recovery.assigned_global_track_id == "G1"
    assert second_recovery.local_track_id == "front:mot-9"
    assert track.global_track_id == "G1"


def test_predicted_local_evidence_never_locks_and_expires_without_d5_coast() -> None:
    associator = TerminalAssociator()
    assignment = _assignment()
    track = _global("G1")
    associator.decide(
        assignment,
        [track],
        [_local("front:mot-1", 320.0, 0.0)],
        camera=_camera(),
        current_time=0.0,
        camera_id="front",
    )

    predicted = associator.decide(
        assignment,
        [track],
        [
            _local(
                "front:mot-1",
                321.0,
                0.0,
                state="predicted",
                prediction_age_s=0.3,
            )
        ],
        camera=_camera(),
        current_time=0.3,
        camera_id="front",
    )

    assert predicted.decision_state == "reacquire"
    assert predicted.reason == "terminal_visual_evidence_expired"
    assert predicted.metadata["pre_expiry_reason"] == "predicted_local_track_requires_measured_reacquire"
    assert predicted.metadata["visual_evidence_fail_closed"] is True
    assert predicted.local_track_state == "predicted"
    assert predicted.truth_identity_used is False


def test_stale_plan_is_rejected_without_rebinding_or_poisoning_current_plan() -> None:
    associator = TerminalAssociator()
    track = _global("G1")
    current = _assignment(plan_version=2)
    stale = _assignment(plan_version=1)

    assert associator.decide(
        current,
        [track],
        [_local("front:mot-1", 320.0, 0.0)],
        camera=_camera(),
        current_time=0.0,
        camera_id="front",
    ).decision_state == "locked"

    rejected = associator.decide(
        stale,
        [track],
        [_local("front:mot-stale", 320.0, 0.5)],
        camera=_camera(),
        current_time=0.5,
        camera_id="front",
    )
    resumed = associator.decide(
        current,
        [track],
        [_local("front:mot-1", 320.0, 0.6)],
        camera=_camera(),
        current_time=0.6,
        camera_id="front",
    )

    assert rejected.decision_state == "hold"
    assert rejected.reason == "stale_plan_version_rejected"
    assert rejected.local_track_id is None
    assert rejected.metadata["visual_evidence_fresh"] is False
    assert resumed.decision_state == "locked"
    assert resumed.assigned_global_track_id == "G1"
    assert track.global_track_id == "G1"


def test_camera_scoped_history_does_not_bridge_loss_or_local_ids_between_views() -> None:
    associator = TerminalAssociator()
    assignment = _assignment()
    track = _global("G1")

    front_lock = associator.decide(
        assignment,
        [track],
        [_local("shared-local-id", 320.0, 0.0, camera_id="front")],
        camera=_camera(),
        current_time=0.0,
        camera_id="front",
    )
    front_loss = associator.decide(
        assignment,
        [track],
        [],
        camera=_camera(),
        current_time=0.1,
        camera_id="front",
    )
    belly_first_frame = associator.decide(
        assignment,
        [track],
        [_local("shared-local-id", 320.0, 0.1, camera_id="belly")],
        camera=_camera(),
        current_time=0.1,
        camera_id="belly",
    )

    assert front_lock.decision_state == "locked"
    assert front_loss.decision_state == "reacquire"
    assert belly_first_frame.decision_state == "locked"
    assert belly_first_frame.metadata["previous_locked_local_track_id"] is None


def test_same_camera_crossing_uses_geometry_hungarian_and_not_local_truth_ids() -> None:
    before = associate_tracks_to_detections_geometrically(
        [_global("G1", -1.0), _global("G2", 1.0)],
        [
            _local("front:anonymous-A", 315.0, 0.0),
            _local("front:anonymous-B", 325.0, 0.0),
        ],
        _camera(),
        timestamp=0.0,
        arrival_timestamp=0.01,
        frame_id="R1/front",
    )
    after_tracks = [_global("G1", 1.0), _global("G2", -1.0)]
    after_locals = [
        _local("front:anonymous-A", 325.0, 1.0),
        _local("front:anonymous-B", 315.0, 1.0),
    ]

    after = associate_tracks_to_detections_geometrically(
        after_tracks,
        after_locals,
        _camera(),
        timestamp=1.0,
        arrival_timestamp=1.01,
        frame_id="R1/front",
    )

    assert before.assignments == after.assignments == {
        "G1": "front:anonymous-A",
        "G2": "front:anonymous-B",
    }
    assert before.ambiguous_count == after.ambiguous_count == 0
    assert all(record["truth_identity_used"] is False for record in after.to_log_records())


def test_cross_camera_partial_overlap_registers_only_shared_targets_as_multi_view() -> None:
    tracks = [
        _global("G1", -6.0),
        _global("G2", -2.0),
        _global("G3", 2.0),
        _global("G4", 6.0),
    ]
    bindings = [GlobalTrackBinding(global_track_id=track.global_track_id) for track in tracks]
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=tracks,
        bindings=bindings,
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="R1",
                camera_id="front",
                camera=_camera(),
                local_tracks=(
                    _local("front:a", 290.0, 1.0),
                    _local("front:b", 310.0, 1.0),
                    _local("front:c", 330.0, 1.0),
                ),
                timestamp=1.0,
            ),
            CameraLocalTrackBatch(
                resource_id="R2",
                camera_id="front",
                camera=_camera(),
                local_tracks=(
                    _local("peer:b", 310.0, 1.02),
                    _local("peer:c", 330.0, 1.02),
                    _local("peer:d", 350.0, 1.02),
                ),
                timestamp=1.02,
            ),
        ],
        current_time=1.02,
        max_binding_age_s=None,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    by_global = {item.global_track_id: item for item in result.cross_view_associations}
    assert by_global["G1"].supporting_resource_ids == ("R1",)
    assert by_global["G2"].supporting_resource_ids == ("R1", "R2")
    assert by_global["G3"].supporting_resource_ids == ("R1", "R2")
    assert by_global["G4"].supporting_resource_ids == ("R2",)
    assert all(candidate.offline_truth_global_id is None for candidate in result.candidates)


def test_extrinsic_drift_and_timestamp_bias_fail_geometry_gate() -> None:
    static_track = _global("G1", 0.0, timestamp=10.0)
    binding = GlobalTrackBinding(global_track_id="G1", timestamp=10.0)
    local = _local("recon:anonymous", 320.0, 10.0, bbox=False)

    healthy = register_local_visual_tracks_to_global_tracks(
        global_tracks=[static_track],
        bindings=[binding],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="RECON",
                camera_id="eo",
                camera=_camera(),
                local_tracks=(local,),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )
    drifted = register_local_visual_tracks_to_global_tracks(
        global_tracks=[static_track],
        bindings=[binding],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="RECON",
                camera_id="eo",
                camera=_camera(translation_x_m=4.0),
                local_tracks=(local,),
                timestamp=10.0,
            )
        ],
        current_time=10.0,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    moving_track = _global("G1", 0.0, velocity_x_m_s=10.0, timestamp=10.0)
    time_biased = register_local_visual_tracks_to_global_tracks(
        global_tracks=[moving_track],
        bindings=[binding],
        camera_batches=[
            CameraLocalTrackBatch(
                resource_id="RECON",
                camera_id="eo",
                camera=_camera(),
                local_tracks=(local,),
                timestamp=10.5,
            )
        ],
        current_time=10.5,
        max_binding_age_s=None,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )

    assert healthy.cross_view_associations
    assert not drifted.cross_view_associations
    assert drifted.rejection_reason_counts["geometry_gate_rejected"] == 1
    assert not time_biased.cross_view_associations
    assert time_biased.rejection_reason_counts["geometry_gate_rejected"] == 1
