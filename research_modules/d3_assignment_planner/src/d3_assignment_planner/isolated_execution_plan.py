"""Strict promotion of an offline D3 solve into an isolated execution plan.

The output of this module is confined to a cloned simulation world.  It is a
new plan generation, but it is not a production publication, runtime ACK,
online authority grant, physical outcome, reward, or causal claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from math import inf, isfinite, nextafter
from typing import Any

from .models import Assignment, AssignmentPlan
from .paired_intervention import (
    PairedInterventionArmSpecification,
    PairedInterventionExecutionReceipt,
    PairedInterventionSpecification,
)
from .planning_evidence import PlanningFrameEvidence
from .runtime_plan_ack import (
    AssignmentPlanRuntimeAckError,
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)


ISOLATED_EXECUTION_PLAN_SCHEMA_V1 = "d3.isolated-execution-plan.v1"
ISOLATED_EXECUTION_PLAN_CONVERSION_SCHEMA_V1 = (
    "d3.isolated-execution-plan-conversion.v1"
)
ISOLATED_EXECUTION_PLAN_CONVERSION_SCHEMA_V2 = (
    "d3.isolated-execution-plan-conversion.v2"
)
ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1 = (
    "d3.isolated-execution-planning-frame-transition.v1"
)
ISOLATED_EXECUTION_PLAN_CONVERSION_KIND = (
    "offline_solve_to_nonproduction_isolated_execution_plan"
)

_HEX_DIGITS = frozenset("0123456789abcdef")
_FORBIDDEN_TRUTH_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
    }
)
_AUTHORITY_METADATA_KEYS = frozenset(
    {
        "plan_schema",
        "plan_owner",
        "active_plan_owner",
        "current_plan_owner",
        "current_plan_owner_node_id",
        "owner_node_id",
        "selected_secondary_node_id",
        "source_node_id",
        "target_node_id",
        "link_type",
        "authority_epoch",
        "lease_expires_at_s",
        "secondary_takeover_state",
        "secondary_plan_version",
        "secondary_readiness_class",
        "secondary_readiness_sustained",
        "secondary_activated_at_s",
        "secondary_plan_executable",
        "secondary_lease_valid_at_activation",
        "secondary_epoch_monotonic",
        "secondary_lease_expires_at_s",
        "secondary_leader_epoch",
        "regional_plan_schema",
        "regional_authorities",
        "regional_owner_layers",
        "regional_owner_node_ids",
        "regional_min_lease_expires_at_s",
        "regional_max_epoch",
        "regional_execution_allowed",
        "regional_commit_modes",
        "regional_single_member_authority_count",
        "regional_atomic_coalition_commit_count",
        "regional_owner_layer",
        "regional_region_id",
        "regional_epoch",
        "regional_lease_expires_at_s",
        "regional_commit_state",
        "regional_commit_required",
        "regional_commit_mode",
        "regional_commit_evidence_present",
    }
)
_CONVERSION_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "conversion_id",
        "experiment_id",
        "experiment_version",
        "pair_id",
        "seed",
        "arm_id",
        "arm_kind",
        "isolation_id",
        "arm_spec_sha256",
        "execution_receipt_sha256",
        "source_snapshot_lineage_sha256",
        "planning_frame_schema_version",
        "planning_frame_transition_schema_version",
        "planning_frame_path",
        "planning_frame_timestamp_s",
        "planning_frame_snapshot_sha256",
        "planning_frame_transition_sha256",
        "offline_solve_source_plan_id",
        "offline_solve_source_plan_version",
        "offline_solve_source_plan_schema",
        "offline_solve_source_plan_payload_sha256",
        "offline_solve_source_created_at_s",
        "formal_authority_plan_id",
        "formal_authority_plan_version",
        "formal_authority_plan_schema",
        "formal_authority_plan_payload_sha256",
        "formal_authority_created_at_s",
        "formal_authority_previous_plan_id",
        "candidate_plan_id",
        "candidate_plan_version",
        "candidate_plan_schema",
        "candidate_plan_payload_sha256",
        "candidate_assignment_inventory_sha256",
        "candidate_target_inventory_sha256",
        "execution_plan_id",
        "execution_plan_version",
        "execution_plan_schema",
        "execution_plan_payload_sha256",
        "execution_assignment_inventory_sha256",
        "execution_target_inventory_sha256",
        "authority_semantics_sha256",
        "previous_plan_id",
        "created_at_s",
        "valid_until_s",
        "isolated_simulation_only",
        "production_runtime_ack",
        "runtime_publication_allowed",
        "runtime_execution_allowed",
        "online_authority_enabled",
        "physical_outcome_available",
        "reward_available",
        "causal_evidence_available",
    }
)


class IsolatedExecutionPlanError(ValueError):
    """Stable fail-closed error for the isolated plan conversion contract."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(message or self.code)


@dataclass(frozen=True, slots=True)
class IsolatedExecutionPlanConversionEvidence:
    """Immutable lineage from one planning frame to one isolated plan."""

    conversion_id: str
    experiment_id: str
    experiment_version: str
    pair_id: str
    seed: int
    arm_id: str
    arm_kind: str
    isolation_id: str
    arm_spec_sha256: str
    execution_receipt_sha256: str
    source_snapshot_lineage_sha256: str
    planning_frame_schema_version: str
    planning_frame_transition_schema_version: str
    planning_frame_path: str
    planning_frame_timestamp_s: float
    planning_frame_snapshot_sha256: str
    planning_frame_transition_sha256: str
    offline_solve_source_plan_id: str
    offline_solve_source_plan_version: int
    offline_solve_source_plan_schema: str
    offline_solve_source_plan_payload_sha256: str
    offline_solve_source_created_at_s: float
    formal_authority_plan_id: str
    formal_authority_plan_version: int
    formal_authority_plan_schema: str
    formal_authority_plan_payload_sha256: str
    formal_authority_created_at_s: float
    formal_authority_previous_plan_id: str | None
    candidate_plan_id: str
    candidate_plan_version: int
    candidate_plan_schema: str
    candidate_plan_payload_sha256: str
    candidate_assignment_inventory_sha256: str
    candidate_target_inventory_sha256: str
    execution_plan_id: str
    execution_plan_version: int
    execution_plan_schema: str
    execution_plan_payload_sha256: str
    execution_assignment_inventory_sha256: str
    execution_target_inventory_sha256: str
    authority_semantics_sha256: str
    previous_plan_id: str
    created_at_s: float
    valid_until_s: float
    isolated_simulation_only: bool = True
    production_runtime_ack: bool = False
    runtime_publication_allowed: bool = False
    runtime_execution_allowed: bool = False
    online_authority_enabled: bool = False
    physical_outcome_available: bool = False
    reward_available: bool = False
    causal_evidence_available: bool = False
    evidence_kind: str = ISOLATED_EXECUTION_PLAN_CONVERSION_KIND
    schema_version: str = ISOLATED_EXECUTION_PLAN_CONVERSION_SCHEMA_V2

    def __post_init__(self) -> None:
        if self.schema_version != ISOLATED_EXECUTION_PLAN_CONVERSION_SCHEMA_V2:
            _fail("conversion_schema_unsupported")
        if self.evidence_kind != ISOLATED_EXECUTION_PLAN_CONVERSION_KIND:
            _fail("conversion_evidence_kind_invalid")
        for name in (
            "conversion_id",
            "experiment_id",
            "experiment_version",
            "pair_id",
            "arm_id",
            "arm_kind",
            "isolation_id",
            "planning_frame_schema_version",
            "planning_frame_transition_schema_version",
            "planning_frame_path",
            "offline_solve_source_plan_id",
            "offline_solve_source_plan_schema",
            "formal_authority_plan_id",
            "formal_authority_plan_schema",
            "candidate_plan_id",
            "candidate_plan_schema",
            "execution_plan_id",
            "execution_plan_schema",
            "previous_plan_id",
        ):
            _required_text(getattr(self, name), name)
        for name in (
            "arm_spec_sha256",
            "execution_receipt_sha256",
            "source_snapshot_lineage_sha256",
            "planning_frame_snapshot_sha256",
            "planning_frame_transition_sha256",
            "offline_solve_source_plan_payload_sha256",
            "formal_authority_plan_payload_sha256",
            "candidate_plan_payload_sha256",
            "candidate_assignment_inventory_sha256",
            "candidate_target_inventory_sha256",
            "execution_plan_payload_sha256",
            "execution_assignment_inventory_sha256",
            "execution_target_inventory_sha256",
            "authority_semantics_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        for name in (
            "seed",
            "offline_solve_source_plan_version",
            "formal_authority_plan_version",
            "candidate_plan_version",
            "execution_plan_version",
        ):
            _nonnegative_int(getattr(self, name), name)
        for name in (
            "planning_frame_timestamp_s",
            "offline_solve_source_created_at_s",
            "formal_authority_created_at_s",
            "created_at_s",
            "valid_until_s",
        ):
            _finite_nonnegative(getattr(self, name), name)
        _optional_text(
            self.formal_authority_previous_plan_id,
            "formal_authority_previous_plan_id",
        )
        if (
            self.planning_frame_transition_schema_version
            != ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1
        ):
            _fail("planning_frame_transition_schema_unsupported")
        _validate_recorded_frame_transition(
            offline_solve_source_plan_id=self.offline_solve_source_plan_id,
            offline_solve_source_plan_version=(
                self.offline_solve_source_plan_version
            ),
            formal_authority_plan_id=self.formal_authority_plan_id,
            formal_authority_plan_version=self.formal_authority_plan_version,
            formal_authority_previous_plan_id=(
                self.formal_authority_previous_plan_id
            ),
        )
        if self.execution_plan_version != self.formal_authority_plan_version + 1:
            _fail("execution_plan_version_not_strictly_new")
        if self.previous_plan_id != self.formal_authority_plan_id:
            _fail("execution_previous_plan_mismatch")
        if self.created_at_s <= self.formal_authority_created_at_s:
            _fail("execution_created_at_not_strictly_new")
        if self.created_at_s <= self.planning_frame_timestamp_s:
            _fail("execution_created_at_not_after_intervention")
        if self.valid_until_s <= self.created_at_s:
            _fail("execution_validity_window_invalid")
        if not self.isolated_simulation_only:
            _fail("isolated_simulation_marker_missing")
        forbidden_true = (
            "production_runtime_ack",
            "runtime_publication_allowed",
            "runtime_execution_allowed",
            "online_authority_enabled",
            "physical_outcome_available",
            "reward_available",
            "causal_evidence_available",
        )
        if any(getattr(self, name) is not False for name in forbidden_true):
            _fail("nonproduction_boundary_violated")
        expected_id = _conversion_id(
            arm_spec_sha256=self.arm_spec_sha256,
            planning_frame_transition_sha256=(
                self.planning_frame_transition_sha256
            ),
            solve_source_plan_sha256=(
                self.offline_solve_source_plan_payload_sha256
            ),
            authority_plan_sha256=self.formal_authority_plan_payload_sha256,
            candidate_plan_sha256=self.candidate_plan_payload_sha256,
            execution_plan_id=self.execution_plan_id,
            execution_plan_version=self.execution_plan_version,
        )
        if self.conversion_id != expected_id:
            _fail("conversion_id_mismatch")

    @property
    def fingerprint(self) -> str:
        return canonical_runtime_payload_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "conversion_id": self.conversion_id,
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "pair_id": self.pair_id,
            "seed": int(self.seed),
            "arm_id": self.arm_id,
            "arm_kind": self.arm_kind,
            "isolation_id": self.isolation_id,
            "arm_spec_sha256": self.arm_spec_sha256,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "source_snapshot_lineage_sha256": self.source_snapshot_lineage_sha256,
            "planning_frame_schema_version": self.planning_frame_schema_version,
            "planning_frame_transition_schema_version": (
                self.planning_frame_transition_schema_version
            ),
            "planning_frame_path": self.planning_frame_path,
            "planning_frame_timestamp_s": float(self.planning_frame_timestamp_s),
            "planning_frame_snapshot_sha256": (
                self.planning_frame_snapshot_sha256
            ),
            "planning_frame_transition_sha256": (
                self.planning_frame_transition_sha256
            ),
            "offline_solve_source_plan_id": self.offline_solve_source_plan_id,
            "offline_solve_source_plan_version": int(
                self.offline_solve_source_plan_version
            ),
            "offline_solve_source_plan_schema": (
                self.offline_solve_source_plan_schema
            ),
            "offline_solve_source_plan_payload_sha256": (
                self.offline_solve_source_plan_payload_sha256
            ),
            "offline_solve_source_created_at_s": float(
                self.offline_solve_source_created_at_s
            ),
            "formal_authority_plan_id": self.formal_authority_plan_id,
            "formal_authority_plan_version": int(
                self.formal_authority_plan_version
            ),
            "formal_authority_plan_schema": self.formal_authority_plan_schema,
            "formal_authority_plan_payload_sha256": (
                self.formal_authority_plan_payload_sha256
            ),
            "formal_authority_created_at_s": float(
                self.formal_authority_created_at_s
            ),
            "formal_authority_previous_plan_id": (
                self.formal_authority_previous_plan_id
            ),
            "candidate_plan_id": self.candidate_plan_id,
            "candidate_plan_version": int(self.candidate_plan_version),
            "candidate_plan_schema": self.candidate_plan_schema,
            "candidate_plan_payload_sha256": self.candidate_plan_payload_sha256,
            "candidate_assignment_inventory_sha256": (
                self.candidate_assignment_inventory_sha256
            ),
            "candidate_target_inventory_sha256": (
                self.candidate_target_inventory_sha256
            ),
            "execution_plan_id": self.execution_plan_id,
            "execution_plan_version": int(self.execution_plan_version),
            "execution_plan_schema": self.execution_plan_schema,
            "execution_plan_payload_sha256": self.execution_plan_payload_sha256,
            "execution_assignment_inventory_sha256": (
                self.execution_assignment_inventory_sha256
            ),
            "execution_target_inventory_sha256": (
                self.execution_target_inventory_sha256
            ),
            "authority_semantics_sha256": self.authority_semantics_sha256,
            "previous_plan_id": self.previous_plan_id,
            "created_at_s": float(self.created_at_s),
            "valid_until_s": float(self.valid_until_s),
            "isolated_simulation_only": self.isolated_simulation_only,
            "production_runtime_ack": self.production_runtime_ack,
            "runtime_publication_allowed": self.runtime_publication_allowed,
            "runtime_execution_allowed": self.runtime_execution_allowed,
            "online_authority_enabled": self.online_authority_enabled,
            "physical_outcome_available": self.physical_outcome_available,
            "reward_available": self.reward_available,
            "causal_evidence_available": self.causal_evidence_available,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "IsolatedExecutionPlanConversionEvidence":
        item = _strict_mapping(
            value,
            fields=_CONVERSION_FIELDS,
            code="conversion_fields_mismatch",
        )
        _assert_truth_free(item)
        return cls(
            conversion_id=_required_text(item["conversion_id"], "conversion_id"),
            experiment_id=_required_text(item["experiment_id"], "experiment_id"),
            experiment_version=_required_text(
                item["experiment_version"], "experiment_version"
            ),
            pair_id=_required_text(item["pair_id"], "pair_id"),
            seed=_nonnegative_int(item["seed"], "seed"),
            arm_id=_required_text(item["arm_id"], "arm_id"),
            arm_kind=_required_text(item["arm_kind"], "arm_kind"),
            isolation_id=_required_text(item["isolation_id"], "isolation_id"),
            arm_spec_sha256=_sha256_text(
                item["arm_spec_sha256"], "arm_spec_sha256"
            ),
            execution_receipt_sha256=_sha256_text(
                item["execution_receipt_sha256"], "execution_receipt_sha256"
            ),
            source_snapshot_lineage_sha256=_sha256_text(
                item["source_snapshot_lineage_sha256"],
                "source_snapshot_lineage_sha256",
            ),
            planning_frame_schema_version=_required_text(
                item["planning_frame_schema_version"],
                "planning_frame_schema_version",
            ),
            planning_frame_transition_schema_version=_required_text(
                item["planning_frame_transition_schema_version"],
                "planning_frame_transition_schema_version",
            ),
            planning_frame_path=_required_text(
                item["planning_frame_path"], "planning_frame_path"
            ),
            planning_frame_timestamp_s=_finite_nonnegative(
                item["planning_frame_timestamp_s"],
                "planning_frame_timestamp_s",
            ),
            planning_frame_snapshot_sha256=_sha256_text(
                item["planning_frame_snapshot_sha256"],
                "planning_frame_snapshot_sha256",
            ),
            planning_frame_transition_sha256=_sha256_text(
                item["planning_frame_transition_sha256"],
                "planning_frame_transition_sha256",
            ),
            offline_solve_source_plan_id=_required_text(
                item["offline_solve_source_plan_id"],
                "offline_solve_source_plan_id",
            ),
            offline_solve_source_plan_version=_nonnegative_int(
                item["offline_solve_source_plan_version"],
                "offline_solve_source_plan_version",
            ),
            offline_solve_source_plan_schema=_required_text(
                item["offline_solve_source_plan_schema"],
                "offline_solve_source_plan_schema",
            ),
            offline_solve_source_plan_payload_sha256=_sha256_text(
                item["offline_solve_source_plan_payload_sha256"],
                "offline_solve_source_plan_payload_sha256",
            ),
            offline_solve_source_created_at_s=_finite_nonnegative(
                item["offline_solve_source_created_at_s"],
                "offline_solve_source_created_at_s",
            ),
            formal_authority_plan_id=_required_text(
                item["formal_authority_plan_id"], "formal_authority_plan_id"
            ),
            formal_authority_plan_version=_nonnegative_int(
                item["formal_authority_plan_version"],
                "formal_authority_plan_version",
            ),
            formal_authority_plan_schema=_required_text(
                item["formal_authority_plan_schema"],
                "formal_authority_plan_schema",
            ),
            formal_authority_plan_payload_sha256=_sha256_text(
                item["formal_authority_plan_payload_sha256"],
                "formal_authority_plan_payload_sha256",
            ),
            formal_authority_created_at_s=_finite_nonnegative(
                item["formal_authority_created_at_s"],
                "formal_authority_created_at_s",
            ),
            formal_authority_previous_plan_id=_optional_text(
                item["formal_authority_previous_plan_id"],
                "formal_authority_previous_plan_id",
            ),
            candidate_plan_id=_required_text(
                item["candidate_plan_id"], "candidate_plan_id"
            ),
            candidate_plan_version=_nonnegative_int(
                item["candidate_plan_version"], "candidate_plan_version"
            ),
            candidate_plan_schema=_required_text(
                item["candidate_plan_schema"], "candidate_plan_schema"
            ),
            candidate_plan_payload_sha256=_sha256_text(
                item["candidate_plan_payload_sha256"],
                "candidate_plan_payload_sha256",
            ),
            candidate_assignment_inventory_sha256=_sha256_text(
                item["candidate_assignment_inventory_sha256"],
                "candidate_assignment_inventory_sha256",
            ),
            candidate_target_inventory_sha256=_sha256_text(
                item["candidate_target_inventory_sha256"],
                "candidate_target_inventory_sha256",
            ),
            execution_plan_id=_required_text(
                item["execution_plan_id"], "execution_plan_id"
            ),
            execution_plan_version=_nonnegative_int(
                item["execution_plan_version"], "execution_plan_version"
            ),
            execution_plan_schema=_required_text(
                item["execution_plan_schema"], "execution_plan_schema"
            ),
            execution_plan_payload_sha256=_sha256_text(
                item["execution_plan_payload_sha256"],
                "execution_plan_payload_sha256",
            ),
            execution_assignment_inventory_sha256=_sha256_text(
                item["execution_assignment_inventory_sha256"],
                "execution_assignment_inventory_sha256",
            ),
            execution_target_inventory_sha256=_sha256_text(
                item["execution_target_inventory_sha256"],
                "execution_target_inventory_sha256",
            ),
            authority_semantics_sha256=_sha256_text(
                item["authority_semantics_sha256"], "authority_semantics_sha256"
            ),
            previous_plan_id=_required_text(
                item["previous_plan_id"], "previous_plan_id"
            ),
            created_at_s=_finite_nonnegative(item["created_at_s"], "created_at_s"),
            valid_until_s=_finite_nonnegative(
                item["valid_until_s"], "valid_until_s"
            ),
            isolated_simulation_only=_strict_bool(
                item["isolated_simulation_only"], "isolated_simulation_only"
            ),
            production_runtime_ack=_strict_bool(
                item["production_runtime_ack"], "production_runtime_ack"
            ),
            runtime_publication_allowed=_strict_bool(
                item["runtime_publication_allowed"], "runtime_publication_allowed"
            ),
            runtime_execution_allowed=_strict_bool(
                item["runtime_execution_allowed"], "runtime_execution_allowed"
            ),
            online_authority_enabled=_strict_bool(
                item["online_authority_enabled"], "online_authority_enabled"
            ),
            physical_outcome_available=_strict_bool(
                item["physical_outcome_available"], "physical_outcome_available"
            ),
            reward_available=_strict_bool(
                item["reward_available"], "reward_available"
            ),
            causal_evidence_available=_strict_bool(
                item["causal_evidence_available"], "causal_evidence_available"
            ),
            evidence_kind=_required_text(item["evidence_kind"], "evidence_kind"),
            schema_version=_required_text(item["schema_version"], "schema_version"),
        )


@dataclass(frozen=True, slots=True)
class IsolatedExecutionPlanBuildResult:
    """The new AssignmentPlan and the immutable evidence that created it."""

    plan: AssignmentPlan
    conversion_evidence: IsolatedExecutionPlanConversionEvidence

    def __post_init__(self) -> None:
        plan_hash = _validated_plan_hash(self.plan, "execution_plan_invalid")
        if plan_hash != self.conversion_evidence.execution_plan_payload_sha256:
            _fail("execution_plan_payload_sha256_mismatch")

    @property
    def plan_payload_sha256(self) -> str:
        return self.conversion_evidence.execution_plan_payload_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ISOLATED_EXECUTION_PLAN_SCHEMA_V1,
            "plan": _jsonable(self.plan),
            "conversion_evidence": self.conversion_evidence.to_dict(),
        }


def canonical_isolated_execution_planning_frame_sha256(
    planning_frame_evidence: PlanningFrameEvidence,
) -> str:
    """Hash one complete solve-source to authority-plan frame transition."""

    context = _validate_planning_frame_binding(planning_frame_evidence)
    return canonical_runtime_payload_sha256(
        {
            "schema_version": ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1,
            "planning_frame_schema_version": planning_frame_evidence.schema_version,
            "planning_path": planning_frame_evidence.planning_path,
            "selection_source": planning_frame_evidence.selection_source,
            "timestamp_s": planning_frame_evidence.timestamp_s,
            "forced_replan": planning_frame_evidence.forced_replan,
            "planning_frame_snapshot_sha256": context["frame_snapshot_sha256"],
            "offline_solve_source_plan_id": (
                context["offline_solve_source_plan"].plan_id
            ),
            "offline_solve_source_plan_version": (
                context["offline_solve_source_plan"].version
            ),
            "offline_solve_source_plan_payload_sha256": (
                context["solve_source_plan_sha256"]
            ),
            "formal_authority_plan_id": context["formal_authority_plan"].plan_id,
            "formal_authority_plan_version": (
                context["formal_authority_plan"].version
            ),
            "formal_authority_plan_payload_sha256": (
                context["authority_plan_sha256"]
            ),
        }
    )


def build_isolated_execution_plan(
    *,
    specification: PairedInterventionSpecification,
    arm_specification: PairedInterventionArmSpecification,
    execution_receipt: PairedInterventionExecutionReceipt,
    planning_frame_evidence: PlanningFrameEvidence,
    offline_solve_source_plan: AssignmentPlan,
    formal_authority_plan: AssignmentPlan,
    offline_candidate_plan: AssignmentPlan,
) -> IsolatedExecutionPlanBuildResult:
    """Create one frame-bound plan newer than the current formal authority."""

    context = _validate_conversion_inputs(
        specification=specification,
        arm=arm_specification,
        receipt=execution_receipt,
        planning_frame_evidence=planning_frame_evidence,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        candidate_plan=offline_candidate_plan,
    )
    execution_plan = _build_execution_plan(
        arm=arm_specification,
        pair_id=context["pair_id"],
        planning_frame_evidence=planning_frame_evidence,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        candidate_plan=offline_candidate_plan,
        frame_snapshot_sha256=context["frame_snapshot_sha256"],
        frame_transition_sha256=context["frame_transition_sha256"],
        solve_source_plan_sha256=context["solve_source_plan_sha256"],
        authority_plan_sha256=context["authority_plan_sha256"],
        candidate_plan_sha256=context["candidate_plan_sha256"],
        created_at_s=context["created_at_s"],
        valid_until_s=context["valid_until_s"],
    )
    evidence = _build_conversion_evidence(
        specification=specification,
        arm=arm_specification,
        receipt=execution_receipt,
        pair_id=context["pair_id"],
        planning_frame_evidence=planning_frame_evidence,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        candidate_plan=offline_candidate_plan,
        execution_plan=execution_plan,
        frame_snapshot_sha256=context["frame_snapshot_sha256"],
        frame_transition_sha256=context["frame_transition_sha256"],
        solve_source_plan_sha256=context["solve_source_plan_sha256"],
        authority_plan_sha256=context["authority_plan_sha256"],
        candidate_plan_sha256=context["candidate_plan_sha256"],
        valid_until_s=context["valid_until_s"],
    )
    return IsolatedExecutionPlanBuildResult(
        plan=execution_plan,
        conversion_evidence=evidence,
    )


def validate_isolated_execution_plan_conversion(
    value: IsolatedExecutionPlanConversionEvidence | Mapping[str, Any],
    *,
    specification: PairedInterventionSpecification,
    arm_specification: PairedInterventionArmSpecification,
    execution_receipt: PairedInterventionExecutionReceipt,
    planning_frame_evidence: PlanningFrameEvidence,
    offline_solve_source_plan: AssignmentPlan,
    formal_authority_plan: AssignmentPlan,
    offline_candidate_plan: AssignmentPlan,
    expected_execution_plan: AssignmentPlan,
) -> IsolatedExecutionPlanConversionEvidence:
    """Rebuild and validate one conversion without weakening runtime ACK gates."""

    evidence = (
        value
        if isinstance(value, IsolatedExecutionPlanConversionEvidence)
        else IsolatedExecutionPlanConversionEvidence.from_dict(value)
    )
    expected = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm_specification,
        execution_receipt=execution_receipt,
        planning_frame_evidence=planning_frame_evidence,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        offline_candidate_plan=offline_candidate_plan,
    )
    _validate_execution_plan_contract(
        expected_execution_plan,
        formal_authority_plan=formal_authority_plan,
        candidate_plan=offline_candidate_plan,
        expected_plan=expected.plan,
        intervention_timestamp_s=arm_specification.intervention_timestamp_s,
        valid_until_s=expected.conversion_evidence.valid_until_s,
    )
    actual_plan_hash = _validated_plan_hash(
        expected_execution_plan, "execution_plan_invalid"
    )
    if actual_plan_hash != expected.plan_payload_sha256:
        _fail("execution_plan_payload_mismatch")
    if canonical_runtime_payload_sha256(evidence.to_dict()) != (
        canonical_runtime_payload_sha256(expected.conversion_evidence.to_dict())
    ):
        _fail("conversion_evidence_mismatch")
    return evidence


def _validate_conversion_inputs(
    *,
    specification: PairedInterventionSpecification,
    arm: PairedInterventionArmSpecification,
    receipt: PairedInterventionExecutionReceipt,
    planning_frame_evidence: PlanningFrameEvidence,
    offline_solve_source_plan: AssignmentPlan,
    formal_authority_plan: AssignmentPlan,
    candidate_plan: AssignmentPlan,
) -> dict[str, Any]:
    if not isinstance(specification, PairedInterventionSpecification):
        _fail("specification_type_invalid")
    if not isinstance(arm, PairedInterventionArmSpecification):
        _fail("arm_specification_type_invalid")
    if not isinstance(receipt, PairedInterventionExecutionReceipt):
        _fail("execution_receipt_type_invalid")
    if not isinstance(planning_frame_evidence, PlanningFrameEvidence):
        _fail("planning_frame_type_invalid")
    _assert_truth_free(planning_frame_evidence)
    _assert_truth_free(offline_solve_source_plan)
    _assert_truth_free(formal_authority_plan)
    _assert_truth_free(candidate_plan)
    solve_source_hash = _validated_plan_hash(
        offline_solve_source_plan, "offline_solve_source_plan_invalid"
    )
    authority_hash = _validated_plan_hash(
        formal_authority_plan, "formal_authority_plan_invalid"
    )
    candidate_hash = _validated_plan_hash(candidate_plan, "candidate_plan_invalid")
    frame_context = _validate_planning_frame_binding(planning_frame_evidence)
    if frame_context["solve_source_plan_sha256"] != solve_source_hash:
        _fail("planning_frame_solve_source_payload_mismatch")
    if frame_context["authority_plan_sha256"] != authority_hash:
        _fail("planning_frame_authority_payload_mismatch")
    frame_snapshot_hash = frame_context["frame_snapshot_sha256"]
    frame_transition_hash = canonical_isolated_execution_planning_frame_sha256(
        planning_frame_evidence
    )

    matches = tuple(
        (pair.pair_id, candidate)
        for pair in specification.pairs
        for candidate in (pair.control, pair.treatment)
        if candidate.arm_id == arm.arm_id
    )
    if len(matches) != 1 or matches[0][1].fingerprint != arm.fingerprint:
        _fail("arm_not_in_experiment_specification")
    pair_id = matches[0][0]
    if receipt.pair_id != pair_id:
        _fail("receipt_pair_id_mismatch")
    if receipt.seed != arm.seed or receipt.arm_kind != arm.arm_kind:
        _fail("receipt_arm_identity_mismatch")
    if receipt.arm_spec_sha256 != arm.fingerprint:
        _fail("receipt_arm_spec_sha256_mismatch")
    if receipt.input_snapshot_sha256 != arm.observation_input_snapshot_sha256:
        _fail("receipt_source_snapshot_mismatch")
    if (
        arm.source_plan_id != offline_solve_source_plan.plan_id
        or arm.source_plan_version != offline_solve_source_plan.version
        or arm.expected_previous_plan_version != offline_solve_source_plan.version
        or arm.current_plan_version != offline_solve_source_plan.version
        or arm.source_plan_created_at_s
        != float(offline_solve_source_plan.created_at)
    ):
        _fail("offline_solve_source_plan_lineage_mismatch")
    if (
        receipt.source_plan_version != offline_solve_source_plan.version
        or receipt.expected_previous_plan_version
        != offline_solve_source_plan.version
        or receipt.current_plan_version != offline_solve_source_plan.version
    ):
        _fail("receipt_source_plan_lineage_mismatch")
    if (
        receipt.output_plan_id != candidate_plan.plan_id
        or receipt.output_plan_version != candidate_plan.version
        or receipt.output_plan_payload_sha256 != candidate_hash
    ):
        _fail("receipt_candidate_plan_mismatch")
    if candidate_plan.version not in {
        offline_solve_source_plan.version,
        offline_solve_source_plan.version + 1,
    }:
        _fail("candidate_plan_generation_invalid")
    if candidate_plan.created_at > arm.intervention_timestamp_s:
        _fail("candidate_plan_from_future")
    if (
        offline_solve_source_plan.stale_after_s is not None
        and arm.intervention_timestamp_s
        >= offline_solve_source_plan.created_at
        + offline_solve_source_plan.stale_after_s
    ):
        _fail("offline_solve_source_plan_expired")
    if frame_snapshot_hash != arm.observation_input_snapshot_sha256:
        _fail("planning_frame_snapshot_lineage_mismatch")
    if float(planning_frame_evidence.timestamp_s) != arm.intervention_timestamp_s:
        _fail("planning_frame_timestamp_mismatch")
    metadata = candidate_plan.metadata
    if not isinstance(metadata, Mapping):
        _fail("candidate_plan_metadata_invalid")
    if metadata.get("isolated_simulation") is not True:
        _fail("candidate_isolated_simulation_marker_missing")
    if metadata.get("runtime_execution_allowed") is not False:
        _fail("candidate_runtime_execution_not_forbidden")
    for key in ("ppo_enabled", "online_assist_enabled", "online_authority_enabled"):
        if metadata.get(key) is not False:
            _fail(f"candidate_{key}_must_remain_disabled")
    if metadata.get("paired_intervention_pair_id") not in {None, pair_id}:
        _fail("candidate_pair_lineage_mismatch")
    expected_candidate_lineage = {
        "paired_intervention_pair_id": pair_id,
        "paired_intervention_arm_id": arm.arm_id,
        "paired_intervention_arm_kind": arm.arm_kind,
        "paired_intervention_seed": arm.seed,
        "paired_intervention_arm_spec_sha256": arm.fingerprint,
        "source_snapshot_sha256": arm.observation_input_snapshot_sha256,
        "planning_frame_schema_version": planning_frame_evidence.schema_version,
        "planning_frame_transition_schema_version": (
            ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1
        ),
        "planning_frame_path": planning_frame_evidence.planning_path,
        "planning_frame_timestamp_s": float(planning_frame_evidence.timestamp_s),
        "planning_frame_snapshot_sha256": frame_snapshot_hash,
        "planning_frame_transition_sha256": frame_transition_hash,
        "offline_solve_source_plan_id": offline_solve_source_plan.plan_id,
        "offline_solve_source_plan_version": offline_solve_source_plan.version,
        "offline_solve_source_plan_payload_sha256": solve_source_hash,
        "formal_authority_plan_id": formal_authority_plan.plan_id,
        "formal_authority_plan_version": formal_authority_plan.version,
        "formal_authority_plan_payload_sha256": authority_hash,
    }
    for key, expected in expected_candidate_lineage.items():
        if metadata.get(key) != expected:
            _fail("candidate_source_lineage_mismatch", key)
    if metadata.get("paired_intervention_arm_kind") != arm.arm_kind:
        _fail("candidate_arm_lineage_mismatch")
    if arm.ppo_enabled or arm.online_assist_enabled or arm.online_authority_enabled:
        _fail("experiment_online_authority_enabled")
    if not arm.rule_fallback_enabled or not specification.rule_fallback_enabled:
        _fail("rule_fallback_disabled")

    created_at_s, valid_until_s = _resolve_execution_time_window(
        formal_authority_plan,
        intervention_timestamp_s=arm.intervention_timestamp_s,
        requested_valid_until_s=arm.plan_valid_until_s,
    )
    return {
        "pair_id": pair_id,
        "frame_snapshot_sha256": frame_snapshot_hash,
        "frame_transition_sha256": frame_transition_hash,
        "solve_source_plan_sha256": solve_source_hash,
        "authority_plan_sha256": authority_hash,
        "candidate_plan_sha256": candidate_hash,
        "created_at_s": created_at_s,
        "valid_until_s": valid_until_s,
    }


def _build_execution_plan(
    *,
    arm: PairedInterventionArmSpecification,
    pair_id: str,
    planning_frame_evidence: PlanningFrameEvidence,
    offline_solve_source_plan: AssignmentPlan,
    formal_authority_plan: AssignmentPlan,
    candidate_plan: AssignmentPlan,
    frame_snapshot_sha256: str,
    frame_transition_sha256: str,
    solve_source_plan_sha256: str,
    authority_plan_sha256: str,
    candidate_plan_sha256: str,
    created_at_s: float,
    valid_until_s: float,
) -> AssignmentPlan:
    version = formal_authority_plan.version + 1
    created_at = float(created_at_s)
    valid_until = float(valid_until_s)
    identity_digest = canonical_runtime_payload_sha256(
        {
            "schema_version": ISOLATED_EXECUTION_PLAN_SCHEMA_V1,
            "arm_spec_sha256": arm.fingerprint,
            "planning_frame_transition_sha256": frame_transition_sha256,
            "offline_solve_source_plan_payload_sha256": (
                solve_source_plan_sha256
            ),
            "formal_authority_plan_payload_sha256": authority_plan_sha256,
            "candidate_plan_payload_sha256": candidate_plan_sha256,
            "version": version,
            "previous_plan_id": formal_authority_plan.plan_id,
            "created_at_s": created_at,
            "valid_until_s": valid_until,
        }
    )
    plan_id = (
        f"d3-isolated-exec-{arm.seed}-{arm.arm_kind}-{identity_digest[:16]}"
    )
    source_metadata = dict(formal_authority_plan.metadata)
    metadata = dict(candidate_plan.metadata)
    for key in _AUTHORITY_METADATA_KEYS:
        metadata.pop(key, None)
        if key in source_metadata:
            metadata[key] = source_metadata[key]
    source_node_id = _authority_text(
        source_metadata.get("source_node_id"),
        formal_authority_plan.source_node_id,
    )
    target_node_id = _authority_text(
        source_metadata.get("target_node_id"),
        formal_authority_plan.target_node_id,
    )
    link_type = _authority_text(
        source_metadata.get("link_type"), formal_authority_plan.link_type
    )
    authority_epoch = _first_nonnegative_int(
        source_metadata,
        "authority_epoch",
        "secondary_leader_epoch",
        "regional_max_epoch",
    )
    lease_expires_at_s = _first_finite_number(
        source_metadata,
        "lease_expires_at_s",
        "secondary_lease_expires_at_s",
        "regional_min_lease_expires_at_s",
    )
    if authority_epoch is not None:
        metadata["authority_epoch"] = authority_epoch
    if lease_expires_at_s is not None:
        metadata["lease_expires_at_s"] = lease_expires_at_s
    if source_metadata.get("active_plan_owner") == "secondary":
        metadata["secondary_plan_version"] = version
    conversion_id = _conversion_id(
        arm_spec_sha256=arm.fingerprint,
        planning_frame_transition_sha256=frame_transition_sha256,
        solve_source_plan_sha256=solve_source_plan_sha256,
        authority_plan_sha256=authority_plan_sha256,
        candidate_plan_sha256=candidate_plan_sha256,
        execution_plan_id=plan_id,
        execution_plan_version=version,
    )
    metadata.update(
        {
            "isolated_execution_plan_schema": ISOLATED_EXECUTION_PLAN_SCHEMA_V1,
            "isolated_execution_conversion_id": conversion_id,
            "planning_frame_schema_version": planning_frame_evidence.schema_version,
            "planning_frame_transition_schema_version": (
                ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1
            ),
            "planning_frame_path": planning_frame_evidence.planning_path,
            "planning_frame_timestamp_s": float(
                planning_frame_evidence.timestamp_s
            ),
            "planning_frame_snapshot_sha256": frame_snapshot_sha256,
            "planning_frame_transition_sha256": frame_transition_sha256,
            "offline_solve_source_plan_id": offline_solve_source_plan.plan_id,
            "offline_solve_source_plan_version": (
                offline_solve_source_plan.version
            ),
            "offline_solve_source_plan_payload_sha256": (
                solve_source_plan_sha256
            ),
            "formal_authority_plan_id": formal_authority_plan.plan_id,
            "formal_authority_plan_version": formal_authority_plan.version,
            "formal_authority_plan_payload_sha256": authority_plan_sha256,
            "offline_candidate_plan_id": candidate_plan.plan_id,
            "offline_candidate_plan_version": candidate_plan.version,
            "offline_candidate_plan_payload_sha256": candidate_plan_sha256,
            "paired_intervention_pair_id": pair_id,
            "paired_intervention_arm_id": arm.arm_id,
            "paired_intervention_arm_kind": arm.arm_kind,
            "paired_intervention_seed": arm.seed,
            "source_snapshot_sha256": arm.observation_input_snapshot_sha256,
            "current_plan_id": plan_id,
            "current_plan_version": version,
            "previous_plan_id": formal_authority_plan.plan_id,
            "previous_plan_version": formal_authority_plan.version,
            "supersedes_plan_id": formal_authority_plan.plan_id,
            "supersedes_plan_version": formal_authority_plan.version,
            "plan_version": version,
            "identity_created_at_s": created_at,
            "last_evaluated_at_s": created_at,
            "plan_valid_until_s": valid_until,
            "execution_signature_changed": True,
            "plan_refresh_only": False,
            "evaluation_refresh_only": False,
            "plan_published": True,
            "isolated_plan_published": True,
            "isolated_simulation": True,
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
            "runtime_ack_available": False,
            "runtime_publication_allowed": False,
            "runtime_execution_allowed": False,
            "control_applied_to_production_world": False,
            "online_authority_enabled": False,
            "online_assist_enabled": False,
            "ppo_enabled": False,
            "physical_outcome_available": False,
            "reward_available": False,
            "causal_evidence_available": False,
        }
    )
    assignments = tuple(
        _promote_assignment(
            assignment,
            formal_authority_plan=formal_authority_plan,
            plan_id=plan_id,
            version=version,
            created_at_s=created_at,
            source_node_id=source_node_id,
            link_type=link_type,
        )
        for assignment in candidate_plan.assignments
    )
    execution_plan = replace(
        candidate_plan,
        plan_id=plan_id,
        version=version,
        assignments=assignments,
        created_at=created_at,
        last_changed_at=created_at,
        previous_plan_id=formal_authority_plan.plan_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        link_type=link_type,
        human_authorization_state="offline_not_authorized",
        metadata=metadata,
    )
    _validate_execution_plan_contract(
        execution_plan,
        formal_authority_plan=formal_authority_plan,
        candidate_plan=candidate_plan,
        expected_plan=execution_plan,
        intervention_timestamp_s=arm.intervention_timestamp_s,
        valid_until_s=valid_until,
    )
    return execution_plan


def _promote_assignment(
    assignment: Assignment,
    *,
    formal_authority_plan: AssignmentPlan,
    plan_id: str,
    version: int,
    created_at_s: float,
    source_node_id: str | None,
    link_type: str | None,
) -> Assignment:
    formal_by_binding = {
        (item.resource_id, item.target_id): item
        for item in formal_authority_plan.assignments
    }
    formal = formal_by_binding.get((assignment.resource_id, assignment.target_id))
    target_node_id = (
        None if formal is None else formal.target_node_id
    ) or assignment.target_node_id
    metadata = dict(assignment.metadata)
    formal_metadata = {} if formal is None else dict(formal.metadata)
    for key in _AUTHORITY_METADATA_KEYS:
        metadata.pop(key, None)
        if key in formal_metadata:
            metadata[key] = formal_metadata[key]
    if formal_authority_plan.metadata.get("active_plan_owner") == "secondary":
        metadata["secondary_plan_version"] = version
    metadata.update(
        {
            "current_plan_id": plan_id,
            "current_plan_version": version,
            "previous_plan_id": formal_authority_plan.plan_id,
            "previous_plan_version": formal_authority_plan.version,
            "supersedes_plan_id": formal_authority_plan.plan_id,
            "supersedes_plan_version": formal_authority_plan.version,
            "plan_version": version,
            "identity_created_at_s": created_at_s,
            "last_evaluated_at_s": created_at_s,
            "isolated_simulation": True,
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
            "runtime_publication_allowed": False,
            "runtime_execution_allowed": False,
            "online_authority_enabled": False,
        }
    )
    return replace(
        assignment,
        source_node_id=(
            None if formal is None else formal.source_node_id
        ) or source_node_id,
        target_node_id=target_node_id,
        link_type=(None if formal is None else formal.link_type) or link_type,
        plan_version=version,
        metadata=metadata,
    )


def _build_conversion_evidence(
    *,
    specification: PairedInterventionSpecification,
    arm: PairedInterventionArmSpecification,
    receipt: PairedInterventionExecutionReceipt,
    pair_id: str,
    planning_frame_evidence: PlanningFrameEvidence,
    offline_solve_source_plan: AssignmentPlan,
    formal_authority_plan: AssignmentPlan,
    candidate_plan: AssignmentPlan,
    execution_plan: AssignmentPlan,
    frame_snapshot_sha256: str,
    frame_transition_sha256: str,
    solve_source_plan_sha256: str,
    authority_plan_sha256: str,
    candidate_plan_sha256: str,
    valid_until_s: float,
) -> IsolatedExecutionPlanConversionEvidence:
    execution_hash = _validated_plan_hash(execution_plan, "execution_plan_invalid")
    return IsolatedExecutionPlanConversionEvidence(
        conversion_id=str(execution_plan.metadata["isolated_execution_conversion_id"]),
        experiment_id=specification.experiment_id,
        experiment_version=specification.experiment_version,
        pair_id=pair_id,
        seed=arm.seed,
        arm_id=arm.arm_id,
        arm_kind=arm.arm_kind,
        isolation_id=arm.isolation_id,
        arm_spec_sha256=arm.fingerprint,
        execution_receipt_sha256=receipt.fingerprint,
        source_snapshot_lineage_sha256=_source_lineage_sha256(arm),
        planning_frame_schema_version=planning_frame_evidence.schema_version,
        planning_frame_transition_schema_version=(
            ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1
        ),
        planning_frame_path=planning_frame_evidence.planning_path,
        planning_frame_timestamp_s=float(planning_frame_evidence.timestamp_s),
        planning_frame_snapshot_sha256=frame_snapshot_sha256,
        planning_frame_transition_sha256=frame_transition_sha256,
        offline_solve_source_plan_id=offline_solve_source_plan.plan_id,
        offline_solve_source_plan_version=offline_solve_source_plan.version,
        offline_solve_source_plan_schema=offline_solve_source_plan.plan_schema,
        offline_solve_source_plan_payload_sha256=solve_source_plan_sha256,
        offline_solve_source_created_at_s=offline_solve_source_plan.created_at,
        formal_authority_plan_id=formal_authority_plan.plan_id,
        formal_authority_plan_version=formal_authority_plan.version,
        formal_authority_plan_schema=formal_authority_plan.plan_schema,
        formal_authority_plan_payload_sha256=authority_plan_sha256,
        formal_authority_created_at_s=formal_authority_plan.created_at,
        formal_authority_previous_plan_id=formal_authority_plan.previous_plan_id,
        candidate_plan_id=candidate_plan.plan_id,
        candidate_plan_version=candidate_plan.version,
        candidate_plan_schema=candidate_plan.plan_schema,
        candidate_plan_payload_sha256=candidate_plan_sha256,
        candidate_assignment_inventory_sha256=_candidate_assignment_inventory_sha256(
            candidate_plan
        ),
        candidate_target_inventory_sha256=_target_inventory_sha256(candidate_plan),
        execution_plan_id=execution_plan.plan_id,
        execution_plan_version=execution_plan.version,
        execution_plan_schema=execution_plan.plan_schema,
        execution_plan_payload_sha256=execution_hash,
        execution_assignment_inventory_sha256=_execution_assignment_inventory_sha256(
            execution_plan
        ),
        execution_target_inventory_sha256=_target_inventory_sha256(execution_plan),
        authority_semantics_sha256=_authority_semantics_sha256(execution_plan),
        previous_plan_id=execution_plan.previous_plan_id or "",
        created_at_s=execution_plan.created_at,
        valid_until_s=valid_until_s,
    )


def _validate_execution_plan_contract(
    plan: AssignmentPlan,
    *,
    formal_authority_plan: AssignmentPlan,
    candidate_plan: AssignmentPlan,
    expected_plan: AssignmentPlan,
    intervention_timestamp_s: float,
    valid_until_s: float,
) -> None:
    if plan.plan_id in {formal_authority_plan.plan_id, candidate_plan.plan_id}:
        _fail("execution_plan_id_not_new")
    if plan.version != formal_authority_plan.version + 1:
        _fail("execution_plan_version_not_strictly_new")
    if plan.previous_plan_id != formal_authority_plan.plan_id:
        _fail("execution_previous_plan_mismatch")
    if plan.created_at <= formal_authority_plan.created_at:
        _fail("execution_created_at_not_strictly_new")
    if plan.created_at <= intervention_timestamp_s:
        _fail("execution_created_at_not_after_intervention")
    if valid_until_s <= plan.created_at:
        _fail("execution_validity_window_invalid")
    if plan.resource_count != candidate_plan.resource_count:
        _fail("execution_resource_count_changed")
    if plan.target_count != candidate_plan.target_count:
        _fail("execution_target_count_changed")
    if plan.unassigned_target_ids != candidate_plan.unassigned_target_ids:
        _fail("execution_unassigned_inventory_changed")
    if plan.incomplete_target_ids != candidate_plan.incomplete_target_ids:
        _fail("execution_incomplete_inventory_changed")
    if plan.coalitions != candidate_plan.coalitions:
        _fail("execution_coalition_inventory_changed")
    if plan.demand_summaries != candidate_plan.demand_summaries:
        _fail("execution_demand_summary_inventory_changed")
    if _binding_semantics(plan) != _binding_semantics(candidate_plan):
        _fail("execution_assignment_inventory_changed")
    if _authority_semantics(plan) != _authority_semantics(expected_plan):
        _fail("execution_authority_semantics_changed")
    metadata = plan.metadata
    required = {
        "isolated_simulation": True,
        "isolated_simulation_only": True,
        "production_runtime_ack": False,
        "runtime_publication_allowed": False,
        "runtime_execution_allowed": False,
        "online_authority_enabled": False,
    }
    if not isinstance(metadata, Mapping) or any(
        metadata.get(key) is not value for key, value in required.items()
    ):
        _fail("execution_nonproduction_boundary_invalid")
    if metadata.get("current_plan_id") != plan.plan_id:
        _fail("execution_current_plan_id_mismatch")
    if metadata.get("current_plan_version") != plan.version:
        _fail("execution_current_plan_version_mismatch")
    if float(metadata.get("plan_valid_until_s", -1.0)) != float(valid_until_s):
        _fail("execution_valid_until_mismatch")
    _assert_truth_free(plan)


def _binding_semantics(plan: AssignmentPlan) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        sorted(
            (
                item.target_id,
                item.resource_id,
                float(item.cost),
                canonical_runtime_payload_sha256(item.cost_breakdown),
                item.feasibility_state,
                item.stale_after_s,
                item.terminal_feedback_state,
                item.duplicate_terminal_lock_risk,
                item.coalition_id,
                item.coalition_version,
                item.member_role,
                item.wave_id,
                item.arrival_window_start_s,
                item.arrival_window_end_s,
                item.required_resource_count,
                item.terminal_authorization_scope,
                item.arrival_coordination_required,
            )
            for item in plan.assignments
        )
    )


def _candidate_assignment_inventory_sha256(plan: AssignmentPlan) -> str:
    return canonical_runtime_payload_sha256(_binding_semantics(plan))


def _execution_assignment_inventory_sha256(plan: AssignmentPlan) -> str:
    return canonical_runtime_payload_sha256(_binding_semantics(plan))


def _target_inventory_sha256(plan: AssignmentPlan) -> str:
    return canonical_runtime_payload_sha256(
        {
            "resource_count": plan.resource_count,
            "target_count": plan.target_count,
            "unassigned_target_ids": plan.unassigned_target_ids,
            "incomplete_target_ids": plan.incomplete_target_ids,
            "coalitions": plan.coalitions,
            "demand_summaries": plan.demand_summaries,
        }
    )


def _authority_semantics(plan: AssignmentPlan) -> Mapping[str, Any]:
    metadata = plan.metadata if isinstance(plan.metadata, Mapping) else {}
    return {
        "source_node_id": plan.source_node_id,
        "target_node_id": plan.target_node_id,
        "link_type": plan.link_type,
        "metadata": {
            key: metadata[key]
            for key in sorted(_AUTHORITY_METADATA_KEYS)
            if key in metadata
        },
    }


def _authority_semantics_sha256(plan: AssignmentPlan) -> str:
    return canonical_runtime_payload_sha256(_authority_semantics(plan))


def _validate_planning_frame_binding(
    evidence: PlanningFrameEvidence,
) -> dict[str, Any]:
    if not isinstance(evidence, PlanningFrameEvidence):
        _fail("planning_frame_type_invalid")
    if not evidence.available:
        _fail("planning_frame_unavailable", evidence.reason)
    if evidence.timestamp_s is None or not isfinite(float(evidence.timestamp_s)):
        _fail("planning_frame_timestamp_invalid")
    if evidence.previous_plan is None:
        _fail("planning_frame_solve_source_missing")
    if evidence.plan is None:
        _fail("planning_frame_authority_plan_missing")
    _assert_truth_free(evidence)
    solve_source = evidence.previous_plan
    authority = evidence.plan
    solve_hash = _validated_plan_hash(
        solve_source, "planning_frame_solve_source_invalid"
    )
    authority_hash = _validated_plan_hash(
        authority, "planning_frame_authority_plan_invalid"
    )
    if evidence.previous_plan_version != solve_source.version:
        _fail("planning_frame_previous_version_mismatch")
    if evidence.plan_id != authority.plan_id:
        _fail("planning_frame_plan_id_mismatch")
    if evidence.plan_version != authority.version:
        _fail("planning_frame_plan_version_mismatch")
    _validate_recorded_frame_transition(
        offline_solve_source_plan_id=solve_source.plan_id,
        offline_solve_source_plan_version=solve_source.version,
        formal_authority_plan_id=authority.plan_id,
        formal_authority_plan_version=authority.version,
        formal_authority_previous_plan_id=authority.previous_plan_id,
    )
    if authority.created_at < solve_source.created_at:
        _fail("planning_frame_authority_created_before_solve_source")
    if authority.created_at > float(evidence.timestamp_s):
        _fail("planning_frame_authority_from_future")
    try:
        from .offline_intervention_execution import (
            canonical_planning_frame_snapshot_sha256,
        )

        snapshot_hash = canonical_planning_frame_snapshot_sha256(evidence)
    except (TypeError, ValueError) as exc:
        _fail("planning_frame_snapshot_invalid", str(exc))
    return {
        "frame_snapshot_sha256": snapshot_hash,
        "solve_source_plan_sha256": solve_hash,
        "authority_plan_sha256": authority_hash,
        "offline_solve_source_plan": solve_source,
        "formal_authority_plan": authority,
    }


def _validate_recorded_frame_transition(
    *,
    offline_solve_source_plan_id: str,
    offline_solve_source_plan_version: int,
    formal_authority_plan_id: str,
    formal_authority_plan_version: int,
    formal_authority_previous_plan_id: str | None,
) -> None:
    solve_id = _required_text(
        offline_solve_source_plan_id, "offline_solve_source_plan_id"
    )
    authority_id = _required_text(
        formal_authority_plan_id, "formal_authority_plan_id"
    )
    solve_version = _nonnegative_int(
        offline_solve_source_plan_version,
        "offline_solve_source_plan_version",
    )
    authority_version = _nonnegative_int(
        formal_authority_plan_version,
        "formal_authority_plan_version",
    )
    previous_id = _optional_text(
        formal_authority_previous_plan_id,
        "formal_authority_previous_plan_id",
    )
    if authority_version == solve_version:
        if authority_id != solve_id:
            _fail("planning_frame_same_generation_id_mismatch")
        return
    if authority_version != solve_version + 1:
        _fail("planning_frame_authority_version_jump")
    if previous_id != solve_id:
        _fail("planning_frame_authority_previous_plan_mismatch")


def _resolve_execution_time_window(
    plan: AssignmentPlan,
    *,
    intervention_timestamp_s: float,
    requested_valid_until_s: float,
) -> tuple[float, float]:
    intervention = _finite_nonnegative(
        intervention_timestamp_s, "intervention_timestamp_s"
    )
    requested_valid_until = _finite_nonnegative(
        requested_valid_until_s, "requested_valid_until_s"
    )
    created_at = nextafter(max(float(plan.created_at), intervention), inf)
    if not isfinite(created_at):
        _fail("execution_created_at_not_representable")
    metadata = plan.metadata if isinstance(plan.metadata, Mapping) else {}
    deadlines = [requested_valid_until]
    lease = _first_finite_number(
        metadata,
        "lease_expires_at_s",
        "secondary_lease_expires_at_s",
        "regional_min_lease_expires_at_s",
    )
    if lease is not None:
        deadlines.append(lease)
    if plan.stale_after_s is not None:
        deadlines.append(
            float(plan.created_at)
            + _finite_nonnegative(plan.stale_after_s, "stale_after_s")
        )
    metadata_valid_until = metadata.get("plan_valid_until_s")
    if metadata_valid_until is not None:
        deadlines.append(
            _finite_nonnegative(metadata_valid_until, "plan_valid_until_s")
        )
    valid_until = min(deadlines)
    if valid_until <= created_at:
        if lease is not None and lease <= created_at:
            _fail("formal_authority_lease_invalid")
        _fail("execution_validity_window_invalid")
    _validate_authority_window(
        plan,
        created_at_s=created_at,
        valid_until_s=valid_until,
    )
    return created_at, valid_until


def _validate_authority_window(
    plan: AssignmentPlan, *, created_at_s: float, valid_until_s: float
) -> None:
    metadata = plan.metadata if isinstance(plan.metadata, Mapping) else {}
    owner = metadata.get("active_plan_owner", metadata.get("plan_owner"))
    if owner is not None:
        _required_text(owner, "formal authority owner")
        owner_node = metadata.get("owner_node_id", plan.source_node_id)
        _required_text(owner_node, "formal authority owner_node_id")
    epoch = _first_nonnegative_int(
        metadata,
        "authority_epoch",
        "secondary_leader_epoch",
        "regional_max_epoch",
    )
    if epoch is not None and epoch < 0:
        _fail("formal_authority_epoch_invalid")
    lease = _first_finite_number(
        metadata,
        "lease_expires_at_s",
        "secondary_lease_expires_at_s",
        "regional_min_lease_expires_at_s",
    )
    if lease is not None and (
        lease <= created_at_s or valid_until_s > lease
    ):
        _fail("formal_authority_lease_invalid")
    deadlines: list[float] = []
    if plan.stale_after_s is not None:
        stale_after = _finite_nonnegative(plan.stale_after_s, "stale_after_s")
        deadlines.append(float(plan.created_at) + stale_after)
    metadata_valid_until = metadata.get("plan_valid_until_s")
    if metadata_valid_until is not None:
        deadlines.append(
            _finite_nonnegative(metadata_valid_until, "plan_valid_until_s")
        )
    if any(
        deadline <= created_at_s or valid_until_s > deadline
        for deadline in deadlines
    ):
        _fail("formal_authority_validity_window_insufficient")


def _source_lineage_sha256(arm: PairedInterventionArmSpecification) -> str:
    return canonical_runtime_payload_sha256(
        {
            "scenario_version": arm.scenario_version,
            "scenario_config_sha256": arm.scenario_config_sha256,
            "initial_world_state_sha256": arm.initial_world_state_sha256,
            "input_snapshot_schema_version": arm.input_snapshot_schema_version,
            "observation_input_snapshot_sha256": (
                arm.observation_input_snapshot_sha256
            ),
            "d1_d2_lineage_contract_version": (
                arm.d1_d2_lineage_contract_version
            ),
            "d1_d2_lineage_contract_sha256": (
                arm.d1_d2_lineage_contract_sha256
            ),
        }
    )


def _conversion_id(
    *,
    arm_spec_sha256: str,
    planning_frame_transition_sha256: str,
    solve_source_plan_sha256: str,
    authority_plan_sha256: str,
    candidate_plan_sha256: str,
    execution_plan_id: str,
    execution_plan_version: int,
) -> str:
    digest = canonical_runtime_payload_sha256(
        {
            "arm_spec_sha256": arm_spec_sha256,
            "planning_frame_transition_sha256": (
                planning_frame_transition_sha256
            ),
            "solve_source_plan_sha256": solve_source_plan_sha256,
            "authority_plan_sha256": authority_plan_sha256,
            "candidate_plan_sha256": candidate_plan_sha256,
            "execution_plan_id": execution_plan_id,
            "execution_plan_version": execution_plan_version,
        }
    )
    return f"d3-isolated-conversion-{digest[:24]}"


def _validated_plan_hash(plan: AssignmentPlan, code: str) -> str:
    try:
        return validated_assignment_plan_payload_sha256(plan)
    except AssignmentPlanRuntimeAckError as exc:
        _fail(code, f"{code}:{exc.code}")


def _first_nonnegative_int(metadata: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in metadata and metadata[key] is not None:
            return _nonnegative_int(metadata[key], key)
    return None


def _first_finite_number(metadata: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in metadata and metadata[key] is not None:
            return _finite_nonnegative(metadata[key], key)
    return None


def _authority_text(*values: Any) -> str | None:
    for value in values:
        if value is not None:
            return _required_text(value, "authority text")
    return None


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _assert_truth_free(getattr(value, item.name), f"{path}.{item.name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_TRUTH_KEYS:
                _fail("truth_field_forbidden", f"{path}.{key}")
            _assert_truth_free(item, f"{path}.{key}")
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            _assert_truth_free(item, f"{path}[{index}]")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _strict_mapping(
    value: Any, *, fields: frozenset[str], code: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code)
    actual = frozenset(str(key) for key in value)
    if actual != fields or any(not isinstance(key, str) for key in value):
        _fail(code)
    return value


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("text_required", f"{name} must be non-empty text")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _sha256_text(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if len(text) != 64 or any(char not in _HEX_DIGITS for char in text):
        _fail("sha256_invalid", f"{name} must be lowercase SHA-256")
    return text


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("nonnegative_integer_required", name)
    return value


def _finite_nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool):
        _fail("finite_nonnegative_required", name)
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        _fail("finite_nonnegative_required", name)
    if not isfinite(result) or result < 0.0:
        _fail("finite_nonnegative_required", name)
    return result


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        _fail("boolean_required", name)
    return value


def _fail(code: str, message: str | None = None) -> None:
    raise IsolatedExecutionPlanError(code, message)
