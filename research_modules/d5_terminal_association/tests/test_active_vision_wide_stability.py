from __future__ import annotations

import pytest

from d5_terminal_association.active_vision_contracts import (
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionSafetyConfigV1,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    DeterministicLookAtScanPolicy,
    FriendlyObservationReservation,
)
from d5_terminal_association.active_vision_corpus_audit import (
    active_vision_camera_role,
)
from d5_terminal_association.active_vision_learning import (
    active_vision_candidate_batch,
)


def _snapshot(
    now: float,
    *,
    assignments_by_camera: dict[str, tuple[str, ...]] | None = None,
    plan_version: int = 4,
    coalition_version: int = 7,
    communication_version: int = 9,
    communication_healthy: bool = True,
    evidence_age_s: float = 0.05,
    association_confidence: float = 0.95,
    visibility_by_target: dict[str, float] | None = None,
    occlusion_fraction: float = 0.1,
    in_fov: bool = True,
    include_projections: bool = True,
    current_fov_by_camera: dict[str, ActiveVisionFovMode] | None = None,
    busy_cameras: frozenset[str] = frozenset(),
    slew_unavailable_cameras: frozenset[str] = frozenset(),
    reservations: tuple[FriendlyObservationReservation, ...] = (),
) -> ActiveVisionSnapshotV1:
    assignments_by_camera = assignments_by_camera or {"CAM-0": ("GT-A",)}
    visibility_by_target = visibility_by_target or {}
    current_fov_by_camera = current_fov_by_camera or {}
    track_ids = tuple(
        sorted({target for targets in assignments_by_camera.values() for target in targets})
    )
    tracks = tuple(
        ActiveVisionTrackReference(
            global_track_id=track_id,
            track_version=3,
            measurement_timestamp=now - evidence_age_s,
        )
        for track_id in track_ids
    )
    cameras = tuple(
        ActiveVisionCameraState(
            camera_id=camera_id,
            resource_id=f"RES-{camera_id}",
            state_timestamp=now - 0.01,
            yaw_deg=0.0,
            pitch_deg=0.0,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-90.0, 90.0),
            pitch_limits_deg=(-45.0, 30.0),
            max_yaw_rate_deg_s=60.0,
            max_pitch_rate_deg_s=45.0,
            max_slew_deg_s=70.0,
            current_fov_mode=current_fov_by_camera.get(
                camera_id, ActiveVisionFovMode.WIDE
            ),
            slew_available=camera_id not in slew_unavailable_cameras,
            action_in_progress_until=(now + 0.5 if camera_id in busy_cameras else None),
        )
        for camera_id in sorted(assignments_by_camera)
    )
    assignments = tuple(
        ActiveVisionAssignmentReference(
            resource_id=f"RES-{camera_id}",
            camera_id=camera_id,
            global_track_id=track_id,
        )
        for camera_id, target_ids in sorted(assignments_by_camera.items())
        for track_id in target_ids
    )
    projections = (
        tuple(
            ActiveVisionProjectionEvidence(
                camera_id=camera_id,
                global_track_id=track_id,
                measurement_timestamp=now - evidence_age_s,
                arrival_timestamp=now - min(0.02, evidence_age_s),
                yaw_error_deg=3.0,
                pitch_error_deg=-1.0,
                projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
                visibility_probability=visibility_by_target.get(track_id, 0.9),
                occlusion_fraction=occlusion_fraction,
                association_confidence=association_confidence,
                in_fov=in_fov,
            )
            for camera_id, target_ids in sorted(assignments_by_camera.items())
            for track_id in target_ids
        )
        if include_projections
        else ()
    )
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=now,
        plan=ActiveVisionPlanReference(
            plan_version=plan_version,
            coalition_version=coalition_version,
            assignments=assignments,
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=communication_version,
            plan_version=plan_version,
            coalition_version=coalition_version,
            update_timestamp=now - 0.01,
            healthy=communication_healthy,
            peer_reservations=reservations,
        ),
        tracks=tracks,
        cameras=cameras,
        projections=projections,
    )


def _select(
    policy: DeterministicLookAtScanPolicy,
    snapshot: ActiveVisionSnapshotV1,
    *,
    camera_id: str = "CAM-0",
    expected_plan_version: int | None = None,
):
    return policy.select_action(
        snapshot,
        camera_id=camera_id,
        current_timestamp=snapshot.snapshot_timestamp,
        expected_plan_version=(
            snapshot.plan.plan_version
            if expected_plan_version is None
            else expected_plan_version
        ),
        expected_coalition_version=snapshot.plan.coalition_version,
        expected_communication_version=snapshot.communication.communication_version,
    )


def test_default_gate_keeps_first_two_stable_frames_wide_then_zooms() -> None:
    policy = DeterministicLookAtScanPolicy()

    first = _select(policy, _snapshot(10.0))
    second = _select(policy, _snapshot(10.1))
    duplicate_second = _select(policy, _snapshot(10.1))
    third = _select(policy, _snapshot(10.2))

    assert policy.config.zoom_stability_window_frames == 3
    assert first.intent is ActiveVisionIntent.OBSERVE_TARGET
    assert first.fov_mode is ActiveVisionFovMode.WIDE
    assert second.fov_mode is ActiveVisionFovMode.WIDE
    assert duplicate_second.fov_mode is ActiveVisionFovMode.WIDE
    assert third.fov_mode is ActiveVisionFovMode.ZOOM


def test_configurable_two_frame_gate_and_one_frame_compatibility() -> None:
    two_frame = DeterministicLookAtScanPolicy(
        ActiveVisionSafetyConfigV1(zoom_stability_window_frames=2)
    )
    immediate = DeterministicLookAtScanPolicy(
        ActiveVisionSafetyConfigV1(zoom_stability_window_frames=1)
    )

    assert _select(two_frame, _snapshot(10.0)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(two_frame, _snapshot(10.1)).fov_mode is ActiveVisionFovMode.ZOOM
    assert _select(immediate, _snapshot(10.0)).fov_mode is ActiveVisionFovMode.ZOOM


def test_plan_and_target_changes_restart_the_stability_window() -> None:
    config = ActiveVisionSafetyConfigV1(zoom_stability_window_frames=2)
    plan_policy = DeterministicLookAtScanPolicy(config)
    coalition_policy = DeterministicLookAtScanPolicy(config)
    target_policy = DeterministicLookAtScanPolicy(config)

    assert _select(plan_policy, _snapshot(10.0, plan_version=4)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(plan_policy, _snapshot(10.1, plan_version=5)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(plan_policy, _snapshot(10.2, plan_version=5)).fov_mode is ActiveVisionFovMode.ZOOM

    assert _select(coalition_policy, _snapshot(15.0, coalition_version=7)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(coalition_policy, _snapshot(15.1, coalition_version=8)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(coalition_policy, _snapshot(15.2, coalition_version=8)).fov_mode is ActiveVisionFovMode.ZOOM

    assert _select(target_policy, _snapshot(20.0)).fov_mode is ActiveVisionFovMode.WIDE
    changed = _snapshot(20.1, assignments_by_camera={"CAM-0": ("GT-B",)})
    assert _select(target_policy, changed).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(
        target_policy,
        _snapshot(20.2, assignments_by_camera={"CAM-0": ("GT-B",)}),
    ).fov_mode is ActiveVisionFovMode.ZOOM


def test_stale_projection_and_time_regression_reset_before_zoom() -> None:
    config = ActiveVisionSafetyConfigV1(zoom_stability_window_frames=2)
    stale_policy = DeterministicLookAtScanPolicy(config)
    time_policy = DeterministicLookAtScanPolicy(config)

    assert _select(stale_policy, _snapshot(10.0)).fov_mode is ActiveVisionFovMode.WIDE
    stale = _select(stale_policy, _snapshot(10.1, evidence_age_s=1.0))
    assert stale.intent is ActiveVisionIntent.REACQUIRE
    assert stale.fov_mode is ActiveVisionFovMode.WIDE
    assert _select(stale_policy, _snapshot(10.2)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(stale_policy, _snapshot(10.3)).fov_mode is ActiveVisionFovMode.ZOOM

    assert _select(time_policy, _snapshot(20.0)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(time_policy, _snapshot(20.1)).fov_mode is ActiveVisionFovMode.ZOOM
    regressed = _select(time_policy, _snapshot(20.05))
    assert regressed.intent is ActiveVisionIntent.SEARCH_SECTOR
    assert regressed.fov_mode is ActiveVisionFovMode.WIDE
    assert _select(time_policy, _snapshot(20.2)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(time_policy, _snapshot(20.3)).fov_mode is ActiveVisionFovMode.ZOOM


def test_reacquire_search_and_hold_all_select_wide_when_available() -> None:
    reacquire = _select(
        DeterministicLookAtScanPolicy(),
        _snapshot(10.0, association_confidence=0.2),
    )
    search = _select(
        DeterministicLookAtScanPolicy(),
        _snapshot(10.0, include_projections=False),
    )
    invalid_projection = _select(
        DeterministicLookAtScanPolicy(),
        _snapshot(10.0, in_fov=False),
    )
    hold = _select(
        DeterministicLookAtScanPolicy(),
        _snapshot(
            10.0,
            busy_cameras=frozenset({"CAM-0"}),
        ),
    )

    assert (reacquire.intent, reacquire.fov_mode) == (
        ActiveVisionIntent.REACQUIRE,
        ActiveVisionFovMode.WIDE,
    )
    assert (search.intent, search.fov_mode) == (
        ActiveVisionIntent.SEARCH_SECTOR,
        ActiveVisionFovMode.WIDE,
    )
    assert (invalid_projection.intent, invalid_projection.fov_mode) == (
        ActiveVisionIntent.REACQUIRE,
        ActiveVisionFovMode.WIDE,
    )
    assert (hold.intent, hold.fov_mode) == (
        ActiveVisionIntent.HOLD,
        ActiveVisionFovMode.WIDE,
    )


@pytest.mark.parametrize(
    ("camera_id", "expected_role", "busy", "slew_unavailable"),
    (
        ("INTERCEPTOR-CAM-0", "interceptor", True, False),
        ("INTERCEPTOR-CAM-1", "interceptor", False, True),
        ("RECON-CAM-0", "recon", True, False),
        ("RECON-CAM-1", "recon", False, True),
    ),
)
def test_runtime_camera_role_busy_or_unavailable_produces_truth_free_hold(
    camera_id: str,
    expected_role: str,
    busy: bool,
    slew_unavailable: bool,
) -> None:
    snapshot = _snapshot(
        10.0,
        assignments_by_camera={camera_id: ("GT-A",)},
        busy_cameras=frozenset({camera_id}) if busy else frozenset(),
        slew_unavailable_cameras=(
            frozenset({camera_id}) if slew_unavailable else frozenset()
        ),
    )

    action = _select(
        DeterministicLookAtScanPolicy(),
        snapshot,
        camera_id=camera_id,
    )

    assert (
        active_vision_camera_role(snapshot.camera(camera_id).resource_id)
        == expected_role
    )
    assert action.intent is ActiveVisionIntent.HOLD
    assert action.target_global_track_id is None
    assert action.search_sector_deg is None
    assert action.reason == "rule_hold:gimbal_unavailable_or_busy"
    assert snapshot.assigned_target_ids(camera_id) == ("GT-A",)
    candidates = active_vision_candidate_batch(snapshot, camera_id=camera_id)
    assert sum(
        candidate.action_key == action.action_key
        for candidate in candidates.actions
    ) == 1


def test_recon_cue_loss_with_assignment_selects_search_without_rebinding() -> None:
    camera_id = "RECON-CAM-0"
    snapshot = _snapshot(
        10.0,
        assignments_by_camera={camera_id: ("GT-A",)},
        include_projections=False,
    )

    action = _select(
        DeterministicLookAtScanPolicy(),
        snapshot,
        camera_id=camera_id,
    )

    assert active_vision_camera_role(snapshot.camera(camera_id).resource_id) == "recon"
    assert snapshot.assigned_target_ids(camera_id) == ("GT-A",)
    assert snapshot.projection(camera_id, "GT-A") is None
    assert action.intent is ActiveVisionIntent.SEARCH_SECTOR
    assert action.target_global_track_id is None
    assert action.search_sector_deg is not None
    assert action.reason == "rule_scan:rule_no_usable_assigned_projection"
    candidates = active_vision_candidate_batch(snapshot, camera_id=camera_id)
    assert sum(
        candidate.action_key == action.action_key
        for candidate in candidates.actions
    ) == 1


def test_version_and_communication_failures_reset_and_fail_closed() -> None:
    config = ActiveVisionSafetyConfigV1(zoom_stability_window_frames=2)
    policy = DeterministicLookAtScanPolicy(config)

    assert _select(policy, _snapshot(10.0)).fov_mode is ActiveVisionFovMode.WIDE
    stale = _select(policy, _snapshot(10.1), expected_plan_version=5)
    unhealthy = _select(policy, _snapshot(10.2, communication_healthy=False))

    assert stale.intent is ActiveVisionIntent.SEARCH_SECTOR
    assert stale.fov_mode is ActiveVisionFovMode.WIDE
    assert "stale_plan_version" in stale.reason
    assert unhealthy.intent is ActiveVisionIntent.SEARCH_SECTOR
    assert unhealthy.fov_mode is ActiveVisionFovMode.WIDE
    assert "communication_unhealthy" in unhealthy.reason
    assert _select(policy, _snapshot(10.3)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(policy, _snapshot(10.4)).fov_mode is ActiveVisionFovMode.ZOOM


def test_ambiguous_binding_and_friend_reservation_reset_the_gate() -> None:
    config = ActiveVisionSafetyConfigV1(zoom_stability_window_frames=2)
    ambiguous_policy = DeterministicLookAtScanPolicy(config)
    conflict_policy = DeterministicLookAtScanPolicy(config)
    ambiguous = _snapshot(
        10.0,
        assignments_by_camera={"CAM-0": ("GT-A", "GT-B")},
        visibility_by_target={"GT-A": 0.90, "GT-B": 0.89},
    )

    ambiguous_action = _select(ambiguous_policy, ambiguous)
    assert ambiguous_action.intent is ActiveVisionIntent.REACQUIRE
    assert ambiguous_action.fov_mode is ActiveVisionFovMode.WIDE

    clear_assignments = {"CAM-0": ("GT-A", "GT-B")}
    clear_visibility = {"GT-A": 0.95, "GT-B": 0.40}
    assert _select(
        ambiguous_policy,
        _snapshot(10.1, assignments_by_camera=clear_assignments, visibility_by_target=clear_visibility),
    ).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(
        ambiguous_policy,
        _snapshot(10.2, assignments_by_camera=clear_assignments, visibility_by_target=clear_visibility),
    ).fov_mode is ActiveVisionFovMode.ZOOM

    assert _select(conflict_policy, _snapshot(20.0)).fov_mode is ActiveVisionFovMode.WIDE
    reservation = FriendlyObservationReservation(
        owner_resource_id="RES-PEER",
        camera_id="CAM-PEER",
        communication_version=9,
        coalition_version=7,
        expires_timestamp=22.0,
        global_track_id="GT-A",
    )
    conflict = _select(conflict_policy, _snapshot(20.1, reservations=(reservation,)))
    assert conflict.intent is ActiveVisionIntent.SEARCH_SECTOR
    assert conflict.fov_mode is ActiveVisionFovMode.WIDE
    assert _select(conflict_policy, _snapshot(20.2)).fov_mode is ActiveVisionFovMode.WIDE
    assert _select(conflict_policy, _snapshot(20.3)).fov_mode is ActiveVisionFovMode.ZOOM


def test_stability_state_is_isolated_per_camera() -> None:
    policy = DeterministicLookAtScanPolicy(
        ActiveVisionSafetyConfigV1(zoom_stability_window_frames=2)
    )
    assignments = {"CAM-0": ("GT-A",), "CAM-1": ("GT-B",)}

    assert _select(policy, _snapshot(10.0, assignments_by_camera=assignments), camera_id="CAM-0").fov_mode is ActiveVisionFovMode.WIDE
    assert _select(policy, _snapshot(10.1, assignments_by_camera=assignments), camera_id="CAM-0").fov_mode is ActiveVisionFovMode.ZOOM
    assert _select(policy, _snapshot(10.1, assignments_by_camera=assignments), camera_id="CAM-1").fov_mode is ActiveVisionFovMode.WIDE
    assert _select(policy, _snapshot(10.2, assignments_by_camera=assignments), camera_id="CAM-1").fov_mode is ActiveVisionFovMode.ZOOM


def test_snapshot_indexes_preserve_camera_assignment_and_projection_semantics() -> None:
    snapshot = _snapshot(10.0)

    camera = snapshot.camera("CAM-0")
    projection = snapshot.projection("CAM-0", "GT-A")

    assert camera.camera_id == "CAM-0"
    assert projection is not None
    assert projection.global_track_id == "GT-A"
    assert snapshot.assigned_target_ids("CAM-0") == ("GT-A",)
    assert snapshot.camera("CAM-0") is camera
    assert snapshot.projection("CAM-0", "GT-A") is projection
    assert snapshot.assigned_target_ids("CAM-UNKNOWN") == ()
