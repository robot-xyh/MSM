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
        "\n".join(json.dumps({"event": "d2_frame", "frame": frame}) for frame in frames)
    )

    loaded_frames = load_airsim_replay_frames(replay_path)
    report = run_airsim_replay_association(
        loaded_frames,
        replay_name="airsim_dense_5v5",
        gate_thresholds=[5.99, 9.21],
    )

    assert report.frame_count == len(frames)
    assert report.target_count == 5
    assert report.metrics["frame_count"] == len(frames)
    assert "id_switch_count" in report.metrics
    assert "track_continuity" in report.metrics
    assert "duplicate_assignment_count" in report.metrics
    assert len(report.association_logs) == len(frames)
    assert len(report.global_track_ids) == 5
    assert report.risk_summary["id_switch_count"] == report.metrics["id_switch_count"]
    assert "soft_risk_frame_count" in report.risk_summary
    assert "hard_risk_frame_count" in report.risk_summary
    assert len(report.threshold_sensitivity) == 2
    for row in report.threshold_sensitivity:
        assert row["target_count"] == 5
        assert "id_switch_count" in row
        assert "track_continuity" in row
        assert "duplicate_assignment_count" in row
        assert "risk_summary" in row

    report_path = tmp_path / "d2_report.json"
    logs_path = tmp_path / "d2_association_logs.jsonl"
    write_replay_association_report(report, report_path)
    write_association_logs_jsonl(report.association_logs, logs_path)

    report_json = json.loads(report_path.read_text())
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines()]
    assert report_json["replay_name"] == "airsim_dense_5v5"
    assert len(log_lines) == len(frames)
    assert "risk_summary" in log_lines[-1]


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
