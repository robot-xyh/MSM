from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    Assignment,
    CameraModel,
    GlobalTrack,
    IdentityChecker,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociator,
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


def _track(global_id: str, position: tuple[float, float, float]) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_id,
        position=np.array(position, dtype=float),
        velocity=np.zeros(3, dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        category="uav",
        timestamp=0.0,
        track_version=0,
    )


def _local(local_id: str, center: tuple[float, float], category: str = "uav") -> LocalVisualTrack:
    u, v = center
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array(center, dtype=float),
        bbox=(u - 6.0, v - 6.0, u + 6.0, v + 6.0),
        bearing_rate=np.zeros(2, dtype=float),
        category=category,
        quality=0.95,
        mot_history_length=5,
        timestamp=1.0,
    )


def test_d5_dry_run_consumes_fake_camera_local_tracks_and_recon_cue() -> None:
    camera = _camera()
    associator = TerminalAssociator()
    assigned = _track("G-assigned", (0.0, 0.0, 20.0))
    distractor = _track("G-distractor", (3.0, 0.0, 20.0))
    before_ids = [assigned.global_track_id, distractor.global_track_id]
    cue = ReconImageCue(
        cue_id="dry-run-cue-1",
        producer_node_id="secondary-recon-1",
        timestamp=1.0,
        image_frame_id="R1/front_rgb",
        global_track_id="G-assigned",
        center_px=np.array([320.0, 240.0]),
        confidence=0.9,
        scoped_resource_ids=("R1",),
        metadata={"dry_run": True, "reprojected_to_local_camera": True},
    )

    decision = associator.decide(
        assignment=Assignment("G-assigned", resource_id="R1", authorization_state="recorded"),
        global_tracks=[assigned, distractor],
        local_tracks=[
            _local("L-assigned", (320.0, 240.0)),
            _local("L-distractor", (344.0, 240.0)),
        ],
        identity_claims=[],
        camera=camera,
        current_time=1.0,
        recon_image_cues=[cue],
    )

    assert decision.decision_state == "locked"
    assert decision.local_track_id == "L-assigned"
    assert decision.recon_cue_used is True
    assert [assigned.global_track_id, distractor.global_track_id] == before_ids


def test_d5_dry_run_exposes_ambiguity_and_friend_overlap_metrics_inputs() -> None:
    camera = _camera()
    checker = IdentityChecker(friendly_platform_ids={"FRIEND-1"})
    associator = TerminalAssociator(identity_checker=checker)
    assigned = _track("G-assigned", (0.0, 0.0, 20.0))

    ambiguous = associator.decide(
        assignment=Assignment("G-assigned", resource_id="R1"),
        global_tracks=[assigned],
        local_tracks=[
            _local("L-left", (319.4, 240.0)),
            _local("L-right", (320.6, 240.0)),
        ],
        identity_claims=[],
        camera=camera,
        current_time=1.0,
    )
    assert ambiguous.decision_state == "ambiguous"
    assert ambiguous.ambiguity_score >= 0.5
    assert len(ambiguous.candidate_costs) == 2

    friend_claims = checker.parse_claims(
        [
            {
                "platform_id": "FRIEND-1",
                "protocol": "OpenDroneID",
                "local_track_id": "L-friend",
                "timestamp": 1.0,
                "is_friend": True,
                "signature_valid": True,
            }
        ],
        current_time=1.0,
    )
    friend_hold = associator.decide(
        assignment=Assignment("G-assigned", resource_id="R1"),
        global_tracks=[assigned],
        local_tracks=[_local("L-friend", (320.0, 240.0), category="friend")],
        identity_claims=friend_claims,
        camera=camera,
        current_time=1.0,
    )

    assert friend_hold.decision_state == "hold"
    assert friend_hold.friend_conflict_state == "verified_friend_overlap"
    assert friend_hold.reason == "verified_friend_overlap_inside_gate"
