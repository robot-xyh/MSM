from __future__ import annotations

import numpy as np

from d2_data_association import (
    Detection,
    GNNHungarianAssociator,
    GlobalTrack,
    JPDAAssociator,
    MHTAssociator,
    TrackLifecycleState,
)
from d2_data_association.gating import build_gated_cost_matrix, mahalanobis_squared


def make_track(track_id: str, x: float, y: float) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=track_id,
        state=np.array([x, y, 0.0, 0.0]),
        covariance=np.diag([0.5, 0.5, 1.0, 1.0]),
        timestamp=0.0,
        lifecycle_state=TrackLifecycleState.CONFIRMED,
        hits=3,
    )


def make_velocity_track(
    track_id: str,
    x: float,
    y: float,
    vx: float,
    vy: float,
    previous_x: float,
    previous_y: float,
) -> GlobalTrack:
    track = GlobalTrack(
        global_track_id=track_id,
        state=np.array([x, y, vx, vy]),
        covariance=np.diag([0.4, 0.4, 1.0, 1.0]),
        timestamp=1.0,
        lifecycle_state=TrackLifecycleState.CONFIRMED,
        hits=4,
        age=4,
        last_update_time=0.0,
        identity_confidence=0.8,
    )
    track.history.append(
        {
            "timestamp": 0.0,
            "event": "update",
            "state": [previous_x, previous_y, vx, vy],
        }
    )
    return track


def make_detection(detection_id: str, x: float, y: float) -> Detection:
    return Detection(
        detection_id=detection_id,
        timestamp=0.0,
        position=np.array([x, y]),
        covariance=np.eye(2) * 0.5,
    )


def test_mahalanobis_gate_accepts_near_and_rejects_far() -> None:
    track = make_track("T1", 0.0, 0.0)
    near = make_detection("D1", 0.4, 0.0)
    far = make_detection("D2", 10.0, 0.0)

    assert mahalanobis_squared(track, near) < 9.21
    assert mahalanobis_squared(track, far) > 9.21

    gated = build_gated_cost_matrix([track], [near, far], gate_threshold=9.21)
    assert gated.candidate_counts_by_track["T1"] == 1
    assert gated.rejected_pairs[0].reason == "mahalanobis_gate"


def test_gnn_hungarian_matches_nearest_without_duplicates() -> None:
    tracks = [make_track("T1", 0.0, 0.0), make_track("T2", 10.0, 0.0)]
    detections = [make_detection("D1", 0.1, 0.0), make_detection("D2", 9.9, 0.0)]

    result = GNNHungarianAssociator().associate(tracks, detections, timestamp=0.0)

    assert {(pair.track_id, pair.detection_id) for pair in result.matched_pairs} == {
        ("T1", "D1"),
        ("T2", "D2"),
    }
    assert len({pair.detection_id for pair in result.matched_pairs}) == 2
    assert result.unmatched_track_ids == []
    assert result.unmatched_detection_ids == []


def test_gnn_motion_consistency_breaks_crossing_tie() -> None:
    tracks = [
        make_velocity_track("T-east", 0.0, 0.0, 1.0, 0.0, -1.0, 0.0),
        make_velocity_track("T-west", 0.0, 0.0, -1.0, 0.0, 1.0, 0.0),
    ]
    detections = [
        make_detection("D-west", -0.2, 0.0),
        make_detection("D-east", 0.2, 0.0),
    ]

    result = GNNHungarianAssociator(
        gate_threshold=9.21,
        feature_weight=0.0,
        motion_weight=4.0,
        quality_aware_gate=False,
    ).associate(tracks, detections, timestamp=1.0)

    assert {(pair.track_id, pair.detection_id) for pair in result.matched_pairs} == {
        ("T-east", "D-east"),
        ("T-west", "D-west"),
    }
    assert result.metadata["solver"] == "scipy.optimize.linear_sum_assignment"
    assert result.metadata["motion_weight"] == 4.0
    motion_by_pair = result.metadata["motion_consistency_by_pair"]
    assert motion_by_pair["T-east->D-east"] < motion_by_pair["T-east->D-west"]
    assert motion_by_pair["T-west->D-west"] < motion_by_pair["T-west->D-east"]


def test_quality_aware_gate_adjusts_for_quality_density_and_covariance() -> None:
    low_quality_track = GlobalTrack(
        global_track_id="T-low",
        state=np.array([0.0, 0.0, 0.0, 0.0]),
        covariance=np.diag([0.5, 0.5, 1.0, 1.0]),
        timestamp=1.0,
        lifecycle_state=TrackLifecycleState.LOST,
        hits=1,
        misses=3,
        age=6,
        identity_confidence=0.0,
    )
    borderline = make_detection("D-borderline", 2.03, 0.0)

    fixed_gate = build_gated_cost_matrix(
        [low_quality_track],
        [borderline],
        gate_threshold=4.0,
        quality_aware_gate=False,
    )
    quality_gate = build_gated_cost_matrix(
        [low_quality_track],
        [borderline],
        gate_threshold=4.0,
        quality_aware_gate=True,
    )

    assert fixed_gate.candidate_counts_by_track["T-low"] == 0
    assert quality_gate.gate_thresholds_by_track["T-low"] > 4.0
    assert quality_gate.candidate_counts_by_track["T-low"] == 1

    association = GNNHungarianAssociator(
        gate_threshold=4.0,
        quality_aware_gate=True,
    ).associate([low_quality_track], [borderline], timestamp=1.0)
    assert [(pair.track_id, pair.detection_id) for pair in association.matched_pairs] == [
        ("T-low", "D-borderline")
    ]

    dense_tracks = [make_track("T1", 0.0, 0.0), make_track("T2", 0.4, 0.0)]
    dense_detections = [make_detection("D1", 0.05, 0.0), make_detection("D2", 0.45, 0.0)]
    dense_gate = build_gated_cost_matrix(
        dense_tracks,
        dense_detections,
        gate_threshold=9.21,
        quality_aware_gate=True,
    )

    assert dense_gate.target_density_by_track["T1"] > 0.0
    assert dense_gate.gate_thresholds_by_track["T1"] < 9.21


def test_jpda_outputs_marginals_and_valid_pair() -> None:
    tracks = [make_track("T1", 0.0, 0.0), make_track("T2", 2.0, 0.0)]
    detections = [make_detection("D1", 0.2, 0.0), make_detection("D2", 1.8, 0.0)]

    result = JPDAAssociator(min_marginal_probability=0.20).associate(
        tracks, detections, timestamp=0.0
    )

    assert result.associator_type == "JPDAAssociator"
    assert result.metadata["joint_hypothesis_count"] > 0
    assert result.metadata["marginal_probabilities"].shape == (2, 2)
    assert len(result.matched_pairs) >= 1


def test_mht_returns_interface_compatible_association() -> None:
    tracks = [make_track("T1", 0.0, 0.0), make_track("T2", 5.0, 0.0)]
    detections = [make_detection("D1", 0.1, 0.0), make_detection("D2", 5.2, 0.0)]
    associator = MHTAssociator(max_hypotheses=4)

    first = associator.associate(tracks, detections, timestamp=0.0)
    second = associator.associate(tracks, detections, timestamp=1.0)

    assert first.associator_type == "MHTAssociator"
    assert len(first.matched_pairs) == 2
    assert second.metadata["branch_count"] <= 4
    assert second.metadata["max_history"] == 5
