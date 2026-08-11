from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.d5_long_range_registration import (
    D5_LONG_RANGE_REGISTRATION_SCHEMA_VERSION,
    D5LongRangeRegistrationReportGenerator,
    evaluate_d5_long_range_registration,
    load_d5_long_range_registration_episode,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_csv(
    path: Path,
    rows: list[dict],
    *,
    fieldnames: list[str] | None = None,
) -> None:
    names = fieldnames or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def _crossing_results(camera: str, total: int, evaluable: int) -> list[dict]:
    return [
        {
            "camera_vehicle_name": camera,
            "availability": index < evaluable,
            "unavailable_reason": (
                "" if index < evaluable else "missing_pair_observation:GT-1,GT-2"
            ),
        }
        for index in range(total)
    ]


def _mot_scope(
    *,
    short_gaps: int,
    reacquisition: int,
    crossing_total: int,
    crossing_evaluable: int,
    camera: str,
    effective_short_gaps: int | None = None,
) -> dict:
    scope = {
        "fragmentation_count": short_gaps,
        "reacquisition_count": reacquisition,
        "reacquisition_identity_changed_count": reacquisition,
        "id_switch_count": 0,
        "crossing_window_count": crossing_total,
        "crossing_evaluable_window_count": crossing_evaluable,
        "crossing_not_evaluable_window_count": crossing_total - crossing_evaluable,
        "crossing_id_switch_count": 0,
        "crossing_track_purity": 1.0,
        "crossing_track_continuity": 1.0,
        "crossing_window_results": _crossing_results(
            camera, crossing_total, crossing_evaluable
        ),
    }
    if effective_short_gaps is not None:
        scope["effective_short_gap_fragmentation_count"] = effective_short_gaps
    return scope


def _write_v2_baseline(root: Path) -> Path:
    evidence = root / "coverage_safe"
    evidence.mkdir(parents=True)
    _write_json(
        evidence / "metrics.json",
        {
            "schema_version": "d5-long-range-cv-scan-metrics-v2",
            "seed": 20260810,
            "association_accuracy": 0.9979317476732161,
            "association_evaluable_count": 1934,
            "id_switch_count": 0,
            "duplicate_assignment_count": 0,
            "online_truth_identity_use_count": 0,
            "global_track_id_rewrite_count": 0,
            "geometric_binding_switch_count": 7,
        },
    )
    center = _mot_scope(
        short_gaps=0,
        reacquisition=40,
        crossing_total=16,
        crossing_evaluable=1,
        camera="Center_CV",
    )
    interceptor = _mot_scope(
        short_gaps=3,
        reacquisition=8,
        crossing_total=15,
        crossing_evaluable=2,
        camera="Interceptor_CV",
    )
    aggregate = _mot_scope(
        short_gaps=3,
        reacquisition=48,
        crossing_total=31,
        crossing_evaluable=3,
        camera="aggregate",
    )
    aggregate["crossing_window_results"] = (
        center["crossing_window_results"] + interceptor["crossing_window_results"]
    )
    _write_json(
        evidence / "mot_continuity.json",
        {
            "schema_version": "d5-long-range-mot-continuity-v2",
            "aggregate": aggregate,
            "by_camera": {"Center_CV": center, "Interceptor_CV": interceptor},
        },
    )
    _write_csv(
        evidence / "associations.csv",
        [
            {
                "camera_id": "Center_CV:0",
                "assignment_selected": "True",
                "truth_identity_used": "False",
            },
            {
                "camera_id": "Interceptor_CV:0",
                "assignment_selected": "True",
                "truth_identity_used": "False",
            },
        ],
    )
    return root


def _write_v3_complete(root: Path, *, online_truth_use_count: int = 0) -> Path:
    root.mkdir(parents=True)
    event_rows: list[dict] = []
    dropout_rows: list[dict] = []
    for camera in ("Center_CV", "Interceptor_CV"):
        local_track_id = f"{camera}-L1"
        stream_id = f"episode-v3:{camera}:0"

        def event(
            name: str,
            timestamp: float,
            *,
            incumbent: str = "",
            candidate: str = "",
            reason: str,
            measured: bool,
            confirmed: bool,
            margin: str = "",
            prediction_age: str = "",
        ) -> dict:
            return {
                "record_type": "temporal_binding_event",
                "association_source": "temporal_geometric_detect",
                "resource_id": camera,
                "camera_id": "0",
                "stream_id": stream_id,
                "local_track_id": local_track_id,
                "incumbent_global_track_id": incumbent,
                "candidate_global_track_id": candidate,
                "binding_event": name,
                "binding_reason": reason,
                "measurement_timestamp": str(timestamp),
                "arrival_timestamp": str(timestamp + 0.001),
                "candidate_margin": margin,
                "candidate_margin_is_infinite": "False",
                "prediction_age_s": prediction_age,
                "measured_evidence": str(measured),
                "association_confirmed": str(confirmed),
                "terminal_authorization_allowed": "False",
                "truth_identity_used": "False",
                "camera_vehicle_name": camera,
            }

        event_rows.extend(
            [
                event(
                    "confirmed",
                    0.0,
                    candidate="GT-1",
                    reason="initial_measured_binding",
                    measured=True,
                    confirmed=True,
                ),
                event(
                    "held",
                    0.1,
                    incumbent="GT-1",
                    reason="measurement_missing_within_coast_window",
                    measured=False,
                    confirmed=False,
                    prediction_age="0.1",
                ),
                event(
                    "recovered",
                    0.2,
                    incumbent="GT-1",
                    candidate="GT-1",
                    reason="measured_binding_recovered_within_coast_window",
                    measured=True,
                    confirmed=True,
                ),
                event(
                    "pending",
                    0.3,
                    incumbent="GT-1",
                    candidate="GT-2",
                    reason="challenger_requires_consecutive_measured_frames",
                    measured=True,
                    confirmed=False,
                    margin="2.0",
                ),
                event(
                    "confirmed",
                    0.4,
                    incumbent="GT-1",
                    candidate="GT-2",
                    reason="challenger_confirmed_after_consecutive_measured_frames",
                    measured=True,
                    confirmed=True,
                    margin="2.0",
                ),
            ]
        )
        for timestamp, age in ((0.1, 0.1), (0.15, 0.15)):
            dropout_rows.append(
                {
                    "record_type": "temporal_prediction",
                    "association_source": "temporal_geometric_detect",
                    "resource_id": camera,
                    "camera_id": "0",
                    "stream_id": stream_id,
                    "global_track_id": "GT-1",
                    "local_track_id": local_track_id,
                    "local_track_state": "predicted",
                    "decision_state": "coast",
                    "predicted_center_px": "[100.0, 200.0]",
                    "predicted_bbox": "[90.0, 190.0, 110.0, 210.0]",
                    "prediction_covariance_px": "[[4.0, 0.0], [0.0, 4.0]]",
                    "prediction_age_s": str(age),
                    "last_measurement_timestamp": "0.0",
                    "measurement_timestamp": str(timestamp),
                    "arrival_timestamp": str(timestamp + 0.001),
                    "terminal_authorization_allowed": "False",
                    "truth_identity_used": "False",
                    "metadata": "{}",
                    "camera_vehicle_name": camera,
                }
            )

    binding_counts = {
        name: sum(row["binding_event"] == name for row in event_rows)
        for name in {row["binding_event"] for row in event_rows}
    }
    _write_json(
        root / "metrics.json",
        {
            "schema_version": "d5-long-range-cv-scan-metrics-v3",
            "seed": 31,
            "association_accuracy": 0.98,
            "association_evaluable_count": 100,
            "association_wrong_count": 2,
            "duplicate_assignment_count": 0,
            "online_truth_use_count": online_truth_use_count,
            "global_track_id_rewrite_count": 0,
            "geometric_binding_switch_count": 2,
            "temporal_association": {
                "coast_time_s": 0.25,
                "challenger_required_frames": 2,
                "binding_event_count": len(event_rows),
                "binding_event_counts": binding_counts,
                "coasted_record_count": len(dropout_rows),
                "coasted_binding_count": 2,
                "recovery_count": 2,
                "expiry_count": 0,
                "confirmed_switch_count": 2,
                "raw_short_gap_fragmentation_count": 2,
                "effective_fragmentation_count": 0,
                "predicted_record_authorization_count": 0,
                "episode_scoped_state": True,
            },
        },
    )
    center = _mot_scope(
        short_gaps=1,
        effective_short_gaps=0,
        reacquisition=1,
        crossing_total=10,
        crossing_evaluable=5,
        camera="Center_CV",
    )
    interceptor = _mot_scope(
        short_gaps=1,
        effective_short_gaps=0,
        reacquisition=0,
        crossing_total=10,
        crossing_evaluable=5,
        camera="Interceptor_CV",
    )
    aggregate = _mot_scope(
        short_gaps=2,
        effective_short_gaps=0,
        reacquisition=1,
        crossing_total=20,
        crossing_evaluable=10,
        camera="aggregate",
    )
    aggregate["reacquisition_identity_changed_count"] = 0
    aggregate["crossing_window_results"] = (
        center["crossing_window_results"] + interceptor["crossing_window_results"]
    )
    _write_json(
        root / "mot_continuity.json",
        {
            "schema_version": "d5-long-range-mot-continuity-v3",
            "aggregate": aggregate,
            "by_camera": {"Center_CV": center, "Interceptor_CV": interceptor},
        },
    )

    association_rows: list[dict] = []
    for camera in ("Center_CV", "Interceptor_CV"):
        for index in range(50):
            association_rows.append(
                {
                    "camera_id": f"{camera}:0",
                    "assignment_selected": "True",
                    "association_source": "temporal_geometric_detect",
                    "measured_evidence": "True",
                    "truth_identity_used": "False",
                    "terminal_authorization_allowed": "False",
                }
            )
    _write_csv(root / "associations.csv", association_rows)
    _write_csv(root / "temporal_binding_events.csv", event_rows)
    _write_csv(root / "dropout_events.csv", dropout_rows)
    return root


def _write_frozen_sidecar_baseline(root: Path) -> Path:
    root.mkdir(parents=True)
    online_rows = [
        {
            "schema_version": "d5-long-range-online-replay-v1",
            "camera_vehicle_name": camera,
            "camera_id": f"{camera}:0",
            "frame_index": 10,
            "measurement_timestamp": 0.1,
            "global_tracks": [],
            "local_tracks": [],
            "truth_identity_used": False,
        }
        for camera in ("Center_CV", "Interceptor_CV")
    ]
    online_path = root / "online_replay.jsonl"
    online_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in online_rows),
        encoding="utf-8",
    )
    sidecar = {
        "schema_version": "d5-long-range-offline-sidecar-v1",
        "offline_truth_only": True,
        "incorrect_associations": [
            {"camera_vehicle_name": "Center_CV", "frame_index": index}
            for index in range(4)
        ],
        "binding_switches": [
            {"camera_id": "Center_CV:0", "frame_index": index}
            for index in range(7)
        ],
        "short_gaps": [
            {
                "camera_vehicle_name": "Interceptor_CV",
                "gap_s": value,
            }
            for value in (0.17, 0.10, 0.08)
        ],
        "truth_labels": [],
    }
    sidecar_path = root / "offline_truth_sidecar.json"
    _write_json(sidecar_path, sidecar)

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    _write_json(
        root / "baseline_manifest.json",
        {
            "schema_version": "d5-long-range-baseline-v1",
            "scenario_id": "frozen-v2",
            "online_fixture_record_count": 2,
            "frozen_fixture_sha256": {
                "online_replay.jsonl": sha(online_path),
                "offline_truth_sidecar.json": sha(sidecar_path),
            },
            "core_metrics": {
                "seed": 20260810,
                "target_count": 20,
                "association_accuracy": 0.9979317476732161,
                "association_evaluable_count": 1934,
                "id_switch_count": 0,
                "short_gap_fragmentation_count": 3,
                "reacquisition_count": 48,
                "geometric_binding_switch_count": 7,
                "crossing_window_count": 31,
                "crossing_evaluable_window_count": 3,
                "duplicate_assignment_count": 0,
                "online_truth_identity_use_count": 0,
                "global_track_id_rewrite_count": 0,
            },
            "failure_counts": {
                "incorrect_association_count": 4,
                "binding_switch_count": 7,
                "short_gap_count": 3,
                "crossing_unavailable_reason_counts": {
                    "missing_pair_observation": 28
                },
            },
            "identity_boundary": {
                "online_actor_or_object_identity_present": False,
                "truth_sidecar_offline_only": True,
                "global_track_id_center_owned": True,
            },
        },
    )
    return root


def test_v2_frozen_baseline_is_compatible_and_fail_closed(tmp_path: Path) -> None:
    episode = load_d5_long_range_registration_episode(
        _write_v2_baseline(tmp_path / "baseline-v2")
    )
    result = evaluate_d5_long_range_registration(episode)
    metrics = result["aggregate"]

    assert result["schema_version"] == D5_LONG_RANGE_REGISTRATION_SCHEMA_VERSION
    assert metrics["association_accuracy"]["value"] == pytest.approx(
        0.9979317476732161
    )
    assert metrics["association_evaluable_count"]["value"] == 1934
    assert metrics["association_wrong_count"]["value"] == 4
    assert metrics["id_switch_count"]["value"] == 0
    assert metrics["measured_short_gap_count"]["value"] == 3
    assert metrics["effective_short_gap_fragmentation_count"]["value"] == 3
    assert metrics["long_reacquisition_count"]["value"] == 48
    assert metrics["geometric_binding_switch_count"]["value"] == 7
    assert metrics["crossing_evaluable_count"]["value"] == 3
    assert metrics["crossing_total_count"]["value"] == 31
    assert metrics["duplicate_assignment_count"]["value"] == 0
    assert metrics["online_truth_use_count"]["value"] == 0
    assert metrics["global_track_id_rewrite_count"]["value"] == 0
    assert metrics["bounded_coast_frame_count"]["availability"] == "unavailable"
    assert metrics["binding_oscillation_count"]["availability"] == "unavailable"
    assert result["status"] == "fail_closed"
    assert result["p1_closed"] is False


def test_frozen_online_replay_and_truth_sidecar_are_scored_without_online_truth(
    tmp_path: Path,
) -> None:
    root = _write_frozen_sidecar_baseline(tmp_path / "frozen-sidecar")
    result = evaluate_d5_long_range_registration(root)
    episode = result["episodes"][0]
    metrics = result["aggregate"]

    assert episode["artifacts"]["frozen_baseline"]["availability"] == "available"
    assert episode["artifacts"]["associations"]["availability"] == "unavailable"
    assert metrics["association_accuracy"]["value"] == pytest.approx(
        0.9979317476732161
    )
    assert metrics["association_wrong_count"]["value"] == 4
    assert metrics["measured_short_gap_count"]["value"] == 3
    assert metrics["measured_short_gap_total_duration_s"]["value"] == pytest.approx(
        0.35
    )
    assert metrics["online_truth_use_count"]["value"] == 0
    assert metrics["binding_oscillation_count"]["availability"] == "unavailable"
    assert result["status"] == "fail_closed"


def test_v3_complete_fields_pass_structural_and_actual_crossing_gates(
    tmp_path: Path,
) -> None:
    root = _write_v3_complete(tmp_path / "episode-v3")
    result = evaluate_d5_long_range_registration(root)
    metrics = result["aggregate"]

    assert metrics["measured_short_gap_count"]["value"] == 2
    assert metrics["measured_short_gap_total_duration_s"]["value"] == pytest.approx(0.4)
    assert metrics["effective_short_gap_fragmentation_count"]["value"] == 0
    assert metrics["bounded_coast_event_count"]["value"] == 2
    assert metrics["bounded_coast_frame_count"]["value"] == 4
    assert metrics["bounded_coast_max_age_s"]["value"] == pytest.approx(0.15)
    assert metrics["bounded_coast_same_id_recovery_count"]["value"] == 2
    assert metrics["coast_expiry_count"]["value"] == 0
    assert metrics["binding_switch_pending_count"]["value"] == 2
    assert metrics["binding_switch_confirmed_count"]["value"] == 2
    assert metrics["binding_oscillation_count"]["value"] == 0
    assert metrics["crossing_availability_ratio"]["value"] == pytest.approx(0.5)
    assert result["gates"]["structural_gate_passed"] is True
    assert result["gates"]["actual_crossing_gate"]["passed"] is True
    assert result["status"] == "passed"
    assert result["p1_closed"] is False


def test_missing_fields_remain_unavailable_instead_of_zero(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    root.mkdir()
    _write_json(root / "metrics.json", {"schema_version": "v3"})
    _write_json(root / "mot_continuity.json", {"aggregate": {}})
    _write_csv(
        root / "associations.csv",
        [{"camera_id": "Cam-A:0", "truth_identity_used": "False"}],
    )

    result = evaluate_d5_long_range_registration(root)
    metrics = result["aggregate"]

    assert metrics["association_accuracy"] == {
        "availability": "unavailable",
        "value": None,
        "reason": "one_or_more_all_episodes_values_unavailable",
        "source": None,
    }
    assert metrics["binding_oscillation_count"]["value"] is None
    assert metrics["crossing_total_count"]["value"] is None
    assert result["gates"]["structural_gate_passed"] is False
    assert result["status"] == "fail_closed"


def test_empty_main_csv_files_are_unavailable_without_blocking_report(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty-main-csv"
    root.mkdir()
    _write_json(
        root / "metrics.json",
        {
            "schema_version": "d5-long-range-cv-scan-metrics-v3",
            "temporal_association": {
                "binding_event_count": 0,
                "coasted_record_count": 0,
            },
        },
    )
    _write_json(root / "mot_continuity.json", {"aggregate": {}})
    for name in (
        "associations.csv",
        "temporal_binding_events.csv",
        "dropout_events.csv",
    ):
        (root / name).write_text("", encoding="utf-8")

    result = evaluate_d5_long_range_registration(root)
    artifacts = result["episodes"][0]["artifacts"]

    for name in ("associations", "temporal_binding_events", "dropout_events"):
        assert artifacts[name]["availability"] == "unavailable"
        assert artifacts[name]["reason"] == "empty_file_no_header"
    assert result["aggregate"]["association_accuracy"]["value"] is None
    assert result["aggregate"]["binding_oscillation_count"]["value"] is None
    assert result["status"] == "fail_closed"


def test_geometry_preflight_never_substitutes_for_actual_crossing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "preflight-only"
    root.mkdir()
    _write_json(
        root / "metrics.json",
        {
            "association_accuracy": 1.0,
            "association_evaluable_count": 20,
            "association_wrong_count": 0,
            "duplicate_assignment_count": 0,
            "online_truth_use_count": 0,
            "global_track_id_rewrite_count": 0,
            "crossing_geometry_preflight": {
                "crossing_window_count": 30,
                "evaluable_window_count": 30,
            },
        },
    )
    _write_json(
        root / "mot_continuity.json",
        {
            "aggregate": {
                "fragmentation_count": 0,
                "effective_short_gap_fragmentation_count": 0,
                "reacquisition_count": 0,
                "reacquisition_identity_changed_count": 0,
                "id_switch_count": 0,
            }
        },
    )
    _write_csv(
        root / "associations.csv",
        [
            {
                "camera_id": "Cam-A:0",
                "association_correct": "True",
                "truth_identity_used": "False",
                "duplicate_assignment": "False",
                "global_track_id_rewritten": "False",
            }
        ],
    )
    _write_csv(
        root / "temporal_binding_events.csv",
        [],
        fieldnames=["camera_id", "binding_event", "switch_event"],
    )
    _write_csv(
        root / "dropout_events.csv",
        [],
        fieldnames=[
            "camera_id",
            "dropout_event",
            "short_gap",
            "gap_duration_s",
            "coast_frame_count",
            "max_prediction_age_s",
            "same_id_recovery",
        ],
    )

    result = evaluate_d5_long_range_registration(root)

    crossing = result["episodes"][0]["aggregate"]["crossing_total_count"]
    assert crossing["availability"] == "unavailable"
    assert "preflight_not_accepted" in crossing["reason"]
    gate = result["gates"]["actual_crossing_gate"]
    assert gate["geometry_preflight_accepted"] is False
    assert gate["status"] == "unavailable"


def test_gate_failure_and_report_bundle_outputs(tmp_path: Path) -> None:
    episode = _write_v3_complete(
        tmp_path / "unsafe-v3",
        online_truth_use_count=1,
    )
    output = tmp_path / "report"
    paths = D5LongRangeRegistrationReportGenerator().write_report_bundle(
        output,
        episode,
    )

    assert set(paths) == {"per_episode_csv", "aggregate_json", "markdown", "plot"}
    assert all(path.exists() for path in paths.values())
    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["status"] == "fail_closed"
    truth_gate = aggregate["gates"]["structural_checks"]["online_truth_use_count"]
    assert truth_gate["status"] == "failed"
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "失败关闭" in markdown
    assert "不声称P1" in markdown
    assert "几何预检" in markdown
    assert paths["plot"].stat().st_size > 0
