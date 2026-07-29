"""Main-owned composition of the scalable D1-D7 online module path.

The stack is intentionally glue code.  Sensor, association, assignment,
failover, terminal-association, and guidance algorithms remain owned by their
respective D modules.  This module schedules those implementations on the
shared episode clock and translates only versioned, truth-free DTOs.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, replace
from enum import Enum
import hashlib
import json
import math
from numbers import Integral, Real
from time import perf_counter
from typing import Any, Iterable, Mapping

import numpy as np

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
    ASSOCIATION_SPARSE_PREFILTER_DEFAULT_SELECTOR,
    ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
    CV_MOTION_MODEL_CACHE_DIAGNOSTICS_SCHEMA_VERSION,
    CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION_ID,
    CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION_ID,
    DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
    DEFAULT_CV_MOTION_MODEL_CACHE_CAPACITY,
    ExperimentalCentroidEvidenceDisposition,
    ExperimentalCentroidPublicationState,
    MAX_CV_MOTION_MODEL_CACHE_CAPACITY,
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
    OnlineBatchFrameBuilder,
    REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
    REPLAY_PREFIX_SUMMARY_DEFAULT_SELECTOR,
    REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
    SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    SCAN_INPUT_REFERENCE_IMPLEMENTATION,
    ScanInputConfig,
    ScanInputOrganizer,
    Scalable3DFusionAdapter,
    run_experimental_centroid_publication_overlay_atomically,
)
from research_modules.d1_sensor_fusion.src.d1_sensor_fusion.fusion import (
    DEFAULT_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY,
    MAX_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY,
    OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION,
    OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION_ID,
    OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION_ID,
    STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION_ID,
    STRUCTURED_NUMERICAL_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION,
    STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION_ID,
)
from research_modules.d2_data_association.d2_data_association import (
    AmbiguityComponent3D,
    AmbiguityHoldLeaseConfig,
    D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION,
    D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION,
    IdentityCommitmentRecoveryConfig,
    IdentityCommitmentState,
    IdentityEvidenceCommitment,
    ObservationClaimLedgerConfig,
    ReplayCoastConfig,
    Scalable3DTracker,
    detections3d_from_d1_global_tracks_with_audit,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
    RegionalAuthorityGrant,
    RegionalAuthorityInput,
    RegionalCoalitionCommitEvidence,
    RegionalPlanAuthorityError,
    ResourceState,
    TargetDemand,
    TargetTrack,
    continue_active_secondary_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    AdvisorMode,
    C2Health,
    CausalCommunicationEvidenceGate,
    CausalMessageKind,
    CoalitionCommitState,
    CoalitionMemberAck,
    CommunicationDeliveryReceipt,
    CommunicationEvidenceExpectation,
    D5Consistency,
    MobileReconSecondary,
    REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA,
    REGION_RESOURCE_COALITION_ACK_TOPIC,
    REGION_RESOURCE_OWNER_ACK_TOPIC,
    RegionDefinition,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverCoordinator,
    RegionalFailoverSnapshot,
    RegionalFallbackMember,
    RegionResourceEdge,
    RegionResourceAdvisoryGate,
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
    RegionResourceCoalitionAckDelivery,
    RegionResourceCoalitionCommitEvidence,
    RegionResourceCoalitionRequirement,
    RegionResourceD3PlanReference,
    RegionResourceOwnerAckDelivery,
    RegionResourcePhysicalWindowEvidence,
    RegionResourceProjectionConfig,
    RegionResourceRuntimeAckParser,
    RegionResourceSafeAdoptionAssembler,
    RegionResourceSafeAdoptionContext,
    RegionResourceSnapshot,
    RegionalScenarioMetadata,
    RegionalTaskEvidence,
    SecondaryReadinessEvidence,
    build_region_resource_owner_plan_ack,
    canonical_payload_digest,
    canonical_runtime_payload_sha256,
    validate_region_resource_coalition_ack_delivery,
    validate_region_resource_owner_ack_delivery,
)
from research_modules.d5_terminal_association.src.d5_terminal_association import (
    RUNTIME_OBSERVED_EVIDENCE_KIND,
    ActiveVisionA3AdoptionTrace,
    ActiveVisionA3AnonymousObservationFrame,
    ActiveVisionA3BenefitAuditInput,
    ActiveVisionA3CandidatePhysicalWindowStatus,
    ActiveVisionA3CandidateStageEvidence,
    ActiveVisionA3PhysicalObservationWindow,
    ActiveVisionA3RuleArmTrace,
    ActiveVisionA3WindowArm,
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCameraFeedbackV1,
    ActiveVisionCommunicationState,
    ActiveVisionControllerV1,
    ActiveVisionFovMode,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    active_vision_a3_observation_frame,
    active_vision_a3_zero_detection_frame,
    assemble_active_vision_a3_adoption_trace,
    assemble_active_vision_a3_evidence,
    assemble_active_vision_a3_physical_observation_window,
    assemble_active_vision_a3_rule_arm_physical_observation_window,
    assemble_active_vision_a3_rule_arm_trace,
    camera_observation_command_payload,
    Scalable3DTerminalAdapter,
)
from research_modules.d7_proportional_guidance.d7_proportional_guidance import (
    AssignmentPairGuidanceInput3D,
    D4GuidancePermission,
    ScalableGuidanceConfig3D,
    ScalableGuidanceController3D,
    TerminalVisualObservation3D,
)

from .models import CameraFrameEvent, OnlineSensorBatch, ScenarioConfig
from .runtime_ports import (
    CameraObservationCommand,
    CameraRuntimeState,
    PlatformNavigationBatch,
    RuntimeCommunicationIntent,
    RuntimePublication,
    RuntimeStepInput,
    RuntimeStepOutput,
)


INTEGRATED_STACK_SCHEMA_VERSION = "scalable3d-module-stack-v1"
D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION = "per_track_copy_v1"
D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION = "immutable_shared_v2"
D1_CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION = "per_prediction_build_v1"
D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION = "bounded_exact_lru_v1"
D1_OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION = (
    "per_publication_build_v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION = (
    "bounded_generation_lru_v1"
)
D1_STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION = (
    "dense_output_probe_v1"
)
D1_STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION = (
    "known_dimension_structural_columns_v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION = (
    "full_consistency_snapshot_v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION = (
    "required_observation_subset_v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_DEFAULT_IMPLEMENTATION = (
    D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION_ID = (
    "main.d1_publication_evidence.full_consistency_snapshot.v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION_ID = (
    "main.d1_publication_evidence.required_observation_subset.v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION = (
    "scalable3d-d1-publication-evidence-snapshot-execution-config-v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION = (
    "scalable3d-d1-publication-evidence-snapshot-diagnostics-v1"
)
_EPS = 1.0e-9
_D4_GATE_NODE_ID = "D4-AUTHORITY-GATE"
_D4_READINESS_TOPIC = "d4.secondary_readiness.v1"
_D4_PLAN_TOPIC = "d4.regional_plan_broadcast.v1"
_D4_ACK_TOPIC = REGION_RESOURCE_COALITION_ACK_TOPIC
_D4_OWNER_ACK_TOPIC = REGION_RESOURCE_OWNER_ACK_TOPIC
_D4_CONTROL_SCHEMA = "scalable3d-d4-causal-message-v1"
_D4_STRICT_EVIDENCE_RANDOM_STREAM = "d4_strict_evidence_v1"


@dataclass
class _D4ReadinessReception:
    payload: dict[str, Any]
    receipt: CommunicationDeliveryReceipt
    first_arrival_s: float
    last_arrival_s: float
    observation_count: int


@dataclass(frozen=True)
class _D4AcceptedDelivery:
    payload: dict[str, Any]
    receipt: CommunicationDeliveryReceipt


@dataclass(frozen=True)
class _D4RegionAdvisorySource:
    snapshot: Any
    recommendation: Any
    formal_snapshot: RegionalFailoverSnapshot
    formal_decision: Any


@dataclass
class _D4A2PendingAdoption:
    context: RegionResourceSafeAdoptionContext
    preparation: Any
    plan_reference: RegionResourceD3PlanReference
    runtime_ack: Any
    expected_owner_ack: Any
    source_state_payload_sha256: str
    non_hold_control_applied_count: int
    owner_ack_delivery: RegionResourceOwnerAckDelivery | None = None
    coalition_ack_deliveries: dict[
        tuple[str, str, int], dict[str, RegionResourceCoalitionAckDelivery]
    ] | None = None
    coalition_commits: tuple[RegionResourceCoalitionCommitEvidence, ...] = ()
    physical_window_start_s: float | None = None
    physical_window_source_payload_sha256: str | None = None
    final_evidence: Any | None = None

    def __post_init__(self) -> None:
        if self.coalition_ack_deliveries is None:
            self.coalition_ack_deliveries = {}


@dataclass(frozen=True)
class _D5A3CommandContext:
    window_index: int
    timestamp_s: float
    snapshot: ActiveVisionSnapshotV1
    decision: Any
    command: CameraObservationCommand


@dataclass
class _D5A3PendingObservationWindow:
    trace: ActiveVisionA3AdoptionTrace | ActiveVisionA3RuleArmTrace
    observation_frames: list[ActiveVisionA3AnonymousObservationFrame]


@dataclass(frozen=True)
class IntegratedStackConfig:
    """Main-level scheduling and deterministic adapter settings."""

    assignment_lease_multiplier: float = 3.0
    d3_candidate_edges_per_target: int = 32
    d3_unassigned_base_cost: float = 50.0
    d3_human_authorization_state: str = "approved"
    d4_advisory_ttl_multiplier: float = 1.5
    d4_readiness_period_s: float = 0.10
    d4_plan_broadcast_period_s: float = 0.10
    d4_communication_stale_after_s: float = 1.10
    terminal_switch_range_m: float = 120.0
    secondary_coverage_ratio: float = 0.90
    secondary_network_full_view_rate: float = 0.90
    capture_learning_artifacts: bool = False
    d5_active_vision_enabled: bool = True
    d5_active_vision_mode: str = "disabled"
    d5_active_vision_zoom_fov_deg: float = 30.0
    d5_active_vision_observation_triggered: bool = True
    d5_active_vision_evidence_tail_s: float = 0.25
    d5_recon_track_cues_enabled: bool = False
    d1_scan_max_lateness_s: float = 0.5
    d1_scan_max_buffer_residence_s: float = 5.0
    d1_scan_input_implementation: str = SCAN_INPUT_CANDIDATE_IMPLEMENTATION
    d1_online_batch_frame_implementation: str = (
        ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
    )
    d1_publication_metadata_implementation: str = (
        D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION
    )
    d1_cv_motion_model_implementation: str = (
        D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION
    )
    d1_cv_motion_model_cache_capacity: int = (
        DEFAULT_CV_MOTION_MODEL_CACHE_CAPACITY
    )
    d1_opaque_source_identity_implementation: str = (
        D1_OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION
    )
    d1_opaque_source_identity_cache_capacity: int = (
        DEFAULT_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY
    )
    d1_structured_numerical_jacobian_implementation: str = (
        D1_STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION
    )
    d1_association_sparse_prefilter_implementation: str = (
        ASSOCIATION_SPARSE_PREFILTER_DEFAULT_SELECTOR
    )
    d1_replay_prefix_summary_implementation: str = (
        REPLAY_PREFIX_SUMMARY_DEFAULT_SELECTOR
    )
    d1_publication_evidence_snapshot_implementation: str = (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_DEFAULT_IMPLEMENTATION
    )
    d2_claim_retention_s: float = 30.0
    d2_claim_max_lateness_s: float = 5.0
    d2_claim_capacity_safety_factor: float = 2.0
    d2_replay_coast_grace_s: float = 0.5
    d1_scan_event_log_limit: int = 4_096
    d1_coalesce_same_fusion_time: bool = True
    d1_radar_assignment_ambiguity_governance_v2: bool = False
    d1_d2_structural_ambiguity_hold_enabled: bool = False
    d1_publish_opaque_source_key: bool = False
    d1_identity_neutral_centroid_correction_enabled: bool = False
    d1_centroid_publication_overlay_shadow_enabled: bool = False
    d2_ambiguity_hold_gap_scan_periods: int = 2
    d2_ambiguity_hold_hard_scan_periods: int = 5
    d1_ambiguity_pending_evidence_limit: int = 4_096

    def __post_init__(self) -> None:
        if self.assignment_lease_multiplier <= 1.0:
            raise ValueError("assignment_lease_multiplier must exceed one")
        if self.d3_candidate_edges_per_target <= 0:
            raise ValueError("d3_candidate_edges_per_target must be positive")
        if self.d3_unassigned_base_cost <= 0.0:
            raise ValueError("d3_unassigned_base_cost must be positive")
        if self.d4_advisory_ttl_multiplier <= 1.0:
            raise ValueError("d4_advisory_ttl_multiplier must exceed one")
        for name in (
            "d4_readiness_period_s",
            "d4_plan_broadcast_period_s",
            "d4_communication_stale_after_s",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if (
            self.d4_communication_stale_after_s
            <= self.d4_plan_broadcast_period_s
        ):
            raise ValueError(
                "d4_communication_stale_after_s must exceed the plan broadcast period"
            )
        if self.terminal_switch_range_m <= 0.0:
            raise ValueError("terminal_switch_range_m must be positive")
        active_mode = str(self.d5_active_vision_mode).strip().lower()
        if active_mode not in {"disabled", "shadow", "assist"}:
            raise ValueError(
                "d5_active_vision_mode must be disabled, shadow, or assist"
            )
        object.__setattr__(self, "d5_active_vision_mode", active_mode)
        if not 1.0 < float(self.d5_active_vision_zoom_fov_deg) < 179.0:
            raise ValueError("d5_active_vision_zoom_fov_deg must be in (1, 179)")
        evidence_tail = float(self.d5_active_vision_evidence_tail_s)
        if not np.isfinite(evidence_tail) or evidence_tail < 0.0:
            raise ValueError(
                "d5_active_vision_evidence_tail_s must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "d5_active_vision_evidence_tail_s",
            evidence_tail,
        )
        for name in (
            "d1_scan_max_lateness_s",
            "d1_scan_max_buffer_residence_s",
            "d2_claim_retention_s",
            "d2_claim_max_lateness_s",
            "d2_replay_coast_grace_s",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.d1_scan_max_buffer_residence_s < self.d1_scan_max_lateness_s:
            raise ValueError(
                "d1_scan_max_buffer_residence_s must cover d1_scan_max_lateness_s"
            )
        scan_input_implementation = str(
            self.d1_scan_input_implementation
        ).strip()
        if scan_input_implementation not in {
            SCAN_INPUT_REFERENCE_IMPLEMENTATION,
            SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_scan_input_implementation must be reference_v1 or candidate_v2"
            )
        object.__setattr__(
            self,
            "d1_scan_input_implementation",
            scan_input_implementation,
        )
        online_batch_frame_implementation = str(
            self.d1_online_batch_frame_implementation
        ).strip()
        if online_batch_frame_implementation not in {
            ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
            ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_online_batch_frame_implementation must be "
                "convert_then_frame_v1 or closed_immutable_batch_to_frame_v1"
            )
        object.__setattr__(
            self,
            "d1_online_batch_frame_implementation",
            online_batch_frame_implementation,
        )
        publication_metadata_implementation = str(
            self.d1_publication_metadata_implementation
        ).strip()
        if publication_metadata_implementation not in {
            D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION,
            D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_publication_metadata_implementation must be "
                "per_track_copy_v1 or immutable_shared_v2"
            )
        object.__setattr__(
            self,
            "d1_publication_metadata_implementation",
            publication_metadata_implementation,
        )
        cv_motion_model_implementation = str(
            self.d1_cv_motion_model_implementation
        ).strip()
        if cv_motion_model_implementation not in {
            D1_CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION,
            D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_cv_motion_model_implementation must be "
                "per_prediction_build_v1 or bounded_exact_lru_v1"
            )
        object.__setattr__(
            self,
            "d1_cv_motion_model_implementation",
            cv_motion_model_implementation,
        )
        if (
            isinstance(self.d1_cv_motion_model_cache_capacity, bool)
            or not isinstance(
                self.d1_cv_motion_model_cache_capacity,
                Integral,
            )
        ):
            raise TypeError(
                "d1_cv_motion_model_cache_capacity must be an integer"
            )
        cv_motion_model_cache_capacity = int(
            self.d1_cv_motion_model_cache_capacity
        )
        if not (
            1
            <= cv_motion_model_cache_capacity
            <= MAX_CV_MOTION_MODEL_CACHE_CAPACITY
        ):
            raise ValueError(
                "d1_cv_motion_model_cache_capacity must be between 1 and "
                f"{MAX_CV_MOTION_MODEL_CACHE_CAPACITY}"
            )
        object.__setattr__(
            self,
            "d1_cv_motion_model_cache_capacity",
            cv_motion_model_cache_capacity,
        )
        opaque_source_identity_implementation = str(
            self.d1_opaque_source_identity_implementation
        ).strip()
        if opaque_source_identity_implementation not in {
            D1_OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION,
            D1_OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_opaque_source_identity_implementation must be "
                "per_publication_build_v1 or bounded_generation_lru_v1"
            )
        object.__setattr__(
            self,
            "d1_opaque_source_identity_implementation",
            opaque_source_identity_implementation,
        )
        if (
            isinstance(self.d1_opaque_source_identity_cache_capacity, bool)
            or not isinstance(
                self.d1_opaque_source_identity_cache_capacity,
                Integral,
            )
        ):
            raise TypeError(
                "d1_opaque_source_identity_cache_capacity must be an integer"
            )
        opaque_source_identity_cache_capacity = int(
            self.d1_opaque_source_identity_cache_capacity
        )
        if not (
            1
            <= opaque_source_identity_cache_capacity
            <= MAX_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY
        ):
            raise ValueError(
                "d1_opaque_source_identity_cache_capacity must be between 1 "
                f"and {MAX_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY}"
            )
        object.__setattr__(
            self,
            "d1_opaque_source_identity_cache_capacity",
            opaque_source_identity_cache_capacity,
        )
        structured_jacobian_implementation = str(
            self.d1_structured_numerical_jacobian_implementation
        ).strip()
        if structured_jacobian_implementation not in {
            D1_STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION,
            D1_STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_structured_numerical_jacobian_implementation must be "
                "dense_output_probe_v1 or "
                "known_dimension_structural_columns_v1"
            )
        object.__setattr__(
            self,
            "d1_structured_numerical_jacobian_implementation",
            structured_jacobian_implementation,
        )
        association_sparse_prefilter_implementation = str(
            self.d1_association_sparse_prefilter_implementation
        ).strip()
        if association_sparse_prefilter_implementation not in {
            ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
            ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
        }:
            raise ValueError(
                "d1_association_sparse_prefilter_implementation must be "
                "disabled_v1 or modality_conservative_quadratic_bound_v1"
            )
        object.__setattr__(
            self,
            "d1_association_sparse_prefilter_implementation",
            association_sparse_prefilter_implementation,
        )
        replay_prefix_summary_implementation = str(
            self.d1_replay_prefix_summary_implementation
        ).strip()
        if replay_prefix_summary_implementation not in {
            REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
            REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
        }:
            raise ValueError(
                "d1_replay_prefix_summary_implementation must be "
                "per_checkpoint_prefix_rebuild_v1 or "
                "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
            )
        object.__setattr__(
            self,
            "d1_replay_prefix_summary_implementation",
            replay_prefix_summary_implementation,
        )
        publication_evidence_snapshot_implementation = str(
            self.d1_publication_evidence_snapshot_implementation
        ).strip()
        if publication_evidence_snapshot_implementation not in {
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION,
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION,
        }:
            raise ValueError(
                "d1_publication_evidence_snapshot_implementation must be "
                "full_consistency_snapshot_v1 or "
                "required_observation_subset_v1"
            )
        object.__setattr__(
            self,
            "d1_publication_evidence_snapshot_implementation",
            publication_evidence_snapshot_implementation,
        )
        if (
            not np.isfinite(self.d2_claim_capacity_safety_factor)
            or self.d2_claim_capacity_safety_factor < 1.0
        ):
            raise ValueError(
                "d2_claim_capacity_safety_factor must be finite and at least one"
            )
        if int(self.d1_scan_event_log_limit) <= 0:
            raise ValueError("d1_scan_event_log_limit must be positive")
        if not isinstance(self.d1_coalesce_same_fusion_time, bool):
            raise TypeError("d1_coalesce_same_fusion_time must be a bool")
        if not isinstance(
            self.d1_radar_assignment_ambiguity_governance_v2,
            bool,
        ):
            raise TypeError(
                "d1_radar_assignment_ambiguity_governance_v2 must be a bool"
            )
        if not isinstance(
            self.d1_d2_structural_ambiguity_hold_enabled,
            bool,
        ):
            raise TypeError(
                "d1_d2_structural_ambiguity_hold_enabled must be a bool"
            )
        if not isinstance(self.d1_publish_opaque_source_key, bool):
            raise TypeError("d1_publish_opaque_source_key must be a bool")
        if not isinstance(
            self.d1_identity_neutral_centroid_correction_enabled,
            bool,
        ):
            raise TypeError(
                "d1_identity_neutral_centroid_correction_enabled must be a bool"
            )
        if not isinstance(
            self.d1_centroid_publication_overlay_shadow_enabled,
            bool,
        ):
            raise TypeError(
                "d1_centroid_publication_overlay_shadow_enabled must be a bool"
            )
        if (
            self.d1_identity_neutral_centroid_correction_enabled
            and not self.d1_d2_structural_ambiguity_hold_enabled
        ):
            raise ValueError(
                "D1 identity-neutral centroid correction requires "
                "D1-D2 structural ambiguity hold"
            )
        if (
            self.d1_centroid_publication_overlay_shadow_enabled
            and not self.d1_d2_structural_ambiguity_hold_enabled
        ):
            raise ValueError(
                "D1 centroid publication overlay shadow requires "
                "D1-D2 structural ambiguity hold"
            )
        if (
            self.d1_centroid_publication_overlay_shadow_enabled
            and self.d1_identity_neutral_centroid_correction_enabled
        ):
            raise ValueError(
                "D1 centroid publication overlay shadow cannot be combined "
                "with the rejected in-filter centroid correction"
            )
        if (
            self.d1_radar_assignment_ambiguity_governance_v2
            and self.d1_d2_structural_ambiguity_hold_enabled
        ):
            raise ValueError(
                "rejected D1 ambiguity v2 and D1-D2 ambiguity hold "
                "cannot both be enabled"
            )
        for name in (
            "d2_ambiguity_hold_gap_scan_periods",
            "d2_ambiguity_hold_hard_scan_periods",
            "d1_ambiguity_pending_evidence_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or int(value) != value or int(value) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            self.d2_ambiguity_hold_hard_scan_periods
            < self.d2_ambiguity_hold_gap_scan_periods
        ):
            raise ValueError(
                "d2 ambiguity hard hold cannot be shorter than the gap hold"
            )
        for name in ("secondary_coverage_ratio", "secondary_network_full_view_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


def _initial_cv_motion_model_cache_diagnostics(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    candidate_enabled = (
        config.d1_cv_motion_model_implementation
        == D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION
    )
    return {
        "schema_version": CV_MOTION_MODEL_CACHE_DIAGNOSTICS_SCHEMA_VERSION,
        "implementation_id": (
            CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION_ID
            if candidate_enabled
            else CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION_ID
        ),
        "candidate_enabled": candidate_enabled,
        "cache_capacity": int(config.d1_cv_motion_model_cache_capacity),
        "cache_entry_count": 0,
        "operation_counts": {},
    }


def _initial_opaque_source_identity_cache_diagnostics(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    candidate_enabled = (
        config.d1_opaque_source_identity_implementation
        == D1_OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION
    )
    return {
        "schema_version": (
            OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "implementation_id": (
            OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION_ID
            if candidate_enabled
            else OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION_ID
        ),
        "candidate_enabled": candidate_enabled,
        "cache_capacity": int(
            config.d1_opaque_source_identity_cache_capacity
        ),
        "cache_entry_count": 0,
        "cache_generation": None,
        "operation_counts": {},
        "conservation": {
            "request_equals_hit_plus_miss_plus_bypass": True,
            "build_equals_miss_plus_bypass": True,
            "eviction_not_above_miss": True,
            "entry_count_within_capacity": True,
            "peak_entry_count_within_capacity": True,
        },
    }


def _initial_structured_numerical_jacobian_diagnostics(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    candidate_enabled = (
        config.d1_structured_numerical_jacobian_implementation
        == D1_STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION
    )
    return {
        "schema_version": (
            STRUCTURED_NUMERICAL_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "implementation_id": (
            STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION_ID
            if candidate_enabled
            else STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION_ID
        ),
        "candidate_enabled": candidate_enabled,
        "operation_counts": {},
        "conservation": {
            "attempt_equals_success_plus_failure": True,
            "attempt_equals_reference_plus_candidate": True,
        },
    }


def _initial_association_sparse_prefilter_diagnostics(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    return Scalable3DFusionAdapter(
        association_sparse_prefilter=(
            config.d1_association_sparse_prefilter_implementation
        )
    ).association_sparse_prefilter_diagnostics()


def _initial_replay_prefix_summary_diagnostics(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    return Scalable3DFusionAdapter(
        replay_prefix_summary=(
            config.d1_replay_prefix_summary_implementation
        )
    ).replay_prefix_summary_diagnostics()


def _d1_publication_evidence_snapshot_execution_config(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    selector = config.d1_publication_evidence_snapshot_implementation
    candidate_enabled = (
        selector
        == D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION
    )
    return {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "selector": selector,
        "implementation_id": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION_ID
            if candidate_enabled
            else D1_PUBLICATION_EVIDENCE_SNAPSHOT_REFERENCE_IMPLEMENTATION_ID
        ),
        "candidate_enabled": candidate_enabled,
        "required_id_sources": (
            "source_observations",
            "materialized_track_latest_observation",
        ),
        "required_id_order": "deduplicated_lexicographic",
        "invalid_or_unknown_id_policy": "fallback_to_full_snapshot",
        "episode_final_export_scope": "full_exact_materialized_records",
        "truth_dependent_inputs_allowed": False,
    }


def _initial_d1_publication_evidence_snapshot_diagnostics(
    config: IntegratedStackConfig,
) -> dict[str, Any]:
    return {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "execution_config": (
            _d1_publication_evidence_snapshot_execution_config(config)
        ),
        "operation_counts": {},
        "fallback_reason_counts": {},
        "conservation": {
            "selection_partition": True,
            "candidate_selection_partition": True,
            "adapter_call_partition": True,
            "reference_deduplication_partition": True,
            "fallback_not_above_candidate_selection": True,
            "all_required_records_available": True,
        },
    }


@dataclass(frozen=True)
class D4RegionLearningFrame:
    """One truth-free regional snapshot and its formal D4 source evidence."""

    frame_index: int
    timestamp_s: float
    snapshot: Any
    recommendation: Any | None
    formal_snapshot: Any
    formal_decision: Any


@dataclass(frozen=True)
class D5GraphLearningFrame:
    """One anonymous cross-camera graph with measurement-to-tracklet links."""

    frame_index: int
    timestamp_s: float
    graph: Any
    source_observation_links: tuple[Any, ...]


@dataclass(frozen=True)
class D5ActiveVisionLearningFrame:
    """One truth-free active-vision decision frame and camera feedback."""

    frame_index: int
    timestamp_s: float
    snapshot: ActiveVisionSnapshotV1
    decisions: tuple[Any, ...]
    camera_feedback: tuple[ActiveVisionCameraFeedbackV1, ...]


@dataclass(frozen=True)
class IntegratedLearningArtifacts:
    """Detached, truth-free episode artifacts for offline dataset construction."""

    d3_planning_frames: tuple[Any, ...]
    d4_region_frames: tuple[D4RegionLearningFrame, ...]
    d5_graph_frames: tuple[D5GraphLearningFrame, ...]
    d5_active_vision_frames: tuple[D5ActiveVisionLearningFrame, ...] = ()


class IntegratedScalableModuleStack:
    """Truth-free D1-D7 rule baseline for one scalable point-mass episode.

    The first integrated profile deliberately keeps learning models optional.
    D3 uses its deterministic sparse cost/Hungarian path and D5 uses its
    geometry rule when no edge model is supplied.  D7 always remains the
    deterministic three-dimensional PN/visual-PNG controller.
    """

    def __init__(
        self,
        config: IntegratedStackConfig | None = None,
        *,
        d3_learning_assistant: Any | None = None,
        d4_region_advisor: Any | None = None,
        d4_unseen_seed_count: int = 0,
        d5_edge_model: Any | None = None,
        d5_shadow_edge_model: Any | None = None,
        d5_active_vision_policy: Any | None = None,
        learning_runtime_diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.stack_config = config or IntegratedStackConfig()
        if int(d4_unseen_seed_count) < 0:
            raise ValueError("d4_unseen_seed_count must be non-negative")
        self.d3_learning_assistant = d3_learning_assistant
        self._configured_d4_region_advisor = d4_region_advisor
        self.d4_region_advisor = d4_region_advisor
        self.d4_unseen_seed_count = int(d4_unseen_seed_count)
        if d5_edge_model is not None and d5_shadow_edge_model is not None:
            raise ValueError(
                "D5 applied and shadow edge models are mutually exclusive"
            )
        self.d5_edge_model = d5_edge_model
        self.d5_shadow_edge_model = d5_shadow_edge_model
        self.d5_active_vision_policy = d5_active_vision_policy
        self.learning_runtime_diagnostics = dict(
            learning_runtime_diagnostics or {}
        )
        self.config: ScenarioConfig | None = None
        self.d1: Scalable3DFusionAdapter | None = None
        self.d1_scan_input: ScanInputOrganizer | None = None
        self.d2: Scalable3DTracker | None = None
        self.d3: AssignmentPlanner | None = None
        self.d4: RegionalFailoverCoordinator | None = None
        self.d5: Scalable3DTerminalAdapter | None = None
        self.d7: ScalableGuidanceController3D | None = None
        self.d5_active_vision: ActiveVisionControllerV1 | None = None
        self.latest_d1_tracks: tuple[Any, ...] = ()
        self.latest_d2_tracks: tuple[Any, ...] = ()
        self.latest_d2_result: Any | None = None
        self.latest_plan: Any | None = None
        self.latest_bindings: tuple[Any, ...] = ()
        self.latest_d4_decision: Any | None = None
        self.latest_d4_region_snapshot: Any | None = None
        self.latest_d4_region_advice: Any | None = None
        self.latest_d4_region_consumption: Any | None = None
        self.latest_d5_result: Any | None = None
        self.latest_d5_shadow_scoring: dict[str, Any] | None = None
        self.latest_guidance_batch: Any | None = None
        self.latest_active_vision_snapshot: ActiveVisionSnapshotV1 | None = None
        self.latest_active_vision_decisions: tuple[Any, ...] = ()
        self.latest_active_vision_recon_cue_count = 0
        self._latest_terminal_by_pair: dict[tuple[str, str], tuple[dict[str, Any], Any]] = {}
        self._track_region_by_id: dict[str, str] = {}
        self._resource_index_by_id: dict[str, int] = {}
        self._next_association_s = 0.0
        self._next_assignment_s = 0.0
        self._next_active_vision_s = 0.0
        self._active_vision_communication_version = 0
        self._last_center_health = C2Health.NORMAL
        self._last_secondary_failed = False
        self._fault_generation_changed = False
        self._regional_plan_rejection_reason: str | None = None
        self._d4_region_hint_bridge_rejection_reason: str | None = None
        self._d4_region_advisory_gate: RegionResourceAdvisoryGate | None = None
        self._next_d4_region_hint_version = 1
        self._d4_causal_gate = CausalCommunicationEvidenceGate()
        self._next_d4_readiness_s = 0.0
        self._next_d4_plan_broadcast_s = 0.0
        self._d4_message_sequence = 0
        self._d4_partition_generation = 0
        self._d4_last_broadcast_plan_key: tuple[
            str, int, int, int, bool
        ] | None = None
        self._d4_readiness_receptions: dict[
            tuple[str, str, int, int, int], _D4ReadinessReception
        ] = {}
        self._d4_plan_deliveries: dict[
            tuple[str, int, int, int], _D4AcceptedDelivery
        ] = {}
        self._d4_ack_deliveries: dict[
            tuple[str, str, int, int, int], _D4AcceptedDelivery
        ] = {}
        self._d4_runtime_ack_parser = RegionResourceRuntimeAckParser()
        self._d4_safe_adoption_assembler = RegionResourceSafeAdoptionAssembler()
        self._d4_plan_source_envelopes: dict[tuple[str, int], Any] = {}
        self._d4_plan_transport_references: dict[
            tuple[str, int], tuple[str, int]
        ] = {}
        self._d4_advice_source_envelopes: dict[str, Any] = {}
        self._d4_advisory_sources: dict[str, _D4RegionAdvisorySource] = {}
        self._d4_a2_pending_by_plan: dict[
            tuple[str, int], _D4A2PendingAdoption
        ] = {}
        self._d4_a2_evidence_by_application: dict[str, Any] = {}
        self._d4_owner_ack_delivery_count = 0
        self._d4_coalition_ack_delivery_count = 0
        self._d4_a2_physical_window_count = 0
        self._d4_a2_bridge_blocker_counts: Counter[str] = Counter()
        self._latest_runtime_state_payload_sha256: str | None = None
        self._d4_expected_plan_authorities: dict[
            tuple[str, int, int, int, str], str
        ] = {}
        self._d4_communication_received_count = 0
        self._d4_communication_accepted_count = 0
        self._d4_communication_rejected_count = 0
        self._d4_communication_accept_counts: Counter[str] = Counter()
        self._d4_communication_rejection_counts: Counter[str] = Counter()
        self._d4_communication_intent_counts: Counter[str] = Counter()
        self._d4_communication_event_evaluation_count = 0
        self._d4_vetted_secondary_by_region: dict[str, str] = {}
        self._d3_learning_frames: list[Any] = []
        self._d4_learning_frames: list[D4RegionLearningFrame] = []
        self._d5_learning_frames: list[D5GraphLearningFrame] = []
        self._d5_shadow_scoring_frame_count = 0
        self._d5_shadow_scoring_success_count = 0
        self._d5_shadow_scoring_rejected_count = 0
        self._d5_shadow_scoring_edge_count = 0
        self._d5_shadow_scoring_rejection_reasons: Counter[str] = Counter()
        self._d5_active_vision_learning_frames: list[
            D5ActiveVisionLearningFrame
        ] = []
        self._d5_a3_command_index = 0
        self._d5_a3_command_context_by_camera: dict[
            str, _D5A3CommandContext
        ] = {}
        self._d5_a3_pending_by_camera: dict[
            str, list[_D5A3PendingObservationWindow]
        ] = {}
        self._d5_a3_evidence_by_comparison_key: dict[
            str, ActiveVisionA3BenefitAuditInput
        ] = {}
        self._d5_a3_candidate_stage_by_comparison_key: dict[
            str, ActiveVisionA3CandidateStageEvidence
        ] = {}
        self._d5_a3_r0_pending_by_camera: dict[
            str, list[_D5A3PendingObservationWindow]
        ] = {}
        self._d5_a3_r0_window_by_comparison_key: dict[
            str, ActiveVisionA3PhysicalObservationWindow
        ] = {}
        self._d5_a3_runtime_ack_count = 0
        self._d5_a3_r0_runtime_ack_count = 0
        self._d5_a3_observation_frame_count = 0
        self._d5_a3_r0_observation_frame_count = 0
        self._d5_a3_physical_window_count = 0
        self._d5_a3_r0_physical_window_count = 0
        self._d5_camera_empty_frame_received_count = 0
        self._d5_camera_empty_frame_consumed_count = 0
        self._d5_camera_empty_frame_rejected_count = 0
        self._d5_camera_empty_frame_unmatched_count = 0
        self._d5_active_vision_tail_suppressed_count = 0
        self._d5_a3_bridge_blocker_counts: Counter[str] = Counter()
        self._d2_identity_lineage_by_track: dict[str, tuple[dict[str, Any], ...]] = {}
        self._d2_observation_replay_generation: dict[str, int] = {}
        self._latest_d2_input_signature: tuple[tuple[Any, ...], ...] | None = None
        self._d2_pending_d1_update = False
        self._d1_posterior_generation = 0
        self._d2_pending_d1_posterior_generation: int | None = None
        self._d2_consumed_d1_posterior_generation = 0
        self._d2_posterior_consumption_count = 0
        self._d2_pre_tick_posterior_merge_count = 0
        self._d2_finalize_unchanged_posterior_skip_count = 0
        self._d2_finalize_coalesced_release_count = 0
        self._d2_publication_metadata_audit_batch_count = 0
        self._d2_publication_metadata_audit_totals: Counter[str] = Counter()
        self._d2_latest_publication_metadata_audit: dict[str, int] = {}
        self._identity_commitment_binding_hold_count = 0
        self._identity_commitment_binding_hold_event_count = 0
        self._identity_commitment_binding_hold_target_ids: tuple[str, ...] = ()
        self._identity_commitment_replan_required = False
        self._d1_publisher_reset_generation = 0
        self._d1_publisher_epoch = "main-stack-not-reset"
        self._pending_structural_ambiguity_evidence: dict[str, Any] = {}
        self._structural_ambiguity_evidence_received_count = 0
        self._structural_ambiguity_evidence_consumed_count = 0
        self._structural_ambiguity_d2_consumption_count = 0
        self._d1_centroid_overlay_shadow_state = (
            ExperimentalCentroidPublicationState()
        )
        self._d1_centroid_overlay_shadow_evaluation_count = 0
        self._d1_centroid_overlay_shadow_decision_count = 0
        self._d1_centroid_overlay_shadow_accepted_count = 0
        self._d1_centroid_overlay_shadow_rejected_count = 0
        self._d1_centroid_overlay_shadow_error_count = 0
        self._d1_centroid_overlay_shadow_rejection_reasons: Counter[str] = (
            Counter()
        )
        self._d1_centroid_overlay_shadow_forbidden_mutation_count = 0
        self._d1_centroid_overlay_shadow_max_watermark_count = 0
        self._d1_centroid_overlay_shadow_max_payload_bytes = 0
        self._d1_latest_lineage_by_observation: dict[str, dict[str, Any]] = {}
        self._d1_pending_lineage_by_track: dict[
            str, dict[str, dict[str, Any]]
        ] = {}
        self._d1_scan_events: deque[dict[str, Any]] = deque(
            maxlen=int(self.stack_config.d1_scan_event_log_limit)
        )
        self._d1_scan_event_total_count = 0
        self._d1_state_only_scan_count = 0
        self._d1_materialized_snapshot_count = 0
        self._d1_same_fusion_time_coalesced_scan_count = 0
        self._d1_publication_evidence_snapshot_counts: Counter[str] = Counter()
        self._d1_publication_evidence_snapshot_fallback_reasons: Counter[
            str
        ] = Counter()
        self._d1_scan_input_closed = False
        self._stage_wall_time_s: dict[str, float] = {}
        self._stage_call_count: dict[str, int] = {}
        self._stage_samples_s: dict[str, list[float]] = {}

    def runtime_manifest_profile(self) -> dict[str, Any]:
        """Return the main-owned runtime treatment profile for episode hashing."""

        sparse_prefilter_diagnostics = (
            _initial_association_sparse_prefilter_diagnostics(
                self.stack_config
            )
        )
        replay_prefix_summary_diagnostics = (
            _initial_replay_prefix_summary_diagnostics(self.stack_config)
        )
        return {
            "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
            "module_stack_schema_version": INTEGRATED_STACK_SCHEMA_VERSION,
            "configuration": asdict(self.stack_config),
            "d1_scan_input_implementation": (
                self.stack_config.d1_scan_input_implementation
            ),
            "d1_online_batch_frame_implementation": (
                self.stack_config.d1_online_batch_frame_implementation
            ),
            "d1_online_batch_frame_execution_config": (
                OnlineBatchFrameBuilder(
                    implementation=(
                        self.stack_config.d1_online_batch_frame_implementation
                    )
                ).execution_config()
            ),
            "d1_publication_metadata_implementation": (
                self.stack_config.d1_publication_metadata_implementation
            ),
            "d1_cv_motion_model_implementation": (
                self.stack_config.d1_cv_motion_model_implementation
            ),
            "d1_cv_motion_model_cache_diagnostics": (
                _initial_cv_motion_model_cache_diagnostics(
                    self.stack_config
                )
            ),
            "d1_opaque_source_identity_implementation": (
                self.stack_config.d1_opaque_source_identity_implementation
            ),
            "d1_opaque_source_identity_cache_diagnostics": (
                _initial_opaque_source_identity_cache_diagnostics(
                    self.stack_config
                )
            ),
            "d1_structured_numerical_jacobian_implementation": (
                self.stack_config
                .d1_structured_numerical_jacobian_implementation
            ),
            "d1_structured_numerical_jacobian_diagnostics": (
                _initial_structured_numerical_jacobian_diagnostics(
                    self.stack_config
                )
            ),
            "d1_association_sparse_prefilter_implementation": (
                self.stack_config
                .d1_association_sparse_prefilter_implementation
            ),
            "d1_association_sparse_prefilter_execution_config": dict(
                sparse_prefilter_diagnostics["execution_config"]
            ),
            "d1_association_sparse_prefilter_diagnostics": (
                sparse_prefilter_diagnostics
            ),
            "d1_replay_prefix_summary_implementation": (
                self.stack_config.d1_replay_prefix_summary_implementation
            ),
            "d1_replay_prefix_summary_execution_config": dict(
                replay_prefix_summary_diagnostics["execution_config"]
            ),
            "d1_replay_prefix_summary_diagnostics": (
                replay_prefix_summary_diagnostics
            ),
            "d1_publication_evidence_snapshot_implementation": (
                self.stack_config
                .d1_publication_evidence_snapshot_implementation
            ),
            "d1_publication_evidence_snapshot_execution_config": (
                _d1_publication_evidence_snapshot_execution_config(
                    self.stack_config
                )
            ),
            "d1_publication_evidence_snapshot_diagnostics": (
                _initial_d1_publication_evidence_snapshot_diagnostics(
                    self.stack_config
                )
            ),
        }

    def runtime_manifest_profile_for_scenario(
        self,
        config: ScenarioConfig,
    ) -> dict[str, Any]:
        """Resolve scenario-dependent D1 execution settings before manifest hashing."""

        profile = self.runtime_manifest_profile()
        organizer = ScanInputOrganizer(
            _scan_input_config(config, self.stack_config),
            implementation=self.stack_config.d1_scan_input_implementation,
        )
        profile["d1_scan_input_execution_config"] = organizer.execution_config()
        return profile

    def reset(self, config: ScenarioConfig) -> None:
        self.config = config
        self._d1_publisher_reset_generation += 1
        self._d1_publisher_epoch = (
            "main-stack-reset-"
            f"{self._d1_publisher_reset_generation:08d}-v1"
        )
        self.d1 = Scalable3DFusionAdapter(
            radar_assignment_ambiguity_governance_v2=(
                self.stack_config.d1_radar_assignment_ambiguity_governance_v2
            ),
            radar_assignment_ambiguity_hold_evidence=(
                self.stack_config.d1_d2_structural_ambiguity_hold_enabled
            ),
            publish_opaque_source_key=(
                self.stack_config.d1_publish_opaque_source_key
            ),
            radar_assignment_ambiguity_neutral_centroid_correction=(
                self.stack_config
                .d1_identity_neutral_centroid_correction_enabled
            ),
            publisher_node_id=(
                DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID
            ),
            publisher_epoch=self._d1_publisher_epoch,
            immutable_shared_publication_metadata=(
                self.stack_config.d1_publication_metadata_implementation
                == D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION
            ),
            cached_cv_motion_model=(
                self.stack_config.d1_cv_motion_model_implementation
                == D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION
            ),
            cv_motion_model_cache_capacity=(
                self.stack_config.d1_cv_motion_model_cache_capacity
            ),
            cached_opaque_source_identity=(
                self.stack_config.d1_opaque_source_identity_implementation
                == D1_OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION
            ),
            opaque_source_identity_cache_capacity=(
                self.stack_config
                .d1_opaque_source_identity_cache_capacity
            ),
            structured_numerical_jacobian=(
                self.stack_config
                .d1_structured_numerical_jacobian_implementation
                == D1_STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION
            ),
            association_sparse_prefilter=(
                self.stack_config
                .d1_association_sparse_prefilter_implementation
            ),
            replay_prefix_summary=(
                self.stack_config.d1_replay_prefix_summary_implementation
            ),
        )
        self.d1_scan_input = ScanInputOrganizer(
            _scan_input_config(config, self.stack_config),
            implementation=self.stack_config.d1_scan_input_implementation,
        )
        self.d1_online_batch_frame_builder = OnlineBatchFrameBuilder(
            implementation=(
                self.stack_config.d1_online_batch_frame_implementation
            ),
            radar_covariance_config=self.d1.radar_covariance_config,
            unobserved_velocity_variance_m2ps2=(
                self.d1.unobserved_velocity_variance_m2ps2
            ),
            position_only_radar_nis_gate=(
                self.d1.position_only_radar_nis_gate
            ),
        )
        self.d2 = Scalable3DTracker(
            observation_claim_config=_observation_claim_config(
                config,
                self.stack_config,
            ),
            replay_coast_config=ReplayCoastConfig(
                config_version="main-scalable3d-replay-coast-policy-v1",
                grace_seconds=self.stack_config.d2_replay_coast_grace_s,
            ),
            identity_commitment_recovery_config=(
                IdentityCommitmentRecoveryConfig(
                    config_version=(
                        "main-scalable3d-identity-recovery-publication-"
                        "freshness-v1"
                    ),
                    max_recovery_evidence_age_seconds=(
                        config.identity_lineage_freshness_budget_s
                    ),
                )
            ),
            ambiguity_hold_config=AmbiguityHoldLeaseConfig(
                enabled=(
                    self.stack_config.d1_d2_structural_ambiguity_hold_enabled
                ),
                equivalent_scan_period_seconds=config.radar_period_s,
                gap_scan_periods=(
                    self.stack_config.d2_ambiguity_hold_gap_scan_periods
                ),
                hard_scan_periods=(
                    self.stack_config.d2_ambiguity_hold_hard_scan_periods
                ),
                max_component_age_seconds=(
                    config.radar_latency_s
                    + self.stack_config.d1_scan_max_buffer_residence_s
                    + config.association_period_s
                ),
            ),
        )
        self.d3 = AssignmentPlanner(
            config=PlannerConfig.scalable_3d(
                max_candidate_edges_per_target=(
                    self.stack_config.d3_candidate_edges_per_target
                ),
                unassigned_base_cost=self.stack_config.d3_unassigned_base_cost,
                human_authorization_state=(
                    self.stack_config.d3_human_authorization_state
                ),
            ),
            learning_assistant=self.d3_learning_assistant,
        )
        self.d4 = RegionalFailoverCoordinator()
        if self._configured_d4_region_advisor is None:
            ttl_s = max(
                config.assignment_period_s * self.stack_config.d4_advisory_ttl_multiplier,
                config.assignment_period_s + config.physics_dt_s,
            )
            self.d4_region_advisor = RegionResourceAdvisor(
                config=RegionResourceAdvisorConfig(
                    mode=AdvisorMode.SHADOW,
                    projection=RegionResourceProjectionConfig(
                        advisory_ttl_s=ttl_s,
                    ),
                )
            )
        else:
            self.d4_region_advisor = self._configured_d4_region_advisor
        self._d4_region_advisory_gate = RegionResourceAdvisoryGate(
            projector=getattr(self.d4_region_advisor, "projector", None)
        )
        self.d5 = Scalable3DTerminalAdapter()
        self.d7 = ScalableGuidanceController3D(
            ScalableGuidanceConfig3D(
                terminal_switch_range_m=self.stack_config.terminal_switch_range_m,
                intercept_radius_m=config.intercept_radius_m,
            )
        )
        self.d5_active_vision = ActiveVisionControllerV1(
            learned_policy=self.d5_active_vision_policy,
            default_mode=ActiveVisionRuntimeMode(
                self.stack_config.d5_active_vision_mode
            ),
        )
        self.latest_d1_tracks = ()
        self.latest_d2_tracks = ()
        self.latest_d2_result = None
        self.latest_plan = None
        self.latest_bindings = ()
        self.latest_d4_decision = None
        self.latest_d4_region_snapshot = None
        self.latest_d4_region_advice = None
        self.latest_d4_region_consumption = None
        self.latest_d5_result = None
        self.latest_d5_shadow_scoring = None
        self.latest_guidance_batch = None
        self.latest_active_vision_snapshot = None
        self.latest_active_vision_decisions = ()
        self.latest_active_vision_recon_cue_count = 0
        self._latest_terminal_by_pair.clear()
        self._track_region_by_id.clear()
        self._resource_index_by_id.clear()
        self._next_association_s = 0.0
        self._next_assignment_s = 0.0
        self._next_active_vision_s = 0.0
        self._active_vision_communication_version = 0
        self._last_center_health = C2Health.NORMAL
        self._last_secondary_failed = False
        self._fault_generation_changed = False
        self._regional_plan_rejection_reason = None
        self._d4_region_hint_bridge_rejection_reason = None
        self._next_d4_region_hint_version = 1
        self._d4_causal_gate = CausalCommunicationEvidenceGate()
        self._next_d4_readiness_s = 0.0
        self._next_d4_plan_broadcast_s = 0.0
        self._d4_message_sequence = 0
        self._d4_partition_generation = 0
        self._d4_last_broadcast_plan_key = None
        self._d4_readiness_receptions.clear()
        self._d4_plan_deliveries.clear()
        self._d4_ack_deliveries.clear()
        self._d4_runtime_ack_parser = RegionResourceRuntimeAckParser()
        self._d4_safe_adoption_assembler = RegionResourceSafeAdoptionAssembler(
            projector=getattr(self.d4_region_advisor, "projector", None)
        )
        self._d4_plan_source_envelopes.clear()
        self._d4_plan_transport_references.clear()
        self._d4_advice_source_envelopes.clear()
        self._d4_advisory_sources.clear()
        self._d4_a2_pending_by_plan.clear()
        self._d4_a2_evidence_by_application.clear()
        self._d4_owner_ack_delivery_count = 0
        self._d4_coalition_ack_delivery_count = 0
        self._d4_a2_physical_window_count = 0
        self._d4_a2_bridge_blocker_counts.clear()
        self._latest_runtime_state_payload_sha256 = None
        self._d4_expected_plan_authorities.clear()
        self._d4_communication_received_count = 0
        self._d4_communication_accepted_count = 0
        self._d4_communication_rejected_count = 0
        self._d4_communication_accept_counts.clear()
        self._d4_communication_rejection_counts.clear()
        self._d4_communication_intent_counts.clear()
        self._d4_communication_event_evaluation_count = 0
        self._d4_vetted_secondary_by_region.clear()
        self._d3_learning_frames.clear()
        self._d4_learning_frames.clear()
        self._d5_learning_frames.clear()
        self._d5_shadow_scoring_frame_count = 0
        self._d5_shadow_scoring_success_count = 0
        self._d5_shadow_scoring_rejected_count = 0
        self._d5_shadow_scoring_edge_count = 0
        self._d5_shadow_scoring_rejection_reasons.clear()
        self._d5_active_vision_learning_frames.clear()
        self._d5_a3_command_index = 0
        self._d5_a3_command_context_by_camera.clear()
        self._d5_a3_pending_by_camera.clear()
        self._d5_a3_evidence_by_comparison_key.clear()
        self._d5_a3_candidate_stage_by_comparison_key.clear()
        self._d5_a3_r0_pending_by_camera.clear()
        self._d5_a3_r0_window_by_comparison_key.clear()
        self._d5_a3_runtime_ack_count = 0
        self._d5_a3_r0_runtime_ack_count = 0
        self._d5_a3_observation_frame_count = 0
        self._d5_a3_r0_observation_frame_count = 0
        self._d5_a3_physical_window_count = 0
        self._d5_a3_r0_physical_window_count = 0
        self._d5_camera_empty_frame_received_count = 0
        self._d5_camera_empty_frame_consumed_count = 0
        self._d5_camera_empty_frame_rejected_count = 0
        self._d5_camera_empty_frame_unmatched_count = 0
        self._d5_active_vision_tail_suppressed_count = 0
        self._d5_a3_bridge_blocker_counts.clear()
        self._d2_identity_lineage_by_track.clear()
        self._d2_observation_replay_generation.clear()
        self._latest_d2_input_signature = None
        self._d2_pending_d1_update = False
        self._d1_posterior_generation = 0
        self._d2_pending_d1_posterior_generation = None
        self._d2_consumed_d1_posterior_generation = 0
        self._d2_posterior_consumption_count = 0
        self._d2_pre_tick_posterior_merge_count = 0
        self._d2_finalize_unchanged_posterior_skip_count = 0
        self._d2_finalize_coalesced_release_count = 0
        self._d2_publication_metadata_audit_batch_count = 0
        self._d2_publication_metadata_audit_totals.clear()
        self._d2_latest_publication_metadata_audit.clear()
        self._identity_commitment_binding_hold_count = 0
        self._identity_commitment_binding_hold_event_count = 0
        self._identity_commitment_binding_hold_target_ids = ()
        self._identity_commitment_replan_required = False
        self._pending_structural_ambiguity_evidence.clear()
        self._structural_ambiguity_evidence_received_count = 0
        self._structural_ambiguity_evidence_consumed_count = 0
        self._structural_ambiguity_d2_consumption_count = 0
        self._d1_centroid_overlay_shadow_state = (
            ExperimentalCentroidPublicationState()
        )
        self._d1_centroid_overlay_shadow_evaluation_count = 0
        self._d1_centroid_overlay_shadow_decision_count = 0
        self._d1_centroid_overlay_shadow_accepted_count = 0
        self._d1_centroid_overlay_shadow_rejected_count = 0
        self._d1_centroid_overlay_shadow_error_count = 0
        self._d1_centroid_overlay_shadow_rejection_reasons.clear()
        self._d1_centroid_overlay_shadow_forbidden_mutation_count = 0
        self._d1_centroid_overlay_shadow_max_watermark_count = 0
        self._d1_centroid_overlay_shadow_max_payload_bytes = 0
        self._d1_latest_lineage_by_observation.clear()
        self._d1_pending_lineage_by_track.clear()
        self._d1_scan_events.clear()
        self._d1_scan_event_total_count = 0
        self._d1_state_only_scan_count = 0
        self._d1_materialized_snapshot_count = 0
        self._d1_same_fusion_time_coalesced_scan_count = 0
        self._d1_publication_evidence_snapshot_counts.clear()
        self._d1_publication_evidence_snapshot_fallback_reasons.clear()
        self._d1_scan_input_closed = False
        self._stage_wall_time_s.clear()
        self._stage_call_count.clear()
        self._stage_samples_s.clear()

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        config = self._require_ready()
        now = float(step_input.timestamp)
        if not np.isfinite(now) or now < 0.0:
            raise ValueError("runtime timestamp must be finite and non-negative")
        self._validate_navigation(step_input.interceptors, "interceptor")
        self._validate_navigation(step_input.recon, "recon")
        self._latest_runtime_state_payload_sha256 = (
            self._runtime_state_payload_sha256(step_input)
        )
        self._resource_index_by_id = {
            resource_id: index
            for index, resource_id in enumerate(step_input.interceptors.platform_ids)
        }
        publications: list[RuntimePublication] = []
        communication_intents, d4_evidence_changed, d4_delivery_seen = (
            self._consume_d4_communication_deliveries(step_input, now=now)
        )
        if d4_delivery_seen:
            publications.append(self._d4_communication_publication(now))

        arrived = tuple(
            sorted(
                step_input.arrived_sensor_batches,
                key=lambda item: (
                    float(item.arrival_timestamp),
                    float(item.measurement_timestamp),
                    str(item.sensor_id),
                    str(item.batch_id),
                ),
            )
        )
        vision_batches = tuple(
            batch for batch in arrived if _batch_modality(batch) == "vision_bbox"
        )
        released_scans: list[Any] = []
        for batch in arrived:
            started = perf_counter()
            scan_result = self.d1_scan_input.ingest(
                self.d1_online_batch_frame_builder.build(batch)
            )
            self._record_timing("d1_scan_input", perf_counter() - started)
            self._record_d1_scan_events(scan_result.events)
            released_scans.extend(scan_result.released_scans)

        started = perf_counter()
        scan_clock_result = self.d1_scan_input.advance_arrival_time(now)
        self._record_timing("d1_scan_input_clock", perf_counter() - started)
        self._record_d1_scan_events(scan_clock_result.events)
        self._consume_d1_released_scans(
            released_scans,
            publications=publications,
            publication_timestamp=now,
        )

        if (
            self._d2_pending_d1_update
            and self.latest_d1_tracks
            and now + _EPS >= self._next_association_s
        ):
            associated = self._associate_latest_d1_tracks(
                publications,
                publication_timestamp=now,
                timing_stage="d2_association",
                source_d1_posterior_generation=(
                    self._d2_pending_d1_posterior_generation
                ),
            )
            if associated:
                self._d2_pending_d1_update = False
                self._d2_pending_d1_posterior_generation = None
                self._next_association_s = _advance_schedule(
                    self._next_association_s,
                    config.association_period_s,
                    now,
                )

        if vision_batches:
            started = perf_counter()
            self.latest_d5_result = self.d5.process(
                vision_batches,
                self.latest_d2_tracks,
                edge_model=self.d5_edge_model,
            )
            self.latest_d5_shadow_scoring = (
                self._evaluate_d5_shadow_scoring(now)
            )
            self._latest_terminal_by_pair = self._terminal_pairs_from_d5(
                self.latest_d5_result
            )
            if self.stack_config.capture_learning_artifacts:
                self._d5_learning_frames.append(
                    D5GraphLearningFrame(
                        frame_index=len(self._d5_learning_frames),
                        timestamp_s=now,
                        graph=self.latest_d5_result.association.graph,
                        source_observation_links=tuple(
                            self.latest_d5_result.source_observation_links
                        ),
                    )
                )
            self._record_timing("d5_terminal_association", perf_counter() - started)
            publications.append(self._d5_publication(now))
            if self.latest_d5_shadow_scoring is not None:
                publications.append(self._d5_shadow_scoring_publication(now))

        if step_input.arrived_camera_frame_events:
            self._record_active_vision_zero_detection_frames(
                step_input.arrived_camera_frame_events
            )

        center_health, secondary_failed = self._fault_state(now)
        self._fault_generation_changed = bool(
            self._fault_generation_changed
            or center_health != self._last_center_health
            or secondary_failed != self._last_secondary_failed
        )
        self._last_center_health = center_health
        self._last_secondary_failed = secondary_failed
        assignment_due = bool(
            self.latest_d2_tracks
            and now + _EPS >= self._next_assignment_s
        )
        if (
            d4_evidence_changed
            and not assignment_due
            and center_health is C2Health.FAILED
            and self.latest_plan is not None
            and self.latest_d2_tracks
        ):
            started = perf_counter()
            snapshot = self._d4_snapshot(
                step_input,
                now=now,
                center_health=center_health,
                secondary_failed=secondary_failed,
            )
            self.latest_d4_decision = self.d4.evaluate(snapshot)
            self._remember_d4_vetted_secondaries(
                self.latest_d4_decision
            )
            self._d4_communication_event_evaluation_count += 1
            self._record_timing(
                "d4_communication_event_failover",
                perf_counter() - started,
            )
            publications.append(self._d4_publication(now))

        if assignment_due:
            self._run_assignment_and_failover(
                step_input,
                now=now,
                center_health=center_health,
                secondary_failed=secondary_failed,
            )
            if (
                self.stack_config.capture_learning_artifacts
                and self.d3.latest_planning_evidence is not None
            ):
                self._d3_learning_frames.append(self.d3.latest_planning_evidence)
            if self.latest_plan is not None:
                publications.append(self._d3_publication(now))
            if self.latest_d4_decision is not None:
                publications.append(self._d4_publication(now))
            if self.latest_d4_region_consumption is not None:
                publications.append(self._d4_region_consumption_publication(now))
            if self.latest_d4_region_advice is not None:
                publications.append(self._d4_region_advice_publication(now))
            self._fault_generation_changed = False
            self._next_assignment_s = _advance_schedule(
                self._next_assignment_s,
                config.assignment_period_s,
                now,
            )

        self._advance_d4_a2_physical_windows(step_input, now=now)

        communication_intents.extend(
            self._d4_periodic_communication_intents(
                step_input,
                now=now,
                center_health=center_health,
                secondary_failed=secondary_failed,
            )
        )

        camera_commands: tuple[CameraObservationCommand, ...] = ()
        active_vision_ready = bool(
            self.stack_config.d5_active_vision_enabled
            and self.latest_plan is not None
            and self.latest_d2_tracks
            and step_input.cameras
            and now + _EPS >= self._next_active_vision_s
        )
        observation_trigger_satisfied = bool(
            not self.stack_config.d5_active_vision_observation_triggered
            or self._active_vision_communication_version == 0
            or vision_batches
            or step_input.arrived_camera_frame_events
        )
        evidence_tail_open = bool(
            now + self.stack_config.d5_active_vision_evidence_tail_s
            <= config.duration_s + _EPS
        )
        if (
            active_vision_ready
            and observation_trigger_satisfied
            and not evidence_tail_open
        ):
            self._d5_active_vision_tail_suppressed_count += 1
        if (
            active_vision_ready
            and observation_trigger_satisfied
            and evidence_tail_open
        ):
            started = perf_counter()
            camera_commands = self._run_active_vision(step_input, now)
            self._record_timing("d5_active_vision", perf_counter() - started)
            publications.append(self._d5_active_vision_publication(now, camera_commands))
            self._next_active_vision_s = _advance_schedule(
                self._next_active_vision_s,
                config.visual_period_s,
                now,
            )

        interceptor_acceleration = np.zeros((config.resource_count, 3), dtype=float)
        if self.latest_plan is not None and self.latest_d2_tracks:
            started = perf_counter()
            pair_inputs = self._guidance_inputs(step_input, now)
            self.latest_guidance_batch = self.d7.command_batch(
                pair_inputs,
                resource_count=config.resource_count,
            )
            interceptor_acceleration = self.latest_guidance_batch.to_world_acceleration()
            self._record_timing("d7_guidance", perf_counter() - started)
            publications.append(self._d7_publication(now))

        return RuntimeStepOutput(
            interceptor_acceleration_ned=interceptor_acceleration,
            recon_acceleration_ned=np.zeros((config.recon_count, 3), dtype=float),
            camera_commands=camera_commands,
            publications=tuple(publications),
            communication_intents=tuple(communication_intents),
            diagnostics=self._diagnostics(now),
        )

    def finalize(self, timestamp: float) -> RuntimeStepOutput:
        """Flush finite scan tails after the episode stops producing input.

        Finalization publishes every ordered D1 tail result, then sends only
        the final fused posterior to D2. It never emits a camera or motion
        command, so no post-episode control is applied to the world.
        """

        config = self._require_ready()
        now = float(timestamp)
        if not np.isfinite(now) or now < 0.0:
            raise ValueError("finalization timestamp must be finite and non-negative")
        self._finalize_all_d5_a3_pending(timestamp_s=now)
        if self._d1_scan_input_closed:
            return RuntimeStepOutput(
                interceptor_acceleration_ned=np.zeros(
                    (config.resource_count, 3), dtype=float
                ),
                recon_acceleration_ned=np.zeros((config.recon_count, 3), dtype=float),
                publications=(),
                diagnostics=self._diagnostics(
                    now,
                    include_timing_distribution=True,
                ),
            )

        publications: list[RuntimePublication] = []
        started = perf_counter()
        scan_result = self.d1_scan_input.close()
        self._record_timing("d1_scan_input_finalize", perf_counter() - started)
        self._consume_d1_scan_result(
            scan_result,
            publications=publications,
            publication_timestamp=now,
        )
        released_count = len(scan_result.released_scans)
        if released_count or self._d2_pending_d1_update:
            self._d2_finalize_coalesced_release_count += max(0, released_count - 1)
            associated = self._associate_latest_d1_tracks(
                publications,
                publication_timestamp=now,
                timing_stage="d2_association_finalize",
                source_d1_posterior_generation=(
                    self._d2_pending_d1_posterior_generation
                ),
            )
            if (
                not associated
                and self._pending_structural_ambiguity_evidence
            ):
                raise RuntimeError(
                    "finalization cannot discard pending structural "
                    "ambiguity evidence"
                )
            if not associated:
                raise RuntimeError(
                    "finalization failed to consume pending D1 posterior "
                    f"generation {self._d2_pending_d1_posterior_generation}"
                )
            self._d2_pending_d1_update = False
            self._d2_pending_d1_posterior_generation = None
        self._d1_scan_input_closed = True

        return RuntimeStepOutput(
            interceptor_acceleration_ned=np.zeros(
                (config.resource_count, 3), dtype=float
            ),
            recon_acceleration_ned=np.zeros((config.recon_count, 3), dtype=float),
            publications=tuple(publications),
            diagnostics=self._diagnostics(
                now,
                include_timing_distribution=True,
            ),
        )

    def observation_governance_audit(self) -> dict[str, Any]:
        """Return a truth-free public snapshot for main/D6 persistence."""

        self._require_ready()
        d1_audit = self.d1_scan_input.audit_summary().to_dict()
        d1_execution_config = self.d1_scan_input.execution_config()
        d1_performance_diagnostics = (
            self.d1_scan_input.performance_diagnostics()
        )
        d1_online_batch_frame_diagnostics = (
            self.d1_online_batch_frame_builder.diagnostics()
        )
        d2_summary = self.d2.summary()
        return {
            "schema_version": "scalable3d-observation-governance-runtime-v2",
            "d1_scan_input": d1_audit,
            "d1_scan_input_implementation": self.d1_scan_input.implementation,
            "d1_scan_input_execution_config": d1_execution_config,
            "d1_scan_input_performance_diagnostics": (
                d1_performance_diagnostics
            ),
            "d1_online_batch_frame_implementation": (
                self.d1_online_batch_frame_builder.implementation
            ),
            "d1_online_batch_frame_execution_config": (
                self.d1_online_batch_frame_builder.execution_config()
            ),
            "d1_online_batch_frame_diagnostics": (
                d1_online_batch_frame_diagnostics
            ),
            "d1_publication_metadata_implementation": (
                self.stack_config.d1_publication_metadata_implementation
            ),
            "d1_publication_metadata_diagnostics": (
                self.d1.publication_materialization_diagnostics()
            ),
            "d1_cv_motion_model_implementation": (
                self.stack_config.d1_cv_motion_model_implementation
            ),
            "d1_cv_motion_model_cache_diagnostics": (
                self.d1.cv_motion_model_cache_diagnostics()
            ),
            "d1_opaque_source_identity_implementation": (
                self.stack_config.d1_opaque_source_identity_implementation
            ),
            "d1_opaque_source_identity_cache_diagnostics": (
                self.d1.opaque_source_identity_cache_diagnostics()
            ),
            "d1_structured_numerical_jacobian_implementation": (
                self.stack_config
                .d1_structured_numerical_jacobian_implementation
            ),
            "d1_structured_numerical_jacobian_diagnostics": (
                self.d1.structured_numerical_jacobian_diagnostics()
            ),
            "d1_association_sparse_prefilter_implementation": (
                self.stack_config
                .d1_association_sparse_prefilter_implementation
            ),
            "d1_association_sparse_prefilter_execution_config": (
                self.d1.association_sparse_prefilter_execution_config()
            ),
            "d1_association_sparse_prefilter_diagnostics": (
                self.d1.association_sparse_prefilter_diagnostics()
            ),
            "d1_replay_prefix_summary_implementation": (
                self.stack_config.d1_replay_prefix_summary_implementation
            ),
            "d1_replay_prefix_summary_execution_config": (
                self.d1.replay_prefix_summary_execution_config()
            ),
            "d1_replay_prefix_summary_diagnostics": (
                self.d1.replay_prefix_summary_diagnostics()
            ),
            "d1_publication_evidence_snapshot_implementation": (
                self.stack_config
                .d1_publication_evidence_snapshot_implementation
            ),
            "d1_publication_evidence_snapshot_execution_config": (
                _d1_publication_evidence_snapshot_execution_config(
                    self.stack_config
                )
            ),
            "d1_publication_evidence_snapshot_diagnostics": (
                self._d1_publication_evidence_snapshot_diagnostics()
            ),
            "d1_scan_event_total_count": self._d1_scan_event_total_count,
            "d1_scan_event_retained_count": len(self._d1_scan_events),
            "d1_scan_event_log_limit": self._d1_scan_events.maxlen,
            "d1_scan_events": tuple(self._d1_scan_events),
            "d1_coalesce_same_fusion_time_enabled": bool(
                self.stack_config.d1_coalesce_same_fusion_time
            ),
            "d1_fusion_association": self.d1.association_audit_summary(),
            "d1_state_only_scan_count": int(self._d1_state_only_scan_count),
            "d1_materialized_snapshot_count": int(
                self._d1_materialized_snapshot_count
            ),
            "d1_same_fusion_time_coalesced_scan_count": int(
                self._d1_same_fusion_time_coalesced_scan_count
            ),
            "d2_claim_ledger": dict(
                d2_summary.get("observation_claim_ledger", {})
            ),
            "d2_observation_rejection_reason_counts": dict(
                d2_summary.get("observation_rejection_reason_counts", {})
            ),
            "d2_publication_metadata_audit": {
                "schema_version": (
                    "scalable3d-d2-publication-metadata-audit-v1"
                ),
                "batch_count": int(
                    self._d2_publication_metadata_audit_batch_count
                ),
                "latest": dict(
                    sorted(
                        self._d2_latest_publication_metadata_audit.items()
                    )
                ),
                "totals": dict(
                    sorted(
                        self._d2_publication_metadata_audit_totals.items()
                    )
                ),
            },
            "d2_duplicate_coalescence_count": int(
                d2_summary.get("duplicate_coalescence_count", 0)
            ),
            "d2_replay_quarantine_count": int(
                d2_summary.get("replay_quarantine_count", 0)
            ),
            "d2_replay_coast_count": int(
                d2_summary.get("replay_coast_count", 0)
            ),
            "d2_replay_coast_reason_counts": dict(
                d2_summary.get("replay_coast_reason_counts", {})
            ),
            "d2_replay_coast_config": dict(
                d2_summary.get("replay_coast_config", {})
            ),
            "d1_d2_structural_ambiguity_hold_enabled": bool(
                self.stack_config.d1_d2_structural_ambiguity_hold_enabled
            ),
            "d1_publish_opaque_source_key": bool(
                self.stack_config.d1_publish_opaque_source_key
            ),
            "d1_identity_neutral_centroid_correction_enabled": bool(
                self.stack_config
                .d1_identity_neutral_centroid_correction_enabled
            ),
            "d1_centroid_publication_overlay_shadow_enabled": bool(
                self.stack_config
                .d1_centroid_publication_overlay_shadow_enabled
            ),
            "d1_centroid_publication_overlay_shadow_status": (
                "offline_shadow_not_consumed"
                if self.stack_config
                .d1_centroid_publication_overlay_shadow_enabled
                else "disabled"
            ),
            "d1_centroid_overlay_shadow_evaluation_count": int(
                self._d1_centroid_overlay_shadow_evaluation_count
            ),
            "d1_centroid_overlay_shadow_decision_count": int(
                self._d1_centroid_overlay_shadow_decision_count
            ),
            "d1_centroid_overlay_shadow_accepted_count": int(
                self._d1_centroid_overlay_shadow_accepted_count
            ),
            "d1_centroid_overlay_shadow_rejected_count": int(
                self._d1_centroid_overlay_shadow_rejected_count
            ),
            "d1_centroid_overlay_shadow_error_count": int(
                self._d1_centroid_overlay_shadow_error_count
            ),
            "d1_centroid_overlay_shadow_rejection_reason_counts": dict(
                sorted(
                    self
                    ._d1_centroid_overlay_shadow_rejection_reasons
                    .items()
                )
            ),
            "d1_centroid_overlay_shadow_forbidden_mutation_count": int(
                self._d1_centroid_overlay_shadow_forbidden_mutation_count
            ),
            "d1_centroid_overlay_shadow_watermark_count": len(
                self._d1_centroid_overlay_shadow_state.watermarks
            ),
            "d1_centroid_overlay_shadow_max_watermark_count": int(
                self._d1_centroid_overlay_shadow_max_watermark_count
            ),
            "d1_centroid_overlay_shadow_watermark_capacity": int(
                self._d1_centroid_overlay_shadow_state.max_entries
            ),
            "d1_centroid_overlay_shadow_max_payload_bytes": int(
                self._d1_centroid_overlay_shadow_max_payload_bytes
            ),
            "d1_centroid_overlay_shadow_d2_consumption_count": 0,
            "d1_centroid_overlay_shadow_d3_consumption_count": 0,
            "d1_structural_ambiguity_publisher_node_id": (
                DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID
            ),
            "d1_structural_ambiguity_publisher_epoch": (
                self._d1_publisher_epoch
            ),
            "d1_structural_ambiguity_evidence_received_count": int(
                self._structural_ambiguity_evidence_received_count
            ),
            "d1_structural_ambiguity_pending_evidence_count": len(
                self._pending_structural_ambiguity_evidence
            ),
            "d2_structural_ambiguity_evidence_consumed_count": int(
                self._structural_ambiguity_evidence_consumed_count
            ),
            "d2_structural_ambiguity_consumption_count": int(
                self._structural_ambiguity_d2_consumption_count
            ),
            "d2_ambiguity_hold_config": dict(
                d2_summary.get("ambiguity_hold_config", {})
            ),
            "d2_ambiguity_hold_active_component_count": int(
                d2_summary.get(
                    "ambiguity_hold_active_component_count",
                    0,
                )
            ),
            "d2_ambiguity_hold_active_track_count": int(
                d2_summary.get("ambiguity_hold_active_track_count", 0)
            ),
            "d2_ambiguity_hold_reserved_evidence_count": int(
                d2_summary.get(
                    "ambiguity_hold_reserved_evidence_count",
                    0,
                )
            ),
            "d2_ambiguity_hold_component_event_counts": dict(
                d2_summary.get(
                    "ambiguity_hold_component_event_counts",
                    {},
                )
            ),
            "d2_ambiguity_hold_prevented_counts": dict(
                d2_summary.get("ambiguity_hold_prevented_counts", {})
            ),
            "d2_binding_pre_update_rejection_count": int(
                d2_summary.get("binding_pre_update_rejection_count", 0)
            ),
            "d3_identity_commitment_binding_hold_count": int(
                self._identity_commitment_binding_hold_count
            ),
            "d3_identity_commitment_binding_hold_event_count": int(
                self._identity_commitment_binding_hold_event_count
            ),
            "d3_identity_commitment_binding_hold_target_ids": (
                self._identity_commitment_binding_hold_target_ids
            ),
            "d3_identity_commitment_replan_required": bool(
                self._identity_commitment_replan_required
            ),
            "d1_posterior_generation": int(self._d1_posterior_generation),
            "d2_pending_d1_posterior_generation": (
                None
                if self._d2_pending_d1_posterior_generation is None
                else int(self._d2_pending_d1_posterior_generation)
            ),
            "d2_consumed_d1_posterior_generation": int(
                self._d2_consumed_d1_posterior_generation
            ),
            "d2_posterior_consumption_count": int(
                self._d2_posterior_consumption_count
            ),
            "d2_pre_tick_posterior_merge_count": int(
                self._d2_pre_tick_posterior_merge_count
            ),
            "d2_finalize_unchanged_posterior_skip_count": int(
                self._d2_finalize_unchanged_posterior_skip_count
            ),
            "d2_finalize_coalesced_release_count": int(
                self._d2_finalize_coalesced_release_count
            ),
            "d2_timestamp_conflict_count": int(
                d2_summary.get("observation_timestamp_conflict_count", 0)
            ),
            "d2_tracker_state_timestamp": self.d2.state_timestamp,
            "online_truth_use_count": 0,
        }

    def _d1_publication_evidence_snapshot_diagnostics(
        self,
    ) -> dict[str, Any]:
        names = (
            "selection_count",
            "reference_selection_count",
            "candidate_selection_count",
            "candidate_subset_success_count",
            "candidate_fallback_count",
            "adapter_snapshot_call_count",
            "full_snapshot_call_count",
            "subset_snapshot_call_count",
            "publication_count",
            "source_observation_reference_count",
            "track_latest_observation_reference_count",
            "required_observation_id_count",
            "duplicate_reference_count",
            "invalid_required_id_count",
            "empty_required_id_selection_count",
            "returned_record_count",
            "lookup_miss_count",
        )
        counts = {
            name: int(
                self._d1_publication_evidence_snapshot_counts.get(name, 0)
            )
            for name in names
        }
        return {
            "schema_version": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "execution_config": (
                _d1_publication_evidence_snapshot_execution_config(
                    self.stack_config
                )
            ),
            "operation_counts": counts,
            "fallback_reason_counts": dict(
                sorted(
                    self
                    ._d1_publication_evidence_snapshot_fallback_reasons
                    .items()
                )
            ),
            "conservation": {
                "selection_partition": (
                    counts["selection_count"]
                    == counts["reference_selection_count"]
                    + counts["candidate_selection_count"]
                ),
                "candidate_selection_partition": (
                    counts["candidate_selection_count"]
                    == counts["candidate_subset_success_count"]
                    + counts["candidate_fallback_count"]
                ),
                "adapter_call_partition": (
                    counts["adapter_snapshot_call_count"]
                    == counts["full_snapshot_call_count"]
                    + counts["subset_snapshot_call_count"]
                ),
                "reference_deduplication_partition": (
                    counts["source_observation_reference_count"]
                    + counts["track_latest_observation_reference_count"]
                    == counts["required_observation_id_count"]
                    + counts["duplicate_reference_count"]
                ),
                "fallback_not_above_candidate_selection": (
                    counts["candidate_fallback_count"]
                    <= counts["candidate_selection_count"]
                ),
                "all_required_records_available": (
                    counts["lookup_miss_count"] == 0
                    and counts["invalid_required_id_count"] == 0
                ),
            },
        }

    @staticmethod
    def _required_d1_publication_evidence_ids(
        processed: Iterable[tuple[Any, ...]],
    ) -> tuple[tuple[str, ...], int, int, int]:
        required_ids: set[str] = set()
        source_reference_count = 0
        track_reference_count = 0
        invalid_required_id_count = 0
        for item in processed:
            result, batch = item[0], item[1]
            source_observations = tuple(
                getattr(
                    batch,
                    "measurements",
                    getattr(batch, "observations", ()),
                )
            )
            for observation in source_observations:
                raw_observation_id = getattr(
                    observation,
                    "observation_id",
                    None,
                )
                if (
                    not isinstance(raw_observation_id, str)
                    or not raw_observation_id
                ):
                    invalid_required_id_count += 1
                    continue
                source_reference_count += 1
                required_ids.add(raw_observation_id)

            if not bool(getattr(result, "tracks_materialized", True)):
                continue
            for track in tuple(getattr(result, "tracks", ())):
                metadata = getattr(track, "metadata", {})
                if not isinstance(metadata, Mapping):
                    continue
                observation_id = str(
                    metadata.get("latest_observation_id", "")
                ).strip()
                if not observation_id:
                    continue
                track_reference_count += 1
                required_ids.add(observation_id)
        return (
            tuple(sorted(required_ids)),
            source_reference_count,
            track_reference_count,
            invalid_required_id_count,
        )

    def _d1_publication_evidence_by_observation(
        self,
        processed: tuple[tuple[Any, ...], ...],
    ) -> dict[str, Any]:
        counts = self._d1_publication_evidence_snapshot_counts
        counts["selection_count"] += 1
        counts["publication_count"] += len(processed)
        candidate_enabled = (
            self.stack_config
            .d1_publication_evidence_snapshot_implementation
            == D1_PUBLICATION_EVIDENCE_SNAPSHOT_CANDIDATE_IMPLEMENTATION
        )
        if not candidate_enabled:
            counts["reference_selection_count"] += 1
            counts["full_snapshot_call_count"] += 1
            counts["adapter_snapshot_call_count"] += 1
            records = self.d1.consistency_evidence_snapshot()
            counts["returned_record_count"] += len(records)
            return {item.observation_id: item for item in records}

        (
            required_ids,
            source_reference_count,
            track_reference_count,
            invalid_required_id_count,
        ) = self._required_d1_publication_evidence_ids(processed)
        counts["source_observation_reference_count"] += (
            source_reference_count
        )
        counts["track_latest_observation_reference_count"] += (
            track_reference_count
        )
        counts["required_observation_id_count"] += len(required_ids)
        counts["duplicate_reference_count"] += (
            source_reference_count
            + track_reference_count
            - len(required_ids)
        )
        counts["invalid_required_id_count"] += (
            invalid_required_id_count
        )
        if not required_ids:
            counts["empty_required_id_selection_count"] += 1

        fallback_reason: str | None = None
        records: tuple[Any, ...]
        counts["candidate_selection_count"] += 1
        if invalid_required_id_count:
            fallback_reason = "invalid_required_observation_id"
            records = ()
        elif not required_ids:
            fallback_reason = "empty_required_observation_id_set"
            records = ()
        else:
            counts["subset_snapshot_call_count"] += 1
            counts["adapter_snapshot_call_count"] += 1
            try:
                records = self.d1.consistency_evidence_snapshot(
                    required_ids
                )
            except KeyError:
                fallback_reason = "unknown_required_observation_id"
                records = ()
            except ValueError:
                fallback_reason = "invalid_required_observation_id"
                records = ()

        evidence_by_observation = {
            item.observation_id: item for item in records
        }
        missing_required_ids = set(required_ids).difference(
            evidence_by_observation
        )
        if (
            fallback_reason is None
            and missing_required_ids
        ):
            fallback_reason = "subset_snapshot_missing_required_record"

        if fallback_reason is not None:
            counts["candidate_fallback_count"] += 1
            self._d1_publication_evidence_snapshot_fallback_reasons[
                fallback_reason
            ] += 1
            counts["full_snapshot_call_count"] += 1
            counts["adapter_snapshot_call_count"] += 1
            records = self.d1.consistency_evidence_snapshot()
            evidence_by_observation = {
                item.observation_id: item for item in records
            }
            missing_required_ids = set(required_ids).difference(
                evidence_by_observation
            )
        else:
            counts["candidate_subset_success_count"] += 1

        counts["returned_record_count"] += len(records)
        counts["lookup_miss_count"] += len(missing_required_ids)
        return evidence_by_observation

    def _consume_d1_scan_result(
        self,
        scan_result: Any,
        *,
        publications: list[RuntimePublication],
        publication_timestamp: float,
    ) -> bool:
        self._record_d1_scan_events(scan_result.events)
        return self._consume_d1_released_scans(
            scan_result.released_scans,
            publications=publications,
            publication_timestamp=publication_timestamp,
        )

    def _consume_d1_released_scans(
        self,
        released_scans: Iterable[Any],
        *,
        publications: list[RuntimePublication],
        publication_timestamp: float,
    ) -> bool:
        """Fuse ordered scans and materialize one snapshot per fusion time.

        D1 state updates remain strictly ordered.  When several consecutive
        scans resolve to the same nondecreasing fusion timestamp, only the last
        posterior is converted into detached ``GlobalTrack`` objects.  Every
        scan still emits its batch summary and observation lineage.
        """

        scans = tuple(released_scans)
        if not scans:
            return False

        processed: list[
            tuple[
                Any,
                Any,
                int | None,
                tuple[Any, ...] | None,
                ExperimentalCentroidEvidenceDisposition | None,
            ]
        ] = []
        shadow_evidence: list[Any] = []
        shadow_oosm_evidence_ids: set[str] = set()
        shadow_stale_evidence_ids: set[str] = set()
        for index, released_scan in enumerate(scans):
            previous_fusion_time = float(self.d1.current_time)
            fusion_timestamp = max(
                previous_fusion_time,
                float(released_scan.arrival_timestamp),
            )
            next_fusion_timestamp = None
            if index + 1 < len(scans):
                next_fusion_timestamp = max(
                    fusion_timestamp,
                    float(scans[index + 1].arrival_timestamp),
                )
            materialize_tracks = bool(
                not self.stack_config.d1_coalesce_same_fusion_time
                or next_fusion_timestamp is None
                or next_fusion_timestamp > fusion_timestamp + _EPS
            )
            started = perf_counter()
            result = self.d1.process_scan_batch(
                released_scan.observations,
                materialize_tracks=materialize_tracks,
            )
            self._record_timing("d1_fusion", perf_counter() - started)
            self._latch_structural_ambiguity_evidence(result)
            shadow_context: tuple[Any, ...] | None = None
            shadow_disposition: (
                ExperimentalCentroidEvidenceDisposition | None
            ) = None
            if (
                self.stack_config
                .d1_centroid_publication_overlay_shadow_enabled
            ):
                result_evidence = tuple(
                    getattr(result, "structural_ambiguity_evidence", ())
                )
                shadow_evidence.extend(result_evidence)
                observations = tuple(released_scan.observations)
                scan_has_oosm = any(
                    float(item.measurement_timestamp)
                    < previous_fusion_time - _EPS
                    for item in observations
                )
                scan_has_stale = any(
                    bool(item.is_stale_at(fusion_timestamp))
                    for item in observations
                )
                if scan_has_oosm:
                    shadow_oosm_evidence_ids.update(
                        str(item.evidence_id) for item in result_evidence
                    )
                if scan_has_stale:
                    shadow_stale_evidence_ids.update(
                        str(item.evidence_id) for item in result_evidence
                    )
            if materialize_tracks:
                self.latest_d1_tracks = tuple(result.tracks)
                self._d1_materialized_snapshot_count += 1
                self._d1_posterior_generation += 1
                if self._d2_pending_d1_update:
                    self._d2_pre_tick_posterior_merge_count += 1
                self._d2_pending_d1_update = True
                self._d2_pending_d1_posterior_generation = int(
                    self._d1_posterior_generation
                )
                posterior_generation: int | None = int(
                    self._d1_posterior_generation
                )
                if (
                    self.stack_config
                    .d1_centroid_publication_overlay_shadow_enabled
                ):
                    if shadow_evidence:
                        shadow_context = tuple(shadow_evidence)
                        shadow_disposition = (
                            ExperimentalCentroidEvidenceDisposition(
                                oosm_evidence_ids=frozenset(
                                    shadow_oosm_evidence_ids
                                ),
                                stale_evidence_ids=frozenset(
                                    shadow_stale_evidence_ids
                                ),
                            )
                        )
                    shadow_evidence.clear()
                    shadow_oosm_evidence_ids.clear()
                    shadow_stale_evidence_ids.clear()
            else:
                self._d1_state_only_scan_count += 1
                self._d1_same_fusion_time_coalesced_scan_count += 1
                posterior_generation = None
            processed.append(
                (
                    result,
                    released_scan,
                    posterior_generation,
                    shadow_context,
                    shadow_disposition,
                )
            )

        evidence_by_observation = (
            self._d1_publication_evidence_by_observation(tuple(processed))
        )
        for (
            result,
            released_scan,
            posterior_generation,
            shadow_context,
            shadow_disposition,
        ) in processed:
            publications.append(
                self._d1_publication(
                    result,
                    released_scan,
                    publication_timestamp,
                    evidence_by_observation=evidence_by_observation,
                    posterior_generation=posterior_generation,
                )
            )
            if shadow_context is not None:
                assert shadow_disposition is not None
                publications.append(
                    self._d1_centroid_overlay_shadow_publication(
                        canonical_tracks=tuple(result.tracks),
                        evidence_items=shadow_context,
                        disposition=shadow_disposition,
                        publication_timestamp=publication_timestamp,
                        posterior_generation=posterior_generation,
                    )
                )
        return True

    def _latch_structural_ambiguity_evidence(self, result: Any) -> None:
        """Retain every D1 sidecar until one successful D2 consumption."""

        evidence_items = tuple(
            getattr(result, "structural_ambiguity_evidence", ())
        )
        for evidence in evidence_items:
            evidence_id = str(evidence.evidence_id)
            existing = self._pending_structural_ambiguity_evidence.get(
                evidence_id
            )
            if existing is not None:
                if existing.to_dict() != evidence.to_dict():
                    raise RuntimeError(
                        "conflicting structural ambiguity evidence_id"
                    )
                continue
            if (
                len(self._pending_structural_ambiguity_evidence)
                >= self.stack_config.d1_ambiguity_pending_evidence_limit
            ):
                raise RuntimeError(
                    "structural ambiguity pending evidence limit exceeded"
                )
            self._pending_structural_ambiguity_evidence[evidence_id] = evidence
            self._structural_ambiguity_evidence_received_count += 1

    def _record_d1_scan_events(self, events: Iterable[Any]) -> None:
        records = tuple(item.to_dict() for item in events)
        self._d1_scan_event_total_count += len(records)
        self._d1_scan_events.extend(records)

    def _associate_latest_d1_tracks(
        self,
        publications: list[RuntimePublication],
        *,
        publication_timestamp: float,
        timing_stage: str,
        skip_unchanged_posterior: bool = False,
        source_d1_posterior_generation: int | None = None,
    ) -> bool:
        if not self.latest_d1_tracks:
            return False
        started = perf_counter()
        hold_enabled = bool(
            self.stack_config.d1_d2_structural_ambiguity_hold_enabled
        )
        if self._pending_structural_ambiguity_evidence and not hold_enabled:
            raise RuntimeError(
                "D1 structural ambiguity evidence requires the atomic "
                "D1-D2 hold treatment"
            )
        ambiguity_components = tuple(
            AmbiguityComponent3D.from_mapping(evidence.to_dict())
            for _, evidence in sorted(
                self._pending_structural_ambiguity_evidence.items()
            )
        )
        detection_batch = detections3d_from_d1_global_tracks_with_audit(
            self.latest_d1_tracks,
            use_opaque_d1_source_tokens=hold_enabled,
            publisher_node_id=(
                DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID
            ),
            publisher_epoch=(
                self._d1_publisher_epoch if hold_enabled else None
            ),
        )
        detections = detection_batch.detections
        audit = detection_batch.metadata_audit.to_dict()
        self._d2_publication_metadata_audit_batch_count += 1
        self._d2_latest_publication_metadata_audit = {
            str(key): int(value) for key, value in audit.items()
        }
        self._d2_publication_metadata_audit_totals.update(
            self._d2_latest_publication_metadata_audit
        )
        if not detections:
            self._record_timing(timing_stage, perf_counter() - started)
            return False
        input_signature = _d2_input_signature(detections)
        if (
            skip_unchanged_posterior
            and input_signature == self._latest_d2_input_signature
            and not ambiguity_components
        ):
            self._d2_finalize_unchanged_posterior_skip_count += 1
            self._record_timing(timing_stage, perf_counter() - started)
            return False
        d2_timestamp = max(item.measurement_timestamp for item in detections)
        if (
            self.d2.state_timestamp is not None
            and d2_timestamp + _EPS < self.d2.state_timestamp
        ):
            self._record_timing(timing_stage, perf_counter() - started)
            return False
        self.latest_d2_result = self.d2.step(
            detections,
            d2_timestamp,
            ambiguity_components=ambiguity_components,
        )
        self._latest_d2_input_signature = input_signature
        self.latest_d2_tracks = tuple(self.d2.active_tracks())
        self._update_d2_identity_lineage(self.latest_d2_result, detections)
        self._reconcile_active_bindings_with_identity_commitment(
            self.latest_d2_result
        )
        self._d2_consumed_d1_posterior_generation = int(
            self._d1_posterior_generation
            if source_d1_posterior_generation is None
            else source_d1_posterior_generation
        )
        self._d2_posterior_consumption_count += 1
        if ambiguity_components:
            consumed_count = len(ambiguity_components)
            self._structural_ambiguity_evidence_consumed_count += (
                consumed_count
            )
            self._structural_ambiguity_d2_consumption_count += 1
            self._pending_structural_ambiguity_evidence.clear()
        publications.append(self._d2_publication(publication_timestamp))
        self._record_timing(timing_stage, perf_counter() - started)
        return True

    def _run_assignment_and_failover(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
        center_health: C2Health,
        secondary_failed: bool,
    ) -> None:
        config = self._require_ready()
        previous_region_snapshot = self.latest_d4_region_snapshot
        previous_region_advice = self.latest_d4_region_advice
        previous_d4_decision = self.latest_d4_decision
        self.latest_d4_region_advice = None
        self.latest_d4_region_consumption = None
        self._d4_region_hint_bridge_rejection_reason = None
        adapter_started = perf_counter()
        tracks = self._d3_tracks()
        resources = self._d3_resources(step_input.interceptors)
        self._record_timing("main_d3_adapter", perf_counter() - adapter_started)
        previous_plan = self.latest_plan
        preplanning_snapshot: RegionalFailoverSnapshot | None = None
        if previous_plan is not None and not self._fault_generation_changed:
            preplanning_snapshot = self._d4_snapshot(
                step_input,
                now=now,
                center_health=center_health,
                secondary_failed=secondary_failed,
            )
            started = perf_counter()
            self.latest_d4_decision = self.d4.evaluate(
                preplanning_snapshot
            )
            self._remember_d4_vetted_secondaries(
                self.latest_d4_decision
            )
            self._record_timing(
                "d4_preplanning_refresh",
                perf_counter() - started,
            )
        current_target_ids = {track.track_id for track in tracks}
        previous_target_ids = (
            set()
            if previous_plan is None
            else {
                *(item.target_id for item in previous_plan.assignments),
                *previous_plan.unassigned_target_ids,
                *previous_plan.incomplete_target_ids,
            }
        )
        selected_secondary = (
            None
            if secondary_failed or previous_plan is None
            else self._selected_secondary_for_active_regions(previous_plan)
        )
        active_owner = (
            "center"
            if previous_plan is None
            else str(previous_plan.metadata.get("active_plan_owner", "center"))
        )
        if active_owner == "secondary" and previous_plan is not None:
            current_secondary = str(previous_plan.metadata.get("owner_node_id", ""))
            if selected_secondary != current_secondary:
                selected_secondary = None
        if center_health == C2Health.FAILED:
            if previous_plan is None:
                # No accepted authority exists from which a fallback generation
                # can legally advance.  The caller remains fail-closed.
                self.latest_plan = None
                self.latest_bindings = ()
                self.latest_d4_decision = None
                return
            force_secondary_failure_fence = bool(
                self._fault_generation_changed and secondary_failed
            )
            regional_authority: RegionalAuthorityInput | None = None
            regional_authority_attempted = bool(
                not force_secondary_failure_fence
                and self._has_fallback_authority_decision()
            )
            if regional_authority_attempted:
                try:
                    regional_authority = self._regional_authority_from_d4(
                        previous_plan,
                        target_ids=current_target_ids,
                        now=now,
                    )
                except RegionalPlanAuthorityError as error:
                    self._regional_plan_rejection_reason = error.reason

            if force_secondary_failure_fence:
                if previous_region_advice is not None:
                    self._d4_region_hint_bridge_rejection_reason = (
                        "secondary_failure_generation_fence_before_advisory"
                    )
                started = perf_counter()
                self.latest_plan = self.d3.advance_authority_generation(
                    previous_plan,
                    timestamp=now,
                    expected_previous_version=previous_plan.version,
                    fence_reason=(
                        "secondary_failure_before_distributed_adjudication"
                    ),
                )
                self._record_timing(
                    "d3_authority_fence",
                    perf_counter() - started,
                )
                self._regional_plan_rejection_reason = None
            elif regional_authority is not None:
                if previous_region_advice is not None:
                    self._d4_region_hint_bridge_rejection_reason = (
                        "regional_authority_path_does_not_consume_resource_advice"
                    )
                started = perf_counter()
                try:
                    self.latest_plan = self.d3.plan_regional_authority(
                        tracks,
                        resources,
                        timestamp=now,
                        previous_plan=previous_plan,
                        authority=regional_authority,
                        expected_previous_version=previous_plan.version,
                    )
                    self._regional_plan_rejection_reason = None
                except RegionalPlanAuthorityError as error:
                    self.latest_plan = previous_plan
                    self._regional_plan_rejection_reason = error.reason
                self._record_timing("d3_regional_assignment", perf_counter() - started)
            elif regional_authority_attempted:
                # A malformed or incomplete regional authority must not fall
                # through to a different owner path.
                self.latest_plan = previous_plan
            elif selected_secondary is not None:
                regional_hint = self._d3_regional_hint_from_previous_d4(
                    previous_plan=previous_plan,
                    advice_result=previous_region_advice,
                    source_snapshot=previous_region_snapshot,
                    source_decision=previous_d4_decision,
                    now=now,
                    fault_generation_changed=self._fault_generation_changed,
                )
                started = perf_counter()
                candidate = self.d3.plan(
                    tracks,
                    resources,
                    timestamp=now,
                    previous_plan=previous_plan,
                    expected_previous_version=previous_plan.version,
                    forced_replan=(
                        self._fault_generation_changed
                        or current_target_ids != previous_target_ids
                        or self._identity_commitment_replan_required
                    ),
                    publish=False,
                    regional_planning_hint=regional_hint,
                )
                self._record_d3_regional_hint_outcome(candidate, regional_hint)
                lease_expires_at = now + max(
                    config.assignment_period_s
                    * self.stack_config.assignment_lease_multiplier,
                    config.region_policy_period_s,
                )
                if active_owner == "secondary":
                    leader_epoch = int(
                        previous_plan.metadata.get(
                            "secondary_leader_epoch",
                            previous_plan.version,
                        )
                    )
                    self.latest_plan = continue_active_secondary_plan(
                        candidate,
                        previous_plan=previous_plan,
                        readiness_class="takeover_ready",
                        readiness_sustained=True,
                        published_at_s=now,
                        lease_expires_at_s=lease_expires_at,
                        leader_epoch=leader_epoch,
                    )
                else:
                    self.latest_plan = prepare_secondary_takeover_plan(
                        candidate,
                        supersedes_plan=previous_plan,
                        secondary_node_id=selected_secondary,
                        readiness_class="takeover_ready",
                        readiness_sustained=True,
                        activated_at_s=now,
                        lease_expires_at_s=lease_expires_at,
                        leader_epoch=previous_plan.version + 1,
                    )
                self.latest_plan = self.d3.publish_plan(self.latest_plan)
                self._record_timing("d3_assignment", perf_counter() - started)
                self._regional_plan_rejection_reason = None
            elif self._fault_generation_changed:
                if previous_region_advice is not None:
                    self._d4_region_hint_bridge_rejection_reason = (
                        "fault_generation_changed_before_advisory_consumption"
                    )
                # Multi-owner fallback requires D4 to observe a strictly newer
                # D3 generation before authority can change.  This center-owned
                # fence plan is immediately gated by the D4 decision below.
                started = perf_counter()
                self.latest_plan = self.d3.advance_authority_generation(
                    previous_plan,
                    timestamp=now,
                    expected_previous_version=previous_plan.version,
                    fence_reason="fault_generation_before_regional_adjudication",
                )
                self._record_timing("d3_authority_fence", perf_counter() - started)
                self._regional_plan_rejection_reason = None
            else:
                self.latest_plan = previous_plan
        else:
            regional_hint = self._d3_regional_hint_from_previous_d4(
                previous_plan=previous_plan,
                advice_result=previous_region_advice,
                source_snapshot=previous_region_snapshot,
                source_decision=previous_d4_decision,
                now=now,
                fault_generation_changed=self._fault_generation_changed,
            )
            started = perf_counter()
            self.latest_plan = self.d3.plan(
                tracks,
                resources,
                timestamp=now,
                previous_plan=previous_plan,
                expected_previous_version=(
                    None if previous_plan is None else previous_plan.version
                ),
                forced_replan=(
                    self._fault_generation_changed
                    or current_target_ids != previous_target_ids
                    or self._identity_commitment_replan_required
                ),
                regional_planning_hint=regional_hint,
            )
            self._record_d3_regional_hint_outcome(
                self.latest_plan,
                regional_hint,
            )
            self._record_timing("d3_assignment", perf_counter() - started)
            self._regional_plan_rejection_reason = None
        self.latest_bindings = guidance_bindings_from_assignment_plan(
            self.latest_plan,
            resource_vehicle_map={
                resource_id: resource_id
                for resource_id in step_input.interceptors.platform_ids
            },
            now_s=now,
            previous_plan=previous_plan,
            current_plan_id=self.latest_plan.plan_id,
            current_plan_version=self.latest_plan.version,
        )
        plan_identity_changed = bool(
            previous_plan is None
            or self.latest_plan.plan_id != previous_plan.plan_id
            or self.latest_plan.version != previous_plan.version
        )
        self._reconcile_active_bindings_with_identity_commitment(
            self.latest_d2_result
        )
        if (
            plan_identity_changed
            and not self._identity_commitment_binding_hold_target_ids
        ):
            self._identity_commitment_replan_required = False
        if preplanning_snapshot is None:
            adapter_started = perf_counter()
            snapshot = self._d4_snapshot(
                step_input,
                now=now,
                center_health=center_health,
                secondary_failed=secondary_failed,
            )
            self._record_timing(
                "main_d4_adapter",
                perf_counter() - adapter_started,
            )
            started = perf_counter()
            self.latest_d4_decision = self.d4.evaluate(snapshot)
            self._remember_d4_vetted_secondaries(
                self.latest_d4_decision
            )
            self._record_timing(
                "d4_regional_failover",
                perf_counter() - started,
            )
        else:
            snapshot = preplanning_snapshot
        self._run_d4_region_resource_advisor(
            step_input,
            formal_snapshot=snapshot,
            now=now,
        )

    def _d3_regional_hint_from_previous_d4(
        self,
        *,
        previous_plan: Any | None,
        advice_result: Any | None,
        source_snapshot: Any | None,
        source_decision: Any | None,
        now: float,
        fault_generation_changed: bool,
    ) -> Mapping[str, Any] | None:
        """Gate one prior D4 advisory and translate it into a D3-owned DTO.

        The D4 snapshot and formal decision are deliberately frozen with the
        advisory.  D4 first revalidates that exact authority generation; D3
        then independently checks the current plan, resources, commitments,
        reserve and candidate graph before applying the hint.
        """

        if advice_result is None:
            return None
        if fault_generation_changed:
            self._d4_region_hint_bridge_rejection_reason = (
                "fault_generation_changed_before_advisory_consumption"
            )
            return None
        if previous_plan is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_previous_plan_missing"
            )
            return None
        effective_mode = getattr(advice_result, "effective_mode", None)
        effective_mode_value = getattr(effective_mode, "value", effective_mode)
        if str(effective_mode_value).lower() != AdvisorMode.ASSIST.value or not bool(
            getattr(advice_result, "assist_eligible", False)
        ):
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_not_assist_eligible"
            )
            return None
        advisory = getattr(advice_result, "advisory_contract", None)
        if advisory is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_contract_missing"
            )
            return None
        if source_snapshot is None or source_decision is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_source_evidence_missing"
            )
            return None
        if self._d4_region_advisory_gate is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_gate_unavailable"
            )
            return None

        try:
            consumption = self._d4_region_advisory_gate.consume(
                advisory,
                source_snapshot,
                evaluated_at_s=now,
                formal_decision=source_decision,
            )
        except Exception as exc:
            self._d4_region_hint_bridge_rejection_reason = (
                f"regional_advisory_gate_error:{type(exc).__name__}"
            )
            return None
        self.latest_d4_region_consumption = consumption
        if not consumption.consumable:
            first_reason = (
                consumption.rejection_reasons[0]
                if consumption.rejection_reasons
                else "unspecified"
            )
            self._d4_region_hint_bridge_rejection_reason = (
                f"regional_advisory_rejected:{first_reason}"
            )
            return None

        source_plans = tuple(advisory.source_plan_versions)
        expected_source = (str(previous_plan.plan_id), int(previous_plan.version))
        if len(source_plans) != 1 or source_plans[0] != expected_source:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_source_plan_mismatch"
            )
            return None

        advisory_version = self._next_d4_region_hint_version
        self._next_d4_region_hint_version += 1
        constraints = tuple(
            {
                "region_id": region.region_id,
                "owner_id": region.source_version.owner_id,
                "owner_layer": region.source_version.owner_layer.value,
                "owner_epoch": int(region.source_version.epoch),
                "lease_expires_at_s": float(
                    region.source_version.lease_expires_at_s
                ),
                "source_plan_id": expected_source[0],
                "source_plan_version": expected_source[1],
                "resource_quota_delta": int(region.resource_quota_delta),
                "reserve_ratio": float(region.reserve_ratio),
                "hold": bool(region.hold),
                "request_replan": bool(region.request_replan),
            }
            for region in advisory.regions
        )
        transfers = tuple(
            {
                "source_region_id": transfer.source_region_id,
                "target_region_id": transfer.target_region_id,
                "resource_count": int(transfer.resource_count),
                "edge_id": transfer.edge_id,
                "expected_transfer_time_s": float(
                    transfer.expected_transfer_time_s
                ),
            }
            for transfer in advisory.transfers
        )
        return {
            "schema": REGIONAL_PLANNING_HINT_SCHEMA_V1,
            "advisory_id": advisory.advisory_id,
            "advisory_version": advisory_version,
            "created_at_s": float(advisory.created_at_s),
            "expires_at_s": float(advisory.valid_until_s),
            "source_plan_id": expected_source[0],
            "source_plan_version": expected_source[1],
            "projected": bool(advisory.projected),
            "constraints": constraints,
            "transfer_allowances": transfers,
        }

    def _record_d3_regional_hint_outcome(
        self,
        plan: Any,
        regional_hint: Mapping[str, Any] | None,
    ) -> None:
        if regional_hint is None:
            return
        metadata = getattr(plan, "metadata", {})
        successor_available = bool(
            metadata.get(
                "regional_hint_successor_plan_available",
                False,
            )
        )
        successor_matches_plan = bool(
            metadata.get("regional_hint_successor_plan_id")
            == getattr(plan, "plan_id", None)
            and metadata.get("regional_hint_successor_plan_version")
            == getattr(plan, "version", None)
        )
        if (
            bool(metadata.get("regional_hint_applied", False))
            and successor_available
            and successor_matches_plan
        ):
            self._d4_region_hint_bridge_rejection_reason = None
            return
        reason = (
            metadata.get("regional_hint_successor_rejection_reason")
            or metadata.get("regional_hint_fallback_reason")
        )
        self._d4_region_hint_bridge_rejection_reason = (
            "d3_regional_hint_rejected:"
            f"{reason or 'unspecified'}"
        )

    def _run_d4_region_resource_advisor(
        self,
        step_input: RuntimeStepInput,
        *,
        formal_snapshot: RegionalFailoverSnapshot,
        now: float,
    ) -> None:
        """Publish aggregate advice without mutating D4 authority or D3 plans."""

        if self.latest_d4_decision is None:
            return
        if (
            self.d4_region_advisor is None
            and not self.stack_config.capture_learning_artifacts
        ):
            return
        started = perf_counter()
        regional_snapshot = self._d4_region_resource_snapshot(
            step_input,
            formal_snapshot=formal_snapshot,
            now=now,
        )
        self.latest_d4_region_snapshot = regional_snapshot
        recommendation = None
        if self.d4_region_advisor is not None:
            recommendation = self.d4_region_advisor.advise(
                regional_snapshot,
                formal_decision=self.latest_d4_decision,
                unseen_seed_count=self.d4_unseen_seed_count,
            )
            self.latest_d4_region_advice = recommendation
            advisory = getattr(recommendation, "advisory_contract", None)
            candidate = getattr(recommendation, "recommendation", None)
            if advisory is not None and candidate is not None:
                self._d4_advisory_sources[str(advisory.advisory_id)] = (
                    _D4RegionAdvisorySource(
                        snapshot=regional_snapshot,
                        recommendation=candidate,
                        formal_snapshot=formal_snapshot,
                        formal_decision=self.latest_d4_decision,
                    )
                )
        if self.stack_config.capture_learning_artifacts:
            self._d4_learning_frames.append(
                D4RegionLearningFrame(
                    frame_index=len(self._d4_learning_frames),
                    timestamp_s=now,
                    snapshot=regional_snapshot,
                    recommendation=recommendation,
                    formal_snapshot=formal_snapshot,
                    formal_decision=self.latest_d4_decision,
                )
            )
        self._record_timing(
            "d4_region_resource_advisor",
            perf_counter() - started,
        )

    def learning_artifacts(self) -> IntegratedLearningArtifacts:
        """Return detached truth-free frames; evaluator labels remain outside the stack."""

        return IntegratedLearningArtifacts(
            d3_planning_frames=tuple(self._d3_learning_frames),
            d4_region_frames=tuple(self._d4_learning_frames),
            d5_graph_frames=tuple(self._d5_learning_frames),
            d5_active_vision_frames=tuple(
                self._d5_active_vision_learning_frames
            ),
        )

    def record_assignment_plan_runtime_ack(
        self,
        *,
        acknowledgement: Mapping[str, Any],
        acknowledgement_envelope: Any,
        source_publication_envelopes: Iterable[Any],
        timestamp_s: float,
        partition_generation: int,
    ) -> tuple[RuntimeCommunicationIntent, ...]:
        """Bind a real assignment ACK to D4 evidence and route the owner ACK.

        This callback is invoked only after main has published the D3 plan,
        D7 guidance batch, and assignment ACK. Missing source envelopes or an
        unavailable learned advisory remain audit blockers and do not affect
        the active plan.
        """

        envelopes = tuple(source_publication_envelopes)
        self._cache_d4_runtime_source_envelopes(envelopes)
        consumption_envelope = next(
            (
                item
                for item in envelopes
                if getattr(item, "topic", "")
                == "modules.d4.region_resource_consumption"
            ),
            None,
        )
        if consumption_envelope is None:
            return ()
        d3_envelope = next(
            (
                item
                for item in envelopes
                if getattr(item, "topic", "") == "modules.d3.assignment_plan"
            ),
            None,
        )
        d7_envelope = next(
            (
                item
                for item in envelopes
                if getattr(item, "topic", "")
                == "modules.d7.guidance_commands"
            ),
            None,
        )
        if d3_envelope is None or d7_envelope is None:
            self._d4_a2_bridge_blocker_counts[
                "runtime_ack_source_envelope_missing"
            ] += 1
            return ()

        try:
            consumption_payload = dict(consumption_envelope.payload)
            successor_published = not (
                consumption_payload.get("bridge_rejection_reason") is not None
                or consumption_payload.get("d3_hint_applied") is not True
                or consumption_payload.get(
                    "d3_successor_plan_available"
                )
                is not True
                or consumption_payload.get("d3_successor_state")
                != "successor_published"
            )
            nested_advisory = dict(consumption_payload["advisory"])
            advisory_id = str(nested_advisory["advisory_id"])
            source_versions = tuple(
                (str(item[0]), int(item[1]))
                for item in nested_advisory["source_plan_versions"]
            )
            if len(source_versions) != 1:
                raise ValueError("A2 runtime bridge requires one source plan")
            source = self._d4_advisory_sources[advisory_id]
            plan_payload = dict(d3_envelope.payload)
            plan_metadata = dict(plan_payload.get("metadata", {}))
            advisory_version_value = plan_metadata.get(
                "regional_hint_advisory_version"
            )
            if not isinstance(advisory_version_value, Integral):
                self._d4_a2_bridge_blocker_counts[
                    "current_plan_advisory_version_missing"
                ] += 1
                return ()
            advisory_version = int(advisory_version_value)
            context = self._d4_safe_adoption_context(
                source,
                advisory_version=advisory_version,
                partition_generation=int(partition_generation),
                consumption_timestamp_s=float(
                    consumption_payload["evaluated_at_s"]
                ),
            )
            preparation = self._d4_safe_adoption_assembler.prepare(
                snapshot=source.snapshot,
                candidate=source.recommendation,
                context=context,
                formal_decision=source.formal_decision,
            )
            if (
                not preparation.available
                or preparation.applied_recommendation is None
            ):
                partial = self._d4_safe_adoption_assembler.assemble(
                    preparation=preparation,
                    context=context,
                    evaluated_at_s=float(timestamp_s),
                )
                self._remember_d4_a2_evidence(partial)
                self._d4_a2_bridge_blocker_counts[
                    "candidate_preparation_unavailable"
                ] += 1
                return ()
            if not successor_published:
                partial = self._d4_safe_adoption_assembler.assemble(
                    preparation=preparation,
                    context=context,
                    evaluated_at_s=float(timestamp_s),
                )
                self._remember_d4_a2_evidence(partial)
                self._d4_a2_bridge_blocker_counts[
                    "consumption_not_applied_to_current_plan"
                ] += 1
                return ()
            if (
                consumption_payload.get("d3_successor_plan_id")
                != plan_payload.get("plan_id")
                or consumption_payload.get(
                    "d3_successor_plan_version"
                )
                != plan_payload.get("plan_version")
            ):
                self._d4_a2_bridge_blocker_counts[
                    "consumption_successor_identity_mismatch"
                ] += 1
                return ()
            advisory_envelope = self._d4_advice_source_envelopes[advisory_id]
            source_plan_envelope = self._d4_plan_source_envelopes[
                source_versions[0]
            ]
            runtime_ack = self._d4_runtime_ack_parser.consume(
                advisory_source=advisory_envelope,
                consumption_source=consumption_envelope,
                assignment_plan_ack_source=acknowledgement_envelope,
                d3_plan_source_envelope=d3_envelope,
                d7_guidance_source_envelope=d7_envelope,
                advisory_source_plan_envelope=source_plan_envelope,
            )
            plan_reference = self._d4_plan_reference_from_runtime_ack(
                runtime_ack=runtime_ack,
                d3_envelope=d3_envelope,
                preparation=preparation,
            )
            partial = self._d4_safe_adoption_assembler.assemble(
                preparation=preparation,
                context=context,
                evaluated_at_s=float(timestamp_s),
                d3_successor_plan=plan_reference,
                runtime_ack=runtime_ack,
            )
            self._remember_d4_a2_evidence(partial)
            if (
                not runtime_ack.runtime_advisory_applied_ack_available
                or runtime_ack.adoption_kind
                != "new_execution_plan_applied"
                or plan_reference.plan_id
                == plan_reference.previous_plan_id
                or plan_reference.plan_version
                <= plan_reference.previous_plan_version
            ):
                self._d4_a2_bridge_blocker_counts[
                    "owner_ack_not_eligible"
                ] += 1
                return ()
            source_state_sha = self._latest_runtime_state_payload_sha256
            if source_state_sha is None:
                self._d4_a2_bridge_blocker_counts[
                    "runtime_state_snapshot_missing"
                ] += 1
                return ()
            expected_owner_ack = build_region_resource_owner_plan_ack(
                message_id=(
                    "d4-owner-ack:"
                    f"{plan_reference.plan_id}:v{plan_reference.plan_version}:"
                    f"a{advisory_version}"
                ),
                applied_recommendation=preparation.applied_recommendation,
                d3_successor_plan=plan_reference,
                runtime_ack=runtime_ack,
                context=context,
                acknowledged_at_s=float(timestamp_s),
                accepted=True,
            )
            pending = _D4A2PendingAdoption(
                context=context,
                preparation=preparation,
                plan_reference=plan_reference,
                runtime_ack=runtime_ack,
                expected_owner_ack=expected_owner_ack,
                source_state_payload_sha256=source_state_sha,
                non_hold_control_applied_count=max(
                    0,
                    int(acknowledgement["control_applied_binding_count"])
                    - int(acknowledgement["held_binding_count"]),
                ),
                final_evidence=partial,
            )
            self._d4_a2_pending_by_plan[
                (plan_reference.plan_id, plan_reference.plan_version)
            ] = pending
            return (
                self._d4_intent(
                    source=expected_owner_ack.owner_node_id,
                    destination=context.runtime_node_id,
                    topic=_D4_OWNER_ACK_TOPIC,
                    payload=expected_owner_ack.to_transport_payload(),
                    random_stream=_D4_STRICT_EVIDENCE_RANDOM_STREAM,
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            self._d4_a2_bridge_blocker_counts[
                f"runtime_ack_bridge_{type(exc).__name__.lower()}"
            ] += 1
            return ()

    def _cache_d4_runtime_source_envelopes(
        self,
        envelopes: Iterable[Any],
    ) -> None:
        for envelope in envelopes:
            topic = str(getattr(envelope, "topic", ""))
            payload = getattr(envelope, "payload", None)
            if not isinstance(payload, Mapping):
                continue
            if topic == "modules.d3.assignment_plan":
                plan_id = str(payload.get("plan_id", "")).strip()
                plan_version = payload.get("plan_version")
                if plan_id and isinstance(plan_version, Integral):
                    key = (plan_id, int(plan_version))
                    self._d4_plan_source_envelopes[key] = envelope
                    self._d4_plan_transport_references[key] = (
                        canonical_runtime_payload_sha256(payload),
                        int(getattr(envelope, "sequence")),
                    )
            elif topic == "modules.d4.region_resource_advice":
                advisory_value = payload.get("advisory_contract")
                if isinstance(advisory_value, Mapping):
                    advisory_id = str(
                        advisory_value.get("advisory_id", "")
                    ).strip()
                    if advisory_id:
                        self._d4_advice_source_envelopes[
                            advisory_id
                        ] = envelope

    def _d4_safe_adoption_context(
        self,
        source: _D4RegionAdvisorySource,
        *,
        advisory_version: int,
        partition_generation: int,
        consumption_timestamp_s: float,
    ) -> RegionResourceSafeAdoptionContext:
        center_health = source.formal_snapshot.center_health
        secondary_regions = tuple(
            sorted(
                item.region_id
                for item in source.snapshot.regions
                if item.current_owner_layer
                is RegionalAuthorityLayer.SECONDARY
            )
        )
        active_regions = ()
        if center_health not in {C2Health.NORMAL, C2Health.FAILED}:
            active_regions = tuple(
                sorted(
                    item.region_id
                    for item in source.snapshot.regions
                    if item.current_owner_layer
                    is not RegionalAuthorityLayer.CENTER
                )
            )
        return RegionResourceSafeAdoptionContext(
            consumption_timestamp_s=consumption_timestamp_s,
            center_health=center_health,
            runtime_node_id="MAIN-RUNTIME",
            advisory_version=advisory_version,
            partition_generation=partition_generation,
            secondary_available_region_ids=secondary_regions,
            partitioned_region_ids=tuple(
                source.formal_snapshot.partitioned_region_ids
            ),
            active_degradation_region_ids=active_regions,
            active_degradation_evidence_sha256=(
                canonical_runtime_payload_sha256(
                    source.formal_decision.to_dict()
                )
                if active_regions
                else None
            ),
        )

    def _d4_plan_reference_from_runtime_ack(
        self,
        *,
        runtime_ack: Any,
        d3_envelope: Any,
        preparation: Any,
    ) -> RegionResourceD3PlanReference:
        payload = dict(d3_envelope.payload)
        metadata = dict(payload.get("metadata", {}))
        applied = preparation.applied_recommendation
        if applied is None:
            raise ValueError("D4 plan reference requires a prepared advisory")
        advisory_payload_sha = applied.advisory_payload_sha256
        lease = applied.lease_expires_at_s
        created_at = float(payload["created_at"])
        valid_until = float(lease)
        if valid_until <= created_at:
            raise ValueError("D4 successor plan has no positive authority lease")
        owner_layer = applied.owner_layer.value
        owner_node_id = applied.owner_node_id
        if owner_layer is None or owner_node_id is None:
            raise ValueError("D4 successor plan owner is unavailable")
        return RegionResourceD3PlanReference(
            plan_id=str(payload["plan_id"]),
            plan_version=int(payload["plan_version"]),
            previous_plan_id=str(applied.source_plan_id),
            previous_plan_version=int(applied.source_plan_version),
            owner_node_id=str(owner_node_id),
            owner_layer=str(owner_layer),
            epoch=int(applied.epoch),
            created_at_s=created_at,
            valid_until_s=valid_until,
            source_advisory_id=str(applied.advisory.advisory_id),
            source_advisory_version=int(applied.advisory_version),
            source_advisory_payload_sha256=advisory_payload_sha,
            plan_payload_sha256=canonical_runtime_payload_sha256(payload),
            plan_bus_sequence=int(getattr(d3_envelope, "sequence")),
            accepted_by_main_runtime=True,
            regional_hint_applied=bool(
                metadata.get("regional_hint_applied", False)
            ),
            stale_version_rejected=True,
            coalition_requirements=self._d4_coalition_requirements(),
        )

    def _d4_coalition_requirements(
        self,
    ) -> tuple[RegionResourceCoalitionRequirement, ...]:
        plan = self.latest_plan
        if plan is None:
            return ()
        requirements: list[RegionResourceCoalitionRequirement] = []
        for coalition in tuple(getattr(plan, "coalitions", ())):
            members = tuple(
                sorted(
                    assignment.resource_id
                    for assignment in plan.assignments
                    if assignment.target_id == coalition.target_id
                    and assignment.coalition_id == coalition.coalition_id
                )
            )
            required_count = max(
                (
                    int(assignment.required_resource_count)
                    for assignment in plan.assignments
                    if assignment.target_id == coalition.target_id
                    and assignment.coalition_id == coalition.coalition_id
                ),
                default=1,
            )
            if required_count <= 1:
                continue
            if len(members) != required_count:
                raise ValueError(
                    "incomplete coalition cannot enter A2 adoption evidence"
                )
            requirements.append(
                RegionResourceCoalitionRequirement(
                    global_track_id=str(coalition.target_id),
                    coalition_id=str(coalition.coalition_id),
                    coalition_version=int(coalition.version),
                    required_member_ids=members,
                )
            )
        return tuple(requirements)

    def _remember_d4_a2_evidence(self, evidence: Any) -> None:
        applied = getattr(evidence, "applied_recommendation", None)
        key = (
            str(applied.application_id)
            if applied is not None
            else str(getattr(evidence, "input_sha256", "unavailable"))
        )
        self._d4_a2_evidence_by_application[key] = evidence

    def _runtime_state_payload_sha256(
        self,
        step_input: RuntimeStepInput,
    ) -> str:
        return canonical_runtime_payload_sha256(
            {
                "interceptors": {
                    "platform_ids": list(step_input.interceptors.platform_ids),
                    "state_ned": step_input.interceptors.state_ned.tolist(),
                    "covariance": step_input.interceptors.covariance.tolist(),
                    "active": step_input.interceptors.active.tolist(),
                },
                "recon": {
                    "platform_ids": list(step_input.recon.platform_ids),
                    "state_ned": step_input.recon.state_ned.tolist(),
                    "covariance": step_input.recon.covariance.tolist(),
                    "active": step_input.recon.active.tolist(),
                },
            }
        )

    def _advance_d4_a2_physical_windows(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
    ) -> None:
        current_state_sha = self._latest_runtime_state_payload_sha256
        if current_state_sha is None:
            return
        for plan_key, pending in tuple(
            self._d4_a2_pending_by_plan.items()
        ):
            if pending.final_evidence is not None and bool(
                getattr(
                    pending.final_evidence,
                    "safe_adoption_available",
                    False,
                )
            ):
                continue
            plan = pending.plan_reference
            if now >= plan.valid_until_s - _EPS:
                self._d4_a2_bridge_blocker_counts[
                    "physical_window_lease_expired"
                ] += 1
                continue
            current_plan = self.latest_plan
            if (
                current_plan is None
                or str(current_plan.plan_id) != plan.plan_id
                or int(current_plan.version) != plan.plan_version
            ):
                self._d4_a2_bridge_blocker_counts[
                    "physical_window_plan_superseded"
                ] += 1
                continue
            pending.non_hold_control_applied_count = max(
                pending.non_hold_control_applied_count,
                self._d4_current_plan_non_hold_control_count(
                    plan_id=plan.plan_id,
                    plan_version=plan.plan_version,
                ),
            )
            if pending.owner_ack_delivery is None:
                continue
            commits = self._d4_coalition_commits_for_pending(
                pending,
                now=now,
            )
            if plan.coalition_requirements and not commits:
                partial = self._d4_safe_adoption_assembler.assemble(
                    preparation=pending.preparation,
                    context=pending.context,
                    evaluated_at_s=now,
                    d3_successor_plan=plan,
                    runtime_ack=pending.runtime_ack,
                    owner_ack_delivery=pending.owner_ack_delivery,
                )
                pending.final_evidence = partial
                self._remember_d4_a2_evidence(partial)
                continue
            pending.coalition_commits = commits
            if pending.physical_window_start_s is None:
                pending.physical_window_start_s = now
                pending.physical_window_source_payload_sha256 = (
                    current_state_sha
                )
                partial = self._d4_safe_adoption_assembler.assemble(
                    preparation=pending.preparation,
                    context=pending.context,
                    evaluated_at_s=now,
                    d3_successor_plan=plan,
                    runtime_ack=pending.runtime_ack,
                    owner_ack_delivery=pending.owner_ack_delivery,
                    coalition_commits=commits,
                )
                pending.final_evidence = partial
                self._remember_d4_a2_evidence(partial)
                continue
            if now <= pending.physical_window_start_s + _EPS:
                continue
            source_sha = pending.physical_window_source_payload_sha256
            if (
                source_sha is None
                or source_sha == current_state_sha
                or pending.non_hold_control_applied_count <= 0
            ):
                continue
            hard_violations = self._d4_physical_hard_constraint_violations(
                step_input
            )
            if hard_violations:
                self._d4_a2_bridge_blocker_counts[
                    "physical_window_hard_constraint_violation"
                ] += hard_violations
                continue
            window = RegionResourcePhysicalWindowEvidence(
                window_id=(
                    f"d4-a2-window:{plan.plan_id}:v{plan.plan_version}:"
                    f"{pending.physical_window_start_s:.6f}"
                ),
                available=True,
                window_start_s=pending.physical_window_start_s,
                window_end_s=now,
                advisory_id=str(pending.runtime_ack.advisory_id),
                advisory_version=int(
                    pending.runtime_ack.advisory_version
                ),
                advisory_payload_sha256=str(
                    pending.runtime_ack.advisory_payload_sha256
                ),
                applied_plan_id=plan.plan_id,
                applied_plan_version=plan.plan_version,
                runtime_ack_sha256=_d4_safe_adoption_sha256(
                    pending.runtime_ack.to_dict()
                ),
                owner_ack_receipt_id=(
                    pending.owner_ack_delivery.receipt.receipt_id
                ),
                coalition_commit_sha256=tuple(
                    sorted(item.immutable_digest for item in commits)
                ),
                source_state_payload_sha256=source_sha,
                post_state_payload_sha256=current_state_sha,
                physical_execution_observed=True,
                hard_constraint_violation_count=0,
            )
            evidence = self._d4_safe_adoption_assembler.assemble(
                preparation=pending.preparation,
                context=pending.context,
                evaluated_at_s=now,
                d3_successor_plan=plan,
                runtime_ack=pending.runtime_ack,
                owner_ack_delivery=pending.owner_ack_delivery,
                coalition_commits=commits,
                physical_window=window,
            )
            pending.final_evidence = evidence
            self._remember_d4_a2_evidence(evidence)
            if bool(getattr(evidence, "safe_adoption_available", False)):
                self._d4_a2_physical_window_count += 1

    def _d4_current_plan_non_hold_control_count(
        self,
        *,
        plan_id: str,
        plan_version: int,
    ) -> int:
        """Count executable D7 bindings from the latest applied plan batch."""

        current_plan = self.latest_plan
        guidance_batch = self.latest_guidance_batch
        if (
            current_plan is None
            or guidance_batch is None
            or str(current_plan.plan_id) != str(plan_id)
            or int(current_plan.version) != int(plan_version)
        ):
            return 0
        active_bindings = {
            (str(assignment.resource_id), str(assignment.target_id))
            for assignment in current_plan.assignments
        }
        applied_bindings = {
            (
                str(command.resource_id),
                str(command.assigned_global_track_id),
            )
            for command in guidance_batch.pair_commands
            if (
                str(command.plan_id) == str(plan_id)
                and int(command.plan_version) == int(plan_version)
                and str(getattr(command.mode, "value", command.mode))
                != "hold"
                and (
                    str(command.resource_id),
                    str(command.assigned_global_track_id),
                )
                in active_bindings
            )
        }
        return len(applied_bindings)

    def _d4_coalition_commits_for_pending(
        self,
        pending: _D4A2PendingAdoption,
        *,
        now: float,
    ) -> tuple[RegionResourceCoalitionCommitEvidence, ...]:
        requirements = pending.plan_reference.coalition_requirements
        if not requirements:
            return ()
        summaries = tuple(
            summary
            for region in (
                ()
                if self.latest_d4_decision is None
                else self.latest_d4_decision.region_decisions
            )
            for summary in region.coalition_commits
        )
        output: list[RegionResourceCoalitionCommitEvidence] = []
        for requirement in requirements:
            deliveries = tuple(
                pending.coalition_ack_deliveries.get(
                    (
                        requirement.global_track_id,
                        requirement.coalition_id,
                        requirement.coalition_version,
                    ),
                    {},
                ).values()
            )
            by_member = {
                item.member_ack.resource_id: item for item in deliveries
            }
            if set(by_member) != set(requirement.required_member_ids):
                return ()
            summary = next(
                (
                    item
                    for item in summaries
                    if item.global_track_id
                    == requirement.global_track_id
                    and tuple(item.required_member_ids)
                    == requirement.required_member_ids
                    and item.atomic_committed
                    and item.execution_authorized
                    and item.state == "executing"
                ),
                None,
            )
            if summary is None:
                return ()
            committed_at = max(
                item.receipt.arrival_timestamp_s
                for item in by_member.values()
            )
            state = CoalitionCommitState(
                global_track_id=requirement.global_track_id,
                coalition_id=requirement.coalition_id,
                coalition_version=requirement.coalition_version,
                plan_id=pending.plan_reference.plan_id,
                plan_version=pending.plan_reference.plan_version,
                epoch=pending.plan_reference.epoch,
                coordinator_id=pending.plan_reference.owner_node_id,
                coordinator_role=pending.plan_reference.owner_layer.value,
                required_member_ids=requirement.required_member_ids,
                acked_member_ids=requirement.required_member_ids,
                state="executing",
                lease_expires_at=pending.plan_reference.valid_until_s,
                proposed_at=pending.plan_reference.created_at_s,
                updated_at=now,
                committed_at=committed_at,
                executing_at=now,
                reason=str(summary.reason),
            )
            output.append(
                RegionResourceCoalitionCommitEvidence(
                    state=state,
                    member_ack_deliveries=tuple(
                        by_member[member_id]
                        for member_id in requirement.required_member_ids
                    ),
                )
            )
        return tuple(output)

    def _d4_physical_hard_constraint_violations(
        self,
        step_input: RuntimeStepInput,
    ) -> int:
        config = self._require_ready()
        violations = 0
        speed_limit = max(20.0, config.interceptor_speed_mps * 1.5)
        speeds = np.linalg.norm(
            step_input.interceptors.state_ned[:, 3:6],
            axis=1,
        )
        violations += int(np.count_nonzero(speeds > speed_limit + 1.0e-6))
        if self.latest_guidance_batch is not None:
            for command in self.latest_guidance_batch.pair_commands:
                acceleration = np.asarray(
                    command.acceleration_ned_mps2,
                    dtype=float,
                )
                if (
                    not np.all(np.isfinite(acceleration))
                    or np.linalg.norm(acceleration)
                    > self.d7.config.max_accel_mps2 + 1.0e-6
                ):
                    violations += 1
        return violations

    def record_active_vision_runtime_feedback(
        self,
        *,
        timestamp_s: float,
        camera_states: Iterable[CameraRuntimeState],
        acknowledgements: Iterable[Mapping[str, Any]],
        acknowledgement_envelopes: Iterable[Any] = (),
        source_publication_envelopes: Iterable[Any] = (),
        episode_id: str | None = None,
        pairing_context_sha256: str | None = None,
        source_git_commit: str | None = None,
    ) -> None:
        """Bind camera ACK envelopes and post-command state to A3 evidence.

        D5 decides from the pre-command snapshot. Main applies the bounded camera
        command immediately afterwards and publishes the ACK before this callback.
        A valid A3 trace therefore requires the ACK bus sequence, the matching D5
        publication, frozen model provenance, and the resulting runtime state.
        """

        timestamp = float(timestamp_s)
        states = tuple(camera_states)
        acknowledgement_items = tuple(acknowledgements)
        self._record_active_vision_learning_feedback(
            timestamp_s=timestamp,
            camera_states=states,
            acknowledgements=acknowledgement_items,
        )
        if not acknowledgement_items:
            return

        state_by_camera = {state.camera_id: state for state in states}
        ack_envelope_by_camera: dict[str, Any] = {}
        for envelope in tuple(acknowledgement_envelopes):
            if str(getattr(envelope, "topic", "")) != "runtime.camera_command_ack":
                self._d5_a3_bridge_blocker_counts[
                    "camera_ack_envelope_topic_invalid"
                ] += 1
                continue
            payload = getattr(envelope, "payload", None)
            if not isinstance(payload, Mapping):
                self._d5_a3_bridge_blocker_counts[
                    "camera_ack_envelope_payload_invalid"
                ] += 1
                continue
            camera_id = str(payload.get("camera_id", "")).strip()
            if not camera_id or camera_id in ack_envelope_by_camera:
                self._d5_a3_bridge_blocker_counts[
                    "camera_ack_envelope_membership_invalid"
                ] += 1
                continue
            ack_envelope_by_camera[camera_id] = envelope

        active_vision_envelope = next(
            (
                envelope
                for envelope in tuple(source_publication_envelopes)
                if str(getattr(envelope, "topic", ""))
                == "modules.d5.active_vision"
            ),
            None,
        )
        if active_vision_envelope is None:
            self._d5_a3_bridge_blocker_counts[
                "active_vision_publication_envelope_missing"
            ] += len(acknowledgement_items)

        config = self._require_ready()
        scale = max(config.target_count, config.resource_count)
        for acknowledgement in acknowledgement_items:
            camera_id = str(acknowledgement.get("camera_id", "")).strip()
            context = self._d5_a3_command_context_by_camera.get(camera_id)
            runtime_state = state_by_camera.get(camera_id)
            ack_envelope = ack_envelope_by_camera.get(camera_id)
            if context is None:
                self._d5_a3_bridge_blocker_counts[
                    "active_vision_command_context_missing"
                ] += 1
                continue
            if (
                abs(context.timestamp_s - timestamp) > _EPS
                or runtime_state is None
                or ack_envelope is None
                or active_vision_envelope is None
            ):
                self._d5_a3_bridge_blocker_counts[
                    "active_vision_runtime_chain_incomplete"
                ] += 1
                continue
            if (
                pairing_context_sha256 is None
                or not _is_sha256_text(pairing_context_sha256)
            ):
                self._d5_a3_bridge_blocker_counts[
                    "active_vision_pairing_context_missing"
                ] += 1
                continue

            resolved_episode_id = str(
                episode_id
                or f"{config.scenario_name}-s{config.seed}"
            ).strip()
            source_event_sha256 = canonical_runtime_payload_sha256(
                {
                    "episode_id": resolved_episode_id,
                    "event_log_stream": "modules.d5.active_vision",
                    "schema_version": str(
                        getattr(active_vision_envelope, "schema_version", "")
                    ),
                }
            )
            comparison_key = (
                f"{config.scenario_name}|scale={scale}|seed={config.seed}|"
                f"window={context.window_index}|camera={camera_id}"
            )
            sample_key = (
                f"{resolved_episode_id}:active-vision:"
                f"{context.window_index:06d}:{camera_id}"
            )
            requested_mode = ActiveVisionRuntimeMode(
                context.decision.requested_mode
            )
            effective_mode = ActiveVisionRuntimeMode(
                context.decision.effective_mode
            )
            if (
                requested_mode is ActiveVisionRuntimeMode.DISABLED
                and effective_mode is ActiveVisionRuntimeMode.DISABLED
            ):
                try:
                    trace = assemble_active_vision_a3_rule_arm_trace(
                        comparison_key=comparison_key,
                        scenario_id=config.scenario_name,
                        scale=scale,
                        seed=config.seed,
                        window_index=context.window_index,
                        sample_key=sample_key,
                        pairing_context_sha256=str(
                            pairing_context_sha256
                        ),
                        source_event_log_sha256=source_event_sha256,
                        snapshot=context.snapshot,
                        rule_decision=context.decision,
                        issued_command=context.command,
                        runtime_ack_payload=acknowledgement,
                        post_command_camera_state=runtime_state,
                        runtime_ack_evidence_kind=(
                            RUNTIME_OBSERVED_EVIDENCE_KIND
                        ),
                        camera_feedback_evidence_kind=(
                            RUNTIME_OBSERVED_EVIDENCE_KIND
                        ),
                        camera_state_source_sequence=int(
                            getattr(ack_envelope, "sequence")
                        ),
                        online_truth_use_count=0,
                        global_track_id_rewrite_count=0,
                    )
                except (TypeError, ValueError) as exc:
                    self._d5_a3_bridge_blocker_counts[
                        f"active_vision_r0_trace_{type(exc).__name__.lower()}"
                    ] += 1
                    continue
                self._d5_a3_r0_runtime_ack_count += 1
                self._d5_a3_r0_pending_by_camera.setdefault(
                    camera_id,
                    [],
                ).append(
                    _D5A3PendingObservationWindow(
                        trace=trace,
                        observation_frames=[],
                    )
                )
                continue

            provenance = self._d5_a3_runtime_provenance(
                source_git_commit=source_git_commit,
            )
            if provenance is None:
                continue
            (
                model_fingerprint,
                manifest_sha256,
                weights_sha256,
                implementation_sha256,
                commit,
            ) = provenance
            if context.decision.model_fingerprint != model_fingerprint:
                self._d5_a3_bridge_blocker_counts[
                    "active_vision_decision_fingerprint_mismatch"
                ] += 1
                continue
            try:
                trace = assemble_active_vision_a3_adoption_trace(
                    comparison_key=comparison_key,
                    scenario_id=config.scenario_name,
                    scale=scale,
                    seed=config.seed,
                    window_index=context.window_index,
                    sample_key=sample_key,
                    pairing_context_sha256=str(pairing_context_sha256),
                    source_event_log_sha256=source_event_sha256,
                    snapshot=context.snapshot,
                    decision=context.decision,
                    issued_command=context.command,
                    runtime_ack_payload=acknowledgement,
                    post_command_camera_state=runtime_state,
                    policy_evaluated=True,
                    policy_evaluated_timestamp=context.timestamp_s,
                    model_fingerprint=model_fingerprint,
                    bundle_manifest_sha256=manifest_sha256,
                    bundle_weights_sha256=weights_sha256,
                    implementation_sha256=implementation_sha256,
                    source_git_commit=commit,
                    runtime_ack_evidence_kind=(
                        RUNTIME_OBSERVED_EVIDENCE_KIND
                    ),
                    camera_feedback_evidence_kind=(
                        RUNTIME_OBSERVED_EVIDENCE_KIND
                    ),
                    camera_state_source_sequence=int(
                        getattr(ack_envelope, "sequence")
                    ),
                    online_truth_use_count=0,
                    global_track_id_rewrite_count=0,
                )
            except (TypeError, ValueError) as exc:
                self._d5_a3_bridge_blocker_counts[
                    f"active_vision_trace_{type(exc).__name__.lower()}"
                ] += 1
                continue
            self._d5_a3_runtime_ack_count += 1
            initial = assemble_active_vision_a3_evidence(
                trace,
                candidate_window=None,
                same_key_r0_window=None,
            )
            self._d5_a3_evidence_by_comparison_key[
                trace.comparison_key
            ] = initial
            if trace.model_action_adopted:
                self._d5_a3_pending_by_camera.setdefault(
                    camera_id,
                    [],
                ).append(
                    _D5A3PendingObservationWindow(
                    trace=trace,
                    observation_frames=[],
                )
                )

    def _record_active_vision_learning_feedback(
        self,
        *,
        timestamp_s: float,
        camera_states: Iterable[CameraRuntimeState],
        acknowledgements: Iterable[Mapping[str, Any]],
    ) -> None:
        if not self.stack_config.capture_learning_artifacts:
            return
        if not self._d5_active_vision_learning_frames:
            raise RuntimeError("active-vision feedback has no captured decision frame")
        frame = self._d5_active_vision_learning_frames[-1]
        timestamp = float(timestamp_s)
        if abs(float(frame.timestamp_s) - timestamp) > _EPS:
            raise ValueError("active-vision feedback timestamp does not match latest frame")
        state_by_camera = {state.camera_id: state for state in camera_states}
        ack_by_camera: dict[str, Mapping[str, Any]] = {}
        for acknowledgement in acknowledgements:
            camera_id = str(acknowledgement.get("camera_id", ""))
            if not camera_id or camera_id in ack_by_camera:
                raise ValueError("active-vision feedback has missing or duplicate camera ACK")
            ack_by_camera[camera_id] = acknowledgement

        expected_camera_ids = {
            decision.effective_action.camera_id for decision in frame.decisions
        }
        if set(ack_by_camera) != expected_camera_ids:
            raise ValueError("active-vision feedback ACK set does not match decisions")

        feedback: list[ActiveVisionCameraFeedbackV1] = []
        for prior in frame.camera_feedback:
            camera_id = prior.camera_state.camera_id
            runtime_state = state_by_camera.get(camera_id)
            acknowledgement = ack_by_camera.get(camera_id)
            if runtime_state is None or acknowledgement is None:
                raise ValueError("active-vision feedback is missing a runtime camera state")
            if acknowledgement.get("status") == "applied" and int(
                runtime_state.last_communication_version
            ) != int(acknowledgement["command_version"]):
                raise ValueError("applied camera ACK disagrees with runtime camera state")
            accepted_version = int(runtime_state.last_communication_version)
            feedback.append(
                ActiveVisionCameraFeedbackV1(
                    camera_state=self._active_vision_camera_state(runtime_state),
                    last_accepted_command_version=(
                        None if accepted_version == 0 else accepted_version
                    ),
                )
            )

        self._d5_active_vision_learning_frames[-1] = replace(
            frame,
            camera_feedback=tuple(feedback),
        )

    def _d5_a3_runtime_provenance(
        self,
        *,
        source_git_commit: str | None,
    ) -> tuple[str, str, str, str, str] | None:
        diagnostics = self.learning_runtime_diagnostics.get(
            "d5_active_vision",
            {},
        )
        policy = self.d5_active_vision_policy
        manifest = getattr(policy, "manifest", None)
        code_provenance = (
            manifest.get("code_provenance")
            if isinstance(manifest, Mapping)
            else None
        )
        values = {
            "model_fingerprint": diagnostics.get("model_fingerprint"),
            "bundle_manifest_sha256": diagnostics.get(
                "bundle_manifest_sha256"
            ),
            "bundle_weights_sha256": diagnostics.get(
                "bundle_weights_sha256"
            ),
            "implementation_sha256": (
                code_provenance.get("implementation_sha256")
                if isinstance(code_provenance, Mapping)
                else None
            ),
            "source_git_commit": source_git_commit,
        }
        if (
            diagnostics.get("bundle_loaded") is not True
            or diagnostics.get("assist_admitted") is not True
            or diagnostics.get("effective_mode") != "assist"
            or not bool(getattr(policy, "available", False))
            or not bool(getattr(policy, "assist_admitted", False))
        ):
            self._d5_a3_bridge_blocker_counts[
                "active_vision_assist_provenance_unavailable"
            ] += 1
            return None
        fingerprint = str(values["model_fingerprint"] or "").strip()
        if (
            fingerprint != str(getattr(policy, "model_fingerprint", ""))
            or str(values["bundle_manifest_sha256"])
            != str(getattr(policy, "bundle_manifest_sha256", ""))
            or str(values["bundle_weights_sha256"])
            != str(getattr(policy, "bundle_weights_sha256", ""))
        ):
            self._d5_a3_bridge_blocker_counts[
                "active_vision_bundle_provenance_mismatch"
            ] += 1
            return None
        digests = (
            str(values["bundle_manifest_sha256"] or ""),
            str(values["bundle_weights_sha256"] or ""),
            str(values["implementation_sha256"] or ""),
        )
        commit = str(values["source_git_commit"] or "").strip().lower()
        if (
            not fingerprint
            or any(not _is_sha256_text(value) for value in digests)
            or not _is_git_commit_text(commit)
        ):
            self._d5_a3_bridge_blocker_counts[
                "active_vision_frozen_provenance_incomplete"
            ] += 1
            return None
        return (fingerprint, *digests, commit)

    def record_active_vision_observation_publication(
        self,
        *,
        publication_envelope: Any,
    ) -> None:
        """Attach one published anonymous D5 frame to prior A3 commands."""

        if str(getattr(publication_envelope, "topic", "")) != (
            "modules.d5.terminal_association"
        ):
            raise ValueError("active-vision observation source topic is invalid")
        if (
            not self._d5_a3_pending_by_camera
            and not self._d5_a3_r0_pending_by_camera
        ):
            return
        result = self.latest_d5_result
        if result is None:
            self._d5_a3_bridge_blocker_counts[
                "active_vision_d5_result_missing"
            ] += 1
            return
        payload = getattr(publication_envelope, "payload", None)
        if not isinstance(payload, Mapping):
            self._d5_a3_bridge_blocker_counts[
                "active_vision_d5_publication_invalid"
            ] += 1
            return
        published_keys = {
            str(item.get("tracklet_key", ""))
            for item in payload.get("local_tracklets", ())
            if isinstance(item, Mapping)
        }
        actual_keys = {item.tracklet_key for item in result.tracklets}
        if published_keys != actual_keys:
            self._d5_a3_bridge_blocker_counts[
                "active_vision_tracklet_publication_mismatch"
            ] += 1
            return

        center_track_ids = tuple(
            track.global_track_id for track in self.latest_d2_tracks
        )
        bindings = tuple(result.association.bindings)
        source_sequence = int(getattr(publication_envelope, "sequence"))
        publication_timestamp = float(
            getattr(publication_envelope, "timestamp")
        )
        pending_maps = (
            (False, self._d5_a3_pending_by_camera),
            (True, self._d5_a3_r0_pending_by_camera),
        )
        for is_r0, pending_map in pending_maps:
            for camera_id in tuple(pending_map):
                self._record_d5_a3_observations_for_camera(
                    camera_id=camera_id,
                    pending_map=pending_map,
                    is_r0=is_r0,
                    result=result,
                    bindings=bindings,
                    center_track_ids=center_track_ids,
                    source_sequence=source_sequence,
                    publication_timestamp=publication_timestamp,
                )

    def _record_active_vision_zero_detection_frames(
        self,
        frame_events: Iterable[CameraFrameEvent],
    ) -> None:
        """Attach processed zero-detection frames to eligible A3 or R0 commands."""

        center_track_ids = tuple(
            track.global_track_id for track in self.latest_d2_tracks
        )
        for event in sorted(
            tuple(frame_events),
            key=lambda item: (
                item.arrival_timestamp,
                item.measurement_timestamp,
                item.camera_id,
                item.event_id,
            ),
        ):
            self._d5_camera_empty_frame_received_count += 1
            if not event.empty:
                self._d5_camera_empty_frame_rejected_count += 1
                self._d5_a3_bridge_blocker_counts[
                    "camera_empty_frame_contains_detections"
                ] += 1
                continue
            consumed = False
            for is_r0, pending_map in (
                (False, self._d5_a3_pending_by_camera),
                (True, self._d5_a3_r0_pending_by_camera),
            ):
                consumed = bool(
                    self._record_d5_a3_zero_detection_for_camera(
                        event=event,
                        pending_map=pending_map,
                        is_r0=is_r0,
                        center_track_ids=center_track_ids,
                    )
                    or consumed
                )
            if consumed:
                self._d5_camera_empty_frame_consumed_count += 1
            else:
                self._d5_camera_empty_frame_unmatched_count += 1

    def _record_d5_a3_zero_detection_for_camera(
        self,
        *,
        event: CameraFrameEvent,
        pending_map: dict[str, list[_D5A3PendingObservationWindow]],
        is_r0: bool,
        center_track_ids: tuple[str, ...],
    ) -> bool:
        """Bind one empty camera frame using command time and version lineage."""

        current_pending = tuple(pending_map.get(event.camera_id, ()))
        if not current_pending:
            return False
        expired: list[
            tuple[
                _D5A3PendingObservationWindow,
                bool,
                ActiveVisionA3CandidatePhysicalWindowStatus,
            ]
        ] = []
        eligible: list[_D5A3PendingObservationWindow] = []
        for pending in current_pending:
            trace = pending.trace
            target_id = trace.target_global_track_id
            if target_id is not None and target_id not in center_track_ids:
                self._d5_a3_bridge_blocker_counts[
                    "active_vision_target_reference_stale"
                ] += 1
                expired.append(
                    (
                        pending,
                        False,
                        ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
                    )
                )
                continue
            if (
                self.latest_plan is None
                or int(self.latest_plan.version) != trace.decision.plan_version
            ):
                self._d5_a3_bridge_blocker_counts[
                    "active_vision_plan_version_changed"
                ] += 1
                expired.append(
                    (
                        pending,
                        False,
                        ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
                    )
                )
                continue
            feedback = trace.camera_feedback
            command = trace.issued_command_payload
            if feedback is None or command is None:
                expired.append(
                    (
                        pending,
                        False,
                        ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
                    )
                )
                continue
            window_start = feedback.camera_state.state_timestamp
            window_expires = float(command["expires_timestamp"])
            if window_expires + _EPS < event.measurement_timestamp:
                expired.append(
                    (
                        pending,
                        True,
                        ActiveVisionA3CandidatePhysicalWindowStatus.MISSING,
                    )
                )
                continue
            if not (
                window_start + _EPS < event.measurement_timestamp
                and event.measurement_timestamp <= window_expires + _EPS
            ):
                continue
            eligible.append(pending)

        for pending, inventory_complete, status in expired:
            self._finalize_d5_a3_pending(
                event.camera_id,
                pending,
                is_r0=is_r0,
                inventory_end_timestamp=event.arrival_timestamp,
                observation_inventory_complete=inventory_complete,
                physical_window_status=status,
            )
        if not eligible:
            return False
        selected = max(
            eligible,
            key=lambda item: (
                item.trace.camera_feedback.camera_state.state_timestamp,
                item.trace.window_index,
            ),
        )
        for pending in eligible:
            if pending is not selected:
                self._finalize_d5_a3_pending(
                    event.camera_id,
                    pending,
                    is_r0=is_r0,
                    inventory_end_timestamp=event.arrival_timestamp,
                    observation_inventory_complete=True,
                    physical_window_status=(
                        ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
                    ),
                )
        trace = selected.trace
        event_versions = (
            event.plan_version,
            event.coalition_version,
            event.communication_version,
        )
        trace_versions = (
            trace.decision.plan_version,
            trace.decision.coalition_version,
            trace.decision.communication_version,
        )
        if event.resource_id != trace.resource_id:
            self._d5_camera_empty_frame_rejected_count += 1
            self._d5_a3_bridge_blocker_counts[
                "camera_empty_frame_resource_mismatch"
            ] += 1
            return False
        if event_versions != trace_versions:
            self._d5_camera_empty_frame_rejected_count += 1
            self._d5_a3_bridge_blocker_counts[
                "camera_empty_frame_version_mismatch"
            ] += 1
            return False
        arm_label = "r0" if is_r0 else "a3"
        try:
            frame = active_vision_a3_zero_detection_frame(
                frame_key=f"{arm_label}-empty:{event.event_id}",
                camera_id=event.camera_id,
                resource_id=event.resource_id,
                measurement_timestamp=event.measurement_timestamp,
                arrival_timestamp=event.arrival_timestamp,
                plan_version=trace.decision.plan_version,
                coalition_version=trace.decision.coalition_version,
                communication_version=trace.decision.communication_version,
                target_global_track_id=trace.target_global_track_id,
                center_global_track_ids=center_track_ids,
                evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
                source_sequence=event.scan_index,
            )
        except (TypeError, ValueError) as exc:
            self._d5_camera_empty_frame_rejected_count += 1
            self._d5_a3_bridge_blocker_counts[
                f"camera_empty_frame_{type(exc).__name__.lower()}"
            ] += 1
            self._finalize_d5_a3_pending(
                event.camera_id,
                selected,
                is_r0=is_r0,
                inventory_end_timestamp=event.arrival_timestamp,
                observation_inventory_complete=True,
                physical_window_status=(
                    ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
                ),
            )
            return False
        selected.observation_frames.append(frame)
        if is_r0:
            self._d5_a3_r0_observation_frame_count += 1
        else:
            self._d5_a3_observation_frame_count += 1
        self._finalize_d5_a3_pending(
            event.camera_id,
            selected,
            is_r0=is_r0,
            inventory_end_timestamp=event.arrival_timestamp,
            observation_inventory_complete=True,
            physical_window_status=(
                ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE
            ),
        )
        return True

    def _record_d5_a3_observations_for_camera(
        self,
        *,
        camera_id: str,
        pending_map: dict[str, list[_D5A3PendingObservationWindow]],
        is_r0: bool,
        result: Any,
        bindings: tuple[Any, ...],
        center_track_ids: tuple[str, ...],
        source_sequence: int,
        publication_timestamp: float,
    ) -> None:
        """Attach one publication to either the candidate or R0 pending set."""

        tracklets = tuple(
            item
            for item in result.tracklets
            if item.camera_id == camera_id
        )
        grouped: dict[float, list[Any]] = {}
        for tracklet in tracklets:
            grouped.setdefault(
                float(tracklet.measurement_timestamp),
                [],
            ).append(tracklet)
        for measurement_timestamp in sorted(grouped):
            current_pending = tuple(pending_map.get(camera_id, ()))
            expired: list[
                tuple[
                    _D5A3PendingObservationWindow,
                    bool,
                    ActiveVisionA3CandidatePhysicalWindowStatus,
                ]
            ] = []
            eligible: list[_D5A3PendingObservationWindow] = []
            for pending in current_pending:
                trace = pending.trace
                target_id = trace.target_global_track_id
                if (
                    target_id is not None
                    and target_id not in center_track_ids
                ):
                    self._d5_a3_bridge_blocker_counts[
                        "active_vision_target_reference_stale"
                    ] += 1
                    expired.append(
                        (
                            pending,
                            False,
                            ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
                        )
                    )
                    continue
                if (
                    self.latest_plan is None
                    or int(self.latest_plan.version)
                    != trace.decision.plan_version
                ):
                    self._d5_a3_bridge_blocker_counts[
                        "active_vision_plan_version_changed"
                    ] += 1
                    expired.append(
                        (
                            pending,
                            False,
                            ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
                        )
                    )
                    continue
                feedback = trace.camera_feedback
                command = trace.issued_command_payload
                if feedback is None or command is None:
                    expired.append(
                        (
                            pending,
                            False,
                            ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
                        )
                    )
                    continue
                window_start = feedback.camera_state.state_timestamp
                window_expires = float(command["expires_timestamp"])
                if window_expires + _EPS < measurement_timestamp:
                    expired.append(
                        (
                            pending,
                            True,
                            ActiveVisionA3CandidatePhysicalWindowStatus.MISSING,
                        )
                    )
                elif (
                    window_start + _EPS < measurement_timestamp
                    and measurement_timestamp <= window_expires + _EPS
                ):
                    eligible.append(pending)

            for pending, inventory_complete, status in expired:
                self._finalize_d5_a3_pending(
                    camera_id,
                    pending,
                    is_r0=is_r0,
                    inventory_end_timestamp=publication_timestamp,
                    observation_inventory_complete=inventory_complete,
                    physical_window_status=status,
                )
            if not eligible:
                continue
            selected = max(
                eligible,
                key=lambda item: (
                    item.trace.camera_feedback.camera_state.state_timestamp,
                    item.trace.window_index,
                ),
            )
            for pending in eligible:
                if pending is not selected:
                    self._finalize_d5_a3_pending(
                        camera_id,
                        pending,
                        is_r0=is_r0,
                        inventory_end_timestamp=publication_timestamp,
                        observation_inventory_complete=True,
                        physical_window_status=(
                            ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
                        ),
                    )

            trace = selected.trace
            target_id = trace.target_global_track_id
            observations = tuple(
                sorted(
                    (
                        item
                        for item in grouped[measurement_timestamp]
                        if item.resource_id == trace.resource_id
                    ),
                    key=lambda item: item.tracklet_key,
                )
            )
            if not observations:
                self._finalize_d5_a3_pending(
                    camera_id,
                    selected,
                    is_r0=is_r0,
                    inventory_end_timestamp=publication_timestamp,
                    observation_inventory_complete=True,
                    physical_window_status=(
                        ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
                    ),
                )
                continue
            arm_label = "r0" if is_r0 else "a3"
            frame_key = (
                f"{arm_label}-frame:{source_sequence}:{camera_id}:"
                f"{measurement_timestamp:.9f}"
            )
            try:
                frame = active_vision_a3_observation_frame(
                    frame_key=frame_key,
                    observations=observations,
                    bindings=bindings,
                    target_global_track_id=target_id,
                    center_global_track_ids=center_track_ids,
                    plan_version=trace.decision.plan_version,
                    coalition_version=trace.decision.coalition_version,
                    communication_version=(
                        trace.decision.communication_version
                    ),
                    evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
                    source_sequence=source_sequence,
                )
            except (TypeError, ValueError) as exc:
                self._d5_a3_bridge_blocker_counts[
                    f"active_vision_observation_{type(exc).__name__.lower()}"
                ] += 1
            else:
                selected.observation_frames.append(frame)
                if is_r0:
                    self._d5_a3_r0_observation_frame_count += 1
                else:
                    self._d5_a3_observation_frame_count += 1
            self._finalize_d5_a3_pending(
                camera_id,
                selected,
                is_r0=is_r0,
                inventory_end_timestamp=publication_timestamp,
                observation_inventory_complete=True,
                physical_window_status=(
                    ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE
                    if selected.observation_frames
                    else ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
                ),
            )

    def _finalize_d5_a3_pending(
        self,
        camera_id: str,
        pending: _D5A3PendingObservationWindow,
        *,
        is_r0: bool = False,
        inventory_end_timestamp: float | None = None,
        observation_inventory_complete: bool = False,
        physical_window_status: (
            ActiveVisionA3CandidatePhysicalWindowStatus
        ) = ActiveVisionA3CandidatePhysicalWindowStatus.UNKNOWN,
    ) -> None:
        pending_map = (
            self._d5_a3_r0_pending_by_camera
            if is_r0
            else self._d5_a3_pending_by_camera
        )
        pending_items = pending_map.get(camera_id)
        if not pending_items:
            return
        for index, item in enumerate(pending_items):
            if item is pending:
                pending_items.pop(index)
                break
        else:
            return
        if not pending_items:
            pending_map.pop(camera_id, None)
        trace = pending.trace
        if is_r0:
            r0_window = None
            if pending.observation_frames:
                frames = tuple(pending.observation_frames)
                feedback = trace.camera_feedback
                start = feedback.camera_state.state_timestamp
                end = max(
                    max(item.measurement_timestamp for item in frames),
                    max(item.arrival_timestamp for item in frames),
                    start + 1.0e-6,
                )
                try:
                    r0_window = (
                        assemble_active_vision_a3_rule_arm_physical_observation_window(
                            trace,
                            observation_frames=frames,
                            window_start_timestamp=start,
                            window_end_timestamp=end,
                        )
                    )
                except (TypeError, ValueError) as exc:
                    self._d5_a3_bridge_blocker_counts[
                        f"active_vision_r0_window_{type(exc).__name__.lower()}"
                    ] += 1
            if r0_window is not None:
                self._d5_a3_r0_window_by_comparison_key[
                    trace.comparison_key
                ] = r0_window
                self._d5_a3_r0_physical_window_count += 1
            return

        candidate_window = None
        if trace.model_action_adopted and pending.observation_frames:
            frames = tuple(pending.observation_frames)
            feedback = trace.camera_feedback
            if feedback is not None:
                start = feedback.camera_state.state_timestamp
                end = max(
                    max(item.measurement_timestamp for item in frames),
                    max(item.arrival_timestamp for item in frames),
                    start + 1.0e-6,
                )
                try:
                    candidate_window = (
                        assemble_active_vision_a3_physical_observation_window(
                            trace,
                            arm=ActiveVisionA3WindowArm.A3,
                            observation_frames=frames,
                            window_start_timestamp=start,
                            window_end_timestamp=end,
                        )
                    )
                except (TypeError, ValueError) as exc:
                    self._d5_a3_bridge_blocker_counts[
                        f"active_vision_window_{type(exc).__name__.lower()}"
                    ] += 1
        resolved_status = physical_window_status
        if candidate_window is not None:
            resolved_status = (
                ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE
            )
            observation_inventory_complete = True
        elif (
            resolved_status
            is ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE
        ):
            resolved_status = (
                ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
            )
        try:
            stage_evidence = self._d5_a3_candidate_stage_evidence(
                trace=trace,
                frames=tuple(pending.observation_frames),
                inventory_end_timestamp=inventory_end_timestamp,
                observation_inventory_complete=(
                    observation_inventory_complete
                ),
                physical_window_status=resolved_status,
            )
        except (TypeError, ValueError) as exc:
            self._d5_a3_bridge_blocker_counts[
                f"active_vision_candidate_stage_{type(exc).__name__.lower()}"
            ] += 1
        else:
            self._d5_a3_candidate_stage_by_comparison_key[
                trace.comparison_key
            ] = stage_evidence
        evidence = assemble_active_vision_a3_evidence(
            trace,
            candidate_window=candidate_window,
            same_key_r0_window=None,
        )
        self._d5_a3_evidence_by_comparison_key[
            trace.comparison_key
        ] = evidence
        if candidate_window is not None:
            self._d5_a3_physical_window_count += 1

    def _d5_a3_candidate_stage_evidence(
        self,
        *,
        trace: ActiveVisionA3AdoptionTrace,
        frames: tuple[ActiveVisionA3AnonymousObservationFrame, ...],
        inventory_end_timestamp: float | None,
        observation_inventory_complete: bool,
        physical_window_status: ActiveVisionA3CandidatePhysicalWindowStatus,
    ) -> ActiveVisionA3CandidateStageEvidence:
        command = trace.issued_command_payload
        ack = trace.runtime_ack
        feedback = trace.camera_feedback
        if command is None:
            raise ValueError("candidate-stage trace is missing its command")
        issued = float(command["issued_timestamp"])
        expires = float(command["expires_timestamp"])
        inventory_end = (
            issued
            if inventory_end_timestamp is None
            else max(issued, float(inventory_end_timestamp))
        )
        status = physical_window_status
        inventory_complete = bool(observation_inventory_complete)
        if (
            status is ActiveVisionA3CandidatePhysicalWindowStatus.UNKNOWN
        ):
            if inventory_end + _EPS >= expires:
                status = ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
                inventory_complete = True
            else:
                status = (
                    ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
                )
        measurements = tuple(
            float(item.measurement_timestamp) for item in frames
        )
        arrivals = tuple(float(item.arrival_timestamp) for item in frames)
        return ActiveVisionA3CandidateStageEvidence(
            comparison_key=trace.comparison_key,
            scenario_id=trace.scenario_id,
            scale=trace.scale,
            seed=trace.seed,
            window_index=trace.window_index,
            sample_key=trace.sample_key,
            camera_id=trace.camera_id,
            resource_id=trace.resource_id,
            pairing_context_sha256=trace.pairing_context_sha256,
            adoption_trace_sha256=trace.trace_sha256,
            source_event_log_sha256=trace.source_event_log_sha256,
            inventory_start_timestamp=issued,
            inventory_end_timestamp=inventory_end,
            runtime_event_inventory_complete=True,
            command_issued_timestamp=issued,
            command_expires_timestamp=expires,
            runtime_ack_timestamp=(
                None if ack is None else float(ack.ack_timestamp)
            ),
            runtime_ack_applied=(
                None
                if ack is None
                else bool(ack.accepted and ack.status_code == "applied")
            ),
            camera_feedback_timestamp=(
                None
                if feedback is None
                else float(feedback.camera_state.state_timestamp)
            ),
            observation_inventory_complete=inventory_complete,
            anonymous_observation_frame_count=len(frames),
            first_measurement_timestamp=(
                None if not measurements else min(measurements)
            ),
            last_measurement_timestamp=(
                None if not measurements else max(measurements)
            ),
            first_arrival_timestamp=(
                None if not arrivals else min(arrivals)
            ),
            last_arrival_timestamp=(
                None if not arrivals else max(arrivals)
            ),
            physical_window_status=status,
            evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        )

    def _finalize_all_d5_a3_pending(
        self,
        *,
        timestamp_s: float,
    ) -> None:
        inventory_end = float(timestamp_s)
        for camera_id in tuple(self._d5_a3_pending_by_camera):
            for pending in tuple(
                self._d5_a3_pending_by_camera.get(camera_id, ())
            ):
                command = pending.trace.issued_command_payload
                expires = (
                    None
                    if command is None
                    else float(command["expires_timestamp"])
                )
                complete = bool(
                    expires is not None
                    and inventory_end + _EPS >= expires
                )
                self._finalize_d5_a3_pending(
                    camera_id,
                    pending,
                    inventory_end_timestamp=inventory_end,
                    observation_inventory_complete=complete,
                    physical_window_status=(
                        ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
                        if complete
                        else ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
                    ),
                )
        for camera_id in tuple(self._d5_a3_r0_pending_by_camera):
            for pending in tuple(
                self._d5_a3_r0_pending_by_camera.get(camera_id, ())
            ):
                self._finalize_d5_a3_pending(
                    camera_id,
                    pending,
                    is_r0=True,
                    inventory_end_timestamp=inventory_end,
                )

    def active_vision_r0_window_records(
        self,
    ) -> tuple[dict[str, Any], ...]:
        """Return independent deterministic R0 windows for main pairing."""

        return tuple(
            window.to_dict()
            for _, window in sorted(
                self._d5_a3_r0_window_by_comparison_key.items()
            )
        )

    def active_vision_a3_candidate_stage_records(
        self,
    ) -> tuple[dict[str, Any], ...]:
        """Return runtime-observed A3 stage inventories for main pairing."""

        return tuple(
            evidence.to_dict()
            for _, evidence in sorted(
                self._d5_a3_candidate_stage_by_comparison_key.items()
            )
        )

    def learning_adoption_evidence_records(
        self,
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        """Return truth-free A1/A2/A3 records for D6 read-only auditing."""

        a2 = tuple(
            evidence.to_dict()
            for _, evidence in sorted(
                self._d4_a2_evidence_by_application.items()
            )
        )
        a3 = tuple(
            evidence.to_dict()
            for _, evidence in sorted(
                self._d5_a3_evidence_by_comparison_key.items()
            )
        )
        return {
            "a1": (),
            "a2": a2,
            "a3": a3,
        }

    def d1_consistency_evidence_records(self) -> tuple[Any, ...]:
        """Return the final truth-free D1 evidence snapshot for offline scoring."""

        if self.d1 is None:
            return ()
        return tuple(self.d1.consistency_evidence_records())

    def _run_active_vision(
        self,
        step_input: RuntimeStepInput,
        now: float,
    ) -> tuple[CameraObservationCommand, ...]:
        """Build a truth-free D5 snapshot and emit bounded camera-only commands."""

        if self.d5_active_vision is None or self.latest_plan is None:
            return ()
        self._active_vision_communication_version += 1
        plan_version = int(self.latest_plan.version)
        coalition_version = max(
            (
                int(assignment.coalition_version or 0)
                for assignment in self.latest_plan.assignments
            ),
            default=0,
        )
        track_by_id = {
            track.global_track_id: track for track in self.latest_d2_tracks
        }
        committed_target_ids = self._committed_d2_target_ids()
        committed_track_by_id = {
            track_id: track
            for track_id, track in track_by_id.items()
            if track_id in committed_target_ids
        }
        camera_by_resource = {
            camera.resource_id: camera for camera in step_input.cameras
        }
        interceptor_assignments = tuple(
            ActiveVisionAssignmentReference(
                resource_id=assignment.resource_id,
                camera_id=camera_by_resource[assignment.resource_id].camera_id,
                global_track_id=assignment.target_id,
            )
            for assignment in self.latest_plan.assignments
            if assignment.resource_id in camera_by_resource
            and assignment.target_id in committed_track_by_id
        )
        recon_assignments = self._active_vision_recon_track_cues(
            step_input,
            track_by_id=committed_track_by_id,
            camera_by_resource=camera_by_resource,
        )
        assignments = interceptor_assignments + recon_assignments
        tracks = tuple(
            ActiveVisionTrackReference(
                global_track_id=track.global_track_id,
                track_version=max(0, int(track.age)),
                measurement_timestamp=min(now, float(track.timestamp)),
            )
            for track in sorted(
                self.latest_d2_tracks,
                key=lambda item: item.global_track_id,
            )
        )
        cameras = tuple(
            self._active_vision_camera_state(camera)
            for camera in sorted(step_input.cameras, key=lambda item: item.camera_id)
        )
        projections = tuple(
            self._active_vision_projection(
                resource_id=assignment.resource_id,
                target_id=assignment.global_track_id,
                camera=camera_by_resource[assignment.resource_id],
                track=track_by_id[assignment.global_track_id],
                step_input=step_input,
                now=now,
            )
            for assignment in assignments
            if assignment.resource_id in camera_by_resource
            and assignment.global_track_id in track_by_id
        )
        snapshot = ActiveVisionSnapshotV1(
            snapshot_timestamp=now,
            plan=ActiveVisionPlanReference(
                plan_version=plan_version,
                coalition_version=coalition_version,
                assignments=assignments,
            ),
            communication=ActiveVisionCommunicationState(
                communication_version=self._active_vision_communication_version,
                plan_version=plan_version,
                coalition_version=coalition_version,
                update_timestamp=now,
                healthy=not bool(
                    getattr(self.latest_d4_decision, "fail_closed", False)
                ),
            ),
            tracks=tracks,
            cameras=cameras,
            projections=projections,
        )
        decisions = tuple(
            self.d5_active_vision.decide(
                snapshot,
                camera_id=camera.camera_id,
                current_timestamp=now,
                expected_plan_version=plan_version,
                expected_coalition_version=coalition_version,
                expected_communication_version=(
                    self._active_vision_communication_version
                ),
                requested_mode=self.stack_config.d5_active_vision_mode,
            )
            for camera in cameras
        )
        commands = tuple(
            self._active_vision_command(
                decision,
                runtime_camera=next(
                    item
                    for item in step_input.cameras
                    if item.camera_id == decision.effective_action.camera_id
                ),
                step_input=step_input,
            )
            for decision in decisions
        )
        self._d5_a3_command_context_by_camera.clear()
        for decision, command in zip(decisions, commands, strict=True):
            context = _D5A3CommandContext(
                window_index=self._d5_a3_command_index,
                timestamp_s=now,
                snapshot=snapshot,
                decision=decision,
                command=command,
            )
            self._d5_a3_command_context_by_camera[command.camera_id] = context
            self._d5_a3_command_index += 1
        self.latest_active_vision_snapshot = snapshot
        self.latest_active_vision_decisions = decisions
        self.latest_active_vision_recon_cue_count = len(recon_assignments)
        if self.stack_config.capture_learning_artifacts:
            runtime_camera_by_id = {
                camera.camera_id: camera for camera in step_input.cameras
            }
            self._d5_active_vision_learning_frames.append(
                D5ActiveVisionLearningFrame(
                    frame_index=len(self._d5_active_vision_learning_frames),
                    timestamp_s=now,
                    snapshot=snapshot,
                    decisions=decisions,
                    camera_feedback=tuple(
                        ActiveVisionCameraFeedbackV1(
                            camera_state=camera,
                            last_accepted_command_version=(
                                None
                                if runtime_camera_by_id[
                                    camera.camera_id
                                ].last_communication_version == 0
                                else runtime_camera_by_id[
                                    camera.camera_id
                                ].last_communication_version
                            ),
                        )
                        for camera in cameras
                    ),
                )
            )
        return commands

    def _active_vision_recon_track_cues(
        self,
        step_input: RuntimeStepInput,
        *,
        track_by_id: Mapping[str, Any],
        camera_by_resource: Mapping[str, CameraRuntimeState],
    ) -> tuple[ActiveVisionAssignmentReference, ...]:
        """Select truth-free observation cues for recon cameras.

        D3 continues to own interceptor allocation. These references only tell
        D5 which already assigned global track a recon camera should observe so
        an interceptor/recon overlap can be formed for cross-view association.
        """

        if not self.stack_config.d5_recon_track_cues_enabled:
            return ()
        target_ids = tuple(
            sorted(
                {
                    assignment.target_id
                    for assignment in self.latest_plan.assignments
                    if assignment.target_id in track_by_id
                }
            )
        )
        recon_cameras = tuple(
            sorted(
                (
                    camera
                    for camera in step_input.cameras
                    if camera.platform_kind == "recon"
                    and camera.resource_id in camera_by_resource
                ),
                key=lambda item: item.camera_id,
            )
        )
        if not target_ids or not recon_cameras:
            return ()

        interceptor_cameras_by_target: dict[str, list[CameraRuntimeState]] = {}
        for assignment in self.latest_plan.assignments:
            camera = camera_by_resource.get(assignment.resource_id)
            if (
                assignment.target_id in track_by_id
                and camera is not None
                and camera.platform_kind == "interceptor"
            ):
                interceptor_cameras_by_target.setdefault(
                    assignment.target_id, []
                ).append(camera)

        def camera_angular_offset(
            camera: CameraRuntimeState,
            global_track_id: str,
        ) -> float:
            camera_position = _active_camera_position(camera, step_input)
            predicted_position, _ = _predict_track_position(
                track_by_id[global_track_id],
                float(step_input.timestamp),
            )
            yaw_deg, pitch_deg = _yaw_pitch_from_ned(
                predicted_position - camera_position
            )
            return abs(_wrap_degrees(yaw_deg - camera.yaw_deg)) + abs(
                float(pitch_deg - camera.pitch_deg)
            )

        unused_target_ids = set(target_ids)
        cues: list[ActiveVisionAssignmentReference] = []
        for camera in recon_cameras:
            candidate_ids = unused_target_ids or set(target_ids)

            def overlap_offset(global_track_id: str) -> tuple[float, str]:
                interceptor_offsets = tuple(
                    camera_angular_offset(item, global_track_id)
                    for item in interceptor_cameras_by_target.get(
                        global_track_id, ()
                    )
                )
                return (
                    camera_angular_offset(camera, global_track_id)
                    + min(interceptor_offsets, default=360.0),
                    global_track_id,
                )

            selected_target_id = min(candidate_ids, key=overlap_offset)
            unused_target_ids.discard(selected_target_id)
            cues.append(
                ActiveVisionAssignmentReference(
                    resource_id=camera.resource_id,
                    camera_id=camera.camera_id,
                    global_track_id=selected_target_id,
                )
            )
        return tuple(cues)

    def _active_vision_camera_state(
        self,
        camera: CameraRuntimeState,
    ) -> ActiveVisionCameraState:
        config = self._require_ready()
        wide_fov = (
            config.camera_horizontal_fov_deg
            if camera.platform_kind == "interceptor"
            else config.recon_camera_horizontal_fov_deg
        )
        zoom_fov = min(
            float(self.stack_config.d5_active_vision_zoom_fov_deg),
            float(wide_fov) * 0.75,
        )
        return ActiveVisionCameraState(
            camera_id=camera.camera_id,
            resource_id=camera.resource_id,
            state_timestamp=camera.timestamp,
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-180.0, 180.0),
            pitch_limits_deg=(-89.9, 89.9),
            max_yaw_rate_deg_s=60.0,
            max_pitch_rate_deg_s=60.0,
            max_slew_deg_s=80.0,
            current_fov_mode=ActiveVisionFovMode(camera.fov_mode),
            wide_horizontal_fov_deg=float(wide_fov),
            zoom_horizontal_fov_deg=float(zoom_fov),
        )

    def _active_vision_projection(
        self,
        *,
        resource_id: str,
        target_id: str,
        camera: CameraRuntimeState,
        track: Any,
        step_input: RuntimeStepInput,
        now: float,
    ) -> ActiveVisionProjectionEvidence:
        camera_position = _active_camera_position(camera, step_input)
        predicted_position, predicted_covariance = _predict_track_position(
            track,
            now,
        )
        relative = predicted_position - camera_position
        target_yaw, target_pitch = _yaw_pitch_from_ned(relative)
        yaw_error = _wrap_degrees(target_yaw - camera.yaw_deg)
        pitch_error = float(target_pitch - camera.pitch_deg)
        angular_covariance = _angular_covariance_deg2(
            relative,
            predicted_covariance,
            attitude_std_deg=(0.08 if camera.platform_kind == "interceptor" else 0.04),
        )
        vertical_fov = _vertical_fov_deg(
            camera.horizontal_fov_deg,
            platform_kind=camera.platform_kind,
            config=self._require_ready(),
        )
        in_fov = bool(
            abs(yaw_error) <= 0.5 * camera.horizontal_fov_deg
            and abs(pitch_error) <= 0.5 * vertical_fov
            and relative.dot(relative) > 1.0e-9
        )
        terminal = self._latest_terminal_by_pair.get(
            (resource_id, target_id)
        )
        if terminal is None:
            association_confidence = float(
                np.clip(
                    float(track.track_quality)
                    * (1.0 - float(track.association_risk)),
                    0.0,
                    1.0,
                )
            )
        else:
            association_confidence = float(
                np.clip(terminal[0]["association_confidence"], 0.0, 1.0)
            )
        visibility_probability = float(
            np.clip(
                (0.35 + 0.65 * float(track.track_quality))
                * (1.0 if in_fov else 0.15),
                0.0,
                1.0,
            )
        )
        return ActiveVisionProjectionEvidence(
            camera_id=camera.camera_id,
            global_track_id=target_id,
            measurement_timestamp=min(now, float(track.timestamp)),
            arrival_timestamp=now,
            yaw_error_deg=yaw_error,
            pitch_error_deg=pitch_error,
            projection_covariance_deg2=tuple(
                float(value) for value in angular_covariance.reshape(-1)
            ),
            visibility_probability=visibility_probability,
            occlusion_fraction=0.0,
            association_confidence=association_confidence,
            in_fov=in_fov,
        )

    def _active_vision_command(
        self,
        decision: Any,
        *,
        runtime_camera: CameraRuntimeState,
        step_input: RuntimeStepInput,
    ) -> CameraObservationCommand:
        action = decision.effective_action
        yaw = _wrap_degrees(runtime_camera.yaw_deg + action.yaw_delta_deg)
        pitch = float(
            np.clip(
                runtime_camera.pitch_deg + action.pitch_delta_deg,
                -89.9,
                89.9,
            )
        )
        position = _active_camera_position(runtime_camera, step_input)
        aim_point = position + _direction_from_yaw_pitch(yaw, pitch) * 1_000.0
        config = self._require_ready()
        wide_fov = (
            config.camera_horizontal_fov_deg
            if runtime_camera.platform_kind == "interceptor"
            else config.recon_camera_horizontal_fov_deg
        )
        horizontal_fov = (
            float(wide_fov)
            if action.fov_mode is ActiveVisionFovMode.WIDE
            else min(
                float(self.stack_config.d5_active_vision_zoom_fov_deg),
                float(wide_fov) * 0.75,
            )
        )
        reason = action.reason
        if decision.fallback_reason is not None:
            reason = f"{reason}|fallback={decision.fallback_reason}"
        return CameraObservationCommand(
            camera_id=action.camera_id,
            resource_id=runtime_camera.resource_id,
            issued_timestamp=action.issued_timestamp,
            expires_timestamp=action.expires_timestamp,
            plan_version=action.plan_version,
            coalition_version=action.coalition_version,
            communication_version=action.communication_version,
            intent=action.intent.value,
            aim_point_ned=aim_point,
            horizontal_fov_deg=horizontal_fov,
            fov_mode=action.fov_mode.value,
            target_global_track_id=action.target_global_track_id,
            requested_mode=decision.requested_mode.value,
            effective_mode=decision.effective_mode.value,
            reason=reason,
        )

    def _d4_region_resource_snapshot(
        self,
        step_input: RuntimeStepInput,
        *,
        formal_snapshot: RegionalFailoverSnapshot,
        now: float,
    ) -> RegionResourceSnapshot:
        """Aggregate online estimates into a truth-free regional graph."""

        config = self._require_ready()
        region_ids = tuple(item.region_id for item in formal_snapshot.regions)
        tasks_by_region: dict[str, list[RegionalTaskEvidence]] = {
            region_id: [] for region_id in region_ids
        }
        for task in formal_snapshot.tasks:
            tasks_by_region.setdefault(task.region_id, []).append(task)

        assigned_region_by_resource: dict[str, str] = {}
        for task in formal_snapshot.tasks:
            for resource_id in task.d3_assigned_member_ids:
                assigned_region_by_resource.setdefault(resource_id, task.region_id)
        active_resources_by_region = {region_id: 0 for region_id in region_ids}
        for index, resource_id in enumerate(step_input.interceptors.platform_ids):
            if not bool(step_input.interceptors.active[index]):
                continue
            region_id = assigned_region_by_resource.get(
                resource_id,
                _region_for_position(
                    step_input.interceptors.state_ned[index, :3],
                    config.region_count,
                ),
            )
            if region_id in active_resources_by_region:
                active_resources_by_region[region_id] += 1

        decision_by_region = {
            item.region_id: item for item in self.latest_d4_decision.region_decisions
        }
        region_signals: dict[str, dict[str, Any]] = {}
        for region_id in region_ids:
            tasks = tasks_by_region.get(region_id, [])
            decision = decision_by_region[region_id]
            committed_ids = {
                resource_id
                for task in tasks
                for resource_id in task.d3_assigned_member_ids
            }
            available = max(
                active_resources_by_region.get(region_id, 0),
                len(committed_ids),
            )
            reserve = min(
                max(0, available - len(committed_ids)),
                int(math.ceil(0.10 * available)),
            )
            applicable = [
                task
                for task in tasks
                if task.d5_consistency != D5Consistency.NOT_APPLICABLE
            ]
            required_visual = sum(task.required_member_count for task in applicable)
            supported_visual = sum(len(task.d5_support_member_ids) for task in applicable)
            d5_visibility = (
                1.0
                if required_visual == 0
                else min(1.0, supported_visual / required_visual)
            )
            consistency_score = {
                D5Consistency.CONSISTENT: 1.0,
                D5Consistency.UNKNOWN: 0.5,
                D5Consistency.INCONSISTENT: 0.0,
                D5Consistency.NOT_APPLICABLE: 1.0,
            }
            d5_consistency = (
                1.0
                if not applicable
                else float(
                    np.mean(
                        [consistency_score[task.d5_consistency] for task in applicable]
                    )
                )
            )
            readiness_records = tuple(decision.secondary_readiness.values())
            secondary_coverage = max(
                (float(item.get("coverage_ratio", 0.0)) for item in readiness_records),
                default=0.0,
            )
            secondary_readiness = max(
                (float(bool(item.get("ready", False))) for item in readiness_records),
                default=0.0,
            )
            unresolved_demand = sum(
                max(0, task.required_member_count - len(task.d3_assigned_member_ids))
                + int(not task.d3_resource_feasible)
                for task in tasks
            )
            region_signals[region_id] = {
                "target_demand": float(
                    sum(task.required_member_count for task in tasks)
                ),
                "high_threat_backlog": float(unresolved_demand),
                "d1_uncertainty": float(
                    np.mean([task.d1_covariance_trace for task in tasks])
                    if tasks
                    else 0.0
                ),
                "d2_uncertainty": float(
                    np.mean([task.d2_ambiguity_score for task in tasks])
                    if tasks
                    else 0.0
                ),
                "d5_visibility": d5_visibility,
                "d5_consistency": d5_consistency,
                "available_resources": available,
                "reserve_resources": reserve,
                "secondary_coverage": secondary_coverage,
                "secondary_readiness": secondary_readiness,
                "communication_capacity": (
                    config.communication_bandwidth_bytes_per_s * 8.0 / 1_000_000.0
                    if config.communication_enabled
                    else 0.0
                ),
                "communication_latency_s": config.communication_latency_s,
                "packet_loss_rate": config.communication_drop_probability,
                "committed_resources": len(committed_ids),
                "coalition_ack_complete": all(
                    (not commit.commit_required) or commit.execution_authorized
                    for commit in decision.coalition_commits
                ),
                "fault_fenced": bool(
                    decision.fail_closed or not decision.execution_allowed
                ),
                "fault_fence_epoch": (
                    int(formal_snapshot.epoch)
                    if decision.fail_closed or not decision.execution_allowed
                    else None
                ),
                "assignment_conflict_count": sum(
                    "conflict" in str(reason)
                    for reason in decision.risk_factors
                ),
                "degradation_failed": bool(decision.fail_closed),
            }

        edges = self._d4_region_resource_edges(
            region_ids,
            region_signals,
        )
        return RegionResourceSnapshot.from_regional_decision(
            self.latest_d4_decision,
            snapshot_id=(
                f"{config.scenario_name}-s{config.seed}-"
                f"p{formal_snapshot.plan_version}-t{now:.6f}"
            ),
            scenario_id=config.scenario_name,
            scenario_version=config.scenario_version,
            seed=config.seed,
            region_signals=region_signals,
            edges=edges,
        )

    def _d4_region_resource_edges(
        self,
        region_ids: tuple[str, ...],
        region_signals: Mapping[str, Mapping[str, Any]],
    ) -> tuple[RegionResourceEdge, ...]:
        config = self._require_ready()
        if len(region_ids) <= 1:
            return ()
        arc_distance = 2.0 * math.pi * config.protected_radius_m / len(region_ids)
        transfer_time = arc_distance / config.interceptor_speed_mps
        bandwidth_mbps = (
            config.communication_bandwidth_bytes_per_s * 8.0 / 1_000_000.0
            if config.communication_enabled
            else 0.0
        )
        directed_pairs: set[tuple[str, str]] = set()
        for index, source in enumerate(region_ids):
            directed_pairs.add((source, region_ids[(index + 1) % len(region_ids)]))
            directed_pairs.add((source, region_ids[(index - 1) % len(region_ids)]))
        edges: list[RegionResourceEdge] = []
        for source, target in sorted(directed_pairs):
            signal = region_signals[source]
            transferable = max(
                0,
                int(signal["available_resources"])
                - int(signal["reserve_resources"])
                - int(signal["committed_resources"]),
            )
            edges.append(
                RegionResourceEdge(
                    source_region_id=source,
                    target_region_id=target,
                    transferable_resources=transferable,
                    distance_m=arc_distance,
                    transfer_time_s=transfer_time,
                    bandwidth_mbps=bandwidth_mbps,
                    communication_available=config.communication_enabled,
                    maneuver_available=True,
                    partitioned=(
                        not config.communication_enabled
                        or config.communication_drop_probability >= 1.0
                    ),
                    bidirectional=False,
                )
            )
        return tuple(edges)

    def _consume_d4_communication_deliveries(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
    ) -> tuple[list[RuntimeCommunicationIntent], bool, bool]:
        """Turn actual network deliveries into bounded D4 evidence.

        The main transport remains authoritative for arrival time. D4's causal
        gate validates the receipt, while this adapter checks the current plan
        and payload-specific identities before exposing any readiness or ACK.
        """

        partition_generation = int(
            step_input.communication_partition_generation
        )
        changed = partition_generation != self._d4_partition_generation
        self._d4_partition_generation = partition_generation
        seen = False
        intents: list[RuntimeCommunicationIntent] = []
        deliveries = tuple(
            sorted(
                step_input.delivered_communication_messages,
                key=lambda item: (
                    float(getattr(item, "arrival_timestamp", 0.0)),
                    int(getattr(getattr(item, "envelope", None), "sequence", 0)),
                ),
            )
        )
        for delivered in deliveries:
            seen = True
            self._d4_communication_received_count += 1
            try:
                receipt = CommunicationDeliveryReceipt.from_delivered_message(
                    delivered
                )
                payload = dict(delivered.envelope.payload)
            except (AttributeError, KeyError, TypeError, ValueError):
                self._record_d4_communication_rejection(
                    "receipt_invalid"
                )
                continue
            plan = self.latest_plan
            if plan is None:
                self._record_d4_communication_rejection(
                    "current_plan_missing"
                )
                continue
            if (
                receipt.message_kind
                == CausalMessageKind.REGIONAL_PLAN_OWNER_ACK.value
            ):
                try:
                    delivery = (
                        RegionResourceOwnerAckDelivery.from_delivered_message(
                            delivered
                        )
                    )
                    ack = delivery.ack
                    pending = self._d4_a2_pending_by_plan[
                        (ack.applied_plan_id, ack.applied_plan_version)
                    ]
                    if (
                        str(plan.plan_id) != ack.applied_plan_id
                        or int(plan.version) != ack.applied_plan_version
                    ):
                        raise ValueError("owner ACK references a stale plan")
                    validation = validate_region_resource_owner_ack_delivery(
                        delivery,
                        expected_ack=pending.expected_owner_ack,
                        expected_destination_node_id=(
                            pending.context.runtime_node_id
                        ),
                        decision_timestamp_s=now,
                        communication_gate=self._d4_causal_gate,
                    )
                except (KeyError, TypeError, ValueError):
                    self._record_d4_communication_rejection(
                        "owner_ack_delivery_invalid"
                    )
                    continue
                if not validation.accepted:
                    self._record_d4_communication_rejection(
                        *validation.reason_codes
                    )
                    continue
                self._d4_communication_accepted_count += 1
                self._d4_communication_accept_counts[
                    receipt.message_kind
                ] += 1
                communication_validation = (
                    validation.communication_validation
                )
                if (
                    communication_validation is not None
                    and communication_validation.idempotent_replay
                ):
                    continue
                pending.owner_ack_delivery = delivery
                self._d4_owner_ack_delivery_count += 1
                changed = True
                partial = self._d4_safe_adoption_assembler.assemble(
                    preparation=pending.preparation,
                    context=pending.context,
                    evaluated_at_s=now,
                    d3_successor_plan=pending.plan_reference,
                    runtime_ack=pending.runtime_ack,
                    owner_ack_delivery=delivery,
                )
                pending.final_evidence = partial
                self._remember_d4_a2_evidence(partial)
                continue
            if (
                receipt.message_kind
                == CausalMessageKind.COALITION_MEMBER_ACK.value
                and isinstance(payload.get("member_ack"), Mapping)
            ):
                try:
                    delivery = (
                        RegionResourceCoalitionAckDelivery.from_delivered_message(
                            delivered
                        )
                    )
                    member_ack = delivery.member_ack
                    if (
                        str(plan.plan_id) != member_ack.plan_id
                        or int(plan.version) != member_ack.plan_version
                    ):
                        raise ValueError(
                            "coalition ACK references a stale plan"
                        )
                    matching_assignment = next(
                        assignment
                        for assignment in plan.assignments
                        if assignment.resource_id == member_ack.resource_id
                        and assignment.target_id == member_ack.global_track_id
                        and assignment.coalition_id == member_ack.coalition_id
                        and int(assignment.coalition_version or 0)
                        == member_ack.coalition_version
                    )
                    pending = self._d4_a2_pending_by_plan.get(
                        (member_ack.plan_id, member_ack.plan_version)
                    )
                    transport_reference = self._d4_plan_transport_references.get(
                        (member_ack.plan_id, member_ack.plan_version)
                    )
                    if pending is not None:
                        requirement = next(
                            item
                            for item in pending.plan_reference.coalition_requirements
                            if item.global_track_id
                            == member_ack.global_track_id
                            and item.coalition_id == member_ack.coalition_id
                            and item.coalition_version
                            == member_ack.coalition_version
                            and member_ack.resource_id
                            in item.required_member_ids
                        )
                        expected_authority = (
                            pending.plan_reference.owner_node_id
                        )
                        expected_plan_payload_sha256 = (
                            pending.plan_reference.plan_payload_sha256
                        )
                        expected_plan_bus_sequence = (
                            pending.plan_reference.plan_bus_sequence
                        )
                        expected_lease_expires_at_s = (
                            pending.plan_reference.valid_until_s
                        )
                        expected_partition_generation = (
                            pending.context.partition_generation
                        )
                    else:
                        if transport_reference is None:
                            raise ValueError(
                                "coalition ACK has no published plan reference"
                            )
                        requirement = None
                        expected_authority = (
                            self._d4_expected_authority_for_delivery(
                                plan,
                                member_ack.resource_id,
                                receipt,
                            )
                        )
                        (
                            expected_plan_payload_sha256,
                            expected_plan_bus_sequence,
                        ) = transport_reference
                        expected_lease_expires_at_s = (
                            delivery.lease_expires_at_s
                        )
                        expected_partition_generation = partition_generation
                    validation = (
                        validate_region_resource_coalition_ack_delivery(
                            delivery,
                            expected_member_ack=member_ack,
                            expected_authority_id=expected_authority,
                            expected_plan_payload_sha256=(
                                expected_plan_payload_sha256
                            ),
                            expected_plan_bus_sequence=(
                                expected_plan_bus_sequence
                            ),
                            expected_lease_expires_at_s=(
                                expected_lease_expires_at_s
                            ),
                            expected_partition_generation=(
                                expected_partition_generation
                            ),
                            expected_destination_node_id=expected_authority,
                            decision_timestamp_s=now,
                            expected_message_id=delivery.message_id,
                            communication_gate=self._d4_causal_gate,
                        )
                    )
                except (KeyError, StopIteration, TypeError, ValueError):
                    self._record_d4_communication_rejection(
                        "coalition_ack_delivery_invalid"
                    )
                    continue
                if not validation.accepted:
                    self._record_d4_communication_rejection(
                        *validation.reason_codes
                    )
                    continue
                self._d4_communication_accepted_count += 1
                self._d4_communication_accept_counts[
                    receipt.message_kind
                ] += 1
                communication_validation = (
                    validation.communication_validation
                )
                if (
                    communication_validation is not None
                    and communication_validation.idempotent_replay
                ):
                    continue
                key = (
                    member_ack.resource_id,
                    member_ack.global_track_id,
                    member_ack.plan_version,
                    member_ack.epoch,
                    delivery.partition_generation,
                )
                self._d4_ack_deliveries[key] = _D4AcceptedDelivery(
                    payload=member_ack.to_dict(),
                    receipt=delivery.receipt,
                )
                if pending is not None and requirement is not None:
                    coalition_key = (
                        requirement.global_track_id,
                        requirement.coalition_id,
                        requirement.coalition_version,
                    )
                    pending.coalition_ack_deliveries.setdefault(
                        coalition_key,
                        {},
                    )[member_ack.resource_id] = delivery
                    self._d4_coalition_ack_delivery_count += 1
                changed = True
                continue
            expected_epoch = self._plan_authority_epoch(plan)
            custom_reasons = self._d4_payload_rejection_reasons(
                receipt,
                payload,
                plan=plan,
                expected_epoch=expected_epoch,
                partition_generation=partition_generation,
            )
            if custom_reasons:
                self._record_d4_communication_rejection(*custom_reasons)
                continue
            expectation = CommunicationEvidenceExpectation(
                expected_source_node_id=receipt.source_node_id,
                expected_destination_node_id=receipt.destination_node_id,
                expected_authority_id=receipt.authority_id,
                expected_plan_version=int(plan.version),
                expected_epoch=expected_epoch,
                expected_lease_expires_at_s=receipt.lease_expires_at_s,
                decision_timestamp_s=now,
                expected_partition_generation=partition_generation,
                expected_payload_digest=canonical_payload_digest(payload),
                expected_message_id=receipt.message_id,
            )
            if receipt.message_kind == CausalMessageKind.SECONDARY_READINESS.value:
                validation = self._d4_causal_gate.validate_secondary_readiness(
                    receipt,
                    expectation,
                )
            elif (
                receipt.message_kind
                == CausalMessageKind.REGIONAL_PLAN_BROADCAST.value
            ):
                validation = (
                    self._d4_causal_gate.validate_regional_plan_broadcast(
                        receipt,
                        expectation,
                    )
                )
            elif (
                receipt.message_kind
                == CausalMessageKind.COALITION_MEMBER_ACK.value
            ):
                validation = (
                    self._d4_causal_gate.validate_coalition_member_ack(
                        receipt,
                        expectation,
                    )
                )
            else:
                self._record_d4_communication_rejection(
                    "message_kind_unsupported"
                )
                continue
            if not validation.accepted:
                self._record_d4_communication_rejection(
                    *validation.reason_codes
                )
                continue

            self._d4_communication_accepted_count += 1
            self._d4_communication_accept_counts[
                receipt.message_kind
            ] += 1
            if validation.idempotent_replay:
                continue
            if receipt.message_kind == CausalMessageKind.SECONDARY_READINESS.value:
                changed = (
                    self._record_d4_readiness_delivery(payload, receipt)
                    or changed
                )
            elif (
                receipt.message_kind
                == CausalMessageKind.REGIONAL_PLAN_BROADCAST.value
            ):
                key = (
                    receipt.destination_node_id,
                    receipt.plan_version,
                    receipt.epoch,
                    receipt.partition_generation,
                )
                self._d4_plan_deliveries[key] = _D4AcceptedDelivery(
                    payload=payload,
                    receipt=receipt,
                )
                intents.extend(
                    self._d4_ack_intents_from_plan_delivery(
                        payload,
                        receipt,
                        step_input.interceptors,
                        now=now,
                    )
                )
                changed = True
            else:
                key = (
                    str(payload["resource_id"]),
                    str(payload["global_track_id"]),
                    receipt.plan_version,
                    receipt.epoch,
                    receipt.partition_generation,
                )
                self._d4_ack_deliveries[key] = _D4AcceptedDelivery(
                    payload=payload,
                    receipt=receipt,
                )
                changed = True
        return intents, changed, seen

    def _d4_payload_rejection_reasons(
        self,
        receipt: CommunicationDeliveryReceipt,
        payload: Mapping[str, Any],
        *,
        plan: Any,
        expected_epoch: int,
        partition_generation: int,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if str(payload.get("plan_id", "")) != str(plan.plan_id):
            reasons.append("plan_id_mismatch")
        if receipt.plan_version != int(plan.version):
            reasons.append(
                "plan_version_stale"
                if receipt.plan_version < int(plan.version)
                else "plan_version_mismatch"
            )
        if receipt.epoch != int(expected_epoch):
            reasons.append(
                "epoch_stale"
                if receipt.epoch < int(expected_epoch)
                else "epoch_mismatch"
            )
        if receipt.partition_generation != int(partition_generation):
            reasons.append("partition_generation_mismatch")
        if receipt.message_kind == CausalMessageKind.SECONDARY_READINESS.value:
            if receipt.destination_node_id != _D4_GATE_NODE_ID:
                reasons.append("destination_node_mismatch")
            if str(payload.get("node_id", "")) != receipt.source_node_id:
                reasons.append("readiness_node_mismatch")
            if receipt.authority_id != receipt.source_node_id:
                reasons.append("authority_id_mismatch")
        elif (
            receipt.message_kind
            == CausalMessageKind.REGIONAL_PLAN_BROADCAST.value
        ):
            if str(payload.get("member_id", "")) != receipt.destination_node_id:
                reasons.append("plan_member_mismatch")
            expected_authority = self._d4_expected_authority_for_delivery(
                plan,
                receipt.destination_node_id,
                receipt,
            )
            if (
                receipt.source_node_id != expected_authority
                or receipt.authority_id != expected_authority
            ):
                reasons.append("plan_authority_mismatch")
        elif receipt.message_kind == CausalMessageKind.COALITION_MEMBER_ACK.value:
            if str(payload.get("resource_id", "")) != receipt.source_node_id:
                reasons.append("ack_member_mismatch")
            expected_authority = self._d4_expected_authority_for_delivery(
                plan,
                receipt.source_node_id,
                receipt,
            )
            if (
                receipt.destination_node_id != expected_authority
                or receipt.authority_id != expected_authority
            ):
                reasons.append("ack_authority_mismatch")
        return tuple(dict.fromkeys(reasons))

    def _record_d4_communication_rejection(self, *reasons: str) -> None:
        self._d4_communication_rejected_count += 1
        normalized = tuple(
            dict.fromkeys(str(reason or "receipt_invalid") for reason in reasons)
        )
        self._d4_communication_rejection_counts.update(normalized)

    def _record_d4_readiness_delivery(
        self,
        payload: Mapping[str, Any],
        receipt: CommunicationDeliveryReceipt,
    ) -> bool:
        changed = False
        for region_id in tuple(str(item) for item in payload.get("region_ids", ())):
            key = (
                receipt.source_node_id,
                region_id,
                receipt.plan_version,
                receipt.epoch,
                receipt.partition_generation,
            )
            previous = self._d4_readiness_receptions.get(key)
            if previous is None:
                continuous_predecessors = tuple(
                    item
                    for candidate_key, item in self._d4_readiness_receptions.items()
                    if candidate_key[0] == receipt.source_node_id
                    and candidate_key[1] == region_id
                    and candidate_key[4] == receipt.partition_generation
                    and 0.0
                    <= receipt.arrival_timestamp_s - item.last_arrival_s
                    <= self.stack_config.d4_communication_stale_after_s
                )
                predecessor = (
                    max(
                        continuous_predecessors,
                        key=lambda item: item.last_arrival_s,
                    )
                    if continuous_predecessors
                    else None
                )
                self._d4_readiness_receptions[key] = _D4ReadinessReception(
                    payload=dict(payload),
                    receipt=receipt,
                    first_arrival_s=(
                        receipt.arrival_timestamp_s
                        if predecessor is None
                        else predecessor.first_arrival_s
                    ),
                    last_arrival_s=receipt.arrival_timestamp_s,
                    observation_count=(
                        1
                        if predecessor is None
                        else predecessor.observation_count + 1
                    ),
                )
            else:
                previous.payload = dict(payload)
                previous.receipt = receipt
                previous.last_arrival_s = receipt.arrival_timestamp_s
                previous.observation_count += 1
            changed = True
        return changed

    def _d4_ack_intents_from_plan_delivery(
        self,
        payload: Mapping[str, Any],
        receipt: CommunicationDeliveryReceipt,
        navigation: PlatformNavigationBatch,
        *,
        now: float,
    ) -> list[RuntimeCommunicationIntent]:
        resource_id = receipt.destination_node_id
        active_by_id = {
            node_id: bool(navigation.active[index])
            for index, node_id in enumerate(navigation.platform_ids)
        }
        intents: list[RuntimeCommunicationIntent] = []
        for assignment in tuple(payload.get("member_assignments", ())):
            if not isinstance(assignment, Mapping):
                continue
            required_count = int(assignment.get("required_member_count", 1))
            if required_count <= 1:
                continue
            coalition_id = str(assignment.get("coalition_id") or "")
            coalition_version = int(assignment.get("coalition_version") or 0)
            global_track_id = str(assignment.get("global_track_id") or "")
            if not coalition_id or not global_track_id:
                continue
            plan_payload_sha256 = str(
                payload.get("plan_payload_sha256", "")
            )
            plan_bus_sequence = payload.get("plan_bus_sequence")
            if (
                len(plan_payload_sha256) != 64
                or not isinstance(plan_bus_sequence, Integral)
                or int(plan_bus_sequence) <= 0
            ):
                self._d4_a2_bridge_blocker_counts[
                    "coalition_plan_transport_reference_missing"
                ] += 1
                ack_payload = self._d4_message_payload(
                    message_kind=CausalMessageKind.COALITION_MEMBER_ACK.value,
                    source=resource_id,
                    destination=receipt.source_node_id,
                    authority_id=receipt.authority_id,
                    plan_id=str(payload["plan_id"]),
                    plan_version=receipt.plan_version,
                    epoch=receipt.epoch,
                    lease_expires_at_s=receipt.lease_expires_at_s,
                    partition_generation=receipt.partition_generation,
                    now=now,
                    extra={
                        "resource_id": resource_id,
                        "global_track_id": global_track_id,
                        "coalition_id": coalition_id,
                        "coalition_version": coalition_version,
                        "can_execute": active_by_id.get(resource_id, False),
                        "evidence_timestamp": now,
                        "valid_until": receipt.lease_expires_at_s,
                        "source_plan_message_id": receipt.message_id,
                    },
                )
                intents.append(
                    self._d4_intent(
                        source=resource_id,
                        destination=receipt.source_node_id,
                        topic=_D4_ACK_TOPIC,
                        payload=ack_payload,
                    )
                )
                continue
            member_ack = CoalitionMemberAck(
                resource_id=resource_id,
                global_track_id=global_track_id,
                coalition_id=coalition_id,
                coalition_version=coalition_version,
                plan_id=str(payload["plan_id"]),
                plan_version=receipt.plan_version,
                epoch=receipt.epoch,
                can_execute=active_by_id.get(resource_id, False),
                evidence_timestamp=now,
                valid_until=receipt.lease_expires_at_s,
                metadata={
                    "source_plan_message_id": receipt.message_id,
                },
            )
            self._d4_message_sequence += 1
            message_id = (
                "d4:coalition_member_ack:"
                f"{self._d4_message_sequence:012d}"
            )
            ack_payload = {
                "schema": REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA,
                "message_id": message_id,
                "message_kind": (
                    CausalMessageKind.COALITION_MEMBER_ACK.value
                ),
                "authority_id": receipt.authority_id,
                "plan_version": receipt.plan_version,
                "plan_payload_sha256": plan_payload_sha256,
                "plan_bus_sequence": int(plan_bus_sequence),
                "epoch": receipt.epoch,
                "lease_expires_at_s": receipt.lease_expires_at_s,
                "partition_generation": receipt.partition_generation,
                "member_ack": member_ack.to_dict(),
            }
            intents.append(
                self._d4_intent(
                    source=resource_id,
                    destination=receipt.source_node_id,
                    topic=_D4_ACK_TOPIC,
                    payload=ack_payload,
                    random_stream=_D4_STRICT_EVIDENCE_RANDOM_STREAM,
                )
            )
        return intents

    def _d4_periodic_communication_intents(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
        center_health: C2Health,
        secondary_failed: bool,
    ) -> list[RuntimeCommunicationIntent]:
        config = self._require_ready()
        plan = self.latest_plan
        if not config.communication_enabled or plan is None:
            return []
        epoch = self._plan_authority_epoch(plan)
        partition_generation = int(
            step_input.communication_partition_generation
        )
        intents: list[RuntimeCommunicationIntent] = []
        lease_duration_s = max(
            config.assignment_period_s
            * self.stack_config.assignment_lease_multiplier,
            config.region_policy_period_s,
        )
        if (
            not secondary_failed
            and now + _EPS >= self._next_d4_readiness_s
        ):
            active_indices = [
                index
                for index, active in enumerate(step_input.recon.active)
                if bool(active)
            ]
            all_regions = _region_ids(config.region_count)
            for rank, index in enumerate(active_indices):
                node_id = step_input.recon.platform_ids[index]
                region_ids = tuple(
                    region_id
                    for region_index, region_id in enumerate(all_regions)
                    if region_index % len(active_indices) == rank
                )
                lease_expires_at = now + lease_duration_s
                payload = self._d4_message_payload(
                    message_kind=CausalMessageKind.SECONDARY_READINESS.value,
                    source=node_id,
                    destination=_D4_GATE_NODE_ID,
                    authority_id=node_id,
                    plan_id=plan.plan_id,
                    plan_version=plan.version,
                    epoch=epoch,
                    lease_expires_at_s=lease_expires_at,
                    partition_generation=partition_generation,
                    now=now,
                    extra={
                        "node_id": node_id,
                        "region_ids": region_ids,
                        "readiness_timestamp_s": now,
                        "heartbeat_timestamp_s": now,
                        "cue_freshness_s": 0.0,
                        "availability_confirmed": True,
                        "gimbal_pointing_ok": True,
                        "coverage_matches_requested_cell": True,
                        "coverage_ratio": (
                            self.stack_config.secondary_coverage_ratio
                        ),
                        "network_full_view_rate": (
                            self.stack_config.secondary_network_full_view_rate
                        ),
                    },
                )
                intents.append(
                    self._d4_intent(
                        source=node_id,
                        destination=_D4_GATE_NODE_ID,
                        topic=_D4_READINESS_TOPIC,
                        payload=payload,
                    )
                )
            self._next_d4_readiness_s = _advance_schedule(
                self._next_d4_readiness_s,
                self.stack_config.d4_readiness_period_s,
                now,
            )

        if now + _EPS >= self._next_d4_plan_broadcast_s:
            transport_reference = self._d4_plan_transport_references.get(
                (str(plan.plan_id), int(plan.version))
            )
            strict_transport_reference_available = (
                transport_reference is not None
            )
            if transport_reference is None:
                self._d4_a2_bridge_blocker_counts[
                    "plan_transport_reference_not_yet_published"
                ] += 1
                plan_payload_sha256 = None
                plan_bus_sequence = None
            else:
                plan_payload_sha256, plan_bus_sequence = transport_reference
            plan_key = (
                str(plan.plan_id),
                int(plan.version),
                int(epoch),
                partition_generation,
                strict_transport_reference_available,
            )
            plan_changed = plan_key != self._d4_last_broadcast_plan_key
            for index, resource_id in enumerate(
                step_input.interceptors.platform_ids
            ):
                if not bool(step_input.interceptors.active[index]):
                    continue
                delivery = self._d4_plan_deliveries.get(
                    (
                        resource_id,
                        int(plan.version),
                        int(epoch),
                        partition_generation,
                    )
                )
                refresh_due = bool(
                    delivery is None
                    or now - delivery.receipt.arrival_timestamp_s
                    >= (
                        self.stack_config.d4_communication_stale_after_s
                        - self.stack_config.d4_plan_broadcast_period_s
                    )
                )
                if not plan_changed and not refresh_due:
                    continue
                authority_id = self._d4_authority_for_member(
                    plan,
                    resource_id,
                )
                if not self._d4_authority_can_transmit(
                    authority_id,
                    step_input,
                    center_health=center_health,
                    secondary_failed=secondary_failed,
                ):
                    continue
                lease_expires_at = self._d4_plan_lease_for_member(
                    plan,
                    resource_id,
                    now=now,
                    default_duration_s=lease_duration_s,
                )
                if lease_expires_at <= now + _EPS:
                    continue
                self._d4_expected_plan_authorities[
                    (
                        str(plan.plan_id),
                        int(plan.version),
                        int(epoch),
                        partition_generation,
                        resource_id,
                    )
                ] = authority_id
                member_assignments = tuple(
                    {
                        "global_track_id": assignment.target_id,
                        "required_member_count": (
                            assignment.required_resource_count
                        ),
                        "coalition_id": assignment.coalition_id,
                        "coalition_version": assignment.coalition_version,
                        "member_role": assignment.member_role,
                    }
                    for assignment in plan.assignments
                    if assignment.resource_id == resource_id
                )
                transport_binding = (
                    {
                        "plan_payload_sha256": plan_payload_sha256,
                        "plan_bus_sequence": plan_bus_sequence,
                    }
                    if strict_transport_reference_available
                    else {}
                )
                payload = self._d4_message_payload(
                    message_kind=(
                        CausalMessageKind.REGIONAL_PLAN_BROADCAST.value
                    ),
                    source=authority_id,
                    destination=resource_id,
                    authority_id=authority_id,
                    plan_id=plan.plan_id,
                    plan_version=plan.version,
                    epoch=epoch,
                    lease_expires_at_s=lease_expires_at,
                    partition_generation=partition_generation,
                    now=now,
                    extra={
                        "member_id": resource_id,
                        "member_assignments": member_assignments,
                        **transport_binding,
                    },
                )
                intents.append(
                    self._d4_intent(
                        source=authority_id,
                        destination=resource_id,
                        topic=_D4_PLAN_TOPIC,
                        payload=payload,
                        random_stream=(
                            _D4_STRICT_EVIDENCE_RANDOM_STREAM
                            if strict_transport_reference_available
                            else "shared_v1"
                        ),
                    )
                )
            self._d4_last_broadcast_plan_key = plan_key
            if strict_transport_reference_available:
                self._next_d4_plan_broadcast_s = _advance_schedule(
                    self._next_d4_plan_broadcast_s,
                    self.stack_config.d4_plan_broadcast_period_s,
                    now,
                )
        return intents

    def _d4_message_payload(
        self,
        *,
        message_kind: str,
        source: str,
        destination: str,
        authority_id: str,
        plan_id: str,
        plan_version: int,
        epoch: int,
        lease_expires_at_s: float,
        partition_generation: int,
        now: float,
        extra: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._d4_message_sequence += 1
        return {
            "schema": _D4_CONTROL_SCHEMA,
            "message_id": (
                f"d4:{message_kind}:{self._d4_message_sequence:012d}"
            ),
            "message_kind": message_kind,
            "source_node_id": source,
            "destination_node_id": destination,
            "authority_id": authority_id,
            "plan_id": str(plan_id),
            "plan_version": int(plan_version),
            "epoch": int(epoch),
            "lease_expires_at_s": float(lease_expires_at_s),
            "partition_generation": int(partition_generation),
            "generated_timestamp_s": float(now),
            **dict(extra),
        }

    def _d4_intent(
        self,
        *,
        source: str,
        destination: str,
        topic: str,
        payload: Mapping[str, Any],
        random_stream: str = "shared_v1",
    ) -> RuntimeCommunicationIntent:
        self._d4_communication_intent_counts[topic] += 1
        return RuntimeCommunicationIntent(
            source=source,
            destination=destination,
            topic=topic,
            schema_version=_D4_CONTROL_SCHEMA,
            payload=payload,
            random_stream=random_stream,
        )

    def _d4_authority_for_member(self, plan: Any, resource_id: str) -> str:
        assignments = tuple(
            assignment
            for assignment in plan.assignments
            if assignment.resource_id == resource_id
        )
        for assignment in assignments:
            metadata = dict(assignment.metadata)
            owner = metadata.get("regional_owner_node_id") or metadata.get(
                "owner_node_id"
            )
            if owner:
                if (
                    self._last_secondary_failed
                    and str(owner).startswith("RECON-")
                ):
                    distributed_owner = (
                        self._d4_distributed_authority_for_member(
                            resource_id
                        )
                    )
                    if distributed_owner is not None:
                        return distributed_owner
                return str(owner)
        metadata = dict(plan.metadata)
        owner = metadata.get("owner_node_id") or metadata.get(
            "current_plan_owner_node_id"
        )
        if owner and str(owner) != "regional_multi_owner":
            if (
                str(owner) == "d3_central"
                and self._last_center_health is C2Health.FAILED
            ):
                for assignment in assignments:
                    region_id = self._track_region_by_id.get(
                        assignment.target_id
                    )
                    if (
                        region_id is not None
                        and region_id
                        in self._d4_vetted_secondary_by_region
                    ):
                        return self._d4_vetted_secondary_by_region[
                            region_id
                        ]
                if self._d4_vetted_secondary_by_region:
                    return self._d4_vetted_secondary_by_region[
                        sorted(self._d4_vetted_secondary_by_region)[0]
                    ]
            return str(owner)
        source = getattr(plan, "source_node_id", None)
        if source and str(source) != "d3_regional_router":
            return str(source)
        return str(resource_id)

    def _d4_expected_authority_for_delivery(
        self,
        plan: Any,
        resource_id: str,
        receipt: CommunicationDeliveryReceipt,
    ) -> str:
        return self._d4_expected_plan_authorities.get(
            (
                str(plan.plan_id),
                int(receipt.plan_version),
                int(receipt.epoch),
                int(receipt.partition_generation),
                str(resource_id),
            ),
            self._d4_authority_for_member(plan, resource_id),
        )

    def _d4_distributed_authority_for_member(
        self,
        resource_id: str,
    ) -> str | None:
        decision = self.latest_d4_decision
        if decision is None:
            return None
        for region in decision.region_decisions:
            if (
                region.selected_layer
                is not RegionalAuthorityLayer.DISTRIBUTED
                or not region.execution_allowed
                or region.fail_closed
            ):
                continue
            assigned_members = {
                member_id
                for member_ids in region.fallback_assignments.values()
                for member_id in member_ids
            }
            if resource_id in assigned_members and region.ownership.owner_id:
                return str(region.ownership.owner_id)
        return None

    def _remember_d4_vetted_secondaries(self, decision: Any) -> None:
        """Retain only D4-assessed ready owners for one authority transition."""

        for region in decision.region_decisions:
            selected = region.selected_secondary_id
            if selected is None:
                continue
            readiness = region.secondary_readiness.get(selected, {})
            if readiness.get("ready") is True:
                self._d4_vetted_secondary_by_region[
                    region.region_id
                ] = selected

    @staticmethod
    def _d4_authority_can_transmit(
        authority_id: str,
        step_input: RuntimeStepInput,
        *,
        center_health: C2Health,
        secondary_failed: bool,
    ) -> bool:
        if authority_id == "d3_central":
            return center_health is not C2Health.FAILED
        if authority_id in set(step_input.recon.platform_ids):
            if secondary_failed:
                return False
            index = step_input.recon.platform_ids.index(authority_id)
            return bool(step_input.recon.active[index])
        if authority_id in set(step_input.interceptors.platform_ids):
            index = step_input.interceptors.platform_ids.index(authority_id)
            return bool(step_input.interceptors.active[index])
        return False

    @staticmethod
    def _d4_plan_lease_for_member(
        plan: Any,
        resource_id: str,
        *,
        now: float,
        default_duration_s: float,
    ) -> float:
        for assignment in plan.assignments:
            if assignment.resource_id != resource_id:
                continue
            metadata = dict(assignment.metadata)
            for key in (
                "regional_lease_expires_at_s",
                "secondary_lease_expires_at_s",
            ):
                if metadata.get(key) is not None:
                    return float(metadata[key])
        metadata = dict(plan.metadata)
        for key in (
            "regional_min_lease_expires_at_s",
            "secondary_lease_expires_at_s",
        ):
            if metadata.get(key) is not None:
                return float(metadata[key])
        return float(now) + float(default_duration_s)

    def _d4_communication_publication(
        self,
        now: float,
    ) -> RuntimePublication:
        return RuntimePublication(
            topic="modules.d4.communication_evidence",
            source="MAIN-STACK",
            schema_version="scalable3d-d4-communication-evidence-v1",
            payload={
                "timestamp_s": now,
                "partition_generation": self._d4_partition_generation,
                "received_count": self._d4_communication_received_count,
                "accepted_count": self._d4_communication_accepted_count,
                "rejected_count": self._d4_communication_rejected_count,
                "accept_counts": dict(
                    sorted(self._d4_communication_accept_counts.items())
                ),
                "rejection_counts": dict(
                    sorted(self._d4_communication_rejection_counts.items())
                ),
            },
            copy_payload=False,
        )

    def _selected_secondary_for_active_regions(self, plan: Any) -> str | None:
        """Return one D4-vetted owner only when it covers every active region."""

        if self.latest_d4_decision is None:
            return None
        active_regions = {
            self._track_region_by_id.get(assignment.target_id)
            for assignment in plan.assignments
        }
        active_regions.discard(None)
        if not active_regions:
            return None
        decision_by_region = {
            decision.region_id: decision
            for decision in self.latest_d4_decision.region_decisions
        }
        selected_ids: set[str] = set()
        for region_id in active_regions:
            decision = decision_by_region.get(str(region_id))
            if decision is None or decision.selected_secondary_id is None:
                return None
            readiness = decision.secondary_readiness.get(
                decision.selected_secondary_id,
                {},
            )
            if readiness.get("ready") is not True:
                return None
            selected_ids.add(decision.selected_secondary_id)
        return next(iter(selected_ids)) if len(selected_ids) == 1 else None

    def _has_fallback_authority_decision(self) -> bool:
        if self.latest_d4_decision is None:
            return False
        fallback_layers = {
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.DISTRIBUTED,
        }
        return any(
            decision.task_ids
            and decision.selected_layer in fallback_layers
            and decision.execution_allowed
            and not decision.fail_closed
            and decision.ownership.active
            for decision in self.latest_d4_decision.region_decisions
        )

    def _regional_authority_from_d4(
        self,
        previous_plan: Any,
        *,
        target_ids: set[str],
        now: float,
    ) -> RegionalAuthorityInput:
        """Translate one complete D4 frame into D3-owned authority DTOs.

        The adapter never invents an owner, membership, epoch, lease or global
        track identity.  Missing coverage and inconsistent source generations
        are rejected before D3 is called.
        """

        frame = self.latest_d4_decision
        if frame is None:
            raise RegionalPlanAuthorityError("regional_d4_decision_missing")
        if float(frame.timestamp_s) > float(now) + _EPS:
            raise RegionalPlanAuthorityError("regional_d4_decision_from_future")

        assignments_by_target = previous_plan.assignments_by_target()
        explicitly_unassigned_targets = {
            str(target_id)
            for target_id in previous_plan.unassigned_target_ids
            if str(target_id) in target_ids
        }
        if any(
            assignments_by_target.get(target_id)
            for target_id in explicitly_unassigned_targets
        ):
            raise RegionalPlanAuthorityError(
                "regional_d3_unassigned_target_has_executable_binding"
            )
        executable_target_ids = target_ids - explicitly_unassigned_targets
        if not executable_target_ids:
            raise RegionalPlanAuthorityError(
                "regional_d4_no_executable_targets"
            )
        if any(
            target_id not in assignments_by_target
            for target_id in executable_target_ids
        ):
            raise RegionalPlanAuthorityError(
                "regional_d3_executable_target_assignment_missing"
            )
        coalition_by_target = {
            coalition.target_id: coalition for coalition in previous_plan.coalitions
        }
        task_to_target = {
            f"task:{target_id}": target_id for target_id in sorted(target_ids)
        }
        covered_targets: set[str] = set()
        grants: list[RegionalAuthorityGrant] = []
        fallback_layers = {
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.DISTRIBUTED,
        }

        for decision in frame.region_decisions:
            regional_task_ids = tuple(
                task_id for task_id in decision.task_ids if task_id in task_to_target
            )
            if not regional_task_ids:
                continue
            if len(regional_task_ids) != len(decision.task_ids):
                raise RegionalPlanAuthorityError("regional_d4_unknown_task_id")
            if decision.selected_layer not in fallback_layers:
                raise RegionalPlanAuthorityError("regional_d4_target_not_fallback_owned")
            ownership = decision.ownership
            if (
                not decision.execution_allowed
                or decision.fail_closed
                or not ownership.active
            ):
                raise RegionalPlanAuthorityError("regional_d4_execution_not_allowed")
            if (
                ownership.owner_layer is not decision.selected_layer
                or not ownership.owner_id
                or not ownership.owner_role
            ):
                raise RegionalPlanAuthorityError("regional_d4_owner_contract_mismatch")
            if (
                ownership.plan_id != previous_plan.plan_id
                or ownership.plan_version != previous_plan.version
            ):
                raise RegionalPlanAuthorityError("regional_d4_stale_source_plan")
            if set(ownership.task_ids) != set(decision.task_ids):
                raise RegionalPlanAuthorityError("regional_d4_owner_task_set_mismatch")
            if float(now) >= float(ownership.lease_expires_at_s):
                raise RegionalPlanAuthorityError("regional_d4_authority_lease_expired")

            commit_by_target = {
                commit.global_track_id: commit
                for commit in decision.coalition_commits
            }
            grant_targets: list[str] = []
            assigned_by_target: dict[str, tuple[str, ...]] = {}
            commit_evidence: list[RegionalCoalitionCommitEvidence] = []
            grant_lease = float(ownership.lease_expires_at_s)

            for task_id in regional_task_ids:
                target_id = task_to_target[task_id]
                if target_id in covered_targets:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_duplicate_target_authority"
                    )
                previous_assignments = assignments_by_target.get(target_id, ())
                if not previous_assignments:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_target_assignment_missing"
                    )
                assigned_resource_ids = tuple(
                    decision.fallback_assignments.get(task_id, ())
                )
                required_count = int(
                    previous_assignments[0].required_resource_count
                )
                if len(assigned_resource_ids) != required_count:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_required_member_count_unsatisfied"
                    )
                commit = commit_by_target.get(target_id)
                if commit is None:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_commit_evidence_missing"
                    )
                if bool(commit.commit_required) != (required_count > 1):
                    raise RegionalPlanAuthorityError(
                        "regional_d4_commit_requirement_mismatch"
                    )
                if set(commit.required_member_ids) != set(assigned_resource_ids):
                    raise RegionalPlanAuthorityError(
                        "regional_d4_commit_membership_mismatch"
                    )

                coalition_id: str | None = None
                coalition_version: int | None = None
                if required_count > 1:
                    coalition = coalition_by_target.get(target_id)
                    previous_member_ids = {
                        assignment.resource_id for assignment in previous_assignments
                    }
                    if coalition is None or previous_member_ids != set(
                        assigned_resource_ids
                    ):
                        raise RegionalPlanAuthorityError(
                            "regional_coalition_version_transition_unadjudicated"
                        )
                    coalition_id = coalition.coalition_id
                    coalition_version = coalition.version

                evidence_lease = min(
                    float(commit.lease_expires_at_s),
                    float(ownership.lease_expires_at_s),
                )
                grant_lease = min(grant_lease, evidence_lease)
                commit_evidence.append(
                    RegionalCoalitionCommitEvidence(
                        target_id=target_id,
                        coordinator_id=commit.coordinator_id,
                        epoch=int(ownership.epoch),
                        lease_expires_at_s=evidence_lease,
                        required_member_ids=tuple(commit.required_member_ids),
                        acked_member_ids=tuple(commit.acked_member_ids),
                        commit_required=bool(commit.commit_required),
                        state=commit.state,
                        atomic_committed=bool(commit.atomic_committed),
                        execution_authorized=bool(commit.execution_authorized),
                        coalition_id=coalition_id,
                        coalition_version=coalition_version,
                        metadata={
                            "d4_reason": commit.reason,
                            "formation_algorithm": commit.formation_algorithm,
                            "rejected_ack_reasons": tuple(
                                commit.rejected_ack_reasons
                            ),
                        },
                    )
                )
                grant_targets.append(target_id)
                assigned_by_target[target_id] = assigned_resource_ids
                covered_targets.add(target_id)

            commit_evidence = [
                replace(
                    evidence,
                    lease_expires_at_s=min(
                        float(evidence.lease_expires_at_s),
                        grant_lease,
                    ),
                )
                for evidence in commit_evidence
            ]
            grants.append(
                RegionalAuthorityGrant(
                    region_id=decision.region_id,
                    owner_layer=decision.selected_layer.value,
                    owner_node_id=str(ownership.owner_id),
                    owner_role=str(ownership.owner_role),
                    epoch=int(ownership.epoch),
                    source_plan_id=previous_plan.plan_id,
                    source_plan_version=previous_plan.version,
                    lease_expires_at_s=grant_lease,
                    target_ids=tuple(grant_targets),
                    assigned_resource_ids_by_target=assigned_by_target,
                    execution_allowed=True,
                    fail_closed=False,
                    coalition_commits=tuple(commit_evidence),
                    decision_reason=decision.reason,
                    metadata={
                        "d4_schema": frame.schema,
                        "d4_action": decision.action.value,
                        "d4_adjudicated_at_s": float(frame.timestamp_s),
                    },
                )
            )

        if covered_targets != executable_target_ids:
            raise RegionalPlanAuthorityError("regional_d4_target_set_incomplete")
        return RegionalAuthorityInput(
            adjudicated_at_s=float(frame.timestamp_s),
            grants=tuple(grants),
        )

    def _d3_tracks(self) -> tuple[TargetTrack, ...]:
        config = self._require_ready()
        if self.latest_d2_result is None:
            raise RuntimeError("D3 track adapter requires a D2 association result")
        commitment_by_track = self._d2_identity_commitments(
            self.latest_d2_result
        )
        usable = tuple(
            track
            for track in self.latest_d2_tracks
            if _enum_value(track.lifecycle_state) not in {"lost", "dropped"}
        )
        high_count = 0
        if config.metadata.get("demand_pattern") == "hybrid_2_primary_1_reserve":
            fraction = float(config.metadata.get("high_threat_fraction", 0.10))
            high_count = max(1, int(math.ceil(len(usable) * fraction))) if usable else 0
        output: list[TargetTrack] = []
        all_regions = _region_ids(config.region_count)
        local_only = _regional_resource_locality_enabled(config)
        for index, track in enumerate(sorted(usable, key=lambda item: item.global_track_id)):
            commitment = commitment_by_track[track.global_track_id]
            position = np.asarray(track.state[:3], dtype=float)
            region_id = _region_for_position(position, config.region_count)
            self._track_region_by_id[track.global_track_id] = region_id
            distance = float(np.linalg.norm(position[:2]))
            threat = float(
                np.clip(
                    1.0
                    - (distance - config.protected_radius_m)
                    / max(_EPS, config.world_half_extent_m - config.protected_radius_m),
                    0.05,
                    0.95,
                )
            )
            demand = None
            if index < high_count:
                threat = max(threat, 0.95)
                demand = TargetDemand(
                    required_resource_count=3,
                    primary_resource_count=2,
                    coordination_mode="hybrid",
                )
            covariance_trace = float(np.trace(track.covariance[:3, :3]))
            output.append(
                TargetTrack(
                    track_id=track.global_track_id,
                    threat_score=threat,
                    covariance=float(np.clip(covariance_trace / 100.0, 0.0, 1.0)),
                    window_cost=0.0,
                    assignable=True,
                    position_ned=tuple(float(value) for value in position),
                    velocity_ned=tuple(float(value) for value in track.state[3:]),
                    position_covariance_ned=track.covariance[:3, :3].copy(),
                    region_id=region_id,
                    candidate_resource_region_ids=(
                        (region_id,) if local_only else all_regions
                    ),
                    demand=demand,
                    identity_commitment_state=(
                        commitment.identity_commitment_state.value
                    ),
                    metadata={
                        "global_track_id_owner": "D2_center",
                        "lifecycle_state": _enum_value(track.lifecycle_state),
                        "track_quality": float(track.track_quality),
                        "identity_commitment": commitment.to_dict(),
                    },
                )
            )
        return tuple(output)

    def _d3_resources(
        self,
        navigation: PlatformNavigationBatch,
    ) -> tuple[ResourceState, ...]:
        config = self._require_ready()
        all_regions = _region_ids(config.region_count)
        local_only = _regional_resource_locality_enabled(config)
        resources: list[ResourceState] = []
        for index, resource_id in enumerate(navigation.platform_ids):
            active = bool(navigation.active[index])
            position = navigation.state_ned[index, :3]
            region_id = _region_for_position(position, config.region_count)
            resources.append(
                ResourceState(
                    resource_id=resource_id,
                    status="available" if active else "unavailable",
                    availability_score=1.0 if active else 0.0,
                    position_ned=tuple(float(value) for value in position),
                    velocity_ned=tuple(
                        float(value) for value in navigation.state_ned[index, 3:]
                    ),
                    position_covariance_ned=navigation.covariance[index, :3, :3].copy(),
                    max_speed_mps=config.interceptor_speed_mps,
                    # The square workspace diameter is 2*sqrt(2)*half_extent.
                    max_intercept_range_m=3.0 * config.world_half_extent_m,
                    region_id=region_id,
                    reachable_target_region_ids=(
                        (region_id,) if local_only else all_regions
                    ),
                    capability_class="intercept_visual",
                )
            )
        return tuple(resources)

    def _d4_snapshot(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
        center_health: C2Health,
        secondary_failed: bool,
    ) -> RegionalFailoverSnapshot:
        config = self._require_ready()
        plan = self.latest_plan
        scenario = RegionalScenarioMetadata.from_scalable_scenario(config.to_dict())
        regions = _region_definitions(scenario.region_ids)
        lease_expires_at = now + max(
            config.assignment_period_s * self.stack_config.assignment_lease_multiplier,
            config.region_policy_period_s,
        )
        snapshot_epoch = self._plan_authority_epoch(plan)
        if self._fault_generation_changed:
            # A new failure generation must advance the fencing epoch before D4
            # can move authority to a different layer or owner.
            snapshot_epoch = max(snapshot_epoch, int(plan.version))
        track_by_id = {
            track.global_track_id: track for track in self.latest_d2_tracks
        }
        d3_track_by_id = {
            track.track_id: track for track in self._d3_tracks()
        }
        assignments_by_target = plan.assignments_by_target()
        coalition_by_target = {
            coalition.target_id: coalition for coalition in plan.coalitions
        }
        tasks: list[RegionalTaskEvidence] = []
        task_target_ids = (
            tuple(sorted(d3_track_by_id))
            if _regional_resource_locality_enabled(config)
            else tuple(sorted(assignments_by_target))
        )
        for target_id in task_target_ids:
            assignments = assignments_by_target.get(target_id, ())
            track = track_by_id.get(target_id)
            if track is None:
                continue
            coalition = coalition_by_target.get(target_id)
            required_count = (
                coalition.required_resource_count
                if coalition is not None
                else (
                    assignments[0].required_resource_count
                    if assignments
                    else (
                        d3_track_by_id[target_id].demand.required_resource_count
                        if d3_track_by_id[target_id].demand is not None
                        else 1
                    )
                )
            )
            assigned_ids = tuple(item.resource_id for item in assignments)
            support_ids = tuple(
                resource_id
                for resource_id in assigned_ids
                if (resource_id, target_id) in self._latest_terminal_by_pair
            )
            terminal_applicable = self._terminal_applicable(
                target_id,
                assigned_ids,
                step_input.interceptors,
            )
            if not terminal_applicable:
                consistency = D5Consistency.NOT_APPLICABLE
            elif len(support_ids) == len(assigned_ids):
                consistency = D5Consistency.CONSISTENT
            else:
                consistency = D5Consistency.UNKNOWN
            tasks.append(
                RegionalTaskEvidence(
                    task_id=f"task:{target_id}",
                    global_track_id=target_id,
                    region_id=self._track_region_by_id.get(
                        target_id,
                        _region_for_position(track.state[:3], config.region_count),
                    ),
                    d3_plan_id=plan.plan_id,
                    d3_plan_version=plan.version,
                    d3_epoch=snapshot_epoch,
                    d3_lease_expires_at_s=lease_expires_at,
                    required_member_count=required_count,
                    required_capabilities=("intercept",),
                    d3_assigned_member_ids=assigned_ids,
                    coalition_id=(None if coalition is None else coalition.coalition_id),
                    coalition_version=(None if coalition is None else coalition.version),
                    d1_covariance_trace=float(np.trace(track.covariance[:3, :3])),
                    d1_measurement_age_s=max(0.0, now - float(track.last_update_time)),
                    d2_ambiguity_score=float(
                        0.0
                        if self.latest_d2_result is None
                        else self.latest_d2_result.ambiguity_score
                    ),
                    d2_id_switch_count=0,
                    d2_duplicate_track_count=0,
                    d3_is_current=True,
                    d3_resource_feasible=bool(assignments)
                    and all(
                        item.feasibility_state == "feasible"
                        for item in assignments
                    )
                    and self._regional_plan_rejection_reason is None,
                    d5_consistency=consistency,
                    d5_support_member_ids=support_ids,
                )
            )
        members = self._d4_members(
            step_input.interceptors,
            tuple(tasks),
            now=now,
            plan_version=plan.version,
            epoch=snapshot_epoch,
            partition_generation=step_input.communication_partition_generation,
        )
        secondaries = () if secondary_failed else self._d4_secondaries(
            step_input.recon,
            scenario.region_ids,
            now=now,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            epoch=snapshot_epoch,
            lease_expires_at=lease_expires_at,
            partition_generation=step_input.communication_partition_generation,
        )
        acks = self._d4_acks(
            tasks,
            step_input.interceptors,
            now,
            lease_expires_at,
            plan_version=plan.version,
            epoch=snapshot_epoch,
            partition_generation=step_input.communication_partition_generation,
        )
        return RegionalFailoverSnapshot(
            timestamp_s=now,
            scenario=scenario,
            center_health=center_health,
            center_node_id="d3_central",
            plan_id=plan.plan_id,
            plan_version=plan.version,
            epoch=snapshot_epoch,
            lease_expires_at_s=lease_expires_at,
            regions=regions,
            tasks=tuple(tasks),
            secondary_nodes=secondaries,
            fallback_members=members,
            coalition_acks=acks,
        )

    @staticmethod
    def _plan_authority_epoch(plan: Any) -> int:
        metadata = dict(plan.metadata)
        if bool(metadata.get("fault_authority_generation_fence", False)):
            return int(plan.version)
        for key in ("regional_max_epoch", "secondary_leader_epoch"):
            value = metadata.get(key)
            if value is not None:
                return int(value)
        return int(plan.version)

    def _d4_members(
        self,
        navigation: PlatformNavigationBatch,
        tasks: tuple[RegionalTaskEvidence, ...],
        *,
        now: float,
        plan_version: int,
        epoch: int,
        partition_generation: int,
    ) -> tuple[RegionalFallbackMember, ...]:
        config = self._require_ready()
        task_track = {
            task.task_id: next(
                track
                for track in self.latest_d2_tracks
                if track.global_track_id == task.global_track_id
            )
            for task in tasks
        }
        all_regions = _region_ids(config.region_count)
        members: list[RegionalFallbackMember] = []
        for index, resource_id in enumerate(navigation.platform_ids):
            delivery = self._d4_plan_deliveries.get(
                (
                    resource_id,
                    int(plan_version),
                    int(epoch),
                    int(partition_generation),
                )
            )
            if (
                delivery is None
                and self._fault_generation_changed
                and self._last_secondary_failed
            ):
                expected_targets = {
                    task.global_track_id
                    for task in tasks
                    if resource_id in task.d3_assigned_member_ids
                }
                bridged = tuple(
                    candidate
                    for key, candidate in self._d4_plan_deliveries.items()
                    if key[0] == resource_id
                    and key[1] == int(plan_version) - 1
                    and key[3] == int(partition_generation)
                    and {
                        str(item.get("global_track_id", ""))
                        for item in candidate.payload.get(
                            "member_assignments",
                            (),
                        )
                        if isinstance(item, Mapping)
                    }
                    == expected_targets
                )
                if bridged:
                    delivery = max(
                        bridged,
                        key=lambda item: (
                            item.receipt.arrival_timestamp_s
                        ),
                    )
            communication_ready = bool(
                delivery is not None
                and delivery.receipt.arrival_timestamp_s <= now + _EPS
                and delivery.receipt.lease_expires_at_s > now
                and now - delivery.receipt.arrival_timestamp_s
                <= self.stack_config.d4_communication_stale_after_s
            )
            scores: dict[str, float] = {}
            for task in tasks:
                distance = float(
                    np.linalg.norm(
                        navigation.state_ned[index, :3]
                        - task_track[task.task_id].state[:3]
                    )
                )
                assigned_bonus = 1_000.0 if resource_id in task.d3_assigned_member_ids else 0.0
                scores[task.task_id] = assigned_bonus - distance
            members.append(
                RegionalFallbackMember(
                    node_id=resource_id,
                    region_ids=all_regions,
                    capabilities=("intercept", "visual"),
                    task_bid_scores=scores,
                    available=bool(navigation.active[index]),
                    communication_ready=(
                        bool(navigation.active[index])
                        and communication_ready
                    ),
                    max_concurrent_tasks=1,
                )
            )
        return tuple(members)

    def _d4_secondaries(
        self,
        navigation: PlatformNavigationBatch,
        region_ids: tuple[str, ...],
        *,
        now: float,
        plan_id: str,
        plan_version: int,
        epoch: int,
        lease_expires_at: float,
        partition_generation: int,
    ) -> tuple[MobileReconSecondary, ...]:
        active_indices = [
            index for index, active in enumerate(navigation.active) if bool(active)
        ]
        if not active_indices:
            return ()
        output: list[MobileReconSecondary] = []
        for rank, index in enumerate(active_indices):
            node_id = navigation.platform_ids[index]
            covered_regions = tuple(
                region_id
                for region_index, region_id in enumerate(region_ids)
                if region_index % len(active_indices) == rank
            )
            readiness: dict[str, SecondaryReadinessEvidence] = {}
            for region_id in covered_regions:
                reception = self._d4_readiness_receptions.get(
                    (
                        node_id,
                        region_id,
                        int(plan_version),
                        int(epoch),
                        int(partition_generation),
                    )
                )
                if reception is None:
                    continue
                payload = reception.payload
                if str(payload.get("plan_id", "")) != str(plan_id):
                    continue
                receipt = reception.receipt
                sustained = bool(
                    reception.observation_count >= 3
                    and reception.last_arrival_s - reception.first_arrival_s
                    >= 0.20 - _EPS
                )
                generated = float(
                    payload.get(
                        "generated_timestamp_s",
                        receipt.sent_timestamp_s,
                    )
                )
                readiness[region_id] = SecondaryReadinessEvidence(
                    node_id=node_id,
                    current_time_s=now,
                    readiness_timestamp_s=float(
                        payload.get("readiness_timestamp_s", generated)
                    ),
                    readiness_stale_after_s=(
                        self.stack_config.d4_communication_stale_after_s
                    ),
                    availability_confirmed=bool(
                        navigation.active[index]
                        and payload.get("availability_confirmed", False)
                    ),
                    lease_epoch=receipt.epoch,
                    lease_expires_at_s=min(
                        receipt.lease_expires_at_s,
                        lease_expires_at,
                    ),
                    heartbeat_timestamp_s=float(
                        payload.get("heartbeat_timestamp_s", generated)
                    ),
                    heartbeat_stale_after_s=(
                        self.stack_config.d4_communication_stale_after_s
                    ),
                    cue_freshness_s=max(0.0, now - generated),
                    cue_stale_after_s=(
                        self.stack_config.d4_communication_stale_after_s
                    ),
                    gimbal_pointing_ok=bool(
                        payload.get("gimbal_pointing_ok", False)
                    ),
                    communication_received_timestamp_s=(
                        reception.last_arrival_s
                    ),
                    communication_stale_after_s=(
                        self.stack_config.d4_communication_stale_after_s
                    ),
                    coverage_matches_requested_cell=bool(
                        payload.get(
                            "coverage_matches_requested_cell",
                            False,
                        )
                    ),
                    coverage_ratio=float(
                        payload.get("coverage_ratio", 0.0)
                    ),
                    network_full_view_rate=float(
                        payload.get("network_full_view_rate", 0.0)
                    ),
                    takeover_ready_sustained=sustained,
                    takeover_ready_since_s=reception.first_arrival_s,
                    takeover_ready_observation_count=(
                        reception.observation_count
                    ),
                )
            output.append(
                MobileReconSecondary(
                    node_id=node_id,
                    readiness_by_region=readiness,
                    takeover_priority=rank,
                )
            )
        return tuple(output)

    def _d4_acks(
        self,
        tasks: Iterable[RegionalTaskEvidence],
        navigation: PlatformNavigationBatch,
        now: float,
        lease_expires_at: float,
        *,
        plan_version: int,
        epoch: int,
        partition_generation: int,
    ) -> tuple[CoalitionMemberAck, ...]:
        active_by_id = {
            resource_id: bool(navigation.active[index])
            for index, resource_id in enumerate(navigation.platform_ids)
        }
        acks: list[CoalitionMemberAck] = []
        for task in tasks:
            if task.required_member_count <= 1:
                continue
            for resource_id in task.d3_assigned_member_ids:
                delivery = self._d4_ack_deliveries.get(
                    (
                        resource_id,
                        task.global_track_id,
                        int(plan_version),
                        int(epoch),
                        int(partition_generation),
                    )
                )
                if delivery is None:
                    continue
                payload = delivery.payload
                receipt = delivery.receipt
                if (
                    receipt.lease_expires_at_s <= now
                    or float(payload.get("valid_until", 0.0)) <= now
                    or str(payload.get("coalition_id", ""))
                    != str(task.coalition_id)
                    or int(payload.get("coalition_version", -1))
                    != int(task.coalition_version or 0)
                ):
                    continue
                acks.append(
                    CoalitionMemberAck(
                        resource_id=resource_id,
                        global_track_id=task.global_track_id,
                        coalition_id=str(task.coalition_id),
                        coalition_version=int(task.coalition_version or 0),
                        plan_id=task.d3_plan_id,
                        plan_version=task.d3_plan_version,
                        epoch=task.d3_epoch,
                        can_execute=bool(
                            active_by_id.get(resource_id, False)
                            and payload.get("can_execute", False)
                        ),
                        evidence_timestamp=float(
                            payload.get(
                                "evidence_timestamp",
                                receipt.sent_timestamp_s,
                            )
                        ),
                        valid_until=min(
                            float(payload["valid_until"]),
                            receipt.lease_expires_at_s,
                            lease_expires_at,
                        ),
                        metadata={
                            "communication_receipt_id": receipt.receipt_id,
                            "communication_arrival_timestamp_s": (
                                receipt.arrival_timestamp_s
                            ),
                        },
                    )
                )
        return tuple(acks)

    def _terminal_applicable(
        self,
        target_id: str,
        resource_ids: Iterable[str],
        navigation: PlatformNavigationBatch,
    ) -> bool:
        track = next(
            (item for item in self.latest_d2_tracks if item.global_track_id == target_id),
            None,
        )
        if track is None:
            return False
        index_by_id = {
            resource_id: index
            for index, resource_id in enumerate(navigation.platform_ids)
        }
        ranges = [
            float(
                np.linalg.norm(
                    navigation.state_ned[index_by_id[resource_id], :3]
                    - track.state[:3]
                )
            )
            for resource_id in resource_ids
            if resource_id in index_by_id
        ]
        return bool(ranges and min(ranges) <= self.stack_config.terminal_switch_range_m)

    def _guidance_inputs(
        self,
        step_input: RuntimeStepInput,
        now: float,
    ) -> tuple[AssignmentPairGuidanceInput3D, ...]:
        track_by_id = {
            track.global_track_id: track for track in self.latest_d2_tracks
        }
        committed_target_ids = self._committed_d2_target_ids()
        output: list[AssignmentPairGuidanceInput3D] = []
        for binding in self.latest_bindings:
            resource_index = self._resource_index_by_id.get(binding.resource_id)
            track = track_by_id.get(binding.assigned_global_track_id)
            if (
                resource_index is None
                or track is None
                or binding.assigned_global_track_id
                not in committed_target_ids
            ):
                continue
            association_visual = self._latest_terminal_by_pair.get(
                (binding.resource_id, binding.assigned_global_track_id)
            )
            association = None if association_visual is None else association_visual[0]
            visual = None if association_visual is None else association_visual[1]
            permission = self._d4_permission(binding.assigned_global_track_id)
            output.append(
                AssignmentPairGuidanceInput3D(
                    resource_index=resource_index,
                    resource_state=step_input.interceptors.state_ned[resource_index],
                    global_track=track,
                    binding=binding,
                    d4_permission=permission,
                    terminal_association=association,
                    active_plan_id=self.latest_plan.plan_id,
                    active_plan_version=self.latest_plan.version,
                    timestamp_s=now,
                    visual_observation=visual,
                    camera_recognition_ready=visual is not None,
                    available_accel_mps2=self.d7.config.max_accel_mps2,
                )
            )
        return tuple(output)

    def _d4_permission(self, target_id: str) -> D4GuidancePermission:
        if self.latest_d4_decision is None:
            return D4GuidancePermission(
                action="hold_for_review",
                reason="d4_decision_missing",
                requires_human_review=True,
            )
        region_id = self._track_region_by_id.get(target_id)
        decision = next(
            (
                item
                for item in self.latest_d4_decision.region_decisions
                if item.region_id == region_id
            ),
            None,
        )
        if decision is None or not decision.execution_allowed:
            return D4GuidancePermission(
                action="hold_for_review",
                mode="hold",
                reason=("region_decision_missing" if decision is None else decision.reason),
                requires_human_review=True,
            )
        assignment = next(
            (
                item
                for item in self.latest_plan.assignments
                if item.target_id == target_id
            ),
            None,
        )
        if assignment is None:
            return D4GuidancePermission(
                action="hold_for_review",
                reason="d3_target_assignment_missing",
                requires_human_review=True,
            )
        task_commit = next(
            (
                commit
                for commit in decision.coalition_commits
                if commit.global_track_id == target_id
            ),
            None,
        )
        required_count = int(assignment.required_resource_count)
        commit_required = required_count > 1
        if commit_required and (
            task_commit is None
            or not task_commit.commit_required
            or not task_commit.execution_authorized
        ):
            return D4GuidancePermission(
                action="hold_for_review",
                mode=decision.selected_layer.value,
                reason="d4_atomic_coalition_commit_missing",
                requires_human_review=True,
            )

        if decision.selected_layer in {
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.DISTRIBUTED,
        }:
            mismatch = self._fallback_plan_mismatch_reason(
                assignment,
                decision,
                region_id=str(region_id),
            )
            if mismatch:
                return D4GuidancePermission(
                    action="hold_for_review",
                    mode=decision.selected_layer.value,
                    reason=mismatch,
                    requires_human_review=True,
                )
            commit_fields = self._guidance_commit_fields(
                target_id,
                task_commit,
                commit_required=commit_required,
                assignment=assignment,
            )
            return D4GuidancePermission(
                action="continue",
                mode=decision.selected_layer.value,
                reason=decision.reason,
                target_node_id=str(decision.ownership.owner_id),
                terminal_consistent=True,
                new_plan_id=self.latest_plan.plan_id,
                new_plan_version=self.latest_plan.version,
                secondary_capability_class=(
                    "mobile_high_recon"
                    if decision.selected_layer is RegionalAuthorityLayer.SECONDARY
                    else None
                ),
                secondary_readiness_class=(
                    "takeover_ready"
                    if decision.selected_layer is RegionalAuthorityLayer.SECONDARY
                    else None
                ),
                visual_png_allowed=True,
                center_available=False,
                metadata={
                    "required_resource_count": required_count,
                    "commit_required": commit_required,
                    "regional_region_id": region_id,
                    "regional_owner_layer": decision.selected_layer.value,
                    "regional_owner_node_id": decision.ownership.owner_id,
                    "regional_epoch": decision.ownership.epoch,
                },
                **commit_fields,
            )

        if decision.selected_layer is not RegionalAuthorityLayer.CENTER:
            return D4GuidancePermission(
                action="hold_for_review",
                mode=decision.selected_layer.value,
                reason="d4_region_not_executable",
                requires_human_review=True,
            )
        action = decision.action.value
        if action not in {
            RegionalAction.CONTINUE_CENTER.value,
            RegionalAction.REQUEST_SECONDARY_ASSIST.value,
        }:
            return D4GuidancePermission(
                action="hold_for_review",
                reason=decision.reason,
                requires_human_review=True,
            )
        commit_fields = self._guidance_commit_fields(
            target_id,
            task_commit,
            commit_required=commit_required,
            assignment=assignment,
        )
        return D4GuidancePermission(
            action=action,
            reason=decision.reason,
            terminal_consistent=True,
            new_plan_id=self.latest_plan.plan_id,
            new_plan_version=self.latest_plan.version,
            visual_png_allowed=True,
            center_available=True,
            metadata={
                "required_resource_count": required_count,
                "commit_required": commit_required,
            },
            **commit_fields,
        )

    def _fallback_plan_mismatch_reason(
        self,
        assignment: Any,
        decision: Any,
        *,
        region_id: str,
    ) -> str:
        plan = self.latest_plan
        ownership = decision.ownership
        if (
            ownership.plan_id != plan.plan_id
            or ownership.plan_version != plan.version
        ):
            return "regional_d4_plan_version_mismatch"
        plan_owner = str(plan.metadata.get("active_plan_owner", "center"))
        assignment_metadata = dict(assignment.metadata)
        if plan_owner == "regional":
            if (
                str(assignment_metadata.get("regional_owner_layer", ""))
                != decision.selected_layer.value
            ):
                return "regional_owner_layer_mismatch"
            if str(assignment_metadata.get("regional_region_id", "")) != region_id:
                return "regional_owner_region_mismatch"
            owner_node_id = str(assignment_metadata.get("owner_node_id", ""))
            if owner_node_id != str(ownership.owner_id):
                return "regional_owner_node_mismatch"
            if int(assignment_metadata.get("regional_epoch", -1)) != int(
                ownership.epoch
            ):
                return "regional_owner_epoch_mismatch"
            lease = float(
                assignment_metadata.get("regional_lease_expires_at_s", -math.inf)
            )
        elif (
            plan_owner == "secondary"
            and decision.selected_layer is RegionalAuthorityLayer.SECONDARY
        ):
            owner_node_id = str(plan.metadata.get("owner_node_id", ""))
            if owner_node_id != str(ownership.owner_id):
                return "secondary_owner_plan_mismatch"
            if int(plan.metadata.get("secondary_leader_epoch", -1)) != int(
                ownership.epoch
            ):
                return "secondary_owner_epoch_mismatch"
            lease = float(
                plan.metadata.get("secondary_lease_expires_at_s", -math.inf)
            )
        else:
            return "fallback_plan_not_yet_reissued_by_d3"
        if float(self.latest_d4_decision.timestamp_s) >= lease:
            return "regional_plan_lease_expired"
        if float(self.latest_d4_decision.timestamp_s) >= float(
            ownership.lease_expires_at_s
        ):
            return "regional_d4_lease_expired"
        return ""

    def _guidance_commit_fields(
        self,
        target_id: str,
        task_commit: Any | None,
        *,
        commit_required: bool,
        assignment: Any,
    ) -> dict[str, Any]:
        coalition_id = _coalition_id_for(self.latest_plan, target_id)
        coalition_version = _coalition_version_for(self.latest_plan, target_id)
        coalition_epoch = _coalition_epoch_for(self.latest_plan, target_id)
        if task_commit is None:
            return {
                "coalition_id": coalition_id,
                "coalition_version": coalition_version,
                "atomic_coalition_formed": None,
                "coalition_commit_state": None,
                "coalition_epoch": coalition_epoch,
            }
        lease_values = [float(task_commit.lease_expires_at_s)]
        assignment_lease = assignment.metadata.get("regional_lease_expires_at_s")
        if assignment_lease is not None:
            lease_values.append(float(assignment_lease))
        secondary_lease = self.latest_plan.metadata.get(
            "secondary_lease_expires_at_s"
        )
        if secondary_lease is not None:
            lease_values.append(float(secondary_lease))
        effective_lease = min(lease_values)
        return {
            "coalition_id": coalition_id,
            "coalition_version": coalition_version,
            "atomic_coalition_formed": (
                bool(task_commit.atomic_committed) if commit_required else None
            ),
            "coalition_commit_state": task_commit.state,
            "coalition_epoch": coalition_epoch,
            "coalition_lease_expires_at_s": effective_lease,
            "coalition_required_member_ids": tuple(
                task_commit.required_member_ids
            ),
            "coalition_acked_member_ids": tuple(task_commit.acked_member_ids),
            "commit_plan_id": self.latest_plan.plan_id,
            "commit_plan_version": self.latest_plan.version,
            "commit_coalition_id": coalition_id,
            "commit_coalition_version": coalition_version,
        }

    def _terminal_pairs_from_d5(
        self,
        result: Any,
    ) -> dict[tuple[str, str], tuple[dict[str, Any], TerminalVisualObservation3D]]:
        graph = result.association.graph
        cluster_by_key = {
            cluster.cluster_key: cluster for cluster in result.association.clusters
        }
        geometry_by_key = {
            geometry.camera_key: geometry for geometry in result.camera_geometries
        }
        output: dict[
            tuple[str, str], tuple[dict[str, Any], TerminalVisualObservation3D]
        ] = {}
        for binding in result.association.bindings:
            if binding.decision_state != "bound" or binding.global_track_id is None:
                continue
            cluster = cluster_by_key[binding.cluster_key]
            for node_index in cluster.node_indices:
                tracklet = graph.nodes[node_index]
                if tracklet.resource_id not in self._resource_index_by_id:
                    continue
                geometry = geometry_by_key.get(tracklet.camera_key)
                if geometry is None or tracklet.bbox_xyxy is None:
                    continue
                confidence = float(
                    np.clip(
                        tracklet.confidence
                        * math.exp(-max(0.0, float(binding.cost or 0.0)) / 6.0),
                        0.0,
                        1.0,
                    )
                )
                association = {
                    "assigned_global_track_id": binding.global_track_id,
                    "local_track_id": tracklet.local_track_id,
                    "association_confidence": confidence,
                    "friend_conflict_state": "none",
                    "decision_state": "locked",
                    "assignment_version": (
                        None if self.latest_plan is None else self.latest_plan.version
                    ),
                    "plan_id": None if self.latest_plan is None else self.latest_plan.plan_id,
                    "plan_version": (
                        None if self.latest_plan is None else self.latest_plan.version
                    ),
                    "resource_id": tracklet.resource_id,
                    "metadata": {
                        "source": "d5_scalable_3d_sparse_graph",
                        "cross_view_support_count": len(cluster.node_indices),
                        "probability_source": result.association.probability_source,
                    },
                }
                camera = geometry.camera
                visual = TerminalVisualObservation3D(
                    timestamp_s=tracklet.measurement_timestamp,
                    bbox_xyxy=tracklet.bbox_xyxy,
                    image_width_px=int(camera.image_size[0]),
                    image_height_px=int(camera.image_size[1]),
                    camera_intrinsics=camera.K,
                    camera_to_ned_rotation=camera.R.T,
                    detection_confidence=tracklet.confidence,
                    local_track_id=tracklet.local_track_id,
                    assigned_global_track_id=binding.global_track_id,
                    camera_id=tracklet.camera_id,
                )
                output[(tracklet.resource_id, binding.global_track_id)] = (
                    association,
                    visual,
                )
        return output

    def _evaluate_d5_shadow_scoring(
        self,
        now: float,
    ) -> dict[str, Any] | None:
        """Score the frozen D5 graph without changing clusters or bindings."""

        if self.d5_shadow_edge_model is None:
            return None
        if self.latest_d5_result is None:
            raise RuntimeError("D5 shadow scoring requires a D5 result")
        association = self.latest_d5_result.association
        graph = association.graph
        diagnostics = dict(
            self.learning_runtime_diagnostics.get("d5", {})
        )
        self._d5_shadow_scoring_frame_count += 1
        base = {
            "schema_version": "scalable3d-d5-g1-shadow-scoring-v1",
            "timestamp": float(now),
            "authorization_id": diagnostics.get(
                "experiment_authorization_id"
            ),
            "authorization_sha256": diagnostics.get(
                "experiment_authorization_sha256"
            ),
            "authorization_expires_at_utc": diagnostics.get(
                "experiment_authorization_expires_at_utc"
            ),
            "model_fingerprint": diagnostics.get("model_fingerprint"),
            "graph_node_count": int(graph.node_count),
            "graph_edge_count": int(graph.edge_count),
            "online_probability_source": association.probability_source,
            "model_output_applied": False,
            "global_track_id_authority": False,
            "assignment_authority": False,
            "failover_authority": False,
            "control_authority": False,
        }

        def reject(reason: str, *, latency_ms: float | None = None) -> dict[str, Any]:
            self._d5_shadow_scoring_rejected_count += 1
            self._d5_shadow_scoring_rejection_reasons[reason] += 1
            return {
                **base,
                "status": "rejected",
                "rejection_reason": reason,
                "inference_latency_ms": latency_ms,
                "decision_threshold": None,
                "probabilities_sha256": None,
                "edge_scores": [],
            }

        if diagnostics.get("effective_mode") != "authorized_shadow":
            return reject("runtime_mode_not_authorized_shadow")
        if diagnostics.get("experiment_authorization_valid") is not True:
            return reject("experiment_authorization_not_valid")
        if diagnostics.get("model_output_applied") is not False:
            return reject("model_output_application_not_closed")
        if association.probability_source != "deterministic_geometry_rule":
            return reject("online_association_not_rule_authoritative")
        if getattr(self.d5_shadow_edge_model, "available", False) is not True:
            return reject(
                str(
                    getattr(
                        self.d5_shadow_edge_model,
                        "failure_reason",
                        "shadow_model_unavailable",
                    )
                )
            )

        binding_signature = tuple(
            (
                item.cluster_key,
                item.global_track_id,
                item.decision_state,
                item.cost,
                tuple(item.supporting_tracklet_keys),
            )
            for item in association.bindings
        )
        started = perf_counter()
        try:
            raw = self.d5_shadow_edge_model.forward_graph(graph)
            if hasattr(raw, "detach") and callable(raw.detach):
                raw = raw.detach().cpu().numpy()
            probabilities = np.asarray(raw, dtype=float).reshape(-1)
        except Exception as exc:
            latency_ms = (perf_counter() - started) * 1_000.0
            self._record_timing(
                "d5_g1_shadow_scoring",
                latency_ms / 1_000.0,
            )
            return reject(
                f"model_error:{type(exc).__name__}",
                latency_ms=latency_ms,
            )
        latency_ms = (perf_counter() - started) * 1_000.0
        self._record_timing("d5_g1_shadow_scoring", latency_ms / 1_000.0)
        if probabilities.shape != (graph.edge_count,):
            return reject(
                "model_output_shape_mismatch",
                latency_ms=latency_ms,
            )
        if not np.all(np.isfinite(probabilities)):
            return reject(
                "model_output_non_finite",
                latency_ms=latency_ms,
            )
        if np.any((probabilities < 0.0) | (probabilities > 1.0)):
            return reject(
                "model_output_out_of_range",
                latency_ms=latency_ms,
            )
        if latency_ms > float(self.d5.config.model_inference_timeout_ms):
            return reject(
                "model_inference_timeout",
                latency_ms=latency_ms,
            )
        if tuple(
            (
                item.cluster_key,
                item.global_track_id,
                item.decision_state,
                item.cost,
                tuple(item.supporting_tracklet_keys),
            )
            for item in association.bindings
        ) != binding_signature:
            raise RuntimeError(
                "D5 shadow scoring mutated the online association result"
            )
        threshold = float(
            getattr(
                self.d5_shadow_edge_model,
                "decision_threshold",
                self.d5.config.edge_probability_threshold,
            )
        )
        if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            return reject(
                "model_decision_threshold_invalid",
                latency_ms=latency_ms,
            )
        probability_bytes = probabilities.astype(
            "<f8",
            copy=False,
        ).tobytes(order="C")
        edge_scores = [
            {
                "source_tracklet_key": edge.source_tracklet_key,
                "target_tracklet_key": edge.target_tracklet_key,
                "probability": float(probability),
            }
            for edge, probability in zip(
                graph.edges,
                probabilities,
                strict=True,
            )
        ]
        self._d5_shadow_scoring_success_count += 1
        self._d5_shadow_scoring_edge_count += int(graph.edge_count)
        return {
            **base,
            "status": "scored",
            "rejection_reason": None,
            "inference_latency_ms": latency_ms,
            "decision_threshold": threshold,
            "probabilities_sha256": hashlib.sha256(
                probability_bytes
            ).hexdigest(),
            "edge_scores": edge_scores,
        }

    def _fault_state(self, now: float) -> tuple[C2Health, bool]:
        config = self._require_ready()
        center = C2Health.NORMAL
        secondary_failed = False
        schedule = config.metadata.get("fault_schedule", ())
        for raw in schedule if isinstance(schedule, (list, tuple)) else ():
            if not isinstance(raw, Mapping) or float(raw.get("time_s", math.inf)) > now:
                continue
            component = str(raw.get("component", "")).lower()
            action = str(raw.get("action", "")).lower()
            if component == "center":
                center = {
                    "normal": C2Health.NORMAL,
                    "degraded": C2Health.DEGRADED,
                    "suspect": C2Health.SUSPECT,
                    "failed": C2Health.FAILED,
                }.get(action, center)
            elif component == "secondary" and action == "failed":
                secondary_failed = True
        return center, secondary_failed

    def _d1_centroid_overlay_shadow_publication(
        self,
        *,
        canonical_tracks: tuple[Any, ...],
        evidence_items: tuple[Any, ...],
        disposition: ExperimentalCentroidEvidenceDisposition,
        publication_timestamp: float,
        posterior_generation: int | None,
    ) -> RuntimePublication:
        """Evaluate a detached D1 publication overlay without feeding consumers."""

        if (
            not self.stack_config
            .d1_centroid_publication_overlay_shadow_enabled
        ):
            raise RuntimeError("D1 centroid overlay shadow is disabled")
        if posterior_generation is None:
            raise ValueError(
                "D1 centroid overlay shadow requires a materialized posterior"
            )

        started = perf_counter()
        phase_wall_time_s: dict[str, float] = {}
        revision = (
            f"{self._d1_publisher_epoch}:posterior:"
            f"{int(posterior_generation):08d}"
        )
        publication_id = (
            "main-d1-centroid-overlay-shadow:"
            f"{self._d1_publisher_epoch}:"
            f"{int(posterior_generation):08d}"
        )
        phase_started = perf_counter()
        before_surface = self._d1_centroid_overlay_forbidden_surface(
            canonical_tracks,
            evidence_items,
        )
        canonical_before_bytes = _d1_shadow_canonical_json_bytes(
            before_surface["canonical_tracks"]
        )
        evidence_before_bytes = _d1_shadow_canonical_json_bytes(
            before_surface["structural_ambiguity_evidence"]
        )
        canonical_before_sha256 = _d1_shadow_sha256_bytes(
            canonical_before_bytes
        )
        canonical_track_payload_bytes = len(canonical_before_bytes)
        evidence_before_sha256 = _d1_shadow_sha256_bytes(
            evidence_before_bytes
        )
        before_surface_sha256 = _d1_shadow_sha256(
            {
                "canonical_tracks_sha256": canonical_before_sha256,
                "structural_ambiguity_evidence_sha256": (
                    evidence_before_sha256
                ),
            }
        )
        del before_surface, canonical_before_bytes, evidence_before_bytes
        phase_wall_time_s["forbidden_surface_before_digest"] = (
            perf_counter() - phase_started
        )

        evaluation_error: str | None = None
        atomic_result = None
        try:
            phase_started = perf_counter()
            try:
                atomic_result = (
                    run_experimental_centroid_publication_overlay_atomically(
                        canonical_tracks,
                        evidence_items,
                        state=self._d1_centroid_overlay_shadow_state,
                        disposition=disposition,
                        base_publication_revision=revision,
                        overlay_valid_for_publication_id=publication_id,
                    )
                )
            finally:
                phase_wall_time_s["atomic_overlay_operation"] = (
                    perf_counter() - phase_started
                )
            evaluation = atomic_result.evaluation
            shadow_tracks = (
                canonical_tracks
                if atomic_result.shadow_tracks is None
                else atomic_result.shadow_tracks
            )
            if atomic_result.atomic_failure_reason is not None:
                evaluation_error = (
                    "RuntimeError:"
                    f"{atomic_result.atomic_failure_reason[:240]}"
                )
        except (
            FloatingPointError,
            RuntimeError,
            TypeError,
            ValueError,
            np.linalg.LinAlgError,
        ) as exc:
            evaluation = None
            shadow_tracks = canonical_tracks
            evaluation_error = (
                f"{type(exc).__name__}:{str(exc)[:240]}"
            )

        phase_started = perf_counter()
        after_surface = self._d1_centroid_overlay_forbidden_surface(
            canonical_tracks,
            evidence_items,
        )
        canonical_after_bytes = _d1_shadow_canonical_json_bytes(
            after_surface["canonical_tracks"]
        )
        evidence_after_bytes = _d1_shadow_canonical_json_bytes(
            after_surface["structural_ambiguity_evidence"]
        )
        canonical_after_sha256 = _d1_shadow_sha256_bytes(
            canonical_after_bytes
        )
        evidence_after_sha256 = _d1_shadow_sha256_bytes(
            evidence_after_bytes
        )
        after_surface_sha256 = _d1_shadow_sha256(
            {
                "canonical_tracks_sha256": canonical_after_sha256,
                "structural_ambiguity_evidence_sha256": (
                    evidence_after_sha256
                ),
            }
        )
        del after_surface, canonical_after_bytes, evidence_after_bytes
        phase_wall_time_s["forbidden_surface_after_digest"] = (
            perf_counter() - phase_started
        )
        forbidden_mutation_detected = (
            canonical_before_sha256 != canonical_after_sha256
            or evidence_before_sha256 != evidence_after_sha256
        )
        if forbidden_mutation_detected:
            self._d1_centroid_overlay_shadow_forbidden_mutation_count += 1
            raise RuntimeError(
                "D1 centroid overlay shadow mutated a forbidden canonical surface"
            )

        decisions = (
            ()
            if evaluation is None
            else tuple(evaluation.decisions)
        )
        if (
            evaluation_error is None
            and any(item.decision == "accepted" for item in decisions)
            and shadow_tracks is canonical_tracks
        ):
            evaluation_error = (
                "RuntimeError:accepted_overlay_not_materialized"
            )
        if evaluation is not None:
            self._d1_centroid_overlay_shadow_state = evaluation.next_state
        phase_started = perf_counter()
        if shadow_tracks is canonical_tracks:
            shadow_sha256 = canonical_after_sha256
            shadow_track_payload_bytes = canonical_track_payload_bytes
        else:
            shadow_payload = [track.to_dict() for track in shadow_tracks]
            shadow_payload_bytes = _d1_shadow_canonical_json_bytes(
                shadow_payload
            )
            shadow_sha256 = _d1_shadow_sha256_bytes(
                shadow_payload_bytes
            )
            shadow_track_payload_bytes = len(shadow_payload_bytes)
        phase_wall_time_s["shadow_payload_digest"] = (
            perf_counter() - phase_started
        )
        canonical_global_track_ids = [
            str(track.global_track_id) for track in canonical_tracks
        ]
        shadow_global_track_ids = [
            str(track.global_track_id) for track in shadow_tracks
        ]
        accepted = sum(item.decision == "accepted" for item in decisions)
        rejected = sum(item.decision == "rejected" for item in decisions)
        rejection_reasons = Counter(
            str(item.reject_reason)
            for item in decisions
            if item.reject_reason is not None
        )
        self._d1_centroid_overlay_shadow_evaluation_count += 1
        self._d1_centroid_overlay_shadow_decision_count += len(decisions)
        self._d1_centroid_overlay_shadow_accepted_count += accepted
        self._d1_centroid_overlay_shadow_rejected_count += rejected
        self._d1_centroid_overlay_shadow_rejection_reasons.update(
            rejection_reasons
        )
        if evaluation_error is not None:
            self._d1_centroid_overlay_shadow_error_count += 1
        watermark_count = len(
            self._d1_centroid_overlay_shadow_state.watermarks
        )
        self._d1_centroid_overlay_shadow_max_watermark_count = max(
            self._d1_centroid_overlay_shadow_max_watermark_count,
            watermark_count,
        )
        self._d1_centroid_overlay_shadow_max_payload_bytes = max(
            self._d1_centroid_overlay_shadow_max_payload_bytes,
            shadow_track_payload_bytes,
        )
        prepared_integrity_check = (
            None
            if atomic_result is None
            else atomic_result.post_integrity_check.to_dict()
        )
        phase_started = perf_counter()
        payload = {
                "timestamp": float(publication_timestamp),
                "posterior_generation": int(posterior_generation),
                "status": "offline_shadow_not_consumed",
                "overlay_execution_mode": (
                    "atomic_experimental_offline_v1"
                ),
                "base_publication_revision": revision,
                "overlay_valid_for_publication_id": publication_id,
                "canonical_track_count": len(canonical_tracks),
                "shadow_track_count": len(shadow_tracks),
                "evidence_count": len(evidence_items),
                "decision_count": len(decisions),
                "accepted_count": accepted,
                "rejected_count": rejected,
                "rejection_reason_counts": dict(
                    sorted(rejection_reasons.items())
                ),
                "evaluation_error": evaluation_error,
                "canonical_preparation": {
                    "prepared_publication": (
                        None
                        if atomic_result is None
                        else atomic_result.prepared_publication.to_dict()
                    ),
                    "post_integrity_check": prepared_integrity_check,
                    "canonical_publication_digest": (
                        None
                        if atomic_result is None
                        else atomic_result.canonical_publication_digest
                    ),
                    "shadow_publication_digest": (
                        None
                        if atomic_result is None
                        else atomic_result.shadow_publication_digest
                    ),
                    "shadow_materialized": (
                        False
                        if atomic_result is None
                        else atomic_result.shadow_materialized
                    ),
                    "work": (
                        None
                        if atomic_result is None
                        else atomic_result.work.to_dict()
                    ),
                    "atomic_failure_reason": (
                        None
                        if atomic_result is None
                        else atomic_result.atomic_failure_reason
                    ),
                },
                "canonical_tracks_sha256": canonical_before_sha256,
                "shadow_tracks_sha256": shadow_sha256,
                "shadow_differs_from_canonical": (
                    shadow_sha256 != canonical_before_sha256
                ),
                "canonical_global_track_ids_sha256": _d1_shadow_sha256(
                    canonical_global_track_ids
                ),
                "shadow_global_track_ids_sha256": _d1_shadow_sha256(
                    shadow_global_track_ids
                ),
                "global_track_id_sequence_unchanged": (
                    canonical_global_track_ids == shadow_global_track_ids
                ),
                "decisions": [item.to_dict() for item in decisions],
                "forbidden_mutation_audit": {
                    "digest_semantics": (
                        "sha256_of_canonical_track_and_evidence_digest_manifest_v1"
                    ),
                    "before_sha256": before_surface_sha256,
                    "after_sha256": after_surface_sha256,
                    "canonical_tracks_before_sha256": (
                        canonical_before_sha256
                    ),
                    "canonical_tracks_after_sha256": (
                        canonical_after_sha256
                    ),
                    "structural_ambiguity_evidence_before_sha256": (
                        evidence_before_sha256
                    ),
                    "structural_ambiguity_evidence_after_sha256": (
                        evidence_after_sha256
                    ),
                    "passed": not forbidden_mutation_detected,
                    "filter_adapter_reference_passed_to_prototype": False,
                    "history_reference_passed_to_prototype": False,
                    "checkpoint_reference_passed_to_prototype": False,
                    "replay_cache_reference_passed_to_prototype": False,
                    "scan_watermark_reference_passed_to_prototype": False,
                    "canonical_business_tracks_replaced": False,
                    "d2_consumption_count": 0,
                    "d3_consumption_count": 0,
                },
                "bounded_memory_audit": {
                    "generation_watermark_count": watermark_count,
                    "generation_watermark_capacity": int(
                        self._d1_centroid_overlay_shadow_state.max_entries
                    ),
                    "shadow_track_payload_bytes": shadow_track_payload_bytes,
                },
                "measurement_timestamps": sorted(
                    {
                        float(item.measurement_timestamp)
                        for item in evidence_items
                    }
                ),
                "arrival_timestamps": sorted(
                    {
                        float(item.arrival_timestamp)
                        for item in evidence_items
                    }
                ),
                "online_truth_use_count": 0,
            }
        phase_wall_time_s["audit_log_materialization"] = (
            perf_counter() - phase_started
        )
        evaluation_wall_time_s = perf_counter() - started
        payload["phase_wall_time_ms"] = {
            name: 1_000.0 * seconds
            for name, seconds in sorted(phase_wall_time_s.items())
        }
        payload["evaluation_wall_time_ms"] = (
            1_000.0 * evaluation_wall_time_s
        )
        for phase_name, elapsed_s in phase_wall_time_s.items():
            self._record_timing(
                (
                    "d1_centroid_publication_overlay_shadow."
                    f"{phase_name}"
                ),
                elapsed_s,
            )
        self._record_timing(
            "d1_centroid_publication_overlay_shadow",
            evaluation_wall_time_s,
        )

        return RuntimePublication(
            topic="audit.d1.centroid_publication_overlay_shadow",
            source="main",
            schema_version="scalable3d-d1-centroid-overlay-shadow-v1",
            payload=payload,
            copy_payload=False,
        )

    def _d1_centroid_overlay_forbidden_surface(
        self,
        canonical_tracks: tuple[Any, ...],
        evidence_items: tuple[Any, ...],
    ) -> dict[str, Any]:
        """Hash every canonical surface reachable by the shadow prototype."""

        return {
            "canonical_tracks": [
                track.to_dict() for track in canonical_tracks
            ],
            "structural_ambiguity_evidence": [
                item.to_dict() for item in evidence_items
            ],
        }

    def _d1_publication(
        self,
        result: Any,
        batch: Any,
        now: float,
        *,
        evidence_by_observation: Mapping[str, Any] | None = None,
        posterior_generation: int | None = None,
    ) -> RuntimePublication:
        if evidence_by_observation is None:
            evidence_by_observation = {
                item.observation_id: item
                for item in self.d1.consistency_evidence_snapshot()
            }
        tracks_materialized = bool(
            getattr(result, "tracks_materialized", True)
        )
        tracks = tuple(result.tracks) if tracks_materialized else ()
        current_track_count = (
            len(tracks)
            if tracks_materialized
            else int(getattr(result, "current_track_count"))
        )
        structural_ambiguity_evidence = tuple(
            getattr(result, "structural_ambiguity_evidence", ())
        )
        source_observations = tuple(
            getattr(batch, "measurements", getattr(batch, "observations", ()))
        )
        source_observation_ids = {
            str(measurement.observation_id) for measurement in source_observations
        }
        observation_timestamps = {
            str(measurement.observation_id): float(
                measurement.measurement_timestamp
            )
            for measurement in source_observations
        }
        for track in tracks:
            metadata = getattr(track, "metadata", {})
            observation_id = str(
                metadata.get("latest_observation_id", "")
                if isinstance(metadata, Mapping)
                else ""
            ).strip()
            if not observation_id or observation_id in observation_timestamps:
                continue
            evidence = evidence_by_observation.get(observation_id)
            observation_timestamps[observation_id] = float(
                getattr(track, "timestamp", now)
                if evidence is None
                else evidence.measurement_timestamp
            )

        d1_track_id_by_observation: dict[str, str] = {}
        for observation_id in source_observation_ids:
            evidence = evidence_by_observation.get(observation_id)
            if evidence is None or evidence.source_global_track_id is None:
                continue
            d1_track_id_by_observation[observation_id] = str(
                evidence.source_global_track_id
            )
        for track in tracks:
            metadata = getattr(track, "metadata", {})
            if not isinstance(metadata, Mapping):
                continue
            observation_id = str(metadata.get("latest_observation_id", "")).strip()
            d1_track_id = str(getattr(track, "global_track_id", "")).strip()
            if observation_id in source_observation_ids and d1_track_id:
                d1_track_id_by_observation[observation_id] = d1_track_id

        observation_lineage = []
        for observation_id, measurement_timestamp in observation_timestamps.items():
            evidence = evidence_by_observation.get(observation_id)
            lineage = (
                (observation_id,)
                if evidence is None
                else _lineage_ending_in_observation(
                    evidence.source_lineage,
                    observation_id,
                )
            )
            replay_generation = (
                self._d2_observation_replay_generation.get(
                    observation_id,
                    -1,
                )
                + 1
            )
            lineage_record = {
                "observation_id": observation_id,
                "measurement_timestamp": float(measurement_timestamp),
                "source_lineage": list(lineage),
                "replay_generation": replay_generation,
            }
            observation_lineage.append(lineage_record)
            self._d1_latest_lineage_by_observation[observation_id] = dict(
                lineage_record
            )
            d1_track_id = d1_track_id_by_observation.get(observation_id)
            if d1_track_id is not None:
                self._d1_pending_lineage_by_track.setdefault(
                    d1_track_id,
                    {},
                )[observation_id] = dict(lineage_record)
        return RuntimePublication(
            topic="modules.d1.fused_tracks",
            source="D1",
            schema_version="d1-scalable3d-fusion-v1",
            payload={
                "timestamp": now,
                "batch_id": str(
                    getattr(batch, "batch_id", getattr(batch, "scan_id", ""))
                ),
                "sensor_id": batch.sensor_id,
                # Schema v1 consumers define track_count as the serialized
                # track-array length.  State-only records therefore expose the
                # live inventory separately instead of pretending an empty
                # array is a full snapshot.
                "track_count": len(tracks),
                "current_track_count": current_track_count,
                "tracks_materialized": tracks_materialized,
                "posterior_generation": posterior_generation,
                "snapshot_kind": (
                    "full_posterior" if tracks_materialized else "state_update"
                ),
                "tracks": [_track_summary(track) for track in tracks],
                "summary": result.summary.to_dict(),
                "observation_lineage": observation_lineage,
                "structural_ambiguity_evidence_count": len(
                    structural_ambiguity_evidence
                ),
                "structural_ambiguity_evidence": [
                    item.to_dict() for item in structural_ambiguity_evidence
                ],
            },
            copy_payload=False,
        )

    def _d2_publication(self, now: float) -> RuntimePublication:
        result = self.latest_d2_result
        risk = result.risk_summary
        tracker_summary = self.d2.summary()
        association_metadata = result.metadata
        return RuntimePublication(
            topic="modules.d2.associated_tracks",
            source="D2",
            schema_version="d2-scalable3d-association-v1",
            payload={
                "timestamp": now,
                "source_d1_posterior_generation": int(
                    self._d2_consumed_d1_posterior_generation
                ),
                "track_count": len(self.latest_d2_tracks),
                "tracks": [_track_summary(track) for track in self.latest_d2_tracks],
                "association": {
                    "timestamp": float(result.timestamp),
                    "associator_type": result.associator_type,
                    "matched_pairs": [pair.to_dict() for pair in result.matched_pairs],
                    "unmatched_track_ids": list(result.unmatched_track_ids),
                    "unmatched_detection_ids": list(result.unmatched_detection_ids),
                    "ambiguity_score": float(result.ambiguity_score),
                    "rejected_pair_count": len(result.rejected_pairs),
                    "candidate_edge_count": int(
                        result.metadata.get("candidate_edge_count", 0)
                    ),
                    "dense_pair_count": int(
                        result.metadata.get("dense_pair_count", 0)
                    ),
                    "source_binding_conflicts": list(
                        association_metadata.get("source_binding_conflicts", ())
                    ),
                    "binding_pre_update_rejection_count": int(
                        association_metadata.get(
                            "binding_pre_update_rejection_count",
                            0,
                        )
                    ),
                    "ambiguity_hold": dict(
                        association_metadata.get("ambiguity_hold", {})
                    ),
                    "identity_commitment": {
                        "schema_version": str(
                            association_metadata.get(
                                "identity_commitment_schema_version",
                                "",
                            )
                        ),
                        "policy_version": str(
                            association_metadata.get(
                                "identity_commitment_policy_version",
                                "",
                            )
                        ),
                        "state_counts": dict(
                            association_metadata.get(
                                "identity_commitment_state_counts",
                                {},
                            )
                        ),
                        "transition_counts_cumulative": dict(
                            association_metadata.get(
                                "identity_commitment_transition_counts_cumulative",
                                {},
                            )
                        ),
                        "blocked_recovery_counts_cumulative": dict(
                            association_metadata.get(
                                "identity_commitment_blocked_recovery_counts_cumulative",
                                {},
                            )
                        ),
                        "suppressed_association_count": int(
                            association_metadata.get(
                                "identity_commitment_suppressed_association_count",
                                0,
                            )
                        ),
                        "suppressed_association_reason_counts": dict(
                            association_metadata.get(
                                "identity_commitment_suppressed_association_reason_counts",
                                {},
                            )
                        ),
                        "suppressed_births": dict(
                            association_metadata.get(
                                "identity_commitment_suppressed_births",
                                {},
                            )
                        ),
                        "recovery_config": dict(
                            association_metadata.get(
                                "identity_commitment_recovery_config",
                                {},
                            )
                        ),
                        "recovery_barrier": dict(
                            association_metadata.get(
                                "identity_commitment_recovery_barrier",
                                {},
                            )
                        ),
                        "online_truth_used": False,
                    },
                    "structural_ambiguity_evidence_consumed_total": int(
                        self._structural_ambiguity_evidence_consumed_count
                    ),
                    "structural_ambiguity_d2_consumption_count": int(
                        self._structural_ambiguity_d2_consumption_count
                    ),
                    "observation_evidence_governance": {
                        "schema_version": (
                            "d2-observation-evidence-governance-v1"
                        ),
                        "input_detection_count": int(
                            association_metadata.get("input_detection_count", 0)
                        ),
                        "fresh_detection_count": int(
                            association_metadata.get("fresh_detection_count", 0)
                        ),
                        "freshness_available_count": int(
                            association_metadata.get(
                                "observation_freshness_available_count",
                                0,
                            )
                        ),
                        "freshness_unavailable_count": int(
                            association_metadata.get(
                                "observation_freshness_unavailable_count",
                                0,
                            )
                        ),
                        "replay_quarantined_detection_count": int(
                            association_metadata.get(
                                "replay_quarantined_detection_count",
                                0,
                            )
                        ),
                        "replay_quarantine_events": list(
                            association_metadata.get(
                                "replay_quarantine_events",
                                (),
                            )
                        ),
                        "duplicate_coalescence_count": int(
                            association_metadata.get(
                                "duplicate_coalescence_count",
                                0,
                            )
                        ),
                        "duplicate_coalescence_events": list(
                            association_metadata.get(
                                "duplicate_coalescence_events",
                                (),
                            )
                        ),
                        "suppressed_births_by_detection": dict(
                            association_metadata.get(
                                "suppressed_births_by_detection",
                                {},
                            )
                        ),
                        "tentative_drop_miss_threshold": int(
                            association_metadata.get(
                                "tentative_drop_miss_threshold",
                                tracker_summary.get(
                                    "tentative_drop_miss_threshold",
                                    0,
                                ),
                            )
                        ),
                        "cumulative": {
                            "observation_claim_count": int(
                                tracker_summary.get("observation_claim_count", 0)
                            ),
                            "replay_quarantine_count": int(
                                tracker_summary.get("replay_quarantine_count", 0)
                            ),
                            "observation_timestamp_conflict_count": int(
                                tracker_summary.get(
                                    "observation_timestamp_conflict_count",
                                    0,
                                )
                            ),
                            "duplicate_coalescence_count": int(
                                tracker_summary.get(
                                    "duplicate_coalescence_count",
                                    0,
                                )
                            ),
                            "tentative_stale_drop_count": int(
                                tracker_summary.get(
                                    "tentative_stale_drop_count",
                                    0,
                                )
                            ),
                        },
                        "claim_ledger": dict(
                            tracker_summary.get("observation_claim_ledger", {})
                        ),
                        "replay_coast_count": int(
                            association_metadata.get("replay_coast_count", 0)
                        ),
                        "replay_coast_reason_counts": dict(
                            association_metadata.get(
                                "replay_coast_reason_counts",
                                {},
                            )
                        ),
                        "replay_coast_config": dict(
                            tracker_summary.get("replay_coast_config", {})
                        ),
                        "global_track_id_owner": "D2_center",
                        "online_truth_used": False,
                    },
                    "risk_summary": (
                        None
                        if risk is None
                        else {
                            "association_ambiguity": risk.association_ambiguity,
                            "duplicate_track_risk": risk.duplicate_track_risk,
                            "covariance_overlap_rate": risk.covariance_overlap_rate,
                            "source_binding_conflict_count": (
                                risk.source_binding_conflict_count
                            ),
                        }
                    ),
                },
                "id_switch_count": None,
                "id_switch_count_available": False,
                "identity_lineage": self._d2_identity_lineage_payload(result),
                "identity_lineage_policy": (
                    "d2_center_track_to_d1_source_observation_commitment_v2"
                ),
            },
            copy_payload=False,
        )

    def _update_d2_identity_lineage(
        self,
        result: Any,
        detections: list[Any],
    ) -> None:
        """Retain truth-free D1 observation lineage for each D2-owned track."""

        self._d2_identity_lineage_by_track.clear()
        commitment_by_track = self._d2_identity_commitments(result)
        detection_by_id = {item.detection_id: item for item in detections}
        d1_track_id_by_detection = {
            detection.detection_id: str(source_track.global_track_id)
            for source_track, detection in zip(
                self.latest_d1_tracks,
                detections,
                strict=True,
            )
        }
        for detection_id, global_track_id in dict(
            result.metadata.get("detection_to_track", {})
        ).items():
            commitment = commitment_by_track.get(str(global_track_id))
            if commitment is None:
                raise RuntimeError(
                    "D2 detection mapping lacks identity commitment"
                )
            if (
                commitment.identity_commitment_state
                != IdentityCommitmentState.COMMITTED
            ):
                raise RuntimeError(
                    "D2 uncommitted track cannot expose detection binding"
                )
            detection = detection_by_id.get(str(detection_id))
            if detection is None:
                continue
            observation_id = str(
                detection.metadata.get("latest_observation_id", "")
            ).strip()
            if not observation_id:
                continue
            d1_track_id = d1_track_id_by_detection.get(str(detection_id))
            pending_by_observation = self._d1_pending_lineage_by_track.get(
                d1_track_id or "",
                {},
            )
            committed_measurement_timestamp = (
                commitment.measurement_timestamp
            )
            if committed_measurement_timestamp is None:
                raise RuntimeError(
                    "committed D2 observed identity lacks measurement timestamp"
                )
            timestamp_tolerance = max(
                _EPS,
                float(self.d2.observation_timestamp_tolerance_s),
            )
            lineage_candidates = pending_by_observation.values()
            if commitment.ambiguity_component_key is not None:
                lineage_candidates = (
                    item
                    for item in lineage_candidates
                    if abs(
                        float(item["measurement_timestamp"])
                        - committed_measurement_timestamp
                    )
                    <= timestamp_tolerance
                )
            lineage_records = tuple(
                sorted(
                    lineage_candidates,
                    key=lambda item: (
                        float(item["measurement_timestamp"]),
                        str(item["observation_id"]),
                    ),
                )
            )
            if not lineage_records:
                latest_record = self._d1_latest_lineage_by_observation.get(
                    observation_id
                )
                if (
                    latest_record is None
                    or abs(
                        float(latest_record["measurement_timestamp"])
                        - committed_measurement_timestamp
                    )
                    > timestamp_tolerance
                ):
                    raise RuntimeError(
                        "committed D2 observation has no matching D1 lineage"
                    )
                lineage_records = (latest_record,)

            canonical_id = str(global_track_id)
            accumulated = list(
                self._d2_identity_lineage_by_track.get(canonical_id, ())
            )
            emitted_ids = {
                str(item["observation_id"]) for item in accumulated
            }
            for lineage_record in lineage_records:
                emitted_observation_id = str(lineage_record["observation_id"])
                self._d2_observation_replay_generation[
                    emitted_observation_id
                ] = int(lineage_record["replay_generation"])
                if emitted_observation_id not in emitted_ids:
                    accumulated.append(dict(lineage_record))
                    emitted_ids.add(emitted_observation_id)
            if commitment.ambiguity_component_key is None:
                for lineage_record in lineage_records:
                    pending_by_observation.pop(
                        str(lineage_record["observation_id"]),
                        None,
                    )
            else:
                for pending_observation_id, pending_record in tuple(
                    pending_by_observation.items()
                ):
                    if (
                        float(pending_record["measurement_timestamp"])
                        <= committed_measurement_timestamp
                        + timestamp_tolerance
                    ):
                        pending_by_observation.pop(
                            pending_observation_id,
                            None,
                        )
            if d1_track_id and not pending_by_observation:
                self._d1_pending_lineage_by_track.pop(d1_track_id, None)
            self._d2_identity_lineage_by_track[canonical_id] = tuple(accumulated)

    def _d2_identity_lineage_payload(self, result: Any) -> list[dict[str, Any]]:
        commitment_by_track = self._d2_identity_commitments(result)
        detection_to_track = dict(result.metadata.get("detection_to_track", {}))
        created = set(result.metadata.get("created_track_ids_by_detection", {}).values())
        updated_track_ids = set(str(item) for item in detection_to_track.values())
        payload = []
        for track in self.latest_d2_tracks:
            global_track_id = str(track.global_track_id)
            lifecycle_state = _enum_value(track.lifecycle_state)
            if global_track_id in created:
                association_state = "created"
            elif global_track_id in updated_track_ids:
                association_state = "matched"
            elif lifecycle_state == "lost":
                association_state = "lost"
            elif lifecycle_state == "dropped":
                association_state = "dropped"
            else:
                association_state = "unmatched"
            commitment = commitment_by_track[global_track_id]
            if commitment.association_state != association_state:
                raise RuntimeError(
                    "D2 identity commitment association_state conflicts with "
                    "the published association result"
                )
            source_observations = (
                [
                    dict(item)
                    for item in self._d2_identity_lineage_by_track.get(
                        global_track_id,
                        (),
                    )
                ]
                if (
                    commitment.identity_commitment_state
                    == IdentityCommitmentState.COMMITTED
                )
                else []
            )
            if (
                association_state in {"created", "matched"}
                and commitment.identity_commitment_state
                == IdentityCommitmentState.COMMITTED
                and not source_observations
            ):
                raise RuntimeError(
                    "committed D2 observed identity lacks D1 source lineage"
                )
            payload.append(
                {
                    "global_track_id": global_track_id,
                    "lifecycle_state": lifecycle_state,
                    "association_state": association_state,
                    "identity_commitment": commitment.to_dict(),
                    "source_observations": source_observations,
                }
            )
        return payload

    def _d2_identity_commitments(
        self,
        result: Any,
    ) -> dict[str, IdentityEvidenceCommitment]:
        raw = result.metadata.get("identity_commitment_by_track")
        if not isinstance(raw, Mapping):
            raise RuntimeError("D2 identity commitment map is unavailable")
        commitments: dict[str, IdentityEvidenceCommitment] = {}
        for raw_track_id, raw_commitment in raw.items():
            track_id = str(raw_track_id)
            if not isinstance(raw_commitment, Mapping):
                raise RuntimeError("D2 identity commitment must be a mapping")
            commitment = IdentityEvidenceCommitment.from_mapping(
                raw_commitment
            )
            if commitment.global_track_id != track_id:
                raise RuntimeError(
                    "D2 identity commitment key conflicts with global_track_id"
                )
            if (
                commitment.schema_version
                != D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION
                or commitment.policy_version
                != D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION
            ):
                raise RuntimeError(
                    "D2 identity commitment schema or policy is unsupported"
                )
            commitments[track_id] = commitment
        active_ids = {
            str(track.global_track_id) for track in self.latest_d2_tracks
        }
        if set(commitments) != active_ids:
            raise RuntimeError(
                "D2 identity commitment map does not cover active tracks exactly"
            )
        return commitments

    def _committed_d2_target_ids(
        self,
        result: Any | None = None,
    ) -> frozenset[str]:
        source = self.latest_d2_result if result is None else result
        if source is None:
            return frozenset()
        return frozenset(
            track_id
            for track_id, commitment in self._d2_identity_commitments(
                source
            ).items()
            if (
                commitment.identity_commitment_state
                == IdentityCommitmentState.COMMITTED
            )
        )

    def _reconcile_active_bindings_with_identity_commitment(
        self,
        result: Any | None,
    ) -> None:
        """Hold old bindings as soon as D2 withdraws identity commitment."""

        if result is None or self.latest_plan is None:
            self._identity_commitment_binding_hold_target_ids = ()
            return
        committed_target_ids = self._committed_d2_target_ids(result)
        uncommitted_assigned_target_ids = tuple(
            sorted(
                {
                    assignment.target_id
                    for assignment in self.latest_plan.assignments
                    if assignment.target_id not in committed_target_ids
                }
            )
        )
        if not uncommitted_assigned_target_ids:
            self._identity_commitment_binding_hold_target_ids = ()
            return

        held_target_ids = set(uncommitted_assigned_target_ids)
        retained_bindings = tuple(
            binding
            for binding in self.latest_bindings
            if binding.assigned_global_track_id not in held_target_ids
        )
        removed_binding_count = len(self.latest_bindings) - len(
            retained_bindings
        )
        if (
            removed_binding_count > 0
            or uncommitted_assigned_target_ids
            != self._identity_commitment_binding_hold_target_ids
        ):
            self._identity_commitment_binding_hold_event_count += 1
        self._identity_commitment_binding_hold_count += removed_binding_count
        self.latest_bindings = retained_bindings
        self._identity_commitment_binding_hold_target_ids = (
            uncommitted_assigned_target_ids
        )
        self._identity_commitment_replan_required = True

    def _d3_publication(self, now: float) -> RuntimePublication:
        plan = self.latest_plan
        return RuntimePublication(
            topic="modules.d3.assignment_plan",
            source="D3",
            schema_version=str(plan.plan_schema),
            payload={
                "timestamp": now,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "created_at": plan.created_at,
                "assignment_count": len(plan.assignments),
                "target_count": plan.target_count,
                "resource_count": plan.resource_count,
                "assignments": [
                    {
                        "resource_id": item.resource_id,
                        "global_track_id": item.target_id,
                        "coalition_id": item.coalition_id,
                        "coalition_version": item.coalition_version,
                        "member_role": item.member_role,
                        "owner_node_id": item.metadata.get("owner_node_id"),
                        "regional_owner_layer": item.metadata.get(
                            "regional_owner_layer"
                        ),
                        "regional_region_id": item.metadata.get(
                            "regional_region_id"
                        ),
                        "regional_epoch": item.metadata.get("regional_epoch"),
                        "regional_commit_mode": item.metadata.get(
                            "regional_commit_mode"
                        ),
                    }
                    for item in plan.assignments
                ],
                "unassigned_global_track_ids": list(plan.unassigned_target_ids),
                "solver_name": plan.solver_name,
                "metadata": dict(plan.metadata),
            },
            copy_payload=False,
        )

    def _d4_publication(self, now: float) -> RuntimePublication:
        return RuntimePublication(
            topic="modules.d4.regional_failover",
            source="D4",
            schema_version="d4-regional-failover-v1",
            payload=self.latest_d4_decision.to_bus_payload(),
            copy_payload=False,
        )

    def _d4_region_advice_publication(self, now: float) -> RuntimePublication:
        payload = self.latest_d4_region_advice.to_dict()
        # The confidence-gate diagnostic is local preflight evidence. It is
        # intentionally excluded from the online bus contract.
        payload.pop("runtime_confidence_gate_diagnostic", None)
        return RuntimePublication(
            topic="modules.d4.region_resource_advice",
            source="D4",
            schema_version="d4-region-resource-advisory-runtime-v1",
            payload={
                "timestamp": now,
                **payload,
            },
            copy_payload=False,
        )

    def _d4_region_consumption_publication(
        self,
        now: float,
    ) -> RuntimePublication:
        consumption = self.latest_d4_region_consumption
        plan_metadata = (
            {}
            if self.latest_plan is None
            else dict(self.latest_plan.metadata)
        )
        successor_available = bool(
            plan_metadata.get(
                "regional_hint_successor_plan_available",
                False,
            )
        )
        return RuntimePublication(
            topic="modules.d4.region_resource_consumption",
            source="main",
            schema_version=str(consumption.schema),
            payload={
                "timestamp": now,
                **consumption.to_dict(),
                "bridge_rejection_reason": (
                    self._d4_region_hint_bridge_rejection_reason
                ),
                "d3_hint_applied": bool(
                    self.latest_plan is not None
                    and plan_metadata.get(
                        "regional_hint_applied",
                        False,
                    )
                    and successor_available
                ),
                "d3_successor_plan_available": successor_available,
                "d3_successor_state": plan_metadata.get(
                    "regional_hint_successor_state"
                ),
                "d3_successor_plan_id": plan_metadata.get(
                    "regional_hint_successor_plan_id"
                ),
                "d3_successor_plan_version": plan_metadata.get(
                    "regional_hint_successor_plan_version"
                ),
            },
            copy_payload=False,
        )

    def _d5_publication(self, now: float) -> RuntimePublication:
        association = self.latest_d5_result.association
        binding_by_tracklet_key = {
            tracklet_key: binding
            for binding in association.bindings
            for tracklet_key in binding.supporting_tracklet_keys
        }
        return RuntimePublication(
            topic="modules.d5.terminal_association",
            source="D5",
            schema_version="d5-scalable3d-association-v1",
            payload={
                "timestamp": now,
                "camera_batch_count": len(self.latest_d5_result.camera_batches),
                "tracklet_count": len(self.latest_d5_result.tracklets),
                "graph_node_count": association.graph.node_count,
                "graph_edge_count": association.graph.edge_count,
                "probability_source": association.probability_source,
                "scoring_status": association.scoring_status,
                "fallback_reason": association.fallback_reason,
                "diagnostics": dict(association.diagnostics),
                "local_tracklets": [
                    {
                        "resource_id": item.resource_id,
                        "camera_id": item.camera_id,
                        "local_track_id": item.local_track_id,
                        "tracklet_key": item.tracklet_key,
                        "measurement_timestamp": item.measurement_timestamp,
                        "arrival_timestamp": item.arrival_timestamp,
                        "bbox_xyxy": (
                            None
                            if item.bbox_xyxy is None
                            else list(item.bbox_xyxy)
                        ),
                        "center_px": item.center_px.tolist(),
                        "covariance_px": item.covariance_px.tolist(),
                        "confidence": item.confidence,
                        "center_binding": (
                            None
                            if item.tracklet_key
                            not in binding_by_tracklet_key
                            else {
                                "cluster_key": (
                                    binding_by_tracklet_key[
                                        item.tracklet_key
                                    ].cluster_key
                                ),
                                "global_track_id": (
                                    binding_by_tracklet_key[
                                        item.tracklet_key
                                    ].global_track_id
                                ),
                                "decision_state": (
                                    binding_by_tracklet_key[
                                        item.tracklet_key
                                    ].decision_state
                                ),
                                "cost": (
                                    binding_by_tracklet_key[
                                        item.tracklet_key
                                    ].cost
                                ),
                            }
                        ),
                    }
                    for item in self.latest_d5_result.tracklets
                ],
                "bindings": [
                    {
                        "cluster_key": item.cluster_key,
                        "global_track_id": item.global_track_id,
                        "decision_state": item.decision_state,
                        "cost": item.cost,
                        "supporting_tracklet_keys": list(item.supporting_tracklet_keys),
                    }
                    for item in association.bindings
                ],
            },
            copy_payload=False,
        )

    def _d5_shadow_scoring_publication(
        self,
        now: float,
    ) -> RuntimePublication:
        payload = self.latest_d5_shadow_scoring
        if payload is None:
            raise RuntimeError("D5 shadow scoring publication is unavailable")
        if not math.isclose(
            float(payload["timestamp"]),
            float(now),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise RuntimeError("D5 shadow scoring timestamp mismatch")
        return RuntimePublication(
            topic="modules.d5.g1_shadow_scoring",
            source="main",
            schema_version="scalable3d-d5-g1-shadow-scoring-v1",
            payload=payload,
            copy_payload=False,
        )

    def _d5_active_vision_publication(
        self,
        now: float,
        commands: tuple[CameraObservationCommand, ...],
    ) -> RuntimePublication:
        mode_counts = Counter(command.effective_mode for command in commands)
        intent_counts = Counter(command.intent for command in commands)
        return RuntimePublication(
            topic="modules.d5.active_vision",
            source="D5",
            schema_version="d5.active-vision-runtime.v1",
            payload={
                "timestamp": now,
                "command_count": len(commands),
                "recon_track_cue_count": (
                    self.latest_active_vision_recon_cue_count
                ),
                "effective_mode_counts": dict(sorted(mode_counts.items())),
                "intent_counts": dict(sorted(intent_counts.items())),
                "commands": [
                    camera_observation_command_payload(command)
                    for command in commands
                ],
            },
            copy_payload=False,
        )

    def _d7_publication(self, now: float) -> RuntimePublication:
        commands = self.latest_guidance_batch.pair_commands
        mode_counts = Counter(command.mode.value for command in commands)
        return RuntimePublication(
            topic="modules.d7.guidance_commands",
            source="D7",
            schema_version="d7-scalable3d-guidance-v1",
            payload={
                "timestamp": now,
                "command_count": len(commands),
                "mode_counts": dict(sorted(mode_counts.items())),
                "commands": [
                    {
                        "resource_id": command.resource_id,
                        "global_track_id": command.assigned_global_track_id,
                        "plan_id": command.plan_id,
                        "plan_version": command.plan_version,
                        "mode": command.mode.value,
                        "acceleration_ned_mps2": list(command.acceleration_ned_mps2),
                        "command_norm_mps2": command.command_norm_mps2,
                        "gate_reason": command.gate_reason,
                        "visual_switch_allowed": command.visual_switch_allowed,
                    }
                    for command in commands
                ],
            },
            copy_payload=False,
        )

    def _diagnostics(
        self,
        now: float,
        *,
        include_timing_distribution: bool = False,
    ) -> dict[str, Any]:
        governance = self.observation_governance_audit()
        stage_timings: dict[str, dict[str, float | int]] = {}
        for stage in sorted(self._stage_wall_time_s):
            record: dict[str, float | int] = {
                "call_count": self._stage_call_count[stage],
                "wall_time_s": self._stage_wall_time_s[stage],
                "mean_wall_time_ms": (
                    1_000.0
                    * self._stage_wall_time_s[stage]
                    / self._stage_call_count[stage]
                ),
            }
            if include_timing_distribution:
                samples = np.asarray(self._stage_samples_s[stage], dtype=float)
                record.update(
                    {
                        "p50_wall_time_ms": (
                            1_000.0 * float(np.percentile(samples, 50.0))
                        ),
                        "p95_wall_time_ms": (
                            1_000.0 * float(np.percentile(samples, 95.0))
                        ),
                        "max_wall_time_ms": 1_000.0 * float(np.max(samples)),
                    }
                )
            stage_timings[stage] = record
        a2_evidence = tuple(self._d4_a2_evidence_by_application.values())
        a2_stage_counts = Counter(
            getattr(item.stage, "value", str(item.stage))
            for item in a2_evidence
        )
        a3_evidence = tuple(
            self._d5_a3_evidence_by_comparison_key.values()
        )
        return {
            "schema_version": INTEGRATED_STACK_SCHEMA_VERSION,
            "timestamp": now,
            "d1_track_count": len(self.latest_d1_tracks),
            "d2_track_count": len(self.latest_d2_tracks),
            "d3_assignment_count": (
                0 if self.latest_plan is None else len(self.latest_plan.assignments)
            ),
            "d3_identity_commitment_binding_hold_count": int(
                self._identity_commitment_binding_hold_count
            ),
            "d3_identity_commitment_binding_hold_event_count": int(
                self._identity_commitment_binding_hold_event_count
            ),
            "d3_identity_commitment_binding_hold_target_ids": (
                self._identity_commitment_binding_hold_target_ids
            ),
            "d3_identity_commitment_replan_required": bool(
                self._identity_commitment_replan_required
            ),
            "d3_identity_commitment_rejected_target_count": int(
                0
                if self.latest_plan is None
                else self.latest_plan.metadata.get(
                    "identity_commitment_uncommitted_rejected_count",
                    0,
                )
            ),
            "d4_region_count": (
                0
                if self.latest_d4_decision is None
                else len(self.latest_d4_decision.region_decisions)
            ),
            "d4_communication_partition_generation": (
                self._d4_partition_generation
            ),
            "d4_communication_received_count": (
                self._d4_communication_received_count
            ),
            "d4_communication_accepted_count": (
                self._d4_communication_accepted_count
            ),
            "d4_communication_rejected_count": (
                self._d4_communication_rejected_count
            ),
            "d4_communication_accept_counts": dict(
                sorted(self._d4_communication_accept_counts.items())
            ),
            "d4_communication_rejection_counts": dict(
                sorted(self._d4_communication_rejection_counts.items())
            ),
            "d4_communication_intent_counts": dict(
                sorted(self._d4_communication_intent_counts.items())
            ),
            "d4_communication_event_evaluation_count": (
                self._d4_communication_event_evaluation_count
            ),
            "d4_readiness_reception_count": len(
                self._d4_readiness_receptions
            ),
            "d4_plan_delivery_count": len(self._d4_plan_deliveries),
            "d4_ack_delivery_count": len(self._d4_ack_deliveries),
            "d4_a2_owner_ack_delivery_count": (
                self._d4_owner_ack_delivery_count
            ),
            "d4_a2_coalition_ack_delivery_count": (
                self._d4_coalition_ack_delivery_count
            ),
            "d4_a2_physical_window_count": (
                self._d4_a2_physical_window_count
            ),
            "d4_a2_evidence_record_count": len(a2_evidence),
            "d4_a2_evidence_stage_counts": dict(
                sorted(a2_stage_counts.items())
            ),
            "d4_a2_safe_adoption_count": sum(
                bool(item.safe_adoption_available)
                for item in a2_evidence
            ),
            "d4_a2_evidence_status": (
                "verified_safe_adoption"
                if any(item.safe_adoption_available for item in a2_evidence)
                else (
                    "evidence_incomplete"
                    if a2_evidence
                    else "evidence_unavailable"
                )
            ),
            "d4_a2_bridge_blocker_counts": dict(
                sorted(self._d4_a2_bridge_blocker_counts.items())
            ),
            "d5_binding_count": (
                0
                if self.latest_d5_result is None
                else sum(
                    item.global_track_id is not None
                    for item in self.latest_d5_result.association.bindings
                )
            ),
            "d5_a3_runtime_ack_count": self._d5_a3_runtime_ack_count,
            "d5_a3_observation_frame_count": (
                self._d5_a3_observation_frame_count
            ),
            "d5_a3_physical_window_count": (
                self._d5_a3_physical_window_count
            ),
            "d5_a3_r0_runtime_ack_count": (
                self._d5_a3_r0_runtime_ack_count
            ),
            "d5_a3_r0_observation_frame_count": (
                self._d5_a3_r0_observation_frame_count
            ),
            "d5_a3_r0_physical_window_count": (
                self._d5_a3_r0_physical_window_count
            ),
            "d5_camera_empty_frame_received_count": (
                self._d5_camera_empty_frame_received_count
            ),
            "d5_camera_empty_frame_consumed_count": (
                self._d5_camera_empty_frame_consumed_count
            ),
            "d5_camera_empty_frame_rejected_count": (
                self._d5_camera_empty_frame_rejected_count
            ),
            "d5_camera_empty_frame_unmatched_count": (
                self._d5_camera_empty_frame_unmatched_count
            ),
            "d5_active_vision_observation_triggered": (
                self.stack_config.d5_active_vision_observation_triggered
            ),
            "d5_active_vision_evidence_tail_s": (
                self.stack_config.d5_active_vision_evidence_tail_s
            ),
            "d5_active_vision_tail_suppressed_count": (
                self._d5_active_vision_tail_suppressed_count
            ),
            "d5_a3_r0_window_record_count": len(
                self._d5_a3_r0_window_by_comparison_key
            ),
            "d5_a3_evidence_record_count": len(a3_evidence),
            "d5_a3_candidate_stage_record_count": len(
                self._d5_a3_candidate_stage_by_comparison_key
            ),
            "d5_a3_model_action_adopted_count": sum(
                bool(item.model_action_adopted) for item in a3_evidence
            ),
            "d5_a3_evidence_status": (
                "verified_adoption"
                if any(item.model_action_adopted for item in a3_evidence)
                else (
                    "verified_zero_adoption"
                    if a3_evidence
                    else "evidence_unavailable"
                )
            ),
            "d5_a3_bridge_blocker_counts": dict(
                sorted(self._d5_a3_bridge_blocker_counts.items())
            ),
            "d5_g1_shadow_scoring_frame_count": int(
                self._d5_shadow_scoring_frame_count
            ),
            "d5_g1_shadow_scoring_success_count": int(
                self._d5_shadow_scoring_success_count
            ),
            "d5_g1_shadow_scoring_rejected_count": int(
                self._d5_shadow_scoring_rejected_count
            ),
            "d5_g1_shadow_scoring_edge_count": int(
                self._d5_shadow_scoring_edge_count
            ),
            "d5_g1_shadow_scoring_rejection_reasons": dict(
                sorted(self._d5_shadow_scoring_rejection_reasons.items())
            ),
            "d5_g1_shadow_model_output_applied": False,
            "d1_fusion_performance": (
                self.d1.fusion_performance_diagnostics().to_dict()
            ),
            "d1_scan_input_implementation": governance[
                "d1_scan_input_implementation"
            ],
            "d1_scan_input_execution_config": dict(
                governance["d1_scan_input_execution_config"]
            ),
            "d1_scan_input_performance_diagnostics": dict(
                governance["d1_scan_input_performance_diagnostics"]
            ),
            "d1_online_batch_frame_implementation": governance[
                "d1_online_batch_frame_implementation"
            ],
            "d1_online_batch_frame_execution_config": dict(
                governance["d1_online_batch_frame_execution_config"]
            ),
            "d1_online_batch_frame_diagnostics": dict(
                governance["d1_online_batch_frame_diagnostics"]
            ),
            "d1_publication_metadata_implementation": governance[
                "d1_publication_metadata_implementation"
            ],
            "d1_publication_metadata_diagnostics": dict(
                governance["d1_publication_metadata_diagnostics"]
            ),
            "d1_cv_motion_model_implementation": governance[
                "d1_cv_motion_model_implementation"
            ],
            "d1_cv_motion_model_cache_diagnostics": dict(
                governance["d1_cv_motion_model_cache_diagnostics"]
            ),
            "d1_opaque_source_identity_implementation": governance[
                "d1_opaque_source_identity_implementation"
            ],
            "d1_opaque_source_identity_cache_diagnostics": dict(
                governance[
                    "d1_opaque_source_identity_cache_diagnostics"
                ]
            ),
            "d1_structured_numerical_jacobian_implementation": governance[
                "d1_structured_numerical_jacobian_implementation"
            ],
            "d1_structured_numerical_jacobian_diagnostics": dict(
                governance[
                    "d1_structured_numerical_jacobian_diagnostics"
                ]
            ),
            "d1_association_sparse_prefilter_implementation": governance[
                "d1_association_sparse_prefilter_implementation"
            ],
            "d1_association_sparse_prefilter_execution_config": dict(
                governance[
                    "d1_association_sparse_prefilter_execution_config"
                ]
            ),
            "d1_association_sparse_prefilter_diagnostics": dict(
                governance[
                    "d1_association_sparse_prefilter_diagnostics"
                ]
            ),
            "d1_replay_prefix_summary_implementation": governance[
                "d1_replay_prefix_summary_implementation"
            ],
            "d1_replay_prefix_summary_execution_config": dict(
                governance[
                    "d1_replay_prefix_summary_execution_config"
                ]
            ),
            "d1_replay_prefix_summary_diagnostics": dict(
                governance["d1_replay_prefix_summary_diagnostics"]
            ),
            "d1_publication_evidence_snapshot_implementation": governance[
                "d1_publication_evidence_snapshot_implementation"
            ],
            "d1_publication_evidence_snapshot_execution_config": dict(
                governance[
                    "d1_publication_evidence_snapshot_execution_config"
                ]
            ),
            "d1_publication_evidence_snapshot_diagnostics": dict(
                governance[
                    "d1_publication_evidence_snapshot_diagnostics"
                ]
            ),
            "d2_publication_metadata_audit": dict(
                governance["d2_publication_metadata_audit"]
            ),
            "d1_fusion_association": dict(
                governance["d1_fusion_association"]
            ),
            "d5_terminal_performance": self.d5.performance_snapshot().to_dict(),
            "d5_active_vision_command_count": len(
                self.latest_active_vision_decisions
            ),
            "d5_active_vision_recon_cue_count": (
                self.latest_active_vision_recon_cue_count
            ),
            "d5_active_vision_requested_mode": (
                self.stack_config.d5_active_vision_mode
            ),
            "d5_active_vision_effective_mode_counts": dict(
                sorted(
                    Counter(
                        decision.effective_mode.value
                        for decision in self.latest_active_vision_decisions
                    ).items()
                )
            ),
            "d5_active_vision_fallback_reason_counts": dict(
                sorted(
                    Counter(
                        decision.fallback_reason
                        for decision in self.latest_active_vision_decisions
                        if decision.fallback_reason is not None
                    ).items()
                )
            ),
            "d7_command_count": (
                0
                if self.latest_guidance_batch is None
                else len(self.latest_guidance_batch.pair_commands)
            ),
            "regional_plan_rejection_reason": (
                self._regional_plan_rejection_reason
            ),
            "d4_region_advice_available": self.latest_d4_region_advice is not None,
            "d4_region_advice_effective_mode": (
                None
                if self.latest_d4_region_advice is None
                else self.latest_d4_region_advice.effective_mode.value
            ),
            "d4_region_advice_fallback_reason": (
                None
                if self.latest_d4_region_advice is None
                else self.latest_d4_region_advice.fallback_reason
            ),
            "d4_region_consumption_available": (
                self.latest_d4_region_consumption is not None
            ),
            "d4_region_consumable": (
                None
                if self.latest_d4_region_consumption is None
                else bool(self.latest_d4_region_consumption.consumable)
            ),
            "d4_region_consumption_rejection_reasons": (
                ()
                if self.latest_d4_region_consumption is None
                else tuple(
                    self.latest_d4_region_consumption.rejection_reasons
                )
            ),
            "d4_region_hint_bridge_rejection_reason": (
                self._d4_region_hint_bridge_rejection_reason
            ),
            "d3_regional_hint_applied": bool(
                self.latest_plan is not None
                and self.latest_plan.metadata.get("regional_hint_applied", False)
            ),
            "learning_runtime": dict(self.learning_runtime_diagnostics),
            "observation_governance": governance,
            "online_truth_use_count": 0,
            "stage_timings": stage_timings,
        }

    def _record_timing(self, stage: str, elapsed_s: float) -> None:
        elapsed = float(elapsed_s)
        self._stage_wall_time_s[stage] = (
            self._stage_wall_time_s.get(stage, 0.0) + elapsed
        )
        self._stage_call_count[stage] = self._stage_call_count.get(stage, 0) + 1
        self._stage_samples_s.setdefault(stage, []).append(elapsed)

    def _validate_navigation(
        self,
        navigation: PlatformNavigationBatch,
        expected_kind: str,
    ) -> None:
        if navigation.platform_kind != expected_kind:
            raise ValueError(
                f"expected {expected_kind} navigation, got {navigation.platform_kind}"
            )

    def _require_ready(self) -> ScenarioConfig:
        if self.config is None:
            raise RuntimeError("module stack must be reset before step")
        assert self.d1 is not None
        assert self.d1_scan_input is not None
        assert self.d2 is not None
        assert self.d3 is not None
        assert self.d4 is not None
        assert self.d5 is not None
        assert self.d7 is not None
        return self.config


def _scan_input_config(
    config: ScenarioConfig,
    stack_config: IntegratedStackConfig,
) -> ScanInputConfig:
    scan_rate_hz = 0.0
    if config.radar_enabled:
        scan_rate_hz += 1.0 / config.radar_period_s
    if config.acoustic_enabled:
        scan_rate_hz += config.acoustic_sensor_count / config.acoustic_period_s
    if config.visual_enabled:
        scan_rate_hz += (
            config.resource_count + config.recon_count
        ) / config.visual_period_s
    buffering_horizon_s = max(
        stack_config.d1_scan_max_lateness_s + config.physics_dt_s,
        config.physics_dt_s,
    )
    maximum_scans = max(
        1_024,
        int(math.ceil(2.0 * scan_rate_hz * buffering_horizon_s)),
    )
    maximum_observations = max(
        200_000,
        maximum_scans * max(1, config.target_count),
    )
    return ScanInputConfig(
        max_lateness_s=stack_config.d1_scan_max_lateness_s,
        max_buffer_residence_s=stack_config.d1_scan_max_buffer_residence_s,
        max_buffered_scans=maximum_scans,
        max_buffered_observations=maximum_observations,
    )


def _observation_claim_config(
    config: ScenarioConfig,
    stack_config: IntegratedStackConfig,
) -> ObservationClaimLedgerConfig:
    protected_window_s = max(
        stack_config.d2_claim_retention_s,
        stack_config.d2_claim_max_lateness_s,
    )
    claims_per_window = (
        config.target_count
        * protected_window_s
        / config.association_period_s
    )
    maximum_claims = max(
        4_096,
        int(
            math.ceil(
                claims_per_window
                * stack_config.d2_claim_capacity_safety_factor
            )
        ),
    )
    return ObservationClaimLedgerConfig(
        config_version="main-scalable3d-observation-claim-policy-v1",
        retention_seconds=stack_config.d2_claim_retention_s,
        max_count=maximum_claims,
        max_lateness_seconds=stack_config.d2_claim_max_lateness_s,
    )


def _active_camera_position(
    camera: CameraRuntimeState,
    step_input: RuntimeStepInput,
) -> np.ndarray:
    navigation = (
        step_input.interceptors
        if camera.platform_kind == "interceptor"
        else step_input.recon
    )
    try:
        index = navigation.platform_ids.index(camera.resource_id)
    except ValueError as exc:
        raise ValueError(
            f"active-vision camera resource is unavailable: {camera.resource_id}"
        ) from exc
    if not bool(navigation.active[index]):
        raise ValueError(
            f"active-vision camera resource is inactive: {camera.resource_id}"
        )
    return np.asarray(navigation.state_ned[index, :3], dtype=float)


def _predict_track_position(track: Any, now: float) -> tuple[np.ndarray, np.ndarray]:
    state = np.asarray(track.state, dtype=float).reshape(6)
    covariance = np.asarray(track.covariance, dtype=float).reshape(6, 6)
    dt = max(0.0, float(now) - float(track.timestamp))
    position = state[:3] + state[3:] * dt
    transition = np.eye(6, dtype=float)
    transition[:3, 3:] = np.eye(3, dtype=float) * dt
    propagated = transition @ covariance @ transition.T
    position_covariance = 0.5 * (
        propagated[:3, :3] + propagated[:3, :3].T
    )
    return position, position_covariance


def _yaw_pitch_from_ned(direction_ned: np.ndarray) -> tuple[float, float]:
    vector = np.asarray(direction_ned, dtype=float).reshape(3)
    horizontal = float(np.linalg.norm(vector[:2]))
    if not np.all(np.isfinite(vector)) or float(np.linalg.norm(vector)) < 1.0e-9:
        return 0.0, 0.0
    yaw = math.degrees(math.atan2(float(vector[1]), float(vector[0])))
    pitch = math.degrees(math.atan2(float(-vector[2]), max(horizontal, 1.0e-9)))
    return _wrap_degrees(yaw), float(np.clip(pitch, -89.9, 89.9))


def _direction_from_yaw_pitch(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    return np.array(
        [
            math.cos(pitch) * math.cos(yaw),
            math.cos(pitch) * math.sin(yaw),
            -math.sin(pitch),
        ],
        dtype=float,
    )


def _wrap_degrees(value: float) -> float:
    return float((float(value) + 180.0) % 360.0 - 180.0)


def _angular_covariance_deg2(
    relative_ned: np.ndarray,
    position_covariance_ned: np.ndarray,
    *,
    attitude_std_deg: float,
) -> np.ndarray:
    relative = np.asarray(relative_ned, dtype=float).reshape(3)
    covariance = np.asarray(position_covariance_ned, dtype=float).reshape(3, 3)
    north, east, down = (float(value) for value in relative)
    horizontal_squared = north * north + east * east
    range_squared = horizontal_squared + down * down
    if range_squared < 1.0e-8 or horizontal_squared < 1.0e-8:
        return np.eye(2, dtype=float) * 1.0e6
    horizontal = math.sqrt(horizontal_squared)
    jacobian = np.array(
        [
            [-east / horizontal_squared, north / horizontal_squared, 0.0],
            [
                down * north / (range_squared * horizontal),
                down * east / (range_squared * horizontal),
                -horizontal / range_squared,
            ],
        ],
        dtype=float,
    )
    radians_covariance = jacobian @ covariance @ jacobian.T
    degrees_covariance = radians_covariance * (180.0 / math.pi) ** 2
    degrees_covariance += np.eye(2, dtype=float) * float(attitude_std_deg) ** 2
    degrees_covariance = 0.5 * (degrees_covariance + degrees_covariance.T)
    minimum_eigenvalue = float(np.linalg.eigvalsh(degrees_covariance).min())
    if minimum_eigenvalue < 0.0:
        degrees_covariance += np.eye(2, dtype=float) * (-minimum_eigenvalue + 1.0e-9)
    return degrees_covariance


def _vertical_fov_deg(
    horizontal_fov_deg: float,
    *,
    platform_kind: str,
    config: ScenarioConfig,
) -> float:
    if platform_kind == "interceptor":
        width = config.camera_width_px
        height = config.camera_height_px
    else:
        width = config.recon_camera_width_px
        height = config.recon_camera_height_px
    horizontal = math.radians(float(horizontal_fov_deg))
    return math.degrees(
        2.0 * math.atan(math.tan(0.5 * horizontal) * float(height) / float(width))
    )


def _d2_input_signature(detections: Iterable[Any]) -> tuple[tuple[Any, ...], ...]:
    """Identify new D1 evidence without depending on D1-owned track identity."""

    signature: list[tuple[Any, ...]] = []
    for detection in detections:
        raw_metadata = getattr(detection, "metadata", {})
        metadata = raw_metadata if isinstance(raw_metadata, Mapping) else {}
        observation_id = str(metadata.get("latest_observation_id", "")).strip()
        if observation_id:
            signature.append(
                (
                    str(metadata.get("latest_sensor_id", "")),
                    observation_id,
                    float(
                        metadata.get(
                            "latest_measurement_timestamp",
                            metadata.get(
                                "source_measurement_timestamp",
                                detection.measurement_timestamp,
                            ),
                        )
                    ),
                    int(metadata.get("hits", 0)),
                    int(metadata.get("latest_replay_filter_update_count", 0)),
                )
            )
            continue
        signature.append(
            (
                "anonymous_detection",
                str(detection.detection_id),
                float(detection.measurement_timestamp),
            )
        )
    return tuple(sorted(signature))


def _batch_modality(batch: OnlineSensorBatch) -> str:
    modalities = {str(item.modality).lower() for item in batch.measurements}
    if len(modalities) != 1:
        raise ValueError("online sensor batch must contain one modality")
    return next(iter(modalities))


def _advance_schedule(current: float, period: float, now: float) -> float:
    value = float(current)
    while value <= now + _EPS:
        value += float(period)
    return value


def _region_ids(count: int) -> tuple[str, ...]:
    width = max(3, len(str(int(count))))
    return tuple(f"region-{index:0{width}d}" for index in range(int(count)))


def _regional_resource_locality_enabled(config: ScenarioConfig) -> bool:
    value = config.metadata.get("regional_resource_locality_enforced", False)
    if type(value) is not bool:
        raise ValueError(
            "regional_resource_locality_enforced must be a boolean"
        )
    return value


def _region_for_position(position_ned: np.ndarray, region_count: int) -> str:
    position = np.asarray(position_ned, dtype=float).reshape(3)
    angle = math.atan2(float(position[1]), float(position[0])) % (2.0 * math.pi)
    index = min(
        region_count - 1,
        int(math.floor(angle / (2.0 * math.pi) * region_count)),
    )
    return _region_ids(region_count)[index]


def _region_definitions(region_ids: tuple[str, ...]) -> tuple[RegionDefinition, ...]:
    if len(region_ids) == 1:
        return (RegionDefinition(region_ids[0], "sector-000"),)
    return tuple(
        RegionDefinition(
            region_id=region_id,
            coverage_cell=f"sector-{index:03d}",
            neighbor_region_ids=(
                region_ids[(index - 1) % len(region_ids)],
                region_ids[(index + 1) % len(region_ids)],
            ),
        )
        for index, region_id in enumerate(region_ids)
    )


def _track_summary(track: Any) -> dict[str, Any]:
    lifecycle = getattr(track, "lifecycle_state", getattr(track, "track_level", "unknown"))
    return {
        "global_track_id": str(track.global_track_id),
        "timestamp": float(track.timestamp),
        "state_ned": np.asarray(track.state, dtype=float).tolist(),
        "covariance": np.asarray(track.covariance, dtype=float).tolist(),
        "track_state": _enum_value(lifecycle),
    }


def _d1_shadow_sha256(value: Any) -> str:
    encoded = _d1_shadow_canonical_json_bytes(value)
    return _d1_shadow_sha256_bytes(encoded)


def _d1_shadow_sha256_bytes(encoded: bytes) -> str:
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _d4_safe_adoption_sha256(value: Any) -> str:
    """Match D4's immutable evidence digest for cross-module validation."""

    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _d1_shadow_canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _d1_shadow_canonicalize(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _d1_shadow_canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Enum):
        return _d1_shadow_canonicalize(value.value)
    if isinstance(value, np.ndarray):
        return _d1_shadow_canonicalize(value.tolist())
    if isinstance(value, np.generic):
        return _d1_shadow_canonicalize(value.item())
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        if not np.isfinite(number):
            raise ValueError("D1 shadow audit contains nonfinite input")
        return number
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key in sorted(
            value,
            key=lambda item: str(item).encode("utf-8"),
        ):
            key = str(raw_key)
            if key in normalized:
                raise ValueError(
                    "D1 shadow audit mapping has duplicate string keys"
                )
            normalized[key] = _d1_shadow_canonicalize(value[raw_key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [_d1_shadow_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized_items = [
            _d1_shadow_canonicalize(item) for item in value
        ]
        return sorted(
            normalized_items,
            key=_d1_shadow_canonical_json_bytes,
        )
    raise TypeError(
        "unsupported D1 shadow audit type: "
        f"{type(value).__name__}"
    )


def _lineage_ending_in_observation(
    lineage: Any,
    observation_id: str,
) -> tuple[str, ...]:
    items = tuple(str(item) for item in lineage)
    if not items:
        return (str(observation_id),)
    if items[-1] == str(observation_id):
        return items
    return (*items, str(observation_id))


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower()


def _coalition_id_for(plan: Any, target_id: str) -> str | None:
    coalition = next(
        (item for item in plan.coalitions if item.target_id == target_id),
        None,
    )
    return None if coalition is None else coalition.coalition_id


def _coalition_version_for(plan: Any, target_id: str) -> int | None:
    coalition = next(
        (item for item in plan.coalitions if item.target_id == target_id),
        None,
    )
    return None if coalition is None else coalition.version


def _coalition_epoch_for(plan: Any, target_id: str) -> int | None:
    coalition = next(
        (item for item in plan.coalitions if item.target_id == target_id),
        None,
    )
    if coalition is None:
        return None
    return int(coalition.metadata.get("coalition_epoch", coalition.version))


def _is_sha256_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


def _is_git_commit_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 40 and all(
        character in "0123456789abcdef" for character in text
    )
