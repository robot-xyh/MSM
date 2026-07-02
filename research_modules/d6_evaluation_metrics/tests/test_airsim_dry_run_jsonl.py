from __future__ import annotations

from pathlib import Path

import pytest

from d6_evaluation_metrics import dump_episode_log_jsonl, load_episode_log_jsonl


def test_d6_loads_airsim_dry_run_jsonl_schema_and_computes_episode_metrics(tmp_path: Path) -> None:
    path = dump_episode_log_jsonl(
        [
            {
                "record_type": "truth_summary",
                "payload": {
                    "truth_timestamps": {"T1": [0.0, 1.0]},
                    "high_threat_by_timestamp": {"0.0": ["T1"]},
                },
            },
            {
                "record_type": "track",
                "payload": {
                    "timestamp": 0.0,
                    "global_track_id": "G-T1",
                    "truth_id": "T1",
                    "position": [0.0, 0.0, 20.0],
                    "truth_position": [0.0, 0.0, 20.0],
                    "covariance_trace": 0.3,
                    "association_source": "airsim_phase1_dry_run",
                    "ignored_extra_field": "schema_forward_compatibility",
                },
            },
            {
                "record_type": "assignment",
                "payload": {
                    "timestamp": 0.0,
                    "plan_id": "dry-run-plan",
                    "version": 1,
                    "resource_id": "R1",
                    "global_track_id": "G-T1",
                    "truth_id": "T1",
                    "authorization_state": "recorded",
                    "active": True,
                },
            },
            {
                "record_type": "terminal",
                "payload": {
                    "timestamp": 1.0,
                    "resource_id": "R1",
                    "assigned_global_track_id": "G-T1",
                    "local_track_id": "L-ambiguous",
                    "decision_state": "ambiguous",
                    "ambiguity_score": 0.92,
                    "friend_conflict_state": "none",
                    "assignment_version": 1,
                    "expected_global_track_id": "G-T1",
                    "association_correct": True,
                },
            },
            {
                "record_type": "terminal",
                "payload": {
                    "timestamp": 2.0,
                    "resource_id": "R1",
                    "assigned_global_track_id": "G-T1",
                    "local_track_id": "L-friend",
                    "decision_state": "hold",
                    "ambiguity_score": 1.0,
                    "friend_conflict_state": "verified_friend_overlap",
                    "assignment_version": 1,
                },
            },
            {
                "record_type": "terminal",
                "payload": {
                    "timestamp": 3.0,
                    "resource_id": "R1",
                    "assigned_global_track_id": "G-T1",
                    "local_track_id": "L-locked",
                    "decision_state": "locked",
                    "ambiguity_score": 0.1,
                    "friend_conflict_state": "none",
                    "assignment_version": 1,
                    "expected_global_track_id": "G-T1",
                    "association_correct": True,
                },
            },
            {
                "record_type": "event",
                "payload": {
                    "timestamp": 4.0,
                    "event_type": "human_override",
                    "actor_id": "operator",
                    "severity": "info",
                    "metadata": {"dry_run": True},
                },
            },
        ],
        tmp_path / "airsim_phase1_dry_run.jsonl",
    )

    collector, truth_summary = load_episode_log_jsonl(path)
    metrics = collector.compute_episode(
        episode_id="airsim_phase1_dry_run",
        duration=4.0,
        truth_summary=truth_summary,
    )

    assert metrics.episode_id == "airsim_phase1_dry_run"
    assert metrics.metadata["terminal_record_count"] == 3
    assert metrics.detection_probability == pytest.approx(0.5)
    assert metrics.terminal_association_accuracy == pytest.approx(1.0)
    assert metrics.ambiguous_fov_event_count == 2
    assert metrics.friend_overlap_hold_count == 1
    assert metrics.human_override_count == 1


def test_d6_rejects_unknown_dry_run_record_type(tmp_path: Path) -> None:
    path = dump_episode_log_jsonl(
        [{"record_type": "airsim_frame", "payload": {"timestamp": 0.0}}],
        tmp_path / "bad.jsonl",
    )

    with pytest.raises(ValueError, match="unsupported record_type"):
        load_episode_log_jsonl(path)
