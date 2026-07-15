from __future__ import annotations

import csv
import json
from pathlib import Path

from d6_evaluation_metrics import (
    EpisodeMetrics,
    MetricsCollector,
    ReportGenerator,
    TrackRecord,
    load_main_episode_bus_metrics,
    merge_replay_with_execution_metrics,
)


TRACKING_METRICS = ("track_rmse", "track_continuity", "id_switch_count")


def _assert_tracking_unavailable(metrics: EpisodeMetrics) -> None:
    for metric_name in TRACKING_METRICS:
        assert getattr(metrics, metric_name) is None
        assert metrics.metric_availability[metric_name]["status"] == "unavailable"


def test_empty_input_keeps_truth_tracking_metrics_explicitly_unavailable() -> None:
    metrics = MetricsCollector().compute_episode("empty")

    _assert_tracking_unavailable(metrics)
    default_payload = EpisodeMetrics("default").to_dict()
    for metric_name in TRACKING_METRICS:
        assert default_payload[metric_name] is None
        assert default_payload["metric_availability"][metric_name]["status"] == (
            "unavailable"
        )


def test_anonymous_tracks_remain_unavailable_in_json_csv_and_markdown(
    tmp_path: Path,
) -> None:
    collector = MetricsCollector()
    collector.extend_tracks(
        [
            TrackRecord(0.0, "G1", None, position=(0.0, 0.0)),
            TrackRecord(1.0, "G1", None, position=(1.0, 0.0)),
        ]
    )
    metrics = collector.compute_episode(
        "anonymous",
        truth_summary={"truth_timestamps": {"T1": [0.0, 1.0]}},
    )

    _assert_tracking_unavailable(metrics)
    payload = json.loads(json.dumps(metrics.to_dict()))
    for metric_name in TRACKING_METRICS:
        assert payload[metric_name] is None
        assert payload["metric_availability"][metric_name]["status"] == (
            "unavailable"
        )

    reporter = ReportGenerator()
    csv_path = reporter.write_episode_csv([metrics], tmp_path / "episodes.csv")
    markdown_path = reporter.write_markdown_report(
        [metrics],
        tmp_path / "report.md",
    )
    row = next(csv.DictReader(csv_path.open(encoding="utf-8")))
    csv_availability = json.loads(row["metric_availability"])
    for metric_name in TRACKING_METRICS:
        assert row[metric_name] == ""
        assert row[f"{metric_name}_availability"] == "unavailable"
        assert csv_availability[metric_name]["status"] == "unavailable"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Tracking Truth Availability" in markdown
    assert "| anonymous | id_switch_count | unavailable |" in markdown


def test_incomplete_truth_sidecar_does_not_promote_false_zero_through_merge(
    tmp_path: Path,
) -> None:
    collector = MetricsCollector()
    collector.add_track(
        TrackRecord(
            1.0,
            "G1",
            "T1",
            position=(1.0, 0.0),
            truth_position=None,
        )
    )
    metrics = collector.compute_episode(
        "incomplete-sidecar",
        truth_summary={"truth_timestamps": {"T1": [0.0]}},
    )

    assert metrics.track_rmse is None
    assert metrics.track_continuity is None
    assert metrics.id_switch_count == 0
    assert metrics.metric_availability["track_rmse"]["status"] == "unavailable"
    assert metrics.metric_availability["track_continuity"]["status"] == (
        "unavailable"
    )
    assert metrics.metric_availability["id_switch_count"]["status"] == "available"

    stale_replay = {
        "episode_id": "stale-zero",
        "track_rmse": 0.0,
        "track_continuity": 0.0,
        "id_switch_count": 0,
        "metric_availability": {
            metric_name: {
                "status": "unavailable",
                "reason": "truth sidecar incomplete",
            }
            for metric_name in TRACKING_METRICS
        },
    }
    merged = merge_replay_with_execution_metrics(stale_replay, None)["metrics"]
    for metric_name in TRACKING_METRICS:
        assert metric_name in merged
        assert merged[metric_name] is None
        assert merged["metric_availability"][metric_name]["status"] == (
            "unavailable"
        )

    stale_episode = EpisodeMetrics(**stale_replay)
    summary = {
        row["metric"]: row for row in ReportGenerator().summarize([stale_episode])
    }
    for metric_name in TRACKING_METRICS:
        assert summary[metric_name]["count"] == 0
        assert summary[metric_name]["unavailable_count"] == 1

    main_bus_path = tmp_path / "main_episode_bus_metrics.json"
    main_bus_path.write_text(
        json.dumps({"metrics": stale_replay}),
        encoding="utf-8",
    )
    loaded = load_main_episode_bus_metrics(main_bus_path)
    _assert_tracking_unavailable(loaded)


def test_complete_truth_with_stable_identity_reports_available_zero_switches() -> None:
    collector = MetricsCollector()
    collector.extend_tracks(
        [
            TrackRecord(0.0, "G1", "T1", (0.0, 0.0), (0.0, 0.0)),
            TrackRecord(1.0, "G1", "T1", (1.0, 0.0), (1.0, 0.0)),
        ]
    )
    metrics = collector.compute_episode(
        "stable",
        truth_summary={"truth_timestamps": {"T1": [0.0, 1.0]}},
    )

    assert metrics.track_rmse == 0.0
    assert metrics.track_continuity == 1.0
    assert metrics.id_switch_count == 0
    for metric_name in TRACKING_METRICS:
        assert metrics.metric_availability[metric_name]["status"] == "available"


def test_complete_truth_with_identity_change_reports_available_switch() -> None:
    collector = MetricsCollector()
    collector.extend_tracks(
        [
            TrackRecord(0.0, "G1", "T1", (0.0, 0.0), (0.0, 0.0)),
            TrackRecord(1.0, "G2", "T1", (2.0, 0.0), (1.0, 0.0)),
        ]
    )
    metrics = collector.compute_episode(
        "switch",
        truth_summary={"truth_timestamps": {"T1": [0.0, 1.0]}},
    )

    assert metrics.track_rmse is not None
    assert metrics.track_continuity == 1.0
    assert metrics.id_switch_count == 1
    assert metrics.metric_availability["id_switch_count"]["status"] == "available"
