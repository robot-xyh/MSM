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


def test_episode_scale_counts_use_runtime_counts_not_scenario_name() -> None:
    collector = MetricsCollector()

    metrics = collector.compute_episode(
        "blocks_cv_5v5_runtime_n3",
        truth_summary={
            "drone_count": 3,
            "resource_count": 3,
            "target_count": 4,
            "camera_count": 6,
            "metric_scope": "contract_metrics",
            "scenario": {"name": "blocks_cv_5v5"},
        },
    )

    assert metrics.scenario_group == "blocks_cv_5v5"
    assert metrics.metric_scope == "contract"
    assert metrics.drone_count == 3
    assert metrics.resource_count == 3
    assert metrics.target_count == 4
    assert metrics.camera_count == 6
    assert metrics.metadata["drone_count"] == 3
    assert metrics.metadata["resource_count"] == 3
    assert metrics.metadata["target_count"] == 4
    assert metrics.metadata["camera_count"] == 6
    assert metrics.metadata["metric_scope"] == "contract"


def test_active_degradation_review_labels_and_posterior_rules() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=1.0,
                event_type="d4_active_degradation_decision",
                metadata={"review_label": "necessary"},
            ),
            EventRecord(
                timestamp=2.0,
                event_type="d4_active_degradation_decision",
                metadata={"review_label": "false_positive"},
            ),
            EventRecord(
                timestamp=3.0,
                event_type="d4_active_degradation_decision",
                metadata={
                    "pre_window_risk_score": 0.8,
                    "post_window_risk_score": 0.2,
                },
            ),
            EventRecord(
                timestamp=4.0,
                event_type="d4_active_degradation_decision",
                metadata={"trigger_reason": "operator_probe"},
            ),
        ]
    )

    metrics = collector.compute_episode("active_review_fixture")

    assert metrics.active_degradation_count == 4
    assert metrics.active_degradation_precision == pytest.approx(2.0 / 3.0)
    assert metrics.unnecessary_active_degradation_count == 1
    assert metrics.metadata["active_degradation_reviewed_count"] == 3
    assert metrics.metadata["active_degradation_necessary_count"] == 2
    assert metrics.metadata["active_degradation_review_label_counts"] == {
        "false_positive": 1,
        "necessary": 1,
        "risk_reduced": 1,
    }


def test_blocks_2v2_degradation_reassignment_png_metrics() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=1.0,
                event_type="d4_active_degradation_decision",
                metadata={
                    "mode": "active_degradation",
                    "action": "degrade_to_secondary",
                    "assignment_phase": "secondary_reassignment",
                },
            ),
            EventRecord(
                timestamp=1.2,
                event_type="d7_control_command",
                actor_id="INT-01",
                metadata={
                    "resource_id": "INT-01",
                    "target_id": "TGT-001",
                    "mode": "radar_midcourse",
                    "terminal_switch_allowed": False,
                    "terminal_switch_reject_reason": "d4_reassign_pending",
                },
            ),
            EventRecord(
                timestamp=2.0,
                event_type="d7_control_command",
                actor_id="INT-01",
                metadata={
                    "resource_id": "INT-01",
                    "target_id": "TGT-001",
                    "mode": "vision_terminal",
                    "guidance_law": "png_vm",
                    "mode_switch": True,
                    "terminal_switch_allowed": True,
                    "terminal_mode_entered": True,
                },
            ),
            EventRecord(
                timestamp=2.1,
                event_type="terminal_lock",
                actor_id="INT-01",
                metadata={
                    "assigned_global_track_id": "TGT-001",
                    "local_track_id": "L-VIS-001",
                },
            ),
        ]
    )

    metrics = collector.compute_episode("blocks_2v2_active_degrade")

    assert metrics.active_degradation_count == 1
    assert metrics.secondary_node_takeover_count == 1
    assert metrics.secondary_reassignment_count == 1
    assert metrics.d4_reassign_pending_count == 1
    assert metrics.terminal_lock_count == 1
    assert metrics.visual_png_switch_count == 1
    assert metrics.terminal_switch_allowed_rate == pytest.approx(0.5)
    assert metrics.terminal_switch_reject_count == 1


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
    assert metrics.terminal_lock_count == 2


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
                    "los_quality_gate_passed": True,
                    "maneuver_margin_gate_pass": False,
                    "terminal_switch_allowed": False,
                },
            ),
            EventRecord(
                timestamp=13.5,
                event_type="terminal_switch_rejected",
                metadata={
                    "guidance_law": "pn",
                    "terminal_switch_reject_reason": "camera_quality",
                    "camera_quality_gate_passed": False,
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
    assert metrics.terminal_switch_allowed_rate == pytest.approx(0.0)
    assert metrics.terminal_switch_reject_count == 1
    assert metrics.gate_reject_count == 1
    assert metrics.metadata["guidance_law_counts"] == {"pn": 2}
    assert metrics.metadata["terminal_switch_reject_reasons"] == {"camera_quality": 1}


def test_secondary_sensing_metrics_use_actual_target_and_camera_counts() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=0.0,
                event_type="secondary_coverage_frame",
                actor_id="fixed-node",
                metadata={
                    "secondary_node_type": "fixed_downlook_secondary",
                    "frame_id": "f0",
                    "covered_target_ids": ["T1", "T2"],
                    "single_camera_full_view_count": 1,
                    "single_camera_total_count": 2,
                },
            ),
            EventRecord(
                timestamp=0.0,
                event_type="secondary_coverage_frame",
                actor_id="mobile-recon",
                metadata={
                    "secondary_node_type": "mobile_recon_gimbal",
                    "frame_id": "f0",
                    "covered_target_ids": ["T3"],
                    "single_camera_full_view_count": 0,
                    "single_camera_total_count": 1,
                    "cue_pointing_error_deg": 4.0,
                    "gimbal_pointing_error_deg": 2.0,
                },
            ),
            EventRecord(
                timestamp=1.0,
                event_type="secondary_coverage_frame",
                actor_id="fixed-node",
                metadata={
                    "secondary_node_type": "fixed_downlook_secondary",
                    "frame_id": "f1",
                    "covered_target_ids": ["T1"],
                    "single_camera_full_view_count": 0,
                    "single_camera_total_count": 2,
                },
            ),
            EventRecord(
                timestamp=1.0,
                event_type="secondary_coverage_frame",
                actor_id="mobile-recon",
                metadata={
                    "secondary_node_type": "mobile_recon_gimbal",
                    "frame_id": "f1",
                    "covered_target_ids": ["T2"],
                    "single_camera_full_view_count": 0,
                    "single_camera_total_count": 1,
                    "cue_pointing_error_deg": 2.0,
                    "gimbal_pointing_error_deg": 4.0,
                },
            ),
            EventRecord(
                timestamp=2.0,
                event_type="d5_cross_view_association",
                metadata={
                    "secondary_node_type": "fixed_downlook_secondary",
                    "target_id": "T1",
                    "association_success": True,
                },
            ),
            EventRecord(
                timestamp=3.0,
                event_type="d5_registration_miss",
                metadata={
                    "secondary_node_type": "mobile_recon_gimbal",
                    "target_id": "T2",
                    "detect_available": True,
                    "d5_registered": False,
                },
            ),
        ]
    )

    metrics = collector.compute_episode(
        "blocks_cv_5v5_secondary_sensing_n3",
        truth_summary={
            "target_count": 3,
            "camera_count": 6,
            "resource_count": 3,
            "drone_count": 3,
            "scenario": {"name": "blocks_cv_5v5"},
        },
    )

    assert metrics.target_count == 3
    assert metrics.camera_count == 6
    assert metrics.secondary_network_joint_full_view_frame_rate == pytest.approx(0.5)
    assert metrics.secondary_network_mean_coverage_ratio == pytest.approx(5.0 / 6.0)
    assert metrics.secondary_single_camera_full_view_frame_rate == pytest.approx(
        1.0 / 6.0
    )
    assert metrics.cross_view_association_count == 1
    assert metrics.secondary_detect_available_but_not_registered_count == 1
    assert metrics.cue_pointing_error_count == 2
    assert metrics.cue_pointing_error_mean_deg == pytest.approx(3.0)
    assert metrics.cue_pointing_error_rmse_deg == pytest.approx(math.sqrt(10.0))
    assert metrics.gimbal_pointing_error_count == 2
    assert metrics.gimbal_pointing_error_mean_deg == pytest.approx(3.0)
    assert metrics.gimbal_pointing_error_rmse_deg == pytest.approx(math.sqrt(10.0))
    node_metrics = metrics.metadata["secondary_sensing_node_type_metrics"]
    assert set(node_metrics) == {"fixed_downlook_secondary", "mobile_recon_gimbal"}
    assert node_metrics["fixed_downlook_secondary"][
        "secondary_network_mean_coverage_ratio"
    ] == pytest.approx(0.5)
    assert node_metrics["mobile_recon_gimbal"]["gimbal_pointing_error_count"] == 2


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
        "active_degradation_count",
        "active_degradation_precision",
        "unnecessary_active_degradation_count",
        "passive_failover_count",
        "secondary_node_takeover_count",
        "secondary_reassignment_count",
        "d4_reassign_pending_count",
        "distributed_fallback_count",
        "failover_active_window_delta_s",
        "terminal_association_accuracy",
        "terminal_id_switch_count",
        "ambiguous_fov_event_count",
        "friend_overlap_hold_count",
        "time_to_terminal_lock",
        "terminal_lock_count",
        "multi_view_consensus_rate",
        "cross_view_conflict_count",
        "duplicate_terminal_lock_count",
        "secondary_network_joint_full_view_frame_rate",
        "secondary_network_mean_coverage_ratio",
        "secondary_single_camera_full_view_frame_rate",
        "cross_view_association_count",
        "secondary_detect_available_but_not_registered_count",
        "cue_pointing_error_count",
        "cue_pointing_error_mean_deg",
        "cue_pointing_error_rmse_deg",
        "cue_pointing_error_max_deg",
        "gimbal_pointing_error_count",
        "gimbal_pointing_error_mean_deg",
        "gimbal_pointing_error_rmse_deg",
        "gimbal_pointing_error_max_deg",
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
        "terminal_switch_allowed_rate",
        "visual_png_switch_count",
        "terminal_takeover_rate",
        "terminal_switch_reject_count",
        "mode_switch_count",
        "terminal_contract_reject_count",
        "intercept_success_count",
        "collision_intercept_count",
        "range_intercept_count",
        "time_to_intercept_s",
        "min_range_m",
        "gate_reject_count",
        "constraint_violation_count",
        "human_override_count",
    }

    assert set(MetricsCollector().compute_episode("episode").metric_names()) == required
