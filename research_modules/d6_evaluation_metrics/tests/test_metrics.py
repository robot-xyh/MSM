from __future__ import annotations

import math

import pytest

from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    STANDARD_MAPPING_VERSION,
    TerminalRecord,
    TrackRecord,
    standard_metric_families,
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
    assert metrics.false_alarm_rate == pytest.approx(0.0)
    assert metrics.missed_detection_rate == pytest.approx(0.25)
    assert metrics.track_rmse == pytest.approx(math.sqrt(25.0 / 3.0))
    assert metrics.track_continuity == pytest.approx(0.75)
    assert metrics.id_switch_count == 1


def test_detection_metrics_require_offline_truth_mapping_and_ignore_truthless_tracks() -> None:
    collector = MetricsCollector()
    collector.extend_tracks(
        [
            TrackRecord(0.0, "G1", None),
            TrackRecord(1.0, "G2", None),
        ]
    )

    unavailable = collector.compute_episode("truthless", duration=2.0)

    assert unavailable.detection_probability is None
    assert unavailable.missed_detection_rate is None
    assert unavailable.false_alarm_rate is None
    for name in (
        "detection_probability",
        "missed_detection_rate",
        "false_alarm_rate",
    ):
        assert unavailable.metric_availability[name]["status"] == "unavailable"

    collector.add_track(TrackRecord(1.0, "G-UNKNOWN", "UNKNOWN"))
    collector.extend_events(
        [
            EventRecord(
                0.0,
                "offline_detection_miss",
                metadata={"truth_id": "T1", "truth_timestamp": 0.0},
            ),
            EventRecord(
                1.0,
                "offline_detection_miss",
                metadata={"truth_id": "T1", "truth_timestamp": 1.0},
            ),
        ]
    )
    scored = collector.compute_episode(
        "truth",
        duration=2.0,
        truth_summary={"truth_timestamps": {"T1": [0.0, 1.0]}},
    )

    assert scored.detection_probability == 0.0
    assert scored.missed_detection_rate == 1.0
    assert scored.false_alarm_rate == pytest.approx(0.5)
    assert scored.metric_availability["false_alarm_rate"]["numerator"] == 1
    assert scored.metadata["offline_detection_pair_evidence"] == {
        "track_match_count": 0,
        "explicit_match_count": 0,
        "explicit_miss_count": 2,
    }


def test_detection_metrics_unavailable_with_truth_opportunities_but_truthless_tracks() -> None:
    collector = MetricsCollector()
    collector.extend_tracks(
        [
            TrackRecord(0.0, "G1", None),
            TrackRecord(1.0, "G1", None),
        ]
    )

    metrics = collector.compute_episode(
        "airsim-truth-isolated",
        duration=2.0,
        truth_summary={"truth_timestamps": {"T1": [0.0, 1.0]}},
    )

    assert metrics.detection_probability is None
    assert metrics.missed_detection_rate is None
    assert metrics.false_alarm_rate is None
    for name in (
        "detection_probability",
        "missed_detection_rate",
        "false_alarm_rate",
    ):
        availability = metrics.metric_availability[name]
        assert availability["status"] == "unavailable"
        assert "offline detection/track-to-truth" in availability["reason"]
    assert metrics.metadata["offline_detection_pair_evidence"] == {
        "track_match_count": 0,
        "explicit_match_count": 0,
        "explicit_miss_count": 0,
    }


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
    assert metrics.active_degradation_label_count == 3
    assert metrics.unnecessary_active_degradation_count == 1
    assert metrics.metadata["active_degradation_reviewed_count"] == 3
    assert metrics.metadata["active_degradation_necessary_count"] == 2
    assert metrics.metadata["active_degradation_review_label_counts"] == {
        "false_positive": 1,
        "necessary": 1,
        "risk_reduced": 1,
    }


def test_active_degradation_precision_is_unavailable_without_review_labels() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=1.0,
                event_type="d4_active_degradation_decision",
                metadata={"trigger_reason": "unreviewed_trigger"},
            )
        ]
    )

    metrics = collector.compute_episode("unreviewed_active_degradation")

    assert metrics.active_degradation_count == 1
    assert metrics.active_degradation_precision is None
    assert metrics.active_degradation_label_count == 0
    assert metrics.unnecessary_active_degradation_count == 0


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


def test_mission_root_cause_performance_and_eval_tracking_fields() -> None:
    collector = MetricsCollector()
    collector.extend_tracks(
        [
            TrackRecord(
                timestamp=0.0,
                global_track_id="G-T1-A",
                truth_id="T1",
                position=(0.0, 0.0),
                truth_position=(0.0, 0.0),
            ),
            TrackRecord(
                timestamp=1.0,
                global_track_id="G-T1-B",
                truth_id="T1",
                position=(1.0, 0.0),
                truth_position=(1.0, 0.0),
            ),
        ]
    )
    collector.extend_events(
        [
            EventRecord(
                timestamp=1.2,
                event_type="terminal_switch_rejected",
                metadata={
                    "terminal_switch_reject_reason": "camera_quality",
                    "camera_quality_gate_pass": False,
                    "terminal_handover_pending": True,
                    "terminal_switch_allowed": False,
                },
            ),
            EventRecord(
                timestamp=1.5,
                event_type="secondary_coverage_frame",
                metadata={
                    "secondary_node_type": "mobile_recon_gimbal",
                    "frame_id": "f0",
                    "covered_target_ids": ["T1"],
                    "target_count": 2,
                },
            ),
            EventRecord(
                timestamp=2.0,
                event_type="module_performance",
                actor_id="D6",
                metadata={
                    "module": "D6",
                    "module_duration_ms": 12.0,
                    "loop_latency_s": 0.02,
                    "record_latency_ms": 3.0,
                    "cpu_budget_utilization": 0.5,
                    "gpu_usage_percent": 10.0,
                    "budget_exceeded": True,
                },
            ),
        ]
    )

    metrics = collector.compute_episode(
        episode_id="p0_eval_tracking",
        truth_summary={
            "target_count": 2,
            "required_intercept_count": 2,
            "high_threat_by_timestamp": {0.0: ["T1", "T2"]},
            "eval_priority": "P0-A",
            "implementation_status": "implemented",
            "evidence_path": "outputs/p0_eval_tracking/main_episode_bus_metrics.json",
        },
    )

    assert metrics.mission_outcome == "partial"
    assert metrics.eval_priority == "P0-A"
    assert metrics.implementation_status == "implemented"
    assert metrics.evidence_path.endswith("main_episode_bus_metrics.json")
    assert metrics.module_duration_ms == pytest.approx(12.0)
    assert metrics.loop_latency_ms == pytest.approx(20.0)
    assert metrics.record_latency_ms == pytest.approx(3.0)
    assert metrics.cpu_budget_utilization == pytest.approx(0.5)
    assert metrics.gpu_budget_utilization == pytest.approx(0.1)
    assert metrics.performance_budget_violation_count == 1
    assert metrics.metadata["performance"]["module_duration_ms"]["count"] == 1
    assert metrics.metadata["performance"]["cpu_budget"]["placeholder"] is False

    causes = {item["cause"] for item in metrics.metadata["top_failure_causes"]}
    assert {"tracking", "assignment", "terminal_gate", "guidance", "coverage"} <= causes
    assert metrics.metadata["root_cause"] in causes
    assert "intercept_success_count=0/2" in str(
        metrics.metadata["failure_cause_details"]["guidance"]
    )


def test_explicit_mission_outcome_and_runtime_exception_abort() -> None:
    explicit = MetricsCollector().compute_episode(
        "explicit_success",
        truth_summary={
            "mission_outcome": "success",
            "success_reason": "all_required_targets_intercepted",
            "eval_priority": "P0-C",
            "implementation_status": "implemented",
            "evidence_path": "reports/episode_metrics.csv",
        },
    )

    assert explicit.mission_outcome == "success"
    assert explicit.success_reason == "all_required_targets_intercepted"
    assert explicit.eval_priority == "P0-C"
    assert explicit.evidence_path == "reports/episode_metrics.csv"

    collector = MetricsCollector()
    collector.add_event(
        EventRecord(
            timestamp=3.0,
            event_type="runtime_exception",
            severity="fatal",
            metadata={"failure_cause": "runtime_exception"},
        )
    )

    aborted = collector.compute_episode("runtime_abort")

    assert aborted.mission_outcome == "aborted"
    assert aborted.metadata["root_cause"] == "runtime_exception"
    assert aborted.metadata["top_failure_causes"][0]["cause"] == "runtime_exception"


def test_standard_mapping_metadata_and_non_numeric_fields() -> None:
    collector = MetricsCollector()
    collector.add_event(
        EventRecord(
            timestamp=0.0,
            event_type="scenario_metadata",
            metadata={
                "scenario_version": "event-scenario-v1",
                "standard_mapping_version": STANDARD_MAPPING_VERSION,
            },
        )
    )

    metrics = collector.compute_episode(
        episode_id="standard_mapping_fixture",
        truth_summary={
            "scenario": {
                "name": "blocks_cv_5v5",
                "scenario_version": "scenario-v2",
            },
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
        },
    )

    assert metrics.scenario_version == "scenario-v2"
    assert metrics.standard_mapping_version == STANDARD_MAPPING_VERSION
    assert "mission/root cause=" in metrics.standard_metric_family_summary
    assert "reproducibility/evidence=" in metrics.standard_metric_family_summary
    assert metrics.metadata["scenario_version"] == "scenario-v2"
    assert metrics.metadata["standard_mapping_version"] == STANDARD_MAPPING_VERSION
    assert metrics.metadata["standard_metric_families"] == standard_metric_families()
    assert metrics.metadata["standard_mapping"]["version"] == STANDARD_MAPPING_VERSION
    assert metrics.metadata["standard_mapping"]["mapped_metric_count"] > 0
    assert "scenario_version" not in metrics.metric_names()
    assert "standard_mapping_version" not in metrics.metric_names()
    assert "standard_metric_family_summary" not in metrics.metric_names()


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
        "governance_schema_provenance_rate",
        "governance_config_provenance_rate",
        "governance_schema_mismatch_count",
        "d1_oosm_observation_rate",
        "d1_stale_observation_rate",
        "d1_replay_observation_rate",
        "d1_mean_delay_s",
        "d1_max_delay_s",
        "d1_region_quality_coverage_rate",
        "d1_region_mean_a95_m",
        "d1_region_handover_readiness_mean",
        "d1_degraded_region_count",
        "d2_soft_risk_frame_rate",
        "d2_hard_risk_frame_rate",
        "d2_max_association_risk",
        "d2_nis_mean",
        "d2_nis_in_confidence_rate",
        "d2_nees_mean",
        "d2_nees_in_confidence_rate",
        "d2_false_track_count",
        "d2_false_track_rate",
        "d3_resource_target_ratio",
        "d3_assignment_coverage_rate",
        "d3_unassigned_target_rate",
        "d3_hysteresis_reject_rate",
        "d3_stale_reject_rate",
        "d3_feedback_accept_rate",
        "d3_feedback_sample_count",
        "failover_time",
        "consensus_rounds",
        "degraded_completion_rate",
        "active_degradation_count",
        "active_degradation_precision",
        "active_degradation_label_count",
        "unnecessary_active_degradation_count",
        "passive_failover_count",
        "secondary_node_takeover_count",
        "secondary_reassignment_count",
        "d4_reassign_pending_count",
        "distributed_fallback_count",
        "failover_active_window_delta_s",
        "secondary_registration_usable_dwell_s",
        "secondary_takeover_ready_dwell_s",
        "secondary_plan_pending_dwell_s",
        "secondary_plan_active_dwell_s",
        "secondary_activation_latency_s",
        "secondary_takeover_fallback_count",
        "secondary_lease_expiry_count",
        "stale_plan_reject_count",
        "terminal_association_accuracy",
        "terminal_id_switch_count",
        "ambiguous_fov_event_count",
        "friend_overlap_hold_count",
        "time_to_terminal_lock",
        "terminal_lock_count",
        "multi_view_consensus_rate",
        "cross_view_conflict_count",
        "duplicate_terminal_lock_count",
        "visual_detection_recall",
        "local_id_continuity",
        "cross_view_registration_rate",
        "visual_pipeline_latency_ms",
        "visual_cpu_budget_utilization",
        "visual_gpu_budget_utilization",
        "visual_budget_violation_count",
        "online_truth_field_violation_count",
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
        "contract_evaluated_count",
        "contract_allowed_count",
        "contract_allowed_rate",
        "control_evaluated_count",
        "control_allowed_count",
        "control_allowed_rate",
        "mode_switched_count",
        "physical_intercept_count",
        "pair_physical_success_count",
        "pair_physical_success_rate",
        "target_intercept_success_count",
        "target_intercept_success_rate",
        "coalition_completion_count",
        "coalition_completion_rate",
        "detection_acquisition_timeout_count",
        "image_kf_predict_count",
        "blind_push_count",
        "visual_reacquisition_count",
        "terminal_visual_lost_after_coast_count",
        "truth_identity_online_use_count",
        "terminal_filter_measured_count",
        "terminal_filter_predicted_count",
        "terminal_filter_innovation_rejected_count",
        "terminal_filter_reset_count",
        "terminal_filter_expired_count",
        "ttc_area_jump_reject_count",
        "ttc_bbox_clipping_reject_count",
        "ttc_not_expanding_reject_count",
        "ttc_out_of_range_reject_count",
        "soft_prediction_count",
        "soft_prediction_duration_s",
        "soft_prediction_expired_count",
        "terminal_coast_count",
        "terminal_coast_duration_s",
        "terminal_coast_expired_count",
        "terminal_lock_continuity",
        "visual_mode_duration_s",
        "command_discontinuity_mean_mps",
        "command_discontinuity_max_mps",
        "intercept_success_count",
        "collision_intercept_count",
        "range_intercept_count",
        "time_to_intercept_s",
        "min_range_m",
        "gate_reject_count",
        "constraint_violation_count",
        "human_override_count",
        "module_duration_ms",
        "loop_latency_ms",
        "record_latency_ms",
        "cpu_budget_utilization",
        "gpu_budget_utilization",
        "performance_budget_violation_count",
    }

    required.update(
        {
            "target_demand_satisfaction_rate_micro",
            "target_demand_satisfaction_rate_macro",
            "unmet_slot_count",
            "over_support_count",
            "coalition_formation_time_s",
            "coalition_reconfiguration_time_s",
            "simultaneous_arrival_dispersion_s",
            "common_window_success_rate",
            "wave_interval_s",
            "wave_order_violation_count",
            "primary_success_rate",
            "reserve_activation_count",
            "reserve_activation_rate",
            "reserve_activation_latency_s",
            "planned_cooperative_lock_count",
            "planned_cooperative_lock_success_rate",
            "authorized_cooperative_lock_count",
            "erroneous_duplicate_lock_count",
            "same_resource_lock_continuity_count",
            "replan_request_count",
            "replan_request_deduplicated_count",
            "replan_no_change_ack_count",
            "replan_applied_count",
            "replan_expired_count",
            "replan_pending_dwell_s",
            "replan_convergence_time_s",
            "coalition_commit_count",
            "coalition_required_member_count",
            "coalition_acked_member_count",
            "coalition_member_ack_rate",
            "coalition_ack_latency_s",
            "coalition_commit_timeout_count",
            "coalition_commit_aborted_count",
            "coalition_commit_reconfiguring_count",
            "coalition_commit_lease_expired_count",
            "secondary_coalition_commit_count",
            "distributed_coalition_commit_count",
            "coalition_member_loss_count",
            "coalition_member_replacement_count",
            "coalition_member_replacement_time_s",
            "coalition_digest_conflict_count",
            "coalition_stale_rejection_count",
            "coalition_stale_rejection_rate",
            "messages_sent_count",
            "messages_delivered_count",
            "messages_dropped_count",
            "payload_bytes_sent",
            "payload_bytes_delivered",
            "coalition_consensus_rounds",
            "end_to_end_latency_ms",
            "minimum_member_separation_m",
            "collision_risk_exposure_s",
            "geometry_rejection_count",
            "geometry_rejection_rate",
            "canonical_duplicate_count",
            "cross_node_id_switch_count",
            "common_information_duplicate_rejection_count",
            "common_information_duplicate_rejection_rate",
        }
    )

    assert set(MetricsCollector().compute_episode("episode").metric_names()) == required


def test_terminal_execution_funnel_separates_cv_contract_from_physical_intercept() -> None:
    cv_collector = MetricsCollector()
    cv_collector.extend_events(
        [
            EventRecord(
                1.0,
                "d7_guidance_record",
                actor_id="R1",
                metadata={
                    "resource_id": "R1",
                    "target_id": "G1",
                    "terminal_switch_allowed": True,
                    "d7_runtime_terminal_switch_allowed": False,
                    "mode_switch": False,
                },
            ),
            EventRecord(
                2.0,
                "d7_guidance_record",
                actor_id="R1",
                metadata={
                    "resource_id": "R1",
                    "target_id": "G1",
                    "terminal_switch_allowed": True,
                    "d7_runtime_terminal_switch_allowed": True,
                    "mode_switch": True,
                },
            ),
        ]
    )

    cv_metrics = cv_collector.compute_episode("cv-contract-only")

    assert cv_metrics.contract_evaluated_count == 2
    assert cv_metrics.contract_allowed_count == 2
    assert cv_metrics.contract_allowed_rate == 1.0
    assert cv_metrics.control_evaluated_count == 2
    assert cv_metrics.control_allowed_count == 1
    assert cv_metrics.control_allowed_rate == 0.5
    assert cv_metrics.mode_switched_count == 1
    assert cv_metrics.physical_intercept_count is None
    assert cv_metrics.intercept_success_count == 0
    assert cv_metrics.metadata["physical_intercept_evidence_available"] is False

    physical_collector = MetricsCollector()
    physical_collector.add_event(
        EventRecord(
            3.0,
            "d7_control_command",
            actor_id="R2",
            metadata={
                "resource_id": "R2",
                "target_id": "G2",
                "terminal_contract_allowed": True,
                "terminal_switch_allowed": True,
                "mode_switch": True,
                "status": "collision_intercept",
            },
        )
    )

    physical_metrics = physical_collector.compute_episode("physical")

    assert physical_metrics.contract_allowed_count == 1
    assert physical_metrics.control_allowed_count == 1
    assert physical_metrics.mode_switched_count == 1
    assert physical_metrics.physical_intercept_count == 1
    assert physical_metrics.intercept_success_count == 1
    assert physical_metrics.metadata["physical_intercept_evidence_available"] is True
