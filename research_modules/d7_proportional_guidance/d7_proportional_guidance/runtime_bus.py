"""D7-owned runtime-bus helpers for N-pair guidance state injection.

The helpers in this module are passive adapters: callers inject the current
D3/D4/D5 state for each assignment pair and D7 returns gate/log fields.  The
module keeps one visual PNG filter per resource-target context and never calls
AirSim, SimpleFlight, or any vehicle-control API.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .pn import compute_three_dimensional_pn_benchmark
from .calibration import DEFAULT_CALIBRATION_THRESHOLD_VERSION
from .models import GuidanceMode
from .selector import (
    GuidanceLawSelection,
    RuntimeGuidanceLaw,
    VISUAL_HANDOVER_LAWS,
    select_runtime_guidance_law,
)
from .terminal_gate import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    TerminalPngContractDecision,
    coerce_assignment_guidance_binding,
    evaluate_terminal_coast_contract,
    evaluate_terminal_png_contract,
    guidance_mode_from_terminal_contract,
)
from .terminal_delivery import (
    TerminalDeliveryConfig,
    TerminalDeliveryResult,
    TerminalDeliveryState,
    TerminalDropoutReasonScope,
    TerminalFilterAuditState,
    TerminalGuidanceDelivery,
    TerminalLifecycleContext,
)
from .vision_png import (
    PngGuidanceCommand,
    PngGuidanceConfig,
    VisionGuidanceObservation,
)


D7_RUNTIME_BUS_BOUNDARY = "d7_runtime_bus_state_injection_only_no_vehicle_control"
TERMINAL_SEMANTICS_VERSION = "d7_terminal_semantics_v2"
GUIDANCE_LAW_SEMANTICS_VERSION = "d7_guidance_law_semantics_v1"

REACQUIRE_CONTRACT_REJECT_REASONS = frozenset(
    {
        "d5_not_locked",
        "terminal_identity_mismatch",
        "assignment_version_mismatch",
        "d4_terminal_inconsistent",
        "d4_plan_mismatch",
        "d4_owner_missing",
        "d4_owner_mismatch",
        "coalition_plan_version_mismatch",
        "coalition_track_version_mismatch",
        "coalition_version_mismatch",
        "coalition_id_mismatch",
        "coalition_visual_conflict",
        "coalition_visual_completion_missing",
        "coalition_visual_incomplete",
    }
)


@dataclass
class _TerminalLatchState:
    terminal_active: bool = False
    candidate_allowed_streak: int = 0
    candidate_rejected_streak: int = 0
    reacquire_grace_remaining: int = 0
    last_mode: GuidanceMode | None = None
    last_guidance_law: str | None = None
    mode_transition_count: int = 0
    guidance_law_transition_count: int = 0


@dataclass(frozen=True)
class _PendingDeliveryReset:
    reason: str
    measured_lock_was_established: bool


@dataclass(frozen=True)
class D7RuntimePairInput:
    """Injected D7 state for one assignment pair at one runtime sample."""

    binding: AssignmentGuidanceBinding | Mapping[str, Any] | Any
    d4_permission: D4GuidancePermission | Mapping[str, Any] | Any | None = None
    terminal_association: Mapping[str, Any] | Any | None = None
    observation: VisionGuidanceObservation | Mapping[str, Any] | Any | None = None
    timestamp_s: float | None = None
    resource_id: str | None = None
    handover_pending: bool = True
    terminal_locked: bool = False
    current_heading_rad: float = 0.0
    current_speed_mps: float = 0.0
    intercept_speed_mps: float = 0.0
    relative_position_ned: tuple[float, float, float] | None = None
    relative_velocity_ned: tuple[float, float, float] | None = None
    command_z_ned_m: float = 0.0
    requested_guidance_law: RuntimeGuidanceLaw | str | None = None
    terminal_handover_started_at_s: float | None = None
    terminal_timeout_s: float | None = None
    termination_snapshot: bool = False
    termination_status: str | None = None
    termination_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class D7RuntimePairOutput:
    """D7 gate and log fields for one injected assignment-pair sample."""

    timestamp_s: float
    resource_id: str
    assigned_global_track_id: str
    control_context_id: str
    mode: GuidanceMode
    guidance_law: str
    visual_png_enabled: bool
    terminal_contract_allowed: bool
    terminal_contract_reject_reason: str
    terminal_switch_allowed: bool
    terminal_switch_reject_reason: str
    plan_id: str
    plan_version: int
    track_version: int
    d4_action: str
    d5_decision_state: str
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = "primary"
    wave_id: int = 0
    coordination_mode: str = "independent"
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    activation_state: str = "active"
    terminal_authorization_scope: str = "coalition"
    arrival_coordination_required: bool = True
    per_primary_authorization_active: bool = False
    coalition_visual_completion_bypassed: bool = False
    bypassed_arrival_only: bool = False
    requested_guidance_law: str = RuntimeGuidanceLaw.PNG_VM.value
    previous_guidance_law: str | None = None
    guidance_law_transition: bool = False
    guidance_law_transition_reason: str = ""
    guidance_law_transition_count: int = 0
    previous_mode: str | None = None
    mode_transition: bool = False
    mode_transition_reason: str = ""
    mode_transition_count: int = 0
    terminal_contract_applicable: bool = True
    raw_terminal_contract_allowed: bool | None = None
    terminal_semantics_version: str = TERMINAL_SEMANTICS_VERSION
    raw_terminal_gate_applicable: bool = True
    raw_terminal_gate_allowed: bool | None = None
    raw_terminal_gate_reject_reason: str = ""
    latched_visual_mode_active: bool = False
    effective_terminal_contract_allowed: bool = False
    effective_terminal_contract_scope: str = "blocked"
    effective_terminal_contract_reason: str = ""
    effective_control_authorized: bool = False
    effective_control_authorization_scope: str = "not_authorized"
    effective_control_authorization_reason: str = ""
    termination_snapshot: bool = False
    termination_status: str | None = None
    termination_reason: str = ""
    termination_prior_mode: str | None = None
    termination_prior_latched_visual_mode_active: bool = False
    termination_prior_effective_terminal_contract_allowed: bool = False
    termination_prior_effective_control_authorized: bool = False
    terminal_coast_contract_allowed: bool = False
    terminal_coast_contract_reason: str = ""
    raw_terminal_switch_allowed: bool | None = None
    raw_terminal_switch_reject_reason: str = ""
    terminal_wait_duration_s: float | None = None
    terminal_timeout_s: float | None = None
    terminal_timeout: bool = False
    terminal_timeout_reason: str = ""
    command_saturated: bool | None = None
    command_saturation_scope: str = "not_computed"
    command_saturation_reason: str = ""
    terminal_range_m: float | None = None
    assignment_id: str | None = None
    owner_node_id: str | None = None
    d4_target_node_id: str | None = None
    local_track_id: str | None = None
    d4_action_block_reason: str = ""
    d4_visual_png_allowed: bool | None = None
    secondary_capability_class: str | None = None
    secondary_readiness_class: str | None = None
    d3_plan_version_consistent: bool | None = None
    d3_owner_consistent: bool | None = None
    d3_owner_version_consistent: bool | None = None
    d5_lock_consistent: bool | None = None
    d5_lock_consistency_reason: str = ""
    d5_assigned_global_track_id: str | None = None
    d5_assignment_version: int | None = None
    d5_plan_version: int | None = None
    activation_plan_version: int | None = None
    activation_track_version: int | None = None
    activation_coalition_version: int | None = None
    coalition_gate_applicable: bool = False
    coalition_gate_allowed: bool | None = None
    coalition_gate_reject_reason: str = ""
    d4_coalition_id: str | None = None
    d4_coalition_version: int | None = None
    d5_coalition_id: str | None = None
    d5_coalition_version: int | None = None
    d5_coalition_visual_complete: bool | None = None
    d5_coalition_support_count: int | None = None
    d5_required_resource_count: int | None = None
    d5_coalition_conflict_state: str = ""
    coalition_commit_gate_applicable: bool = False
    coalition_commit_gate_allowed: bool | None = None
    coalition_commit_gate_reject_reason: str = ""
    coalition_commit_state: str | None = None
    coalition_epoch: int | None = None
    coalition_lease_expires_at_s: float | None = None
    coalition_lease_valid: bool | None = None
    coalition_required_member_ids: tuple[str, ...] = ()
    coalition_acked_member_ids: tuple[str, ...] = ()
    coalition_resource_required: bool | None = None
    coalition_resource_acked: bool | None = None
    commit_plan_id: str | None = None
    commit_plan_version: int | None = None
    commit_coalition_id: str | None = None
    commit_coalition_version: int | None = None
    detect_registration_outcome: str | None = None
    detect_registration_reject_reasons: tuple[str, ...] = ()
    measurement_age_s: float | None = None
    projection_valid: bool | None = None
    projection_reason: str | None = None
    projection_depth_m: float | None = None
    reprojection_error_px: float | None = None
    mahalanobis_d2: float | None = None
    gate_pass: bool | None = None
    covariance_px_trace: float | None = None
    projection_covariance_px_trace: float | None = None
    camera_pose_source: str | None = None
    calibration_health: str | None = None
    drift_warning: bool | None = None
    tracker_backend: str | None = None
    requested_tracker_backend: str | None = None
    tracker_id_scope: str | None = None
    mot_history_length: int | None = None
    yolo_class_id: int | None = None
    yolo_class_name: str | None = None
    bbox_area_px: float | None = None
    association_probability: float | None = None
    threshold_advisory_version: str = DEFAULT_CALIBRATION_THRESHOLD_VERSION
    terminal_handover_pending: bool = False
    terminal_locked: bool = False
    terminal_handoff_state: str = ""
    terminal_mode_entered: bool = False
    camera_quality_gate_passed: bool | None = None
    los_quality_gate_passed: bool | None = None
    closing_speed_gate_passed: bool | None = None
    closing_speed_gate_threshold_mps: float | None = None
    maneuver_margin_gate_passed: bool | None = None
    bbox_area_ratio: float | None = None
    edge_margin_ratio: float | None = None
    detection_confidence: float | None = None
    bbox_xyxy: tuple[float, float, float, float] | None = None
    camera_id: str | None = None
    frame_timestamp_s: float | None = None
    visual_latency_s: float | None = None
    stable_frame_count: int = 0
    ttc_s: float | None = None
    ttc_raw_area_px2: float | None = None
    ttc_filtered_area_px2: float | None = None
    ttc_area_dot_px2_s: float | None = None
    ttc_valid: bool | None = None
    ttc_reject_reason: str = ""
    los_rate_radps: float = 0.0
    raw_los_rate_radps: float | None = None
    filtered_los_rate_radps: float | None = None
    los_rate_variance_radps2: float | None = None
    los_rate_clamped: bool = False
    los_rate_outlier_rejected: bool = False
    closing_speed_mps: float | None = None
    required_turn_rate_radps: float | None = None
    turn_rate_capacity_radps: float | None = None
    maneuver_margin: float | None = None
    terminal_dwell_active: bool = False
    terminal_release_grace_active: bool = False
    terminal_reacquire_grace_active: bool = False
    terminal_latch_active: bool = False
    terminal_dwell_frames: int = 1
    terminal_release_frames: int = 1
    terminal_reacquire_grace_frames: int = 0
    terminal_delivery_state: str = ""
    terminal_delivery_reason: str = ""
    terminal_visual_lock_measured: bool = False
    terminal_using_extrapolation: bool = False
    terminal_loss_frame_count: int = 0
    terminal_prediction_age_s: float | None = None
    terminal_blind_elapsed_s: float = 0.0
    terminal_blind_decay: float = 0.0
    terminal_command_sample_count: int = 0
    terminal_filter_audit_state: str = ""
    terminal_filter_audit_reason: str = ""
    terminal_lifecycle_reset: bool = False
    terminal_lifecycle_reset_reason: str = ""
    terminal_dropout_reason_scope: str = TerminalDropoutReasonScope.NOT_APPLICABLE.value
    terminal_dropout_reason: str = ""
    terminal_measured_lock_history_available: bool = False
    terminal_measured_lock_ever_established: bool = False
    terminal_contract_reset_reason: str = ""
    terminal_prediction_window_expired: bool = False
    terminal_image_innovation_norm_rad: float | None = None
    terminal_trend_coast_applied: bool = False
    terminal_trend_coast_velocity_ned: tuple[float, float, float] = (0.0, 0.0, 0.0)
    height_delta_m: float | None = None
    horizontal_range_m: float | None = None
    range_3d_m: float | None = None
    pn3d_los_rate_norm_radps: float | None = None
    pn3d_commanded_accel_norm_mps2: float | None = None
    pn3d_benchmark_only: bool = False
    pn3d_default_api_replaced: bool = False
    png_guidance_law_candidate: str | None = None
    selected_velocity_ned: tuple[float, float, float] | None = None
    png_command: PngGuidanceCommand | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal_control_allowed(self) -> bool:
        """Backward-compatible alias for effective control authorization."""

        return self.effective_control_authorized

    @property
    def configured_guidance_law(self) -> str:
        """Normalized strategy requested by the runtime configuration."""

        return self.requested_guidance_law

    @property
    def configured_midcourse_guidance_law(self) -> str:
        """Law configured for the midcourse segment of the strategy."""

        if self.requested_guidance_law in {
            RuntimeGuidanceLaw.PNG_VM.value,
            RuntimeGuidanceLaw.PNG_TTC.value,
        }:
            return RuntimeGuidanceLaw.RADAR_PN.value
        return self.requested_guidance_law

    @property
    def configured_terminal_guidance_law(self) -> str | None:
        """Configured visual law, before any terminal gate is evaluated."""

        if self.requested_guidance_law in {
            RuntimeGuidanceLaw.PNG_VM.value,
            RuntimeGuidanceLaw.PNG_TTC.value,
        }:
            return self.requested_guidance_law
        return None

    @property
    def candidate_guidance_law(self) -> str | None:
        """Visual command law evaluated this sample, whether accepted or rejected."""

        return self.png_guidance_law_candidate

    @property
    def executed_guidance_law(self) -> str | None:
        """Law whose command is executable for this live sample.

        Termination snapshots are audit-only and therefore have no executed law,
        even though the legacy ``guidance_law`` field retains the prior/fallback
        value for backward compatibility.
        """

        return None if self.termination_snapshot else self.guidance_law

    @property
    def visual_control_active(self) -> bool:
        """Canonical current-sample visual-control authorization."""

        return bool(not self.termination_snapshot and self.effective_control_authorized)

    @property
    def executed_visual_mode_switch(self) -> bool:
        """True only for a live transition into an authorized visual-control mode."""

        return bool(
            self.visual_control_active
            and self.latched_visual_mode_active
            and self.mode == GuidanceMode.VISION_TERMINAL
            and self.mode_transition
            and self.previous_mode != GuidanceMode.VISION_TERMINAL.value
        )

    def as_log_record(self) -> dict[str, Any]:
        """Return JSON/CSV-friendly D7 runtime bus fields."""

        return {
            "timestamp_s": self.timestamp_s,
            "resource_id": self.resource_id,
            "target_id": self.assigned_global_track_id,
            "assigned_global_track_id": self.assigned_global_track_id,
            "control_context_id": self.control_context_id,
            "assignment_id": self.assignment_id,
            "mode": self.mode.value,
            "guidance_law_semantics_version": GUIDANCE_LAW_SEMANTICS_VERSION,
            "configured_guidance_law": self.configured_guidance_law,
            "configured_midcourse_guidance_law": (
                self.configured_midcourse_guidance_law
            ),
            "configured_terminal_guidance_law": (
                self.configured_terminal_guidance_law
            ),
            "candidate_guidance_law": self.candidate_guidance_law,
            "executed_guidance_law": self.executed_guidance_law,
            "visual_control_active": self.visual_control_active,
            "executed_visual_mode_switch": self.executed_visual_mode_switch,
            "guidance_law": self.guidance_law,
            "requested_guidance_law": self.requested_guidance_law,
            "previous_guidance_law": self.previous_guidance_law,
            "guidance_law_transition": self.guidance_law_transition,
            "guidance_law_transition_reason": self.guidance_law_transition_reason,
            "guidance_law_transition_count": self.guidance_law_transition_count,
            "previous_mode": self.previous_mode,
            "mode_transition": self.mode_transition,
            "mode_transition_reason": self.mode_transition_reason,
            "mode_transition_count": self.mode_transition_count,
            "terminal_semantics_version": self.terminal_semantics_version,
            "raw_terminal_gate_applicable": self.raw_terminal_gate_applicable,
            "raw_terminal_gate_allowed": self.raw_terminal_gate_allowed,
            "raw_terminal_gate_reject_reason": self.raw_terminal_gate_reject_reason,
            "latched_visual_mode_active": self.latched_visual_mode_active,
            "effective_terminal_contract_allowed": self.effective_terminal_contract_allowed,
            "effective_terminal_contract_scope": self.effective_terminal_contract_scope,
            "effective_terminal_contract_reason": self.effective_terminal_contract_reason,
            "effective_control_authorized": self.effective_control_authorized,
            "effective_control_authorization_scope": self.effective_control_authorization_scope,
            "effective_control_authorization_reason": self.effective_control_authorization_reason,
            "termination_snapshot": self.termination_snapshot,
            "termination_status": self.termination_status,
            "termination_reason": self.termination_reason,
            "termination_prior_mode": self.termination_prior_mode,
            "termination_prior_latched_visual_mode_active": (
                self.termination_prior_latched_visual_mode_active
            ),
            "termination_prior_effective_terminal_contract_allowed": (
                self.termination_prior_effective_terminal_contract_allowed
            ),
            "termination_prior_effective_control_authorized": (
                self.termination_prior_effective_control_authorized
            ),
            "visual_png_enabled": self.visual_png_enabled,
            "visual_png_switch": self.visual_png_enabled,
            "terminal_contract_allowed": self.terminal_contract_allowed,
            "terminal_contract_reject_reason": self.terminal_contract_reject_reason,
            "terminal_contract_applicable": self.terminal_contract_applicable,
            "raw_terminal_contract_allowed": self.raw_terminal_contract_allowed,
            "terminal_coast_contract_allowed": self.terminal_coast_contract_allowed,
            "terminal_coast_contract_reason": self.terminal_coast_contract_reason,
            "raw_terminal_switch_allowed": self.raw_terminal_switch_allowed,
            "raw_terminal_switch_reject_reason": self.raw_terminal_switch_reject_reason,
            "terminal_switch_allowed": self.terminal_switch_allowed,
            "terminal_control_allowed": self.terminal_control_allowed,
            "terminal_switch_reject_reason": self.terminal_switch_reject_reason,
            "terminal_wait_duration_s": self.terminal_wait_duration_s,
            "terminal_timeout_s": self.terminal_timeout_s,
            "terminal_timeout": self.terminal_timeout,
            "terminal_timeout_reason": self.terminal_timeout_reason,
            "command_saturated": self.command_saturated,
            "command_saturation_scope": self.command_saturation_scope,
            "command_saturation_reason": self.command_saturation_reason,
            "terminal_handover_pending": self.terminal_handover_pending,
            "terminal_locked": self.terminal_locked,
            "terminal_handoff_state": self.terminal_handoff_state,
            "terminal_mode_entered": self.terminal_mode_entered,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "owner_node_id": self.owner_node_id,
            "d4_target_node_id": self.d4_target_node_id,
            "track_version": self.track_version,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
            "wave_id": self.wave_id,
            "coordination_mode": self.coordination_mode,
            "arrival_window_start_s": self.arrival_window_start_s,
            "arrival_window_end_s": self.arrival_window_end_s,
            "activation_state": self.activation_state,
            "terminal_authorization_scope": self.terminal_authorization_scope,
            "arrival_coordination_required": self.arrival_coordination_required,
            "per_primary_authorization_active": self.per_primary_authorization_active,
            "coalition_visual_completion_bypassed": self.coalition_visual_completion_bypassed,
            "bypassed_arrival_only": self.bypassed_arrival_only,
            "activation_plan_version": self.activation_plan_version,
            "activation_track_version": self.activation_track_version,
            "activation_coalition_version": self.activation_coalition_version,
            "coalition_gate_applicable": self.coalition_gate_applicable,
            "coalition_gate_allowed": self.coalition_gate_allowed,
            "coalition_gate_reject_reason": self.coalition_gate_reject_reason,
            "d4_coalition_id": self.d4_coalition_id,
            "d4_coalition_version": self.d4_coalition_version,
            "d5_coalition_id": self.d5_coalition_id,
            "d5_coalition_version": self.d5_coalition_version,
            "d5_coalition_visual_complete": self.d5_coalition_visual_complete,
            "d5_coalition_support_count": self.d5_coalition_support_count,
            "d5_required_resource_count": self.d5_required_resource_count,
            "d5_coalition_conflict_state": self.d5_coalition_conflict_state,
            "coalition_commit_gate_applicable": self.coalition_commit_gate_applicable,
            "coalition_commit_gate_allowed": self.coalition_commit_gate_allowed,
            "coalition_commit_gate_reject_reason": self.coalition_commit_gate_reject_reason,
            "coalition_commit_state": self.coalition_commit_state,
            "coalition_epoch": self.coalition_epoch,
            "coalition_lease_expires_at_s": self.coalition_lease_expires_at_s,
            "coalition_lease_valid": self.coalition_lease_valid,
            "coalition_required_member_ids": self.coalition_required_member_ids,
            "coalition_acked_member_ids": self.coalition_acked_member_ids,
            "coalition_resource_required": self.coalition_resource_required,
            "coalition_resource_acked": self.coalition_resource_acked,
            "commit_plan_id": self.commit_plan_id,
            "commit_plan_version": self.commit_plan_version,
            "commit_coalition_id": self.commit_coalition_id,
            "commit_coalition_version": self.commit_coalition_version,
            "terminal_range_m": self.terminal_range_m,
            "d4_action": self.d4_action,
            "d4_state": self.d4_action,
            "d4_action_block_reason": self.d4_action_block_reason,
            "d4_visual_png_allowed": self.d4_visual_png_allowed,
            "secondary_capability_class": self.secondary_capability_class,
            "secondary_readiness_class": self.secondary_readiness_class,
            "d3_plan_version_consistent": self.d3_plan_version_consistent,
            "d3_owner_consistent": self.d3_owner_consistent,
            "d3_owner_version_consistent": self.d3_owner_version_consistent,
            "d5_decision_state": self.d5_decision_state,
            "d5_state": self.d5_decision_state,
            "d5_lock_consistent": self.d5_lock_consistent,
            "d5_lock_consistency_reason": self.d5_lock_consistency_reason,
            "d5_assigned_global_track_id": self.d5_assigned_global_track_id,
            "d5_assignment_version": self.d5_assignment_version,
            "d5_plan_version": self.d5_plan_version,
            "local_track_id": self.local_track_id,
            "detect_registration_outcome": self.detect_registration_outcome,
            "detect_registration_reject_reasons": self.detect_registration_reject_reasons,
            "measurement_age_s": self.measurement_age_s,
            "projection_valid": self.projection_valid,
            "projection_reason": self.projection_reason,
            "projection_depth_m": self.projection_depth_m,
            "reprojection_error_px": self.reprojection_error_px,
            "mahalanobis_d2": self.mahalanobis_d2,
            "gate_pass": self.gate_pass,
            "covariance_px_trace": self.covariance_px_trace,
            "projection_covariance_px_trace": self.projection_covariance_px_trace,
            "camera_pose_source": self.camera_pose_source,
            "calibration_health": self.calibration_health,
            "drift_warning": self.drift_warning,
            "tracker_backend": self.tracker_backend,
            "requested_tracker_backend": self.requested_tracker_backend,
            "tracker_id_scope": self.tracker_id_scope,
            "mot_history_length": self.mot_history_length,
            "yolo_class_id": self.yolo_class_id,
            "yolo_class_name": self.yolo_class_name,
            "bbox_area_px": self.bbox_area_px,
            "association_probability": self.association_probability,
            "threshold_advisory_version": self.threshold_advisory_version,
            "camera_quality_gate_passed": self.camera_quality_gate_passed,
            "los_quality_gate_passed": self.los_quality_gate_passed,
            "closing_speed_gate_passed": self.closing_speed_gate_passed,
            "closing_speed_gate_threshold_mps": self.closing_speed_gate_threshold_mps,
            "maneuver_margin_gate_passed": self.maneuver_margin_gate_passed,
            "bbox_area_ratio": self.bbox_area_ratio,
            "edge_margin_ratio": self.edge_margin_ratio,
            "detection_confidence": self.detection_confidence,
            "bbox_xyxy": self.bbox_xyxy,
            "camera_id": self.camera_id,
            "frame_timestamp_s": self.frame_timestamp_s,
            "visual_latency_s": self.visual_latency_s,
            "stable_frame_count": self.stable_frame_count,
            "ttc_s": self.ttc_s,
            "ttc_raw_area_px2": self.ttc_raw_area_px2,
            "ttc_filtered_area_px2": self.ttc_filtered_area_px2,
            "ttc_area_dot_px2_s": self.ttc_area_dot_px2_s,
            "ttc_valid": self.ttc_valid,
            "ttc_reject_reason": self.ttc_reject_reason,
            "los_rate_radps": self.los_rate_radps,
            "raw_los_rate_radps": self.raw_los_rate_radps,
            "filtered_los_rate_radps": self.filtered_los_rate_radps,
            "los_rate_variance_radps2": self.los_rate_variance_radps2,
            "los_rate_clamped": self.los_rate_clamped,
            "los_rate_outlier_rejected": self.los_rate_outlier_rejected,
            "closing_speed_mps": self.closing_speed_mps,
            "required_turn_rate_radps": self.required_turn_rate_radps,
            "turn_rate_capacity_radps": self.turn_rate_capacity_radps,
            "maneuver_margin": self.maneuver_margin,
            "terminal_dwell_active": self.terminal_dwell_active,
            "terminal_release_grace_active": self.terminal_release_grace_active,
            "terminal_reacquire_grace_active": self.terminal_reacquire_grace_active,
            "terminal_latch_active": self.terminal_latch_active,
            "terminal_dwell_frames": self.terminal_dwell_frames,
            "terminal_release_frames": self.terminal_release_frames,
            "terminal_reacquire_grace_frames": self.terminal_reacquire_grace_frames,
            "terminal_delivery_state": self.terminal_delivery_state,
            "terminal_delivery_reason": self.terminal_delivery_reason,
            "terminal_visual_lock_measured": self.terminal_visual_lock_measured,
            "terminal_using_extrapolation": self.terminal_using_extrapolation,
            "terminal_loss_frame_count": self.terminal_loss_frame_count,
            "terminal_prediction_age_s": self.terminal_prediction_age_s,
            "terminal_blind_elapsed_s": self.terminal_blind_elapsed_s,
            "terminal_blind_decay": self.terminal_blind_decay,
            "terminal_command_sample_count": self.terminal_command_sample_count,
            "terminal_filter_audit_state": self.terminal_filter_audit_state,
            "terminal_filter_audit_reason": self.terminal_filter_audit_reason,
            "terminal_lifecycle_reset": self.terminal_lifecycle_reset,
            "terminal_lifecycle_reset_reason": self.terminal_lifecycle_reset_reason,
            "terminal_dropout_reason_scope": self.terminal_dropout_reason_scope,
            "terminal_dropout_reason": self.terminal_dropout_reason,
            "terminal_measured_lock_history_available": (
                self.terminal_measured_lock_history_available
            ),
            "terminal_measured_lock_ever_established": (
                self.terminal_measured_lock_ever_established
            ),
            "terminal_contract_reset_reason": self.terminal_contract_reset_reason,
            "terminal_prediction_window_expired": self.terminal_prediction_window_expired,
            "terminal_image_innovation_norm_rad": self.terminal_image_innovation_norm_rad,
            "terminal_trend_coast_applied": self.terminal_trend_coast_applied,
            "terminal_trend_coast_velocity_ned": self.terminal_trend_coast_velocity_ned,
            "height_delta_m": self.height_delta_m,
            "horizontal_range_m": self.horizontal_range_m,
            "range_3d_m": self.range_3d_m,
            "pn3d_los_rate_norm_radps": self.pn3d_los_rate_norm_radps,
            "pn3d_commanded_accel_norm_mps2": self.pn3d_commanded_accel_norm_mps2,
            "pn3d_benchmark_only": self.pn3d_benchmark_only,
            "pn3d_default_api_replaced": self.pn3d_default_api_replaced,
            "png_guidance_law_candidate": self.png_guidance_law_candidate,
            "selected_velocity_ned": self.selected_velocity_ned,
            **self.metadata,
        }


class D7RuntimeBus:
    """Stateful per-pair visual filter registry for D7 runtime injection."""

    def __init__(
        self,
        config: PngGuidanceConfig | None = None,
        terminal_delivery_config: TerminalDeliveryConfig | None = None,
    ) -> None:
        self.config = config or PngGuidanceConfig()
        self.terminal_delivery_config = terminal_delivery_config or TerminalDeliveryConfig()
        self._deliveries: dict[str, TerminalGuidanceDelivery] = {}
        self._binding_signatures: dict[str, tuple[Any, ...]] = {}
        self._current_bindings: dict[str, AssignmentGuidanceBinding] = {}
        self._requested_laws: dict[str, RuntimeGuidanceLaw] = {}
        self._terminal_latches: dict[str, _TerminalLatchState] = {}
        self._pending_delivery_resets: dict[str, _PendingDeliveryReset] = {}
        self._last_outputs: dict[str, D7RuntimePairOutput] = {}

    @property
    def control_context_ids(self) -> tuple[str, ...]:
        return tuple(self._deliveries)

    def reset(self) -> None:
        self._deliveries.clear()
        self._binding_signatures.clear()
        self._current_bindings.clear()
        self._requested_laws.clear()
        self._terminal_latches.clear()
        self._pending_delivery_resets.clear()
        self._last_outputs.clear()

    def reset_pair(self, control_context_id: str) -> None:
        self._deliveries.pop(control_context_id, None)
        self._binding_signatures.pop(control_context_id, None)
        self._current_bindings.pop(control_context_id, None)
        self._requested_laws.pop(control_context_id, None)
        self._terminal_latches.pop(control_context_id, None)
        self._pending_delivery_resets.pop(control_context_id, None)
        self._last_outputs.pop(control_context_id, None)

    def inject_state(
        self,
        pair_inputs: Iterable[D7RuntimePairInput | Mapping[str, Any] | Any],
    ) -> list[D7RuntimePairOutput]:
        """Evaluate one runtime bus sample for every injected assignment pair."""

        return [self.evaluate_pair(_coerce_pair_input(item)) for item in pair_inputs]

    def evaluate_pair(self, pair_input: D7RuntimePairInput) -> D7RuntimePairOutput:
        """Evaluate D3/D4/D5 contract and optional visual PNG gate for one pair."""

        binding = coerce_assignment_guidance_binding(pair_input.binding)
        selection = select_runtime_guidance_law(
            pair_input.requested_guidance_law,
            default_visual_law=self.config.law,
        )
        control_context_id = _control_context_id(binding)
        if pair_input.termination_snapshot:
            return self._termination_snapshot(
                pair_input,
                binding=binding,
                selection=selection,
                control_context_id=control_context_id,
            )
        signature = _binding_signature(binding)
        previous_signature = self._binding_signatures.get(control_context_id)
        previous_binding = self._current_bindings.get(control_context_id)
        binding_transition = _binding_transition(previous_binding, binding)
        binding_state_preserved = False
        if previous_signature != signature:
            binding_state_preserved = bool(
                previous_binding is not None
                and binding_transition == "monotonic_current_update"
                and self._requested_laws.get(control_context_id) == selection.requested_law
            )
            if not binding_state_preserved:
                previous_delivery = self._deliveries.get(control_context_id)
                self._deliveries[control_context_id] = self._new_terminal_delivery(selection)
                self._terminal_latches[control_context_id] = _TerminalLatchState()
                if previous_signature is not None:
                    self._pending_delivery_resets[control_context_id] = _PendingDeliveryReset(
                        reason="binding_signature_changed",
                        measured_lock_was_established=bool(
                            previous_delivery is not None
                            and previous_delivery.measured_lock_ever_established
                        ),
                    )
            self._binding_signatures[control_context_id] = signature
            self._current_bindings[control_context_id] = binding
            self._requested_laws[control_context_id] = selection.requested_law
        elif previous_binding is None:
            self._current_bindings[control_context_id] = binding
        elif self._requested_laws.get(control_context_id) != selection.requested_law:
            previous_delivery = self._deliveries.get(control_context_id)
            self._deliveries[control_context_id] = self._new_terminal_delivery(selection)
            self._requested_laws[control_context_id] = selection.requested_law
            self._pending_delivery_resets[control_context_id] = _PendingDeliveryReset(
                reason="requested_guidance_law_changed",
                measured_lock_was_established=bool(
                    previous_delivery is not None
                    and previous_delivery.measured_lock_ever_established
                ),
            )
            latch = self._terminal_latches.setdefault(control_context_id, _TerminalLatchState())
            _reset_terminal_candidate_state(latch)
        latch = self._terminal_latches.setdefault(control_context_id, _TerminalLatchState())

        observation = (
            coerce_vision_guidance_observation(pair_input.observation)
            if pair_input.observation is not None
            else None
        )
        timestamp_s = _resolve_timestamp_s(pair_input, observation, binding)
        timing = _terminal_handover_timing(
            pair_input,
            timestamp_s=timestamp_s,
            enabled=selection.requires_terminal_gate,
            terminal_active=latch.terminal_active,
        )
        decision = evaluate_terminal_png_contract(
            binding=binding,
            d4_permission=pair_input.d4_permission,
            terminal_association=pair_input.terminal_association,
            observation=observation,
            timestamp_s=timestamp_s,
            resource_id=pair_input.resource_id or binding.resource_id,
        )
        delivery_handler = self._deliveries[control_context_id]
        lifecycle_context = _terminal_lifecycle_context(binding, decision, observation)
        coast_decision = TerminalPngContractDecision(False, "")
        coast_context_reject_reason = ""
        if (
            not decision.allowed
            and decision.reject_reason == "d5_not_locked"
            and observation is None
            and delivery_handler.has_measured_lock
        ):
            coast_context_reject_reason = delivery_handler.coast_context_reject_reason(
                lifecycle_context
            )
            if coast_context_reject_reason:
                coast_decision = TerminalPngContractDecision(
                    False,
                    coast_context_reject_reason,
                )
            else:
                coast_decision = evaluate_terminal_coast_contract(
                    binding=binding,
                    d4_permission=pair_input.d4_permission,
                    terminal_association=pair_input.terminal_association,
                    observation=None,
                    timestamp_s=timestamp_s,
                    resource_id=pair_input.resource_id or binding.resource_id,
                )

        common = _common_output_kwargs(
            timestamp_s=timestamp_s,
            binding=binding,
            control_context_id=control_context_id,
            decision=decision,
            terminal_handover_pending=pair_input.handover_pending,
            terminal_locked=pair_input.terminal_locked,
            observation=observation,
            terminal_association=pair_input.terminal_association,
            relative_position_ned=pair_input.relative_position_ned,
            relative_velocity_ned=pair_input.relative_velocity_ned,
            navigation_constant=self.config.navigation_constant,
            requested_guidance_law=selection.requested_law.value,
            terminal_wait_duration_s=timing["wait_duration_s"],
            terminal_timeout_s=timing["timeout_s"],
            terminal_timeout=timing["timed_out"],
            metadata={
                "boundary": D7_RUNTIME_BUS_BOUNDARY,
                "binding_transition": binding_transition,
                "binding_state_preserved": binding_state_preserved,
                "previous_binding_plan_version": (
                    previous_binding.plan_version if previous_binding is not None else None
                ),
                "terminal_contract_fallback_guidance_law": (
                    "" if decision.allowed else RuntimeGuidanceLaw.RADAR_PN.value
                ),
                "arrival_window_semantics": "terminal_png_permission_window",
                **pair_input.metadata,
            },
        )

        if not selection.requires_terminal_gate:
            self._deliveries[control_context_id].reset()
            self._pending_delivery_resets.pop(control_context_id, None)
            _reset_terminal_candidate_state(latch)
            baseline_common = {
                **common,
                "terminal_contract_allowed": False,
                "terminal_contract_reject_reason": "",
                "terminal_contract_applicable": False,
                "raw_terminal_contract_allowed": None,
            }
            output = D7RuntimePairOutput(
                **baseline_common,
                mode=GuidanceMode.RADAR_MIDCOURSE,
                guidance_law=selection.midcourse_law.value,
                visual_png_enabled=False,
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="",
                terminal_handoff_state=f"full_course_{selection.requested_law.value}",
                terminal_mode_entered=False,
                closing_speed_mps=_relative_closing_speed_mps(
                    pair_input.relative_position_ned,
                    pair_input.relative_velocity_ned,
                ),
                terminal_latch_active=False,
                terminal_dwell_frames=self.config.terminal_dwell_frames,
                terminal_release_frames=self.config.terminal_release_frames,
                terminal_reacquire_grace_frames=self.config.terminal_reacquire_grace_frames,
            )
            return self._finalize_output(
                output,
                latch,
                transition_reason="full_course_guidance_selected",
            )

        if timing["timed_out"]:
            delivery = self._deliveries[control_context_id].block(
                assigned_global_track_id=binding.assigned_global_track_id,
                reason="terminal_handover_timeout",
                dropout_sample=observation is None,
            )
            delivery = self._apply_pending_delivery_reset(
                control_context_id,
                delivery,
                dropout_sample=observation is None,
            )
            _reset_terminal_candidate_state(latch)
            output = D7RuntimePairOutput(
                **common,
                mode=GuidanceMode.ABORT_REVOKE,
                guidance_law=RuntimeGuidanceLaw.RADAR_PN.value,
                visual_png_enabled=False,
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="terminal_handover_timeout",
                raw_terminal_switch_allowed=False,
                raw_terminal_switch_reject_reason="terminal_handover_timeout",
                terminal_timeout_reason="terminal_handover_timeout",
                terminal_handoff_state="terminal_timeout",
                terminal_mode_entered=False,
                closing_speed_mps=_relative_closing_speed_mps(
                    pair_input.relative_position_ned,
                    pair_input.relative_velocity_ned,
                ),
                terminal_latch_active=False,
                terminal_dwell_frames=self.config.terminal_dwell_frames,
                terminal_release_frames=self.config.terminal_release_frames,
                terminal_reacquire_grace_frames=self.config.terminal_reacquire_grace_frames,
                **_terminal_delivery_output_fields(delivery),
            )
            return self._finalize_output(
                output,
                latch,
                transition_reason="terminal_handover_timeout",
            )

        if not decision.allowed and not coast_decision.allowed:
            block_reason = coast_context_reject_reason or decision.reject_reason
            delivery = self._deliveries[control_context_id].block(
                assigned_global_track_id=binding.assigned_global_track_id,
                reason=block_reason,
                dropout_sample=observation is None,
            )
            delivery = self._apply_pending_delivery_reset(
                control_context_id,
                delivery,
                dropout_sample=observation is None,
            )
            _reset_terminal_candidate_state(latch)
            if decision.reject_reason in REACQUIRE_CONTRACT_REJECT_REASONS:
                latch.reacquire_grace_remaining = self.config.terminal_reacquire_grace_frames
            output = D7RuntimePairOutput(
                **common,
                mode=guidance_mode_from_terminal_contract(
                    decision,
                    handover_pending=pair_input.handover_pending,
                    terminal_locked=pair_input.terminal_locked,
                ),
                guidance_law="radar_pn",
                visual_png_enabled=False,
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="",
                terminal_handoff_state="contract_rejected",
                terminal_mode_entered=False,
                closing_speed_mps=_relative_closing_speed_mps(
                    pair_input.relative_position_ned,
                    pair_input.relative_velocity_ned,
                ),
                terminal_latch_active=latch.terminal_active,
                terminal_dwell_frames=self.config.terminal_dwell_frames,
                terminal_release_frames=self.config.terminal_release_frames,
                terminal_reacquire_grace_frames=self.config.terminal_reacquire_grace_frames,
                **_terminal_delivery_output_fields(delivery),
            )
            return self._finalize_output(
                output,
                latch,
                transition_reason=f"terminal_contract_rejected:{decision.reject_reason}",
            )

        coast_latch_was_active = coast_decision.allowed and latch.terminal_active
        delivery = delivery_handler.evaluate(
            assigned_global_track_id=binding.assigned_global_track_id,
            timestamp_s=timestamp_s,
            observation=observation,
            current_heading_rad=pair_input.current_heading_rad,
            current_speed_mps=pair_input.current_speed_mps,
            intercept_speed_mps=pair_input.intercept_speed_mps,
            relative_position_ned=pair_input.relative_position_ned,
            relative_velocity_ned=pair_input.relative_velocity_ned,
            command_z_ned_m=pair_input.command_z_ned_m,
            lifecycle_context=lifecycle_context,
            soft_prediction_eligible=bool(
                decision.allowed
                and decision.d5_lock_consistent is True
                and not decision.d5_coalition_conflict_state
            ),
        )
        delivery = self._apply_pending_delivery_reset(
            control_context_id,
            delivery,
            dropout_sample=observation is None,
        )
        command = delivery.command
        if command is None:
            _reset_terminal_candidate_state(latch)
            expired = delivery.state == TerminalDeliveryState.EXPIRED
            output = D7RuntimePairOutput(
                **common,
                mode=GuidanceMode.REACQUIRE if expired else GuidanceMode.HANDOVER_PENDING,
                guidance_law="radar_pn",
                visual_png_enabled=False,
                terminal_switch_allowed=False,
                terminal_switch_reject_reason=delivery.reason,
                raw_terminal_switch_allowed=False,
                raw_terminal_switch_reject_reason=delivery.reason,
                terminal_handoff_state=delivery.state.value,
                terminal_mode_entered=False,
                closing_speed_mps=_relative_closing_speed_mps(
                    pair_input.relative_position_ned,
                    pair_input.relative_velocity_ned,
                ),
                terminal_latch_active=latch.terminal_active,
                terminal_dwell_frames=self.config.terminal_dwell_frames,
                terminal_release_frames=self.config.terminal_release_frames,
                terminal_reacquire_grace_frames=self.config.terminal_reacquire_grace_frames,
                **_terminal_delivery_output_fields(delivery),
            )
            return self._finalize_output(
                output,
                latch,
                transition_reason=delivery.reason,
            )
        quality = command.quality
        candidate_allowed = bool(quality.terminal_switch_allowed)
        candidate_reject_reason = quality.reject_reason
        if coast_decision.allowed and not coast_latch_was_active:
            candidate_allowed = False
            candidate_reject_reason = "bounded_coast_requires_prior_terminal_latch"
        latch_decision = _apply_terminal_latch(
            latch,
            candidate_allowed=candidate_allowed,
            candidate_reject_reason=candidate_reject_reason,
            config=self.config,
        )
        visual_png_enabled = bool(latch_decision["visual_png_enabled"])
        output = D7RuntimePairOutput(
            **common,
            mode=GuidanceMode.VISION_TERMINAL if visual_png_enabled else GuidanceMode.HANDOVER_PENDING,
            guidance_law=command.guidance_law if visual_png_enabled else "radar_pn",
            visual_png_enabled=visual_png_enabled,
            terminal_switch_allowed=visual_png_enabled,
            terminal_switch_reject_reason=str(latch_decision["terminal_switch_reject_reason"]),
            raw_terminal_switch_allowed=bool(quality.terminal_switch_allowed),
            raw_terminal_switch_reject_reason=quality.reject_reason,
            terminal_coast_contract_allowed=coast_decision.allowed,
            terminal_coast_contract_reason=(
                "bounded_coast_reacquire" if coast_decision.allowed else ""
            ),
            terminal_handoff_state=str(latch_decision["terminal_handoff_state"]),
            terminal_mode_entered=visual_png_enabled,
            camera_quality_gate_passed=quality.camera_quality_gate_passed,
            los_quality_gate_passed=quality.los_quality_gate_passed,
            closing_speed_gate_passed=(
                None
                if pair_input.relative_position_ned is None
                else quality.closing_speed_mps > self.config.min_closing_speed_mps
            ),
            closing_speed_gate_threshold_mps=(
                self.config.min_closing_speed_mps
                if pair_input.relative_position_ned is not None
                else None
            ),
            maneuver_margin_gate_passed=quality.maneuver_margin_gate_passed,
            bbox_area_ratio=quality.bbox_area_ratio,
            edge_margin_ratio=quality.edge_margin_ratio,
            stable_frame_count=quality.stable_frame_count,
            ttc_s=quality.ttc_s,
            ttc_raw_area_px2=quality.ttc_raw_area_px2,
            ttc_filtered_area_px2=quality.ttc_filtered_area_px2,
            ttc_area_dot_px2_s=quality.ttc_area_dot_px2_s,
            ttc_valid=quality.ttc_valid,
            ttc_reject_reason=quality.ttc_reject_reason,
            los_rate_radps=quality.los_rate_radps,
            raw_los_rate_radps=quality.raw_los_rate_radps,
            filtered_los_rate_radps=quality.filtered_los_rate_radps,
            los_rate_variance_radps2=quality.los_rate_variance_radps2,
            los_rate_clamped=quality.los_rate_clamped,
            los_rate_outlier_rejected=quality.los_rate_outlier_rejected,
            closing_speed_mps=quality.closing_speed_mps,
            required_turn_rate_radps=quality.required_turn_rate_radps,
            turn_rate_capacity_radps=quality.turn_rate_capacity_radps,
            maneuver_margin=quality.maneuver_margin,
            terminal_dwell_active=bool(latch_decision["terminal_dwell_active"]),
            terminal_release_grace_active=bool(latch_decision["terminal_release_grace_active"]),
            terminal_reacquire_grace_active=bool(latch_decision["terminal_reacquire_grace_active"]),
            terminal_latch_active=latch.terminal_active,
            terminal_dwell_frames=self.config.terminal_dwell_frames,
            terminal_release_frames=self.config.terminal_release_frames,
            terminal_reacquire_grace_frames=self.config.terminal_reacquire_grace_frames,
            png_guidance_law_candidate=command.guidance_law,
            selected_velocity_ned=command.velocity_ned if visual_png_enabled else None,
            png_command=command,
            command_saturated=command.control_saturated,
            command_saturation_scope=(
                "active_visual_command" if visual_png_enabled else "visual_candidate_command"
            ),
            command_saturation_reason=_command_saturation_reason(command),
            **_terminal_delivery_output_fields(delivery),
        )
        return self._finalize_output(
            output,
            latch,
            transition_reason=(
                "terminal_visual_gate_enabled"
                if visual_png_enabled
                else f"terminal_visual_gate_rejected:{quality.reject_reason}"
            ),
        )

    def _apply_pending_delivery_reset(
        self,
        control_context_id: str,
        delivery: TerminalDeliveryResult,
        *,
        dropout_sample: bool,
    ) -> TerminalDeliveryResult:
        pending = self._pending_delivery_resets.pop(control_context_id, None)
        if pending is None:
            return delivery
        updates: dict[str, Any] = {
            "filter_audit_state": TerminalFilterAuditState.RESET,
            "filter_audit_reason": pending.reason,
            "lifecycle_reset": True,
            "lifecycle_reset_reason": pending.reason,
            "contract_reset_reason": pending.reason,
            "measured_lock_history_available": False,
            "measured_lock_ever_established": pending.measured_lock_was_established,
        }
        if dropout_sample:
            updates.update(
                dropout_reason_scope=TerminalDropoutReasonScope.CONTRACT_RESET,
                dropout_reason="terminal_visual_context_reset_before_dropout",
            )
        return replace(delivery, **updates)

    def _termination_snapshot(
        self,
        pair_input: D7RuntimePairInput,
        *,
        binding: AssignmentGuidanceBinding,
        selection: GuidanceLawSelection,
        control_context_id: str,
    ) -> D7RuntimePairOutput:
        status = (pair_input.termination_status or "").strip()
        if not status:
            raise ValueError("termination_status is required for a termination snapshot")
        reason = pair_input.termination_reason.strip() or status
        previous = self._last_outputs.get(control_context_id)
        timestamp_s = float(
            pair_input.timestamp_s
            if pair_input.timestamp_s is not None
            else binding.created_at_s
        )
        if previous is None:
            abort_statuses = {"abort", "aborted", "failed", "failure", "timeout"}
            snapshot = D7RuntimePairOutput(
                timestamp_s=timestamp_s,
                resource_id=binding.resource_id,
                assigned_global_track_id=binding.assigned_global_track_id,
                control_context_id=control_context_id,
                mode=(
                    GuidanceMode.ABORT_REVOKE
                    if status.lower() in abort_statuses
                    else GuidanceMode.HOLD
                ),
                guidance_law=selection.midcourse_law.value,
                visual_png_enabled=False,
                terminal_contract_allowed=False,
                terminal_contract_reject_reason="",
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="termination_snapshot_not_live_control",
                plan_id=binding.plan_id,
                plan_version=binding.plan_version,
                track_version=binding.track_version,
                d4_action="",
                d5_decision_state="",
                requested_guidance_law=selection.requested_law.value,
                owner_node_id=binding.owner_node_id,
                assignment_id=binding.assignment_id,
            )
        else:
            snapshot = replace(
                previous,
                timestamp_s=timestamp_s,
                visual_png_enabled=False,
                terminal_contract_allowed=False,
                terminal_contract_reject_reason="",
                terminal_contract_applicable=False,
                raw_terminal_contract_allowed=None,
                terminal_coast_contract_allowed=False,
                terminal_coast_contract_reason="",
                raw_terminal_switch_allowed=None,
                raw_terminal_switch_reject_reason="",
                terminal_switch_allowed=False,
                terminal_switch_reject_reason="termination_snapshot_not_live_control",
                terminal_handoff_state="termination_snapshot",
                terminal_mode_entered=False,
                terminal_latch_active=False,
                selected_velocity_ned=None,
                png_command=None,
                command_saturated=None,
                command_saturation_scope="not_computed",
                command_saturation_reason="",
            )
        snapshot = replace(
            snapshot,
            terminal_semantics_version=TERMINAL_SEMANTICS_VERSION,
            visual_png_enabled=False,
            terminal_contract_allowed=False,
            terminal_contract_reject_reason="",
            terminal_contract_applicable=False,
            raw_terminal_contract_allowed=None,
            raw_terminal_gate_applicable=False,
            raw_terminal_gate_allowed=None,
            raw_terminal_gate_reject_reason="",
            terminal_coast_contract_allowed=False,
            terminal_coast_contract_reason="",
            raw_terminal_switch_allowed=None,
            raw_terminal_switch_reject_reason="",
            terminal_switch_allowed=False,
            terminal_switch_reject_reason="termination_snapshot_not_live_control",
            terminal_handoff_state="termination_snapshot",
            terminal_mode_entered=False,
            terminal_latch_active=False,
            latched_visual_mode_active=False,
            effective_terminal_contract_allowed=False,
            effective_terminal_contract_scope="termination_snapshot",
            effective_terminal_contract_reason=reason,
            effective_control_authorized=False,
            effective_control_authorization_scope="termination_snapshot",
            effective_control_authorization_reason=reason,
            termination_snapshot=True,
            termination_status=status,
            termination_reason=reason,
            termination_prior_mode=previous.mode.value if previous is not None else None,
            termination_prior_latched_visual_mode_active=(
                previous.latched_visual_mode_active if previous is not None else False
            ),
            termination_prior_effective_terminal_contract_allowed=(
                previous.effective_terminal_contract_allowed if previous is not None else False
            ),
            termination_prior_effective_control_authorized=(
                previous.effective_control_authorized if previous is not None else False
            ),
            previous_mode=previous.mode.value if previous is not None else None,
            mode_transition=False,
            mode_transition_reason="",
            previous_guidance_law=previous.guidance_law if previous is not None else None,
            guidance_law_transition=False,
            guidance_law_transition_reason="",
            metadata={
                **snapshot.metadata,
                "boundary": D7_RUNTIME_BUS_BOUNDARY,
                "termination_snapshot_not_live_control": True,
                **pair_input.metadata,
            },
        )
        delivery = self._deliveries.get(control_context_id)
        if delivery is not None:
            delivery.reset()
        latch = self._terminal_latches.get(control_context_id)
        if latch is not None:
            _reset_terminal_candidate_state(latch)
        self._pending_delivery_resets.pop(control_context_id, None)
        self._last_outputs[control_context_id] = snapshot
        return snapshot

    def _new_terminal_delivery(
        self,
        selection: GuidanceLawSelection,
    ) -> TerminalGuidanceDelivery:
        terminal_law = selection.terminal_law or RuntimeGuidanceLaw.PNG_VM
        return TerminalGuidanceDelivery(
            png_config=replace(self.config, law=terminal_law.value),
            config=self.terminal_delivery_config,
        )

    def _finalize_output(
        self,
        output: D7RuntimePairOutput,
        latch: _TerminalLatchState,
        *,
        transition_reason: str,
    ) -> D7RuntimePairOutput:
        previous_mode = latch.last_mode
        previous_law = latch.last_guidance_law
        mode_transition = previous_mode != output.mode
        law_transition = previous_law != output.guidance_law
        if mode_transition:
            latch.mode_transition_count += 1
        if law_transition:
            latch.guidance_law_transition_count += 1
        latch.last_mode = output.mode
        latch.last_guidance_law = output.guidance_law
        finalized = replace(
            output,
            previous_mode=previous_mode.value if previous_mode is not None else None,
            mode_transition=mode_transition,
            mode_transition_reason=transition_reason if mode_transition else "",
            mode_transition_count=latch.mode_transition_count,
            previous_guidance_law=previous_law,
            guidance_law_transition=law_transition,
            guidance_law_transition_reason=transition_reason if law_transition else "",
            guidance_law_transition_count=latch.guidance_law_transition_count,
        )
        finalized = _normalize_terminal_semantics(
            finalized,
            latched_visual_mode_active=latch.terminal_active,
        )
        self._last_outputs[output.control_context_id] = finalized
        return finalized


def _reset_terminal_candidate_state(latch: _TerminalLatchState) -> None:
    latch.terminal_active = False
    latch.candidate_allowed_streak = 0
    latch.candidate_rejected_streak = 0
    latch.reacquire_grace_remaining = 0


def _normalize_terminal_semantics(
    output: D7RuntimePairOutput,
    *,
    latched_visual_mode_active: bool,
) -> D7RuntimePairOutput:
    """Derive canonical contract/control fields and their legacy aliases."""

    raw_applicable = output.terminal_contract_applicable
    raw_allowed = output.raw_terminal_contract_allowed if raw_applicable else None
    raw_reject_reason = (
        output.terminal_contract_reject_reason
        if raw_applicable and raw_allowed is False
        else ""
    )
    if not raw_applicable:
        effective_contract_allowed = False
        effective_contract_scope = "not_applicable"
        effective_contract_reason = "terminal_gate_not_applicable"
    elif raw_allowed is True:
        effective_contract_allowed = True
        effective_contract_scope = "raw_terminal_gate"
        effective_contract_reason = "raw_terminal_gate_allowed"
    elif output.terminal_coast_contract_allowed:
        effective_contract_allowed = True
        effective_contract_scope = "bounded_coast"
        effective_contract_reason = (
            output.terminal_coast_contract_reason or "bounded_coast_allowed"
        )
    else:
        effective_contract_allowed = False
        effective_contract_scope = "raw_terminal_gate"
        effective_contract_reason = raw_reject_reason or "raw_terminal_gate_rejected"

    effective_control_authorized = bool(
        output.visual_png_enabled and effective_contract_allowed
    )
    if effective_control_authorized:
        control_scope = effective_contract_scope
        control_reason = "latched_visual_mode_authorized"
    elif not effective_contract_allowed:
        control_scope = "effective_terminal_contract_blocked"
        control_reason = effective_contract_reason
    else:
        control_scope = "latched_visual_mode_inactive"
        control_reason = (
            output.terminal_switch_reject_reason
            or output.raw_terminal_switch_reject_reason
            or output.terminal_handoff_state
            or "latched_visual_mode_inactive"
        )

    return replace(
        output,
        terminal_semantics_version=TERMINAL_SEMANTICS_VERSION,
        terminal_contract_applicable=raw_applicable,
        raw_terminal_contract_allowed=raw_allowed,
        raw_terminal_gate_applicable=raw_applicable,
        raw_terminal_gate_allowed=raw_allowed,
        raw_terminal_gate_reject_reason=raw_reject_reason,
        latched_visual_mode_active=latched_visual_mode_active,
        effective_terminal_contract_allowed=effective_contract_allowed,
        effective_terminal_contract_scope=effective_contract_scope,
        effective_terminal_contract_reason=effective_contract_reason,
        effective_control_authorized=effective_control_authorized,
        effective_control_authorization_scope=control_scope,
        effective_control_authorization_reason=control_reason,
        # Existing consumers keep their field names but now receive one
        # internally consistent effective contract/control view.
        terminal_contract_allowed=effective_contract_allowed,
        terminal_contract_reject_reason=(
            "" if effective_contract_allowed else output.terminal_contract_reject_reason
        ),
        visual_png_enabled=effective_control_authorized,
        terminal_switch_allowed=effective_control_authorized,
    )


def _terminal_handover_timing(
    pair_input: D7RuntimePairInput,
    *,
    timestamp_s: float,
    enabled: bool,
    terminal_active: bool,
) -> dict[str, float | bool | None]:
    timeout_s = pair_input.terminal_timeout_s
    if timeout_s is not None and timeout_s < 0.0:
        raise ValueError("terminal_timeout_s must be nonnegative")
    started_at_s = pair_input.terminal_handover_started_at_s
    if not enabled or started_at_s is None:
        return {
            "wait_duration_s": None,
            "timeout_s": timeout_s if enabled else None,
            "timed_out": False,
        }
    wait_duration_s = max(0.0, float(timestamp_s) - float(started_at_s))
    timed_out = bool(
        pair_input.handover_pending
        and not terminal_active
        and timeout_s is not None
        and wait_duration_s >= timeout_s
    )
    return {
        "wait_duration_s": wait_duration_s,
        "timeout_s": timeout_s,
        "timed_out": timed_out,
    }


def _terminal_lifecycle_context(
    binding: AssignmentGuidanceBinding,
    decision: TerminalPngContractDecision,
    observation: VisionGuidanceObservation | None,
) -> TerminalLifecycleContext:
    return TerminalLifecycleContext(
        resource_id=binding.resource_id,
        assigned_global_track_id=binding.assigned_global_track_id,
        local_track_id=(
            observation.local_track_id
            if observation is not None and observation.local_track_id is not None
            else decision.local_track_id
        ),
        plan_owner_id=binding.owner_node_id,
        plan_version=binding.plan_version,
    )


def _command_saturation_reason(command: PngGuidanceCommand) -> str:
    if not command.control_saturated:
        return ""
    if not command.quality.terminal_switch_allowed:
        return "visual_gate_hold_command"
    return "visual_turn_rate_limit"


def _terminal_delivery_output_fields(
    result: TerminalDeliveryResult,
) -> dict[str, Any]:
    return {
        "terminal_delivery_state": result.state.value,
        "terminal_delivery_reason": result.reason,
        "terminal_visual_lock_measured": result.visual_lock_measured,
        "terminal_using_extrapolation": result.using_extrapolation,
        "terminal_loss_frame_count": result.loss_frame_count,
        "terminal_prediction_age_s": result.measurement_age_s,
        "terminal_blind_elapsed_s": result.blind_elapsed_s,
        "terminal_blind_decay": result.blind_decay,
        "terminal_command_sample_count": result.command_sample_count,
        "terminal_filter_audit_state": result.filter_audit_state.value,
        "terminal_filter_audit_reason": result.filter_audit_reason,
        "terminal_lifecycle_reset": result.lifecycle_reset,
        "terminal_lifecycle_reset_reason": result.lifecycle_reset_reason,
        "terminal_dropout_reason_scope": result.dropout_reason_scope.value,
        "terminal_dropout_reason": result.dropout_reason,
        "terminal_measured_lock_history_available": (
            result.measured_lock_history_available
        ),
        "terminal_measured_lock_ever_established": (
            result.measured_lock_ever_established
        ),
        "terminal_contract_reset_reason": result.contract_reset_reason,
        "terminal_prediction_window_expired": result.prediction_window_expired,
        "terminal_image_innovation_norm_rad": result.image_innovation_norm_rad,
        "terminal_trend_coast_applied": result.trend_coast_applied,
        "terminal_trend_coast_velocity_ned": result.trend_coast_velocity_ned,
    }


def coerce_vision_guidance_observation(
    value: VisionGuidanceObservation | Mapping[str, Any] | Any,
) -> VisionGuidanceObservation:
    """Coerce D5/AirSim/replay-style bbox records into D7 observations."""

    if isinstance(value, VisionGuidanceObservation):
        return value
    metadata = dict(_value(value, ("metadata",), default={}) or {})
    latency_s = _optional_float_value(
        value,
        ("visual_latency_s", "measurement_age_s", "latency_s"),
    )
    if latency_s is not None:
        metadata["visual_latency_s"] = latency_s
    source = _optional_string_value(value, ("source", "detector_source", "replay_source"))
    if source is not None:
        metadata.setdefault("source", source)
    frame_index = _value(value, ("frame_index",), default=None)
    if frame_index is not None:
        metadata.setdefault("frame_index", frame_index)
    for name in _OBSERVATION_METADATA_FIELD_NAMES:
        value_from_record = _value(value, (name,), default=None)
        if value_from_record is not None:
            metadata.setdefault(name, value_from_record)
    return VisionGuidanceObservation(
        timestamp_s=_required_float(value, ("timestamp_s", "timestamp", "t")),
        frame_timestamp_s=_optional_float_value(value, ("frame_timestamp_s", "frame_time_s")),
        bbox_xyxy=_bbox_xyxy(value),
        detection_confidence=_float_value(
            value,
            ("detection_confidence", "confidence", "score"),
            default=1.0,
        ),
        local_track_id=_optional_string_value(value, ("local_track_id", "track_id", "bytetrack_id")),
        assigned_global_track_id=_optional_string_value(
            value,
            ("assigned_global_track_id", "global_track_id", "target_id"),
        ),
        camera_id=_optional_string_value(value, ("camera_id", "camera_name")),
        metadata=metadata,
    )


def guidance_law_semantic_violations(
    output: D7RuntimePairOutput,
) -> tuple[str, ...]:
    """Return canonical configured/candidate/executed-law contract violations.

    This helper is passive: it does not change a gate result or a command.  It
    lets main/D6 reject ambiguous persistence where a configured visual law is
    incorrectly reported as the law actually executed by the vehicle.
    """

    violations: list[str] = []
    visual_laws = {law.value for law in VISUAL_HANDOVER_LAWS}
    configured_terminal = output.configured_terminal_guidance_law
    candidate = output.candidate_guidance_law
    executed = output.executed_guidance_law

    if candidate is not None and configured_terminal is None:
        violations.append("candidate_visual_law_without_visual_configuration")
    elif candidate is not None and candidate != configured_terminal:
        violations.append("candidate_visual_law_mismatches_configuration")

    if output.termination_snapshot:
        if executed is not None:
            violations.append("termination_snapshot_has_executed_law")
        if output.effective_control_authorized:
            violations.append("termination_snapshot_has_effective_control")
        if output.executed_visual_mode_switch:
            violations.append("termination_snapshot_has_visual_mode_switch")
        return tuple(violations)

    if output.effective_control_authorized:
        if not output.effective_terminal_contract_allowed:
            violations.append("effective_control_without_effective_contract")
        if not output.latched_visual_mode_active:
            violations.append("effective_control_without_visual_latch")
        if output.mode != GuidanceMode.VISION_TERMINAL:
            violations.append("effective_control_outside_visual_mode")
        if candidate is None:
            violations.append("effective_control_without_candidate_law")
        if executed not in visual_laws:
            violations.append("effective_control_without_executed_visual_law")
        if candidate is not None and executed != candidate:
            violations.append("executed_visual_law_mismatches_candidate")
        if output.selected_velocity_ned is None:
            violations.append("effective_control_without_selected_velocity")
    else:
        if output.mode == GuidanceMode.VISION_TERMINAL:
            violations.append("visual_mode_without_effective_control")
        if executed in visual_laws:
            violations.append("executed_visual_law_without_effective_control")
        if output.selected_velocity_ned is not None:
            violations.append("selected_visual_velocity_without_effective_control")

    if output.executed_visual_mode_switch and not output.effective_control_authorized:
        violations.append("visual_mode_switch_without_effective_control")
    return tuple(violations)


def summarize_runtime_bus_outputs(outputs: Iterable[D7RuntimePairOutput]) -> dict[str, Any]:
    """Summarize D7 runtime bus fields without rerunning guidance or control."""

    rows = list(outputs)
    live_rows = [row for row in rows if not row.termination_snapshot]
    contract_rejects: Counter[str] = Counter()
    raw_gate_rejects: Counter[str] = Counter()
    switch_rejects: Counter[str] = Counter()
    raw_switch_rejects: Counter[str] = Counter()
    guidance_laws: Counter[str] = Counter()
    requested_guidance_laws: Counter[str] = Counter()
    configured_midcourse_laws: Counter[str] = Counter()
    configured_terminal_laws: Counter[str] = Counter()
    guidance_law_semantic_violation_reasons: Counter[str] = Counter()
    guidance_modes: Counter[str] = Counter()
    mode_transition_reasons: Counter[str] = Counter()
    guidance_law_transition_reasons: Counter[str] = Counter()
    command_saturation_reasons: Counter[str] = Counter()
    handoff_states: Counter[str] = Counter()
    d4_actions: Counter[str] = Counter()
    d4_action_block_reasons: Counter[str] = Counter()
    d5_states: Counter[str] = Counter()
    d5_lock_reasons: Counter[str] = Counter()
    secondary_capability_classes: Counter[str] = Counter()
    secondary_readiness_classes: Counter[str] = Counter()
    detect_registration_outcomes: Counter[str] = Counter()
    detect_registration_reject_reasons: Counter[str] = Counter()
    tracker_backends: Counter[str] = Counter()
    plan_versions: Counter[str] = Counter()
    candidate_laws: Counter[str] = Counter()
    coalition_gate_rejects: Counter[str] = Counter()
    coalition_commit_states: Counter[str] = Counter()
    coalition_commit_gate_rejects: Counter[str] = Counter()
    terminal_delivery_states: Counter[str] = Counter()
    terminal_delivery_reasons: Counter[str] = Counter()
    terminal_filter_audit_states: Counter[str] = Counter()
    terminal_filter_audit_reasons: Counter[str] = Counter()
    ttc_reject_reasons: Counter[str] = Counter()
    member_roles: Counter[str] = Counter()
    wave_ids: Counter[str] = Counter()
    coordination_modes: Counter[str] = Counter()
    activation_states: Counter[str] = Counter()
    terminal_authorization_scopes: Counter[str] = Counter()
    effective_contract_scopes: Counter[str] = Counter()
    effective_control_scopes: Counter[str] = Counter()
    dropout_reason_scopes: Counter[str] = Counter()
    contract_reset_reasons: Counter[str] = Counter()
    termination_statuses: Counter[str] = Counter(
        row.termination_status or "unspecified"
        for row in rows
        if row.termination_snapshot
    )
    termination_reasons: Counter[str] = Counter(
        row.termination_reason
        for row in rows
        if row.termination_snapshot and row.termination_reason
    )
    for row in live_rows:
        if row.executed_guidance_law is not None:
            guidance_laws[row.executed_guidance_law] += 1
        requested_guidance_laws[row.configured_guidance_law] += 1
        configured_midcourse_laws[row.configured_midcourse_guidance_law] += 1
        if row.configured_terminal_guidance_law is not None:
            configured_terminal_laws[row.configured_terminal_guidance_law] += 1
        guidance_law_semantic_violation_reasons.update(
            guidance_law_semantic_violations(row)
        )
        guidance_modes[row.mode.value] += 1
        handoff_states[row.terminal_handoff_state or row.mode.value] += 1
        if row.d4_action:
            d4_actions[row.d4_action] += 1
        if row.d4_action_block_reason:
            d4_action_block_reasons[row.d4_action_block_reason] += 1
        if row.d5_decision_state:
            d5_states[row.d5_decision_state] += 1
        if row.d5_lock_consistency_reason:
            d5_lock_reasons[row.d5_lock_consistency_reason] += 1
        if row.secondary_capability_class:
            secondary_capability_classes[row.secondary_capability_class] += 1
        if row.secondary_readiness_class:
            secondary_readiness_classes[row.secondary_readiness_class] += 1
        if row.detect_registration_outcome:
            detect_registration_outcomes[row.detect_registration_outcome] += 1
        detect_registration_reject_reasons.update(row.detect_registration_reject_reasons)
        if row.tracker_backend:
            tracker_backends[row.tracker_backend] += 1
        plan_versions[str(row.plan_version)] += 1
        if row.png_guidance_law_candidate:
            candidate_laws[row.png_guidance_law_candidate] += 1
        if row.coalition_gate_reject_reason:
            coalition_gate_rejects[row.coalition_gate_reject_reason] += 1
        if row.coalition_commit_state:
            coalition_commit_states[row.coalition_commit_state] += 1
        if row.coalition_commit_gate_reject_reason:
            coalition_commit_gate_rejects[row.coalition_commit_gate_reject_reason] += 1
        if row.terminal_delivery_state:
            terminal_delivery_states[row.terminal_delivery_state] += 1
        if row.terminal_delivery_reason:
            terminal_delivery_reasons[row.terminal_delivery_reason] += 1
        if row.terminal_filter_audit_state:
            terminal_filter_audit_states[row.terminal_filter_audit_state] += 1
        if row.terminal_filter_audit_reason:
            terminal_filter_audit_reasons[row.terminal_filter_audit_reason] += 1
        if row.ttc_reject_reason:
            ttc_reject_reasons[row.ttc_reject_reason] += 1
        member_roles[row.member_role] += 1
        wave_ids[str(row.wave_id)] += 1
        coordination_modes[row.coordination_mode] += 1
        activation_states[row.activation_state] += 1
        terminal_authorization_scopes[row.terminal_authorization_scope] += 1
        effective_contract_scopes[row.effective_terminal_contract_scope] += 1
        effective_control_scopes[row.effective_control_authorization_scope] += 1
        dropout_reason_scopes[row.terminal_dropout_reason_scope] += 1
        if row.terminal_contract_reset_reason:
            contract_reset_reasons[row.terminal_contract_reset_reason] += 1
        if row.terminal_contract_reject_reason:
            contract_rejects[row.terminal_contract_reject_reason] += 1
        if row.raw_terminal_gate_reject_reason:
            raw_gate_rejects[row.raw_terminal_gate_reject_reason] += 1
        if row.terminal_switch_reject_reason:
            switch_rejects[row.terminal_switch_reject_reason] += 1
        if row.raw_terminal_switch_reject_reason:
            raw_switch_rejects[row.raw_terminal_switch_reject_reason] += 1
        if row.mode_transition and row.mode_transition_reason:
            mode_transition_reasons[row.mode_transition_reason] += 1
        if row.guidance_law_transition and row.guidance_law_transition_reason:
            guidance_law_transition_reasons[row.guidance_law_transition_reason] += 1
        if row.command_saturated and row.command_saturation_reason:
            command_saturation_reasons[row.command_saturation_reason] += 1

    effective_control_authorized_count = sum(
        1 for row in live_rows if row.effective_control_authorized
    )
    visual_png_switch_count = effective_control_authorized_count
    gate_sample_rows = [row for row in live_rows if row.camera_quality_gate_passed is not None]
    closing_speed_gate_rows = [
        row for row in live_rows if row.closing_speed_gate_passed is not None
    ]
    ttc_values = [row.ttc_s for row in live_rows if row.ttc_s is not None]
    terminal_range_values = [
        row.terminal_range_m for row in live_rows if row.terminal_range_m is not None
    ]
    closing_speed_values = [
        row.closing_speed_mps for row in live_rows if row.closing_speed_mps is not None
    ]
    bbox_values = [row.bbox_area_ratio for row in live_rows if row.bbox_area_ratio is not None]
    edge_values = [row.edge_margin_ratio for row in live_rows if row.edge_margin_ratio is not None]
    measurement_age_values = [
        row.measurement_age_s for row in live_rows if row.measurement_age_s is not None
    ]
    projection_depth_values = [
        row.projection_depth_m for row in live_rows if row.projection_depth_m is not None
    ]
    reprojection_error_values = [
        row.reprojection_error_px for row in live_rows if row.reprojection_error_px is not None
    ]
    mahalanobis_values = [
        row.mahalanobis_d2 for row in live_rows if row.mahalanobis_d2 is not None
    ]
    covariance_trace_values = [
        row.covariance_px_trace for row in live_rows if row.covariance_px_trace is not None
    ]
    projection_covariance_trace_values = [
        row.projection_covariance_px_trace
        for row in live_rows
        if row.projection_covariance_px_trace is not None
    ]
    bbox_area_px_values = [
        row.bbox_area_px for row in live_rows if row.bbox_area_px is not None
    ]
    association_probability_values = [
        row.association_probability
        for row in live_rows
        if row.association_probability is not None
    ]
    mot_history_values = [
        float(row.mot_history_length)
        for row in live_rows
        if row.mot_history_length is not None
    ]
    los_rate_abs_values = [
        abs(row.los_rate_radps)
        for row in gate_sample_rows
    ]
    filtered_los_rate_abs_values = [
        abs(row.filtered_los_rate_radps)
        for row in gate_sample_rows
        if row.filtered_los_rate_radps is not None
    ]
    raw_los_rate_abs_values = [
        abs(row.raw_los_rate_radps)
        for row in gate_sample_rows
        if row.raw_los_rate_radps is not None
    ]
    height_delta_values = [
        row.height_delta_m for row in live_rows if row.height_delta_m is not None
    ]
    range_3d_values = [row.range_3d_m for row in live_rows if row.range_3d_m is not None]
    pn3d_los_rate_values = [
        row.pn3d_los_rate_norm_radps
        for row in live_rows
        if row.pn3d_los_rate_norm_radps is not None
    ]
    terminal_wait_values = [
        row.terminal_wait_duration_s
        for row in live_rows
        if row.terminal_wait_duration_s is not None
    ]
    raw_switch_rows = [
        row for row in live_rows if row.raw_terminal_switch_allowed is not None
    ]
    saturation_rows = [row for row in live_rows if row.command_saturated is not None]
    raw_gate_rows = [row for row in live_rows if row.raw_terminal_gate_applicable]
    contract_rows = [row for row in live_rows if row.terminal_contract_applicable]
    summary = {
        "boundary": D7_RUNTIME_BUS_BOUNDARY,
        "terminal_semantics_version": TERMINAL_SEMANTICS_VERSION,
        "guidance_law_semantics_version": GUIDANCE_LAW_SEMANTICS_VERSION,
        "sample_count": len(rows),
        "live_control_sample_count": len(live_rows),
        "termination_snapshot_count": len(rows) - len(live_rows),
        "termination_status_counts": dict(termination_statuses),
        "termination_reason_counts": dict(termination_reasons),
        "termination_prior_visual_mode_active_count": sum(
            1
            for row in rows
            if row.termination_snapshot
            and row.termination_prior_latched_visual_mode_active
        ),
        "termination_prior_effective_control_authorized_count": sum(
            1
            for row in rows
            if row.termination_snapshot
            and row.termination_prior_effective_control_authorized
        ),
        "control_context_count": len({row.control_context_id for row in rows}),
        "control_context_ids": sorted({row.control_context_id for row in rows}),
        "resource_ids": sorted({row.resource_id for row in rows}),
        "assigned_global_track_ids": sorted({row.assigned_global_track_id for row in rows}),
        "assignment_ids": sorted({row.assignment_id for row in rows if row.assignment_id is not None}),
        "plan_ids": sorted({row.plan_id for row in rows}),
        "plan_version_counts": dict(plan_versions),
        "coalition_ids": sorted({row.coalition_id for row in rows if row.coalition_id}),
        "coalition_version_counts": dict(
            Counter(
                str(row.coalition_version)
                for row in rows
                if row.coalition_version is not None
            )
        ),
        "coalition_gate_applicable_count": sum(
            1 for row in live_rows if row.coalition_gate_applicable
        ),
        "coalition_gate_allowed_count": sum(
            1 for row in live_rows if row.coalition_gate_allowed is True
        ),
        "coalition_gate_reject_reasons": dict(coalition_gate_rejects),
        "coalition_commit_gate_applicable_count": sum(
            1 for row in live_rows if row.coalition_commit_gate_applicable
        ),
        "coalition_commit_gate_allowed_count": sum(
            1 for row in live_rows if row.coalition_commit_gate_allowed is True
        ),
        "coalition_commit_gate_reject_count": sum(coalition_commit_gate_rejects.values()),
        "coalition_commit_gate_reject_reasons": dict(coalition_commit_gate_rejects),
        "coalition_commit_state_counts": dict(coalition_commit_states),
        "coalition_lease_valid_count": sum(
            1 for row in live_rows if row.coalition_lease_valid is True
        ),
        "coalition_resource_required_count": sum(
            1 for row in live_rows if row.coalition_resource_required is True
        ),
        "coalition_resource_acked_count": sum(
            1 for row in live_rows if row.coalition_resource_acked is True
        ),
        "terminal_delivery_state_counts": dict(terminal_delivery_states),
        "terminal_delivery_reason_counts": dict(terminal_delivery_reasons),
        "terminal_filter_audit_state_counts": dict(terminal_filter_audit_states),
        "terminal_filter_audit_reason_counts": dict(terminal_filter_audit_reasons),
        "terminal_dropout_reason_scope_counts": dict(dropout_reason_scopes),
        "terminal_contract_reset_reason_counts": dict(contract_reset_reasons),
        "terminal_lifecycle_reset_count": sum(
            1 for row in live_rows if row.terminal_lifecycle_reset
        ),
        "terminal_trend_coast_applied_count": sum(
            1 for row in live_rows if row.terminal_trend_coast_applied
        ),
        "ttc_valid_count": sum(1 for row in live_rows if row.ttc_valid is True),
        "ttc_reject_reasons": dict(ttc_reject_reasons),
        "terminal_extrapolation_count": sum(
            1 for row in live_rows if row.terminal_using_extrapolation
        ),
        "terminal_reacquired_count": sum(
            1
            for row in live_rows
            if row.terminal_delivery_state == TerminalDeliveryState.REACQUIRED.value
        ),
        "terminal_visual_coast_expired_count": sum(
            1
            for row in live_rows
            if row.terminal_delivery_reason == "terminal_visual_lost_after_coast"
        ),
        "terminal_prediction_window_expired_count": sum(
            1
            for row in live_rows
            if row.terminal_delivery_reason
            == "terminal_visual_prediction_window_expired"
        ),
        "member_role_counts": dict(member_roles),
        "wave_id_counts": dict(wave_ids),
        "coordination_mode_counts": dict(coordination_modes),
        "activation_state_counts": dict(activation_states),
        "terminal_authorization_scope_counts": dict(terminal_authorization_scopes),
        "raw_terminal_gate_applicable_count": len(raw_gate_rows),
        "raw_terminal_gate_allowed_count": sum(
            1 for row in raw_gate_rows if row.raw_terminal_gate_allowed is True
        ),
        "raw_terminal_gate_reject_count": sum(
            1 for row in raw_gate_rows if row.raw_terminal_gate_allowed is False
        ),
        "raw_terminal_gate_reject_reasons": dict(raw_gate_rejects),
        "effective_terminal_contract_allowed_count": sum(
            1 for row in live_rows if row.effective_terminal_contract_allowed
        ),
        "effective_terminal_contract_scope_counts": dict(effective_contract_scopes),
        "latched_visual_mode_active_count": sum(
            1 for row in live_rows if row.latched_visual_mode_active
        ),
        "effective_control_authorized_count": effective_control_authorized_count,
        "visual_control_active_count": effective_control_authorized_count,
        "effective_control_authorization_scope_counts": dict(effective_control_scopes),
        "visual_mode_entry_transition_count": sum(
            1
            for row in live_rows
            if row.executed_visual_mode_switch
        ),
        "executed_visual_mode_switch_count": sum(
            1 for row in live_rows if row.executed_visual_mode_switch
        ),
        "guidance_law_semantic_violation_count": sum(
            guidance_law_semantic_violation_reasons.values()
        ),
        "guidance_law_semantic_violation_reasons": dict(
            guidance_law_semantic_violation_reasons
        ),
        "per_primary_authorization_active_count": sum(
            1 for row in live_rows if row.per_primary_authorization_active
        ),
        "coalition_visual_completion_bypassed_count": sum(
            1 for row in live_rows if row.coalition_visual_completion_bypassed
        ),
        "bypassed_arrival_only_count": sum(
            1 for row in live_rows if row.bypassed_arrival_only
        ),
        "visual_png_switch_count": visual_png_switch_count,
        "visual_png_candidate_count": sum(
            1 for row in live_rows if row.png_guidance_law_candidate is not None
        ),
        "terminal_handover_pending_count": sum(
            1 for row in live_rows if row.terminal_handover_pending
        ),
        "terminal_locked_input_count": sum(1 for row in live_rows if row.terminal_locked),
        "terminal_contract_applicable_count": len(contract_rows),
        "terminal_contract_allowed_count": sum(
            1 for row in contract_rows if row.terminal_contract_allowed
        ),
        "terminal_coast_contract_allowed_count": sum(
            1 for row in contract_rows if row.terminal_coast_contract_allowed
        ),
        "terminal_contract_reject_count": sum(contract_rejects.values()),
        "terminal_contract_reject_reasons": dict(contract_rejects),
        "terminal_switch_allowed_count": effective_control_authorized_count,
        "terminal_switch_reject_count": sum(switch_rejects.values()),
        "terminal_switch_reject_reasons": dict(switch_rejects),
        "backward_compatible_aliases": {
            "requested_guidance_law": "configured_guidance_law",
            "png_guidance_law_candidate": "candidate_guidance_law",
            "guidance_law": "executed_guidance_law_live_samples_only",
            "terminal_contract_applicable": "raw_terminal_gate_applicable",
            "raw_terminal_contract_allowed": "raw_terminal_gate_allowed",
            "terminal_contract_allowed": "effective_terminal_contract_allowed",
            "terminal_switch_allowed": "effective_control_authorized",
            "terminal_control_allowed": "effective_control_authorized",
            "visual_png_enabled": "effective_control_authorized",
            "visual_png_switch": "effective_control_authorized",
            "terminal_contract_allowed_count": (
                "effective_terminal_contract_allowed_count"
            ),
            "terminal_switch_allowed_count": "effective_control_authorized_count",
            "visual_png_switch_count": "effective_control_authorized_count",
        },
        "main_persistence_contract": {
            "configured_law_field": "configured_guidance_law",
            "candidate_law_field": "candidate_guidance_law",
            "executed_law_field": "executed_guidance_law",
            "raw_gate_field": "raw_terminal_gate_allowed",
            "latched_mode_field": "latched_visual_mode_active",
            "effective_control_field": "effective_control_authorized",
            "visual_control_active_field": "visual_control_active",
            "visual_mode_switch_field": "executed_visual_mode_switch",
            "legacy_visual_png_switch_is_active_sample_not_transition": True,
        },
        "raw_terminal_switch_observed_count": len(raw_switch_rows),
        "raw_terminal_switch_allowed_count": sum(
            1 for row in raw_switch_rows if row.raw_terminal_switch_allowed
        ),
        "raw_terminal_switch_allowed_rate": _bool_rate(
            row.raw_terminal_switch_allowed for row in raw_switch_rows
        ),
        "raw_terminal_switch_reject_reasons": dict(raw_switch_rejects),
        "terminal_switch_allowed_rate": (
            visual_png_switch_count / len(live_rows) if live_rows else 0.0
        ),
        "terminal_timeout_count": sum(1 for row in live_rows if row.terminal_timeout),
        "mode_transition_count": sum(1 for row in live_rows if row.mode_transition),
        "mode_transition_reasons": dict(mode_transition_reasons),
        "guidance_law_transition_count": sum(
            1 for row in live_rows if row.guidance_law_transition
        ),
        "guidance_law_transition_reasons": dict(guidance_law_transition_reasons),
        "command_saturation_observed_count": len(saturation_rows),
        "command_saturation_count": sum(1 for row in saturation_rows if row.command_saturated),
        "command_saturation_rate": _bool_rate(row.command_saturated for row in saturation_rows),
        "command_saturation_reasons": dict(command_saturation_reasons),
        "d4_action_block_count": sum(d4_action_block_reasons.values()),
        "d4_action_block_reasons": dict(d4_action_block_reasons),
        "d5_lock_consistent_count": sum(
            1 for row in live_rows if row.d5_lock_consistent is True
        ),
        "d5_lock_consistent_rate": _bool_rate(
            row.d5_lock_consistent for row in live_rows
        ),
        "d5_lock_consistency_reasons": dict(d5_lock_reasons),
        "d3_plan_version_consistent_count": sum(
            1 for row in live_rows if row.d3_plan_version_consistent is True
        ),
        "d3_plan_version_consistent_rate": _bool_rate(
            row.d3_plan_version_consistent for row in live_rows
        ),
        "d3_owner_consistent_count": sum(
            1 for row in live_rows if row.d3_owner_consistent is True
        ),
        "d3_owner_consistent_rate": _bool_rate(
            row.d3_owner_consistent for row in live_rows
        ),
        "d3_owner_version_consistent_count": sum(
            1 for row in live_rows if row.d3_owner_version_consistent is True
        ),
        "d3_owner_version_consistent_rate": _bool_rate(
            row.d3_owner_version_consistent for row in live_rows
        ),
        "secondary_capability_class_counts": dict(secondary_capability_classes),
        "secondary_readiness_class_counts": dict(secondary_readiness_classes),
        "detect_registration_outcome_counts": dict(detect_registration_outcomes),
        "detect_registration_reject_reasons": dict(detect_registration_reject_reasons),
        "projection_valid_rate": _bool_rate(row.projection_valid for row in live_rows),
        "d5_gate_pass_rate": _bool_rate(row.gate_pass for row in live_rows),
        "tracker_backend_counts": dict(tracker_backends),
        "threshold_advisory_version": DEFAULT_CALIBRATION_THRESHOLD_VERSION,
        "terminal_dwell_active_count": sum(
            1 for row in live_rows if row.terminal_dwell_active
        ),
        "terminal_release_grace_active_count": sum(
            1 for row in live_rows if row.terminal_release_grace_active
        ),
        "terminal_reacquire_grace_active_count": sum(
            1 for row in live_rows if row.terminal_reacquire_grace_active
        ),
        "los_rate_clamped_count": sum(1 for row in live_rows if row.los_rate_clamped),
        "los_rate_outlier_rejected_count": sum(
            1 for row in live_rows if row.los_rate_outlier_rejected
        ),
        "pn3d_benchmark_sample_count": sum(
            1 for row in live_rows if row.pn3d_benchmark_only
        ),
        "pn3d_default_api_replaced": any(
            row.pn3d_default_api_replaced for row in live_rows
        ),
        "terminal_contract_allowed_rate": (
            sum(1 for row in contract_rows if row.terminal_contract_allowed) / len(contract_rows)
            if contract_rows
            else 0.0
        ),
        "camera_quality_gate_pass_rate": _bool_rate(
            row.camera_quality_gate_passed for row in gate_sample_rows
        ),
        "los_quality_gate_pass_rate": _bool_rate(
            row.los_quality_gate_passed for row in gate_sample_rows
        ),
        "closing_speed_gate_observed_count": len(closing_speed_gate_rows),
        "closing_speed_gate_pass_count": sum(
            1 for row in closing_speed_gate_rows if row.closing_speed_gate_passed
        ),
        "closing_speed_gate_pass_rate": _bool_rate(
            row.closing_speed_gate_passed for row in closing_speed_gate_rows
        ),
        "maneuver_margin_gate_pass_rate": _bool_rate(
            row.maneuver_margin_gate_passed for row in gate_sample_rows
        ),
        "guidance_law_counts": dict(guidance_laws),
        "executed_guidance_law_counts": dict(guidance_laws),
        "requested_guidance_law_counts": dict(requested_guidance_laws),
        "configured_guidance_law_counts": dict(requested_guidance_laws),
        "configured_midcourse_guidance_law_counts": dict(
            configured_midcourse_laws
        ),
        "configured_terminal_guidance_law_counts": dict(
            configured_terminal_laws
        ),
        "guidance_mode_counts": dict(guidance_modes),
        "terminal_handoff_state_counts": dict(handoff_states),
        "d4_action_counts": dict(d4_actions),
        "d5_decision_state_counts": dict(d5_states),
        "png_guidance_law_candidate_counts": dict(candidate_laws),
        "candidate_guidance_law_counts": dict(candidate_laws),
    }
    summary.update(_numeric_summary("ttc_s", ttc_values))
    summary.update(_numeric_summary("terminal_range_m", terminal_range_values))
    summary.update(_numeric_summary("closing_speed_mps", closing_speed_values))
    summary.update(_numeric_summary("bbox_area_ratio", bbox_values))
    summary.update(_numeric_summary("edge_margin_ratio", edge_values))
    summary.update(_numeric_summary("measurement_age_s", measurement_age_values))
    summary.update(_numeric_summary("projection_depth_m", projection_depth_values))
    summary.update(_numeric_summary("reprojection_error_px", reprojection_error_values))
    summary.update(_numeric_summary("mahalanobis_d2", mahalanobis_values))
    summary.update(_numeric_summary("covariance_px_trace", covariance_trace_values))
    summary.update(_numeric_summary("projection_covariance_px_trace", projection_covariance_trace_values))
    summary.update(_numeric_summary("bbox_area_px", bbox_area_px_values))
    summary.update(_numeric_summary("association_probability", association_probability_values))
    summary.update(_numeric_summary("mot_history_length", mot_history_values))
    summary.update(_numeric_summary("los_rate_abs_radps", los_rate_abs_values))
    summary.update(_numeric_summary("filtered_los_rate_abs_radps", filtered_los_rate_abs_values))
    summary.update(_numeric_summary("raw_los_rate_abs_radps", raw_los_rate_abs_values))
    summary.update(_numeric_summary("height_delta_m", height_delta_values))
    summary.update(_numeric_summary("range_3d_m", range_3d_values))
    summary.update(_numeric_summary("pn3d_los_rate_norm_radps", pn3d_los_rate_values))
    summary.update(_numeric_summary("terminal_wait_duration_s", terminal_wait_values))
    return summary


def _apply_terminal_latch(
    latch: _TerminalLatchState,
    *,
    candidate_allowed: bool,
    candidate_reject_reason: str,
    config: PngGuidanceConfig,
) -> dict[str, Any]:
    if candidate_allowed:
        latch.candidate_allowed_streak += 1
        latch.candidate_rejected_streak = 0
        if latch.reacquire_grace_remaining > 0:
            latch.reacquire_grace_remaining -= 1
            return {
                "visual_png_enabled": False,
                "terminal_switch_reject_reason": "reacquire_grace_active",
                "terminal_handoff_state": "reacquire_grace",
                "terminal_dwell_active": False,
                "terminal_release_grace_active": False,
                "terminal_reacquire_grace_active": True,
            }
        if latch.candidate_allowed_streak < config.terminal_dwell_frames:
            return {
                "visual_png_enabled": False,
                "terminal_switch_reject_reason": "terminal_dwell_active",
                "terminal_handoff_state": "terminal_dwell",
                "terminal_dwell_active": True,
                "terminal_release_grace_active": False,
                "terminal_reacquire_grace_active": False,
            }
        latch.terminal_active = True
        return {
            "visual_png_enabled": True,
            "terminal_switch_reject_reason": "",
            "terminal_handoff_state": "vision_terminal",
            "terminal_dwell_active": False,
            "terminal_release_grace_active": False,
            "terminal_reacquire_grace_active": False,
        }

    latch.candidate_allowed_streak = 0
    if latch.terminal_active:
        latch.candidate_rejected_streak += 1
        if latch.candidate_rejected_streak < config.terminal_release_frames:
            return {
                "visual_png_enabled": False,
                "terminal_switch_reject_reason": candidate_reject_reason or "terminal_release_grace_active",
                "terminal_handoff_state": "terminal_release_grace",
                "terminal_dwell_active": False,
                "terminal_release_grace_active": True,
                "terminal_reacquire_grace_active": False,
            }
        latch.terminal_active = False
    else:
        latch.candidate_rejected_streak = 0
    return {
        "visual_png_enabled": False,
        "terminal_switch_reject_reason": candidate_reject_reason,
        "terminal_handoff_state": "switch_gate_rejected",
        "terminal_dwell_active": False,
        "terminal_release_grace_active": False,
        "terminal_reacquire_grace_active": False,
    }


def _common_output_kwargs(
    *,
    timestamp_s: float,
    binding: AssignmentGuidanceBinding,
    control_context_id: str,
    decision: TerminalPngContractDecision,
    terminal_handover_pending: bool,
    terminal_locked: bool,
    observation: VisionGuidanceObservation | None,
    terminal_association: Mapping[str, Any] | Any | None,
    relative_position_ned: tuple[float, float, float] | None,
    relative_velocity_ned: tuple[float, float, float] | None,
    navigation_constant: float,
    requested_guidance_law: str,
    terminal_wait_duration_s: float | None,
    terminal_timeout_s: float | None,
    terminal_timeout: bool,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp_s": timestamp_s,
        "resource_id": binding.resource_id,
        "assigned_global_track_id": binding.assigned_global_track_id,
        "control_context_id": control_context_id,
        "terminal_contract_allowed": decision.allowed,
        "terminal_contract_reject_reason": decision.reject_reason,
        "raw_terminal_contract_allowed": decision.allowed,
        "requested_guidance_law": requested_guidance_law,
        "terminal_wait_duration_s": terminal_wait_duration_s,
        "terminal_timeout_s": terminal_timeout_s,
        "terminal_timeout": terminal_timeout,
        "plan_id": binding.plan_id,
        "plan_version": binding.plan_version,
        "track_version": binding.track_version,
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "member_role": binding.member_role,
        "wave_id": binding.wave_id,
        "coordination_mode": binding.coordination_mode,
        "arrival_window_start_s": binding.arrival_window_start_s,
        "arrival_window_end_s": binding.arrival_window_end_s,
        "activation_state": binding.activation_state,
        "terminal_authorization_scope": decision.terminal_authorization_scope,
        "arrival_coordination_required": decision.arrival_coordination_required,
        "per_primary_authorization_active": decision.per_primary_authorization_active,
        "coalition_visual_completion_bypassed": decision.coalition_visual_completion_bypassed,
        "bypassed_arrival_only": decision.bypassed_arrival_only,
        "activation_plan_version": binding.activation_plan_version,
        "activation_track_version": binding.activation_track_version,
        "activation_coalition_version": binding.activation_coalition_version,
        "coalition_gate_applicable": decision.coalition_gate_applicable,
        "coalition_gate_allowed": decision.coalition_gate_allowed,
        "coalition_gate_reject_reason": decision.coalition_gate_reject_reason,
        "d4_coalition_id": decision.d4_coalition_id,
        "d4_coalition_version": decision.d4_coalition_version,
        "d5_coalition_id": decision.d5_coalition_id,
        "d5_coalition_version": decision.d5_coalition_version,
        "d5_coalition_visual_complete": decision.d5_coalition_visual_complete,
        "d5_coalition_support_count": decision.d5_coalition_support_count,
        "d5_required_resource_count": decision.d5_required_resource_count,
        "d5_coalition_conflict_state": decision.d5_coalition_conflict_state,
        "coalition_commit_gate_applicable": decision.coalition_commit_gate_applicable,
        "coalition_commit_gate_allowed": decision.coalition_commit_gate_allowed,
        "coalition_commit_gate_reject_reason": decision.coalition_commit_gate_reject_reason,
        "coalition_commit_state": decision.coalition_commit_state,
        "coalition_epoch": decision.coalition_epoch,
        "coalition_lease_expires_at_s": decision.coalition_lease_expires_at_s,
        "coalition_lease_valid": decision.coalition_lease_valid,
        "coalition_required_member_ids": decision.coalition_required_member_ids,
        "coalition_acked_member_ids": decision.coalition_acked_member_ids,
        "coalition_resource_required": decision.coalition_resource_required,
        "coalition_resource_acked": decision.coalition_resource_acked,
        "commit_plan_id": decision.commit_plan_id,
        "commit_plan_version": decision.commit_plan_version,
        "commit_coalition_id": decision.commit_coalition_id,
        "commit_coalition_version": decision.commit_coalition_version,
        "terminal_range_m": _terminal_range_m(relative_position_ned),
        "assignment_id": binding.assignment_id,
        "owner_node_id": binding.owner_node_id,
        "d4_target_node_id": decision.d4_target_node_id,
        "d4_action": decision.d4_action,
        "d4_action_block_reason": decision.d4_action_block_reason,
        "d4_visual_png_allowed": decision.d4_visual_png_allowed,
        "secondary_capability_class": decision.secondary_capability_class,
        "secondary_readiness_class": decision.secondary_readiness_class,
        "d3_plan_version_consistent": decision.d3_plan_version_consistent,
        "d3_owner_consistent": decision.d3_owner_consistent,
        "d3_owner_version_consistent": decision.d3_owner_version_consistent,
        "d5_decision_state": decision.d5_decision_state,
        "d5_lock_consistent": decision.d5_lock_consistent,
        "d5_lock_consistency_reason": decision.d5_lock_consistency_reason,
        "d5_assigned_global_track_id": decision.d5_assigned_global_track_id,
        "d5_assignment_version": decision.d5_assignment_version,
        "d5_plan_version": decision.d5_plan_version,
        "local_track_id": decision.local_track_id,
        "terminal_handover_pending": terminal_handover_pending,
        "terminal_locked": terminal_locked,
        **_observation_output_fields(observation),
        **_d5_registration_output_fields(terminal_association, observation),
        **_pn3d_output_fields(
            relative_position_ned=relative_position_ned,
            relative_velocity_ned=relative_velocity_ned,
            navigation_constant=navigation_constant,
        ),
        "metadata": metadata,
    }


def _observation_output_fields(
    observation: VisionGuidanceObservation | None,
) -> dict[str, Any]:
    if observation is None:
        return {}
    return {
        "detection_confidence": observation.detection_confidence,
        "bbox_xyxy": observation.bbox_xyxy,
        "camera_id": observation.camera_id,
        "frame_timestamp_s": observation.frame_timestamp_s,
        "visual_latency_s": _metadata_float(observation.metadata, "visual_latency_s"),
    }


def _d5_registration_output_fields(
    terminal_association: Mapping[str, Any] | Any | None,
    observation: VisionGuidanceObservation | None,
) -> dict[str, Any]:
    sources: tuple[Any, ...] = (
        terminal_association,
        _value(terminal_association, ("metadata",), default=None),
        observation,
        observation.metadata if observation is not None else None,
    )
    covariance_px = _first_value(sources, ("covariance_px",))
    projection_covariance_px = _first_value(sources, ("projection_covariance_px",))
    measurement_age_s = _first_float_value(
        sources,
        ("measurement_age_s", "visual_latency_s", "latency_s"),
    )
    return {
        "detect_registration_outcome": _first_string_value(
            sources,
            ("detect_registration_outcome", "registration_outcome"),
        ),
        "detect_registration_reject_reasons": _first_string_tuple_value(
            sources,
            ("detect_registration_reject_reasons", "registration_reject_reasons"),
        ),
        "measurement_age_s": measurement_age_s,
        "projection_valid": _first_bool_value(sources, ("projection_valid",)),
        "projection_reason": _first_string_value(sources, ("projection_reason",)),
        "projection_depth_m": _first_float_value(sources, ("projection_depth_m",)),
        "reprojection_error_px": _first_float_value(
            sources,
            ("reprojection_error_px", "pixel_error_px", "reprojection_error"),
        ),
        "mahalanobis_d2": _first_float_value(sources, ("mahalanobis_d2",)),
        "gate_pass": _first_bool_value(sources, ("gate_pass",)),
        "covariance_px_trace": _matrix_trace(covariance_px),
        "projection_covariance_px_trace": _matrix_trace(projection_covariance_px),
        "camera_pose_source": _first_string_value(sources, ("camera_pose_source",)),
        "calibration_health": _first_string_value(sources, ("calibration_health",)),
        "drift_warning": _first_bool_value(sources, ("drift_warning",)),
        "tracker_backend": _first_string_value(sources, ("tracker_backend", "yolo_tracker_backend")),
        "requested_tracker_backend": _first_string_value(sources, ("requested_tracker_backend",)),
        "tracker_id_scope": _first_string_value(sources, ("tracker_id_scope",)),
        "mot_history_length": _first_int_value(sources, ("mot_history_length", "track_history_length")),
        "yolo_class_id": _first_int_value(sources, ("yolo_class_id", "class_id")),
        "yolo_class_name": _first_string_value(sources, ("yolo_class_name", "class_name")),
        "bbox_area_px": _first_float_value(sources, ("bbox_area_px",)),
        "association_probability": _first_float_value(sources, ("association_probability",)),
    }


def _pn3d_output_fields(
    *,
    relative_position_ned: tuple[float, float, float] | None,
    relative_velocity_ned: tuple[float, float, float] | None,
    navigation_constant: float,
) -> dict[str, Any]:
    if relative_position_ned is None or relative_velocity_ned is None:
        return {}
    benchmark = compute_three_dimensional_pn_benchmark(
        relative_position_ned=relative_position_ned,
        relative_velocity_ned=relative_velocity_ned,
        navigation_constant=navigation_constant,
    )
    return {
        "height_delta_m": benchmark.height_delta_m,
        "horizontal_range_m": benchmark.horizontal_range_m,
        "range_3d_m": benchmark.range_3d_m,
        "pn3d_los_rate_norm_radps": benchmark.los_rate_norm_radps,
        "pn3d_commanded_accel_norm_mps2": benchmark.commanded_accel_norm_mps2,
        "pn3d_benchmark_only": benchmark.benchmark_only,
        "pn3d_default_api_replaced": benchmark.default_pn_png_api_replaced,
    }


_OBSERVATION_METADATA_FIELD_NAMES = (
    "detect_registration_outcome",
    "detect_registration_reject_reasons",
    "measurement_age_s",
    "latency_s",
    "projection_valid",
    "projection_reason",
    "projection_depth_m",
    "reprojection_error_px",
    "pixel_error_px",
    "reprojection_error",
    "mahalanobis_d2",
    "gate_pass",
    "covariance_px",
    "projection_covariance_px",
    "camera_pose_source",
    "calibration_health",
    "drift_warning",
    "tracker_backend",
    "requested_tracker_backend",
    "tracker_id_scope",
    "mot_history_length",
    "track_history_length",
    "yolo_class_id",
    "class_id",
    "yolo_class_name",
    "class_name",
    "bbox_area_px",
    "association_probability",
)


def _terminal_range_m(
    relative_position_ned: tuple[float, float, float] | None,
) -> float | None:
    if relative_position_ned is None:
        return None
    north, east, _down = relative_position_ned
    return (north * north + east * east) ** 0.5


def _relative_closing_speed_mps(
    relative_position_ned: tuple[float, float, float] | None,
    relative_velocity_ned: tuple[float, float, float] | None,
) -> float | None:
    if relative_position_ned is None or relative_velocity_ned is None:
        return None
    range_3d = sum(component * component for component in relative_position_ned) ** 0.5
    if range_3d <= 1e-12:
        return None
    dot = sum(p * v for p, v in zip(relative_position_ned, relative_velocity_ned))
    return -dot / range_3d


def _first_value(records: tuple[Any, ...], names: tuple[str, ...]) -> Any:
    for record in records:
        if record is None:
            continue
        value = _value(record, names, default=None)
        if value is not None and value != "":
            return value
    return None


def _first_string_value(records: tuple[Any, ...], names: tuple[str, ...]) -> str | None:
    value = _first_value(records, names)
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    text = str(value)
    return text if text else None


def _first_float_value(records: tuple[Any, ...], names: tuple[str, ...]) -> float | None:
    value = _first_value(records, names)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_int_value(records: tuple[Any, ...], names: tuple[str, ...]) -> int | None:
    value = _first_value(records, names)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_bool_value(records: tuple[Any, ...], names: tuple[str, ...]) -> bool | None:
    value = _first_value(records, names)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok", "allowed"}:
        return True
    if text in {"false", "f", "no", "n", "0", "fail", "failed", "reject", "rejected"}:
        return False
    return None


def _first_string_tuple_value(records: tuple[Any, ...], names: tuple[str, ...]) -> tuple[str, ...]:
    value = _first_value(records, names)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    try:
        return tuple(str(item) for item in value if str(item))
    except TypeError:
        return (str(value),)


def _matrix_trace(value: Any) -> float | None:
    if value is None:
        return None
    try:
        rows = tuple(value)
    except TypeError:
        return None
    total = 0.0
    observed = False
    for index, row in enumerate(rows):
        try:
            items = tuple(row)
        except TypeError:
            continue
        if index < len(items):
            try:
                total += float(items[index])
                observed = True
            except (TypeError, ValueError):
                continue
    return total if observed else None


def _bool_rate(values: Iterable[bool | None]) -> float:
    items = [bool(value) for value in values if value is not None]
    return sum(items) / len(items) if items else 0.0


def _numeric_summary(name: str, values: Iterable[float | None]) -> dict[str, Any]:
    items = [float(value) for value in values if value is not None]
    if not items:
        return {
            f"{name}_observed_count": 0,
            f"{name}_min": None,
            f"{name}_mean": None,
            f"{name}_max": None,
        }
    return {
        f"{name}_observed_count": len(items),
        f"{name}_min": min(items),
        f"{name}_mean": sum(items) / len(items),
        f"{name}_max": max(items),
    }


def _metadata_float(metadata: Mapping[str, Any], name: str) -> float | None:
    value = metadata.get(name)
    if value is None:
        return None
    return float(value)


def _coerce_pair_input(value: D7RuntimePairInput | Mapping[str, Any] | Any) -> D7RuntimePairInput:
    if isinstance(value, D7RuntimePairInput):
        return value
    return D7RuntimePairInput(
        binding=_value(value, ("binding", "assignment", "guidance_binding"), default=None),
        d4_permission=_value(value, ("d4_permission", "d4", "permission"), default=None),
        terminal_association=_value(value, ("terminal_association", "d5_terminal_association", "d5"), default=None),
        observation=_value(value, ("observation", "vision_observation", "bbox_observation"), default=None),
        timestamp_s=_optional_float_value(value, ("timestamp_s", "timestamp", "t")),
        resource_id=_optional_string_value(value, ("resource_id",)),
        handover_pending=bool(_value(value, ("handover_pending",), default=True)),
        terminal_locked=bool(_value(value, ("terminal_locked",), default=False)),
        current_heading_rad=_float_value(value, ("current_heading_rad",), default=0.0),
        current_speed_mps=_float_value(value, ("current_speed_mps",), default=0.0),
        intercept_speed_mps=_float_value(value, ("intercept_speed_mps",), default=0.0),
        relative_position_ned=_optional_tuple3(value, ("relative_position_ned",)),
        relative_velocity_ned=_optional_tuple3(value, ("relative_velocity_ned",)),
        command_z_ned_m=_float_value(value, ("command_z_ned_m",), default=0.0),
        requested_guidance_law=_value(
            value,
            ("requested_guidance_law", "guidance_law", "guidance_strategy"),
            default=None,
        ),
        terminal_handover_started_at_s=_optional_float_value(
            value,
            ("terminal_handover_started_at_s", "handover_started_at_s"),
        ),
        terminal_timeout_s=_optional_float_value(
            value,
            ("terminal_timeout_s", "handover_timeout_s"),
        ),
        termination_snapshot=bool(
            _value(value, ("termination_snapshot", "is_termination_snapshot"), default=False)
        ),
        termination_status=_optional_string_value(
            value,
            ("termination_status", "terminal_status"),
        ),
        termination_reason=(
            _optional_string_value(
                value,
                ("termination_reason", "abort_reason", "terminal_reason"),
            )
            or ""
        ),
        metadata=dict(_value(value, ("metadata",), default={}) or {}),
    )


def _control_context_id(binding: AssignmentGuidanceBinding) -> str:
    return f"{binding.resource_id}->{binding.assigned_global_track_id}"


def _binding_signature(
    binding: AssignmentGuidanceBinding,
) -> tuple[Any, ...]:
    return (
        binding.plan_id,
        binding.plan_version,
        binding.owner_node_id,
        binding.track_version,
        binding.assignment_id,
        binding.coalition_id,
        binding.coalition_version,
        binding.coalition_epoch,
        binding.member_role,
        binding.wave_id,
        binding.coordination_mode,
        binding.arrival_window_start_s,
        binding.arrival_window_end_s,
        binding.activation_state,
        binding.activation_plan_version,
        binding.activation_track_version,
        binding.activation_coalition_version,
        binding.terminal_authorization_scope,
        binding.arrival_coordination_required,
    )


def _binding_transition(
    previous: AssignmentGuidanceBinding | None,
    current: AssignmentGuidanceBinding,
) -> str:
    """Classify whether a rolling binding may retain visual-filter history.

    This classification never authorizes visual PNG. The latest binding still
    passes the complete D3/D4/D5 contract on every sample.
    """

    if previous is None:
        return "initial"
    if _binding_signature(previous) == _binding_signature(current):
        return "unchanged"
    if current.plan_version < previous.plan_version:
        return "plan_version_regression"
    if current.track_version < previous.track_version:
        return "track_version_regression"
    immutable_identity = (
        previous.resource_id == current.resource_id
        and previous.assigned_global_track_id == current.assigned_global_track_id
        and previous.owner_node_id is not None
        and previous.owner_node_id == current.owner_node_id
        and previous.member_role == current.member_role
        and previous.wave_id == current.wave_id
        and previous.coordination_mode == current.coordination_mode
        and previous.activation_state == current.activation_state
        and previous.coalition_id == current.coalition_id
        and previous.terminal_authorization_scope == current.terminal_authorization_scope
        and previous.arrival_coordination_required == current.arrival_coordination_required
    )
    coalition_version_monotonic = (
        previous.coalition_version == current.coalition_version
        or (
            previous.coalition_version is not None
            and current.coalition_version is not None
            and current.coalition_version > previous.coalition_version
        )
    )
    version_advanced = bool(
        current.plan_version > previous.plan_version
        or current.track_version > previous.track_version
        or (
            previous.coalition_version is not None
            and current.coalition_version is not None
            and current.coalition_version > previous.coalition_version
        )
    )
    plan_identity_monotonic = bool(
        current.plan_id == previous.plan_id
        or current.plan_version > previous.plan_version
    )
    if (
        immutable_identity
        and coalition_version_monotonic
        and version_advanced
        and plan_identity_monotonic
        and current.is_authorized
        and current.is_current
        and current.plan_version >= previous.plan_version
        and current.track_version >= previous.track_version
    ):
        return "monotonic_current_update"
    return "control_identity_changed"


def _resolve_timestamp_s(
    pair_input: D7RuntimePairInput,
    observation: VisionGuidanceObservation | None,
    binding: AssignmentGuidanceBinding,
) -> float:
    if pair_input.timestamp_s is not None:
        return float(pair_input.timestamp_s)
    if observation is not None:
        return float(observation.timestamp_s)
    return float(binding.created_at_s)


def _bbox_xyxy(value: Any) -> tuple[float, float, float, float]:
    bbox = _value(value, ("bbox_xyxy", "xyxy", "bbox"), default=None)
    if bbox is not None:
        return _tuple4(bbox, "bbox_xyxy")
    xywh = _value(value, ("bbox_xywh", "xywh"), default=None)
    if xywh is None:
        raise ValueError("observation requires bbox_xyxy/xyxy/bbox or bbox_xywh/xywh")
    x, y, width, height = _tuple4(xywh, "bbox_xywh")
    return (x, y, x + width, y + height)


def _tuple4(value: Any, name: str) -> tuple[float, float, float, float]:
    try:
        items = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence") from exc
    if len(items) != 4:
        raise ValueError(f"{name} must contain exactly four values")
    return (float(items[0]), float(items[1]), float(items[2]), float(items[3]))


def _optional_tuple3(value: Any, names: tuple[str, ...]) -> tuple[float, float, float] | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    try:
        items = tuple(raw)
    except TypeError as exc:
        raise ValueError(f"{names[0]} must be a sequence") from exc
    if len(items) != 3:
        raise ValueError(f"{names[0]} must contain exactly three values")
    return (float(items[0]), float(items[1]), float(items[2]))


def _required_float(value: Any, names: tuple[str, ...]) -> float:
    raw = _value(value, names, default=None)
    if raw is None:
        raise ValueError(f"{names[0]} is required")
    return float(raw)


def _float_value(value: Any, names: tuple[str, ...], *, default: float) -> float:
    return float(_value(value, names, default=default))


def _optional_float_value(value: Any, names: tuple[str, ...]) -> float | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    return float(raw)


def _optional_string_value(value: Any, names: tuple[str, ...]) -> str | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    if hasattr(raw, "value"):
        raw = raw.value
    text = str(raw)
    return text if text else None


def _value(record: Any, names: tuple[str, ...], *, default: Any) -> Any:
    if record is None:
        return default
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if not isinstance(record, Mapping) and hasattr(record, name):
            return getattr(record, name)
    return default
