from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    EpisodeMetrics,
    EventRecord,
    GuidanceLawComparisonReportGenerator,
    MetricsCollector,
    ScenarioDefinition,
    ScenarioLibrary,
    compare_guidance_laws_same_seed,
    default_p1_governance_scenario_library,
)


def test_secondary_lifecycle_dwell_activation_and_reject_metrics() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=0.0,
                event_type="d4_secondary_readiness",
                metadata={"readiness_state": "registration_usable"},
            ),
            EventRecord(
                timestamp=2.0,
                event_type="d4_secondary_readiness",
                metadata={"readiness_state": "takeover_ready"},
            ),
            EventRecord(
                timestamp=4.0,
                event_type="d4_secondary_plan_state",
                metadata={"plan_state": "pending_secondary_plan"},
            ),
            EventRecord(
                timestamp=6.0,
                event_type="d4_secondary_plan_state",
                metadata={"plan_state": "secondary_plan_active"},
            ),
            EventRecord(timestamp=7.0, event_type="stale_plan_reject"),
            EventRecord(timestamp=8.0, event_type="secondary_lease_expired"),
            EventRecord(timestamp=9.0, event_type="secondary_takeover_fallback"),
        ]
    )

    metrics = collector.compute_episode("secondary_lifecycle", duration=10.0)

    assert metrics.secondary_registration_usable_dwell_s == pytest.approx(2.0)
    assert metrics.secondary_takeover_ready_dwell_s == pytest.approx(8.0)
    assert metrics.secondary_plan_pending_dwell_s == pytest.approx(2.0)
    assert metrics.secondary_plan_active_dwell_s == pytest.approx(4.0)
    assert metrics.secondary_activation_latency_s == pytest.approx(4.0)
    assert metrics.secondary_takeover_fallback_count == 1
    assert metrics.secondary_lease_expiry_count == 1
    assert metrics.stale_plan_reject_count == 1
    assert metrics.metadata["secondary_lifecycle_status"] == "available"


def test_d1_d3_governance_metrics_preserve_provenance_and_availability() -> None:
    provenance = {
        "schema_version": "governance.v1",
        "config_profile": "real-5v5",
        "config_version": "2026-07-11",
        "config_hash": "sha256:test",
        "source_commit": "abc123",
        "schema_valid": True,
    }
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=0.0,
                event_type="d1_latency_audit",
                metadata={
                    **provenance,
                    "observation_count": 100,
                    "oosm_observation_count": 10,
                    "stale_observation_count": 5,
                    "replay_count": 20,
                    "mean_delay_s": 0.2,
                    "max_delay_s": 1.0,
                },
            ),
            EventRecord(
                timestamp=1.0,
                event_type="d1_region_quality_window",
                metadata={
                    **provenance,
                    "coverage_cell": "cell-a",
                    "expected_coverage_cell_count": 2,
                    "track_count": 2,
                    "mean_a95_m": 4.0,
                    "mean_handover_readiness": 0.8,
                    "quality_flags": [],
                },
            ),
            EventRecord(
                timestamp=1.0,
                event_type="d1_region_quality_window",
                metadata={
                    **provenance,
                    "coverage_cell": "cell-b",
                    "expected_coverage_cell_count": 2,
                    "track_count": 3,
                    "mean_a95_m": 6.0,
                    "mean_handover_readiness": 0.6,
                    "quality_flags": ["source_gap"],
                },
            ),
            EventRecord(
                timestamp=2.0,
                event_type="d2_governance_summary",
                metadata={
                    **provenance,
                    "risk_profile": "dense-crossing",
                    "risk_profile_version": "risk-v2",
                    "association_risk_threshold_version": "risk-v2",
                    "frame_count": 10,
                    "soft_risk_frame_count": 3,
                    "hard_risk_frame_count": 2,
                    "max_hard_risk_score": 0.9,
                    "nis_mean": 2.0,
                    "nis_sample_count": 10,
                    "nis_in_confidence_count": 8,
                    "nees_mean": 5.0,
                    "nees_sample_count": 10,
                    "nees_in_confidence_count": 7,
                    "false_track_count": 2,
                    "initiated_track_count": 8,
                },
            ),
            EventRecord(
                timestamp=3.0,
                event_type="d3_governance_summary",
                metadata={
                    **provenance,
                    "feedback_profile": "terminal-feedback",
                    "feedback_profile_version": "feedback-v1",
                    "resource_count": 3,
                    "target_count": 5,
                    "assigned_count": 3,
                    "unassigned_target_count": 2,
                    "decision_count": 10,
                    "hysteresis_reject_count": 2,
                    "stale_reject_count": 1,
                    "feedback_record_count": 5,
                    "feedback_accepted_count": 4,
                },
            ),
        ]
    )

    metrics = collector.compute_episode("real_5v5_governance")

    assert metrics.governance_schema_provenance_rate == pytest.approx(1.0)
    assert metrics.governance_config_provenance_rate == pytest.approx(1.0)
    assert metrics.governance_schema_mismatch_count == 0
    assert metrics.d1_oosm_observation_rate == pytest.approx(0.1)
    assert metrics.d1_stale_observation_rate == pytest.approx(0.05)
    assert metrics.d1_replay_observation_rate == pytest.approx(0.2)
    assert metrics.d1_region_quality_coverage_rate == pytest.approx(1.0)
    assert metrics.d1_region_mean_a95_m == pytest.approx(5.2)
    assert metrics.d1_region_handover_readiness_mean == pytest.approx(0.68)
    assert metrics.d1_degraded_region_count == 1
    assert metrics.d2_soft_risk_frame_rate == pytest.approx(0.3)
    assert metrics.d2_hard_risk_frame_rate == pytest.approx(0.2)
    assert metrics.d2_nis_in_confidence_rate == pytest.approx(0.8)
    assert metrics.d2_nees_in_confidence_rate == pytest.approx(0.7)
    assert metrics.d2_false_track_count == 2
    assert metrics.d2_false_track_rate == pytest.approx(0.25)
    assert metrics.d3_resource_target_ratio == pytest.approx(0.6)
    assert metrics.d3_assignment_coverage_rate == pytest.approx(0.6)
    assert metrics.d3_unassigned_target_rate == pytest.approx(0.4)
    assert metrics.d3_hysteresis_reject_rate == pytest.approx(0.2)
    assert metrics.d3_stale_reject_rate == pytest.approx(0.1)
    assert metrics.d3_feedback_accept_rate == pytest.approx(0.8)
    assert metrics.metadata["d3_nm_case_counts"] == {"resource_limited": 1}
    assert metrics.metadata["d2_risk_profiles"]["versions"] == ["risk-v2"]
    assert metrics.metadata["d3_feedback_profiles"]["versions"] == [
        "feedback-v1"
    ]


def test_d1_d3_governance_is_unavailable_without_explicit_events() -> None:
    metrics = MetricsCollector().compute_episode("no_governance")

    assert metrics.governance_schema_provenance_rate is None
    assert metrics.d1_oosm_observation_rate is None
    assert metrics.d2_false_track_count is None
    assert metrics.d3_feedback_sample_count is None
    assert metrics.metadata["d1_d3_governance_status"] == "unavailable"


def test_secondary_lifecycle_is_unavailable_without_events() -> None:
    metrics = MetricsCollector().compute_episode("no_lifecycle", duration=10.0)

    assert metrics.secondary_plan_active_dwell_s is None
    assert metrics.secondary_activation_latency_s is None
    assert metrics.secondary_takeover_fallback_count is None
    assert metrics.metadata["secondary_lifecycle_status"] == "unavailable"


def test_yolo_mot_metrics_use_only_nested_offline_truth() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=0.0,
                event_type="d5_yolo_mot_frame",
                metadata={
                    "detection_backend": "yolov8",
                    "tracker_backend": "bytetrack",
                    "pipeline_latency_ms": 20.0,
                    "cpu_budget_utilization": 0.5,
                    "gpu_budget_utilization": 0.4,
                    "latency_budget_ms": 25.0,
                    "cross_view_candidate_count": 2,
                    "cross_view_registered_count": 1,
                    "offline_truth": {
                        "visible_truth_count": 2,
                        "matched_truth_count": 2,
                        "truth_to_local_track_id": {"A": "L1", "B": "L2"},
                    },
                },
            ),
            EventRecord(
                timestamp=1.0,
                event_type="d5_yolo_mot_frame",
                metadata={
                    "detection_backend": "yolov8",
                    "tracker_backend": "bytetrack",
                    "pipeline_latency_ms": 30.0,
                    "cpu_budget_utilization": 0.7,
                    "gpu_budget_utilization": 0.6,
                    "latency_budget_ms": 25.0,
                    "cross_view_candidate_count": 2,
                    "cross_view_registered_count": 2,
                    "offline_truth": {
                        "visible_truth_count": 2,
                        "matched_truth_count": 2,
                        "truth_to_local_track_id": {"A": "L1", "B": "L3"},
                    },
                },
            ),
            EventRecord(
                timestamp=2.0,
                event_type="d5_yolo_mot_frame",
                metadata={
                    "detection_backend": "yolov8",
                    "tracker_backend": "bytetrack",
                    "pipeline_latency_ms": 25.0,
                    "cross_view_candidate_count": 2,
                    "cross_view_registered_count": 1,
                    "actor_name": "offline-label-leaked-online",
                    "offline_truth": {
                        "visible_truth_count": 2,
                        "matched_truth_count": 1,
                        "truth_to_local_track_id": {"A": "L1"},
                    },
                },
            ),
        ]
    )

    metrics = collector.compute_episode("yolo_mot")

    assert metrics.visual_detection_recall == pytest.approx(5 / 6)
    assert metrics.local_id_continuity == pytest.approx(2 / 3)
    assert metrics.cross_view_registration_rate == pytest.approx(4 / 6)
    assert metrics.visual_pipeline_latency_ms == pytest.approx(25.0)
    assert metrics.visual_cpu_budget_utilization == pytest.approx(0.6)
    assert metrics.visual_gpu_budget_utilization == pytest.approx(0.5)
    assert metrics.visual_budget_violation_count == 1
    assert metrics.online_truth_field_violation_count == 1
    assert metrics.metadata["detection_backend_counts"] == {"yolov8": 3}
    assert metrics.metadata["tracker_backend_counts"] == {"bytetrack": 3}


def test_scenario_library_writes_versioned_seed_matrix(tmp_path: Path) -> None:
    library = ScenarioLibrary(
        [
            ScenarioDefinition(
                scenario_group="blocks_cv_nvn_secondary_takeover",
                scenario_version="v1",
                tags=("airsim", "secondary_takeover", "cross_view"),
                difficulty="stress",
                expected_failure_modes=("pending_secondary_plan", "lease_expired"),
                seeds=(2, 1),
                parameters={"drone_count": 5, "secondary_height_m": 200},
            )
        ]
    )

    outputs = library.write_bundle(tmp_path)
    rows = list(csv.DictReader(outputs["csv"].open(encoding="utf-8")))
    payload = json.loads(outputs["json"].read_text(encoding="utf-8"))

    assert [int(row["seed"]) for row in rows] == [1, 2]
    assert all(row["online_truth_policy"] == "forbidden" for row in rows)
    assert payload["schema_version"] == "d6-scenario-library-v1"
    assert payload["seed_matrix_row_count"] == 2
    report_text = outputs["markdown"].read_text(encoding="utf-8")
    assert "预期失败模式" in report_text
    assert "Expected failure modes" in report_text


def test_default_governance_scenario_library_has_5v5_and_nm_matrix(
    tmp_path: Path,
) -> None:
    library = default_p1_governance_scenario_library(seeds=(11, 12))
    outputs = library.write_bundle(tmp_path)
    payload = json.loads(outputs["json"].read_text(encoding="utf-8"))
    report_text = outputs["markdown"].read_text(encoding="utf-8")

    assert payload["scenario_count"] == 5
    assert payload["seed_matrix_row_count"] == 10
    groups = {row["scenario_group"] for row in payload["seed_matrix"]}
    assert "blocks_cv_5v5_d1_governance" in groups
    assert "blocks_cv_5v5_d2_governance" in groups
    assert "blocks_cv_5v5_d3_governance" in groups
    assert "blocks_cv_3r5t_d3_nm_governance" in groups
    assert "blocks_cv_5r3t_d3_nm_governance" in groups
    assert "场景定义" in report_text
    assert "预期失败模式" in report_text
    assert "Seed 矩阵摘要" in report_text
    assert "D6 只使用这些定义进行离线分组与报告" in report_text


def test_guidance_laws_are_compared_on_same_seed_and_write_bundle(
    tmp_path: Path,
) -> None:
    episodes = [
        _guidance_episode("radar_pn", seed=1, success=1, min_range=3.0),
        _guidance_episode("pure_pursuit", seed=1, success=0, min_range=5.0),
        _guidance_episode("png_vm", seed=1, success=2, min_range=1.0),
        _guidance_episode("png_ttc", seed=1, success=2, min_range=1.5),
        _guidance_episode("radar_pn", seed=2, success=1, min_range=2.5),
        _guidance_episode("png_vm", seed=2, success=2, min_range=0.8),
    ]

    paired, aggregate = compare_guidance_laws_same_seed(episodes)
    png_success = next(
        row
        for row in aggregate
        if row["candidate_law"] == "png_vm"
        and row["metric"] == "intercept_success_rate"
    )
    assert png_success["pair_count"] == 2
    assert png_success["paired_seeds"] == [1, 2]
    assert png_success["reference_mean"] == pytest.approx(0.5)
    assert png_success["candidate_mean"] == pytest.approx(1.0)
    assert len(paired) > len(aggregate)

    outputs = GuidanceLawComparisonReportGenerator().write_bundle(
        episodes,
        tmp_path,
    )
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
    assert "同 Seed" in outputs["markdown"].read_text(encoding="utf-8")


def test_guidance_comparison_rejects_duplicate_law_for_same_seed() -> None:
    episodes = [
        _guidance_episode("radar_pn", seed=1, success=1, min_range=2.0),
        _guidance_episode("radar_pn", seed=1, success=2, min_range=1.0),
    ]

    with pytest.raises(ValueError, match="duplicate experiment guidance law"):
        compare_guidance_laws_same_seed(episodes)


def _guidance_episode(
    law: str,
    *,
    seed: int,
    success: int,
    min_range: float,
) -> EpisodeMetrics:
    return EpisodeMetrics(
        episode_id=f"{law}_{seed}",
        seed=seed,
        metric_scope="execution",
        scenario_group="guidance_same_seed_n2",
        scenario_version=f"guidance:v1:seed{seed}:law{law}",
        drone_count=2,
        resource_count=2,
        target_count=2,
        camera_count=2,
        intercept_success_count=success,
        min_range_m=min_range,
        time_to_intercept_s=5.0,
        terminal_switch_allowed_rate=0.5,
        terminal_takeover_rate=0.5,
        gate_reject_count=2,
        metadata={
            "experiment_guidance_law": law,
            "intercept_status_counts": {
                "collision_intercept": success,
                "timeout": 2 - success,
            },
        },
    )
