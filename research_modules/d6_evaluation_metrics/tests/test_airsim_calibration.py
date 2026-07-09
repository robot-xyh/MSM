from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    AirSimCalibrationReportGenerator,
    STANDARD_MAPPING_VERSION,
    load_airsim_calibration_records,
    summarize_airsim_calibration_records,
)


def test_airsim_calibration_summary_loads_d4d5_and_main_bus_outputs(
    tmp_path: Path,
) -> None:
    batch_root = tmp_path / "p1_d4d5_mobile_recon_20260708_055948"
    seed1_case = batch_root / "p1_d4d5_mobile_recon_20260708_055948_seed001" / "case_001_no_degradation"
    seed2_case = batch_root / "p1_d4d5_mobile_recon_20260708_055948_seed002" / "case_001_no_degradation"
    _write_episode_fixture(
        seed1_case,
        seed=1,
        coverage_ratio=0.70,
        detect_count=72,
        cross_view_count=4,
        not_registered_count=1,
        unnecessary_count=1,
        reject_reasons={"d5_not_locked": 2},
        contract_reject_reasons={"d4_reassign_pending": 1},
        write_contract=True,
    )
    _write_episode_fixture(
        seed2_case,
        seed=2,
        coverage_ratio=0.60,
        detect_count=68,
        cross_view_count=3,
        not_registered_count=2,
        unnecessary_count=0,
        reject_reasons={"stable_frame_count_low": 3},
        contract_reject_reasons={},
        write_contract=False,
    )

    records = load_airsim_calibration_records([batch_root])
    rows = summarize_airsim_calibration_records(records)

    assert len(records) == 3
    execution_seed1 = _find_record(records, metric_scope="execution", seed=1)
    assert execution_seed1.scenario == "no_degradation"
    assert execution_seed1.drone_count == 3
    assert execution_seed1.resource_count == 3
    assert execution_seed1.target_count == 4
    assert execution_seed1.camera_count == 6
    assert execution_seed1.secondary_count == 2
    assert execution_seed1.secondary_height_above_targets_m == pytest.approx(200.0)
    assert execution_seed1.secondary_height_bucket == "secondary_200m"
    assert execution_seed1.secondary_fov_degrees == pytest.approx(80.0)
    assert execution_seed1.detection_backend == "simGetDetections"
    assert execution_seed1.comparison_role == "baseline"
    assert execution_seed1.scenario_version == "p1-calibration-v1"
    assert execution_seed1.standard_mapping_version == STANDARD_MAPPING_VERSION
    assert execution_seed1.evidence_path.endswith("main_episode_bus_metrics.json")
    assert "p1_calibration_v1" in execution_seed1.trend_key
    assert execution_seed1.secondary_network_mean_coverage_ratio == pytest.approx(0.70)
    assert execution_seed1.secondary_visible_target_union_ratio == pytest.approx(0.70)
    assert execution_seed1.secondary_detect_count == 72
    assert execution_seed1.funnel_detect_count == 72
    assert execution_seed1.projection_valid_rate == pytest.approx(0.95)
    assert execution_seed1.geometry_gate_pass_rate == pytest.approx(4 / 72)
    assert execution_seed1.registered_candidate_count == 4
    assert execution_seed1.stable_cross_view_registration_count == 4
    assert execution_seed1.not_registered_count == 1
    assert execution_seed1.funnel_cross_view_association_count == 4
    assert execution_seed1.cross_view_registration_count == 4
    assert execution_seed1.secondary_detect_available_but_not_registered_count == 1
    assert execution_seed1.funnel_reject_reason_counts["projection_invalid"] == 0
    assert execution_seed1.funnel_reject_reason_counts["geometry_gate_rejected"] == 68
    assert execution_seed1.funnel_reject_reason_counts["stability_window_failed"] == 0
    assert execution_seed1.funnel_reject_reason_counts["registered_to_global_track"] == 4
    assert execution_seed1.unnecessary_degradation_count == 1
    assert execution_seed1.d7_guidance_reject_reason_counts == {
        "d4_reassign_pending": 1,
        "d5_not_locked": 2,
    }

    execution_seed1_row = _find_row(rows, metric_scope="execution", seed="1")
    assert execution_seed1_row["scenario"] == "no_degradation"
    assert execution_seed1_row["secondary_height_above_targets_m"] == pytest.approx(200.0)
    assert execution_seed1_row["comparison_role"] == "baseline"
    assert execution_seed1_row["scenario_versions"] == ["p1-calibration-v1"]
    assert execution_seed1_row["standard_mapping_versions"] == [STANDARD_MAPPING_VERSION]
    assert execution_seed1_row["secondary_height_buckets"] == ["secondary_200m"]
    assert execution_seed1_row["secondary_fov_degrees"] == pytest.approx(80.0)
    assert execution_seed1_row["secondary_count"] == "2"
    assert execution_seed1_row["detection_backend"] == "simGetDetections"
    assert execution_seed1_row["drone_count"] == "3"
    assert execution_seed1_row["target_count"] == "4"
    assert execution_seed1_row["secondary_detect_count"] == 72
    assert execution_seed1_row["funnel_detect_count"] == 72
    assert execution_seed1_row["projection_valid_rate_mean"] == pytest.approx(0.95)
    assert execution_seed1_row["geometry_gate_pass_rate_mean"] == pytest.approx(4 / 72)
    assert execution_seed1_row["registered_candidate_count"] == 4
    assert execution_seed1_row["stable_cross_view_registration_count"] == 4
    assert execution_seed1_row["not_registered_count"] == 1
    assert execution_seed1_row["d7_guidance_reject_reason_counts"] == {
        "d4_reassign_pending": 1,
        "d5_not_locked": 2,
    }

    contract_seed1_row = _find_row(rows, metric_scope="contract", seed="1")
    assert contract_seed1_row["d7_guidance_reject_reason_counts"] == {
        "d4_reassign_pending": 1,
        "d5_not_locked": 2,
    }


def test_airsim_calibration_report_bundle_writes_csv_json_and_chinese_markdown(
    tmp_path: Path,
) -> None:
    baseline_case = tmp_path / "batch_seed003" / "case_001_baseline_200m"
    _write_episode_fixture(
        baseline_case,
        seed=3,
        coverage_ratio=0.50,
        detect_count=55,
        cross_view_count=1,
        not_registered_count=40,
        unnecessary_count=1,
        reject_reasons={"stable_frame_count_low": 4},
        contract_reject_reasons={"d5_not_locked": 2},
        write_contract=False,
        height_m=200.0,
        comparison_role="baseline",
    )
    height_case = tmp_path / "batch_seed003" / "case_002_enhanced_50m"
    _write_episode_fixture(
        height_case,
        seed=3,
        coverage_ratio=0.45,
        detect_count=55,
        cross_view_count=1,
        not_registered_count=40,
        unnecessary_count=1,
        reject_reasons={"stable_frame_count_low": 4},
        contract_reject_reasons={"d5_not_locked": 2},
        write_contract=False,
        height_m=50.0,
        comparison_role="enhanced",
    )
    seed_case = tmp_path / "batch_seed003" / "case_003_enhanced_200m"
    _write_episode_fixture(
        seed_case,
        seed=3,
        coverage_ratio=0.65,
        detect_count=75,
        cross_view_count=0,
        not_registered_count=65,
        unnecessary_count=2,
        reject_reasons={"network_union_incomplete": 13},
        contract_reject_reasons={"d5_not_locked": 5},
        write_contract=False,
        height_m=200.0,
        comparison_role="enhanced",
    )

    generator = AirSimCalibrationReportGenerator()
    outputs = generator.write_report_bundle([tmp_path], tmp_path / "d6_report")

    assert outputs["record_csv"].exists()
    assert outputs["summary_csv"].exists()
    assert outputs["summary_json"].exists()
    assert outputs["standard_mapping_csv"].exists()
    assert outputs["markdown"].exists()

    summary_rows = list(csv.DictReader(outputs["summary_csv"].open(encoding="utf-8")))
    assert summary_rows
    assert summary_rows[0]["detection_backend"] == "simGetDetections"
    assert "comparison_role" in summary_rows[0]
    assert "scenario_versions" in summary_rows[0]
    assert "standard_mapping_versions" in summary_rows[0]
    assert "evidence_paths" in summary_rows[0]
    assert "trend_keys" in summary_rows[0]
    assert "secondary_height_buckets" in summary_rows[0]
    assert "funnel_reject_reason_counts" in summary_rows[0]
    assert "network_union_incomplete" in summary_rows[0]["funnel_reject_reason_counts"]
    assert "projection_valid_rate_mean" in summary_rows[0]
    assert "stable_cross_view_registration_count" in summary_rows[0]

    summary_payload = json.loads(outputs["summary_json"].read_text(encoding="utf-8"))
    assert summary_payload["group_fields"][:3] == ["metric_scope", "seed", "scenario"]
    assert "comparison_role" in summary_payload["group_fields"]
    assert summary_payload["rows"][0]["secondary_count"] == "2"
    assert any(
        row["secondary_height_buckets"] == ["secondary_50m"]
        for row in summary_payload["rows"]
    )
    assert any(
        row["secondary_height_buckets"] == ["secondary_200m"]
        for row in summary_payload["rows"]
    )

    mapping_rows = list(
        csv.DictReader(outputs["standard_mapping_csv"].open(encoding="utf-8"))
    )
    assert mapping_rows
    assert any(row["standard_metric_family"] == "terminal" for row in mapping_rows)

    report_text = outputs["markdown"].read_text(encoding="utf-8")
    assert "D6 AirSim 多 Seed 校准报告" in report_text
    assert "Standard C-UAS Mapping" in report_text
    assert STANDARD_MAPPING_VERSION in report_text
    assert "COURAGEOUS/CEN C-UAS testing" in report_text
    assert "Detect-to-registration Funnel" in report_text
    assert "50m vs 200m Secondary Coverage" in report_text
    assert "Coverage Funnel" in report_text
    assert "Baseline vs Enhanced" in report_text
    assert "secondary_50m" in report_text
    assert "secondary_200m" in report_text
    assert "Delta enhanced-baseline" in report_text
    assert "Projection valid" in report_text
    assert "Stable registration" in report_text
    assert "Not registered" in report_text
    assert "Active precision" in report_text
    assert "Unnecessary degradation" in report_text
    assert "D7 Guidance Reject Reason" in report_text
    assert "D6 只消费日志" in report_text
    assert "p1-calibration-v1" in report_text
    assert "network_union_incomplete" in report_text
    assert "geometry_gate_rejected" in report_text
    assert "projection_invalid" in report_text
    assert "d5_not_locked" in report_text


def _find_record(records, *, metric_scope: str, seed: int):
    for record in records:
        if record.metric_scope == metric_scope and record.seed == seed:
            return record
    raise AssertionError(f"record not found: {metric_scope=} {seed=}")


def _find_row(rows, *, metric_scope: str, seed: str):
    for row in rows:
        if row["metric_scope"] == metric_scope and row["seed"] == seed:
            return row
    raise AssertionError(f"row not found: {metric_scope=} {seed=}")


def _write_episode_fixture(
    episode_dir: Path,
    *,
    seed: int,
    coverage_ratio: float,
    detect_count: int,
    cross_view_count: int,
    not_registered_count: int,
    unnecessary_count: int,
    reject_reasons: dict[str, int],
    contract_reject_reasons: dict[str, int],
    write_contract: bool,
    height_m: float = 200.0,
    comparison_role: str = "baseline",
    scenario_version: str = "p1-calibration-v1",
) -> None:
    episode_dir.mkdir(parents=True, exist_ok=True)
    settings_path = episode_dir.parent / "generated_settings" / "blocks_cv_n3_settings.json"
    _write_settings(settings_path)
    _write_json(
        episode_dir / "airsim_blocks_summary.json",
        {
            "connected": True,
            "episode_id": episode_dir.name,
            "frame_count": 13,
            "image_ok_count": 13,
            "metadata": {
                "actor_target_count": 4,
                "camera_vehicle_names": [
                    "Interceptor_Cam_1",
                    "Interceptor_Cam_2",
                    "Interceptor_Cam_3",
                    "Secondary_Recon_1",
                    "Secondary_Recon_2",
                    "Observer_Cam",
                ],
                "resource_vehicle_names": [
                    "Interceptor_Cam_1",
                    "Interceptor_Cam_2",
                    "Interceptor_Cam_3",
                ],
                "secondary_camera_vehicle_names": [
                    "Secondary_Recon_1",
                    "Secondary_Recon_2",
                ],
                "settings_path": str(settings_path),
                "first_frame": {"resource_count": 3, "truth_count": 4},
            },
        },
    )
    _write_json(
        episode_dir / "d4d5_stress_metrics.json",
        {
            "case_name": "no_degradation"
            if "no_degradation" in episode_dir.name
            else "degrade_to_secondary",
            "calibration_role": comparison_role,
            "scenario_version": scenario_version,
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "secondary_recon_mode": "mobile_recon_gimbal",
            "secondary_height_above_targets_m": height_m,
            "geometry": {
                "resource_camera_count": 3,
                "secondary_camera_count": 2,
                "target_count": 4,
                "secondary_height_above_targets_m": height_m,
            },
            "multi_target_fov_rate": 0.8,
            "secondary_visible_target_union_ratio": coverage_ratio,
            "secondary_network_mean_coverage_ratio": coverage_ratio,
            "secondary_network_joint_full_view_frame_rate": 0.0,
            "secondary_single_camera_full_view_frame_rate": 0.0,
            "projection_valid_rate": 0.95,
            "geometry_gate_pass_rate": cross_view_count / detect_count
            if detect_count
            else 0.0,
            "registered_candidate_count": cross_view_count,
            "stable_cross_view_registration_count": cross_view_count,
            "not_registered_count": not_registered_count,
            "secondary_gimbal_pointing_ok_rate": 1.0,
            "secondary_bbox_area_px_stats": {
                "count": detect_count,
                "mean": 3300.0 + seed,
            },
            "secondary_cue_pointing_error_m_stats": {
                "count": 10,
                "mean": 0.25,
            },
            "secondary_detect_available_but_not_registered_count": not_registered_count,
            "cross_view_association_count": cross_view_count,
            "secondary_detection_funnel_counts": {
                "detect_count": detect_count,
                "local_or_recon_cue_count": 0,
                "multi_support_count": 0,
                "cross_view_association_count": cross_view_count,
                "terminal_association_count": 0,
                "breakpoint_reasons": [
                    "not_all_targets_visible",
                    "network_union_incomplete",
                ],
                "rejection_reason_counts": {
                    "geometry_gate_rejected": max(detect_count - cross_view_count, 0),
                    "not_all_targets_visible": 26,
                    "network_union_incomplete": 13,
                    "projection_invalid": 0,
                    "stability_window_failed": 0,
                    "no_global_binding": 0,
                    "stale_or_missing_recon_cue": 0,
                    "registered_to_global_track": cross_view_count,
                },
            },
        },
    )
    main_bus_dir = episode_dir / "main_episode_bus"
    main_bus_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        main_bus_dir / "main_episode_bus_metrics.json",
        _main_bus_payload(
            episode_dir.name,
            seed=seed,
            unnecessary_count=unnecessary_count,
            reject_reasons=reject_reasons,
            contract_reject_reasons=contract_reject_reasons,
            comparison_role=comparison_role,
            scenario_version=scenario_version,
        ),
    )
    if write_contract:
        _write_json(
            main_bus_dir / "main_episode_bus_contract_metrics.json",
            _main_bus_payload(
                episode_dir.name,
                seed=seed,
                unnecessary_count=unnecessary_count,
                reject_reasons=reject_reasons,
                contract_reject_reasons=contract_reject_reasons,
                comparison_role=comparison_role,
                scenario_version=scenario_version,
            ),
        )


def _main_bus_payload(
    episode_id: str,
    *,
    seed: int,
    unnecessary_count: int,
    reject_reasons: dict[str, int],
    contract_reject_reasons: dict[str, int],
    comparison_role: str,
    scenario_version: str,
) -> dict[str, object]:
    return {
        "metrics": {
            "episode_id": episode_id,
            "seed": seed,
            "batch_seed": seed,
            "scenario_group": "blocks_cv_5v5_d4d5_stress",
            "scenario_version": scenario_version,
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "evidence_path": f"evidence/{episode_id}/main_episode_bus_metrics.json",
            "drone_count": 3,
            "resource_count": 3,
            "target_count": 4,
            "camera_count": 6,
            "active_degradation_count": 4,
            "active_degradation_precision": 0.5,
            "unnecessary_active_degradation_count": unnecessary_count,
            "terminal_switch_reject_count": sum(reject_reasons.values()),
            "terminal_contract_reject_count": sum(contract_reject_reasons.values()),
            "gate_reject_count": sum(reject_reasons.values())
            + sum(contract_reject_reasons.values()),
            "metadata": {
                "comparison_role": comparison_role,
                "scenario_version": scenario_version,
                "standard_mapping_version": STANDARD_MAPPING_VERSION,
                "guidance_law_counts": {"png_vm": 2, "radar_pn": 1},
                "terminal_switch_reject_reasons": reject_reasons,
                "terminal_contract_reject_reasons": contract_reject_reasons,
            },
        }
    }


def _write_settings(path: Path) -> None:
    _write_json(
        path,
        {
            "Vehicles": {
                "Interceptor_Cam_1": {"VehicleType": "ComputerVision"},
                "Interceptor_Cam_2": {"VehicleType": "ComputerVision"},
                "Interceptor_Cam_3": {"VehicleType": "ComputerVision"},
                "Secondary_Recon_1": {
                    "VehicleType": "ComputerVision",
                    "Cameras": {
                        "0": {
                            "CaptureSettings": [
                                {
                                    "ImageType": 0,
                                    "FOV_Degrees": 80.0,
                                    "Width": 1920,
                                    "Height": 1080,
                                }
                            ]
                        }
                    },
                },
                "Secondary_Recon_2": {
                    "VehicleType": "ComputerVision",
                    "Cameras": {
                        "0": {
                            "CaptureSettings": [
                                {
                                    "ImageType": 0,
                                    "FOV_Degrees": 80.0,
                                    "Width": 1920,
                                    "Height": 1080,
                                }
                            ]
                        }
                    },
                },
                "Observer_Cam": {"VehicleType": "ComputerVision"},
            }
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
