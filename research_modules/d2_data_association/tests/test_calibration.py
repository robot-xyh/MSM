from __future__ import annotations

import json

from d2_data_association import (
    OFFLINE_TRUTH_SCHEMA_VERSION,
    LongReplayCalibrationProfile,
    build_long_dense_crossing_replay_fixture,
    build_dense_crossing_replay_fixture,
    extract_offline_truth_labels,
    load_offline_truth_labels_jsonl,
    run_airsim_replay_association,
    run_dense_crossing_calibration,
    run_long_replay_calibration,
    strip_offline_truth_from_frames,
    summarize_dense_crossing_calibration,
    write_offline_truth_labels_jsonl,
)


def test_offline_truth_jsonl_contract_round_trip_and_online_isolation(tmp_path) -> None:
    governed_frames = build_dense_crossing_replay_fixture(
        target_count=3,
        seed=41,
        steps=8,
        missed_detection_frames=(3,),
        false_alarm_frames=(4,),
    )
    labels = extract_offline_truth_labels(governed_frames)
    output_path = tmp_path / "offline_truth_labels.jsonl"
    write_offline_truth_labels_jsonl(output_path, labels)
    loaded = load_offline_truth_labels_jsonl(output_path)

    assert loaded == labels
    first_payload = json.loads(output_path.read_text().splitlines()[0])
    assert {
        "schema_version",
        "episode_id",
        "frame_index",
        "timestamp",
        "truth_id",
        "position",
    } <= set(first_payload)
    assert first_payload["schema_version"] == OFFLINE_TRUTH_SCHEMA_VERSION

    online_frames = strip_offline_truth_from_frames(governed_frames)
    online_payload = json.dumps(online_frames, sort_keys=True)
    assert "offline_truth_label" not in online_payload
    assert "offline_truth_state" not in online_payload
    assert '"truth_id"' not in online_payload

    report = run_airsim_replay_association(
        online_frames,
        replay_name="three_target_truth_contract",
        offline_truth_labels=loaded,
    )
    assert report.target_count == 3
    assert report.online_metrics["truth_metrics_available"] is False
    assert report.metrics["truth_metrics_available"] is True
    assert report.metrics["continuity_available"] is True
    assert report.metrics["nis"]["available"] is True
    assert report.metrics["nees"]["available"] is True
    assert report.metrics["online_truth_isolation_violations"] == 0
    serialized_online = json.dumps(
        {
            "online_metrics": report.online_metrics,
            "association_logs": report.association_logs,
        },
        sort_keys=True,
    )
    assert "target-1" not in serialized_online
    assert '"truth_id"' not in serialized_online


def test_dense_crossing_fixture_uses_target_count_not_scenario_constant() -> None:
    frames = build_dense_crossing_replay_fixture(
        target_count=7,
        seed=9,
        steps=8,
        missed_detection_frames=(2,),
        false_alarm_frames=(5,),
    )

    assert all(frame["replay_metadata"]["target_count"] == 7 for frame in frames)
    assert all(len(frame["truth_ids_present"]) == 7 for frame in frames)
    assert len(frames[2]["detections"]) == 6
    assert len(frames[5]["detections"]) == 8
    assert all(
        len(detection["feature"]) == 7
        for frame in frames
        for detection in frame["detections"]
        if not detection.get("is_false_alarm", False)
    )


def test_ten_seed_calibration_is_reproducible_and_reports_availability(tmp_path) -> None:
    seeds = tuple(range(10))
    first = run_dense_crossing_calibration(
        seeds=seeds,
        target_count=5,
        steps=8,
        truth_output_directory=tmp_path / "truth",
    )
    second = run_dense_crossing_calibration(
        seeds=seeds,
        target_count=5,
        steps=8,
    )

    assert first.configuration["target_count"] == 5
    assert first.aggregate["seed_count"] == 10
    assert len(first.per_seed) == 10
    assert [row["deterministic_signature"] for row in first.per_seed] == [
        row["deterministic_signature"] for row in second.per_seed
    ]
    assert first.aggregate["truth_metrics_available_seed_count"] == 10
    assert first.aggregate["continuity_available_seed_count"] == 10
    assert first.aggregate["id_switch_count"]["available_seed_count"] == 10
    assert first.aggregate["track_continuity"]["available_seed_count"] == 10
    assert first.aggregate["source_binding_conflict_count"]["mean"] == 0.0
    assert first.aggregate["source_lineage_quarantine_count"]["mean"] == 0.0
    assert first.aggregate["upstream_local_identity_rejection_count"]["mean"] == 0.0
    assert first.aggregate["nis_availability"]["available_seed_count"] == 10
    assert first.aggregate["nees_availability"]["available_seed_count"] == 10
    assert first.aggregate["online_truth_isolation_violation_count"] == 0
    assert first.aggregate["risk_calibration_summary"]["row_count"] == 10
    assert len(list((tmp_path / "truth").glob("*.jsonl"))) == 10
    for row in first.per_seed:
        assert row["offline_truth_label_count"] == 40
        assert row["gate_profile"]["profile_version"] == "v1"
        assert row["risk_profile_version"] == "v1"
        assert isinstance(row["id_switch_count"], int)
        assert row["source_binding_conflict_count"] == 0
        assert row["source_lineage_quarantine_count"] == 0
        assert row["upstream_local_identity_rejection_count"] == 0
        assert isinstance(row["track_continuity"], float)
        assert row["nis"]["available"] is True
        assert row["nees"]["available"] is True
        assert row["runtime_seconds"] >= 0.0


def test_calibration_summary_does_not_convert_unavailable_to_zero() -> None:
    summary = summarize_dense_crossing_calibration(
        [
            {
                "seed": 3,
                "target_count": 5,
                "truth_metrics_available": False,
                "continuity_available": False,
                "id_switch_count": None,
                "track_continuity": None,
                "runtime_seconds": 0.02,
                "nis": {"available": True, "count": 4},
                "nees": {"available": False, "count": 0},
                "gate_profile": {
                    "profile_name": "test",
                    "profile_version": "v1",
                    "mahalanobis_threshold": 9.21,
                },
                "risk_profile": "test",
                "risk_profile_version": "v1",
            }
        ]
    )

    assert summary["id_switch_count"]["available"] is False
    assert summary["id_switch_count"]["mean"] is None
    assert summary["id_switch_count"]["unavailable_seed_count"] == 1
    assert summary["track_continuity"]["available"] is False
    assert summary["track_continuity"]["mean"] is None
    assert summary["nis_availability"]["available_seed_count"] == 1
    assert summary["nees_availability"]["available_seed_count"] == 0


def test_long_governed_fixture_audits_oosm_without_reordering_measurements() -> None:
    frames = build_long_dense_crossing_replay_fixture(
        target_count=4,
        seed=17,
        steps=40,
    )

    measurement_times = [frame["measurement_timestamp"] for frame in frames]
    arrival_times = [frame["arrival_timestamp"] for frame in frames]
    assert measurement_times == sorted(measurement_times)
    assert any(
        current > following
        for current, following in zip(arrival_times, arrival_times[1:])
    )
    assert all(frame["replay_metadata"]["target_count"] == 4 for frame in frames)
    assert any(len(frame["detections"]) < 4 for frame in frames)
    assert any(len(frame["detections"]) > 4 for frame in frames)


def test_long_replay_calibration_reports_dynamic_n_m_and_identity_governance() -> None:
    report = run_long_replay_calibration(
        seeds=tuple(range(10)),
        target_count=3,
        profile=LongReplayCalibrationProfile(steps=40),
    )

    assert report.configuration["scenario_version"] == "d2-governed-long-replay/v1"
    assert report.schema_version == "d2-long-replay-calibration/v1"
    assert report.configuration["global_track_id_owner"] == "d2_center"
    assert report.configuration["online_associator"] == "GNNHungarianAssociator"
    assert report.configuration["optional_associators_in_mainline"] == []
    assert report.aggregate["seed_count"] == 10
    assert report.aggregate["online_truth_leakage_count"] == 0
    assert report.aggregate["oosm_exposure"]["arrival_order_inversion_count"] > 0
    assert report.aggregate["oosm_exposure"]["all_measurement_order_monotonic"] is True
    for row in report.per_seed:
        assert row["target_count"] == 3
        assert row["measurement_count_min"] < row["target_count"]
        assert row["measurement_count_max"] > row["target_count"]
        assert row["global_track_id_owner"] == "d2_center"
        assert row["online_truth_leakage_count"] == 0
        assert row["truth_metrics_available"] is True
        assert row["continuity_available"] is True
        assert isinstance(row["id_switch_count"], int)
        assert isinstance(row["track_continuity"], float)
        assert isinstance(row["false_track_count"], int)
        assert isinstance(row["rmse"], float)
        assert row["nis"]["available"] is True
        assert row["nees"]["available"] is True
        assert row["oosm_diagnostics"]["measurement_order_monotonic"] is True
