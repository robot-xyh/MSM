from __future__ import annotations

import math

import pytest

from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    TerminalRecord,
    TrackRecord,
)


def test_detection_and_tracking_metrics() -> None:
    collector = MetricsCollector()
    collector.add_track(
        TrackRecord(
            timestamp=0.0,
            global_track_id="G_A_0",
            truth_id="A",
            position=(0.0, 0.0),
            truth_position=(0.0, 0.0),
        )
    )
    collector.add_track(
        TrackRecord(
            timestamp=1.0,
            global_track_id="G_A_1",
            truth_id="A",
            position=(3.0, 4.0),
            truth_position=(0.0, 0.0),
        )
    )
    collector.add_track(
        TrackRecord(
            timestamp=0.0,
            global_track_id="G_B_0",
            truth_id="B",
            position=(1.0, 1.0),
            truth_position=(1.0, 1.0),
        )
    )
    collector.add_track(
        TrackRecord(
            timestamp=0.0,
            global_track_id="FA_0",
            truth_id=None,
            position=(9.0, 9.0),
        )
    )

    metrics = collector.compute_episode(
        episode_id="episode",
        duration=10.0,
        truth_summary={"truth_timestamps": {"A": [0.0, 1.0], "B": [0.0, 1.0]}},
    )

    assert metrics.detection_probability == pytest.approx(0.75)
    assert metrics.false_alarm_rate == pytest.approx(0.1)
    assert metrics.missed_detection_rate == pytest.approx(0.25)
    assert metrics.track_rmse == pytest.approx(math.sqrt(25.0 / 3.0))
    assert metrics.track_continuity == pytest.approx(0.75)
    assert metrics.id_switch_count == 1


def test_assignment_metrics_count_duplicates_and_unassigned_high_threat() -> None:
    collector = MetricsCollector()
    collector.add_assignment(
        AssignmentRecord(
            timestamp=0.0,
            plan_id="p0",
            version=1,
            resource_id="R1",
            global_track_id="G_A",
            truth_id="A",
        )
    )
    collector.add_assignment(
        AssignmentRecord(
            timestamp=0.0,
            plan_id="p0",
            version=1,
            resource_id="R2",
            global_track_id="G_A",
            truth_id="A",
        )
    )
    collector.add_assignment(
        AssignmentRecord(
            timestamp=5.0,
            plan_id="p1",
            version=1,
            resource_id="R1",
            global_track_id="G_B",
            truth_id="B",
        )
    )

    metrics = collector.compute_episode(
        episode_id="episode",
        duration=10.0,
        truth_summary={
            "high_threat_by_timestamp": {
                0.0: ["A", "B"],
                5.0: ["A", "B"],
            }
        },
    )

    assert metrics.duplicate_assignment_count == 1
    assert metrics.unassigned_high_threat_count == 2


def test_unassigned_high_threat_counts_without_any_assignments() -> None:
    collector = MetricsCollector()

    metrics = collector.compute_episode(
        episode_id="episode",
        duration=10.0,
        truth_summary={
            "truth_timestamps": {"A": [0.0, 1.0], "B": [0.0]},
            "high_threat_ids": ["A"],
        },
    )

    assert metrics.unassigned_high_threat_count == 2


def test_required_authorization_assignment_does_not_count_as_effective() -> None:
    collector = MetricsCollector()
    collector.add_assignment(
        AssignmentRecord(
            timestamp=0.0,
            plan_id="candidate",
            version=1,
            resource_id="R1",
            global_track_id="G_A",
            truth_id="A",
            authorization_state="required",
            active=True,
        )
    )

    metrics = collector.compute_episode(
        episode_id="episode",
        duration=10.0,
        truth_summary={"high_threat_by_timestamp": {0.0: ["A"]}},
    )

    assert metrics.unassigned_high_threat_count == 1


def test_degradation_and_safety_metrics() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(timestamp=10.0, event_type="central_failure"),
            EventRecord(timestamp=14.0, event_type="degraded_stable"),
            EventRecord(timestamp=14.0, event_type="consensus_rounds", value=5),
            EventRecord(timestamp=15.0, event_type="degraded_task_completed"),
            EventRecord(timestamp=16.0, event_type="degraded_task_completed"),
            EventRecord(timestamp=17.0, event_type="degraded_task_failed"),
            EventRecord(timestamp=18.0, event_type="constraint_violation"),
            EventRecord(timestamp=19.0, event_type="safety_constraint_violation"),
            EventRecord(timestamp=20.0, event_type="human_override"),
        ]
    )

    metrics = collector.compute_episode(episode_id="episode", duration=30.0)

    assert metrics.failover_time == pytest.approx(4.0)
    assert metrics.consensus_rounds == pytest.approx(5.0)
    assert metrics.degraded_completion_rate == pytest.approx(2.0 / 3.0)
    assert metrics.constraint_violation_count == 2
    assert metrics.human_override_count == 1


def test_terminal_metrics() -> None:
    collector = MetricsCollector()
    collector.add_terminal(
        TerminalRecord(
            timestamp=20.0,
            resource_id="R1",
            assigned_global_track_id="A",
            local_track_id="L0",
            decision_state="fov_entry",
            ambiguity_score=0.7,
            friend_conflict_state="hold",
            expected_global_track_id="A",
        )
    )
    collector.add_terminal(
        TerminalRecord(
            timestamp=22.0,
            resource_id="R1",
            assigned_global_track_id="A",
            local_track_id="L0",
            decision_state="locked",
            ambiguity_score=0.1,
            expected_global_track_id="A",
            association_correct=True,
        )
    )
    collector.add_terminal(
        TerminalRecord(
            timestamp=23.0,
            resource_id="R1",
            assigned_global_track_id="A",
            local_track_id="L1",
            decision_state="locked",
            ambiguity_score=0.1,
            expected_global_track_id="A",
            association_correct=True,
        )
    )

    metrics = collector.compute_episode(episode_id="episode", duration=30.0)

    assert metrics.terminal_association_accuracy == pytest.approx(1.0)
    assert metrics.terminal_id_switch_count == 1
    assert metrics.ambiguous_fov_event_count == 1
    assert metrics.friend_overlap_hold_count == 1
    assert metrics.time_to_terminal_lock == pytest.approx(2.0)


def test_terminal_events_are_deduplicated_across_records_and_events() -> None:
    collector = MetricsCollector()
    collector.add_terminal(
        TerminalRecord(
            timestamp=20.0,
            resource_id="R1",
            assigned_global_track_id="A",
            local_track_id="L0",
            decision_state="ambiguous",
            ambiguity_score=0.9,
            friend_conflict_state="verified_friend_overlap",
        )
    )
    collector.add_event(
        EventRecord(
            timestamp=20.0,
            event_type="terminal_ambiguous_fov",
            actor_id="R1",
            metadata={"assigned_global_track_id": "A", "local_track_id": "L0"},
        )
    )
    collector.add_event(
        EventRecord(
            timestamp=20.0,
            event_type="friend_overlap_hold",
            actor_id="R1",
            metadata={"assigned_global_track_id": "A", "local_track_id": "L0"},
        )
    )

    metrics = collector.compute_episode(episode_id="episode", duration=30.0)

    assert metrics.ambiguous_fov_event_count == 1
    assert metrics.friend_overlap_hold_count == 1


def test_link_metrics_from_link_records_and_event_metadata() -> None:
    collector = MetricsCollector()
    collector.extend_links(
        [
            LinkRecord(
                timestamp=1.0,
                source_node_id="I1",
                target_node_id="C2",
                link_type="c2_direct",
                message_type="track_update",
                sequence_id=2,
                sent_timestamp=1.0,
                received_timestamp=1.08,
                measurement_timestamp=0.9,
                payload_kind="track",
                stale_after_s=0.1,
            ),
            LinkRecord(
                timestamp=1.1,
                source_node_id="I1",
                target_node_id="C2",
                link_type="c2_direct",
                message_type="track_update",
                sequence_id=1,
                sent_timestamp=1.1,
                received_timestamp=1.16,
                payload_kind="track",
            ),
            LinkRecord(
                timestamp=2.0,
                source_node_id="TETHER",
                target_node_id="I1",
                link_type="video_cue",
                message_type="video_metadata",
                payload_kind="video_metadata",
                delivered=True,
                sent_timestamp=2.0,
                received_timestamp=2.04,
            ),
            LinkRecord(
                timestamp=2.1,
                source_node_id="TETHER",
                target_node_id="I1",
                link_type="video_cue",
                message_type="video_metadata",
                payload_kind="video_metadata",
                delivered=False,
            ),
            LinkRecord(
                timestamp=2.2,
                source_node_id="TETHER",
                target_node_id="I1",
                link_type="video_cue",
                message_type="bbox",
                payload_kind="bbox",
                delivered=True,
                sent_timestamp=2.2,
                received_timestamp=2.23,
            ),
        ]
    )
    collector.add_event(
        EventRecord(
            timestamp=3.0,
            event_type="consensus_stable",
            metadata={"consensus_start_timestamp": 2.5},
        )
    )

    metrics = collector.compute_episode("episode")

    assert metrics.cross_node_latency_ms == pytest.approx(52.5)
    assert metrics.message_drop_rate == pytest.approx(1.0 / 5.0)
    assert metrics.out_of_order_count == 1
    assert metrics.stale_track_update_count == 1
    assert metrics.video_metadata_delivery_rate == pytest.approx(0.5)
    assert metrics.bbox_delivery_rate == pytest.approx(1.0)
    assert metrics.consensus_latency_s == pytest.approx(0.5)


def test_multi_view_and_d7_guidance_gate_metrics() -> None:
    collector = MetricsCollector()
    collector.extend_terminals(
        [
            TerminalRecord(
                timestamp=10.0,
                resource_id="R1",
                assigned_global_track_id="G1",
                local_track_id="L1",
                decision_state="locked",
            ),
            TerminalRecord(
                timestamp=10.0,
                resource_id="R2",
                assigned_global_track_id="G1",
                local_track_id="L2",
                decision_state="locked",
            ),
        ]
    )
    collector.extend_events(
        [
            EventRecord(
                timestamp=11.0,
                event_type="multi_view_consensus_result",
                metadata={"consensus_reached": True},
            ),
            EventRecord(
                timestamp=11.5,
                event_type="multi_view_consensus_result",
                metadata={"consensus_reached": False},
            ),
            EventRecord(timestamp=12.0, event_type="cross_view_conflict"),
            EventRecord(
                timestamp=13.0,
                event_type="d7_control_command",
                metadata={
                    "guidance_law": "pn",
                    "camera_quality_gate_pass": True,
                    "los_quality_gate_pass": True,
                    "maneuver_margin_gate_pass": False,
                },
            ),
            EventRecord(
                timestamp=13.5,
                event_type="terminal_switch_rejected",
                metadata={
                    "guidance_law": "pn",
                    "terminal_switch_reject_reason": "camera_quality",
                    "camera_quality_gate_pass": False,
                    "los_quality_gate_pass": True,
                    "maneuver_margin_gate_pass": True,
                },
            ),
        ]
    )

    metrics = collector.compute_episode("episode")

    assert metrics.multi_view_consensus_rate == pytest.approx(0.5)
    assert metrics.cross_view_conflict_count == 1
    assert metrics.duplicate_terminal_lock_count == 1
    assert metrics.camera_quality_gate_pass_rate == pytest.approx(0.5)
    assert metrics.los_quality_gate_pass_rate == pytest.approx(1.0)
    assert metrics.maneuver_margin_gate_pass_rate == pytest.approx(0.5)
    assert metrics.terminal_switch_reject_count == 1
    assert metrics.metadata["guidance_law_counts"] == {"pn": 2}
    assert metrics.metadata["terminal_switch_reject_reasons"] == {"camera_quality": 1}


def test_episode_metrics_contains_all_required_names() -> None:
    required = {
        "detection_probability",
        "false_alarm_rate",
        "missed_detection_rate",
        "track_rmse",
        "track_continuity",
        "id_switch_count",
        "duplicate_assignment_count",
        "unassigned_high_threat_count",
        "failover_time",
        "consensus_rounds",
        "degraded_completion_rate",
        "terminal_association_accuracy",
        "terminal_id_switch_count",
        "ambiguous_fov_event_count",
        "friend_overlap_hold_count",
        "time_to_terminal_lock",
        "multi_view_consensus_rate",
        "cross_view_conflict_count",
        "duplicate_terminal_lock_count",
        "cross_node_latency_ms",
        "message_drop_rate",
        "out_of_order_count",
        "stale_track_update_count",
        "video_metadata_delivery_rate",
        "bbox_delivery_rate",
        "consensus_latency_s",
        "camera_quality_gate_pass_rate",
        "los_quality_gate_pass_rate",
        "maneuver_margin_gate_pass_rate",
        "terminal_switch_reject_count",
        "constraint_violation_count",
        "human_override_count",
    }

    assert set(MetricsCollector().compute_episode("episode").metric_names()) == required
