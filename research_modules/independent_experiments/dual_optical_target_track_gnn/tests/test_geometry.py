from __future__ import annotations

import numpy as np
import pytest

from dual_optical_target_track_gnn import (
    CausalityError,
    ConfirmedTrackPair,
    GeometryFitError,
    evaluate_asynchronous_track_pair,
    form_target_hypothesis,
)

from conftest import (
    CAMERA_POSITIONS,
    TARGET_POSITION,
    TARGET_VELOCITY,
    make_confirmed_pair,
    make_snapshot,
    make_track,
)


def test_asynchronous_weighted_fit_recovers_state_and_covariance() -> None:
    # The two stations observe in disjoint windows separated by about one second.
    track_a = make_track("camera_a", "A-17", (0.10, 0.15, 0.20, 0.25))
    track_b = make_track("camera_b", "B-42", (1.10, 1.15, 1.20, 1.25))
    snapshot = make_snapshot(1, (track_a,), (track_b,))

    quality = evaluate_asynchronous_track_pair(snapshot, "A-17", "B-42")

    assert quality.gate_passed
    assert quality.cross_camera_median_time_offset_s == pytest.approx(0.875, abs=0.1)
    assert quality.state_ned is not None
    assert quality.covariance_6x6 is not None
    reference = float(quality.reference_timestamp)
    expected_position = TARGET_POSITION + TARGET_VELOCITY * reference
    assert np.asarray(quality.state_ned[:3]) == pytest.approx(expected_position, abs=1.0)
    assert np.asarray(quality.state_ned[3:]) == pytest.approx(TARGET_VELOCITY, abs=1.0)
    covariance = np.asarray(quality.covariance_6x6).reshape(6, 6)
    assert np.allclose(covariance, covariance.T, atol=1.0e-9)
    assert np.min(np.linalg.eigvalsh(covariance)) >= -1.0e-8
    assert float(np.trace(covariance)) > 0.0


def test_hypothesis_creation_is_causal_and_uses_past_pair_only() -> None:
    track_a = make_track("camera_a", "A-seed", (0.10, 0.15, 0.20, 0.25))
    track_b = make_track("camera_b", "B-seed", (1.10, 1.15, 1.20, 1.25))
    snapshot = make_snapshot(1, (track_a,), (track_b,))
    pair, publication = make_confirmed_pair(snapshot, "A-seed", "B-seed")

    hypothesis = form_target_hypothesis(
        "H-001",
        {1: snapshot},
        (pair,),
        creation_revolution_index=2,
        online_publications={pair.publication_fingerprint: publication},
    )

    assert hypothesis.created_revolution_index == 2
    assert hypothesis.support_count == 8
    assert hypothesis.confirmed_pairs == (pair,)
    with pytest.raises(CausalityError):
        form_target_hypothesis(
            "H-invalid",
            {1: snapshot},
            (pair,),
            creation_revolution_index=1,
            online_publications={pair.publication_fingerprint: publication},
        )


def test_confirmed_pair_requires_online_anonymous_publication_provenance() -> None:
    track_a = make_track("camera_a", "A-seed", (0.10, 0.15, 0.20, 0.25))
    track_b = make_track("camera_b", "B-seed", (1.10, 1.15, 1.20, 1.25))
    snapshot = make_snapshot(1, (track_a,), (track_b,))
    pair, publication = make_confirmed_pair(snapshot, "A-seed", "B-seed")

    restored = ConfirmedTrackPair.from_dict(pair.to_dict())
    restored.validate_publication(publication)
    assert restored == pair

    offline_label = {
        "schema_version": "dual-optical-online-dataset-v2",
        "offline_truth_only": True,
        "track_truth_counts": {"A-seed": {"TRUTH-001": 3}},
    }
    with pytest.raises(ValueError, match="offline|anonymous|schema"):
        ConfirmedTrackPair.from_online_publication(
            offline_label, "A-seed", "B-seed"
        )

    with pytest.raises(CausalityError, match="publication"):
        form_target_hypothesis(
            "H-no-publication",
            {1: snapshot},
            (pair,),
            creation_revolution_index=2,
            online_publications={},
        )


def test_bad_intersection_geometry_is_rejected() -> None:
    far_position = np.asarray((10_000_000.0, 0.0, 0.0), dtype=float)
    track_a = make_track(
        "camera_a",
        "A-parallel",
        (0.10, 0.15, 0.20, 0.25),
        position=far_position,
        velocity=np.zeros(3),
    )
    track_b = make_track(
        "camera_b",
        "B-parallel",
        (1.10, 1.15, 1.20, 1.25),
        position=far_position,
        velocity=np.zeros(3),
    )
    snapshot = make_snapshot(1, (track_a,), (track_b,))

    quality = evaluate_asynchronous_track_pair(
        snapshot, "A-parallel", "B-parallel"
    )

    assert not quality.gate_passed
    assert quality.covariance_6x6 is None
    assert "degenerate" in quality.rejection_reason or "condition" in quality.rejection_reason


def test_short_baseline_is_rejected() -> None:
    positions = {"camera_a": (0.0, 0.0, 0.0), "camera_b": (0.1, 0.0, 0.0)}
    track_a = make_track(
        "camera_a", "A-short", (0.1, 0.2, 0.3, 0.4), camera_positions=positions
    )
    track_b = make_track(
        "camera_b", "B-short", (1.1, 1.2, 1.3, 1.4), camera_positions=positions
    )
    snapshot = make_snapshot(1, (track_a,), (track_b,), camera_positions=positions)
    quality = evaluate_asynchronous_track_pair(snapshot, "A-short", "B-short")
    assert not quality.gate_passed
    assert "baseline" in quality.rejection_reason
