from __future__ import annotations

import json
from math import atan2, hypot

import numpy as np
import pytest

import d2_data_association.compat as compat
import d2_data_association.p2_benchmark as p2_benchmark
from d2_data_association import (
    Detection,
    GNNHungarianAssociator,
    GlobalTrack,
    OfflineTruthLabel,
    OptionalDependencyStatus,
    OptionalIntegrationUnavailable,
    build_dense_crossing_replay_fixture,
    build_default_dry_run_tracker,
    extract_offline_truth_labels,
    filterpy_filter_from_detection,
    load_airsim_replay_frames,
    run_optional_framework_benchmark,
    strip_offline_truth_from_frames,
    to_filterpy_state,
    to_stonesoup_detection,
)


def _frozen_replay() -> tuple[list[dict], list]:
    governed = build_dense_crossing_replay_fixture(
        target_count=3,
        seed=29,
        steps=8,
        missed_detection_frames=(3, 4),
        false_alarm_frames=(5,),
    )
    return strip_offline_truth_from_frames(governed), extract_offline_truth_labels(
        governed
    )


def test_missing_optional_dependencies_report_explicit_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(compat, "_find_spec", lambda name: None)
    frames, labels = _frozen_replay()
    report = run_optional_framework_benchmark(frames, labels)
    payload = report.to_dict()

    assert payload["schema_version"] == "d2-optional-framework-benchmark/v2"
    assert payload["default_online_path_unchanged"] is True
    assert payload["claims"] == {
        "full_stonesoup_jpda_implemented": False,
        "full_stonesoup_mht_implemented": False,
        "filterpy_end_to_end_tracker_implemented": False,
    }
    baseline, filterpy_row, stonesoup_row, jpda_row, mht_row = payload["results"]
    for row in payload["results"]:
        assert {
            "id_switch_count",
            "track_continuity",
            "latency_seconds",
            "unavailable_reason",
        } <= row.keys()
    assert baseline["implementation"] == "d2_gnn_hungarian"
    assert baseline["executed"] is True
    assert baseline["unavailable_reason"] is None
    assert baseline["id_switch_available"] is True
    assert baseline["continuity_available"] is True
    assert baseline["latency_seconds"] >= 0.0
    for row in (filterpy_row, stonesoup_row):
        assert row["dependency_available"] is False
        assert row["executed"] is False
        assert "not installed" in row["reason"]
        assert row["unavailable_reason"] == row["reason"]
        assert row["latency_seconds"] is None
        assert row["id_switch_count"] is None
        assert row["id_switch_available"] is False
        assert row["track_continuity"] is None
        assert row["continuity_available"] is False
        assert row["metric_unavailable_reason"] == (
            "adapter_only_no_end_to_end_association"
        )
        assert row["full_jpda_implemented"] is False
        assert row["full_mht_implemented"] is False

    for row, implementation in (
        (jpda_row, "d2_jpda_research_adapter"),
        (mht_row, "d2_mht_research_adapter"),
    ):
        assert row["implementation"] == implementation
        assert row["framework"] == "d2_builtin_research"
        assert row["dependency_available"] is True
        assert row["executed"] is True
        assert row["unavailable_reason"] is None
        assert row["id_switch_available"] is True
        assert row["continuity_available"] is True
        assert row["id_switch_count"] is not None
        assert row["track_continuity"] is not None
        assert row["latency_seconds"] >= 0.0
        assert row["end_to_end_tracker_implemented"] is True
        assert row["full_jpda_implemented"] is False
        assert row["full_mht_implemented"] is False

    assert isinstance(
        build_default_dry_run_tracker().associator,
        GNNHungarianAssociator,
    )

    detection = Detection(
        detection_id="online-only",
        timestamp=1.0,
        position=np.array([1.0, 2.0]),
        covariance=np.eye(2),
    )
    track = GlobalTrack(
        global_track_id="GT-1",
        state=np.array([1.0, 2.0, 0.0, 0.0]),
        covariance=np.eye(4),
        timestamp=1.0,
    )
    with pytest.raises(OptionalIntegrationUnavailable, match="not installed"):
        to_stonesoup_detection(detection)
    with pytest.raises(OptionalIntegrationUnavailable, match="not installed"):
        filterpy_filter_from_detection(detection)
    with pytest.raises(OptionalIntegrationUnavailable, match="not installed"):
        to_filterpy_state(track)


def test_available_adapter_smoke_does_not_claim_tracking_metrics(monkeypatch) -> None:
    class FakeFilter:
        def predict(self) -> None:
            return None

        def update(self, measurement) -> None:
            assert np.asarray(measurement).shape == (2, 1)

    def available_status(name: str) -> OptionalDependencyStatus:
        return OptionalDependencyStatus(
            name=name,
            available=True,
            version="test-version",
            purpose="test adapter",
        )

    monkeypatch.setattr(p2_benchmark, "probe_optional_dependency", available_status)
    monkeypatch.setattr(
        p2_benchmark,
        "filterpy_filter_from_detection",
        lambda detection: FakeFilter(),
    )
    monkeypatch.setattr(
        p2_benchmark,
        "to_stonesoup_detection",
        lambda detection: object(),
    )
    frames, labels = _frozen_replay()
    report = run_optional_framework_benchmark(frames, labels)

    for row in report.results[1:3]:
        assert row.dependency_available is True
        assert row.dependency_version == "test-version"
        assert row.executed is True
        assert row.processed_detection_count > 0
        assert row.latency_seconds is not None
        assert row.id_switch_count is None
        assert row.id_switch_available is False
        assert row.track_continuity is None
        assert row.continuity_available is False
        assert row.end_to_end_tracker_implemented is False
        assert row.full_jpda_implemented is False
        assert row.full_mht_implemented is False
        assert row.unavailable_reason == "adapter_only_no_end_to_end_association"

    for row in report.results[3:]:
        assert row.executed is True
        assert row.id_switch_available is True
        assert row.continuity_available is True
        assert row.unavailable_reason is None


def test_benchmark_digest_is_stable_for_same_frozen_input(monkeypatch) -> None:
    monkeypatch.setattr(compat, "_find_spec", lambda name: None)
    frames, labels = _frozen_replay()
    first = run_optional_framework_benchmark(frames, labels)
    second = run_optional_framework_benchmark(frames, labels)

    assert first.input_digest == second.input_digest
    assert first.results[0].id_switch_count == second.results[0].id_switch_count
    assert first.results[0].track_continuity == second.results[0].track_continuity


def test_all_tracker_runs_receive_truth_free_replay(monkeypatch) -> None:
    frames, labels = _frozen_replay()
    frames[0]["detections"][0]["truth_id"] = "must-be-stripped"
    original_run = p2_benchmark.run_airsim_replay_association
    observed_replays: list[str] = []

    def guarded_run(run_frames, **kwargs):
        payload = json.dumps(run_frames, sort_keys=True).lower()
        assert "truth_id" not in payload
        assert "must-be-stripped" not in payload
        observed_replays.append(str(kwargs["replay_name"]))
        return original_run(run_frames, **kwargs)

    monkeypatch.setattr(p2_benchmark, "run_airsim_replay_association", guarded_run)
    report = run_optional_framework_benchmark(
        frames,
        labels,
        frameworks=("jpda", "mht"),
    )

    assert observed_replays == [
        "p2_frozen_replay_baseline",
        "p2_frozen_replay_jpda",
        "p2_frozen_replay_mht",
    ]
    assert all(row.unavailable_reason is None for row in report.results)


def test_unknown_benchmark_adapter_is_rejected() -> None:
    frames, labels = _frozen_replay()

    with pytest.raises(ValueError, match="unsupported optional benchmark framework"):
        run_optional_framework_benchmark(frames, labels, frameworks=("unknown",))


def test_d1_governed_replay_schema_converts_to_online_safe_frames(tmp_path) -> None:
    records = []
    labels = []
    for frame_index in range(3):
        timestamp = frame_index * 0.5
        positions = (
            (20.0 + frame_index, -2.0),
            (24.0 + frame_index, 3.0),
        )
        for target_index, position in enumerate(positions):
            radius = hypot(*position)
            azimuth = atan2(position[1], position[0])
            records.append(
                {
                    "schema_version": "d1.sensor_observation.v1",
                    "observation_id": (
                        f"source-TGT-SECRET-{target_index}-{frame_index}"
                    ),
                    "sensor_id": "RADAR-01",
                    "modality": "radar",
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + 0.2,
                    "frame_id": "ned",
                    "working_frame": "ned",
                    "measurement": [radius, azimuth, 0.0, 0.0],
                    "covariance": np.diag([0.25, 0.0001, 0.0001, 0.5]).tolist(),
                    "confidence": 0.9,
                    "metadata": {
                        "airsim_frame_index": frame_index,
                        "airsim_episode_id": "episode-minimal",
                        "airsim_scenario": "d1-governed-minimal",
                        "sensor_position_ned": [0.0, 0.0, 0.0],
                    },
                    "source_lineage": ["source-TGT-SECRET"],
                }
            )
            labels.append(
                OfflineTruthLabel(
                    episode_id="episode-minimal",
                    frame_index=frame_index,
                    timestamp=timestamp,
                    truth_id=f"truth-{target_index}",
                    position=position,
                    match_annotation={"offline_only": True},
                )
            )
        records.extend(
            [
                {
                    "schema_version": "d1.sensor_observation.v1",
                    "observation_id": f"acoustic-secret-{frame_index}",
                    "sensor_id": "ACOUSTIC-01",
                    "modality": "acoustic",
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + 0.2,
                    "frame_id": "ned",
                    "working_frame": "ned",
                    "measurement": [0.1],
                    "covariance": [[0.01]],
                    "metadata": {"airsim_frame_index": frame_index},
                },
                {
                    "schema_version": "d1.sensor_observation.v1",
                    "observation_id": f"eo-secret-{frame_index}",
                    "sensor_id": "EO-01",
                    "modality": "eo",
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + 0.2,
                    "frame_id": "pixel",
                    "working_frame": "ned",
                    "measurement": [320.0, 240.0],
                    "covariance": [[4.0, 0.0], [0.0, 4.0]],
                    "metadata": {"airsim_frame_index": frame_index},
                },
            ]
        )
    bundle = {
        "manifest": {
            "schema_version": "d1.governed_replay_manifest.v1",
            "observation_schema_version": "d1.sensor_observation.v1",
            "working_frame": "ned",
            "truth_policy": {"online": "stripped"},
            "provenance": {
                "run_id": "episode-minimal",
                "scenario_id": "d1-governed-minimal",
                "seed": 11,
                "metadata": {"target_count": 2},
            },
        },
        "records": records,
    }
    replay_path = tmp_path / "d1_governed_replay.json"
    replay_path.write_text(json.dumps(bundle))

    frames = load_airsim_replay_frames(replay_path)
    assert len(frames) == 3
    assert all(len(frame["detections"]) == 2 for frame in frames)
    assert all(frame["replay_metadata"]["target_count"] == 2 for frame in frames)
    diagnostics = frames[0]["replay_metadata"]["d1_governed_adapter"]
    assert diagnostics["accepted_radar_record_count"] == 6
    assert diagnostics["skipped_reasons"] == {
        "unsupported_modality_acoustic": 3,
        "unsupported_modality_eo": 3,
    }
    online_payload = json.dumps(frames, sort_keys=True)
    assert "TGT-SECRET" not in online_payload
    assert '"truth_id"' not in online_payload
    report = run_optional_framework_benchmark(frames, labels, frameworks=())
    assert report.frame_count == 3
    assert report.target_count == 2
    assert report.input_metadata["source_format"] == "d1_serialize_governed_replay"
    assert report.input_metadata["d1_governed_adapter"] == diagnostics
    assert report.results[0].id_switch_available is True
    assert report.results[0].continuity_available is True
    assert report.results[0].id_switch_count == 0

    legacy_path = tmp_path / "legacy_replay.json"
    legacy_path.write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "timestamp": 0.0,
                        "detections": [
                            {
                                "detection_id": "legacy-0",
                                "position": [1.0, 2.0],
                                "covariance": [[1.0, 0.0], [0.0, 1.0]],
                            }
                        ],
                    }
                ]
            }
        )
    )
    assert len(load_airsim_replay_frames(legacy_path)) == 1
