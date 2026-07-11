from __future__ import annotations

import json

from d2_data_association import (
    InitializationGovernanceProfile,
    RiskThresholds,
    build_5v5_replay_fixture,
    run_airsim_replay_association,
    run_airsim_dry_run_association,
    run_threshold_sensitivity,
)


def test_governed_5v5_replay_isolates_truth_and_reports_p1_metrics() -> None:
    frames = build_5v5_replay_fixture(seed=17, steps=12)
    report = run_airsim_replay_association(
        frames,
        replay_name="5v5_crossing_dense_governance",
        risk_thresholds=RiskThresholds(
            profile_name="d2_5v5_p1",
            profile_version="2026-07-11",
        ),
    )

    metrics = report.metrics
    offline = report.offline_truth_evaluation
    assert report.frame_count == 12
    assert report.target_count == 5
    assert report.online_metrics["truth_metrics_available"] is False
    assert report.online_metrics["confusion_matrix"] == {}
    assert metrics["online_truth_isolated"] is True
    assert metrics["truth_metrics_available"] is True
    assert metrics["truth_target_count"] == 5
    assert metrics["initialization_success_rate"] == 1.0
    assert metrics["confirmation_success_rate"] == 1.0
    assert metrics["initialization_profile"]["required_hits_m"] == 2
    assert metrics["initialization_profile"]["window_scans_n"] == 3
    assert metrics["m_of_n_initialization_success_rate"] == 1.0
    assert metrics["missed_truth_detection_count"] == 2
    assert metrics["false_alarm_detection_count"] == 3
    assert metrics["n_m_mismatch_frame_count"] > 0
    assert metrics["false_track_count"] >= 1
    assert metrics["nis"]["available"] is True
    assert metrics["nis"]["count"] > 0
    assert metrics["nees"]["available"] is True
    assert metrics["nees"]["count"] > 0
    assert metrics["online_truth_isolation_violations"] == 0
    assert offline["profile_version"] == "2026-07-11"
    assert len(offline["frame_metrics"]) == 12

    for log in report.association_logs:
        metadata = log["metadata"]
        assert metadata["risk_profile"] == "d2_5v5_p1"
        assert metadata["risk_profile_version"] == "2026-07-11"
        assert metadata["association_log_schema_version"] == (
            "d2-association-log/v2"
        )
        assert metadata["online_truth_isolated"] is True
        assert "offline_truth_labels" not in metadata
        assert "truth_label_usage" not in metadata
        assert "truth_target_count_m" not in metadata
        assert "nees_available_offline" not in metadata
        assert "track_order" in metadata
        assert "detection_order" in metadata
        assert all(
            detection_id.startswith("online-detection-")
            for detection_id in metadata["detection_order"]
        )


def test_5v5_gate_sensitivity_carries_initialization_false_track_and_consistency() -> None:
    frames = build_5v5_replay_fixture(seed=23, steps=10)
    rows = run_threshold_sensitivity(
        frames,
        gate_thresholds=[5.99, 9.21],
        risk_thresholds=[
            RiskThresholds(
                profile_name="p1_governed",
                profile_version="v2",
            )
        ],
        initialization_profile=InitializationGovernanceProfile(
            profile_name="strict_3_of_4",
            profile_version="v3",
            required_hits_m=3,
            window_scans_n=4,
        ),
    )

    assert len(rows) == 2
    for row in rows:
        assert row["target_count"] == 5
        assert row["risk_profile_version"] == "v2"
        assert row["initialization_success_rate"] > 0.0
        assert row["initialization_profile"] == {
            "profile_name": "strict_3_of_4",
            "profile_version": "v3",
            "required_hits_m": 3,
            "window_scans_n": 4,
        }
        assert row["false_track_count"] >= 1
        assert row["false_track_rate"] > 0.0
        assert row["nis"]["available"] is True
        assert row["nees"]["available"] is True
        assert row["offline_truth_evaluation"]["truth_label_usage"] == (
            "offline_evaluator_only"
        )


def test_fixture_scale_is_data_driven_and_contains_all_stressors() -> None:
    frames = build_5v5_replay_fixture(
        seed=5,
        steps=8,
        missed_detection_frames=(2,),
        false_alarm_frames=(4,),
    )

    assert len(frames) == 8
    assert all(len(frame["truth_ids_present"]) == 5 for frame in frames)
    assert len(frames[2]["detections"]) == 4
    assert len(frames[4]["detections"]) == 6
    assert frames[4]["detections"][-1]["is_false_alarm"] is True
    tags = frames[0]["replay_metadata"]["scenario_tags"]
    assert {"5v5", "crossing", "dense", "missed_detection", "false_alarm"} <= set(tags)


def test_no_truth_replay_still_reports_online_nis_and_keeps_nees_unavailable() -> None:
    frames = [
        {
            "timestamp": float(frame_index),
            "detections": [
                {
                    "detection_id": f"measurement-{frame_index}",
                    "position": [float(frame_index), 0.0],
                    "covariance": [[0.2, 0.0], [0.0, 0.2]],
                }
            ],
        }
        for frame_index in range(4)
    ]

    report = run_airsim_replay_association(frames)

    assert report.metrics["truth_metrics_available"] is False
    assert report.metrics["nis"]["available"] is True
    assert report.metrics["nis"]["count"] == 3
    assert report.metrics["nees"]["available"] is False
    assert report.metrics["nees"]["count"] == 0


def test_actor_identity_and_nested_truth_do_not_enter_online_frames_or_logs() -> None:
    frames = [
        {
            "timestamp": float(frame_index),
            "target_count": 1,
            "detections": [
                {
                    "name": "BP_Intruder_Truth_01",
                    "position": [float(frame_index), 0.0],
                    "covariance": [[0.2, 0.0], [0.0, 0.2]],
                    "offline_truth_label": "target-secret",
                    "offline_truth_state": [float(frame_index), 0.0, 1.0, 0.0],
                    "metadata": {
                        "actor_name": "BP_Intruder_Truth_01",
                        "nested": {
                            "truth_id": "target-secret",
                            "measurement_quality": "stable",
                        },
                    },
                }
            ],
            "truth_ids_present": ["target-secret"],
        }
        for frame_index in range(3)
    ]

    online_result = run_airsim_dry_run_association(
        frames,
        isolate_offline_truth=True,
    )
    online_payload = json.dumps(
        {
            "frames": [frame.to_dict() for frame in online_result.frames],
            "logs": online_result.association_logs,
            "active_tracks": online_result.active_tracks,
        },
        sort_keys=True,
    )
    report = run_airsim_replay_association(frames)

    assert "BP_Intruder_Truth_01" not in online_payload
    assert "target-secret" not in online_payload
    assert "truth_id" not in online_payload
    assert all(
        detection_id.startswith("online-detection-")
        for log in report.association_logs
        for detection_id in log["metadata"]["detection_order"]
    )
    assert report.metrics["online_truth_isolation_violations"] == 0
    assert report.offline_truth_evaluation["summary"]["truth_target_count"] == 1
