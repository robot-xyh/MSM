from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from d5_terminal_association import (
    Assignment,
    AssociationConfig,
    CameraModel,
    GlobalTrack,
    IdentityChecker,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociator,
)


def make_camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [100.0, 0.0, 320.0],
                [0.0, 100.0, 240.0],
                [0.0, 0.0, 1.0],
            ]
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def make_track(
    global_id: str = "G-1",
    position: tuple[float, float, float] = (0.0, 0.0, 10.0),
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    category: str = "uav",
) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_id,
        position=np.array(position),
        velocity=np.array(velocity),
        covariance=np.diag([0.01, 0.01, 0.01]),
        category=category,
        timestamp=0.0,
    )


def make_local(
    local_id: str,
    center: tuple[float, float],
    category: str = "uav",
    bearing_rate: tuple[float, float] = (0.0, 0.0),
) -> LocalVisualTrack:
    u, v = center
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array(center),
        bbox=(u - 5.0, v - 5.0, u + 5.0, v + 5.0),
        bearing_rate=np.array(bearing_rate),
        category=category,
        quality=0.95,
        mot_history_length=5,
    )


def test_projection_covariance_and_mahalanobis_gate() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    track = make_track()
    projections = associator.project_tracks_to_image([track], camera)
    projection = projections["G-1"]

    assert projection.valid
    np.testing.assert_allclose(projection.pixel, np.array([320.0, 240.0]), atol=1e-6)
    assert projection.covariance_px.shape == (2, 2)

    near = make_local("near", (322.0, 240.0))
    far = make_local("far", (380.0, 240.0))
    result = associator.build_cost_matrix(projections, [near, far])

    assert result.costs[0, 0] < associator.config.gate_chi2
    assert result.costs[0, 1] == associator.config.cost_inf


def test_decide_locks_assigned_projection_not_nearest_local_track() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned", (2.0, 0.0, 10.0))
    distractor = make_track("G-other", (0.0, 0.0, 10.0))
    locals_in_view = [
        make_local("nearest_to_center", (320.0, 240.0)),
        make_local("assigned_visual", (340.5, 240.0)),
    ]

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned, distractor],
        locals_in_view,
        [],
        camera,
    )

    assert decision.decision_state == "locked"
    assert decision.assigned_global_track_id == "G-assigned"
    assert decision.local_track_id == "assigned_visual"


def test_ambiguous_when_two_candidates_have_close_costs() -> None:
    associator = TerminalAssociator(AssociationConfig(min_lock_margin=3.0))
    camera = make_camera()
    assigned = make_track("G-assigned")
    locals_in_view = [
        make_local("candidate_left", (319.0, 240.0)),
        make_local("candidate_right", (321.0, 240.0)),
    ]

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned],
        locals_in_view,
        [],
        camera,
    )

    assert decision.decision_state == "ambiguous"
    assert decision.local_track_id in {"candidate_left", "candidate_right"}
    assert decision.reason == "insufficient_best_second_margin"


def test_verified_friend_overlap_forces_hold() -> None:
    checker = IdentityChecker(friendly_platform_ids={"FRIEND-1"})
    associator = TerminalAssociator(identity_checker=checker)
    camera = make_camera()
    assigned = make_track("G-assigned")
    local = make_local("friend_local", (320.0, 240.0), category="friend")
    claims = checker.parse_claims(
        [
            {
                "protocol": "OpenDroneID",
                "platform_id": "FRIEND-1",
                "local_track_id": "friend_local",
                "timestamp": 10.0,
                "is_friend": True,
                "signature_valid": True,
            }
        ],
        current_time=10.2,
    )

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned],
        [local],
        claims,
        camera,
    )

    assert decision.decision_state == "hold"
    assert decision.friend_conflict_state == "verified_friend_overlap"
    assert decision.reason == "verified_friend_overlap_inside_gate"


def test_unsigned_friend_claim_makes_candidate_ambiguous_not_locked() -> None:
    checker = IdentityChecker(friendly_platform_ids={"FRIEND-1"})
    associator = TerminalAssociator(identity_checker=checker)
    camera = make_camera()
    assigned = make_track("G-assigned")
    local = make_local("local_with_bad_claim", (320.0, 240.0))
    claims = checker.parse_claims(
        [
            {
                "protocol": "OpenDroneID",
                "platform_id": "FRIEND-1",
                "local_track_id": "local_with_bad_claim",
                "timestamp": 5.0,
                "is_friend": True,
                "signature_valid": False,
            }
        ],
        current_time=5.1,
    )

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned],
        [local],
        claims,
        camera,
    )

    assert decision.decision_state == "ambiguous"
    assert decision.friend_conflict_state == "spoof_suspected_overlap"


def test_reacquire_when_no_local_track_inside_gate() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned")

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned],
        [make_local("far", (420.0, 240.0))],
        [],
        camera,
    )

    assert decision.decision_state == "reacquire"
    assert decision.local_track_id is None


def test_rate_and_category_costs_are_reflected_in_matrix() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    track = make_track("G-moving", velocity=(1.0, 0.0, 0.0), category="uav")
    projections = associator.project_tracks_to_image([track], camera)
    rate_match = make_local("rate_match", (320.0, 240.0), bearing_rate=(10.0, 0.0))
    rate_bad = make_local("rate_bad", (320.0, 240.0), bearing_rate=(80.0, 0.0))
    category_bad = make_local("category_bad", (320.0, 240.0), category="friend")

    result = associator.build_cost_matrix(projections, [rate_match, rate_bad, category_bad])

    assert result.costs[0, 0] < result.costs[0, 1]
    assert result.breakdowns[("G-moving", "category_bad")].category_cost > 0


def test_secondary_recon_cue_lowers_cost_only_for_scoped_resource() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    track = make_track("G-assigned")
    projection = associator.project_tracks_to_image([track], camera)
    local = make_local("assigned_visual", (320.0, 240.0))
    cue = ReconImageCue(
        cue_id="cue-1",
        producer_node_id="secondary-recon-1",
        timestamp=1.0,
        image_frame_id="sec_cam",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        confidence=0.8,
        scoped_resource_ids=("R-1",),
    )

    in_scope = associator.build_cost_matrix(
        projection,
        [local],
        recon_image_cues=[cue],
        resource_id="R-1",
    )
    out_of_scope = associator.build_cost_matrix(
        projection,
        [local],
        recon_image_cues=[cue],
        resource_id="R-2",
    )

    assert in_scope.breakdowns[("G-assigned", "assigned_visual")].recon_cue_cost < 0.0
    assert out_of_scope.breakdowns[("G-assigned", "assigned_visual")].recon_cue_cost == 0.0


def test_secondary_recon_cue_age_frame_and_reprojection_rules() -> None:
    associator = TerminalAssociator(AssociationConfig(max_recon_cue_age_s=1.0))
    camera = make_camera()
    track = make_track("G-assigned")
    projection = associator.project_tracks_to_image([track], camera)
    local = make_local("assigned_visual", (320.0, 240.0))

    valid_reprojected = ReconImageCue(
        cue_id="cue-valid",
        producer_node_id="secondary-recon-1",
        timestamp=9.5,
        image_frame_id="R-1/front_rgb",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        confidence=0.8,
        scoped_resource_ids=("R-1",),
        metadata={
            "source_image_frame_id": "secondary-recon-1/wide_rgb",
            "target_frame_id": "R-1/front_rgb",
            "reprojected_to_local_camera": True,
        },
    )
    stale = ReconImageCue(
        cue_id="cue-stale",
        producer_node_id="secondary-recon-1",
        timestamp=8.0,
        image_frame_id="R-1/front_rgb",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        confidence=0.8,
        scoped_resource_ids=("R-1",),
        metadata={
            "source_image_frame_id": "secondary-recon-1/wide_rgb",
            "target_frame_id": "R-1/front_rgb",
            "reprojected_to_local_camera": True,
        },
    )
    wrong_frame = ReconImageCue(
        cue_id="cue-wrong-frame",
        producer_node_id="secondary-recon-1",
        timestamp=9.5,
        image_frame_id="secondary-recon-1/wide_rgb",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        confidence=0.8,
        scoped_resource_ids=("R-1",),
        metadata={"source_image_frame_id": "secondary-recon-1/wide_rgb"},
    )
    wrong_scope = ReconImageCue(
        cue_id="cue-wrong-scope",
        producer_node_id="secondary-recon-1",
        timestamp=9.5,
        image_frame_id="R-1/front_rgb",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        confidence=0.8,
        scoped_resource_ids=("R-2",),
        metadata={
            "source_image_frame_id": "secondary-recon-1/wide_rgb",
            "target_frame_id": "R-1/front_rgb",
            "reprojected_to_local_camera": True,
        },
    )

    valid = associator.build_cost_matrix(
        projection,
        [local],
        recon_image_cues=[valid_reprojected],
        resource_id="R-1",
        current_time=10.0,
        frame_id="R-1/front_rgb",
    )
    stale_result = associator.build_cost_matrix(
        projection,
        [local],
        recon_image_cues=[stale],
        resource_id="R-1",
        current_time=10.0,
        frame_id="R-1/front_rgb",
    )
    wrong_frame_result = associator.build_cost_matrix(
        projection,
        [local],
        recon_image_cues=[wrong_frame],
        resource_id="R-1",
        current_time=10.0,
        frame_id="R-1/front_rgb",
    )
    wrong_scope_result = associator.build_cost_matrix(
        projection,
        [local],
        recon_image_cues=[wrong_scope],
        resource_id="R-1",
        current_time=10.0,
        frame_id="R-1/front_rgb",
    )

    key = ("G-assigned", "assigned_visual")
    assert valid.breakdowns[key].recon_cue_cost < 0.0
    assert stale_result.breakdowns[key].recon_cue_cost == 0.0
    assert wrong_frame_result.breakdowns[key].recon_cue_cost == 0.0
    assert wrong_scope_result.breakdowns[key].recon_cue_cost == 0.0


def test_secondary_recon_cue_cannot_override_unauthorized_assignment() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned")
    cue = ReconImageCue(
        cue_id="cue-1",
        producer_node_id="secondary-recon-1",
        timestamp=1.0,
        image_frame_id="sec_cam",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        scoped_resource_ids=("R-1",),
    )

    decision = associator.decide(
        Assignment("G-assigned", authorization_state="required", resource_id="R-1"),
        [assigned],
        [make_local("assigned_visual", (320.0, 240.0))],
        [],
        camera,
        recon_image_cues=[cue],
    )

    assert decision.decision_state == "hold"
    assert decision.reason == "assignment_not_authorized"
    assert decision.recon_cue_used is False


def test_identity_checker_marks_stale_and_verified_claims() -> None:
    checker = IdentityChecker(friendly_platform_ids={"FRIEND-1"}, max_age_s=1.0)
    claims = checker.parse_claims(
        [
            {
                "protocol": "OpenDroneID",
                "platform_id": "FRIEND-1",
                "local_track_id": "fresh",
                "timestamp": 10.0,
                "is_friend": True,
                "signature_valid": True,
            },
            {
                "protocol": "OpenDroneID",
                "platform_id": "FRIEND-1",
                "local_track_id": "old",
                "timestamp": 7.0,
                "is_friend": True,
                "signature_valid": True,
            },
        ],
        current_time=10.5,
    )

    assert claims[0].auth_state == "verified"
    assert claims[1].auth_state == "stale"


def test_decision_does_not_mutate_global_track_id() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned")
    before_ids = [assigned.global_track_id]

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned],
        [make_local("assigned_visual", (320.0, 240.0))],
        [],
        camera,
    )

    assert decision.assigned_global_track_id == "G-assigned"
    assert [assigned.global_track_id] == before_ids
    with pytest.raises(FrozenInstanceError):
        assigned.global_track_id = "rewritten"  # type: ignore[misc]


def test_assignment_version_mismatch_forces_hold_by_default() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned")

    decision = associator.decide(
        Assignment("G-assigned", assignment_version=2),
        [assigned],
        [make_local("assigned_visual", (320.0, 240.0))],
        [],
        camera,
    )

    assert decision.decision_state == "hold"
    assert decision.reason == "assignment_version_mismatch"


def test_unauthorized_assignment_forces_hold() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned")

    decision = associator.decide(
        Assignment("G-assigned", authorization_state="required"),
        [assigned],
        [make_local("assigned_visual", (320.0, 240.0))],
        [],
        camera,
    )

    assert decision.decision_state == "hold"
    assert decision.reason == "assignment_not_authorized"


def test_short_or_low_quality_mot_track_cannot_lock() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    assigned = make_track("G-assigned")
    weak_local = LocalVisualTrack(
        local_track_id="weak",
        center_px=np.array([320.0, 240.0]),
        bbox=(315.0, 235.0, 325.0, 245.0),
        category="uav",
        quality=0.4,
        mot_history_length=1,
    )

    decision = associator.decide(
        Assignment("G-assigned"),
        [assigned],
        [weak_local],
        [],
        camera,
    )

    assert decision.decision_state == "ambiguous"
    assert decision.reason in {"mot_history_too_short", "local_track_quality_too_low"}


def test_projection_uses_current_time_prediction() -> None:
    associator = TerminalAssociator()
    camera = make_camera()
    track = make_track("G-moving", position=(0.0, 0.0, 10.0), velocity=(1.0, 0.0, 0.0))

    projection = associator.project_tracks_to_image([track], camera, timestamp=2.0)["G-moving"]

    assert projection.valid
    np.testing.assert_allclose(projection.pixel, np.array([340.0, 240.0]), atol=1e-6)
