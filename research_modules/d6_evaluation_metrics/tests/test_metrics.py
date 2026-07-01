from __future__ import annotations

import math

import pytest

from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
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
        "constraint_violation_count",
        "human_override_count",
    }

    assert set(MetricsCollector().compute_episode("episode").metric_names()) == required
