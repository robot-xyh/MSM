"""Offline metric collection for D6 evaluation.

The collector is intentionally passive: it consumes recorded observations and
events, then emits episode-level metrics for reports and statistical analysis.
It does not produce tasking, control, targeting, or authorization decisions.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Iterable, Mapping, Sequence

from .m_to_n import (
    M_TO_N_METRIC_NAMES,
    compute_m_to_n_metrics,
)
from .standard_mapping import (
    STANDARD_MAPPING_VERSION,
    standard_mapping_summary,
    standard_metric_families,
    standard_metric_family_summary as _standard_metric_family_summary,
)


Position = Sequence[float]

_D1_D3_GOVERNANCE_METRIC_NAMES = (
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
)

_TERMINAL_DELIVERY_METRIC_NAMES = (
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
)


@dataclass(frozen=True)
class TrackRecord:
    """Offline tracking or detection record aligned to optional truth data."""

    timestamp: float
    global_track_id: str | None
    truth_id: str | None
    position: Position | None = None
    truth_position: Position | None = None
    covariance_trace: float | None = None
    track_state: str = "active"
    association_source: str = "offline"


@dataclass(frozen=True)
class AssignmentRecord:
    """Offline assignment snapshot record.

    ``truth_id`` is optional evaluator-side annotation for measuring outcomes.
    It is not required in operational logs and is never used to make decisions.
    """

    timestamp: float
    plan_id: str
    version: int
    resource_id: str
    global_track_id: str | None
    cost_breakdown: Mapping[str, float] = field(default_factory=dict)
    authorization_state: str = "recorded"
    active: bool = True
    truth_id: str | None = None
    coordination_mode: str | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    coalition_state: str | None = None
    member_role: str | None = None
    wave_id: str | int | None = None
    required_resource_count: int | None = None
    demand_assigned: int | None = None
    demand_shortfall: int | None = None
    demand_complete: bool | None = None
    arrival_window: Sequence[float] | None = None
    arrival_window_start: float | None = None
    arrival_window_end: float | None = None
    minimum_member_separation: float | None = None


@dataclass(frozen=True)
class TargetDemandRecord:
    """Target-side M-to-N demand snapshot aligned with the D3 contract."""

    timestamp: float
    global_track_id: str
    required_resource_count: int
    coordination_mode: str
    demand_assigned: int | None = None
    demand_shortfall: int | None = None
    demand_complete: bool | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    coalition_state: str | None = None
    wave_id: str | int | None = None
    arrival_window: Sequence[float] | None = None
    arrival_window_start: float | None = None
    arrival_window_end: float | None = None
    minimum_member_separation: float | None = None
    evidence_available: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoalitionRecord:
    """Versioned coalition lifecycle snapshot for passive evaluation."""

    timestamp: float
    global_track_id: str
    coalition_id: str
    coalition_version: int
    coalition_state: str
    coordination_mode: str
    member_ids: Sequence[str] = field(default_factory=tuple)
    member_roles: Mapping[str, str] = field(default_factory=dict)
    plan_id: str | None = None
    plan_version: int | None = None
    epoch: int | None = None
    coordinator_id: str | None = None
    coordinator_role: str | None = None
    required_member_ids: Sequence[str] = field(default_factory=tuple)
    acked_member_ids: Sequence[str] = field(default_factory=tuple)
    commit_state: str | None = None
    commit_reason: str | None = None
    lease_expires_at: float | None = None
    proposed_at: float | None = None
    updated_at: float | None = None
    committed_at: float | None = None
    executing_at: float | None = None
    resolved_at: float | None = None
    ack_latency_s: float | None = None
    member_role: str | None = None
    wave_id: str | int | None = None
    required_resource_count: int | None = None
    demand_assigned: int | None = None
    demand_shortfall: int | None = None
    demand_complete: bool | None = None
    arrival_window: Sequence[float] | None = None
    arrival_window_start: float | None = None
    arrival_window_end: float | None = None
    minimum_member_separation: float | None = None
    trigger_timestamp: float | None = None
    messages_sent: int | None = None
    messages_delivered: int | None = None
    payload_bytes_sent: int | None = None
    payload_bytes_delivered: int | None = None
    consensus_rounds: int | None = None
    latency_ms: float | None = None
    evidence_available: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArrivalRecord:
    """Member arrival or wave timing evidence for one coalition version."""

    timestamp: float
    global_track_id: str
    resource_id: str
    coalition_id: str
    coalition_version: int
    coalition_state: str
    member_role: str
    coordination_mode: str
    wave_id: str | int | None = None
    required_resource_count: int | None = None
    arrival_timestamp: float | None = None
    arrival_window: Sequence[float] | None = None
    arrival_window_start: float | None = None
    arrival_window_end: float | None = None
    wave_start_timestamp: float | None = None
    wave_complete_timestamp: float | None = None
    minimum_member_separation: float | None = None
    arrived: bool = True
    evidence_available: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventRecord:
    """Generic offline event record."""

    timestamp: float
    event_type: str
    actor_id: str | None = None
    severity: str = "info"
    note: str = ""
    value: float | int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinkRecord:
    """Optional cross-node communication record for offline evaluation."""

    timestamp: float
    source_node_id: str
    target_node_id: str | None = None
    relay_node_id: str | None = None
    link_type: str = "data"
    message_type: str = "data"
    sequence_id: int | str | None = None
    sent_timestamp: float | None = None
    received_timestamp: float | None = None
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    payload_kind: str = "data"
    delivered: bool = True
    stale_after_s: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalRecord:
    """Offline terminal registration record.

    ``expected_global_track_id`` and ``association_correct`` are evaluator
    annotations used only when truth labels are available.
    """

    timestamp: float
    resource_id: str
    assigned_global_track_id: str | None
    local_track_id: str | None
    decision_state: str = "observed"
    ambiguity_score: float | None = None
    friend_conflict_state: str = "none"
    assignment_version: int | None = None
    expected_global_track_id: str | None = None
    association_correct: bool | None = None
    authorization_state: str = "recorded"
    coordination_mode: str | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    coalition_state: str | None = None
    member_role: str | None = None
    wave_id: str | int | None = None
    required_resource_count: int | None = None
    demand_assigned: int | None = None
    demand_shortfall: int | None = None
    demand_complete: bool | None = None
    arrival_window: Sequence[float] | None = None
    arrival_window_start: float | None = None
    arrival_window_end: float | None = None
    minimum_member_separation: float | None = None


@dataclass
class EpisodeMetrics:
    """Scalar metrics for one offline episode."""

    episode_id: str
    seed: int | None = None
    scenario_group: str = "unlabeled"
    batch_seed: int | None = None
    metric_scope: str = "not_recorded"
    drone_count: int = 0
    resource_count: int = 0
    target_count: int = 0
    camera_count: int = 0
    duration: float = 0.0
    mission_outcome: str = "failed"
    success_reason: str = ""
    failure_reason: str = ""
    eval_priority: str = "P0"
    implementation_status: str = "implemented"
    evidence_path: str = ""
    scenario_version: str = ""
    standard_mapping_version: str = STANDARD_MAPPING_VERSION
    standard_metric_family_summary: str = ""
    detection_probability: float | None = None
    false_alarm_rate: float | None = None
    missed_detection_rate: float | None = None
    track_rmse: float = 0.0
    track_continuity: float = 0.0
    id_switch_count: int = 0
    duplicate_assignment_count: int = 0
    unassigned_high_threat_count: int = 0
    target_demand_satisfaction_rate_micro: float | None = None
    target_demand_satisfaction_rate_macro: float | None = None
    unmet_slot_count: int | None = None
    over_support_count: int | None = None
    coalition_formation_time_s: float | None = None
    coalition_reconfiguration_time_s: float | None = None
    simultaneous_arrival_dispersion_s: float | None = None
    common_window_success_rate: float | None = None
    wave_interval_s: float | None = None
    wave_order_violation_count: int | None = None
    primary_success_rate: float | None = None
    reserve_activation_count: int | None = None
    reserve_activation_rate: float | None = None
    reserve_activation_latency_s: float | None = None
    planned_cooperative_lock_count: int | None = None
    planned_cooperative_lock_success_rate: float | None = None
    authorized_cooperative_lock_count: int | None = None
    erroneous_duplicate_lock_count: int | None = None
    same_resource_lock_continuity_count: int | None = None
    replan_request_count: int | None = None
    replan_request_deduplicated_count: int | None = None
    replan_no_change_ack_count: int | None = None
    replan_applied_count: int | None = None
    replan_expired_count: int | None = None
    replan_pending_dwell_s: float | None = None
    replan_convergence_time_s: float | None = None
    coalition_commit_count: int | None = None
    coalition_required_member_count: int | None = None
    coalition_acked_member_count: int | None = None
    coalition_member_ack_rate: float | None = None
    coalition_ack_latency_s: float | None = None
    coalition_commit_timeout_count: int | None = None
    coalition_commit_aborted_count: int | None = None
    coalition_commit_reconfiguring_count: int | None = None
    coalition_commit_lease_expired_count: int | None = None
    secondary_coalition_commit_count: int | None = None
    distributed_coalition_commit_count: int | None = None
    coalition_member_loss_count: int | None = None
    coalition_member_replacement_count: int | None = None
    coalition_member_replacement_time_s: float | None = None
    coalition_digest_conflict_count: int | None = None
    coalition_stale_rejection_count: int | None = None
    coalition_stale_rejection_rate: float | None = None
    messages_sent_count: int | None = None
    messages_delivered_count: int | None = None
    messages_dropped_count: int | None = None
    payload_bytes_sent: float | None = None
    payload_bytes_delivered: float | None = None
    coalition_consensus_rounds: float | None = None
    end_to_end_latency_ms: float | None = None
    minimum_member_separation_m: float | None = None
    collision_risk_exposure_s: float | None = None
    geometry_rejection_count: int | None = None
    geometry_rejection_rate: float | None = None
    canonical_duplicate_count: int | None = None
    cross_node_id_switch_count: int | None = None
    common_information_duplicate_rejection_count: int | None = None
    common_information_duplicate_rejection_rate: float | None = None
    governance_schema_provenance_rate: float | None = None
    governance_config_provenance_rate: float | None = None
    governance_schema_mismatch_count: int | None = None
    d1_oosm_observation_rate: float | None = None
    d1_stale_observation_rate: float | None = None
    d1_replay_observation_rate: float | None = None
    d1_mean_delay_s: float | None = None
    d1_max_delay_s: float | None = None
    d1_region_quality_coverage_rate: float | None = None
    d1_region_mean_a95_m: float | None = None
    d1_region_handover_readiness_mean: float | None = None
    d1_degraded_region_count: int | None = None
    d2_soft_risk_frame_rate: float | None = None
    d2_hard_risk_frame_rate: float | None = None
    d2_max_association_risk: float | None = None
    d2_nis_mean: float | None = None
    d2_nis_in_confidence_rate: float | None = None
    d2_nees_mean: float | None = None
    d2_nees_in_confidence_rate: float | None = None
    d2_false_track_count: int | None = None
    d2_false_track_rate: float | None = None
    d3_resource_target_ratio: float | None = None
    d3_assignment_coverage_rate: float | None = None
    d3_unassigned_target_rate: float | None = None
    d3_hysteresis_reject_rate: float | None = None
    d3_stale_reject_rate: float | None = None
    d3_feedback_accept_rate: float | None = None
    d3_feedback_sample_count: int | None = None
    failover_time: float = 0.0
    consensus_rounds: float = 0.0
    degraded_completion_rate: float = 0.0
    active_degradation_count: int = 0
    active_degradation_precision: float | None = None
    active_degradation_label_count: int = 0
    unnecessary_active_degradation_count: int = 0
    passive_failover_count: int = 0
    secondary_node_takeover_count: int = 0
    secondary_reassignment_count: int = 0
    d4_reassign_pending_count: int = 0
    distributed_fallback_count: int = 0
    failover_active_window_delta_s: float = 0.0
    secondary_registration_usable_dwell_s: float | None = None
    secondary_takeover_ready_dwell_s: float | None = None
    secondary_plan_pending_dwell_s: float | None = None
    secondary_plan_active_dwell_s: float | None = None
    secondary_activation_latency_s: float | None = None
    secondary_takeover_fallback_count: int | None = None
    secondary_lease_expiry_count: int | None = None
    stale_plan_reject_count: int | None = None
    terminal_association_accuracy: float = 0.0
    terminal_id_switch_count: int = 0
    ambiguous_fov_event_count: int = 0
    friend_overlap_hold_count: int = 0
    time_to_terminal_lock: float = 0.0
    terminal_lock_count: int = 0
    multi_view_consensus_rate: float = 0.0
    cross_view_conflict_count: int = 0
    duplicate_terminal_lock_count: int = 0
    visual_detection_recall: float | None = None
    local_id_continuity: float | None = None
    cross_view_registration_rate: float | None = None
    visual_pipeline_latency_ms: float | None = None
    visual_cpu_budget_utilization: float | None = None
    visual_gpu_budget_utilization: float | None = None
    visual_budget_violation_count: int | None = None
    online_truth_field_violation_count: int | None = None
    secondary_network_joint_full_view_frame_rate: float = 0.0
    secondary_network_mean_coverage_ratio: float = 0.0
    secondary_single_camera_full_view_frame_rate: float = 0.0
    cross_view_association_count: int = 0
    secondary_detect_available_but_not_registered_count: int = 0
    cue_pointing_error_count: int = 0
    cue_pointing_error_mean_deg: float = 0.0
    cue_pointing_error_rmse_deg: float = 0.0
    cue_pointing_error_max_deg: float = 0.0
    gimbal_pointing_error_count: int = 0
    gimbal_pointing_error_mean_deg: float = 0.0
    gimbal_pointing_error_rmse_deg: float = 0.0
    gimbal_pointing_error_max_deg: float = 0.0
    cross_node_latency_ms: float = 0.0
    message_drop_rate: float = 0.0
    out_of_order_count: int = 0
    stale_track_update_count: int = 0
    video_metadata_delivery_rate: float = 0.0
    bbox_delivery_rate: float = 0.0
    consensus_latency_s: float = 0.0
    camera_quality_gate_pass_rate: float = 0.0
    los_quality_gate_pass_rate: float = 0.0
    maneuver_margin_gate_pass_rate: float = 0.0
    terminal_switch_allowed_rate: float = 0.0
    visual_png_switch_count: int = 0
    terminal_takeover_rate: float = 0.0
    terminal_switch_reject_count: int = 0
    mode_switch_count: int = 0
    terminal_contract_reject_count: int = 0
    contract_evaluated_count: int | None = None
    contract_allowed_count: int | None = None
    contract_allowed_rate: float | None = None
    control_evaluated_count: int | None = None
    control_allowed_count: int | None = None
    control_allowed_rate: float | None = None
    mode_switched_count: int | None = None
    physical_intercept_count: int | None = None
    pair_physical_success_count: int | None = None
    pair_physical_success_rate: float | None = None
    target_intercept_success_count: int | None = None
    target_intercept_success_rate: float | None = None
    coalition_completion_count: int | None = None
    coalition_completion_rate: float | None = None
    detection_acquisition_timeout_count: int | None = None
    image_kf_predict_count: int | None = None
    blind_push_count: int | None = None
    visual_reacquisition_count: int | None = None
    terminal_visual_lost_after_coast_count: int | None = None
    truth_identity_online_use_count: int | None = None
    terminal_filter_measured_count: int | None = None
    terminal_filter_predicted_count: int | None = None
    terminal_filter_innovation_rejected_count: int | None = None
    terminal_filter_reset_count: int | None = None
    terminal_filter_expired_count: int | None = None
    ttc_area_jump_reject_count: int | None = None
    ttc_bbox_clipping_reject_count: int | None = None
    ttc_not_expanding_reject_count: int | None = None
    ttc_out_of_range_reject_count: int | None = None
    soft_prediction_count: int | None = None
    soft_prediction_duration_s: float | None = None
    soft_prediction_expired_count: int | None = None
    terminal_coast_count: int | None = None
    terminal_coast_duration_s: float | None = None
    terminal_coast_expired_count: int | None = None
    terminal_lock_continuity: float | None = None
    visual_mode_duration_s: float | None = None
    command_discontinuity_mean_mps: float | None = None
    command_discontinuity_max_mps: float | None = None
    intercept_success_count: int = 0
    collision_intercept_count: int = 0
    range_intercept_count: int = 0
    time_to_intercept_s: float = 0.0
    min_range_m: float = 0.0
    gate_reject_count: int = 0
    constraint_violation_count: int = 0
    human_override_count: int = 0
    module_duration_ms: float = 0.0
    loop_latency_ms: float = 0.0
    record_latency_ms: float = 0.0
    cpu_budget_utilization: float = 0.0
    gpu_budget_utilization: float = 0.0
    performance_budget_violation_count: int = 0
    metric_availability: dict[str, dict[str, Any]] = field(default_factory=dict)
    m_to_n_metric_availability: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def metric_names(cls) -> list[str]:
        return [
            "detection_probability",
            "false_alarm_rate",
            "missed_detection_rate",
            "track_rmse",
            "track_continuity",
            "id_switch_count",
            "duplicate_assignment_count",
            "unassigned_high_threat_count",
            *M_TO_N_METRIC_NAMES,
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
            "terminal_association_accuracy",
            "terminal_id_switch_count",
            "ambiguous_fov_event_count",
            "friend_overlap_hold_count",
            "time_to_terminal_lock",
            "terminal_lock_count",
            "multi_view_consensus_rate",
            "cross_view_conflict_count",
            "duplicate_terminal_lock_count",
            "visual_detection_recall",
            "local_id_continuity",
            "cross_view_registration_rate",
            "visual_pipeline_latency_ms",
            "visual_cpu_budget_utilization",
            "visual_gpu_budget_utilization",
            "visual_budget_violation_count",
            "online_truth_field_violation_count",
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
            "cross_node_latency_ms",
            "message_drop_rate",
            "out_of_order_count",
            "stale_track_update_count",
            "video_metadata_delivery_rate",
            "bbox_delivery_rate",
            "consensus_latency_s",
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
            *_TERMINAL_DELIVERY_METRIC_NAMES,
            "intercept_success_count",
            "collision_intercept_count",
            "range_intercept_count",
            "time_to_intercept_s",
            "min_range_m",
            "gate_reject_count",
            "constraint_violation_count",
            "human_override_count",
            "module_duration_ms",
            "loop_latency_ms",
            "record_latency_ms",
            "cpu_budget_utilization",
            "gpu_budget_utilization",
            "performance_budget_violation_count",
        ]

    @classmethod
    def scale_names(cls) -> list[str]:
        return [
            "drone_count",
            "resource_count",
            "target_count",
            "camera_count",
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def numeric_metric_dict(self) -> dict[str, float | None]:
        return {
            name: None if getattr(self, name) is None else float(getattr(self, name))
            for name in self.metric_names()
        }


class MetricsCollector:
    """Collect records and compute one offline episode's metrics."""

    CENTRAL_FAILURE_EVENTS = {"central_failure", "coordinator_failure"}
    DEGRADED_STABLE_EVENTS = {"degraded_stable", "failover_stable"}
    ACTIVE_DEGRADATION_EVENTS = {
        "active_degradation",
        "active_degradation_decision",
        "d4_active_degradation",
        "d4_active_degradation_decision",
    }
    PASSIVE_FAILOVER_EVENTS = {
        "passive_failover",
        "passive_failover_complete",
        "passive_failover_stable",
        "d4_passive_failover",
    }
    SECONDARY_NODE_TAKEOVER_EVENTS = {
        "secondary_node_takeover",
        "secondary_takeover",
        "secondary_takeover_complete",
        "d4_secondary_node_takeover",
    }
    SECONDARY_REASSIGNMENT_EVENTS = {
        "secondary_reassignment",
        "secondary_node_reassignment",
        "d4_secondary_reassignment",
        "d4_reassign_to_secondary",
        "degrade_to_secondary",
    }
    D4_REASSIGN_PENDING_EVENTS = {
        "d4_reassign_pending",
        "reassign_pending",
        "assignment_reassign_pending",
        "terminal_reassign_pending",
    }
    D1_GOVERNANCE_EVENTS = {
        "d1_governance_summary",
        "d1_latency_audit",
        "d1_region_quality_summary",
        "d1_region_quality_window",
    }
    D2_GOVERNANCE_EVENTS = {
        "d2_governance_summary",
        "d2_association_risk_summary",
        "d2_consistency_summary",
        "d2_false_track_summary",
    }
    D3_GOVERNANCE_EVENTS = {
        "d3_governance_summary",
        "d3_assignment_mismatch_summary",
        "d3_feedback_profile_summary",
    }
    OFFLINE_DETECTION_MATCH_EVENTS = {
        "offline_detection_match",
        "offline_track_truth_match",
    }
    OFFLINE_DETECTION_MISS_EVENTS = {
        "offline_detection_miss",
        "offline_missed_detection",
    }
    SECONDARY_LIFECYCLE_EVENTS = {
        "d4_secondary_readiness",
        "secondary_readiness",
        "secondary_takeover_readiness",
        "d4_secondary_plan_state",
        "secondary_plan_state",
        "secondary_takeover_state",
        "secondary_takeover_fallback",
        "secondary_lease_expired",
        "secondary_plan_lease_expired",
        "stale_plan_reject",
        "secondary_stale_plan_reject",
    }
    DISTRIBUTED_FALLBACK_EVENTS = {
        "distributed_fallback",
        "distributed_fallback_active",
        "distributed_fallback_complete",
        "d4_distributed_fallback",
    }
    CONSTRAINT_VIOLATION_EVENTS = {
        "constraint_violation",
        "safety_constraint_violation",
    }
    HUMAN_OVERRIDE_EVENTS = {
        "human_override",
        "human_reject",
        "human_rejection",
        "operator_override",
    }
    AMBIGUOUS_FOV_EVENTS = {"ambiguous_fov", "terminal_ambiguous_fov"}
    FRIEND_HOLD_EVENTS = {"friend_overlap_hold", "friend_conflict_hold"}
    MESSAGE_DROP_EVENTS = {
        "message_drop",
        "link_drop",
        "packet_drop",
        "communication_drop",
    }
    OUT_OF_ORDER_EVENTS = {
        "out_of_order_message",
        "message_out_of_order",
        "link_out_of_order",
    }
    STALE_TRACK_EVENTS = {"stale_track_update", "stale_track_summary"}
    MULTI_VIEW_CONSENSUS_EVENTS = {
        "multi_view_consensus",
        "multi_view_consensus_result",
        "cross_view_consensus",
    }
    MULTI_VIEW_CONSENSUS_FAILURE_EVENTS = {
        "multi_view_consensus_failed",
        "cross_view_consensus_failed",
    }
    CROSS_VIEW_CONFLICT_EVENTS = {
        "cross_view_conflict",
        "multi_view_conflict",
        "terminal_cross_view_conflict",
    }
    CROSS_VIEW_ASSOCIATION_EVENTS = {
        "cross_view_association",
        "cross_view_association_result",
        "d5_cross_view_association",
        "d5_cross_view_association_result",
        "secondary_cross_view_association",
    }
    SECONDARY_DETECT_NOT_REGISTERED_EVENTS = {
        "secondary_detect_available_but_not_registered",
        "detect_available_but_not_registered",
        "d5_secondary_detect_available_but_not_registered",
        "secondary_detection_not_registered",
        "d5_registration_miss",
    }
    SECONDARY_SENSING_EVENTS = {
        "secondary_coverage_frame",
        "secondary_sensing_frame",
        "secondary_view_frame",
        "secondary_network_frame",
        "d4_secondary_coverage",
        "d5_secondary_view",
        "d5_secondary_view_frame",
        "fixed_downlook_secondary_frame",
        "mobile_recon_gimbal_frame",
        "cue_pointing_sample",
        "gimbal_pointing_sample",
    }
    DUPLICATE_TERMINAL_LOCK_EVENTS = {
        "duplicate_terminal_lock",
        "terminal_duplicate_lock",
    }
    TERMINAL_SWITCH_REJECT_EVENTS = {
        "terminal_switch_reject",
        "terminal_switch_rejected",
        "d7_terminal_switch_reject",
    }
    INTERCEPT_SUCCESS_STATUSES = {"collision_intercept", "range_intercept"}
    INTERCEPT_PAIR_SUMMARY_EVENTS = {
        "d7_intercept_pair_summary",
        "intercept_pair_summary",
    }
    INTERCEPT_SUMMARY_EVENTS = {"d7_intercept_summary", "intercept_summary"}
    D7_CONTROL_COMMAND_EVENTS = {"d7_control_command", "control_command"}
    D7_GUIDANCE_RECORD_EVENTS = {"d7_guidance_record", "guidance_record"}
    D7_GUIDANCE_SUMMARY_EVENTS = {"d7_guidance_summary", "guidance_summary"}
    D7_GUIDANCE_PAIR_SUMMARY_EVENTS = {
        "d7_guidance_pair_summary",
        "guidance_pair_summary",
    }
    D5_PERCEPTION_EVENTS = {
        "d5_perception_frame",
        "d5_visual_tracking_frame",
        "d5_yolo_mot_frame",
        "terminal_perception_frame",
    }
    FOV_ENTRY_STATES = {"fov_entry", "entered_fov", "terminal_fov_entry"}
    LOCK_STATES = {"locked", "lock", "terminal_lock"}
    ASSOCIATION_STATES = {"associated", "locked", "lock", "terminal_lock"}
    ABORT_EVENTS = {
        "mission_aborted",
        "episode_aborted",
        "run_aborted",
        "operator_abort",
        "runtime_abort",
    }
    RUNTIME_EXCEPTION_EVENTS = {
        "runtime_exception",
        "exception",
        "unhandled_exception",
        "module_exception",
        "airsim_exception",
    }
    MISSION_SUCCESS_EVENTS = {
        "mission_success",
        "episode_success",
        "mission_completed",
        "episode_completed",
    }
    MISSION_FAILED_EVENTS = {
        "mission_failed",
        "episode_failed",
        "mission_failure",
        "episode_failure",
    }
    EFFECTIVE_ASSIGNMENT_AUTH_STATES = {
        "recorded",
        "authorized",
        "approved",
        "human_approved",
        "operator_approved",
    }

    def __init__(self, ambiguous_fov_threshold: float = 0.6) -> None:
        self.ambiguous_fov_threshold = ambiguous_fov_threshold
        self.track_records: list[TrackRecord] = []
        self.assignment_records: list[AssignmentRecord] = []
        self.target_demand_records: list[TargetDemandRecord] = []
        self.coalition_records: list[CoalitionRecord] = []
        self.arrival_records: list[ArrivalRecord] = []
        self.event_records: list[EventRecord] = []
        self.link_records: list[LinkRecord] = []
        self.terminal_records: list[TerminalRecord] = []

    def add_track(self, record: TrackRecord) -> None:
        self.track_records.append(record)

    def add_assignment(self, record: AssignmentRecord) -> None:
        self.assignment_records.append(record)

    def add_target_demand(self, record: TargetDemandRecord) -> None:
        self.target_demand_records.append(record)

    def add_coalition(self, record: CoalitionRecord) -> None:
        self.coalition_records.append(record)

    def add_arrival(self, record: ArrivalRecord) -> None:
        self.arrival_records.append(record)

    def add_event(self, record: EventRecord) -> None:
        self.event_records.append(record)

    def add_link(self, record: LinkRecord) -> None:
        self.link_records.append(record)

    def add_terminal(self, record: TerminalRecord) -> None:
        self.terminal_records.append(record)

    def extend_tracks(self, records: Iterable[TrackRecord]) -> None:
        self.track_records.extend(records)

    def extend_assignments(self, records: Iterable[AssignmentRecord]) -> None:
        self.assignment_records.extend(records)

    def extend_target_demands(self, records: Iterable[TargetDemandRecord]) -> None:
        self.target_demand_records.extend(records)

    def extend_coalitions(self, records: Iterable[CoalitionRecord]) -> None:
        self.coalition_records.extend(records)

    def extend_arrivals(self, records: Iterable[ArrivalRecord]) -> None:
        self.arrival_records.extend(records)

    def extend_events(self, records: Iterable[EventRecord]) -> None:
        self.event_records.extend(records)

    def extend_links(self, records: Iterable[LinkRecord]) -> None:
        self.link_records.extend(records)

    def extend_terminals(self, records: Iterable[TerminalRecord]) -> None:
        self.terminal_records.extend(records)

    def compute_episode(
        self,
        episode_id: str,
        seed: int | None = None,
        duration: float | None = None,
        truth_summary: Mapping[str, Any] | None = None,
        scenario_group: str | None = None,
        batch_seed: int | None = None,
        metric_scope: str | None = None,
    ) -> EpisodeMetrics:
        truth_summary = truth_summary or {}
        resolved_scenario_group = scenario_group or _scenario_group_from_truth_summary(
            truth_summary
        )
        resolved_metric_scope = metric_scope or _metric_scope_from_truth_summary(
            truth_summary
        )
        resolved_batch_seed = batch_seed
        if resolved_batch_seed is None:
            resolved_batch_seed = _batch_seed_from_truth_summary(truth_summary)
        if resolved_batch_seed is None:
            resolved_batch_seed = seed
        scale_counts = self._episode_scale_counts(truth_summary)
        scenario_version = _scenario_version_from_sources(
            truth_summary,
            self.event_records,
        )
        standard_mapping_version = _standard_mapping_version_from_sources(
            truth_summary,
            self.event_records,
        )
        episode_duration = (
            float(duration)
            if duration is not None
            else self._infer_duration_from_records()
        )
        metrics = EpisodeMetrics(
            episode_id=episode_id,
            seed=seed,
            scenario_group=resolved_scenario_group,
            batch_seed=resolved_batch_seed,
            metric_scope=resolved_metric_scope,
            **scale_counts,
            duration=episode_duration,
            scenario_version=scenario_version,
            standard_mapping_version=standard_mapping_version,
            standard_metric_family_summary=_standard_metric_family_summary(),
        )

        detection = self._compute_detection_metrics(
            duration=episode_duration,
            truth_summary=truth_summary,
        )
        detection_metadata = detection.pop("_metadata", {})
        tracking = self._compute_tracking_metrics(truth_summary)
        assignment = self._compute_assignment_metrics(truth_summary)
        m_to_n, m_to_n_metadata = compute_m_to_n_metrics(
            demand_records=self.target_demand_records,
            coalition_records=self.coalition_records,
            arrival_records=self.arrival_records,
            assignment_records=self.assignment_records,
            terminal_records=self.terminal_records,
            event_records=self.event_records,
            link_records=self.link_records,
        )
        governance = self._compute_d1_d3_governance_metrics()
        governance_metadata = governance.pop("_metadata", {})
        degradation = self._compute_degradation_metrics()
        degradation_metadata = degradation.pop("_metadata", {})
        secondary_lifecycle = self._compute_secondary_lifecycle_metrics(
            episode_duration
        )
        secondary_lifecycle_metadata = secondary_lifecycle.pop("_metadata", {})
        terminal = self._compute_terminal_metrics()
        visual_perception = self._compute_visual_perception_metrics()
        visual_perception_metadata = visual_perception.pop("_metadata", {})
        secondary_sensing = self._compute_secondary_sensing_metrics(scale_counts)
        secondary_sensing_metadata = secondary_sensing.pop("_metadata", {})
        link = self._compute_link_metrics()
        guidance_gate = self._compute_guidance_gate_metrics()
        guidance_metadata = guidance_gate.pop("_metadata", {})
        terminal_delivery = self._compute_terminal_delivery_metrics()
        terminal_delivery_metadata = terminal_delivery.pop("_metadata", {})
        intercept = self._compute_intercept_metrics()
        intercept_metadata = intercept.pop("_metadata", {})
        safety = self._compute_safety_metrics()
        performance = self._compute_performance_metrics(truth_summary)
        performance_metadata = performance.pop("_metadata", {})

        for metric_group in (
            detection,
            tracking,
            assignment,
            m_to_n,
            governance,
            degradation,
            secondary_lifecycle,
            terminal,
            visual_perception,
            secondary_sensing,
            link,
            guidance_gate,
            terminal_delivery,
            intercept,
            safety,
            performance,
        ):
            for key, value in metric_group.items():
                setattr(metrics, key, value)

        metrics.m_to_n_metric_availability = dict(
            m_to_n_metadata["m_to_n_metric_availability"]
        )
        metrics.metric_availability = {
            **dict(detection_metadata.get("metric_availability", {})),
            **metrics.m_to_n_metric_availability,
            **dict(terminal_delivery_metadata.get("metric_availability", {})),
        }
        metrics.duplicate_assignment_count = int(
            m_to_n_metadata["m_to_n_duplicate_assignment_count"]
        )

        mission_status = self._compute_mission_status(metrics, truth_summary)
        mission_metadata = mission_status.pop("_metadata", {})
        for key, value in mission_status.items():
            setattr(metrics, key, value)

        eval_tracking = self._compute_eval_tracking(truth_summary)
        eval_metadata = eval_tracking.pop("_metadata", {})
        for key, value in eval_tracking.items():
            setattr(metrics, key, value)

        metrics.metadata = {
            "track_record_count": len(self.track_records),
            "assignment_record_count": len(self.assignment_records),
            "target_demand_record_count": len(self.target_demand_records),
            "coalition_record_count": len(self.coalition_records),
            "arrival_record_count": len(self.arrival_records),
            "event_record_count": len(self.event_records),
            "link_record_count": len(self.link_records),
            "terminal_record_count": len(self.terminal_records),
            "offline_only": True,
            "scenario_group": resolved_scenario_group,
            "batch_seed": resolved_batch_seed,
            "metric_scope": resolved_metric_scope,
            "mission_outcome": metrics.mission_outcome,
            "success_reason": metrics.success_reason,
            "failure_reason": metrics.failure_reason,
            "eval_priority": metrics.eval_priority,
            "implementation_status": metrics.implementation_status,
            "evidence_path": metrics.evidence_path,
            "scenario_version": metrics.scenario_version,
            "standard_mapping_version": metrics.standard_mapping_version,
            "standard_metric_families": standard_metric_families(),
            "standard_metric_family_summary": metrics.standard_metric_family_summary,
            "standard_mapping": standard_mapping_summary(),
            **scale_counts,
            **detection_metadata,
            **m_to_n_metadata,
            **governance_metadata,
            **degradation_metadata,
            **secondary_lifecycle_metadata,
            **secondary_sensing_metadata,
            **visual_perception_metadata,
            **guidance_metadata,
            **terminal_delivery_metadata,
            **intercept_metadata,
            **performance_metadata,
            **mission_metadata,
            **eval_metadata,
        }
        return metrics

    def to_record_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "tracks": [asdict(record) for record in self.track_records],
            "assignments": [asdict(record) for record in self.assignment_records],
            "target_demands": [asdict(record) for record in self.target_demand_records],
            "coalitions": [asdict(record) for record in self.coalition_records],
            "arrivals": [asdict(record) for record in self.arrival_records],
            "events": [asdict(record) for record in self.event_records],
            "links": [asdict(record) for record in self.link_records],
            "terminals": [asdict(record) for record in self.terminal_records],
        }

    def _infer_duration_from_records(self) -> float:
        timestamps: list[float] = []
        timestamps.extend(record.timestamp for record in self.track_records)
        timestamps.extend(record.timestamp for record in self.assignment_records)
        timestamps.extend(record.timestamp for record in self.target_demand_records)
        timestamps.extend(record.timestamp for record in self.coalition_records)
        timestamps.extend(record.timestamp for record in self.arrival_records)
        timestamps.extend(record.timestamp for record in self.event_records)
        timestamps.extend(record.timestamp for record in self.link_records)
        timestamps.extend(record.timestamp for record in self.terminal_records)
        if not timestamps:
            return 0.0
        low = min(timestamps)
        high = max(timestamps)
        if high == low:
            return high if high > 0 else 0.0
        return high - low

    def _episode_scale_counts(self, truth_summary: Mapping[str, Any]) -> dict[str, int]:
        target_count = _target_count_from_truth_summary(truth_summary)
        resource_count = _resource_count_from_truth_summary(truth_summary)
        camera_count = _camera_count_from_truth_summary(truth_summary)
        drone_count = _drone_count_from_truth_summary(truth_summary)

        if target_count is None:
            target_count = self._infer_target_count_from_records()
        if resource_count is None:
            resource_count = self._infer_resource_count_from_records()
        if camera_count is None:
            camera_count = self._infer_camera_count_from_records()
        if drone_count is None:
            drone_count = resource_count

        return {
            "drone_count": int(drone_count or 0),
            "resource_count": int(resource_count or 0),
            "target_count": int(target_count or 0),
            "camera_count": int(camera_count or 0),
        }

    def _infer_target_count_from_records(self) -> int:
        target_ids: set[str] = set()
        for record in self.track_records:
            if record.truth_id is not None:
                target_ids.add(str(record.truth_id))
        for record in self.assignment_records:
            target_key = _assignment_target_key(record)
            if target_key is not None:
                target_ids.add(target_key)
        target_ids.update(str(record.global_track_id) for record in self.target_demand_records)
        target_ids.update(str(record.global_track_id) for record in self.coalition_records)
        target_ids.update(str(record.global_track_id) for record in self.arrival_records)
        for record in self.terminal_records:
            if record.assigned_global_track_id is not None:
                target_ids.add(str(record.assigned_global_track_id))
            if record.expected_global_track_id is not None:
                target_ids.add(str(record.expected_global_track_id))
        for record in self.event_records:
            target_id = (
                _metadata_text(record.metadata, "target_id")
                or _metadata_text(record.metadata, "truth_id")
                or _metadata_text(record.metadata, "global_track_id")
                or _metadata_text(record.metadata, "assigned_global_track_id")
            )
            if target_id is not None:
                target_ids.add(target_id)
        return len(target_ids)

    def _infer_resource_count_from_records(self) -> int:
        resource_ids: set[str] = set()
        for record in self.assignment_records:
            resource_ids.add(str(record.resource_id))
        for record in self.coalition_records:
            resource_ids.update(str(resource_id) for resource_id in record.member_ids)
        for record in self.arrival_records:
            resource_ids.add(str(record.resource_id))
        for record in self.terminal_records:
            resource_ids.add(str(record.resource_id))
        for record in self.event_records:
            resource_id = (
                _metadata_text(record.metadata, "resource_id")
                or _metadata_text(record.metadata, "vehicle_name")
                or record.actor_id
            )
            if resource_id is not None:
                resource_ids.add(str(resource_id))
        return len(resource_ids)

    def _infer_camera_count_from_records(self) -> int:
        camera_ids: set[str] = set()
        for record in self.link_records:
            _add_camera_id_from_metadata(camera_ids, record.metadata)
        for record in self.event_records:
            _add_camera_id_from_metadata(camera_ids, record.metadata)
        return len(camera_ids)

    def _compute_detection_metrics(
        self,
        duration: float,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        truth_timestamps = _truth_timestamps_by_id(truth_summary)
        metric_names = (
            "detection_probability",
            "false_alarm_rate",
            "missed_detection_rate",
        )
        if not truth_timestamps:
            availability = {
                name: {
                    "status": "unavailable",
                    "reason": "offline truth (truth_id, timestamp) mapping is absent",
                    "numerator": None,
                    "denominator": None,
                }
                for name in metric_names
            }
            return {
                **{name: None for name in metric_names},
                "_metadata": {"metric_availability": availability},
            }

        truth_pairs = {
            (truth_id, timestamp)
            for truth_id, timestamps in truth_timestamps.items()
            for timestamp in timestamps
        }
        detected_pairs = {
            (str(record.truth_id), float(record.timestamp))
            for record in self.track_records
            if record.truth_id is not None
        }
        explicit_matched_pairs, explicit_missed_pairs = (
            self._offline_detection_adjudication_pairs(truth_pairs)
        )
        track_matched_pairs = detected_pairs & truth_pairs
        if not track_matched_pairs and not explicit_matched_pairs and not explicit_missed_pairs:
            availability = {
                name: {
                    "status": "unavailable",
                    "reason": "truth opportunities exist, but offline detection/track-to-truth match or miss evidence is absent",
                    "numerator": None,
                    "denominator": None,
                }
                for name in metric_names
            }
            return {
                **{name: None for name in metric_names},
                "_metadata": {
                    "metric_availability": availability,
                    "offline_detection_pair_evidence": {
                        "track_match_count": 0,
                        "explicit_match_count": 0,
                        "explicit_miss_count": 0,
                    },
                },
            }

        detected_pairs |= explicit_matched_pairs
        true_positive_count = len(detected_pairs & truth_pairs)
        false_positive_count = len(detected_pairs - truth_pairs)
        missed_count = len(truth_pairs - detected_pairs)
        denominator = len(truth_pairs)

        detection_probability = true_positive_count / denominator
        missed_detection_rate = missed_count / denominator
        false_alarm_rate = false_positive_count / duration if duration > 0 else None

        availability = {
            "detection_probability": {
                "status": "available",
                "reason": "offline match/miss adjudication was recorded by (truth_id, timestamp)",
                "numerator": true_positive_count,
                "denominator": denominator,
            },
            "missed_detection_rate": {
                "status": "available",
                "reason": "offline match/miss adjudication was recorded by (truth_id, timestamp)",
                "numerator": missed_count,
                "denominator": denominator,
            },
            "false_alarm_rate": {
                "status": "available" if duration > 0 else "unavailable",
                "reason": (
                    "truth-labeled detections outside the offline truth-pair set were counted; truthless center tracks were excluded"
                    if duration > 0
                    else "episode duration is zero, so a false-alarm rate cannot be formed"
                ),
                "numerator": false_positive_count,
                "denominator": duration if duration > 0 else None,
            },
        }

        return {
            "detection_probability": detection_probability,
            "false_alarm_rate": false_alarm_rate,
            "missed_detection_rate": missed_detection_rate,
            "_metadata": {
                "metric_availability": availability,
                "offline_detection_pair_evidence": {
                    "track_match_count": len(track_matched_pairs),
                    "explicit_match_count": len(explicit_matched_pairs),
                    "explicit_miss_count": len(explicit_missed_pairs),
                },
            },
        }

    def _offline_detection_adjudication_pairs(
        self,
        truth_pairs: set[tuple[str, float]],
    ) -> tuple[set[tuple[str, float]], set[tuple[str, float]]]:
        matched: set[tuple[str, float]] = set()
        missed: set[tuple[str, float]] = set()
        for record in self.event_records:
            event_type = _event_type(record)
            if (
                event_type not in self.OFFLINE_DETECTION_MATCH_EVENTS
                and event_type not in self.OFFLINE_DETECTION_MISS_EVENTS
            ):
                continue
            offline_truth = record.metadata.get("offline_truth")
            metadata = offline_truth if isinstance(offline_truth, Mapping) else record.metadata
            truth_id = _metadata_text(metadata, "truth_id")
            timestamp = _first_metadata_float(
                metadata,
                ("truth_timestamp", "measurement_timestamp", "timestamp"),
            )
            if timestamp is None:
                timestamp = float(record.timestamp)
            pair = None if truth_id is None else (truth_id, timestamp)
            if pair is None or pair not in truth_pairs:
                continue
            if event_type in self.OFFLINE_DETECTION_MATCH_EVENTS:
                matched.add(pair)
            else:
                missed.add(pair)
        return matched, missed

    def _compute_tracking_metrics(
        self,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, float | int]:
        truth_timestamps = _truth_timestamps_by_id(truth_summary)
        squared_errors: list[float] = []
        for record in self.track_records:
            if record.truth_id is None:
                continue
            distance = _euclidean_distance(record.position, record.truth_position)
            if distance is not None:
                squared_errors.append(distance * distance)
        track_rmse = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else 0.0

        detected_pairs = {
            (record.truth_id, record.timestamp)
            for record in self.track_records
            if record.truth_id is not None
        }
        if truth_timestamps:
            truth_pairs = {
                (truth_id, timestamp)
                for truth_id, timestamps in truth_timestamps.items()
                for timestamp in timestamps
            }
            matched_count = len(detected_pairs & truth_pairs)
            total_truth_count = len(truth_pairs)
            track_continuity = matched_count / total_truth_count if total_truth_count else 0.0
        else:
            track_continuity = 1.0 if detected_pairs else 0.0

        id_switch_count = self._count_track_id_switches()

        return {
            "track_rmse": track_rmse,
            "track_continuity": track_continuity,
            "id_switch_count": id_switch_count,
        }

    def _count_track_id_switches(self) -> int:
        by_truth: dict[str, dict[float, str]] = defaultdict(dict)
        for record in self.track_records:
            if record.truth_id is None or record.global_track_id is None:
                continue
            by_truth[record.truth_id].setdefault(record.timestamp, record.global_track_id)

        switch_count = 0
        for timestamp_to_track in by_truth.values():
            previous_track_id: str | None = None
            for timestamp in sorted(timestamp_to_track):
                track_id = timestamp_to_track[timestamp]
                if previous_track_id is not None and track_id != previous_track_id:
                    switch_count += 1
                previous_track_id = track_id
        return switch_count

    def _compute_assignment_metrics(
        self,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, int]:
        active_records = [
            record
            for record in self.assignment_records
            if record.active and _state(record.authorization_state) in self.EFFECTIVE_ASSIGNMENT_AUTH_STATES
        ]
        snapshots: dict[tuple[float, str, int], list[AssignmentRecord]] = defaultdict(list)
        for record in active_records:
            snapshots[(record.timestamp, record.plan_id, record.version)].append(record)

        duplicate_assignment_count = 0
        for records in snapshots.values():
            target_to_resources: dict[str, set[str]] = defaultdict(set)
            for record in records:
                target_key = _assignment_target_key(record)
                if target_key is not None:
                    target_to_resources[target_key].add(record.resource_id)
            duplicate_assignment_count += sum(
                1 for resources in target_to_resources.values() if len(resources) > 1
            )

        high_threat_by_timestamp = _high_threat_by_timestamp(truth_summary)
        assignment_times = sorted({record.timestamp for record in active_records})

        if not high_threat_by_timestamp:
            high_threat_ids = _high_threat_ids(truth_summary)
            truth_timestamps = _truth_timestamps_by_id(truth_summary)
            evaluation_times = sorted(
                {
                    timestamp
                    for truth_id in high_threat_ids
                    for timestamp in truth_timestamps.get(truth_id, set())
                }
            )
            if not evaluation_times:
                evaluation_times = assignment_times or [0.0]
            high_threat_by_timestamp = {timestamp: set(high_threat_ids) for timestamp in evaluation_times}

        records_by_time: dict[float, list[AssignmentRecord]] = defaultdict(list)
        for record in active_records:
            records_by_time[record.timestamp].append(record)

        unassigned_high_threat_count = 0
        for timestamp, high_threat_ids in high_threat_by_timestamp.items():
            assigned_targets = {
                target
                for record in records_by_time.get(timestamp, [])
                for target in [_assignment_target_key(record)]
                if target is not None
            }
            unassigned_high_threat_count += sum(
                1 for target in high_threat_ids if target not in assigned_targets
            )

        return {
            "duplicate_assignment_count": duplicate_assignment_count,
            "unassigned_high_threat_count": unassigned_high_threat_count,
        }

    def _compute_d1_d3_governance_metrics(self) -> dict[str, Any]:
        module_events = {
            "d1": [
                record
                for record in self.event_records
                if _event_type(record) in self.D1_GOVERNANCE_EVENTS
            ],
            "d2": [
                record
                for record in self.event_records
                if _event_type(record) in self.D2_GOVERNANCE_EVENTS
            ],
            "d3": [
                record
                for record in self.event_records
                if _event_type(record) in self.D3_GOVERNANCE_EVENTS
            ],
        }
        all_events = [record for records in module_events.values() for record in records]
        if not all_events:
            return {
                **{name: None for name in _D1_D3_GOVERNANCE_METRIC_NAMES},
                "_metadata": {
                    "d1_d3_governance_status": "unavailable",
                    "d1_d3_governance_event_count": 0,
                },
            }

        payloads_by_module = {
            module: [_governance_payload(record.metadata) for record in records]
            for module, records in module_events.items()
        }
        schema_count = 0
        config_count = 0
        schema_mismatch_count = 0
        provenance_by_module: dict[str, dict[str, Any]] = {}
        for module, payloads in payloads_by_module.items():
            schema_versions: set[str] = set()
            config_profiles: set[str] = set()
            config_versions: set[str] = set()
            config_hashes: set[str] = set()
            source_commits: set[str] = set()
            for payload in payloads:
                schema_version = _metadata_text(payload, "schema_version")
                if schema_version is not None:
                    schema_count += 1
                    schema_versions.add(schema_version)
                config_profile = _metadata_text(payload, "config_profile") or _metadata_text(
                    payload, "profile_name"
                )
                config_version = _metadata_text(payload, "config_version") or _metadata_text(
                    payload, "profile_version"
                )
                config_hash = _metadata_text(payload, "config_hash")
                if any(value is not None for value in (config_profile, config_version, config_hash)):
                    config_count += 1
                if config_profile is not None:
                    config_profiles.add(config_profile)
                if config_version is not None:
                    config_versions.add(config_version)
                if config_hash is not None:
                    config_hashes.add(config_hash)
                source_commit = _metadata_text(payload, "source_commit")
                if source_commit is not None:
                    source_commits.add(source_commit)
                schema_mismatch = _bool_from_metadata(
                    payload,
                    ("schema_mismatch", "schema_rejected"),
                    default=False,
                )
                if "schema_valid" in payload:
                    schema_mismatch = schema_mismatch or not _as_bool(
                        payload["schema_valid"], default=False
                    )
                schema_mismatch_count += int(schema_mismatch)
            provenance_by_module[module] = {
                "event_count": len(payloads),
                "schema_versions": sorted(schema_versions),
                "config_profiles": sorted(config_profiles),
                "config_versions": sorted(config_versions),
                "config_hashes": sorted(config_hashes),
                "source_commits": sorted(source_commits),
            }

        d1_payloads = payloads_by_module["d1"]
        d1_region_payloads = [
            payload
            for record, payload in zip(module_events["d1"], d1_payloads)
            if _event_type(record)
            in {"d1_region_quality_summary", "d1_region_quality_window"}
            or "coverage_cell" in payload
        ]
        d1_observation_count = _governance_sum(
            d1_payloads,
            ("observation_count", "latency_observation_count"),
        )
        d1_oosm_count = _governance_sum(
            d1_payloads,
            ("oosm_observation_count", "oosm_count"),
        )
        d1_stale_count = _governance_sum(
            d1_payloads,
            ("stale_observation_count", "stale_count"),
        )
        d1_replay_count = _governance_sum(
            d1_payloads,
            ("replay_count",),
        )
        coverage_cells = {
            value
            for payload in d1_region_payloads
            for value in [_metadata_text(payload, "coverage_cell")]
            if value is not None
        }
        expected_region_count = _governance_max(
            d1_region_payloads,
            ("expected_coverage_cell_count", "expected_region_count"),
        )
        degraded_region_count = (
            sum(
                int(
                    _bool_from_metadata(
                        payload,
                        ("region_quality_degraded", "quality_degraded"),
                        default=False,
                    )
                    or bool(payload.get("quality_flags"))
                )
                for payload in d1_region_payloads
            )
            if d1_region_payloads
            else None
        )

        d2_payloads = payloads_by_module["d2"]
        d2_false_track_count = _governance_sum(
            d2_payloads,
            ("false_track_count",),
        )
        d2_track_birth_count = _governance_sum(
            d2_payloads,
            ("initiated_track_count", "track_birth_count"),
        )

        d3_payloads = payloads_by_module["d3"]
        d3_resource_target_ratios = [
            float(resource_count) / float(target_count)
            for payload in d3_payloads
            for resource_count, target_count in [
                (
                    _governance_value(payload, ("resource_count",)),
                    _governance_value(payload, ("target_count",)),
                )
            ]
            if resource_count is not None and target_count is not None and target_count > 0
        ]
        d3_target_count = _governance_sum(d3_payloads, ("target_count",))
        d3_assigned_count = _governance_sum(d3_payloads, ("assigned_count",))
        d3_unassigned_count = _governance_sum(
            d3_payloads,
            ("unassigned_target_count", "unassigned_count"),
        )
        if d3_unassigned_count is None and d3_target_count is not None and d3_assigned_count is not None:
            d3_unassigned_count = max(0.0, d3_target_count - d3_assigned_count)
        d3_decision_count = _governance_sum(
            d3_payloads,
            ("decision_count", "assignment_decision_count"),
        )
        d3_feedback_count = _governance_sum(
            d3_payloads,
            ("feedback_record_count", "feedback_sample_count"),
        )
        d3_feedback_accepted = _governance_sum(
            d3_payloads,
            ("feedback_accepted_count", "accepted_feedback_count"),
        )
        d3_feedback_rejected = _governance_sum(
            d3_payloads,
            ("feedback_rejected_count",),
        )
        if d3_feedback_rejected is None:
            d3_feedback_rejected = _governance_sum(
                d3_payloads,
                (
                "duplicate_reject_count",
                "friend_reject_count",
                "fov_reject_count",
                "geometry_reject_count",
                ),
                sum_all_present_keys=True,
            )
        if (
            d3_feedback_accepted is None
            and d3_feedback_count is not None
            and d3_feedback_rejected is not None
        ):
            d3_feedback_accepted = max(0.0, d3_feedback_count - d3_feedback_rejected)

        result = {
            "governance_schema_provenance_rate": schema_count / len(all_events),
            "governance_config_provenance_rate": config_count / len(all_events),
            "governance_schema_mismatch_count": schema_mismatch_count,
            "d1_oosm_observation_rate": _ratio_or_none(
                d1_oosm_count, d1_observation_count
            ),
            "d1_stale_observation_rate": _ratio_or_none(
                d1_stale_count, d1_observation_count
            ),
            "d1_replay_observation_rate": _ratio_or_none(
                d1_replay_count, d1_observation_count
            ),
            "d1_mean_delay_s": _governance_weighted_mean(
                d1_payloads,
                ("mean_delay_s",),
                ("observation_count", "latency_observation_count"),
            ),
            "d1_max_delay_s": _governance_max(d1_payloads, ("max_delay_s",)),
            "d1_region_quality_coverage_rate": _ratio_or_none(
                float(len(coverage_cells)), expected_region_count
            ),
            "d1_region_mean_a95_m": _governance_weighted_mean(
                d1_region_payloads,
                ("mean_a95_m",),
                ("track_count", "latest_track_count", "sample_count"),
            ),
            "d1_region_handover_readiness_mean": _governance_weighted_mean(
                d1_region_payloads,
                ("mean_handover_readiness",),
                ("track_count", "latest_track_count", "sample_count"),
            ),
            "d1_degraded_region_count": degraded_region_count,
            "d2_soft_risk_frame_rate": _governance_rate(
                d2_payloads,
                ("soft_risk_frame_count",),
                ("frame_count",),
                ("soft_risk_frame_rate",),
            ),
            "d2_hard_risk_frame_rate": _governance_rate(
                d2_payloads,
                ("hard_risk_frame_count",),
                ("frame_count",),
                ("hard_risk_frame_rate",),
            ),
            "d2_max_association_risk": _governance_max(
                d2_payloads,
                (
                    "max_hard_risk_score",
                    "max_soft_risk_score",
                    "max_track_association_risk",
                ),
            ),
            "d2_nis_mean": _governance_weighted_mean(
                d2_payloads,
                ("nis_mean", "mean_nis"),
                ("nis_sample_count",),
            ),
            "d2_nis_in_confidence_rate": _governance_rate(
                d2_payloads,
                ("nis_in_confidence_count",),
                ("nis_sample_count",),
                ("nis_in_confidence_rate",),
            ),
            "d2_nees_mean": _governance_weighted_mean(
                d2_payloads,
                ("nees_mean", "mean_nees"),
                ("nees_sample_count",),
            ),
            "d2_nees_in_confidence_rate": _governance_rate(
                d2_payloads,
                ("nees_in_confidence_count",),
                ("nees_sample_count",),
                ("nees_in_confidence_rate",),
            ),
            "d2_false_track_count": (
                int(d2_false_track_count) if d2_false_track_count is not None else None
            ),
            "d2_false_track_rate": _ratio_or_none(
                d2_false_track_count, d2_track_birth_count
            ),
            "d3_resource_target_ratio": (
                _mean(d3_resource_target_ratios)
                if d3_resource_target_ratios
                else None
            ),
            "d3_assignment_coverage_rate": _ratio_or_none(
                d3_assigned_count, d3_target_count
            ),
            "d3_unassigned_target_rate": _ratio_or_none(
                d3_unassigned_count, d3_target_count
            ),
            "d3_hysteresis_reject_rate": _ratio_or_none(
                _governance_sum(d3_payloads, ("hysteresis_reject_count",)),
                d3_decision_count,
            ),
            "d3_stale_reject_rate": _ratio_or_none(
                _governance_sum(d3_payloads, ("stale_reject_count",)),
                d3_decision_count,
            ),
            "d3_feedback_accept_rate": _ratio_or_none(
                d3_feedback_accepted, d3_feedback_count
            ),
            "d3_feedback_sample_count": (
                int(d3_feedback_count) if d3_feedback_count is not None else None
            ),
            "_metadata": {
                "d1_d3_governance_status": "available",
                "d1_d3_governance_event_count": len(all_events),
                "d1_d3_governance_event_counts": {
                    module: len(records) for module, records in module_events.items()
                },
                "governance_provenance_by_module": provenance_by_module,
                "d1_coverage_cells": sorted(coverage_cells),
                "d2_risk_profiles": _governance_profile_summary(
                    d2_payloads,
                    profile_keys=("risk_profile", "profile_name"),
                    version_keys=(
                        "risk_profile_version",
                        "association_risk_threshold_version",
                        "profile_version",
                    ),
                ),
                "d3_feedback_profiles": _governance_profile_summary(
                    d3_payloads,
                    profile_keys=("feedback_profile", "profile_name"),
                    version_keys=("feedback_profile_version", "profile_version"),
                ),
                "d3_nm_case_counts": _d3_nm_case_counts(d3_payloads),
                "offline_only": True,
            },
        }
        return result

    def _compute_degradation_metrics(self) -> dict[str, Any]:
        sorted_events = sorted(self.event_records, key=lambda record: record.timestamp)
        pending_failures: deque[EventRecord] = deque()
        failover_times: list[float] = []
        failover_active_window_deltas: list[float] = []
        active_window_timestamps: deque[float] = deque()
        consensus_round_values: list[float] = []
        degraded_completed = 0
        degraded_failed = 0
        active_degradation_count = 0
        passive_failover_count = 0
        secondary_node_takeover_count = 0
        distributed_fallback_count = 0
        secondary_reassignment_count = 0
        d4_reassign_pending_count = 0
        trigger_reasons: dict[str, int] = defaultdict(int)
        active_degradation_necessary_count = 0
        unnecessary_active_degradation_count = 0
        active_degradation_reviewed_count = 0
        active_degradation_review_label_counts: dict[str, int] = defaultdict(int)

        for record in sorted_events:
            event_type = _event_type(record)
            classification = self._degradation_classification(record)
            active, passive, secondary, distributed = classification[:4]
            secondary_reassignment, d4_reassign_pending = classification[4:]
            if active:
                active_degradation_count += 1
                active_window_timestamps.append(record.timestamp)
                review_label = _active_degradation_review_label(record)
                review_class = _active_degradation_review_class(review_label)
                if review_label is not None:
                    active_degradation_review_label_counts[review_label] += 1
                if review_class is not None:
                    active_degradation_reviewed_count += 1
                    if review_class == "necessary":
                        active_degradation_necessary_count += 1
                    else:
                        unnecessary_active_degradation_count += 1
            if passive:
                passive_failover_count += 1
            if secondary:
                secondary_node_takeover_count += 1
            if distributed:
                distributed_fallback_count += 1
            if secondary_reassignment:
                secondary_reassignment_count += 1
            if d4_reassign_pending:
                d4_reassign_pending_count += 1

            trigger_reason = (
                _metadata_text(record.metadata, "trigger_reason")
                or _metadata_text(record.metadata, "reason")
                or _metadata_text(record.metadata, "failover_reason")
                or _metadata_text(record.metadata, "degradation_reason")
            )
            if trigger_reason is not None and (active or passive or secondary or distributed):
                trigger_reasons[trigger_reason] += 1

            explicit_delta = self._failover_active_window_delta_from_metadata(record)
            if explicit_delta is not None:
                failover_active_window_deltas.append(explicit_delta)

            if event_type in self.CENTRAL_FAILURE_EVENTS:
                pending_failures.append(record)
            elif event_type in self.DEGRADED_STABLE_EVENTS and pending_failures:
                failure = pending_failures.popleft()
                failover_times.append(max(0.0, record.timestamp - failure.timestamp))
            if (
                passive
                or secondary
                or distributed
                or event_type in self.DEGRADED_STABLE_EVENTS
            ) and explicit_delta is None:
                while active_window_timestamps and active_window_timestamps[0] > record.timestamp:
                    active_window_timestamps.popleft()
                prior_active = None
                for timestamp in active_window_timestamps:
                    if timestamp <= record.timestamp:
                        prior_active = timestamp
                    else:
                        break
                if prior_active is not None:
                    failover_active_window_deltas.append(record.timestamp - prior_active)
            elif event_type == "consensus_rounds":
                value = _event_numeric_value(record, "rounds")
                if value is not None:
                    consensus_round_values.append(value)
            elif event_type == "degraded_task_completed":
                degraded_completed += 1
            elif event_type in {"degraded_task_failed", "degraded_task_cancelled"}:
                degraded_failed += 1

        failover_time = _mean(failover_times)
        consensus_rounds = _mean(consensus_round_values)
        degraded_total = degraded_completed + degraded_failed
        degraded_completion_rate = (
            degraded_completed / degraded_total if degraded_total else 0.0
        )
        active_degradation_precision = (
            active_degradation_necessary_count / active_degradation_reviewed_count
            if active_degradation_reviewed_count
            else None
        )

        return {
            "failover_time": failover_time,
            "consensus_rounds": consensus_rounds,
            "degraded_completion_rate": degraded_completion_rate,
            "active_degradation_count": active_degradation_count,
            "active_degradation_precision": active_degradation_precision,
            "active_degradation_label_count": active_degradation_reviewed_count,
            "unnecessary_active_degradation_count": unnecessary_active_degradation_count,
            "passive_failover_count": passive_failover_count,
            "secondary_node_takeover_count": secondary_node_takeover_count,
            "secondary_reassignment_count": secondary_reassignment_count,
            "d4_reassign_pending_count": d4_reassign_pending_count,
            "distributed_fallback_count": distributed_fallback_count,
            "failover_active_window_delta_s": _mean(failover_active_window_deltas),
            "_metadata": {
                "trigger_reason_distribution": dict(trigger_reasons),
                "failover_active_window_deltas_s": failover_active_window_deltas,
                "active_degradation_reviewed_count": active_degradation_reviewed_count,
                "active_degradation_necessary_count": active_degradation_necessary_count,
                "active_degradation_review_label_counts": dict(
                    active_degradation_review_label_counts
                ),
            },
        }

    def _degradation_classification(
        self,
        record: EventRecord,
    ) -> tuple[bool, bool, bool, bool, bool, bool]:
        event_type = _event_type(record)
        metadata = record.metadata
        mode = _state(str(metadata.get("mode") or metadata.get("degradation_mode") or ""))
        action = _state(str(metadata.get("action") or ""))
        assignment_phase = _state(str(metadata.get("assignment_phase") or ""))
        reject_reason = _state(
            str(
                metadata.get("reject_reason")
                or metadata.get("terminal_switch_reject_reason")
                or metadata.get("terminal_contract_reject_reason")
                or ""
            )
        )
        fallback_type = _state(str(metadata.get("fallback_type") or ""))
        d4_state = _state(str(metadata.get("d4_state") or metadata.get("d4_mode") or ""))

        active = (
            event_type in self.ACTIVE_DEGRADATION_EVENTS
            or mode == "active_degradation"
            or d4_state == "active_degradation"
            or _bool_from_metadata(metadata, ("active_degradation",), default=False)
        )
        passive = (
            event_type in self.PASSIVE_FAILOVER_EVENTS
            or mode == "passive_failover"
            or fallback_type == "passive_failover"
            or _bool_from_metadata(metadata, ("passive_failover",), default=False)
        )
        secondary = (
            event_type in self.SECONDARY_NODE_TAKEOVER_EVENTS
            or action in {
                "secondary_node_takeover",
                "takeover_secondary",
                "request_secondary_assist",
                "degrade_to_secondary",
            }
            or fallback_type in {"secondary_node_takeover", "secondary_takeover"}
            or _bool_from_metadata(metadata, ("secondary_node_takeover",), default=False)
        )
        secondary_reassignment = (
            event_type in self.SECONDARY_REASSIGNMENT_EVENTS
            or mode == "secondary_reassignment"
            or action
            in {
                "secondary_reassignment",
                "reassign_to_secondary",
                "degrade_to_secondary",
                "request_secondary_assist",
                "takeover_secondary",
            }
            or assignment_phase == "secondary_reassignment"
            or fallback_type
            in {
                "secondary_reassignment",
                "secondary_node_reassignment",
                "degrade_to_secondary",
            }
            or _bool_from_metadata(
                metadata,
                ("secondary_reassignment", "reassign_to_secondary"),
                default=False,
            )
        )
        d4_reassign_pending = (
            event_type in self.D4_REASSIGN_PENDING_EVENTS
            or action in {"reassign", "request_center_replan"}
            or reject_reason == "d4_reassign_pending"
            or d4_state == "reassign_pending"
            or _bool_from_metadata(metadata, ("d4_reassign_pending",), default=False)
        )
        distributed = (
            event_type in self.DISTRIBUTED_FALLBACK_EVENTS
            or mode == "distributed_fallback"
            or fallback_type == "distributed_fallback"
            or _bool_from_metadata(metadata, ("distributed_fallback",), default=False)
        )
        return active, passive, secondary, distributed, secondary_reassignment, d4_reassign_pending

    def _compute_secondary_lifecycle_metrics(
        self,
        episode_duration: float,
    ) -> dict[str, Any]:
        lifecycle_events = [
            record
            for record in sorted(self.event_records, key=lambda item: item.timestamp)
            if _event_type(record) in self.SECONDARY_LIFECYCLE_EVENTS
            or _secondary_readiness_state(record.metadata) is not None
            or _secondary_plan_state(record.metadata) is not None
        ]
        if not lifecycle_events:
            return {
                "secondary_registration_usable_dwell_s": None,
                "secondary_takeover_ready_dwell_s": None,
                "secondary_plan_pending_dwell_s": None,
                "secondary_plan_active_dwell_s": None,
                "secondary_activation_latency_s": None,
                "secondary_takeover_fallback_count": None,
                "secondary_lease_expiry_count": None,
                "stale_plan_reject_count": None,
                "_metadata": {
                    "secondary_lifecycle_status": "unavailable",
                    "secondary_lifecycle_event_count": 0,
                },
            }

        readiness_samples: list[tuple[float, str]] = []
        plan_samples: list[tuple[float, str]] = []
        fallback_count = 0
        lease_expiry_count = 0
        stale_reject_count = 0
        previous_readiness: str | None = None
        previous_plan: str | None = None

        for record in lifecycle_events:
            event_type = _event_type(record)
            readiness_state = _secondary_readiness_state(record.metadata)
            plan_state = _secondary_plan_state(record.metadata)
            if readiness_state is not None:
                readiness_samples.append((record.timestamp, readiness_state))
                if previous_readiness == "takeover_ready" and readiness_state in {
                    "registration_usable",
                    "visible_only",
                    "not_ready",
                }:
                    fallback_count += 1
                previous_readiness = readiness_state
            if plan_state is not None:
                plan_samples.append((record.timestamp, plan_state))
                if previous_plan in {
                    "pending_secondary_plan",
                    "secondary_plan_active",
                } and plan_state in {"fallback", "expired", "revoked", "inactive"}:
                    fallback_count += 1
                previous_plan = plan_state

            reject_reason = _state(
                str(
                    record.metadata.get("reject_reason")
                    or record.metadata.get("reason")
                    or record.metadata.get("terminal_contract_reject_reason")
                    or ""
                )
            )
            if event_type in {
                "secondary_takeover_fallback",
            }:
                fallback_count += 1
            if event_type in {
                "secondary_lease_expired",
                "secondary_plan_lease_expired",
            } or reject_reason in {"lease_expired", "secondary_lease_expired"}:
                lease_expiry_count += 1
            if event_type in {
                "stale_plan_reject",
                "secondary_stale_plan_reject",
            } or reject_reason in {
                "stale_plan",
                "stale_plan_reject",
                "stale_version",
            }:
                stale_reject_count += 1

        episode_end = max(
            episode_duration,
            max((record.timestamp for record in lifecycle_events), default=0.0),
        )
        readiness_dwell = _state_dwell_seconds(readiness_samples, episode_end)
        plan_dwell = _state_dwell_seconds(plan_samples, episode_end)
        ready_timestamp = next(
            (
                timestamp
                for timestamp, state in readiness_samples
                if state == "takeover_ready"
            ),
            None,
        )
        active_timestamp = next(
            (
                timestamp
                for timestamp, state in plan_samples
                if state == "secondary_plan_active"
                and (ready_timestamp is None or timestamp >= ready_timestamp)
            ),
            None,
        )
        activation_latency = (
            max(0.0, active_timestamp - ready_timestamp)
            if ready_timestamp is not None and active_timestamp is not None
            else None
        )

        return {
            "secondary_registration_usable_dwell_s": readiness_dwell.get(
                "registration_usable", 0.0
            ),
            "secondary_takeover_ready_dwell_s": readiness_dwell.get(
                "takeover_ready", 0.0
            ),
            "secondary_plan_pending_dwell_s": plan_dwell.get(
                "pending_secondary_plan", 0.0
            ),
            "secondary_plan_active_dwell_s": plan_dwell.get(
                "secondary_plan_active", 0.0
            ),
            "secondary_activation_latency_s": activation_latency,
            "secondary_takeover_fallback_count": fallback_count,
            "secondary_lease_expiry_count": lease_expiry_count,
            "stale_plan_reject_count": stale_reject_count,
            "_metadata": {
                "secondary_lifecycle_status": "available",
                "secondary_lifecycle_event_count": len(lifecycle_events),
                "secondary_readiness_state_dwell_s": readiness_dwell,
                "secondary_plan_state_dwell_s": plan_dwell,
                "secondary_readiness_state_sequence": [
                    {"timestamp_s": timestamp, "state": state}
                    for timestamp, state in readiness_samples
                ],
                "secondary_plan_state_sequence": [
                    {"timestamp_s": timestamp, "state": state}
                    for timestamp, state in plan_samples
                ],
            },
        }

    def _compute_visual_perception_metrics(self) -> dict[str, Any]:
        perception_events = [
            record
            for record in sorted(self.event_records, key=lambda item: item.timestamp)
            if _event_type(record) in self.D5_PERCEPTION_EVENTS
        ]
        if not perception_events:
            return {
                "visual_detection_recall": None,
                "local_id_continuity": None,
                "cross_view_registration_rate": None,
                "visual_pipeline_latency_ms": None,
                "visual_cpu_budget_utilization": None,
                "visual_gpu_budget_utilization": None,
                "visual_budget_violation_count": None,
                "online_truth_field_violation_count": None,
                "_metadata": {
                    "d5_perception_status": "unavailable",
                    "d5_perception_event_count": 0,
                },
            }

        visible_truth_count = 0
        matched_truth_count = 0
        cross_view_candidates = 0
        cross_view_registered = 0
        pipeline_latencies: list[float] = []
        cpu_utilization: list[float] = []
        gpu_utilization: list[float] = []
        backend_counts: dict[str, int] = defaultdict(int)
        tracker_counts: dict[str, int] = defaultdict(int)
        truth_track_history: dict[str, list[tuple[float, str]]] = defaultdict(list)
        budget_violation_count = 0
        truth_field_violation_count = 0

        for record in perception_events:
            metadata = record.metadata
            for key in ("truth_id", "actor_name", "object_name", "segmentation_id"):
                if key in metadata and metadata.get(key) not in (None, ""):
                    truth_field_violation_count += 1

            backend = _metadata_text(metadata, "detection_backend") or _metadata_text(
                metadata, "detector_backend"
            )
            tracker = _metadata_text(metadata, "tracker_backend") or _metadata_text(
                metadata, "mot_backend"
            )
            if backend is not None:
                backend_counts[backend] += 1
            if tracker is not None:
                tracker_counts[tracker] += 1

            offline_truth = metadata.get("offline_truth")
            if isinstance(offline_truth, Mapping):
                visible_truth_count += int(
                    _mapping_nonnegative_int(offline_truth, "visible_truth_count") or 0
                )
                matched_truth_count += int(
                    _mapping_nonnegative_int(offline_truth, "matched_truth_count") or 0
                )
                truth_to_local = offline_truth.get("truth_to_local_track_id")
                if isinstance(truth_to_local, Mapping):
                    for truth_id, local_track_id in truth_to_local.items():
                        if local_track_id is None:
                            continue
                        truth_track_history[str(truth_id)].append(
                            (record.timestamp, str(local_track_id))
                        )

            cross_view_candidates += int(
                _mapping_nonnegative_int(metadata, "cross_view_candidate_count") or 0
            )
            cross_view_registered += int(
                _mapping_nonnegative_int(metadata, "cross_view_registered_count") or 0
            )
            latency = _first_metadata_float(
                metadata,
                ("pipeline_latency_ms", "perception_latency_ms"),
            )
            if latency is None:
                detector_latency = _metadata_float(metadata, "detector_latency_ms")
                tracker_latency = _metadata_float(metadata, "tracker_latency_ms")
                if detector_latency is not None or tracker_latency is not None:
                    latency = (detector_latency or 0.0) + (tracker_latency or 0.0)
            if latency is not None:
                pipeline_latencies.append(latency)

            cpu_value = _first_metadata_float(
                metadata,
                ("cpu_budget_utilization", "cpu_utilization"),
            )
            gpu_value = _first_metadata_float(
                metadata,
                ("gpu_budget_utilization", "gpu_utilization"),
            )
            if cpu_value is not None:
                cpu_utilization.append(cpu_value)
            if gpu_value is not None:
                gpu_utilization.append(gpu_value)

            explicit_violation = _bool_from_metadata(
                metadata,
                ("performance_budget_violation", "visual_budget_violation"),
                default=False,
            )
            latency_budget = _metadata_float(metadata, "latency_budget_ms")
            cpu_budget = _metadata_float(metadata, "cpu_budget_utilization_limit")
            gpu_budget = _metadata_float(metadata, "gpu_budget_utilization_limit")
            budget_violation = explicit_violation
            budget_violation = budget_violation or (
                latency is not None
                and latency_budget is not None
                and latency > latency_budget
            )
            budget_violation = budget_violation or (
                cpu_value is not None and cpu_budget is not None and cpu_value > cpu_budget
            )
            budget_violation = budget_violation or (
                gpu_value is not None and gpu_budget is not None and gpu_value > gpu_budget
            )
            budget_violation_count += int(budget_violation)

        continuity_total = 0
        continuity_kept = 0
        for observations in truth_track_history.values():
            ordered_ids = [
                local_id for _, local_id in sorted(observations, key=lambda item: item[0])
            ]
            for previous, current in zip(ordered_ids, ordered_ids[1:]):
                continuity_total += 1
                continuity_kept += int(previous == current)

        return {
            "visual_detection_recall": (
                matched_truth_count / visible_truth_count
                if visible_truth_count > 0
                else None
            ),
            "local_id_continuity": (
                continuity_kept / continuity_total if continuity_total > 0 else None
            ),
            "cross_view_registration_rate": (
                cross_view_registered / cross_view_candidates
                if cross_view_candidates > 0
                else None
            ),
            "visual_pipeline_latency_ms": (
                _mean(pipeline_latencies) if pipeline_latencies else None
            ),
            "visual_cpu_budget_utilization": (
                _mean(cpu_utilization) if cpu_utilization else None
            ),
            "visual_gpu_budget_utilization": (
                _mean(gpu_utilization) if gpu_utilization else None
            ),
            "visual_budget_violation_count": budget_violation_count,
            "online_truth_field_violation_count": truth_field_violation_count,
            "_metadata": {
                "d5_perception_status": "available",
                "d5_perception_event_count": len(perception_events),
                "detection_backend_counts": dict(backend_counts),
                "tracker_backend_counts": dict(tracker_counts),
                "offline_truth_visible_count": visible_truth_count,
                "offline_truth_matched_count": matched_truth_count,
                "local_id_transition_count": continuity_total,
                "local_id_continuous_transition_count": continuity_kept,
                "cross_view_candidate_count": cross_view_candidates,
                "cross_view_registered_count": cross_view_registered,
                "visual_pipeline_latency_ms_samples": pipeline_latencies,
                "online_truth_fields_are_evaluation_only": True,
            },
        }

    def _failover_active_window_delta_from_metadata(
        self,
        record: EventRecord,
    ) -> float | None:
        metadata = record.metadata
        for key in (
            "failover_active_window_delta_s",
            "active_window_delta_s",
            "failover_window_delta_s",
        ):
            value = _metadata_float(metadata, key)
            if value is not None:
                return max(0.0, value)

        active_window_end = _metadata_float(metadata, "active_window_end_s")
        if active_window_end is None:
            active_window_end = _metadata_float(metadata, "active_window_end_timestamp")
        failover_timestamp = (
            _metadata_float(metadata, "failover_timestamp_s")
            or _metadata_float(metadata, "failover_timestamp")
            or _metadata_float(metadata, "takeover_timestamp_s")
            or _metadata_float(metadata, "takeover_timestamp")
        )
        if active_window_end is not None and failover_timestamp is not None:
            return max(0.0, failover_timestamp - active_window_end)
        return None

    def _compute_terminal_metrics(self) -> dict[str, float | int]:
        accuracy_attempts = 0
        correct_attempts = 0
        for record in self.terminal_records:
            correctness = _terminal_correctness(record)
            is_attempt = (
                _state(record.decision_state) in self.ASSOCIATION_STATES
                or (
                    record.assigned_global_track_id is not None
                    and record.local_track_id is not None
                    and _state(record.decision_state) not in self.FOV_ENTRY_STATES
                )
            )
            if is_attempt and correctness is not None:
                accuracy_attempts += 1
                correct_attempts += int(correctness)

        terminal_association_accuracy = (
            correct_attempts / accuracy_attempts if accuracy_attempts else 0.0
        )

        terminal_id_switch_count = self._count_terminal_id_switches()
        ambiguous_fov_event_count = len(self._terminal_event_keys("ambiguous"))
        friend_overlap_hold_count = len(self._terminal_event_keys("friend_hold"))
        time_to_terminal_lock = self._compute_time_to_terminal_lock()
        terminal_lock_count = self._compute_terminal_lock_count()
        multi_view_consensus_rate = self._compute_multi_view_consensus_rate()
        cross_view_conflict_count = self._compute_cross_view_conflict_count()
        duplicate_terminal_lock_count = self._compute_duplicate_terminal_lock_count()

        return {
            "terminal_association_accuracy": terminal_association_accuracy,
            "terminal_id_switch_count": terminal_id_switch_count,
            "ambiguous_fov_event_count": ambiguous_fov_event_count,
            "friend_overlap_hold_count": friend_overlap_hold_count,
            "time_to_terminal_lock": time_to_terminal_lock,
            "terminal_lock_count": terminal_lock_count,
            "multi_view_consensus_rate": multi_view_consensus_rate,
            "cross_view_conflict_count": cross_view_conflict_count,
            "duplicate_terminal_lock_count": duplicate_terminal_lock_count,
        }

    def _count_terminal_id_switches(self) -> int:
        by_assigned_track: dict[str, dict[float, str]] = defaultdict(dict)
        for record in self.terminal_records:
            if record.assigned_global_track_id is None or record.local_track_id is None:
                continue
            if _state(record.decision_state) in self.FOV_ENTRY_STATES:
                continue
            by_assigned_track[record.assigned_global_track_id].setdefault(
                record.timestamp,
                record.local_track_id,
            )

        switch_count = 0
        for timestamp_to_local in by_assigned_track.values():
            previous_local_id: str | None = None
            for timestamp in sorted(timestamp_to_local):
                local_id = timestamp_to_local[timestamp]
                if previous_local_id is not None and local_id != previous_local_id:
                    switch_count += 1
                previous_local_id = local_id
        return switch_count

    def _terminal_event_keys(self, kind: str) -> set[tuple[str, float, str, str | None, str | None]]:
        keys: set[tuple[str, float, str, str | None, str | None]] = set()
        if kind == "ambiguous":
            for record in self.terminal_records:
                if (
                    record.ambiguity_score is not None
                    and record.ambiguity_score >= self.ambiguous_fov_threshold
                ):
                    keys.add(_terminal_event_key_from_record("ambiguous", record))
            for record in self.event_records:
                if _event_type(record) in self.AMBIGUOUS_FOV_EVENTS:
                    keys.add(_terminal_event_key_from_event("ambiguous", record))
        elif kind == "friend_hold":
            for record in self.terminal_records:
                if _state(record.friend_conflict_state) in {
                    "hold",
                    "friend_overlap",
                    "friend_overlap_hold",
                    "blocked",
                    "verified_friend_overlap",
                }:
                    keys.add(_terminal_event_key_from_record("friend_hold", record))
            for record in self.event_records:
                if _event_type(record) in self.FRIEND_HOLD_EVENTS:
                    keys.add(_terminal_event_key_from_event("friend_hold", record))
        else:
            raise ValueError(f"unknown terminal event kind: {kind}")
        return keys

    def _compute_time_to_terminal_lock(self) -> float:
        entries: dict[tuple[str, str], float] = {}
        locks: dict[tuple[str, str], float] = {}

        for record in self.terminal_records:
            key = _terminal_key_from_record(record)
            if key is None:
                continue
            state = _state(record.decision_state)
            if state in self.FOV_ENTRY_STATES:
                entries.setdefault(key, record.timestamp)
            elif state in self.LOCK_STATES:
                locks.setdefault(key, record.timestamp)

        for record in self.event_records:
            event_type = _event_type(record)
            if event_type not in {"terminal_fov_entry", "terminal_lock"}:
                continue
            key = _terminal_key_from_event(record)
            if key is None:
                continue
            if event_type == "terminal_fov_entry":
                entries.setdefault(key, record.timestamp)
            else:
                locks.setdefault(key, record.timestamp)

        lock_deltas = [
            locks[key] - entry_time
            for key, entry_time in entries.items()
            if key in locks and locks[key] >= entry_time
        ]
        return _mean(lock_deltas)

    def _compute_terminal_lock_count(self) -> int:
        keys: set[tuple[str, float, str, str | None, str | None]] = set()
        for record in self.terminal_records:
            if _state(record.decision_state) in self.LOCK_STATES:
                keys.add(_terminal_event_key_from_record("terminal_lock", record))
        for record in self.event_records:
            if _event_type(record) == "terminal_lock" or _bool_from_metadata(
                record.metadata,
                ("terminal_locked",),
                default=False,
            ):
                keys.add(_terminal_event_key_from_event("terminal_lock", record))
        return len(keys)


    def _compute_multi_view_consensus_rate(self) -> float:
        attempts = 0
        successes = 0
        for record in self.event_records:
            event_type = _event_type(record)
            metadata = record.metadata
            has_consensus_field = any(
                key in metadata
                for key in (
                    "multi_view_consensus",
                    "consensus",
                    "consensus_reached",
                    "multi_view_consensus_reached",
                )
            )
            if (
                event_type in self.MULTI_VIEW_CONSENSUS_EVENTS
                or event_type in self.MULTI_VIEW_CONSENSUS_FAILURE_EVENTS
                or has_consensus_field
            ):
                attempts += 1
                if event_type in self.MULTI_VIEW_CONSENSUS_FAILURE_EVENTS:
                    default = False
                else:
                    default = event_type in self.MULTI_VIEW_CONSENSUS_EVENTS
                successes += int(
                    _bool_from_metadata(
                        metadata,
                        (
                            "multi_view_consensus",
                            "consensus_reached",
                            "multi_view_consensus_reached",
                            "consensus",
                        ),
                        default=default,
                    )
                )
        return successes / attempts if attempts else 0.0

    def _compute_cross_view_conflict_count(self) -> int:
        return sum(
            1
            for record in self.event_records
            if _event_type(record) in self.CROSS_VIEW_CONFLICT_EVENTS
            or _bool_from_metadata(
                record.metadata,
                ("cross_view_conflict", "multi_view_conflict"),
                default=False,
            )
        )

    def _compute_duplicate_terminal_lock_count(self) -> int:
        locks_by_snapshot: dict[tuple[float, str], set[str]] = defaultdict(set)
        for record in self.terminal_records:
            if _state(record.decision_state) not in self.LOCK_STATES:
                continue
            if record.assigned_global_track_id is None:
                continue
            locks_by_snapshot[
                (float(record.timestamp), str(record.assigned_global_track_id))
            ].add(record.resource_id)
        duplicate_keys = {
            key for key, resources in locks_by_snapshot.items() if len(resources) > 1
        }
        for record in self.event_records:
            if (
                _event_type(record) not in self.DUPLICATE_TERMINAL_LOCK_EVENTS
                and not _bool_from_metadata(
                    record.metadata,
                    ("duplicate_terminal_lock",),
                    default=False,
                )
            ):
                continue
            target = (
                _metadata_text(record.metadata, "global_track_id")
                or _metadata_text(record.metadata, "assigned_global_track_id")
                or _metadata_text(record.metadata, "target_id")
            )
            raw_resources = record.metadata.get("resource_ids")
            if target is None or isinstance(raw_resources, (str, bytes)):
                continue
            if isinstance(raw_resources, Sequence):
                resources = {str(value) for value in raw_resources}
                if len(resources) > 1:
                    duplicate_keys.add((float(record.timestamp), target))
        return len(duplicate_keys)

    def _compute_secondary_sensing_metrics(
        self,
        scale_counts: Mapping[str, int],
    ) -> dict[str, Any]:
        target_count = int(scale_counts.get("target_count") or 0)
        camera_count = int(scale_counts.get("camera_count") or 0)
        samples = self._secondary_sensing_samples()

        network_frames: dict[tuple[Any, ...], dict[str, Any]] = {}
        node_frames: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
        single_full_count = 0
        single_frame_count = 0
        node_single_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        cross_view_association_count = 0
        detect_available_not_registered_count = 0
        node_cross_counts: dict[str, int] = defaultdict(int)
        node_not_registered_counts: dict[str, int] = defaultdict(int)
        cue_errors: list[float] = []
        gimbal_errors: list[float] = []
        node_cue_errors: dict[str, list[float]] = defaultdict(list)
        node_gimbal_errors: dict[str, list[float]] = defaultdict(list)

        for sample in samples:
            metadata = sample["metadata"]
            event_type = sample["event_type"]
            fallback_text = sample["fallback_text"]
            node_type = (
                _secondary_node_type(metadata, fallback_text=fallback_text)
                or "secondary_network"
            )
            sample_target_count = _secondary_sample_target_count(
                metadata,
                default_target_count=target_count,
            )
            sample_camera_count = _secondary_sample_camera_count(
                metadata,
                default_camera_count=camera_count,
            )

            coverage = _secondary_coverage_sample(metadata)
            if coverage is not None:
                frame_key = _secondary_frame_key(sample)
                _add_secondary_frame_coverage(
                    network_frames,
                    frame_key,
                    coverage,
                    sample_target_count,
                )
                _add_secondary_frame_coverage(
                    node_frames[node_type],
                    frame_key,
                    coverage,
                    sample_target_count,
                )

            full_count, frame_count = _secondary_single_camera_counts(
                metadata,
                coverage,
                sample_target_count=sample_target_count,
                sample_camera_count=sample_camera_count,
            )
            if frame_count:
                single_full_count += full_count
                single_frame_count += frame_count
                node_single_counts[node_type][0] += full_count
                node_single_counts[node_type][1] += frame_count

            association_count = self._secondary_cross_view_association_increment(
                event_type,
                metadata,
            )
            if association_count:
                cross_view_association_count += association_count
                node_cross_counts[node_type] += association_count

            not_registered_count = self._secondary_not_registered_increment(
                event_type,
                metadata,
            )
            if not_registered_count:
                detect_available_not_registered_count += not_registered_count
                node_not_registered_counts[node_type] += not_registered_count

            cue_sample_errors = _metadata_angle_values_deg(
                metadata,
                degree_keys=(
                    "cue_pointing_error_deg",
                    "cue_error_deg",
                    "cue_angular_error_deg",
                    "cue_pointing_error_angle_deg",
                ),
                radian_keys=(
                    "cue_pointing_error_rad",
                    "cue_error_rad",
                    "cue_angular_error_rad",
                ),
            )
            gimbal_sample_errors = _metadata_angle_values_deg(
                metadata,
                degree_keys=(
                    "gimbal_pointing_error_deg",
                    "gimbal_error_deg",
                    "gimbal_angular_error_deg",
                    "gimbal_pointing_error_angle_deg",
                    "pointing_error_deg",
                ),
                radian_keys=(
                    "gimbal_pointing_error_rad",
                    "gimbal_error_rad",
                    "gimbal_angular_error_rad",
                    "pointing_error_rad",
                ),
            )
            if cue_sample_errors:
                cue_errors.extend(cue_sample_errors)
                node_cue_errors[node_type].extend(cue_sample_errors)
            if gimbal_sample_errors:
                gimbal_errors.extend(gimbal_sample_errors)
                node_gimbal_errors[node_type].extend(gimbal_sample_errors)

        network_stats = _secondary_frame_stats(network_frames)
        cue_stats = _angle_error_stats(cue_errors)
        gimbal_stats = _angle_error_stats(gimbal_errors)

        node_type_metrics: dict[str, dict[str, float | int]] = {}
        node_types = sorted(
            set(node_frames)
            | set(node_single_counts)
            | set(node_cross_counts)
            | set(node_not_registered_counts)
            | set(node_cue_errors)
            | set(node_gimbal_errors)
        )
        for node_type in node_types:
            node_frame_stats = _secondary_frame_stats(node_frames.get(node_type, {}))
            node_single_full, node_single_total = node_single_counts.get(
                node_type,
                [0, 0],
            )
            node_cue_stats = _angle_error_stats(node_cue_errors.get(node_type, []))
            node_gimbal_stats = _angle_error_stats(
                node_gimbal_errors.get(node_type, [])
            )
            node_type_metrics[node_type] = {
                "secondary_network_joint_full_view_frame_rate": (
                    node_frame_stats["full_view_frame_rate"]
                ),
                "secondary_network_mean_coverage_ratio": (
                    node_frame_stats["mean_coverage_ratio"]
                ),
                "secondary_single_camera_full_view_frame_rate": (
                    node_single_full / node_single_total
                    if node_single_total
                    else 0.0
                ),
                "cross_view_association_count": node_cross_counts.get(node_type, 0),
                "secondary_detect_available_but_not_registered_count": (
                    node_not_registered_counts.get(node_type, 0)
                ),
                "cue_pointing_error_count": node_cue_stats["count"],
                "cue_pointing_error_mean_deg": node_cue_stats["mean"],
                "cue_pointing_error_rmse_deg": node_cue_stats["rmse"],
                "cue_pointing_error_max_deg": node_cue_stats["max"],
                "gimbal_pointing_error_count": node_gimbal_stats["count"],
                "gimbal_pointing_error_mean_deg": node_gimbal_stats["mean"],
                "gimbal_pointing_error_rmse_deg": node_gimbal_stats["rmse"],
                "gimbal_pointing_error_max_deg": node_gimbal_stats["max"],
                "frame_count": node_frame_stats["frame_count"],
                "camera_frame_count": node_single_total,
            }

        return {
            "secondary_network_joint_full_view_frame_rate": network_stats[
                "full_view_frame_rate"
            ],
            "secondary_network_mean_coverage_ratio": network_stats[
                "mean_coverage_ratio"
            ],
            "secondary_single_camera_full_view_frame_rate": (
                single_full_count / single_frame_count if single_frame_count else 0.0
            ),
            "cross_view_association_count": cross_view_association_count,
            "secondary_detect_available_but_not_registered_count": (
                detect_available_not_registered_count
            ),
            "cue_pointing_error_count": cue_stats["count"],
            "cue_pointing_error_mean_deg": cue_stats["mean"],
            "cue_pointing_error_rmse_deg": cue_stats["rmse"],
            "cue_pointing_error_max_deg": cue_stats["max"],
            "gimbal_pointing_error_count": gimbal_stats["count"],
            "gimbal_pointing_error_mean_deg": gimbal_stats["mean"],
            "gimbal_pointing_error_rmse_deg": gimbal_stats["rmse"],
            "gimbal_pointing_error_max_deg": gimbal_stats["max"],
            "_metadata": {
                "secondary_sensing_frame_count": network_stats["frame_count"],
                "secondary_sensing_camera_frame_count": single_frame_count,
                "secondary_sensing_target_count": target_count,
                "secondary_sensing_camera_count": camera_count,
                "secondary_sensing_node_type_metrics": node_type_metrics,
                "secondary_sensing_source": "main_d4_d5_event_link_metadata",
            },
        }

    def _secondary_sensing_samples(self) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for record in self.event_records:
            metadata = dict(record.metadata)
            event_type = _event_type(record)
            fallback_text = " ".join(
                str(value)
                for value in (event_type, record.actor_id, record.note)
                if value is not None
            )
            if self._is_secondary_sensing_sample(
                event_type,
                metadata,
                fallback_text,
            ):
                samples.append(
                    {
                        "timestamp": record.timestamp,
                        "event_type": event_type,
                        "metadata": metadata,
                        "fallback_text": fallback_text,
                    }
                )

        for record in self.link_records:
            metadata = dict(record.metadata)
            fallback_text = " ".join(
                str(value)
                for value in (
                    record.source_node_id,
                    record.target_node_id,
                    record.relay_node_id,
                    record.link_type,
                    record.message_type,
                    record.payload_kind,
                )
                if value is not None
            )
            if self._is_secondary_sensing_sample("", metadata, fallback_text):
                samples.append(
                    {
                        "timestamp": record.timestamp,
                        "event_type": "",
                        "metadata": metadata,
                        "fallback_text": fallback_text,
                    }
                )
        return samples

    def _is_secondary_sensing_sample(
        self,
        event_type: str,
        metadata: Mapping[str, Any],
        fallback_text: str,
    ) -> bool:
        if event_type in (
            self.SECONDARY_SENSING_EVENTS
            | self.CROSS_VIEW_ASSOCIATION_EVENTS
            | self.SECONDARY_DETECT_NOT_REGISTERED_EVENTS
            | self.MULTI_VIEW_CONSENSUS_EVENTS
        ):
            return True
        if _secondary_node_type(metadata, fallback_text=fallback_text) is not None:
            return True
        return any(key in metadata for key in _SECONDARY_SENSING_METADATA_KEYS)

    def _secondary_cross_view_association_increment(
        self,
        event_type: str,
        metadata: Mapping[str, Any],
    ) -> int:
        explicit_count = _first_metadata_int(
            metadata,
            (
                "cross_view_association_count",
                "cross_view_associated_count",
                "d5_cross_view_association_count",
            ),
        )
        if explicit_count is not None:
            return max(0, explicit_count)

        if event_type in self.CROSS_VIEW_ASSOCIATION_EVENTS:
            success = _bool_from_metadata(
                metadata,
                (
                    "association_success",
                    "cross_view_association_success",
                    "associated",
                    "registered",
                ),
                default=True,
            )
            return int(success)

        if event_type in self.MULTI_VIEW_CONSENSUS_EVENTS:
            success = _bool_from_metadata(
                metadata,
                (
                    "multi_view_consensus",
                    "consensus_reached",
                    "multi_view_consensus_reached",
                    "cross_view_association",
                ),
                default=True,
            )
            return int(success)

        if _bool_from_metadata(
            metadata,
            (
                "cross_view_association",
                "cross_view_association_success",
                "d5_cross_view_association",
            ),
            default=False,
        ):
            return 1
        return 0

    def _secondary_not_registered_increment(
        self,
        event_type: str,
        metadata: Mapping[str, Any],
    ) -> int:
        explicit_count = _first_metadata_int(
            metadata,
            (
                "secondary_detect_available_but_not_registered_count",
                "detect_available_but_not_registered_count",
                "d5_registration_miss_count",
            ),
        )
        if explicit_count is not None:
            return max(0, explicit_count)

        if event_type in self.SECONDARY_DETECT_NOT_REGISTERED_EVENTS:
            return 1

        detect_available = _bool_from_metadata(
            metadata,
            (
                "secondary_detect_available",
                "detect_available",
                "detection_available",
                "bbox_available",
            ),
            default=False,
        )
        registration_keys = (
            "registered",
            "registration_success",
            "d5_registered",
            "terminal_registered",
            "association_registered",
        )
        has_registration_state = any(key in metadata for key in registration_keys)
        if not detect_available or not has_registration_state:
            return 0
        registered = _bool_from_metadata(metadata, registration_keys, default=True)
        return int(not registered)

    def _compute_link_metrics(self) -> dict[str, float | int]:
        link_items = self._communication_items()
        delivered_items = [item for item in link_items if item["delivered"]]
        latencies_s = [
            latency_s
            for item in delivered_items
            for latency_s in [_communication_latency_s(item)]
            if latency_s is not None
        ]

        dropped_count = sum(1 for item in link_items if not item["delivered"])
        total_messages = len(link_items)
        message_drop_rate = dropped_count / total_messages if total_messages else 0.0

        return {
            "cross_node_latency_ms": _mean(latencies_s) * 1000.0,
            "message_drop_rate": message_drop_rate,
            "out_of_order_count": self._compute_out_of_order_count(link_items),
            "stale_track_update_count": self._compute_stale_track_update_count(link_items),
            "video_metadata_delivery_rate": _delivery_rate(
                link_items,
                {
                    "video_metadata",
                    "video",
                    "video_cue",
                    "video_metadata_delivery",
                    "video_metadata_delivered",
                },
            ),
            "bbox_delivery_rate": _delivery_rate(
                link_items,
                {
                    "bbox",
                    "bboxes",
                    "detection_bbox",
                    "detection_box",
                    "bbox_delivery",
                    "bbox_delivered",
                },
            ),
            "consensus_latency_s": self._compute_consensus_latency_s(link_items),
        }

    def _communication_items(self) -> list[dict[str, Any]]:
        items = [_link_record_to_item(record) for record in self.link_records]
        for record in self.event_records:
            item = _event_to_communication_item(record)
            if item is not None:
                items.append(item)
        return items

    def _compute_out_of_order_count(self, link_items: Sequence[Mapping[str, Any]]) -> int:
        explicit_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.OUT_OF_ORDER_EVENTS
            or _bool_from_metadata(record.metadata, ("out_of_order",), default=False)
        )
        previous_by_stream: dict[tuple[str, str, str, str], int] = {}
        sequence_count = 0
        ordered_items = sorted(
            link_items,
            key=lambda item: float(
                item.get("received_timestamp")
                or item.get("arrival_timestamp")
                or item.get("timestamp")
                or 0.0
            ),
        )
        for item in ordered_items:
            if not item.get("delivered", True):
                continue
            sequence = _sequence_int(item.get("sequence_id"))
            if sequence is None:
                continue
            stream_key = (
                str(item.get("source_node_id") or ""),
                str(item.get("target_node_id") or ""),
                str(item.get("link_type") or ""),
                str(item.get("message_type") or item.get("payload_kind") or ""),
            )
            previous = previous_by_stream.get(stream_key)
            if previous is not None and sequence < previous:
                sequence_count += 1
            previous_by_stream[stream_key] = max(previous or sequence, sequence)
        return explicit_count + sequence_count

    def _compute_stale_track_update_count(
        self,
        link_items: Sequence[Mapping[str, Any]],
    ) -> int:
        explicit_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.STALE_TRACK_EVENTS
            or _bool_from_metadata(record.metadata, ("stale", "stale_track_update"), default=False)
        )
        stale_count = 0
        for item in link_items:
            if not item.get("delivered", True):
                continue
            if _payload_kind(item) not in {"track", "track_summary", "global_track"}:
                continue
            stale_after_s = _optional_float_value(item.get("stale_after_s"))
            if stale_after_s is None:
                continue
            age_s = _track_update_age_s(item)
            if age_s is not None and age_s > stale_after_s:
                stale_count += 1
        return explicit_count + stale_count

    def _compute_consensus_latency_s(
        self,
        link_items: Sequence[Mapping[str, Any]],
    ) -> float:
        latencies: list[float] = []
        for record in self.event_records:
            for key in ("consensus_latency_s", "consensus_latency"):
                value = _metadata_float(record.metadata, key)
                if value is not None:
                    latencies.append(value)
            start_timestamp = _metadata_float(record.metadata, "consensus_start_timestamp")
            if start_timestamp is not None and _event_type(record) in {
                "consensus_stable",
                "consensus_complete",
            }:
                latencies.append(max(0.0, record.timestamp - start_timestamp))

        for item in link_items:
            if not item.get("delivered", True):
                continue
            if _payload_kind(item) not in {"consensus", "bid", "bid_state"}:
                continue
            latency_s = _communication_latency_s(item)
            if latency_s is not None:
                latencies.append(latency_s)
        return _mean(latencies)

    def _compute_guidance_gate_metrics(self) -> dict[str, Any]:
        camera_values: list[bool] = []
        los_values: list[bool] = []
        maneuver_values: list[bool] = []
        terminal_switch_allowed_values: list[bool] = []
        contract_allowed_values: list[bool] = []
        control_allowed_values: list[bool] = []
        terminal_switch_reject_count = 0
        gate_reject_count = 0
        mode_switch_count = 0
        visual_png_switch_count = 0
        terminal_contract_reject_count = 0
        guidance_law_counts: dict[str, int] = defaultdict(int)
        reject_reasons: dict[str, int] = defaultdict(int)
        contract_reject_reasons: dict[str, int] = defaultdict(int)
        guidance_mode_counts: dict[str, int] = defaultdict(int)
        d4_state_counts: dict[str, int] = defaultdict(int)
        d5_state_counts: dict[str, int] = defaultdict(int)
        plan_version_counts: dict[str, int] = defaultdict(int)
        guidance_law_by_pair: dict[tuple[str, str], tuple[float, str]] = {}
        reject_reasons_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
        plan_ids: set[str] = set()

        for record in self.event_records:
            metadata = record.metadata
            event_type = _event_type(record)
            guidance_law = metadata.get("guidance_law")
            if guidance_law is not None:
                guidance_law_text = str(guidance_law)
                guidance_law_counts[guidance_law_text] += 1
                pair_key = _intercept_pair_key(record)
                if pair_key is not None:
                    previous = guidance_law_by_pair.get(pair_key)
                    if previous is None or record.timestamp >= previous[0]:
                        guidance_law_by_pair[pair_key] = (
                            record.timestamp,
                            guidance_law_text,
                        )
            mode = _metadata_text(metadata, "mode")
            if mode is not None:
                guidance_mode_counts[mode] += 1
            d4_state = _metadata_text(metadata, "d4_state") or _metadata_text(
                metadata, "d4_mode"
            )
            if d4_state is not None:
                d4_state_counts[d4_state] += 1
            d5_state = _metadata_text(metadata, "d5_state") or _metadata_text(
                metadata, "terminal_state"
            )
            if d5_state is not None:
                d5_state_counts[d5_state] += 1
            plan_id = _metadata_text(metadata, "plan_id")
            if plan_id is not None:
                plan_ids.add(plan_id)
            plan_version = _metadata_text(metadata, "plan_version") or _metadata_text(
                metadata, "version"
            )
            if plan_version is not None:
                plan_version_counts[plan_version] += 1

            if _bool_from_metadata(metadata, ("mode_switch",), default=False):
                mode_switch_count += 1
            if _visual_png_switch_from_event(record):
                visual_png_switch_count += 1

            if (
                event_type
                in self.D7_CONTROL_COMMAND_EVENTS | self.D7_GUIDANCE_RECORD_EVENTS
                and "terminal_switch_allowed" in metadata
            ):
                terminal_switch_allowed_values.append(
                    _as_bool(metadata["terminal_switch_allowed"], default=False)
                )

            contract_allowed = _first_metadata_bool(
                metadata,
                ("contract_allowed", "terminal_contract_allowed"),
            )
            if (
                contract_allowed is None
                and event_type in self.D7_GUIDANCE_RECORD_EVENTS
                and "terminal_switch_allowed" in metadata
            ):
                # Main episode bus records its contract decision under this
                # historical key; the D7 runtime control decision is separate.
                contract_allowed = _as_bool(
                    metadata["terminal_switch_allowed"],
                    default=False,
                )
            if contract_allowed is not None:
                contract_allowed_values.append(contract_allowed)

            control_allowed = _first_metadata_bool(
                metadata,
                (
                    "control_allowed",
                    "terminal_control_allowed",
                    "d7_runtime_terminal_switch_allowed",
                ),
            )
            if (
                control_allowed is None
                and "terminal_contract_allowed" in metadata
                and "terminal_switch_allowed" in metadata
            ):
                control_allowed = _as_bool(
                    metadata["terminal_switch_allowed"],
                    default=False,
                )
            if control_allowed is not None:
                control_allowed_values.append(control_allowed)

            _append_gate_value(
                camera_values,
                metadata,
                (
                    "camera_quality_gate_pass",
                    "camera_quality_gate_passed",
                    "camera_gate_pass",
                    "camera_gate",
                ),
            )
            _append_gate_value(
                los_values,
                metadata,
                (
                    "los_quality_gate_pass",
                    "los_quality_gate_passed",
                    "los_gate_pass",
                    "los_gate",
                ),
            )
            _append_gate_value(
                maneuver_values,
                metadata,
                (
                    "maneuver_margin_gate_pass",
                    "maneuver_margin_gate_passed",
                    "maneuver_gate_pass",
                    "maneuver_margin_gate",
                    "maneuver_gate",
                ),
            )

            reject_reason = (
                _metadata_text(metadata, "terminal_switch_reject_reason")
                or _metadata_text(metadata, "terminal_contract_reject_reason")
            )
            rejected = event_type in self.TERMINAL_SWITCH_REJECT_EVENTS
            rejected = rejected or reject_reason is not None
            rejected = rejected or _bool_from_metadata(
                metadata,
                ("terminal_switch_rejected", "terminal_switch_reject"),
                default=False,
            )
            if not rejected:
                rejected = _gate_reject_from_metadata(metadata)
            if rejected:
                terminal_switch_reject_count += 1
                gate_reject_count += 1
                if reject_reason is not None:
                    reject_reasons[reject_reason] += 1
                    pair_key = _intercept_pair_key(record)
                    if pair_key is not None:
                        reject_reasons_by_pair[pair_key].add(reject_reason)

            contract_reject_reason = _metadata_text(
                metadata,
                "terminal_contract_reject_reason",
            )
            if contract_reject_reason is not None:
                terminal_contract_reject_count += 1
                contract_reject_reasons[contract_reject_reason] += 1

        return {
            "camera_quality_gate_pass_rate": _bool_rate(camera_values),
            "los_quality_gate_pass_rate": _bool_rate(los_values),
            "maneuver_margin_gate_pass_rate": _bool_rate(maneuver_values),
            "terminal_switch_allowed_rate": _bool_rate(terminal_switch_allowed_values),
            "visual_png_switch_count": visual_png_switch_count,
            "terminal_switch_reject_count": terminal_switch_reject_count,
            "mode_switch_count": mode_switch_count,
            "terminal_contract_reject_count": terminal_contract_reject_count,
            "contract_evaluated_count": (
                len(contract_allowed_values) if contract_allowed_values else None
            ),
            "contract_allowed_count": (
                sum(contract_allowed_values) if contract_allowed_values else None
            ),
            "contract_allowed_rate": (
                _bool_rate(contract_allowed_values)
                if contract_allowed_values
                else None
            ),
            "control_evaluated_count": (
                len(control_allowed_values) if control_allowed_values else None
            ),
            "control_allowed_count": (
                sum(control_allowed_values) if control_allowed_values else None
            ),
            "control_allowed_rate": (
                _bool_rate(control_allowed_values)
                if control_allowed_values
                else None
            ),
            "mode_switched_count": (
                mode_switch_count
                if contract_allowed_values or control_allowed_values
                else None
            ),
            "gate_reject_count": gate_reject_count,
            "_metadata": {
                "guidance_law_counts": dict(guidance_law_counts),
                "guidance_law_pair_counts": _count_guidance_laws_by_pair(
                    guidance_law_by_pair
                ),
                "terminal_switch_reject_reasons": dict(reject_reasons),
                "terminal_switch_reject_reason_pair_counts": _count_reject_reasons_by_pair(
                    reject_reasons_by_pair
                ),
                "terminal_contract_reject_reasons": dict(contract_reject_reasons),
                "guidance_mode_counts": dict(guidance_mode_counts),
                "d4_state_counts": dict(d4_state_counts),
                "d5_state_counts": dict(d5_state_counts),
                "plan_version_counts": dict(plan_version_counts),
                "plan_ids": sorted(plan_ids),
                "terminal_execution_funnel": {
                    "contract_evaluated": len(contract_allowed_values),
                    "contract_allowed": sum(contract_allowed_values),
                    "control_evaluated": len(control_allowed_values),
                    "control_allowed": sum(control_allowed_values),
                    "mode_switched": mode_switch_count,
                },
            },
        }

    def _compute_terminal_delivery_metrics(self) -> dict[str, Any]:
        """Aggregate passive D7 terminal-filter and coast diagnostics.

        Every value remains unavailable until a persisted D7 record carries
        the corresponding field family.  This prevents legacy episodes from
        being interpreted as zero-rejection or zero-coast runs.
        """

        records = [
            record
            for record in self.event_records
            if _event_type(record)
            in self.D7_CONTROL_COMMAND_EVENTS | self.D7_GUIDANCE_RECORD_EVENTS
        ]
        summary_records = [
            record
            for record in self.event_records
            if _event_type(record) in self.INTERCEPT_SUMMARY_EVENTS
        ]
        summary_metadata = summary_records[-1].metadata if summary_records else {}
        evidence: dict[str, bool] = {
            name: False for name in _TERMINAL_DELIVERY_METRIC_NAMES
        }
        counts = {
            name: 0
            for name in _TERMINAL_DELIVERY_METRIC_NAMES
            if name.endswith("_count")
        }
        filter_states: dict[str, int] = defaultdict(int)
        ttc_reject_reasons: dict[str, int] = defaultdict(int)
        profiles: dict[str, int] = defaultdict(int)

        for record in records:
            metadata = record.metadata
            state = _terminal_filter_state(metadata)
            reason = _terminal_filter_reason(metadata)
            if state is not None:
                filter_states[state] += 1
                for name in (
                    "terminal_filter_measured_count",
                    "terminal_filter_predicted_count",
                    "terminal_filter_expired_count",
                ):
                    evidence[name] = True
                if state in {"measured", "update", "updated", "reacquired"}:
                    counts["terminal_filter_measured_count"] += 1
                if state in {
                    "predict",
                    "predicted",
                    "image_kf_predict",
                    "soft_predict",
                    "soft_prediction",
                }:
                    counts["terminal_filter_predicted_count"] += 1
                if state in {"expired", "invalid", "lost_after_coast"}:
                    counts["terminal_filter_expired_count"] += 1

            innovation_rejected = _terminal_diagnostic_flag(
                metadata,
                ("terminal_filter_innovation_rejected", "innovation_rejected"),
                reason_tokens=("innovation_rejected", "innovation_reject"),
            )
            if innovation_rejected is not None:
                evidence["terminal_filter_innovation_rejected_count"] = True
                counts["terminal_filter_innovation_rejected_count"] += int(
                    innovation_rejected
                )

            reset = _terminal_diagnostic_flag(
                metadata,
                ("terminal_filter_reset", "image_kf_reset", "filter_reset"),
                reason_tokens=("filter_reset", "image_kf_reset", "track_reset"),
            )
            if reset is not None or any(
                key in metadata
                for key in ("terminal_filter_reset_reason", "image_kf_reset_reason")
            ):
                evidence["terminal_filter_reset_count"] = True
                counts["terminal_filter_reset_count"] += int(reset is not False)

            ttc_reason = _normalized_reason(
                _first_metadata_text(
                    metadata,
                    (
                        "ttc_reject_reason",
                        "ttc_area_reject_reason",
                        "ttc_validity_reason",
                    ),
                )
            )
            if ttc_reason:
                ttc_reject_reasons[ttc_reason] += 1
            _accumulate_reason_metric(
                metadata,
                ttc_reason,
                metric_name="ttc_area_jump_reject_count",
                flag_keys=("ttc_area_jump_rejected", "area_jump_rejected"),
                reason_tokens=("area_jump", "area_ratio_jump"),
                evidence=evidence,
                counts=counts,
            )
            _accumulate_reason_metric(
                metadata,
                ttc_reason,
                metric_name="ttc_bbox_clipping_reject_count",
                flag_keys=("ttc_bbox_clipping_rejected", "bbox_clipping_rejected"),
                reason_tokens=("bbox_clipping", "bbox_clipped", "edge_clipped"),
                evidence=evidence,
                counts=counts,
            )
            _accumulate_reason_metric(
                metadata,
                ttc_reason,
                metric_name="ttc_not_expanding_reject_count",
                flag_keys=("ttc_not_expanding_rejected", "not_expanding_rejected"),
                reason_tokens=("not_expanding", "area_not_expanding"),
                evidence=evidence,
                counts=counts,
            )
            _accumulate_reason_metric(
                metadata,
                ttc_reason,
                metric_name="ttc_out_of_range_reject_count",
                flag_keys=("ttc_out_of_range_rejected", "ttc_range_rejected"),
                reason_tokens=("ttc_out_of_range", "out_of_range", "max_ttc"),
                evidence=evidence,
                counts=counts,
            )

            soft_prediction = _soft_prediction_active(metadata, state)
            if soft_prediction is not None:
                evidence["soft_prediction_count"] = True
                counts["soft_prediction_count"] += int(soft_prediction)
            soft_expired = _terminal_diagnostic_flag(
                metadata,
                ("soft_prediction_expired", "terminal_soft_prediction_expired"),
                reason_tokens=("soft_prediction_expired", "soft_predict_expired"),
            )
            if soft_expired is not None:
                evidence["soft_prediction_expired_count"] = True
                counts["soft_prediction_expired_count"] += int(soft_expired)

            coast = _terminal_coast_active(metadata, state)
            if coast is not None:
                evidence["terminal_coast_count"] = True
                counts["terminal_coast_count"] += int(coast)
            coast_expired = _terminal_diagnostic_flag(
                metadata,
                ("terminal_coast_expired", "coast_expired"),
                reason_tokens=("lost_after_coast", "coast_expired"),
            )
            if coast_expired is not None:
                evidence["terminal_coast_expired_count"] = True
                counts["terminal_coast_expired_count"] += int(coast_expired)

            profile = _first_metadata_text(
                metadata,
                (
                    "terminal_delivery_profile",
                    "comparison_role",
                    "algorithm_variant",
                ),
            )
            if profile:
                profiles[profile] += 1

        soft_duration = _observed_state_duration(
            records,
            state_predicate=lambda metadata: _soft_prediction_active(
                metadata,
                _terminal_filter_state(metadata),
            ),
            elapsed_keys=(
                "soft_prediction_elapsed_s",
                "terminal_soft_prediction_elapsed_s",
                "terminal_prediction_age_s",
                "prediction_age_s",
            ),
        )
        coast_duration = _observed_state_duration(
            records,
            state_predicate=lambda metadata: _terminal_coast_active(
                metadata,
                _terminal_filter_state(metadata),
            ),
            elapsed_keys=(
                "terminal_coast_elapsed_s",
                "coast_elapsed_s",
                "terminal_blind_elapsed_s",
                "blind_elapsed_s",
            ),
        )
        lock_continuity = _terminal_lock_continuity(records)
        visual_duration = _observed_state_duration(
            records,
            state_predicate=_visual_mode_active,
            elapsed_keys=("visual_mode_elapsed_s", "terminal_mode_elapsed_s"),
        )
        command_deltas = _command_discontinuities(records)

        optional_values: dict[str, float | None] = {
            "soft_prediction_duration_s": soft_duration,
            "terminal_coast_duration_s": coast_duration,
            "terminal_lock_continuity": lock_continuity,
            "visual_mode_duration_s": visual_duration,
            "command_discontinuity_mean_mps": (
                _mean(command_deltas) if command_deltas is not None else None
            ),
            "command_discontinuity_max_mps": (
                max(command_deltas) if command_deltas else None
            ),
        }
        for name in counts:
            explicit_count = _metadata_int(summary_metadata, name)
            if explicit_count is not None:
                counts[name] = explicit_count
                evidence[name] = True
        for name in optional_values:
            explicit_value = _metadata_float(summary_metadata, name)
            if explicit_value is not None:
                optional_values[name] = explicit_value
        for name, value in optional_values.items():
            evidence[name] = value is not None

        summary_profile = _first_metadata_text(
            summary_metadata,
            ("terminal_delivery_profile", "comparison_role", "algorithm_variant"),
        )
        if summary_profile:
            profiles[summary_profile] += 1

        result: dict[str, Any] = {
            name: counts[name] if evidence[name] else None for name in counts
        }
        result.update(optional_values)
        availability = {
            name: {
                "status": "available" if evidence[name] else "unavailable",
                "reason": (
                    "persisted D7 terminal delivery evidence"
                    if evidence[name]
                    else "required D7 terminal delivery fields are absent"
                ),
            }
            for name in _TERMINAL_DELIVERY_METRIC_NAMES
        }
        return {
            **result,
            "_metadata": {
                "metric_availability": availability,
                "terminal_filter_state_counts": dict(filter_states),
                "terminal_ttc_reject_reason_counts": dict(ttc_reject_reasons),
                "terminal_delivery_profile_counts": dict(profiles),
                "terminal_delivery_profile": (
                    next(iter(profiles)) if len(profiles) == 1 else None
                ),
                "terminal_delivery_offline_only": True,
            },
        }

    def _compute_intercept_metrics(self) -> dict[str, Any]:
        summary_success_count: int | None = None
        summary_pair_count: int | None = None
        summary_events: list[EventRecord] = []
        pair_events: list[EventRecord] = []
        command_events: list[EventRecord] = []

        for record in self.event_records:
            event_type = _event_type(record)
            if event_type in self.INTERCEPT_SUMMARY_EVENTS:
                summary_events.append(record)
                value = _metadata_int(record.metadata, "success_count")
                if value is not None:
                    summary_success_count = value
                pair_count = _metadata_int(record.metadata, "pair_count")
                if pair_count is not None:
                    summary_pair_count = pair_count
            elif event_type in self.INTERCEPT_PAIR_SUMMARY_EVENTS:
                pair_events.append(record)
            elif event_type in self.D7_CONTROL_COMMAND_EVENTS:
                command_events.append(record)

        summary_metadata = summary_events[-1].metadata if summary_events else {}

        if pair_events:
            result = self._intercept_metrics_from_pair_events(
                pair_events,
                summary_success_count=summary_success_count,
            )
        else:
            result = self._intercept_metrics_from_command_events(command_events)
            if summary_success_count is not None:
                result["intercept_success_count"] = summary_success_count

        command_physical_evidence = any(
            any(
                key in record.metadata
                for key in (
                    "status",
                    "collision_seen",
                    "target_collision_seen",
                    "physical_intercept",
                )
            )
            for record in command_events
        )
        physical_available, unavailable_reason = _physical_intercept_availability(
            summary_metadata,
            default_available=bool(
                pair_events or command_physical_evidence or summary_success_count is not None
            ),
        )
        layered = _layered_physical_success_metrics(
            pair_events=pair_events,
            command_events=command_events,
            summary_metadata=summary_metadata,
            physical_available=physical_available,
        )
        result.update({key: value for key, value in layered.items() if key != "_metadata"})
        result["physical_intercept_count"] = result["pair_physical_success_count"]

        diagnostics = _detect_coast_diagnostics(
            summary_events=summary_events,
            pair_events=pair_events,
            command_events=command_events,
        )
        result.update({key: value for key, value in diagnostics.items() if key != "_metadata"})

        terminal_takeover = self._terminal_takeover_metrics(
            pair_events,
            command_events,
            summary_pair_count=summary_pair_count,
        )
        result.update(
            {
                key: value
                for key, value in terminal_takeover.items()
                if key != "_metadata"
            }
        )
        result["_metadata"] = {
            **result.get("_metadata", {}),
            **terminal_takeover.get("_metadata", {}),
            **layered.get("_metadata", {}),
            **diagnostics.get("_metadata", {}),
            "intercept_summary_success_count": summary_success_count,
            "intercept_summary_pair_count": summary_pair_count,
            "intercept_pair_event_count": len(pair_events),
            "d7_control_command_event_count": len(command_events),
            "physical_intercept_evidence_available": physical_available,
            "physical_intercept_unavailable_reason": unavailable_reason,
            "physical_intercept_source": (
                "pair_or_control_status"
                if physical_available and (pair_events or command_physical_evidence)
                else "intercept_summary"
                if physical_available and summary_events
                else "unavailable"
            ),
        }
        return result

    def _intercept_metrics_from_pair_events(
        self,
        records: Sequence[EventRecord],
        *,
        summary_success_count: int | None,
    ) -> dict[str, Any]:
        collision_count = 0
        range_count = 0
        time_to_intercepts: list[float] = []
        min_ranges: list[float] = []
        status_counts: dict[str, int] = defaultdict(int)

        for record in records:
            metadata = record.metadata
            status = _state(str(metadata.get("status") or ""))
            if status:
                status_counts[status] += 1
            if status == "collision_intercept":
                collision_count += 1
            elif status == "range_intercept":
                range_count += 1

            min_range = _metadata_float(metadata, "min_range_m")
            if min_range is not None:
                min_ranges.append(min_range)

            if status in self.INTERCEPT_SUCCESS_STATUSES:
                time_to_intercept = _metadata_float(metadata, "time_to_intercept_s")
                if time_to_intercept is not None:
                    time_to_intercepts.append(time_to_intercept)

        success_count = (
            summary_success_count
            if summary_success_count is not None
            else collision_count + range_count
        )
        return {
            "intercept_success_count": success_count,
            "collision_intercept_count": collision_count,
            "range_intercept_count": range_count,
            "time_to_intercept_s": _mean(time_to_intercepts),
            "min_range_m": min(min_ranges) if min_ranges else 0.0,
            "_metadata": {"intercept_status_counts": dict(status_counts)},
        }

    def _terminal_takeover_metrics(
        self,
        pair_events: Sequence[EventRecord],
        command_events: Sequence[EventRecord],
        *,
        summary_pair_count: int | None,
    ) -> dict[str, Any]:
        observed_pairs: set[tuple[str, str]] = set()
        terminal_takeover_pairs: set[tuple[str, str]] = set()
        for record in list(pair_events) + list(command_events):
            pair_key = _intercept_pair_key(record)
            if pair_key is None:
                continue
            observed_pairs.add(pair_key)
            if _terminal_takeover_from_metadata(record.metadata):
                terminal_takeover_pairs.add(pair_key)

        denominator = (
            summary_pair_count
            if summary_pair_count is not None and summary_pair_count > 0
            else len(observed_pairs)
        )
        terminal_takeover_rate = (
            len(terminal_takeover_pairs) / denominator if denominator else 0.0
        )
        return {
            "terminal_takeover_rate": terminal_takeover_rate,
            "_metadata": {
                "terminal_takeover_pair_count": len(terminal_takeover_pairs),
                "terminal_takeover_pair_denominator": denominator,
            },
        }

    def _intercept_metrics_from_command_events(
        self,
        records: Sequence[EventRecord],
    ) -> dict[str, Any]:
        by_pair: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
        for record in records:
            resource_id = str(record.metadata.get("resource_id") or record.actor_id or "")
            target_id = str(record.metadata.get("target_id") or "")
            by_pair[(resource_id, target_id)].append(record)

        collision_count = 0
        range_count = 0
        time_to_intercepts: list[float] = []
        min_ranges: list[float] = []
        status_counts: dict[str, int] = defaultdict(int)

        for pair_records in by_pair.values():
            ordered = sorted(pair_records, key=lambda record: record.timestamp)
            statuses = [
                _state(str(record.metadata.get("status") or ""))
                for record in ordered
                if record.metadata.get("status")
            ]
            final_status = statuses[-1] if statuses else ""
            any_collision_seen = any(
                _bool_from_metadata(
                    record.metadata,
                    ("collision_seen", "target_collision_seen"),
                    default=False,
                )
                for record in ordered
            )
            status = final_status
            if status not in self.INTERCEPT_SUCCESS_STATUSES and any_collision_seen:
                status = "collision_intercept"
            if status:
                status_counts[status] += 1

            if status == "collision_intercept":
                collision_count += 1
            elif status == "range_intercept":
                range_count += 1

            pair_ranges = [
                value
                for record in ordered
                for value in [_metadata_float(record.metadata, "range_m")]
                if value is not None
            ]
            if pair_ranges:
                min_ranges.append(min(pair_ranges))

            if status in self.INTERCEPT_SUCCESS_STATUSES:
                for record in ordered:
                    record_status = _state(str(record.metadata.get("status") or ""))
                    collision_seen = _bool_from_metadata(
                        record.metadata,
                        ("collision_seen", "target_collision_seen"),
                        default=False,
                    )
                    if (
                        record_status in self.INTERCEPT_SUCCESS_STATUSES
                        or collision_seen
                    ):
                        time_to_intercepts.append(float(record.timestamp))
                        break

        return {
            "intercept_success_count": collision_count + range_count,
            "collision_intercept_count": collision_count,
            "range_intercept_count": range_count,
            "time_to_intercept_s": _mean(time_to_intercepts),
            "min_range_m": min(min_ranges) if min_ranges else 0.0,
            "_metadata": {"intercept_status_counts": dict(status_counts)},
        }

    def _compute_safety_metrics(self) -> dict[str, int]:
        constraint_violation_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.CONSTRAINT_VIOLATION_EVENTS
        )
        human_override_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.HUMAN_OVERRIDE_EVENTS
        )
        return {
            "constraint_violation_count": constraint_violation_count,
            "human_override_count": human_override_count,
        }

    def _compute_performance_metrics(
        self,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        module_duration_samples: list[tuple[str, float]] = []
        loop_latency_samples: list[tuple[str, float]] = []
        record_latency_samples: list[tuple[str, float]] = []
        cpu_budget_samples: list[tuple[str, float]] = []
        gpu_budget_samples: list[tuple[str, float]] = []
        budget_violation_count = 0

        for metadata, module_hint in _truth_summary_performance_mappings(truth_summary):
            budget_violation_count += _collect_performance_mapping(
                metadata,
                module_hint=module_hint,
                module_duration_samples=module_duration_samples,
                loop_latency_samples=loop_latency_samples,
                record_latency_samples=record_latency_samples,
                cpu_budget_samples=cpu_budget_samples,
                gpu_budget_samples=gpu_budget_samples,
                allow_generic_duration=True,
            )

        for record in self.event_records:
            performance_event = _is_performance_event(record)
            for metadata in _performance_metadata_mappings(record.metadata):
                module_hint = (
                    _metadata_text(metadata, "module")
                    or _metadata_text(metadata, "module_name")
                    or _metadata_text(metadata, "module_id")
                    or record.actor_id
                    or _event_type(record)
                )
                budget_violation_count += _collect_performance_mapping(
                    metadata,
                    module_hint=module_hint,
                    module_duration_samples=module_duration_samples,
                    loop_latency_samples=loop_latency_samples,
                    record_latency_samples=record_latency_samples,
                    cpu_budget_samples=cpu_budget_samples,
                    gpu_budget_samples=gpu_budget_samples,
                    allow_generic_duration=performance_event,
                )

        for record in self.link_records:
            module_hint = (
                _metadata_text(record.metadata, "module")
                or record.source_node_id
                or record.payload_kind
            )
            for metadata in _performance_metadata_mappings(record.metadata):
                budget_violation_count += _collect_performance_mapping(
                    metadata,
                    module_hint=module_hint,
                    module_duration_samples=module_duration_samples,
                    loop_latency_samples=loop_latency_samples,
                    record_latency_samples=record_latency_samples,
                    cpu_budget_samples=cpu_budget_samples,
                    gpu_budget_samples=gpu_budget_samples,
                    allow_generic_duration=False,
                )

        cpu_utilization = _mean([value for _, value in cpu_budget_samples])
        gpu_utilization = _mean([value for _, value in gpu_budget_samples])
        budget_violation_count += sum(1 for _, value in cpu_budget_samples if value > 1.0)
        budget_violation_count += sum(1 for _, value in gpu_budget_samples if value > 1.0)

        module_duration_values = [value for _, value in module_duration_samples]
        loop_latency_values = [value for _, value in loop_latency_samples]
        record_latency_values = [value for _, value in record_latency_samples]

        return {
            "module_duration_ms": _mean(module_duration_values),
            "loop_latency_ms": _mean(loop_latency_values),
            "record_latency_ms": _mean(record_latency_values),
            "cpu_budget_utilization": cpu_utilization,
            "gpu_budget_utilization": gpu_utilization,
            "performance_budget_violation_count": budget_violation_count,
            "_metadata": {
                "performance": {
                    "module_duration_ms": _performance_distribution(
                        module_duration_samples
                    ),
                    "loop_latency_ms": _performance_distribution(
                        loop_latency_samples
                    ),
                    "record_latency_ms": _performance_distribution(
                        record_latency_samples
                    ),
                    "cpu_budget": _budget_distribution(cpu_budget_samples),
                    "gpu_budget": _budget_distribution(gpu_budget_samples),
                    "budget_violation_count": budget_violation_count,
                }
            },
        }

    def _compute_mission_status(
        self,
        metrics: EpisodeMetrics,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        failure_summary = self._derive_failure_causes(metrics, truth_summary)
        explicit_outcome = _explicit_mission_outcome(truth_summary, self.event_records)
        explicit_success_reason = _explicit_status_text(
            truth_summary,
            self.event_records,
            ("success_reason", "mission_success_reason", "outcome_reason"),
        )
        explicit_failure_reason = _explicit_status_text(
            truth_summary,
            self.event_records,
            ("failure_reason", "mission_failure_reason", "abort_reason"),
        )

        required_success_count = _mission_required_success_count(
            truth_summary,
            metrics,
        )
        abort_signal = self._has_abort_signal()
        runtime_exception_count = self._runtime_exception_count()
        hard_failure = (
            metrics.constraint_violation_count > 0
            or metrics.human_override_count > 0
            or runtime_exception_count > 0
        )

        if explicit_outcome is not None:
            outcome = explicit_outcome
        elif abort_signal or runtime_exception_count > 0:
            outcome = "aborted"
        elif required_success_count > 0 and metrics.intercept_success_count >= required_success_count and not hard_failure:
            outcome = "success"
        elif metrics.intercept_success_count > 0:
            outcome = "partial"
        elif _has_partial_progress(metrics):
            outcome = "partial"
        else:
            outcome = "failed"

        success_reason = explicit_success_reason or _default_success_reason(
            outcome,
            metrics,
            required_success_count,
        )
        failure_reason = explicit_failure_reason
        if not failure_reason and outcome in {"partial", "failed", "aborted"}:
            failure_reason = _default_failure_reason(
                outcome,
                failure_summary["root_cause"],
                failure_summary["top_failure_causes"],
            )

        return {
            "mission_outcome": outcome,
            "success_reason": success_reason,
            "failure_reason": failure_reason,
            "_metadata": failure_summary,
        }

    def _derive_failure_causes(
        self,
        metrics: EpisodeMetrics,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        scores: dict[str, float] = defaultdict(float)
        details: dict[str, list[str]] = defaultdict(list)

        def add(cause: str, score: float, detail: str) -> None:
            normalized = _normalize_failure_cause(cause)
            if normalized is None or score <= 0:
                return
            scores[normalized] += float(score)
            if detail not in details[normalized]:
                details[normalized].append(detail)

        if metrics.id_switch_count:
            add("tracking", metrics.id_switch_count, f"id_switch_count={metrics.id_switch_count}")
        if metrics.missed_detection_rate is not None and metrics.missed_detection_rate > 0.0:
            add(
                "tracking",
                metrics.missed_detection_rate,
                f"missed_detection_rate={metrics.missed_detection_rate:.6g}",
            )
        if metrics.track_continuity > 0.0 and metrics.track_continuity < 0.95:
            add(
                "tracking",
                1.0 - metrics.track_continuity,
                f"track_continuity={metrics.track_continuity:.6g}",
            )
        if metrics.false_alarm_rate is not None and metrics.false_alarm_rate > 0.0:
            add("tracking", metrics.false_alarm_rate, f"false_alarm_rate={metrics.false_alarm_rate:.6g}")

        if metrics.duplicate_assignment_count:
            add(
                "assignment",
                metrics.duplicate_assignment_count,
                f"duplicate_assignment_count={metrics.duplicate_assignment_count}",
            )
        if metrics.unassigned_high_threat_count:
            add(
                "assignment",
                metrics.unassigned_high_threat_count,
                f"unassigned_high_threat_count={metrics.unassigned_high_threat_count}",
            )

        terminal_gate_count = (
            metrics.terminal_switch_reject_count
            + metrics.terminal_contract_reject_count
            + metrics.gate_reject_count
        )
        if terminal_gate_count:
            add("terminal_gate", terminal_gate_count, f"terminal_gate_rejects={terminal_gate_count}")
        if metrics.ambiguous_fov_event_count:
            add(
                "terminal_gate",
                metrics.ambiguous_fov_event_count,
                f"ambiguous_fov_event_count={metrics.ambiguous_fov_event_count}",
            )
        if metrics.friend_overlap_hold_count:
            add(
                "terminal_gate",
                metrics.friend_overlap_hold_count,
                f"friend_overlap_hold_count={metrics.friend_overlap_hold_count}",
            )
        if metrics.duplicate_terminal_lock_count:
            add(
                "terminal_gate",
                metrics.duplicate_terminal_lock_count,
                f"duplicate_terminal_lock_count={metrics.duplicate_terminal_lock_count}",
            )

        required_success_count = _mission_required_success_count(truth_summary, metrics)
        if required_success_count > 0 and metrics.intercept_success_count < required_success_count:
            add(
                "guidance",
                required_success_count - metrics.intercept_success_count,
                "intercept_success_count="
                f"{metrics.intercept_success_count}/{required_success_count}",
            )
        if metrics.visual_png_switch_count == 0 and metrics.terminal_takeover_rate == 0.0 and terminal_gate_count:
            add("guidance", 1.0, "terminal_takeover_not_confirmed")

        if metrics.secondary_network_mean_coverage_ratio > 0.0 and metrics.secondary_network_mean_coverage_ratio < 1.0:
            add(
                "coverage",
                1.0 - metrics.secondary_network_mean_coverage_ratio,
                "secondary_network_mean_coverage_ratio="
                f"{metrics.secondary_network_mean_coverage_ratio:.6g}",
            )
        if metrics.secondary_detect_available_but_not_registered_count:
            add(
                "coverage",
                metrics.secondary_detect_available_but_not_registered_count,
                "secondary_detect_available_but_not_registered_count="
                f"{metrics.secondary_detect_available_but_not_registered_count}",
            )
        if metrics.cross_view_conflict_count:
            add("coverage", metrics.cross_view_conflict_count, f"cross_view_conflict_count={metrics.cross_view_conflict_count}")
        if metrics.camera_quality_gate_pass_rate > 0.0 and metrics.camera_quality_gate_pass_rate < 1.0:
            add(
                "coverage",
                1.0 - metrics.camera_quality_gate_pass_rate,
                f"camera_quality_gate_pass_rate={metrics.camera_quality_gate_pass_rate:.6g}",
            )

        if metrics.message_drop_rate > 0.0:
            add("communication", metrics.message_drop_rate, f"message_drop_rate={metrics.message_drop_rate:.6g}")
        if metrics.stale_track_update_count:
            add(
                "communication",
                metrics.stale_track_update_count,
                f"stale_track_update_count={metrics.stale_track_update_count}",
            )
        if metrics.out_of_order_count:
            add("communication", metrics.out_of_order_count, f"out_of_order_count={metrics.out_of_order_count}")

        if metrics.constraint_violation_count:
            add(
                "safety",
                metrics.constraint_violation_count,
                f"constraint_violation_count={metrics.constraint_violation_count}",
            )
        if metrics.human_override_count:
            add("safety", metrics.human_override_count, f"human_override_count={metrics.human_override_count}")

        if metrics.performance_budget_violation_count:
            add(
                "performance",
                metrics.performance_budget_violation_count,
                "performance_budget_violation_count="
                f"{metrics.performance_budget_violation_count}",
            )

        runtime_exception_count = self._runtime_exception_count()
        if runtime_exception_count:
            add("runtime_exception", runtime_exception_count, f"runtime_exception_count={runtime_exception_count}")

        for record in self.event_records:
            explicit_cause = (
                _metadata_text(record.metadata, "root_cause")
                or _metadata_text(record.metadata, "failure_cause")
                or _metadata_text(record.metadata, "failure_category")
            )
            if explicit_cause is not None:
                add(explicit_cause, 1.0, f"{_event_type(record)}:{explicit_cause}")
            event_type = _event_type(record)
            if event_type in self.MISSION_FAILED_EVENTS:
                failure_cause = (
                    explicit_cause
                    or _metadata_text(record.metadata, "reason")
                    or _metadata_text(record.metadata, "failure_reason")
                    or "guidance"
                )
                add(failure_cause, 1.0, f"{event_type}:{failure_cause}")

        top_failure_causes = [
            {
                "cause": cause,
                "score": score,
                "details": details.get(cause, [])[:5],
            }
            for cause, score in sorted(
                scores.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if score > 0.0
        ]
        root_cause = top_failure_causes[0]["cause"] if top_failure_causes else "none"

        return {
            "root_cause": root_cause,
            "top_failure_causes": top_failure_causes,
            "failure_cause_scores": dict(scores),
            "failure_cause_details": dict(details),
        }

    def _has_abort_signal(self) -> bool:
        for record in self.event_records:
            event_type = _event_type(record)
            if event_type in self.ABORT_EVENTS:
                return True
            if _bool_from_metadata(
                record.metadata,
                ("mission_aborted", "episode_aborted", "aborted"),
                default=False,
            ):
                return True
        return False

    def _runtime_exception_count(self) -> int:
        count = 0
        for record in self.event_records:
            event_type = _event_type(record)
            severity = _state(record.severity)
            if event_type in self.RUNTIME_EXCEPTION_EVENTS:
                count += 1
                continue
            if severity in {"error", "fatal", "exception", "critical"} and (
                "exception" in event_type or "runtime" in event_type
            ):
                count += 1
                continue
            if _bool_from_metadata(
                record.metadata,
                ("runtime_exception", "exception", "unhandled_exception"),
                default=False,
            ):
                count += 1
        return count

    def _compute_eval_tracking(
        self,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        eval_priority = _eval_tracking_text(
            truth_summary,
            (
                "eval_priority",
                "evaluation_priority",
                "gap_priority",
                "priority",
            ),
            default="P0",
        )
        implementation_status = _eval_tracking_text(
            truth_summary,
            (
                "implementation_status",
                "eval_implementation_status",
                "implementation_state",
                "status",
            ),
            default="implemented",
        )
        evidence_path = _eval_tracking_text(
            truth_summary,
            (
                "evidence_path",
                "evidence_file",
                "source_path",
                "metrics_path",
                "output_path",
            ),
            default="",
        )

        for record in self.event_records:
            metadata = record.metadata
            if eval_priority == "P0":
                eval_priority = (
                    _metadata_text(metadata, "eval_priority")
                    or _metadata_text(metadata, "evaluation_priority")
                    or eval_priority
                )
            if implementation_status == "implemented":
                implementation_status = (
                    _metadata_text(metadata, "implementation_status")
                    or _metadata_text(metadata, "eval_implementation_status")
                    or implementation_status
                )
            if not evidence_path:
                evidence_path = (
                    _metadata_text(metadata, "evidence_path")
                    or _metadata_text(metadata, "source_path")
                    or _metadata_text(metadata, "metrics_path")
                    or ""
                )

        return {
            "eval_priority": eval_priority,
            "implementation_status": implementation_status,
            "evidence_path": evidence_path,
            "_metadata": {
                "eval_tracking": {
                    "eval_priority": eval_priority,
                    "implementation_status": implementation_status,
                    "evidence_path": evidence_path,
                }
            },
        }



def _truth_summary_performance_mappings(
    truth_summary: Mapping[str, Any],
) -> list[tuple[Mapping[str, Any], str]]:
    mappings: list[tuple[Mapping[str, Any], str]] = []
    for mapping in _truth_summary_count_mappings(truth_summary):
        module_hint = (
            _metadata_text(mapping, "module")
            or _metadata_text(mapping, "module_name")
            or _metadata_text(mapping, "module_id")
            or "episode"
        )
        if _mapping_has_performance_keys(mapping):
            mappings.append((mapping, module_hint))
        for nested_key in (
            "performance",
            "timing",
            "timings",
            "latency",
            "latencies",
            "runtime_performance",
        ):
            nested = mapping.get(nested_key)
            if isinstance(nested, Mapping):
                nested_module = (
                    _metadata_text(nested, "module")
                    or _metadata_text(nested, "module_name")
                    or module_hint
                )
                mappings.append((nested, nested_module))
    return mappings


def _performance_metadata_mappings(
    metadata: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    mappings: list[Mapping[str, Any]] = []
    if _mapping_has_performance_keys(metadata):
        mappings.append(metadata)
    for nested_key in (
        "performance",
        "timing",
        "timings",
        "latency",
        "latencies",
        "runtime_performance",
    ):
        nested = metadata.get(nested_key)
        if isinstance(nested, Mapping):
            mappings.append(nested)
    return mappings or [metadata]


def _mapping_has_performance_keys(metadata: Mapping[str, Any]) -> bool:
    performance_keys = {
        "module_duration_ms",
        "module_duration_s",
        "loop_latency_ms",
        "loop_latency_s",
        "record_latency_ms",
        "record_latency_s",
        "cpu_budget_utilization",
        "gpu_budget_utilization",
        "cpu_budget_ratio",
        "gpu_budget_ratio",
        "cpu_usage_percent",
        "gpu_usage_percent",
        "performance_budget_violation",
        "budget_violation",
        "budget_exceeded",
    }
    return any(key in metadata for key in performance_keys)


def _is_performance_event(record: EventRecord) -> bool:
    event_type = _event_type(record)
    if any(
        token in event_type
        for token in ("performance", "timing", "latency", "loop", "budget")
    ):
        return True
    return _mapping_has_performance_keys(record.metadata)


def _collect_performance_mapping(
    metadata: Mapping[str, Any],
    *,
    module_hint: str | None,
    module_duration_samples: list[tuple[str, float]],
    loop_latency_samples: list[tuple[str, float]],
    record_latency_samples: list[tuple[str, float]],
    cpu_budget_samples: list[tuple[str, float]],
    gpu_budget_samples: list[tuple[str, float]],
    allow_generic_duration: bool,
) -> int:
    module_name = str(module_hint or "unknown")
    module_duration = _performance_ms_value(
        metadata,
        ms_keys=(
            "module_duration_ms",
            "module_runtime_ms",
            "module_elapsed_ms",
            "processing_duration_ms",
            "processing_time_ms",
        )
        + (("duration_ms", "elapsed_ms") if allow_generic_duration else ()),
        s_keys=(
            "module_duration_s",
            "module_runtime_s",
            "module_elapsed_s",
            "processing_duration_s",
            "processing_time_s",
        )
        + (("duration_s", "elapsed_s") if allow_generic_duration else ()),
    )
    if module_duration is not None:
        module_duration_samples.append((module_name, module_duration))

    loop_latency = _performance_ms_value(
        metadata,
        ms_keys=("loop_latency_ms", "loop_period_ms", "control_loop_latency_ms"),
        s_keys=("loop_latency_s", "loop_period_s", "control_loop_latency_s"),
    )
    if loop_latency is not None:
        loop_latency_samples.append((module_name, loop_latency))

    record_latency = _performance_ms_value(
        metadata,
        ms_keys=(
            "record_latency_ms",
            "record_write_latency_ms",
            "log_record_latency_ms",
            "metrics_record_latency_ms",
        ),
        s_keys=(
            "record_latency_s",
            "record_write_latency_s",
            "log_record_latency_s",
            "metrics_record_latency_s",
        ),
    )
    if record_latency is not None:
        record_latency_samples.append((module_name, record_latency))

    cpu_utilization = _performance_ratio_value(
        metadata,
        (
            "cpu_budget_utilization",
            "cpu_budget_ratio",
            "cpu_budget_used",
            "cpu_utilization",
            "cpu_usage",
            "cpu_usage_percent",
        ),
    )
    if cpu_utilization is not None:
        cpu_budget_samples.append((module_name, cpu_utilization))

    gpu_utilization = _performance_ratio_value(
        metadata,
        (
            "gpu_budget_utilization",
            "gpu_budget_ratio",
            "gpu_budget_used",
            "gpu_utilization",
            "gpu_usage",
            "gpu_usage_percent",
        ),
    )
    if gpu_utilization is not None:
        gpu_budget_samples.append((module_name, gpu_utilization))

    budget_violation_count = 0
    for key in (
        "performance_budget_violation",
        "performance_budget_exceeded",
        "budget_violation",
        "budget_exceeded",
        "latency_budget_exceeded",
    ):
        if key in metadata and _as_bool(metadata[key], default=False):
            budget_violation_count += 1
    return budget_violation_count


def _performance_ms_value(
    metadata: Mapping[str, Any],
    *,
    ms_keys: Sequence[str],
    s_keys: Sequence[str],
) -> float | None:
    for key in ms_keys:
        value = _metadata_float_if_present(metadata, key)
        if value is not None:
            return max(0.0, value)
    for key in s_keys:
        value = _metadata_float_if_present(metadata, key)
        if value is not None:
            return max(0.0, value * 1000.0)
    return None


def _performance_ratio_value(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> float | None:
    for key in keys:
        value = _metadata_float_if_present(metadata, key)
        if value is None:
            continue
        if "percent" in key or value > 1.0 and value <= 100.0:
            return max(0.0, value / 100.0)
        return max(0.0, value)
    return None


def _performance_distribution(
    samples: Sequence[tuple[str, float]],
) -> dict[str, Any]:
    values = [float(value) for _, value in samples]
    by_module: dict[str, list[float]] = defaultdict(list)
    for module_name, value in samples:
        by_module[module_name].append(float(value))
    return {
        "count": len(values),
        "mean": _mean(values),
        "p95": _percentile(values, 95.0),
        "max": max(values) if values else 0.0,
        "by_module": {
            module_name: {
                "count": len(module_values),
                "mean": _mean(module_values),
                "p95": _percentile(module_values, 95.0),
                "max": max(module_values) if module_values else 0.0,
            }
            for module_name, module_values in sorted(by_module.items())
        },
    }


def _budget_distribution(samples: Sequence[tuple[str, float]]) -> dict[str, Any]:
    values = [float(value) for _, value in samples]
    distribution = _performance_distribution(samples)
    distribution["utilization"] = _mean(values)
    distribution["placeholder"] = not values
    return distribution


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _explicit_mission_outcome(
    truth_summary: Mapping[str, Any],
    records: Sequence[EventRecord],
) -> str | None:
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in ("mission_outcome", "outcome", "episode_outcome", "mission_status"):
            value = _normalize_mission_outcome(mapping.get(key))
            if value is not None:
                return value
    for record in records:
        for key in ("mission_outcome", "outcome", "episode_outcome", "mission_status"):
            value = _normalize_mission_outcome(record.metadata.get(key))
            if value is not None:
                return value
        event_type = _event_type(record)
        if event_type in MetricsCollector.MISSION_SUCCESS_EVENTS:
            return "success"
        if event_type in MetricsCollector.MISSION_FAILED_EVENTS:
            return "failed"
        if event_type in MetricsCollector.ABORT_EVENTS:
            return "aborted"
    return None


def _normalize_mission_outcome(value: Any) -> str | None:
    text = _normalized_label(value)
    if not text:
        return None
    if text in {"success", "succeeded", "complete", "completed", "pass", "passed"}:
        return "success"
    if text in {"partial", "partial_success", "degraded_success", "incomplete"}:
        return "partial"
    if text in {"failed", "failure", "fail", "unsuccessful"}:
        return "failed"
    if text in {"aborted", "abort", "cancelled", "canceled", "timeout"}:
        return "aborted"
    return None


def _explicit_status_text(
    truth_summary: Mapping[str, Any],
    records: Sequence[EventRecord],
    keys: Sequence[str],
) -> str:
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in keys:
            value = _metadata_text(mapping, key)
            if value is not None:
                return value
    for record in records:
        for key in keys:
            value = _metadata_text(record.metadata, key)
            if value is not None:
                return value
    return ""


def _mission_required_success_count(
    truth_summary: Mapping[str, Any],
    metrics: EpisodeMetrics,
) -> int:
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in (
            "required_success_count",
            "mission_required_success_count",
            "required_intercept_count",
            "expected_intercept_count",
            "success_target_count",
        ):
            value = _optional_int_value(mapping.get(key))
            if value is not None and value > 0:
                return value
    high_threat_ids = _high_threat_ids(truth_summary)
    if high_threat_ids:
        return len(high_threat_ids)
    high_threat_by_time = _high_threat_by_timestamp(truth_summary)
    if high_threat_by_time:
        return max(len(values) for values in high_threat_by_time.values())
    if metrics.target_count > 0:
        return metrics.target_count
    if metrics.intercept_success_count > 0:
        return metrics.intercept_success_count
    return 0


def _has_partial_progress(metrics: EpisodeMetrics) -> bool:
    return any(
        (
            metrics.detection_probability is not None
            and metrics.detection_probability > 0.0,
            metrics.track_continuity > 0.0,
            metrics.terminal_lock_count > 0,
            metrics.visual_png_switch_count > 0,
            metrics.degraded_completion_rate > 0.0,
        )
    )


def _default_success_reason(
    outcome: str,
    metrics: EpisodeMetrics,
    required_success_count: int,
) -> str:
    if outcome == "success":
        if required_success_count > 0:
            return (
                "intercept_success_count="
                f"{metrics.intercept_success_count}/{required_success_count}"
            )
        return "success_evidence_recorded"
    if outcome == "partial":
        if metrics.intercept_success_count > 0 and required_success_count > 0:
            return (
                "partial_intercept_success_count="
                f"{metrics.intercept_success_count}/{required_success_count}"
            )
        if metrics.terminal_lock_count > 0:
            return f"terminal_lock_count={metrics.terminal_lock_count}"
        if metrics.detection_probability is not None and metrics.detection_probability > 0.0:
            return f"detection_probability={metrics.detection_probability:.6g}"
    return ""


def _default_failure_reason(
    outcome: str,
    root_cause: str,
    top_failure_causes: Sequence[Mapping[str, Any]],
) -> str:
    if not top_failure_causes:
        if outcome == "aborted":
            return "mission_aborted_without_structured_root_cause"
        return "no_success_evidence"
    details = top_failure_causes[0].get("details", [])
    detail_text = ""
    if isinstance(details, Sequence) and details:
        detail_text = f": {details[0]}"
    return f"{root_cause}{detail_text}"


def _normalize_failure_cause(value: Any) -> str | None:
    text = _normalized_label(value)
    if not text:
        return None
    aliases = {
        "track": "tracking",
        "tracking_failure": "tracking",
        "association": "assignment",
        "assignment_failure": "assignment",
        "terminal": "terminal_gate",
        "terminal_gate_failure": "terminal_gate",
        "terminal_contract": "terminal_gate",
        "gate": "terminal_gate",
        "camera_gate": "terminal_gate",
        "guidance_failure": "guidance",
        "intercept": "guidance",
        "intercept_failure": "guidance",
        "secondary_coverage": "coverage",
        "coverage_gap": "coverage",
        "runtime": "runtime_exception",
        "exception": "runtime_exception",
        "runtime_error": "runtime_exception",
        "latency": "performance",
        "performance_budget": "performance",
        "comms": "communication",
        "comm": "communication",
    }
    normalized = aliases.get(text, text)
    allowed = {
        "tracking",
        "assignment",
        "terminal_gate",
        "guidance",
        "coverage",
        "runtime_exception",
        "communication",
        "safety",
        "performance",
    }
    if normalized in allowed:
        return normalized
    for token in allowed:
        if token in normalized:
            return token
    return normalized


def _eval_tracking_text(
    truth_summary: Mapping[str, Any],
    keys: Sequence[str],
    *,
    default: str,
) -> str:
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in keys:
            value = _metadata_text(mapping, key)
            if value is not None:
                return value
    return default


_SECONDARY_NODE_TYPE_KEYS = (
    "secondary_node_type",
    "node_type",
    "camera_node_type",
    "sensor_node_type",
    "platform_role",
    "sensor_role",
    "camera_role",
    "view_node_type",
    "source_node_type",
    "observer_type",
)

_SECONDARY_SENSING_METADATA_KEYS = {
    "secondary_network_joint_full_view_frame_rate",
    "secondary_network_mean_coverage_ratio",
    "secondary_single_camera_full_view_frame_rate",
    "cross_view_association_count",
    "secondary_detect_available_but_not_registered_count",
    "covered_target_ids",
    "visible_target_ids",
    "detected_target_ids",
    "full_view_target_ids",
    "covered_target_count",
    "visible_target_count",
    "detected_target_count",
    "coverage_ratio",
    "secondary_coverage_ratio",
    "network_coverage_ratio",
    "joint_full_view",
    "network_joint_full_view",
    "single_camera_full_view",
    "single_camera_full_view_count",
    "detect_available",
    "detection_available",
    "secondary_detect_available",
    "registration_success",
    "d5_registered",
    "cue_pointing_error_deg",
    "cue_pointing_error_rad",
    "gimbal_pointing_error_deg",
    "gimbal_pointing_error_rad",
    "pointing_error_deg",
    "pointing_error_rad",
}


def _secondary_node_type(
    metadata: Mapping[str, Any],
    *,
    fallback_text: str = "",
) -> str | None:
    for key in _SECONDARY_NODE_TYPE_KEYS:
        value = _metadata_text(metadata, key)
        normalized = _normalize_secondary_node_type(value)
        if normalized is not None:
            return normalized

    for key in ("camera_id", "camera_name", "source_node_id", "resource_id"):
        value = _metadata_text(metadata, key)
        normalized = _normalize_secondary_node_type(value)
        if normalized is not None:
            return normalized
    return _normalize_secondary_node_type(fallback_text)


def _normalize_secondary_node_type(value: Any) -> str | None:
    text = _state(str(value or "")).replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if "fixed_downlook_secondary" in text:
        return "fixed_downlook_secondary"
    if "mobile_recon_gimbal" in text:
        return "mobile_recon_gimbal"
    if "fixed" in text and ("downlook" in text or "down_look" in text):
        return "fixed_downlook_secondary"
    if "secondary" in text and ("downlook" in text or "down_look" in text):
        return "fixed_downlook_secondary"
    if "mobile" in text and ("recon" in text or "gimbal" in text):
        return "mobile_recon_gimbal"
    if "recon" in text and "gimbal" in text:
        return "mobile_recon_gimbal"
    if "gimbal" in text:
        return "mobile_recon_gimbal"
    if "secondary" in text:
        return "secondary_network"
    return None


def _secondary_sample_target_count(
    metadata: Mapping[str, Any],
    *,
    default_target_count: int,
) -> int:
    explicit = _first_metadata_int(
        metadata,
        (
            "target_count",
            "truth_count",
            "total_target_count",
            "expected_target_count",
            "target_object_count",
        ),
    )
    if explicit is not None and explicit > 0:
        return explicit
    return max(0, int(default_target_count or 0))


def _secondary_sample_camera_count(
    metadata: Mapping[str, Any],
    *,
    default_camera_count: int,
) -> int:
    explicit = _first_metadata_int(
        metadata,
        (
            "camera_count",
            "secondary_camera_count",
            "single_camera_total_count",
            "camera_frame_count",
            "single_camera_frame_count",
        ),
    )
    if explicit is not None and explicit > 0:
        return explicit
    return max(0, int(default_camera_count or 0))


def _secondary_coverage_sample(
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    target_ids = _metadata_id_set(
        metadata,
        (
            "covered_target_ids",
            "visible_target_ids",
            "detected_target_ids",
            "full_view_target_ids",
            "target_ids",
        ),
    )
    covered_count = _first_metadata_int(
        metadata,
        (
            "covered_target_count",
            "visible_target_count",
            "detected_target_count",
            "secondary_visible_target_count",
            "network_covered_target_count",
            "joint_covered_target_count",
            "full_view_target_count",
        ),
    )
    coverage_ratio = _first_metadata_float(
        metadata,
        (
            "coverage_ratio",
            "secondary_coverage_ratio",
            "network_coverage_ratio",
            "joint_coverage_ratio",
            "mean_coverage_ratio",
            "secondary_network_mean_coverage_ratio",
        ),
    )
    full_view = _secondary_bool_value(
        metadata,
        (
            "network_joint_full_view",
            "joint_full_view",
            "full_view",
            "full_coverage",
            "all_targets_visible",
            "all_targets_in_fov",
            "secondary_network_joint_full_view",
        ),
    )
    if (
        not target_ids
        and covered_count is None
        and coverage_ratio is None
        and full_view is None
    ):
        return None
    return {
        "target_ids": target_ids,
        "covered_count": None if covered_count is None else max(0, covered_count),
        "coverage_ratio": (
            None if coverage_ratio is None else _clamp_ratio(coverage_ratio)
        ),
        "full_view": full_view,
    }


def _secondary_frame_key(sample: Mapping[str, Any]) -> tuple[Any, ...]:
    metadata = sample["metadata"]
    frame_id = (
        metadata.get("secondary_frame_id")
        or metadata.get("frame_id")
        or metadata.get("frame_index")
        or metadata.get("timestamp")
        or sample.get("timestamp")
    )
    return (frame_id,)


def _add_secondary_frame_coverage(
    frames: dict[tuple[Any, ...], dict[str, Any]],
    frame_key: tuple[Any, ...],
    coverage: Mapping[str, Any],
    target_count: int,
) -> None:
    frame = frames.setdefault(
        frame_key,
        {
            "target_count": max(0, int(target_count or 0)),
            "target_ids": set(),
            "covered_count": None,
            "coverage_ratios": [],
            "full_view_values": [],
        },
    )
    if target_count > 0 and not frame["target_count"]:
        frame["target_count"] = int(target_count)
    frame["target_ids"].update(coverage.get("target_ids", set()))
    covered_count = coverage.get("covered_count")
    if covered_count is not None:
        previous = frame.get("covered_count")
        frame["covered_count"] = max(int(previous or 0), int(covered_count))
    coverage_ratio = coverage.get("coverage_ratio")
    if coverage_ratio is not None:
        frame["coverage_ratios"].append(_clamp_ratio(float(coverage_ratio)))
    full_view = coverage.get("full_view")
    if full_view is not None:
        frame["full_view_values"].append(bool(full_view))


def _secondary_frame_stats(
    frames: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> dict[str, float | int]:
    coverage_ratios: list[float] = []
    full_view_values: list[bool] = []
    for frame in frames.values():
        ratio = _secondary_frame_coverage_ratio(frame)
        if ratio is not None:
            coverage_ratios.append(ratio)
        full_view = _secondary_frame_full_view(frame, ratio)
        if full_view is not None:
            full_view_values.append(full_view)
    return {
        "full_view_frame_rate": _bool_rate(full_view_values),
        "mean_coverage_ratio": _mean(coverage_ratios),
        "frame_count": len(frames),
    }


def _secondary_frame_coverage_ratio(frame: Mapping[str, Any]) -> float | None:
    target_count = int(frame.get("target_count") or 0)
    target_ids = frame.get("target_ids", set())
    if target_count > 0 and target_ids:
        return _clamp_ratio(len(target_ids) / target_count)
    covered_count = frame.get("covered_count")
    if target_count > 0 and covered_count is not None:
        return _clamp_ratio(float(covered_count) / target_count)
    ratios = frame.get("coverage_ratios", [])
    if ratios:
        return _clamp_ratio(max(float(value) for value in ratios))
    return None


def _secondary_frame_full_view(
    frame: Mapping[str, Any],
    coverage_ratio: float | None,
) -> bool | None:
    if coverage_ratio is not None:
        return coverage_ratio >= 1.0
    values = frame.get("full_view_values", [])
    if values:
        return any(bool(value) for value in values)
    return None


def _secondary_single_camera_counts(
    metadata: Mapping[str, Any],
    coverage: Mapping[str, Any] | None,
    *,
    sample_target_count: int,
    sample_camera_count: int,
) -> tuple[int, int]:
    full_count = _first_metadata_int(
        metadata,
        (
            "single_camera_full_view_count",
            "secondary_single_camera_full_view_count",
            "camera_full_view_count",
        ),
    )
    if full_count is not None:
        total_count = _first_metadata_int(
            metadata,
            (
                "single_camera_total_count",
                "single_camera_frame_count",
                "camera_frame_count",
                "secondary_camera_count",
                "camera_count",
            ),
        )
        if total_count is None or total_count <= 0:
            total_count = sample_camera_count or full_count
        return max(0, full_count), max(max(0, full_count), int(total_count))

    single_full = _secondary_bool_value(
        metadata,
        (
            "single_camera_full_view",
            "camera_full_view",
            "secondary_single_camera_full_view",
        ),
    )
    if single_full is not None:
        return int(single_full), 1

    camera_id = _metadata_text(metadata, "camera_id") or _metadata_text(
        metadata,
        "camera_name",
    )
    if camera_id is None or coverage is None:
        return 0, 0

    ratio = _secondary_coverage_ratio_from_sample(coverage, sample_target_count)
    if ratio is not None:
        return int(ratio >= 1.0), 1
    full_view = coverage.get("full_view")
    if full_view is not None:
        return int(bool(full_view)), 1
    return 0, 0


def _secondary_coverage_ratio_from_sample(
    coverage: Mapping[str, Any],
    target_count: int,
) -> float | None:
    target_ids = coverage.get("target_ids", set())
    if target_count > 0 and target_ids:
        return _clamp_ratio(len(target_ids) / target_count)
    covered_count = coverage.get("covered_count")
    if target_count > 0 and covered_count is not None:
        return _clamp_ratio(float(covered_count) / target_count)
    coverage_ratio = coverage.get("coverage_ratio")
    if coverage_ratio is not None:
        return _clamp_ratio(float(coverage_ratio))
    return None


def _metadata_id_set(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> set[str]:
    for key in keys:
        if key not in metadata:
            continue
        values = _id_values(metadata[key])
        if values:
            return values
    return set()


def _id_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        ids: set[str] = set()
        for key in ("target_id", "truth_id", "global_track_id", "object_id", "id"):
            if key in value and value[key] is not None:
                ids.add(str(value[key]))
        if ids:
            return ids
        return {str(key) for key in value if str(key).strip()}
    if isinstance(value, (list, tuple, set)):
        ids: set[str] = set()
        for item in value:
            ids.update(_id_values(item))
        return ids
    text = str(value).strip()
    if not text:
        return set()
    if "," in text:
        return {item.strip() for item in text.split(",") if item.strip()}
    return {text}


def _metadata_angle_values_deg(
    metadata: Mapping[str, Any],
    *,
    degree_keys: Sequence[str],
    radian_keys: Sequence[str],
) -> list[float]:
    values: list[float] = []
    for key in degree_keys:
        if key in metadata:
            values.extend(_metadata_float_values(metadata[key]))
    for key in radian_keys:
        if key in metadata:
            values.extend(
                math.degrees(value) for value in _metadata_float_values(metadata[key])
            )
    return values


def _metadata_float_values(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("value", "error", "angle", "mean"):
            if key in value:
                return _metadata_float_values(value[key])
        return []
    if isinstance(value, (list, tuple, set)):
        values: list[float] = []
        for item in value:
            values.extend(_metadata_float_values(item))
        return values
    if isinstance(value, str) and "," in value:
        values: list[float] = []
        for item in value.split(","):
            values.extend(_metadata_float_values(item.strip()))
        return values
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def _angle_error_stats(values: Sequence[float]) -> dict[str, float | int]:
    magnitudes = [abs(float(value)) for value in values]
    if not magnitudes:
        return {"count": 0, "mean": 0.0, "rmse": 0.0, "max": 0.0}
    return {
        "count": len(magnitudes),
        "mean": _mean(magnitudes),
        "rmse": math.sqrt(sum(value * value for value in magnitudes) / len(magnitudes)),
        "max": max(magnitudes),
    }


def _secondary_bool_value(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> bool | None:
    for key in keys:
        if key in metadata:
            return _as_bool(metadata[key], default=False)
    return None


def _first_metadata_int(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> int | None:
    for key in keys:
        if key in metadata:
            value = _optional_int_value(metadata[key])
            if value is not None:
                return value
    return None


def _clamp_ratio(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _metric_scope_from_truth_summary(truth_summary: Mapping[str, Any]) -> str:
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in (
            "metric_scope",
            "metrics_scope",
            "evaluation_scope",
            "metrics_kind",
            "source_scope",
        ):
            if key in mapping and mapping[key] is not None:
                return _normalize_metric_scope(mapping[key])
        for key in ("source_path", "metrics_path", "metrics_file"):
            if key in mapping and mapping[key] is not None:
                scoped = _normalize_metric_scope(mapping[key])
                if scoped != "not_recorded":
                    return scoped
    return "not_recorded"


def _scenario_version_from_sources(
    truth_summary: Mapping[str, Any],
    records: Sequence[EventRecord],
) -> str:
    keys = (
        "scenario_version",
        "scenario_config_version",
        "scenario_schema_version",
        "scenario_definition_version",
        "config_version",
    )
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in keys:
            value = _metadata_text(mapping, key)
            if value is not None:
                return value
    for record in records:
        for key in keys:
            value = _metadata_text(record.metadata, key)
            if value is not None:
                return value
    return ""


def _standard_mapping_version_from_sources(
    truth_summary: Mapping[str, Any],
    records: Sequence[EventRecord],
) -> str:
    keys = (
        "standard_mapping_version",
        "standard_metric_mapping_version",
        "cuas_standard_mapping_version",
    )
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in keys:
            value = _metadata_text(mapping, key)
            if value == STANDARD_MAPPING_VERSION:
                return value
    for record in records:
        for key in keys:
            value = _metadata_text(record.metadata, key)
            if value == STANDARD_MAPPING_VERSION:
                return value
    return STANDARD_MAPPING_VERSION


def _normalize_metric_scope(value: Any) -> str:
    text = _state(str(value or ""))
    if not text:
        return "not_recorded"
    normalized = text.replace("-", "_").replace(" ", "_")
    if "contract" in normalized:
        return "contract"
    if (
        normalized in {"exec", "executed", "execution", "runtime", "actual"}
        or "execution" in normalized
    ):
        return "execution"
    if "main_episode_bus_metrics" in normalized:
        return "execution"
    return normalized


def _active_degradation_review_label(record: EventRecord) -> str | None:
    metadata = record.metadata
    for key in (
        "review_label",
        "active_degradation_review_label",
        "degradation_review_label",
        "active_degradation_label",
    ):
        label = _metadata_text(metadata, key)
        if label is not None:
            return _normalized_label(label)

    for key in (
        "active_degradation_necessary",
        "degradation_necessary",
        "necessary_active_degradation",
        "was_necessary",
    ):
        if key in metadata:
            necessary = _as_bool(metadata[key], default=False)
            return "necessary" if necessary else "unnecessary"

    for key in (
        "post_window_outcome",
        "post_active_outcome",
        "active_degradation_outcome",
        "review_outcome",
    ):
        label = _metadata_text(metadata, key)
        if label is not None:
            return _normalized_label(label)

    risk_reduction = _active_degradation_risk_reduction(metadata)
    if risk_reduction is not None:
        return "risk_reduced" if risk_reduction > 0.0 else "no_risk_reduction"
    return None


def _active_degradation_review_class(label: str | None) -> str | None:
    if label is None:
        return None
    normalized = _normalized_label(label)
    necessary_labels = {
        "necessary",
        "needed",
        "required",
        "warranted",
        "justified",
        "true_positive",
        "tp",
        "useful",
        "beneficial",
        "improved",
        "stabilized",
        "stabilised",
        "risk_reduced",
        "coverage_restored",
        "reassign_completed",
        "secondary_takeover_success",
        "prevented_failover",
    }
    unnecessary_labels = {
        "unnecessary",
        "not_needed",
        "unneeded",
        "false_positive",
        "fp",
        "avoidable",
        "spurious",
        "no_improvement",
        "unchanged",
        "worse",
        "failed",
        "no_risk_reduction",
    }
    if normalized in necessary_labels:
        return "necessary"
    if normalized in unnecessary_labels:
        return "unnecessary"
    return None


def _normalized_label(value: Any) -> str:
    return _state(str(value)).replace("-", "_").replace(" ", "_")


def _active_degradation_risk_reduction(metadata: Mapping[str, Any]) -> float | None:
    for key in (
        "risk_reduction",
        "risk_reduction_score",
        "post_window_risk_reduction",
        "coverage_gap_reduction",
    ):
        value = _metadata_float_if_present(metadata, key)
        if value is not None:
            return value

    pre_risk = _first_metadata_float(
        metadata,
        (
            "pre_window_risk_score",
            "pre_active_risk_score",
            "risk_score_before",
            "pre_window_coverage_gap_count",
        ),
    )
    post_risk = _first_metadata_float(
        metadata,
        (
            "post_window_risk_score",
            "post_active_risk_score",
            "risk_score_after",
            "post_window_coverage_gap_count",
        ),
    )
    if pre_risk is None or post_risk is None:
        return None
    return pre_risk - post_risk


def _first_metadata_float(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> float | None:
    for key in keys:
        value = _metadata_float_if_present(metadata, key)
        if value is not None:
            return value
    return None


def _governance_payload(metadata: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "provenance",
        "latency_audit",
        "latency_audit_summary",
        "region_quality",
        "region_quality_summary",
        "risk_summary",
        "consistency_summary",
        "false_track_summary",
        "assignment_summary",
        "mismatch_replay_summary",
        "feedback_summary",
        "feedback_profile_summary",
    ):
        nested = metadata.get(key)
        if isinstance(nested, Mapping):
            payload.update(nested)
    payload.update(metadata)
    return payload


def _governance_value(
    payload: Mapping[str, Any],
    keys: Sequence[str],
) -> float | None:
    return _first_metadata_float(payload, keys)


def _governance_sum(
    payloads: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    *,
    sum_all_present_keys: bool = False,
) -> float | None:
    values: list[float] = []
    for payload in payloads:
        if sum_all_present_keys:
            values.extend(
                value
                for key in keys
                for value in [_metadata_float(payload, key)]
                if value is not None
            )
            continue
        value = _governance_value(payload, keys)
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def _governance_max(
    payloads: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
) -> float | None:
    values = [
        value
        for payload in payloads
        for value in [_governance_value(payload, keys)]
        if value is not None
    ]
    return max(values) if values else None


def _governance_weighted_mean(
    payloads: Sequence[Mapping[str, Any]],
    value_keys: Sequence[str],
    weight_keys: Sequence[str],
) -> float | None:
    weighted_sum = 0.0
    weight_sum = 0.0
    unweighted_values: list[float] = []
    for payload in payloads:
        value = _governance_value(payload, value_keys)
        if value is None:
            continue
        unweighted_values.append(value)
        weight = _governance_value(payload, weight_keys)
        if weight is not None and weight > 0:
            weighted_sum += value * weight
            weight_sum += weight
    if weight_sum > 0:
        return weighted_sum / weight_sum
    return _mean(unweighted_values) if unweighted_values else None


def _governance_rate(
    payloads: Sequence[Mapping[str, Any]],
    numerator_keys: Sequence[str],
    denominator_keys: Sequence[str],
    explicit_rate_keys: Sequence[str],
) -> float | None:
    numerator = _governance_sum(payloads, numerator_keys)
    denominator = _governance_sum(payloads, denominator_keys)
    count_rate = _ratio_or_none(numerator, denominator)
    if count_rate is not None:
        return count_rate
    rates = [
        value
        for payload in payloads
        for value in [_governance_value(payload, explicit_rate_keys)]
        if value is not None
    ]
    return _mean(rates) if rates else None


def _ratio_or_none(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def _governance_profile_summary(
    payloads: Sequence[Mapping[str, Any]],
    *,
    profile_keys: Sequence[str],
    version_keys: Sequence[str],
) -> dict[str, list[str]]:
    profiles = {
        value
        for payload in payloads
        for key in profile_keys
        for value in [_metadata_text(payload, key)]
        if value is not None
    }
    versions = {
        value
        for payload in payloads
        for key in version_keys
        for value in [_metadata_text(payload, key)]
        if value is not None
    }
    return {"profiles": sorted(profiles), "versions": sorted(versions)}


def _d3_nm_case_counts(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for payload in payloads:
        resources = _governance_value(payload, ("resource_count",))
        targets = _governance_value(payload, ("target_count",))
        if resources is None or targets is None:
            continue
        if resources < targets:
            counts["resource_limited"] += 1
        elif resources > targets:
            counts["resource_surplus"] += 1
        else:
            counts["balanced"] += 1
    return dict(counts)


def _metadata_float_if_present(metadata: Mapping[str, Any], key: str) -> float | None:
    if key not in metadata or metadata[key] is None:
        return None
    try:
        return float(metadata[key])
    except (TypeError, ValueError):
        return None


def _state(value: str | None) -> str:
    return (value or "").strip().lower()


def _intercept_pair_key(record: EventRecord) -> tuple[str, str] | None:
    resource_id = (
        _metadata_text(record.metadata, "resource_id")
        or _metadata_text(record.metadata, "vehicle_name")
        or record.actor_id
    )
    target_id = _metadata_text(record.metadata, "target_id") or _metadata_text(
        record.metadata,
        "global_track_id",
    )
    if resource_id is None and target_id is None:
        return None
    return (str(resource_id or ""), str(target_id or ""))


def _physical_intercept_availability(
    summary_metadata: Mapping[str, Any],
    *,
    default_available: bool,
) -> tuple[bool, str | None]:
    runtime_mode = _state(_metadata_text(summary_metadata, "runtime_mode"))
    if "computer_vision" in runtime_mode or runtime_mode == "computervision":
        return False, "ComputerVision episodes do not provide physical intercept evidence"
    explicit = _first_metadata_bool(
        summary_metadata,
        ("physical_intercept_available",),
    )
    if explicit is False:
        return False, (
            _metadata_text(summary_metadata, "physical_intercept_unavailable_reason")
            or "physical intercept evidence was marked unavailable"
        )
    if explicit is True:
        return True, None
    if default_available:
        return True, None
    return False, "no collision/range physical intercept evidence"


def _layered_physical_success_metrics(
    *,
    pair_events: Sequence[EventRecord],
    command_events: Sequence[EventRecord],
    summary_metadata: Mapping[str, Any],
    physical_available: bool,
) -> dict[str, Any]:
    criteria = {
        "intercept_radius_m": _metadata_float(summary_metadata, "intercept_radius_m"),
        "distance_frame": _metadata_text(summary_metadata, "intercept_distance_frame"),
        "distance_dimension": _metadata_text(
            summary_metadata,
            "intercept_distance_dimension",
        ),
        "criteria_version": _metadata_text(
            summary_metadata,
            "intercept_success_criteria_version",
        ),
    }
    criteria_complete = all(value is not None for value in criteria.values())
    criteria_matches_5m_ned_3d = bool(
        criteria_complete
        and math.isclose(float(criteria["intercept_radius_m"]), 5.0)
        and _state(str(criteria["distance_frame"])) == "ned"
        and _state(str(criteria["distance_dimension"]))
        in {"3d", "3d_euclidean", "ned_3d_euclidean"}
    )
    metadata: dict[str, Any] = {
        "physical_success_criteria": criteria,
        "physical_success_criteria_complete": criteria_complete,
        "physical_success_criteria_matches_5m_ned_3d": criteria_matches_5m_ned_3d,
    }
    metric_names = (
        "pair_physical_success_count",
        "pair_physical_success_rate",
        "target_intercept_success_count",
        "target_intercept_success_rate",
        "coalition_completion_count",
        "coalition_completion_rate",
    )
    if not physical_available:
        return {**{name: None for name in metric_names}, "_metadata": metadata}

    pair_rows = _physical_pair_rows(pair_events, command_events)
    participating = [row for row in pair_rows if _active_assigned_pair(row)]
    successful = [row for row in participating if _physical_success(row)]
    pair_opportunities = len(participating)
    pair_success_count = len(successful)

    target_ids = {
        target_id
        for row in participating
        for target_id in [_metadata_text(row, "target_id")]
        if target_id is not None
    }
    successful_target_ids = {
        target_id
        for row in successful
        for target_id in [_metadata_text(row, "target_id")]
        if target_id is not None
    }

    if not pair_rows:
        pair_success_count = _metadata_int(
            summary_metadata,
            "pair_physical_success_count",
        )
        pair_opportunities = _metadata_int(
            summary_metadata,
            "pair_physical_opportunity_count",
        )
        target_success_count = _metadata_int(
            summary_metadata,
            "target_intercept_success_count",
        )
        target_opportunities = _metadata_int(
            summary_metadata,
            "target_intercept_opportunity_count",
        )
    else:
        target_success_count = len(successful_target_ids)
        target_opportunities = len(target_ids)

    coalition = _coalition_completion_metrics(
        participating,
        summary_metadata=summary_metadata,
    )
    metadata.update(
        {
            "pair_physical_opportunity_count": pair_opportunities,
            "target_intercept_opportunity_count": target_opportunities,
            "successful_target_ids": sorted(successful_target_ids),
            **coalition.pop("_metadata"),
        }
    )
    return {
        "pair_physical_success_count": pair_success_count,
        "pair_physical_success_rate": _optional_rate(
            pair_success_count,
            pair_opportunities,
        ),
        "target_intercept_success_count": target_success_count,
        "target_intercept_success_rate": _optional_rate(
            target_success_count,
            target_opportunities,
        ),
        **coalition,
        "_metadata": metadata,
    }


def _physical_pair_rows(
    pair_events: Sequence[EventRecord],
    command_events: Sequence[EventRecord],
) -> list[Mapping[str, Any]]:
    if pair_events:
        return [record.metadata for record in pair_events]
    grouped: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    for record in command_events:
        key = _intercept_pair_key(record)
        if key is not None:
            grouped[key].append(record)
    rows: list[Mapping[str, Any]] = []
    for records in grouped.values():
        ordered = sorted(records, key=lambda item: item.timestamp)
        row = dict(ordered[-1].metadata)
        row.setdefault("resource_id", ordered[-1].actor_id)
        collision_seen = any(
            _bool_from_metadata(
                record.metadata,
                ("collision_seen", "target_collision_seen"),
                default=False,
            )
            for record in ordered
        )
        if collision_seen:
            row["status"] = "collision_intercept"
        rows.append(row)
    return rows


def _active_assigned_pair(metadata: Mapping[str, Any]) -> bool:
    assigned = _first_metadata_bool(metadata, ("assigned", "assignment_active"))
    if assigned is False:
        return False
    activation_state = _state(_metadata_text(metadata, "activation_state"))
    if activation_state in {
        "standby",
        "standby_reserve",
        "reserve",
        "inactive",
        "not_activated",
        "cancelled",
    }:
        return False
    return True


def _physical_success(metadata: Mapping[str, Any]) -> bool:
    explicit = _first_metadata_bool(metadata, ("physical_success", "physical_intercept"))
    if explicit is not None:
        return explicit
    return _state(_metadata_text(metadata, "status")) in {
        "collision_intercept",
        "range_intercept",
    }


def _coalition_completion_metrics(
    participating: Sequence[Mapping[str, Any]],
    *,
    summary_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    by_target: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in participating:
        target_id = _metadata_text(row, "target_id")
        if target_id is not None:
            by_target[target_id].append(row)

    coalition_targets: dict[str, tuple[int, list[Mapping[str, Any]]]] = {}
    for target_id, rows in by_target.items():
        explicit_required = [
            value
            for row in rows
            for value in [_metadata_int(row, "required_primary_count")]
            if value is not None
        ]
        explicitly_required_rows = [
            row
            for row in rows
            if _first_metadata_bool(row, ("required_primary",)) is True
        ]
        primary_rows = explicitly_required_rows or [
            row for row in rows if _state(_metadata_text(row, "member_role")) == "primary"
        ]
        required_count = max(explicit_required) if explicit_required else len(primary_rows)
        if required_count > 1:
            coalition_targets[target_id] = (required_count, primary_rows)

    if not coalition_targets:
        explicit_opportunities = _metadata_int(
            summary_metadata,
            "coalition_opportunity_count",
        )
        explicit_count = _metadata_int(
            summary_metadata,
            "coalition_completion_count",
        )
        window_enforced = _first_metadata_bool(
            summary_metadata,
            ("coalition_arrival_window_enforced",),
        )
        if explicit_opportunities is not None and window_enforced is True:
            return {
                "coalition_completion_count": explicit_count or 0,
                "coalition_completion_rate": _optional_rate(
                    explicit_count or 0,
                    explicit_opportunities,
                ),
                "_metadata": {
                    "coalition_opportunity_count": explicit_opportunities,
                    "coalition_completion_availability": "available",
                    "coalition_completion_source": "summary",
                },
            }
        return {
            "coalition_completion_count": 0,
            "coalition_completion_rate": None,
            "_metadata": {
                "coalition_opportunity_count": 0,
                "coalition_completion_availability": "no_coalition_opportunity",
            },
        }

    completed_targets: list[str] = []
    missing_window_targets: list[str] = []
    for target_id, (required_count, primary_rows) in coalition_targets.items():
        if len(primary_rows) < required_count:
            continue
        required_rows = primary_rows[:required_count]
        if any(_arrival_window(row) is None for row in required_rows):
            missing_window_targets.append(target_id)
            continue
        if all(
            _physical_success(row) and _inside_arrival_window(row)
            for row in required_rows
        ):
            completed_targets.append(target_id)

    metadata = {
        "coalition_opportunity_count": len(coalition_targets),
        "completed_coalition_target_ids": sorted(completed_targets),
        "coalition_missing_arrival_window_target_ids": sorted(missing_window_targets),
        "coalition_completion_source": "pair_summary",
    }
    if missing_window_targets:
        metadata["coalition_completion_availability"] = "unavailable"
        metadata["coalition_completion_unavailable_reason"] = (
            "required primary arrival window evidence is incomplete"
        )
        return {
            "coalition_completion_count": None,
            "coalition_completion_rate": None,
            "_metadata": metadata,
        }
    metadata["coalition_completion_availability"] = "available"
    return {
        "coalition_completion_count": len(completed_targets),
        "coalition_completion_rate": len(completed_targets) / len(coalition_targets),
        "_metadata": metadata,
    }


def _arrival_window(metadata: Mapping[str, Any]) -> tuple[float, float] | None:
    start = _metadata_float(metadata, "arrival_window_start_s")
    end = _metadata_float(metadata, "arrival_window_end_s")
    raw_window = metadata.get("arrival_window")
    if (start is None or end is None) and isinstance(raw_window, Mapping):
        start = _optional_float_value(
            raw_window.get("start_s", raw_window.get("start"))
        )
        end = _optional_float_value(raw_window.get("end_s", raw_window.get("end")))
    elif (
        (start is None or end is None)
        and isinstance(raw_window, Sequence)
        and not isinstance(raw_window, (str, bytes))
        and len(raw_window) >= 2
    ):
        start = _optional_float_value(raw_window[0])
        end = _optional_float_value(raw_window[1])
    if start is None or end is None or end < start:
        return None
    return (start, end)


def _inside_arrival_window(metadata: Mapping[str, Any]) -> bool:
    window = _arrival_window(metadata)
    arrival = _first_metadata_float(
        metadata,
        ("arrival_timestamp_s", "time_to_intercept_s"),
    )
    return bool(window is not None and arrival is not None and window[0] <= arrival <= window[1])


def _optional_rate(
    numerator: int | None,
    denominator: int | None,
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _terminal_filter_state(metadata: Mapping[str, Any]) -> str | None:
    value = _first_metadata_text(
        metadata,
        (
            "terminal_filter_state",
            "image_kf_mode",
            "terminal_delivery_state",
        ),
    )
    return _state(value) if value is not None else None


def _terminal_filter_reason(metadata: Mapping[str, Any]) -> str | None:
    return _normalized_reason(
        _first_metadata_text(
            metadata,
            (
                "terminal_filter_reason",
                "terminal_delivery_reason",
                "image_kf_reason",
            ),
        )
    )


def _first_metadata_text(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> str | None:
    for key in keys:
        value = _metadata_text(metadata, key)
        if value is not None:
            return value
    return None


def _normalized_reason(value: str | None) -> str | None:
    if value is None:
        return None
    return _state(value).replace("-", "_").replace(" ", "_")


def _terminal_diagnostic_flag(
    metadata: Mapping[str, Any],
    flag_keys: Sequence[str],
    *,
    reason_tokens: Sequence[str],
) -> bool | None:
    value = _first_metadata_bool(metadata, flag_keys)
    if value is not None:
        return value
    reasons = " ".join(
        value
        for value in (
            _normalized_reason(_metadata_text(metadata, key))
            for key in (
                "terminal_filter_reason",
                "terminal_delivery_reason",
                "image_kf_reason",
                "ttc_reject_reason",
                "ttc_area_reject_reason",
            )
        )
        if value is not None
    )
    if reasons and any(token in reasons for token in reason_tokens):
        return True
    return None


def _accumulate_reason_metric(
    metadata: Mapping[str, Any],
    reason: str | None,
    *,
    metric_name: str,
    flag_keys: Sequence[str],
    reason_tokens: Sequence[str],
    evidence: dict[str, bool],
    counts: dict[str, int],
) -> None:
    explicit = _first_metadata_bool(metadata, flag_keys)
    if explicit is not None:
        evidence[metric_name] = True
        counts[metric_name] += int(explicit)
        return
    if reason is not None:
        evidence[metric_name] = True
        counts[metric_name] += int(any(token in reason for token in reason_tokens))


def _soft_prediction_active(
    metadata: Mapping[str, Any],
    state: str | None,
) -> bool | None:
    explicit = _first_metadata_bool(
        metadata,
        (
            "soft_prediction_active",
            "terminal_soft_prediction",
            "innovation_soft_prediction",
        ),
    )
    if explicit is not None:
        return explicit
    if state in {"soft_predict", "soft_prediction"}:
        return True
    if state is not None and any(
        key in metadata
        for key in (
            "soft_prediction_elapsed_s",
            "terminal_soft_prediction_elapsed_s",
        )
    ):
        return False
    return None


def _terminal_coast_active(
    metadata: Mapping[str, Any],
    state: str | None,
) -> bool | None:
    explicit = _first_metadata_bool(
        metadata,
        (
            "terminal_coast_active",
            "using_blind_push",
            "blind_push",
        ),
    )
    if explicit is not None:
        return explicit
    if state in {"blind_push", "coast", "coasting", "trend_coast"}:
        return True
    if state is not None and any(
        key in metadata
        for key in (
            "terminal_coast_elapsed_s",
            "coast_elapsed_s",
            "terminal_blind_elapsed_s",
            "blind_elapsed_s",
        )
    ):
        return False
    return None


def _visual_mode_active(metadata: Mapping[str, Any]) -> bool | None:
    explicit = _first_metadata_bool(
        metadata,
        ("visual_mode_active", "terminal_mode_entered"),
    )
    if explicit is not None:
        return explicit
    mode = _state(
        _first_metadata_text(metadata, ("mode", "guidance_mode")) or ""
    )
    if not mode:
        return None
    return mode in {
        "terminal",
        "vision_terminal",
        "terminal_guidance",
        "vision_terminal_guidance",
        "png_vm",
        "png_ttc",
        "visual_png",
    }


def _terminal_record_pair_key(record: EventRecord) -> tuple[str, str]:
    metadata = record.metadata
    resource = (
        _first_metadata_text(metadata, ("resource_id", "vehicle_name"))
        or record.actor_id
        or "__unknown_resource__"
    )
    target = _first_metadata_text(
        metadata,
        ("target_id", "global_track_id", "assigned_global_track_id"),
    ) or "__unknown_target__"
    return str(resource), str(target)


def _observed_state_duration(
    records: Sequence[EventRecord],
    *,
    state_predicate: Any,
    elapsed_keys: Sequence[str],
) -> float | None:
    by_pair: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    evidence = False
    for record in records:
        state = state_predicate(record.metadata)
        if state is not None:
            evidence = True
        if state is not None or any(key in record.metadata for key in elapsed_keys):
            by_pair[_terminal_record_pair_key(record)].append(record)
    if not evidence and not by_pair:
        return None

    total = 0.0
    for pair_records in by_pair.values():
        active_start: float | None = None
        elapsed_max = 0.0
        for record in sorted(pair_records, key=lambda item: item.timestamp):
            active = state_predicate(record.metadata)
            elapsed = _first_metadata_float(record.metadata, elapsed_keys)
            if active is True:
                if active_start is None:
                    active_start = record.timestamp
                    elapsed_max = 0.0
                if elapsed is not None:
                    elapsed_max = max(elapsed_max, max(0.0, elapsed))
            elif active is False and active_start is not None:
                total += max(elapsed_max, max(0.0, record.timestamp - active_start))
                active_start = None
                elapsed_max = 0.0
        if active_start is not None:
            last_timestamp = max(record.timestamp for record in pair_records)
            total += max(elapsed_max, max(0.0, last_timestamp - active_start))
    return total


def _terminal_lock_continuity(records: Sequence[EventRecord]) -> float | None:
    by_pair: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    for record in records:
        if "terminal_locked" in record.metadata:
            by_pair[_terminal_record_pair_key(record)].append(record)

    retained = 0
    opportunities = 0
    for pair_records in by_pair.values():
        previous: bool | None = None
        for record in sorted(pair_records, key=lambda item: item.timestamp):
            current = _first_metadata_bool(record.metadata, ("terminal_locked",))
            if previous is True and current is not None:
                opportunities += 1
                retained += int(current)
            previous = current
    if opportunities == 0:
        return None
    return retained / opportunities


def _command_discontinuities(
    records: Sequence[EventRecord],
) -> list[float] | None:
    explicit = [
        value
        for record in records
        for value in [
            _first_metadata_float(
                record.metadata,
                ("command_discontinuity_mps", "velocity_command_step_mps"),
            )
        ]
        if value is not None
    ]
    if explicit:
        return explicit

    by_pair: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    command_evidence = False
    for record in records:
        if any(
            key in record.metadata
            for key in ("command_vx_mps", "command_vy_mps", "command_vz_mps")
        ):
            command_evidence = True
            by_pair[_terminal_record_pair_key(record)].append(record)
    if not command_evidence:
        return None

    deltas: list[float] = []
    for pair_records in by_pair.values():
        previous: tuple[float, float, float] | None = None
        for record in sorted(pair_records, key=lambda item: item.timestamp):
            vx = _metadata_float(record.metadata, "command_vx_mps")
            vy = _metadata_float(record.metadata, "command_vy_mps")
            if vx is None or vy is None:
                continue
            vz = _metadata_float(record.metadata, "command_vz_mps") or 0.0
            current = (vx, vy, vz)
            if previous is not None:
                deltas.append(
                    math.sqrt(sum((value - old) ** 2 for value, old in zip(current, previous)))
                )
            previous = current
    return deltas if deltas else None


def _detect_coast_diagnostics(
    *,
    summary_events: Sequence[EventRecord],
    pair_events: Sequence[EventRecord],
    command_events: Sequence[EventRecord],
) -> dict[str, Any]:
    summary_metadata = summary_events[-1].metadata if summary_events else {}
    names = (
        "detection_acquisition_timeout_count",
        "image_kf_predict_count",
        "blind_push_count",
        "visual_reacquisition_count",
        "terminal_visual_lost_after_coast_count",
        "truth_identity_online_use_count",
    )
    result = {name: _metadata_int(summary_metadata, name) for name in names}

    if result["detection_acquisition_timeout_count"] is None and pair_events:
        timeout_pairs = {
            _intercept_pair_key(record)
            for record in pair_events
            if _state(_metadata_text(record.metadata, "abort_reason"))
            in {
                "terminal_detection_timeout",
                "detection_acquisition_timeout",
                "acquisition_timeout",
                "detection_timeout",
            }
        }
        result["detection_acquisition_timeout_count"] = len(timeout_pairs)

    if result["image_kf_predict_count"] is None:
        evidence = any(
            "image_kf_mode" in record.metadata or "image_kf_predict" in record.metadata
            for record in command_events
        )
        if evidence:
            result["image_kf_predict_count"] = sum(
                1
                for record in command_events
                if _first_metadata_bool(record.metadata, ("image_kf_predict",)) is True
                or _state(_metadata_text(record.metadata, "image_kf_mode")) == "predict"
                or _state(_metadata_text(record.metadata, "los_source")) == "image_kf_predict"
            )

    if result["blind_push_count"] is None:
        evidence = any(
            "using_blind_push" in record.metadata or "blind_push" in record.metadata
            for record in command_events
        )
        if evidence:
            result["blind_push_count"] = sum(
                1
                for record in command_events
                if _first_metadata_bool(
                    record.metadata,
                    ("using_blind_push", "blind_push"),
                )
                is True
            )

    if result["truth_identity_online_use_count"] is None:
        truth_records = [
            record
            for record in (*pair_events, *command_events)
            if "truth_identity_online_use" in record.metadata
        ]
        if truth_records:
            result["truth_identity_online_use_count"] = sum(
                1
                for record in truth_records
                if _first_metadata_bool(
                    record.metadata,
                    ("truth_identity_online_use",),
                )
                is True
            )

    explicit_reacquisition = [
        record
        for record in command_events
        if "visual_reacquisition" in record.metadata
    ]
    explicit_lost = [
        record
        for record in command_events
        if "terminal_visual_lost_after_coast" in record.metadata
    ]
    inferred_reacquisition, inferred_lost = _infer_detect_coast_transitions(command_events)
    if result["visual_reacquisition_count"] is None:
        result["visual_reacquisition_count"] = (
            sum(
                1
                for record in explicit_reacquisition
                if _first_metadata_bool(record.metadata, ("visual_reacquisition",)) is True
            )
            if explicit_reacquisition
            else inferred_reacquisition
        )
    if result["terminal_visual_lost_after_coast_count"] is None:
        result["terminal_visual_lost_after_coast_count"] = (
            sum(
                1
                for record in explicit_lost
                if _first_metadata_bool(
                    record.metadata,
                    ("terminal_visual_lost_after_coast",),
                )
                is True
            )
            if explicit_lost
            else inferred_lost
        )

    return {
        **result,
        "_metadata": {
            "detect_coast_diagnostic_availability": {
                name: "available" if result[name] is not None else "unavailable"
                for name in names
            }
        },
    }


def _infer_detect_coast_transitions(
    command_events: Sequence[EventRecord],
) -> tuple[int | None, int | None]:
    by_pair: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    for record in command_events:
        key = _intercept_pair_key(record)
        if key is not None:
            by_pair[key].append(record)
    detection_evidence = any(
        "detection_seen" in record.metadata for record in command_events
    )
    coast_evidence = any(_coast_active(record.metadata) for record in command_events)
    if not detection_evidence or not coast_evidence:
        return None, None

    reacquisition_count = 0
    lost_count = 0
    for records in by_pair.values():
        had_visual = False
        coasting_after_visual = False
        for record in sorted(records, key=lambda item: item.timestamp):
            detected = _first_metadata_bool(record.metadata, ("detection_seen",))
            if detected is True:
                if had_visual and coasting_after_visual:
                    reacquisition_count += 1
                had_visual = True
                coasting_after_visual = False
            elif detected is False and had_visual and _coast_active(record.metadata):
                coasting_after_visual = True
        if coasting_after_visual:
            lost_count += 1
    return reacquisition_count, lost_count


def _coast_active(metadata: Mapping[str, Any]) -> bool:
    if _first_metadata_bool(metadata, ("using_blind_push", "blind_push")) is True:
        return True
    states = (
        _metadata_text(metadata, "image_kf_mode"),
        _metadata_text(metadata, "los_source"),
        _metadata_text(metadata, "mode"),
        _metadata_text(metadata, "d5_state"),
    )
    return any(
        _state(state) in {
            "predict",
            "image_kf_predict",
            "coast",
            "coasting",
            "blind_push",
            "loss_hold",
        }
        for state in states
    )


def _terminal_takeover_from_metadata(metadata: Mapping[str, Any]) -> bool:
    if _bool_from_metadata(
        metadata,
        (
            "terminal_locked",
            "terminal_switch_allowed",
            "terminal_mode_entered",
            "terminal_takeover",
        ),
        default=False,
    ):
        return True
    mode = _metadata_text(metadata, "mode") or _metadata_text(metadata, "guidance_mode")
    if _state(mode) in {
        "terminal",
        "vision_terminal",
        "terminal_guidance",
        "vision_terminal_guidance",
    }:
        return True
    guidance_law = _metadata_text(metadata, "guidance_law")
    return _state(guidance_law) in {"png_vm", "png_ttc", "los"}


def _visual_png_switch_from_event(record: EventRecord) -> bool:
    metadata = record.metadata
    event_type = _event_type(record)
    if _bool_from_metadata(
        metadata,
        (
            "visual_png_switch",
            "vision_png_switch",
            "png_switch",
            "switched_to_visual_png",
        ),
        default=False,
    ):
        return True
    guidance_law = _state(_metadata_text(metadata, "guidance_law"))
    mode = _state(_metadata_text(metadata, "mode") or _metadata_text(metadata, "guidance_mode"))
    return (
        event_type
        in {
            "visual_png_switch",
            "vision_png_switch",
            "d7_visual_png_switch",
        }
        or guidance_law in {"png_vm", "png_ttc", "visual_png", "vision_png"}
        and (
            _bool_from_metadata(metadata, ("mode_switch",), default=False)
            or mode in {"vision_terminal", "visual_png", "vision_png"}
            or _bool_from_metadata(metadata, ("terminal_mode_entered",), default=False)
        )
    )


def _count_guidance_laws_by_pair(
    guidance_law_by_pair: Mapping[tuple[str, str], tuple[float, str]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for _, guidance_law in guidance_law_by_pair.values():
        counts[guidance_law] += 1
    return dict(counts)


def _count_reject_reasons_by_pair(
    reject_reasons_by_pair: Mapping[tuple[str, str], set[str]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for reasons in reject_reasons_by_pair.values():
        for reason in reasons:
            counts[reason] += 1
    return dict(counts)


def _event_type(record: EventRecord) -> str:
    return _state(record.event_type)


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _bool_rate(values: Sequence[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _link_record_to_item(record: LinkRecord) -> dict[str, Any]:
    return {
        "timestamp": record.timestamp,
        "source_node_id": record.source_node_id,
        "target_node_id": record.target_node_id,
        "relay_node_id": record.relay_node_id,
        "link_type": record.link_type,
        "message_type": record.message_type,
        "sequence_id": record.sequence_id,
        "sent_timestamp": record.sent_timestamp,
        "received_timestamp": record.received_timestamp,
        "measurement_timestamp": record.measurement_timestamp,
        "arrival_timestamp": record.arrival_timestamp,
        "payload_kind": record.payload_kind,
        "delivered": bool(record.delivered),
        "stale_after_s": record.stale_after_s,
        "metadata": dict(record.metadata),
    }


def _event_to_communication_item(record: EventRecord) -> dict[str, Any] | None:
    metadata = record.metadata
    event_type = _event_type(record)
    communication_keys = {
        "source_node_id",
        "target_node_id",
        "relay_node_id",
        "link_type",
        "message_type",
        "sequence_id",
        "sent_timestamp",
        "received_timestamp",
        "measurement_timestamp",
        "arrival_timestamp",
        "payload_kind",
        "stale_after_s",
        "delivered",
        "cross_node_latency_ms",
        "latency_ms",
        "latency_s",
    }
    communication_events = {
        "link_message",
        "message_delivery",
        "communication_message",
        "communication_link",
        "link_delivery",
        "video_metadata_delivery",
        "video_metadata_delivered",
        "bbox_delivery",
        "bbox_delivered",
        "consensus_message",
        "bid_message",
    }
    drop_events = {
        "message_drop",
        "link_drop",
        "packet_drop",
        "communication_drop",
    }
    if not (
        event_type in communication_events
        or event_type in drop_events
        or any(key in metadata for key in communication_keys)
    ):
        return None

    delivered_default = event_type not in drop_events
    return {
        "timestamp": record.timestamp,
        "source_node_id": metadata.get("source_node_id") or record.actor_id,
        "target_node_id": metadata.get("target_node_id"),
        "relay_node_id": metadata.get("relay_node_id"),
        "link_type": metadata.get("link_type", ""),
        "message_type": metadata.get("message_type", event_type),
        "sequence_id": metadata.get("sequence_id"),
        "sent_timestamp": metadata.get("sent_timestamp"),
        "received_timestamp": metadata.get("received_timestamp"),
        "measurement_timestamp": metadata.get("measurement_timestamp"),
        "arrival_timestamp": metadata.get("arrival_timestamp"),
        "payload_kind": metadata.get("payload_kind") or metadata.get("message_type") or event_type,
        "delivered": _bool_from_metadata(
            metadata,
            ("delivered", "message_delivered"),
            default=delivered_default,
        ),
        "stale_after_s": metadata.get("stale_after_s"),
        "metadata": dict(metadata),
    }


def _communication_latency_s(item: Mapping[str, Any]) -> float | None:
    metadata = item.get("metadata", {})
    if isinstance(metadata, Mapping):
        for key in ("cross_node_latency_ms", "latency_ms"):
            value = _metadata_float(metadata, key)
            if value is not None:
                return max(0.0, value / 1000.0)
        value = _metadata_float(metadata, "latency_s")
        if value is not None:
            return max(0.0, value)

    received_timestamp = _optional_float_value(item.get("received_timestamp"))
    sent_timestamp = _optional_float_value(item.get("sent_timestamp"))
    if received_timestamp is not None and sent_timestamp is not None:
        return max(0.0, received_timestamp - sent_timestamp)

    arrival_timestamp = _optional_float_value(item.get("arrival_timestamp"))
    measurement_timestamp = _optional_float_value(item.get("measurement_timestamp"))
    if arrival_timestamp is not None and measurement_timestamp is not None:
        return max(0.0, arrival_timestamp - measurement_timestamp)
    return None


def _track_update_age_s(item: Mapping[str, Any]) -> float | None:
    measurement_timestamp = _optional_float_value(item.get("measurement_timestamp"))
    if measurement_timestamp is None:
        measurement_timestamp = _optional_float_value(item.get("valid_at"))
    if measurement_timestamp is None:
        return _communication_latency_s(item)

    received_timestamp = _optional_float_value(item.get("received_timestamp"))
    if received_timestamp is None:
        received_timestamp = _optional_float_value(item.get("arrival_timestamp"))
    if received_timestamp is None:
        received_timestamp = _optional_float_value(item.get("timestamp"))
    if received_timestamp is None:
        return _communication_latency_s(item)
    return max(0.0, received_timestamp - measurement_timestamp)


def _delivery_rate(
    link_items: Sequence[Mapping[str, Any]],
    payload_kinds: set[str],
) -> float:
    attempts = [
        item
        for item in link_items
        if _payload_kind(item) in payload_kinds
    ]
    if not attempts:
        return 0.0
    delivered = sum(1 for item in attempts if item.get("delivered", True))
    return delivered / len(attempts)


def _payload_kind(item: Mapping[str, Any]) -> str:
    return _state(str(item.get("payload_kind") or item.get("message_type") or ""))


def _sequence_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_float(metadata: Mapping[str, Any], key: str) -> float | None:
    if key not in metadata or metadata[key] is None:
        return None
    return float(metadata[key])


def _metadata_int(metadata: Mapping[str, Any], key: str) -> int | None:
    value = _metadata_float(metadata, key)
    return None if value is None else int(value)


def _metadata_text(metadata: Mapping[str, Any], key: str) -> str | None:
    if key not in metadata or metadata[key] is None:
        return None
    text = str(metadata[key]).strip()
    return text or None


def _optional_float_value(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _bool_from_metadata(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
    *,
    default: bool,
) -> bool:
    for key in keys:
        if key in metadata:
            return _as_bool(metadata[key], default=default)
    return default


def _first_metadata_bool(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> bool | None:
    for key in keys:
        if key in metadata and metadata[key] is not None:
            return _as_bool(metadata[key], default=False)
    return None


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        for key in ("passed", "pass", "ok", "value"):
            if key in value:
                return _as_bool(value[key], default=default)
        return default
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok"}:
        return True
    if text in {"false", "f", "no", "n", "0", "fail", "failed", "reject", "rejected"}:
        return False
    return default


def _first_metadata_float(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> float | None:
    for key in keys:
        value = _metadata_float(metadata, key)
        if value is not None:
            return value
    return None


def _mapping_nonnegative_int(
    metadata: Mapping[str, Any],
    key: str,
) -> int | None:
    value = metadata.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _secondary_readiness_state(metadata: Mapping[str, Any]) -> str | None:
    for key in (
        "readiness_state",
        "secondary_readiness_state",
        "takeover_readiness_state",
    ):
        value = _metadata_text(metadata, key)
        if value is not None:
            state = _state(value)
            if state in {
                "not_ready",
                "visible_only",
                "registration_usable",
                "takeover_ready",
            }:
                return state
    return None


def _secondary_plan_state(metadata: Mapping[str, Any]) -> str | None:
    for key in (
        "plan_state",
        "secondary_plan_state",
        "takeover_state",
        "assignment_phase",
    ):
        value = _metadata_text(metadata, key)
        if value is None:
            continue
        state = _state(value)
        aliases = {
            "pending": "pending_secondary_plan",
            "secondary_pending": "pending_secondary_plan",
            "active": "secondary_plan_active",
            "secondary_active": "secondary_plan_active",
        }
        state = aliases.get(state, state)
        if state in {
            "pending_secondary_plan",
            "secondary_plan_active",
            "fallback",
            "expired",
            "revoked",
            "inactive",
        }:
            return state
    return None


def _state_dwell_seconds(
    samples: Sequence[tuple[float, str]],
    episode_end_s: float,
) -> dict[str, float]:
    if not samples:
        return {}
    ordered = sorted(samples, key=lambda item: item[0])
    collapsed: list[tuple[float, str]] = []
    for timestamp, state in ordered:
        if collapsed and collapsed[-1][1] == state:
            continue
        collapsed.append((max(0.0, float(timestamp)), state))
    dwell: dict[str, float] = defaultdict(float)
    for index, (timestamp, state) in enumerate(collapsed):
        next_timestamp = (
            collapsed[index + 1][0]
            if index + 1 < len(collapsed)
            else max(float(episode_end_s), timestamp)
        )
        dwell[state] += max(0.0, next_timestamp - timestamp)
    return dict(dwell)


def _append_gate_value(
    values: list[bool],
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> None:
    for key in keys:
        if key in metadata:
            values.append(_as_bool(metadata[key], default=False))
            return


def _gate_reject_from_metadata(metadata: Mapping[str, Any]) -> bool:
    gate_keys = (
        "camera_quality_gate_pass",
        "camera_quality_gate_passed",
        "los_quality_gate_pass",
        "los_quality_gate_passed",
        "maneuver_margin_gate_pass",
        "maneuver_margin_gate_passed",
    )
    present_gate_values = [
        _as_bool(metadata[key], default=False)
        for key in gate_keys
        if key in metadata
    ]
    if not present_gate_values:
        return False

    terminal_switch_allowed = _bool_from_metadata(
        metadata,
        ("terminal_switch_allowed",),
        default=True,
    )
    terminal_handover_pending = _bool_from_metadata(
        metadata,
        ("terminal_handover_pending",),
        default=False,
    )
    return terminal_handover_pending and not terminal_switch_allowed and not all(present_gate_values)


def _scenario_group_from_truth_summary(truth_summary: Mapping[str, Any]) -> str:
    explicit = truth_summary.get("scenario_group") or truth_summary.get("scenario_type")
    if explicit is None:
        scenario = truth_summary.get("scenario", {})
        if isinstance(scenario, Mapping):
            explicit = scenario.get("group") or scenario.get("scenario_group")
            if explicit is None:
                explicit = scenario.get("name")
    text = _state(str(explicit or ""))
    if not text:
        return "unlabeled"
    if text in {
        "normal",
        "secondary_200m",
        "distributed",
        "terminal_handoff_tuned",
        "multi_view_inconsistent",
    }:
        return text
    if "secondary" in text and "200" in text:
        return "secondary_200m"
    if "distributed" in text:
        return "distributed"
    if "terminal" in text and ("handoff" in text or "handover" in text) and "tuned" in text:
        return "terminal_handoff_tuned"
    if "multi" in text and "view" in text and "inconsistent" in text:
        return "multi_view_inconsistent"
    if "normal" in text or "baseline" in text:
        return "normal"
    return text


def _batch_seed_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    for key in ("batch_seed", "seed"):
        if key in truth_summary and truth_summary[key] is not None:
            return int(truth_summary[key])
    scenario = truth_summary.get("scenario", {})
    if isinstance(scenario, Mapping):
        for key in ("batch_seed", "seed"):
            if key in scenario and scenario[key] is not None:
                return int(scenario[key])
    return None


def _target_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    explicit = _count_from_truth_summary(
        truth_summary,
        (
            "target_count",
            "truth_count",
            "truth_object_count",
            "target_object_count",
        ),
    )
    if explicit is not None:
        return explicit
    truth_timestamps = _truth_timestamps_by_id(truth_summary)
    if truth_timestamps:
        return len(truth_timestamps)
    return _count_from_truth_summary(truth_summary, ("drone_count",))


def _resource_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    return _count_from_truth_summary(
        truth_summary,
        (
            "resource_count",
            "drone_count",
            "uav_count",
            "vehicle_count",
            "interceptor_count",
        ),
    )


def _camera_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    return _count_from_truth_summary(
        truth_summary,
        (
            "camera_count",
            "camera_node_count",
            "camera_resource_count",
        ),
    )


def _drone_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    return _count_from_truth_summary(
        truth_summary,
        (
            "drone_count",
            "uav_count",
            "resource_count",
            "vehicle_count",
        ),
    )


def _count_from_truth_summary(
    truth_summary: Mapping[str, Any],
    keys: Sequence[str],
) -> int | None:
    mappings = _truth_summary_count_mappings(truth_summary)
    for mapping in mappings:
        for key in keys:
            if key not in mapping:
                continue
            value = _optional_int_value(mapping[key])
            if value is not None:
                return value
    return None


def _truth_summary_count_mappings(
    truth_summary: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    mappings: list[Mapping[str, Any]] = [truth_summary]
    scenario = truth_summary.get("scenario", {})
    if isinstance(scenario, Mapping):
        mappings.append(scenario)

    for mapping in list(mappings):
        for nested_key in ("counts", "metadata", "scale"):
            nested = mapping.get(nested_key)
            if isinstance(nested, Mapping):
                mappings.append(nested)
    return mappings


def _optional_int_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _add_camera_id_from_metadata(camera_ids: set[str], metadata: Mapping[str, Any]) -> None:
    camera_id = _metadata_text(metadata, "camera_id")
    if camera_id is not None:
        camera_ids.add(camera_id)
        return

    camera = metadata.get("camera")
    if isinstance(camera, Mapping):
        nested_camera_id = _metadata_text(camera, "camera_id")
        if nested_camera_id is not None:
            camera_ids.add(nested_camera_id)
            return

    owner = (
        _metadata_text(metadata, "camera_vehicle_name")
        or _metadata_text(metadata, "owner_id")
        or _metadata_text(metadata, "vehicle_name")
    )
    camera_name = _metadata_text(metadata, "camera_name")
    if owner is not None and camera_name is not None:
        camera_ids.add(f"{owner}:{camera_name}")
    elif camera_name is not None:
        camera_ids.add(camera_name)


def _euclidean_distance(
    position: Position | None,
    truth_position: Position | None,
) -> float | None:
    if position is None or truth_position is None:
        return None
    if len(position) != len(truth_position):
        raise ValueError("position and truth_position must have the same dimension")
    squared = [(float(a) - float(b)) ** 2 for a, b in zip(position, truth_position)]
    return math.sqrt(sum(squared))


def _truth_timestamps_by_id(truth_summary: Mapping[str, Any]) -> dict[str, set[float]]:
    raw = truth_summary.get("truth_timestamps", {})
    normalized: dict[str, set[float]] = {}
    if isinstance(raw, Mapping):
        for truth_id, timestamps in raw.items():
            normalized[str(truth_id)] = {float(timestamp) for timestamp in timestamps}
    return normalized


def _truth_opportunity_count(truth_summary: Mapping[str, Any]) -> int | None:
    for key in ("total_truth_opportunities", "truth_opportunity_count"):
        if key in truth_summary and truth_summary[key] is not None:
            return int(truth_summary[key])
    return None


def _high_threat_ids(truth_summary: Mapping[str, Any]) -> set[str]:
    raw = (
        truth_summary.get("high_threat_ids")
        or truth_summary.get("high_priority_ids")
        or []
    )
    return {str(value) for value in raw}


def _high_threat_by_timestamp(
    truth_summary: Mapping[str, Any],
) -> dict[float, set[str]]:
    raw = (
        truth_summary.get("high_threat_by_timestamp")
        or truth_summary.get("high_priority_by_timestamp")
        or {}
    )
    if not isinstance(raw, Mapping):
        return {}
    return {
        float(timestamp): {str(value) for value in values}
        for timestamp, values in raw.items()
    }


def _assignment_target_key(record: AssignmentRecord) -> str | None:
    if record.truth_id is not None:
        return str(record.truth_id)
    if record.global_track_id is not None:
        return str(record.global_track_id)
    return None


def _event_numeric_value(record: EventRecord, metadata_key: str) -> float | None:
    if record.value is not None:
        return float(record.value)
    if metadata_key in record.metadata:
        return float(record.metadata[metadata_key])
    return None


def _terminal_correctness(record: TerminalRecord) -> bool | None:
    if record.association_correct is not None:
        return bool(record.association_correct)
    if record.expected_global_track_id is not None:
        return record.assigned_global_track_id == record.expected_global_track_id
    return None


def _terminal_key_from_record(record: TerminalRecord) -> tuple[str, str] | None:
    target_id = record.assigned_global_track_id or record.expected_global_track_id
    if target_id is None:
        target_id = record.local_track_id
    if target_id is None:
        return None
    return (str(record.resource_id), str(target_id))


def _terminal_key_from_event(record: EventRecord) -> tuple[str, str] | None:
    resource_id = record.actor_id or record.metadata.get("resource_id")
    target_id = (
        record.metadata.get("target_id")
        or record.metadata.get("assigned_global_track_id")
        or record.metadata.get("local_track_id")
    )
    if resource_id is None or target_id is None:
        return None
    return (str(resource_id), str(target_id))


def _terminal_event_key_from_record(
    kind: str,
    record: TerminalRecord,
) -> tuple[str, float, str, str | None, str | None]:
    return (
        kind,
        float(record.timestamp),
        str(record.resource_id),
        None if record.assigned_global_track_id is None else str(record.assigned_global_track_id),
        None if record.local_track_id is None else str(record.local_track_id),
    )


def _terminal_event_key_from_event(
    kind: str,
    record: EventRecord,
) -> tuple[str, float, str, str | None, str | None]:
    resource_id = record.actor_id or record.metadata.get("resource_id") or ""
    target_id = record.metadata.get("assigned_global_track_id") or record.metadata.get("target_id")
    local_track_id = record.metadata.get("local_track_id")
    return (
        kind,
        float(record.timestamp),
        str(resource_id),
        None if target_id is None else str(target_id),
        None if local_track_id is None else str(local_track_id),
    )
