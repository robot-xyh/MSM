from __future__ import annotations

import numpy as np

import pytest

from d2_data_association import Detection, GNNHungarianAssociator, Tracker
from d2_data_association.metrics import MetricsRecorder
from d2_data_association.models import (
    AssociationResult,
    AssociationRiskSummary,
    MatchedPair,
    TrackLifecycleState,
)


def detection(step: int, x: float, truth_id: str = "A") -> Detection:
    truth_position = np.array([x, 0.0])
    return Detection(
        detection_id=f"D{step}",
        timestamp=float(step),
        position=truth_position,
        covariance=np.eye(2) * 0.2,
        truth_id=truth_id,
        metadata={"truth_position": truth_position},
    )


def test_tracker_lifecycle_reaches_engageable_then_lost_and_dropped() -> None:
    tracker = Tracker(
        associator=GNNHungarianAssociator(),
        confirmation_hits=2,
        engageable_hits=3,
        lost_miss_threshold=1,
        drop_miss_threshold=3,
        engageable_covariance_trace=100.0,
    )

    tracker.step([detection(0, 0.0)], timestamp=0.0, truth_ids_present=["A"])
    track = next(iter(tracker.tracks.values()))
    assert track.lifecycle_state == TrackLifecycleState.TENTATIVE

    tracker.step([detection(1, 1.0)], timestamp=1.0, truth_ids_present=["A"])
    assert track.lifecycle_state == TrackLifecycleState.CONFIRMED

    tracker.step([detection(2, 2.0)], timestamp=2.0, truth_ids_present=["A"])
    assert track.lifecycle_state == TrackLifecycleState.ENGAGEABLE

    tracker.step([], timestamp=3.0, truth_ids_present=["A"])
    assert track.lifecycle_state == TrackLifecycleState.LOST

    tracker.step([], timestamp=4.0, truth_ids_present=["A"])
    tracker.step([], timestamp=5.0, truth_ids_present=["A"])
    assert track.lifecycle_state == TrackLifecycleState.DROPPED


def test_metrics_records_id_switch_continuity_duplicate_and_confusion() -> None:
    metrics = MetricsRecorder()
    first = AssociationResult(
        timestamp=0.0,
        matched_pairs=[MatchedPair("T1", "D1", 0.1)],
        unmatched_track_ids=[],
        unmatched_detection_ids=[],
        ambiguity_score=0.0,
        associator_type="test",
    )
    second = AssociationResult(
        timestamp=1.0,
        matched_pairs=[
            MatchedPair("T2", "D2", 0.1),
            MatchedPair("T3", "D2", 0.2),
        ],
        unmatched_track_ids=[],
        unmatched_detection_ids=[],
        ambiguity_score=0.0,
        associator_type="test",
    )

    metrics.record_frame(
        timestamp=0.0,
        truth_ids_present=["A"],
        association_result=first,
        assignments=[("A", "T1", 1.0)],
        runtime_seconds=0.01,
    )
    metrics.record_frame(
        timestamp=1.0,
        truth_ids_present=["A"],
        association_result=second,
        assignments=[("A", "T2", 1.0), ("A", "T3", 4.0)],
        runtime_seconds=0.01,
    )

    summary = metrics.summary()
    assert summary["id_switch_count"] == 1
    assert summary["track_continuity"] == 0.5
    assert summary["identity_continuity"] == 0.5
    assert summary["coverage_continuity"] == 1.0
    assert summary["duplicate_assignment_count"] == 2
    assert summary["confusion_matrix"]["A"]["T1"] == 1
    assert summary["confusion_matrix"]["A"]["T2"] == 1
    assert summary["rmse"] == pytest.approx(2.0**0.5)


def test_identity_continuity_drops_when_track_id_changes_every_frame() -> None:
    metrics = MetricsRecorder()
    for step in range(3):
        track_id = f"T{step}"
        metrics.record_frame(
            timestamp=float(step),
            truth_ids_present=["A"],
            association_result=AssociationResult(
                timestamp=float(step),
                matched_pairs=[MatchedPair(track_id, f"D{step}", 0.0)],
                unmatched_track_ids=[],
                unmatched_detection_ids=[],
                ambiguity_score=0.0,
                associator_type="test",
            ),
            assignments=[("A", track_id, 0.0)],
            runtime_seconds=0.01,
        )

    summary = metrics.summary()

    assert summary["coverage_continuity"] == 1.0
    assert summary["identity_continuity"] == pytest.approx(1.0 / 3.0)
    assert summary["id_switch_count"] == 2


def test_metrics_records_cross_view_weak_evidence_risk_fields() -> None:
    metrics = MetricsRecorder()
    result = AssociationResult(
        timestamp=2.0,
        matched_pairs=[MatchedPair("T1", "D1", 0.2)],
        unmatched_track_ids=[],
        unmatched_detection_ids=[],
        ambiguity_score=0.4,
        associator_type="test",
        source_node_id="interceptor-2",
        link_type="interceptor_peer",
        risk_summary=AssociationRiskSummary(
            timestamp=2.0,
            source_node_id="interceptor-2",
            link_type="interceptor_peer",
            d5_disagreement_count=2,
            duplicate_track_risk=0.75,
            association_ambiguity=0.60,
            covariance_overlap_rate=0.40,
            metadata={
                "weak_evidence_only": True,
                "candidate_global_track_ids": ["T1", "T2"],
            },
        ),
    )

    metrics.record_frame(
        timestamp=2.0,
        truth_ids_present=["A"],
        association_result=result,
        assignments=[("A", "T1", 0.0)],
        runtime_seconds=0.01,
    )

    summary = metrics.summary()
    assert summary["d5_disagreement_count"] == 2
    assert summary["duplicate_track_risk"] == pytest.approx(0.75)
    assert summary["max_duplicate_track_risk"] == pytest.approx(0.75)
    assert summary["association_ambiguity"] == pytest.approx(0.60)
    assert summary["mean_association_ambiguity"] == pytest.approx(0.60)
    assert summary["covariance_overlap_rate"] == pytest.approx(0.40)
    assert summary["source_node_ids"] == ["interceptor-2"]
    assert summary["link_types"] == ["interceptor_peer"]

    log_dict = metrics.association_logs[0].to_dict()
    assert log_dict["source_node_id"] == "interceptor-2"
    assert log_dict["link_type"] == "interceptor_peer"
    assert log_dict["risk_summary"]["d5_disagreement_count"] == 2
    assert log_dict["matched_pairs"][0]["track_id"] == "T1"


def test_metrics_accepts_risk_fields_from_association_metadata() -> None:
    metrics = MetricsRecorder()
    result = AssociationResult(
        timestamp=3.0,
        matched_pairs=[MatchedPair("T7", "D7", 0.3)],
        unmatched_track_ids=[],
        unmatched_detection_ids=[],
        ambiguity_score=0.2,
        associator_type="test",
        metadata={
            "source_node_id": "secondary-recon-1",
            "link_type": "secondary_relay",
            "d5_disagreement_count": 1,
            "duplicate_track_risk": 0.25,
            "association_ambiguity": 0.35,
            "covariance_overlap_rate": 0.15,
        },
    )

    metrics.record_frame(
        timestamp=3.0,
        truth_ids_present=["B"],
        association_result=result,
        assignments=[("B", "T7", 0.0)],
        runtime_seconds=0.01,
    )

    summary = metrics.summary()
    assert summary["d5_disagreement_count"] == 1
    assert summary["duplicate_track_risk"] == pytest.approx(0.25)
    assert summary["association_ambiguity"] == pytest.approx(0.35)
    assert summary["covariance_overlap_rate"] == pytest.approx(0.15)
    assert summary["source_node_ids"] == ["secondary-recon-1"]
    assert summary["link_types"] == ["secondary_relay"]
