from __future__ import annotations

import inspect
import json


from d2_data_association import (
    AssociationRiskSummary,
    RiskThresholds,
    classify_risk_summary,
    load_airsim_replay_frames,
    run_airsim_replay_association,
    run_threshold_sensitivity,
    summarize_multi_seed_risk_calibration,
    write_association_logs_jsonl,
    write_replay_association_report,
)
import d2_data_association.replay as replay_module


def dense_airsim_like_frames(target_count: int = 5, steps: int = 6) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    starts = [-3.0, -2.0, -1.0, 3.0, 2.0]
    directions = [1.0, 1.0, 1.0, -1.0, -1.0]
    y_offsets = [-0.20, -0.08, 0.04, 0.12, 0.22]
    for step in range(steps):
        detections = []
        for index in range(target_count):
            truth_id = f"dense-target-{index}"
            x = starts[index] + directions[index] * step * 0.8
            y = y_offsets[index] + (0.02 * step if index % 2 == 0 else -0.02 * step)
            detections.append(
                {
                    "detection_id": f"det-{step}-{index}",
                    "truth_id": truth_id,
                    "position": {"x_val": x, "y_val": y, "z_val": -20.0},
                    "covariance_ned": [[0.18, 0.0, 0.0], [0.0, 0.18, 0.0], [0.0, 0.0, 0.8]],
                    "truth_position": [x, y],
                    "feature": [1.0 if feature_index == index else 0.0 for feature_index in range(target_count)],
                    "metadata": {
                        "source_node_id": "airsim-cv-replay",
                        "link_type": "computer_vision_metadata",
                        "frame_index": step,
                    },
                }
            )
        frames.append(
            {
                "timestamp": float(step),
                "detections": detections,
                "truth_ids_present": [f"dense-target-{index}" for index in range(target_count)],
            }
        )
    return frames


def test_airsim_jsonl_replay_runs_5_target_association_and_writes_logs(tmp_path) -> None:
    frames = dense_airsim_like_frames()
    replay_path = tmp_path / "airsim_dense_5v5.jsonl"
    replay_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "event": "d2_frame",
                    "seed": 11,
                    "episode_id": "episode-011",
                    "scenario_name": "airsim_dense_5v5",
                    "drone_count": 5,
                    "frame": frame,
                }
            )
            for frame in frames
        )
    )

    loaded_frames = load_airsim_replay_frames(replay_path)
    report = run_airsim_replay_association(
        loaded_frames,
        replay_name="airsim_dense_5v5",
        risk_thresholds=RiskThresholds(
            profile_name="p1_calibration",
            profile_version="2026-07-08",
        ),
        gate_thresholds=[5.99, 9.21],
    )

    assert report.frame_count == len(frames)
    assert report.target_count == 5
    assert report.metrics["frame_count"] == len(frames)
    assert report.replay_metadata["seed"] == 11
    assert report.replay_metadata["episode_id"] == "episode-011"
    assert report.replay_metadata["scenario_name"] == "airsim_dense_5v5"
    assert report.replay_metadata["drone_count"] == 5
    assert "id_switch_count" in report.metrics
    assert "track_continuity" in report.metrics
    assert "duplicate_assignment_count" in report.metrics
    assert len(report.association_logs) == len(frames)
    assert len(report.global_track_ids) == 5
    assert report.risk_summary["id_switch_count"] == report.metrics["id_switch_count"]
    assert report.risk_summary["thresholds"]["profile_version"] == "2026-07-08"
    assert "soft_risk_frame_count" in report.risk_summary
    assert "hard_risk_frame_count" in report.risk_summary
    assert len(report.threshold_sensitivity) == 2
    for row in report.threshold_sensitivity:
        assert row["target_count"] == 5
        assert row["seed"] == 11
        assert row["episode_id"] == "episode-011"
        assert row["scenario_name"] == "airsim_dense_5v5"
        assert row["drone_count"] == 5
        assert row["risk_profile"] == "p1_calibration"
        assert row["risk_profile_version"] == "2026-07-08"
        assert "id_switch_count" in row
        assert "track_continuity" in row
        assert "duplicate_assignment_count" in row
        assert "soft_risk_frame_count" in row
        assert "hard_risk_frame_count" in row
        assert "risk_summary" in row

    report_path = tmp_path / "d2_report.json"
    logs_path = tmp_path / "d2_association_logs.jsonl"
    write_replay_association_report(report, report_path)
    write_association_logs_jsonl(report.association_logs, logs_path)

    report_json = json.loads(report_path.read_text())
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines()]
    assert report_json["replay_name"] == "airsim_dense_5v5"
    assert report_json["replay_metadata"]["seed"] == 11
    assert len(log_lines) == len(frames)
    assert "risk_summary" in log_lines[-1]


def test_main_d6_jsonl_metadata_and_offline_truth_labels_flow_to_logs(tmp_path) -> None:
    frames = []
    for step in range(3):
        frames.append(
            {
                "timestamp": float(step),
                "detections": [
                    {
                        "detection_id": f"cv-A-{step}",
                        "offline_truth_label": "target-A",
                        "position": {"x_val": float(step), "y_val": 0.0},
                        "covariance": [[0.2, 0.0], [0.0, 0.2]],
                        "offline_truth_position": [float(step), 0.0],
                    },
                    {
                        "detection_id": f"cv-B-{step}",
                        "position": {"x_val": float(step), "y_val": 10.0},
                        "covariance": [[0.2, 0.0], [0.0, 0.2]],
                        "offline_truth_position": [float(step), 10.0],
                    },
                ],
                "offline_truth_labels": {
                    f"cv-A-{step}": "target-A",
                    f"cv-B-{step}": "target-B",
                },
            }
        )
    replay_path = tmp_path / "main_d6_episode.jsonl"
    replay_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "event": "d6_episode_row",
                    "seed": 31,
                    "episode_id": "episode-031",
                    "scenario": "real_airsim_replay_fixture",
                    "drone_count": 2,
                    "frame_index": step,
                    "payload": {"d2_frame": frame},
                }
            )
            for step, frame in enumerate(frames)
        )
    )

    loaded_frames = load_airsim_replay_frames(replay_path)
    report = run_airsim_replay_association(loaded_frames)

    assert report.replay_metadata["seed"] == 31
    assert report.replay_metadata["episode_id"] == "episode-031"
    assert report.replay_metadata["scenario"] == "real_airsim_replay_fixture"
    assert report.metrics["id_switch_count"] == 0
    assert report.metrics["confusion_matrix"]["target-A"] == {"T001": 3}
    assert report.metrics["confusion_matrix"]["target-B"] == {"T002": 3}
    assert set(report.global_track_ids) == {"T001", "T002"}
    assert "target-A" not in report.global_track_ids
    assert "target-B" not in report.global_track_ids
    last_log_metadata = report.association_logs[-1]["metadata"]
    assert last_log_metadata["seed"] == 31
    assert last_log_metadata["episode_id"] == "episode-031"
    assert last_log_metadata["scenario"] == "real_airsim_replay_fixture"
    assert last_log_metadata["frame_index"] == 2
    assert last_log_metadata["offline_truth_labels"] == ["target-A", "target-B"]
    assert last_log_metadata["truth_label_usage"] == "offline_metrics_only"


def test_replay_target_count_falls_back_to_input_count_without_truth_labels() -> None:
    frames = []
    for step in range(3):
        detections = []
        for index in range(6):
            detections.append(
                {
                    "detection_id": f"det-{step}-{index}",
                    "position": {
                        "x": float(step),
                        "y": float(index * 12),
                        "z": -15.0,
                    },
                    "covariance": [[0.3, 0.0], [0.0, 0.3]],
                }
            )
        frames.append(
            {
                "timestamp": float(step),
                "detections": detections,
                "replay_metadata": {
                    "seed": 22,
                    "episode_id": "episode-022",
                    "scenario_name": "airsim_nvn_no_truth",
                },
            }
        )

    report = run_airsim_replay_association(frames, replay_name="airsim_nvn_no_truth")

    assert report.target_count == 6
    assert report.replay_metadata["seed"] == 22
    assert report.metrics["id_switch_count"] == 0
    assert "track_continuity" in report.metrics
    assert len(report.association_logs) == len(frames)


def test_threshold_sensitivity_outputs_required_metrics_for_variable_target_count() -> None:
    frames = dense_airsim_like_frames(target_count=4, steps=5)
    rows = run_threshold_sensitivity(
        frames,
        gate_thresholds=[4.0, 9.21],
        risk_thresholds=[
            RiskThresholds(profile_name="default"),
            RiskThresholds(profile_name="strict", soft_association_ambiguity=0.20),
        ],
    )

    assert len(rows) == 4
    assert {row["target_count"] for row in rows} == {4}
    assert {row["risk_profile"] for row in rows} == {"default", "strict"}
    for row in rows:
        assert isinstance(row["id_switch_count"], int)
        assert 0.0 <= row["track_continuity"] <= 1.0
        assert isinstance(row["duplicate_assignment_count"], int)
        assert row["risk_summary"]["thresholds"]["profile_name"] == row["risk_profile"]
        assert "soft_risk_frame_count" in row["risk_summary"]
        assert "hard_risk_frame_count" in row["risk_summary"]


def test_multi_seed_risk_calibration_summary_groups_and_recommends_profile() -> None:
    rows = []
    for seed in (101, 102):
        frames = dense_airsim_like_frames(target_count=4, steps=5)
        for frame in frames:
            frame["seed"] = seed
            frame["scenario_name"] = "multi_seed_dense"
        rows.extend(
            run_threshold_sensitivity(
                frames,
                gate_thresholds=[5.99, 9.21],
                risk_thresholds=[
                    RiskThresholds(
                        profile_name="default",
                        profile_version="p1-v1",
                    ),
                    RiskThresholds(
                        profile_name="strict",
                        profile_version="p1-v1",
                        soft_association_ambiguity=0.20,
                    ),
                ],
            )
        )

    summary = summarize_multi_seed_risk_calibration(rows)

    assert summary["row_count"] == 8
    assert summary["group_count"] == 4
    assert summary["recommended"]["gate_threshold"] in {5.99, 9.21}
    assert summary["recommended"]["risk_profile"] in {"default", "strict"}
    assert "thresholds" in summary["recommended"]
    for group in summary["groups"]:
        assert group["seed_count"] == 2
        assert group["seeds"] == ["101", "102"]
        assert group["scenarios"] == ["multi_seed_dense"]
        assert group["id_switch_count"]["count"] == 2
        assert group["track_continuity"]["count"] == 2
        assert group["duplicate_assignment_count"]["count"] == 2
        assert group["soft_risk_frame_count"]["count"] == 2
        assert group["hard_risk_frame_count"]["count"] == 2
        assert group["soft_risk_frame_rate"]["count"] == 2
        assert group["hard_risk_frame_rate"]["count"] == 2
        assert "mean_hard_risk_frame_rate" in group["recommendation_summary"]


def test_risk_summary_classifies_soft_and_hard_evidence() -> None:
    summary = AssociationRiskSummary(
        timestamp=3.0,
        d5_disagreement_count=1,
        duplicate_track_risk=0.80,
        association_ambiguity=0.60,
        covariance_overlap_rate=0.40,
        metadata={
            "candidate_overlap_rate": 0.50,
            "cost_margin_risk": 0.55,
            "id_switch_delta_sum": 1,
            "duplicate_assignment_delta_sum": 1,
            "track_continuity": 0.40,
            "d5_disagreement_delta": 1,
        },
    )

    breakdown = classify_risk_summary(summary)

    assert breakdown.has_soft_risk is True
    assert breakdown.has_hard_risk is True
    assert set(breakdown.soft_risk_reasons) == {
        "association_ambiguity",
        "candidate_overlap",
        "cost_margin",
        "d5_disagreement",
    }
    assert set(breakdown.hard_risk_reasons) == {
        "id_switch",
        "duplicate_assignment",
        "duplicate_track",
        "continuity_collapse",
    }


def test_replay_helper_does_not_import_airsim() -> None:
    source = inspect.getsource(replay_module)

    assert "import airsim" not in source
    assert "from airsim" not in source
