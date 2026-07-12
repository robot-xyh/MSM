"""Static C-UAS standard mapping for D6 offline metrics.

The mapping is intentionally lightweight. It names how local engineering
metrics line up with standard C-UAS evaluation families without adding external
certification dependencies or changing runtime behavior.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


STANDARD_MAPPING_VERSION = "cuas-standard-map-v1"
STANDARD_MAPPING_CSV_FIELDNAMES = [
    "engineering_metric",
    "standard_metric_family",
    "standard_sources",
    "implementation_status",
    "evidence_requirement",
]

COURAGEOUS_SOURCE = "COURAGEOUS/CEN C-UAS testing"
MDPI_SOURCE = "MDPI C-UAS evaluation review"
OCEF_SOURCE = "OCEF reproducibility discipline"


@dataclass(frozen=True)
class StandardMetricMapping:
    """One local engineering metric mapped to a standard metric family."""

    engineering_metric: str
    standard_metric_family: str
    standard_sources: tuple[str, ...]
    implementation_status: str
    evidence_requirement: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "engineering_metric": self.engineering_metric,
            "standard_metric_family": self.standard_metric_family,
            "standard_sources": "; ".join(self.standard_sources),
            "implementation_status": self.implementation_status,
            "evidence_requirement": self.evidence_requirement,
        }


def _family_rows(
    family: str,
    metrics: tuple[str, ...],
    sources: tuple[str, ...],
    evidence_requirement: str,
    implementation_status: str = "implemented",
) -> tuple[StandardMetricMapping, ...]:
    return tuple(
        StandardMetricMapping(
            engineering_metric=metric,
            standard_metric_family=family,
            standard_sources=sources,
            implementation_status=implementation_status,
            evidence_requirement=evidence_requirement,
        )
        for metric in metrics
    )


STANDARD_METRIC_MAPPINGS: tuple[StandardMetricMapping, ...] = (
    *_family_rows(
        "mission/root cause",
        (
            "mission_outcome",
            "success_reason",
            "failure_reason",
            "metadata.root_cause",
            "metadata.top_failure_causes",
            "metadata.failure_cause_scores",
            "metadata.failure_cause_details",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE, OCEF_SOURCE),
        "Mission outcome or abort/success/failure events plus D6 root-cause metadata.",
    ),
    *_family_rows(
        "detection",
        (
            "detection_probability",
            "false_alarm_rate",
            "missed_detection_rate",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "Truth opportunities, truth-matched TrackRecord rows, and false-alarm records.",
    ),
    *_family_rows(
        "tracking",
        (
            "track_rmse",
            "track_continuity",
            "id_switch_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "TrackRecord timestamps, global_track_id, truth_id, positions, and truth positions.",
    ),
    *_family_rows(
        "assignment",
        (
            "duplicate_assignment_count",
            "unassigned_high_threat_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "AssignmentRecord plan_id/version/resource/global_track_id plus high-threat labels.",
    ),
    *_family_rows(
        "governance",
        (
            "governance_schema_provenance_rate",
            "governance_config_provenance_rate",
            "governance_schema_mismatch_count",
            "d1_oosm_observation_rate",
            "d1_stale_observation_rate",
            "d1_replay_observation_rate",
            "d1_mean_delay_s",
            "d1_max_delay_s",
            "d1_region_quality_coverage_rate",
            "d1_region_mean_a95_m",
            "d1_region_handover_readiness_mean",
            "d1_degraded_region_count",
            "d2_soft_risk_frame_rate",
            "d2_hard_risk_frame_rate",
            "d2_max_association_risk",
            "d2_nis_mean",
            "d2_nis_in_confidence_rate",
            "d2_nees_mean",
            "d2_nees_in_confidence_rate",
            "d2_false_track_count",
            "d2_false_track_rate",
            "d3_resource_target_ratio",
            "d3_assignment_coverage_rate",
            "d3_unassigned_target_rate",
            "d3_hysteresis_reject_rate",
            "d3_stale_reject_rate",
            "d3_feedback_accept_rate",
            "d3_feedback_sample_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE, OCEF_SOURCE),
        "Versioned D1-D3 summary events with schema/config provenance and offline evidence.",
    ),
    *_family_rows(
        "degradation",
        (
            "failover_time",
            "consensus_rounds",
            "degraded_completion_rate",
            "active_degradation_count",
            "active_degradation_precision",
            "active_degradation_label_count",
            "unnecessary_active_degradation_count",
            "passive_failover_count",
            "secondary_node_takeover_count",
            "secondary_reassignment_count",
            "d4_reassign_pending_count",
            "distributed_fallback_count",
            "failover_active_window_delta_s",
            "secondary_registration_usable_dwell_s",
            "secondary_takeover_ready_dwell_s",
            "secondary_plan_pending_dwell_s",
            "secondary_plan_active_dwell_s",
            "secondary_activation_latency_s",
            "secondary_takeover_fallback_count",
            "secondary_lease_expiry_count",
            "stale_plan_reject_count",
            "coalition_commit_count",
            "coalition_required_member_count",
            "coalition_acked_member_count",
            "coalition_member_ack_rate",
            "coalition_ack_latency_s",
            "coalition_commit_timeout_count",
            "coalition_commit_aborted_count",
            "coalition_commit_reconfiguring_count",
            "coalition_commit_lease_expired_count",
            "secondary_coalition_commit_count",
            "distributed_coalition_commit_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "D4/main failover, active/passive degradation, takeover, reassignment, and review metadata.",
    ),
    *_family_rows(
        "terminal",
        (
            "terminal_association_accuracy",
            "terminal_id_switch_count",
            "ambiguous_fov_event_count",
            "friend_overlap_hold_count",
            "time_to_terminal_lock",
            "terminal_lock_count",
            "multi_view_consensus_rate",
            "cross_view_conflict_count",
            "duplicate_terminal_lock_count",
            "secondary_network_joint_full_view_frame_rate",
            "secondary_network_mean_coverage_ratio",
            "secondary_single_camera_full_view_frame_rate",
            "cross_view_association_count",
            "secondary_detect_available_but_not_registered_count",
            "cue_pointing_error_count",
            "cue_pointing_error_mean_deg",
            "cue_pointing_error_rmse_deg",
            "cue_pointing_error_max_deg",
            "gimbal_pointing_error_count",
            "gimbal_pointing_error_mean_deg",
            "gimbal_pointing_error_rmse_deg",
            "gimbal_pointing_error_max_deg",
            "visual_detection_recall",
            "local_id_continuity",
            "cross_view_registration_rate",
            "online_truth_field_violation_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "TerminalRecord rows and D5/main multi-view, registration, coverage, cue, and gimbal metadata.",
    ),
    *_family_rows(
        "communication",
        (
            "cross_node_latency_ms",
            "message_drop_rate",
            "out_of_order_count",
            "stale_track_update_count",
            "video_metadata_delivery_rate",
            "bbox_delivery_rate",
            "consensus_latency_s",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE, OCEF_SOURCE),
        "LinkRecord or communication EventRecord timestamps, delivery state, sequence IDs, and stale thresholds.",
    ),
    *_family_rows(
        "guidance/intercept",
        (
            "camera_quality_gate_pass_rate",
            "los_quality_gate_pass_rate",
            "maneuver_margin_gate_pass_rate",
            "terminal_switch_allowed_rate",
            "visual_png_switch_count",
            "terminal_takeover_rate",
            "terminal_switch_reject_count",
            "mode_switch_count",
            "terminal_contract_reject_count",
            "contract_evaluated_count",
            "contract_allowed_count",
            "contract_allowed_rate",
            "control_evaluated_count",
            "control_allowed_count",
            "control_allowed_rate",
            "mode_switched_count",
            "physical_intercept_count",
            "pair_physical_success_count",
            "pair_physical_success_rate",
            "target_intercept_success_count",
            "target_intercept_success_rate",
            "coalition_completion_count",
            "coalition_completion_rate",
            "detection_acquisition_timeout_count",
            "image_kf_predict_count",
            "blind_push_count",
            "visual_reacquisition_count",
            "terminal_visual_lost_after_coast_count",
            "truth_identity_online_use_count",
            "terminal_filter_measured_count",
            "terminal_filter_predicted_count",
            "terminal_filter_innovation_rejected_count",
            "terminal_filter_reset_count",
            "terminal_filter_expired_count",
            "ttc_area_jump_reject_count",
            "ttc_bbox_clipping_reject_count",
            "ttc_not_expanding_reject_count",
            "ttc_out_of_range_reject_count",
            "soft_prediction_count",
            "soft_prediction_duration_s",
            "soft_prediction_expired_count",
            "terminal_coast_count",
            "terminal_coast_duration_s",
            "terminal_coast_expired_count",
            "terminal_lock_continuity",
            "visual_mode_duration_s",
            "command_discontinuity_mean_mps",
            "command_discontinuity_max_mps",
            "intercept_success_count",
            "collision_intercept_count",
            "range_intercept_count",
            "time_to_intercept_s",
            "min_range_m",
            "gate_reject_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "D7 control/guidance/intercept CSV/JSON or equivalent EventRecord metadata.",
    ),
    *_family_rows(
        "safety",
        (
            "constraint_violation_count",
            "human_override_count",
        ),
        (COURAGEOUS_SOURCE, MDPI_SOURCE),
        "Structured safety constraint violation and operator override/reject events.",
    ),
    *_family_rows(
        "performance",
        (
            "module_duration_ms",
            "loop_latency_ms",
            "record_latency_ms",
            "cpu_budget_utilization",
            "gpu_budget_utilization",
            "performance_budget_violation_count",
            "visual_pipeline_latency_ms",
            "visual_cpu_budget_utilization",
            "visual_gpu_budget_utilization",
            "visual_budget_violation_count",
        ),
        (MDPI_SOURCE, OCEF_SOURCE),
        "Module timing, loop latency, record latency, CPU/GPU budget, and budget violation metadata.",
    ),
    *_family_rows(
        "reproducibility/evidence",
        (
            "episode_id",
            "seed",
            "batch_seed",
            "scenario_group",
            "scenario_version",
            "metric_scope",
            "drone_count",
            "resource_count",
            "target_count",
            "camera_count",
            "evidence_path",
            "standard_mapping_version",
            "standard_metric_family_summary",
        ),
        (COURAGEOUS_SOURCE, OCEF_SOURCE),
        "Episode identity, seed, actual scale, scenario version, mapping version, metric scope, and evidence path.",
    ),
)


def standard_mapping_csv_rows() -> list[dict[str, str]]:
    return [mapping.to_csv_row() for mapping in STANDARD_METRIC_MAPPINGS]


def standard_metric_families() -> list[str]:
    seen: list[str] = []
    for mapping in STANDARD_METRIC_MAPPINGS:
        if mapping.standard_metric_family not in seen:
            seen.append(mapping.standard_metric_family)
    return seen


def standard_metric_family_counts() -> dict[str, int]:
    counts = Counter(mapping.standard_metric_family for mapping in STANDARD_METRIC_MAPPINGS)
    return {family: counts[family] for family in standard_metric_families()}


def standard_metric_family_summary() -> str:
    return "; ".join(
        f"{family}={count}"
        for family, count in standard_metric_family_counts().items()
    )


def standard_mapping_summary() -> dict[str, Any]:
    sources: list[str] = []
    statuses = Counter(mapping.implementation_status for mapping in STANDARD_METRIC_MAPPINGS)
    for mapping in STANDARD_METRIC_MAPPINGS:
        for source in mapping.standard_sources:
            if source not in sources:
                sources.append(source)
    return {
        "version": STANDARD_MAPPING_VERSION,
        "mapped_metric_count": len(STANDARD_METRIC_MAPPINGS),
        "standard_metric_families": standard_metric_families(),
        "family_counts": standard_metric_family_counts(),
        "standard_sources": sources,
        "implementation_status_counts": dict(statuses),
        "field_names": list(STANDARD_MAPPING_CSV_FIELDNAMES),
    }


def standard_mapping_family_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    by_family: dict[str, list[StandardMetricMapping]] = {
        family: [] for family in standard_metric_families()
    }
    for mapping in STANDARD_METRIC_MAPPINGS:
        by_family[mapping.standard_metric_family].append(mapping)

    for family, mappings in by_family.items():
        statuses = sorted({mapping.implementation_status for mapping in mappings})
        sources: list[str] = []
        evidence_requirements: list[str] = []
        for mapping in mappings:
            for source in mapping.standard_sources:
                if source not in sources:
                    sources.append(source)
            if mapping.evidence_requirement not in evidence_requirements:
                evidence_requirements.append(mapping.evidence_requirement)
        rows.append(
            {
                "engineering_metric": ", ".join(
                    mapping.engineering_metric for mapping in mappings
                ),
                "standard_metric_family": family,
                "standard_sources": "; ".join(sources),
                "implementation_status": ", ".join(statuses),
                "evidence_requirement": " ".join(evidence_requirements),
            }
        )
    return rows
