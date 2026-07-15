from __future__ import annotations

import numpy as np
from pathlib import Path
import sys

import pytest

from d2_data_association import (
    Detection,
    GNNHungarianAssociator,
    Tracker,
    TrackerTruthPolicy,
)
from d2_data_association.metrics import (
    AssociationRiskSummaryWindowGenerator,
    MetricsRecorder,
)
from d2_data_association.models import (
    AssociationResult,
    AssociationRiskSummary,
    MatchedPair,
    TrackLifecycleState,
)

D6_MODULE_ROOT = Path(__file__).resolve().parents[2] / "d6_evaluation_metrics"
if str(D6_MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(D6_MODULE_ROOT))

from d6_evaluation_metrics import MetricsCollector, TrackRecord


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
        truth_policy=TrackerTruthPolicy.OFFLINE,
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


def test_tracker_exports_track_quality_and_association_risk_metadata() -> None:
    tracker = Tracker(
        associator=GNNHungarianAssociator(),
        truth_policy=TrackerTruthPolicy.OFFLINE,
        confirmation_hits=2,
        engageable_hits=3,
        engageable_covariance_trace=100.0,
    )

    result = tracker.step([detection(0, 0.0)], timestamp=0.0, truth_ids_present=["A"])
    track = next(iter(tracker.active_tracks()))
    track_id = track.global_track_id

    assert 0.0 <= track.track_quality <= 1.0
    assert 0.0 <= track.association_risk <= 1.0
    assert result.metadata["track_quality_by_track"][track_id] == pytest.approx(
        track.track_quality
    )
    assert result.metadata["association_risk_by_track"][track_id] == pytest.approx(
        track.association_risk
    )
    assert result.metadata["track_quality_metadata_by_track"][track_id][
        "created_this_frame"
    ] is True

    track_dict = track.to_dict()
    assert track_dict["track_quality"] == pytest.approx(track.track_quality)
    assert track_dict["association_risk"] == pytest.approx(track.association_risk)
    assert "quality_metadata" in track_dict

    log_dict = tracker.metrics.association_logs[-1].to_dict()
    risk_metadata = log_dict["risk_summary"]["metadata"]
    assert risk_metadata["track_quality_by_track"][track_id] == pytest.approx(
        track.track_quality
    )
    assert risk_metadata["association_risk_by_track"][track_id] == pytest.approx(
        track.association_risk
    )

    summary = tracker.metrics.summary()
    assert summary["track_quality_by_track"][track_id] == pytest.approx(
        track.track_quality
    )
    assert summary["association_risk_by_track"][track_id] == pytest.approx(
        track.association_risk
    )
    assert summary["max_track_association_risk"] == pytest.approx(
        track.association_risk
    )


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
    assert summary["id_switch_count_available"] is True
    assert summary["id_switch_count_reason"] is None
    assert summary["rmse_available"] is True
    assert summary["rmse_reason"] is None


def test_online_tracker_rejects_truth_fields_before_mutating_state() -> None:
    clean_detection = Detection(
        detection_id="online-1",
        timestamp=0.0,
        position=np.zeros(2),
        covariance=np.eye(2),
    )
    cases = [
        (
            Detection(
                detection_id="truth-id",
                timestamp=0.0,
                position=np.zeros(2),
                covariance=np.eye(2),
                truth_id="target-A",
            ),
            None,
            None,
            "truth_id",
        ),
        (clean_detection, [], None, "truth_ids_present"),
        (
            Detection(
                detection_id="metadata-truth",
                timestamp=0.0,
                position=np.zeros(2),
                covariance=np.eye(2),
                metadata={"nested": {"truth_object_id": "target-A"}},
            ),
            None,
            None,
            "truth_object_id",
        ),
        (
            clean_detection,
            None,
            {"nested": [{"actor_name": "Intruder01"}]},
            "actor_name",
        ),
        (
            clean_detection,
            None,
            {"object_identity": "Intruder01"},
            "object_identity",
        ),
        (
            clean_detection,
            None,
            {"truth_id": "target-A"},
            "truth_id",
        ),
        (
            clean_detection,
            None,
            {"offline_truth_payload": {"target": "target-A"}},
            "offline_truth_payload",
        ),
        (
            clean_detection,
            None,
            {"truth_metrics_available": "target-A"},
            "truth_metrics_available",
        ),
    ]

    for candidate, truth_ids, frame_metadata, expected_path in cases:
        tracker = Tracker(truth_policy=TrackerTruthPolicy.ONLINE)
        with pytest.raises(ValueError, match=expected_path):
            tracker.step(
                [candidate],
                timestamp=0.0,
                truth_ids_present=truth_ids,
                frame_metadata=frame_metadata,
            )
        assert tracker.tracks == {}
        assert tracker.metrics.frame_count == 0


def test_online_tracker_allows_boolean_truth_governance_status() -> None:
    tracker = Tracker(truth_policy=TrackerTruthPolicy.ONLINE)
    frame_metadata = {
        "online_truth_hints_used": False,
        "truth_metrics_available": False,
        "continuity_available": False,
        "online_truth_isolated": True,
    }

    result = tracker.step(
        [
            Detection(
                detection_id="anonymous-status-1",
                timestamp=0.0,
                position=np.zeros(2),
                covariance=np.eye(2),
            )
        ],
        timestamp=0.0,
        frame_metadata=frame_metadata,
    )

    for key, value in frame_metadata.items():
        assert result.metadata[key] is value
        assert result.metadata["replay_metadata"][key] is value
    assert tracker.metrics.frame_count == 1
    assert set(tracker.tracks) == {"T001"}


def test_offline_tracker_allows_truth_and_reports_available_zero_id_switch() -> None:
    tracker = Tracker(truth_policy=TrackerTruthPolicy.OFFLINE)

    tracker.step(
        [detection(0, 0.0)],
        timestamp=0.0,
        truth_ids_present=["A"],
        frame_metadata={"actor_name": "Intruder01", "object_id": "actor-1"},
    )

    summary = tracker.metrics.summary()
    assert summary["truth_metrics_available"] is True
    assert summary["id_switch_count_available"] is True
    assert summary["id_switch_count"] == 0
    assert summary["id_switch_count_reason"] is None


def test_truthless_summary_keeps_metric_fields_unavailable_instead_of_zero() -> None:
    tracker = Tracker(truth_policy=TrackerTruthPolicy.ONLINE)
    tracker.step(
        [
            Detection(
                detection_id="anonymous-1",
                timestamp=0.0,
                position=np.zeros(2),
                covariance=np.eye(2),
                metadata={"online_truth_isolated": True},
            )
        ],
        timestamp=0.0,
    )

    summary = tracker.metrics.summary()
    for field in ("id_switch_count", "track_continuity", "rmse"):
        assert field in summary
        assert summary[field] is None
    assert summary["truth_metrics_available"] is False
    assert summary["truth_metrics_reason"] == "truth_assignment_unavailable"
    assert summary["id_switch_count_available"] is False
    assert summary["id_switch_count_reason"] == "truth_assignment_unavailable"
    assert summary["track_continuity_available"] is False
    assert summary["track_continuity_reason"] == "truth_assignment_unavailable"
    assert summary["rmse_available"] is False
    assert summary["rmse_reason"] == "truth_assignment_unavailable"


def test_tracker_exports_truth_free_lifecycle_counts_and_transitions() -> None:
    tracker = Tracker(
        truth_policy=TrackerTruthPolicy.ONLINE,
        confirmation_hits=1,
        engageable_hits=2,
        lost_miss_threshold=1,
        drop_miss_threshold=3,
        engageable_covariance_trace=100.0,
    )

    def anonymous(step: int, x: float) -> Detection:
        return Detection(
            detection_id=f"anonymous-{step}",
            timestamp=float(step),
            position=np.array([x, 0.0]),
            covariance=np.eye(2) * 0.2,
        )

    tracker.step([anonymous(0, 0.0)], timestamp=0.0)
    tracker.step([anonymous(1, 1.0)], timestamp=1.0)
    tracker.step([], timestamp=2.0)
    tracker.step([anonymous(3, 3.0)], timestamp=3.0)
    tracker.step([], timestamp=4.0)
    tracker.step([], timestamp=5.0)
    tracker.step([], timestamp=6.0)

    summary = tracker.metrics.summary()
    assert summary["lifecycle_metrics_available"] is True
    assert summary["lifecycle_metrics_reason"] == "truth_free_tracker_state_events"
    assert summary["birth_count"] == 1
    assert summary["lost_count"] == 2
    assert summary["drop_count"] == 1
    assert summary["rebirth_count"] == 1
    assert summary["lifecycle_transition_count"] == len(
        summary["lifecycle_transitions"]
    )
    assert any(
        transition["from_state"] == "lost"
        and transition["to_state"] == "engageable"
        for transition in summary["lifecycle_transitions"]
    )


def test_online_d1_source_lineage_prevents_shadow_birth_and_teleport_rebirth() -> None:
    tracker = Tracker(
        associator=GNNHungarianAssociator(
            gate_threshold=16.0,
            source_continuity_weight=2.0,
        ),
        truth_policy=TrackerTruthPolicy.ONLINE,
        confirmation_hits=2,
        engageable_hits=3,
    )

    def source_detection(
        source_track_id: str,
        timestamp: float,
        x: float,
        y: float = 0.0,
    ) -> Detection:
        return Detection(
            detection_id=f"{source_track_id}_{timestamp:.1f}",
            timestamp=timestamp,
            position=np.array([x, y], dtype=float),
            covariance=np.eye(2) * 0.25,
            metadata={
                "source_global_track_id": source_track_id,
                "source_support": {"radar": int(timestamp) + 1},
                "identity_policy": "online_anonymous",
            },
        )

    tracker.step(
        [
            source_detection("global_track_001", 0.0, 0.0),
            source_detection("global_track_002", 0.0, 10.0),
        ],
        timestamp=0.0,
    )
    tracker.step(
        [
            source_detection("global_track_001", 1.0, 1.0),
            source_detection("global_track_002", 1.0, 11.0),
        ],
        timestamp=1.0,
    )

    duplicate_result = tracker.step(
        [
            source_detection("global_track_001", 2.0, 2.0),
            source_detection("global_track_002", 2.0, 12.2),
            source_detection("global_track_003", 2.0, 12.0),
        ],
        timestamp=2.0,
    )

    assert [track.global_track_id for track in tracker.active_tracks()] == [
        "T001",
        "T002",
    ]
    assert {
        pair.track_id: pair.detection_id for pair in duplicate_result.matched_pairs
    }["T002"] == "global_track_002_2.0"
    assert duplicate_result.metadata["suppressed_birth_detection_ids"] == [
        "global_track_003_2.0"
    ]
    assert duplicate_result.metadata["suppressed_births"][0]["reason"] == (
        "gated_shadow_of_existing_track"
    )

    teleport_result = tracker.step(
        [
            source_detection("global_track_001", 3.0, 3.0),
            source_detection("global_track_002", 3.0, -50.0),
            source_detection("global_track_003", 3.0, 13.0),
        ],
        timestamp=3.0,
    )

    assert [track.global_track_id for track in tracker.active_tracks()] == [
        "T001",
        "T002",
    ]
    lineage = teleport_result.metadata["source_lineage_governance"]
    assert lineage["quarantined_detection_ids"] == ["global_track_002_3.0"]
    assert lineage["quarantined_sources"][0]["reason"] == (
        "bound_source_mahalanobis_discontinuity"
    )
    assert {
        pair.track_id: pair.detection_id for pair in teleport_result.matched_pairs
    }["T002"] == "global_track_003_3.0"
    assert teleport_result.metadata["source_track_bindings"] == {
        "global_track_001": "T001",
        "global_track_002": "T002",
        "global_track_003": "T002",
    }
    assert tracker.tracks["T002"].source_track_ids == {
        "global_track_002",
        "global_track_003",
    }


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


def test_risk_summary_window_generator_uses_cost_candidates_idsw_and_d5() -> None:
    generator = AssociationRiskSummaryWindowGenerator(window_size=3)
    first = AssociationResult(
        timestamp=1.0,
        matched_pairs=[MatchedPair("T1", "D1", 0.2)],
        unmatched_track_ids=[],
        unmatched_detection_ids=[],
        ambiguity_score=0.2,
        associator_type="test",
        cost_matrix=np.array([[0.2, 0.25], [0.3, 0.4]]),
        metadata={
            "candidate_counts_by_track": {"T1": 2, "T2": 2},
            "candidate_counts_by_detection": {"D1": 2, "D2": 2},
            "d5_disagreement_count": 1,
            "source_node_id": "d5-terminal",
            "link_type": "terminal_feedback",
        },
    )
    second = AssociationResult(
        timestamp=2.0,
        matched_pairs=[MatchedPair("T2", "D2", 0.1)],
        unmatched_track_ids=[],
        unmatched_detection_ids=[],
        ambiguity_score=0.1,
        associator_type="test",
        cost_matrix=np.array([[0.1, 1.5], [0.2, 0.21]]),
        metadata={
            "candidate_counts_by_track": {"T1": 1, "T2": 2},
            "candidate_counts_by_detection": {"D1": 2, "D2": 1},
            "d5_disagreement_count": 2,
        },
    )

    summary = generator.update(first, id_switch_delta=0, track_continuity=1.0)
    assert summary.covariance_overlap_rate == pytest.approx(1.0)
    assert summary.d5_disagreement_count == 1

    summary = generator.update(second, id_switch_delta=1, track_continuity=0.5)
    assert summary.d5_disagreement_count == 3
    assert summary.duplicate_track_risk >= 0.5
    assert summary.association_ambiguity > 0.1
    assert summary.source_node_id == "d5-terminal"
    assert summary.link_type == "terminal_feedback"
    assert summary.metadata["id_switch_delta_sum"] == 1
    assert summary.metadata["mean_candidate_count"] > 1.0


def test_d2_id_switch_count_matches_d6_episode_counting_convention() -> None:
    frames = [
        (0.0, "A", "T1"),
        (1.0, "A", "T1"),
        (2.0, "A", "T2"),
        (0.0, "B", "T3"),
        (1.0, "B", "T3"),
        (2.0, "B", "T4"),
        (3.0, "B", "T4"),
    ]

    d2_metrics = MetricsRecorder()
    d6_collector = MetricsCollector()
    for timestamp, truth_id, track_id in frames:
        d2_metrics.record_frame(
            timestamp=timestamp,
            truth_ids_present=[truth_id],
            association_result=AssociationResult(
                timestamp=timestamp,
                matched_pairs=[MatchedPair(track_id, f"{truth_id}-{timestamp}", 0.0)],
                unmatched_track_ids=[],
                unmatched_detection_ids=[],
                ambiguity_score=0.0,
                associator_type="test",
            ),
            assignments=[(truth_id, track_id, 0.0)],
            runtime_seconds=0.0,
        )
        d6_collector.add_track(
            TrackRecord(
                timestamp=timestamp,
                global_track_id=track_id,
                truth_id=truth_id,
                position=(0.0, 0.0),
                truth_position=(0.0, 0.0),
            )
        )

    d6_metrics = d6_collector.compute_episode(
        "d2_d6_idsw_contract",
        truth_summary={
            "truth_timestamps": {
                "A": [0.0, 1.0, 2.0],
                "B": [0.0, 1.0, 2.0, 3.0],
            }
        },
        scenario_group="contract",
        batch_seed=0,
    )

    assert d2_metrics.id_switch_count == 2
    assert d2_metrics.id_switch_count == d6_metrics.id_switch_count
