"""Fail-closed attribution contract for adopted D3 runtime plan windows.

The adapter joins one already-verified D3 runtime ACK to one hash-bound D6
observed-outcome window.  It deliberately keeps command publication, applied
control, observed diagnostics, paired evidence, counterfactual evidence, and
causal attribution separate.  Observed proximity or distance progress is not
promoted to a formal PPO reward.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
import json
from math import isfinite
import re
from typing import Any

from .runtime_plan_ack import (
    AssignmentPlanRuntimeAckEvidence,
    RuntimePlanBindingAck,
)


D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1 = (
    "d3_runtime_plan_window_reward_evidence_v1"
)
D3_RUNTIME_REWARD_COMPONENT_POLICY_V1 = (
    "d3_runtime_reward_component_availability_policy_v1"
)
D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V1 = "d6.runtime-plan-outcome-join.v1"
D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V2 = "d6.runtime-plan-outcome-join.v2"
D6_RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_V1 = (
    "bounded_assigned_pair_best_distance_progress_v1"
)

FORMAL_REWARD_COMPONENT_NAMES = (
    "high_threat_coverage",
    "rule_total_cost",
    "unmet_demand_slots",
    "reassignment_churn",
    "plan_expired",
    "safety_rejections",
)

_EVIDENCE_KINDS = frozenset(
    {
        "command",
        "ack_applied",
        "observed_outcome",
        "paired",
        "counterfactual",
        "causal",
        "formal_reward",
        "reward_component",
    }
)
_D6_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "evaluation_date",
        "evaluation_mode",
        "episode",
        "source_artifacts",
        "runtime_ack_evidence",
        "binding_windows",
        "observed_diagnostics",
        "admission",
        "audit",
    }
)
_D6_OPTIONAL_TOP_LEVEL_FIELDS = frozenset(
    {
        "d2_identity_recovery_config_provenance",
        "offline_observation_truth_disposition",
    }
)
_D6_EPISODE_FIELDS = frozenset(
    {
        "episode_id",
        "scenario_name",
        "scenario_version",
        "seed",
        "target_count",
        "resource_count",
        "duration_s",
        "physics_dt_s",
        "manifest_sha256",
        "scenario_config_sha256",
        "config_canonical_sha256",
    }
)
_D6_RUNTIME_ACK_SUMMARY_FIELDS = frozenset(
    {
        "available",
        "reason",
        "ack_count",
        "unique_occurrence_count",
        "new_plan_identity_occurrence_count",
        "same_identity_refresh_occurrence_count",
        "same_identity_evaluation_refresh_occurrence_count",
        "same_identity_plan_refresh_occurrence_count",
        "binding_count",
        "source_sequence_and_payload_hash_verified",
        "online_truth_use_count",
        "d3_learning_applied_ack_count",
        "d4_regional_applied_ack_count",
    }
)
_D6_OBSERVED_DIAGNOSTIC_FIELDS = frozenset(
    {
        "bounded_pair_progress_name",
        "bounded_pair_progress_available_count",
        "assigned_pair_five_meter_event_count",
        "same_resource_other_target_event_count",
        "formal_reward_available",
        "formal_reward",
        "formal_reward_reason",
        "counterfactual_available",
        "counterfactual",
        "counterfactual_reason",
        "causal_attribution_available",
        "causal_attribution",
        "causal_attribution_reason",
    }
)
_D6_ADMISSION_FIELDS = frozenset(
    {
        "runtime_ack_join_available",
        "observed_pair_diagnostic_available",
        "formal_same_seed_paired_shadow_available",
        "held_out_seed_performance_available",
        "formal_learning_adoption_outcome_available",
        "ppo_allowed",
        "assist_allowed",
        "authority_allowed",
        "rule_fallback_required",
        "status",
        "promotion_blockers",
    }
)
_D6_OPTIONAL_ADMISSION_FIELDS = frozenset(
    {
        "identity_recovery_config_provenance_reason",
        "identity_recovery_config_provenance_required",
        "identity_recovery_config_provenance_verified",
    }
)
_D6_AUDIT_FIELDS = frozenset(
    {
        "passed",
        "fail_closed",
        "source_mutation_performed",
        "frozen_900_episode_data_modified",
        "violation_count",
        "violations",
    }
)
_D6_SOURCE_ARTIFACT_NAMES = frozenset(
    {
        "online_observations",
        "d2_identity_evaluation",
        "d2_identity_manifest",
        "d2_online_d1_records",
        "d2_online_d2_records",
        "d2_observation_truth_labels",
        "d2_identity_evidence",
        "offline_truth_state",
        "offline_proximity_intercepts",
        "episode_manifest",
        "scenario_config",
    }
)
_D6_WINDOW_FIELDS = frozenset(
    {
        "ack_bus_sequence",
        "decision_id",
        "occurrence_id",
        "occurrence_index",
        "adoption_kind",
        "plan_id",
        "plan_version",
        "execution_signature_sha256",
        "resource_id",
        "global_track_id",
        "coalition_id",
        "coalition_version",
        "member_role",
        "window_start_timestamp",
        "window_end_timestamp",
        "window_interval",
        "identity_mapping",
        "state_window_available",
        "state_window_reason",
        "state_sample_count",
        "first_state_timestamp",
        "last_state_timestamp",
        "start_3d_distance_m",
        "end_3d_distance_m",
        "min_3d_distance_m",
        "distance_progress_m",
        "best_distance_progress_m",
        "assigned_pair_proximity_event_observed",
        "assigned_pair_proximity_events",
        "other_target_proximity_event_observed",
        "other_target_proximity_events",
        "guidance_command_present",
        "guidance_mode",
        "guidance_gate_reason",
        "control_applied_to_world",
        "held",
        "d3_learning_evidence",
        "d4_regional_hint_evidence",
        "bounded_pair_progress_diagnostic",
        "formal_d3_ppo_reward_available",
        "formal_d3_ppo_reward",
        "formal_d3_ppo_reward_reason",
        "counterfactual_available",
        "counterfactual",
        "counterfactual_reason",
        "causal_attribution_available",
        "causal_attribution",
        "causal_attribution_reason",
    }
)
_ADOPTION_KINDS = frozenset(
    {
        "new_plan_identity",
        "same_identity_evaluation_refresh",
        "same_identity_plan_refresh",
    }
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
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
_SHA256_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_RUNTIME_ACK_CLASS_IDENTITIES = frozenset(
    {
        (
            "d3_assignment_planner.runtime_plan_ack",
            "AssignmentPlanRuntimeAckEvidence",
        ),
        (
            "research_modules.d3_assignment_planner.src."
            "d3_assignment_planner.runtime_plan_ack",
            "AssignmentPlanRuntimeAckEvidence",
        ),
        (
            "research_modules.d3_assignment_planner."
            "d3_assignment_planner.runtime_plan_ack",
            "AssignmentPlanRuntimeAckEvidence",
        ),
    }
)
_RUNTIME_ACK_FIELD_NAMES = frozenset(
    item.name for item in fields(AssignmentPlanRuntimeAckEvidence)
)


class RuntimePlanRewardEvidenceError(ValueError):
    """Stable fail-closed error raised for an invalid attribution input."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(message or self.code)


@dataclass(frozen=True, slots=True)
class EvidenceAvailability:
    """One scalar evidence item with explicit availability and provenance."""

    name: str
    evidence_kind: str
    available: bool
    value: bool | int | float | str | None
    reason: str | None
    provenance_sha256: str | None
    formal_reward_eligible: bool = False

    def __post_init__(self) -> None:
        name = _required_text(self.name, "evidence name")
        kind = _required_text(self.evidence_kind, "evidence kind")
        if kind not in _EVIDENCE_KINDS:
            _fail("unsupported_evidence_kind", f"unsupported evidence kind: {kind}")
        available = _strict_bool(self.available, "evidence available")
        eligible = _strict_bool(
            self.formal_reward_eligible,
            "evidence formal_reward_eligible",
        )
        reason = _optional_text(self.reason, "evidence reason")
        digest = _optional_sha256(
            self.provenance_sha256,
            "evidence provenance SHA-256",
        )
        value = self.value
        if available:
            if value is None or reason is not None or digest is None:
                _fail(
                    "available_evidence_incomplete",
                    "available evidence requires value, null reason, and provenance",
                )
            _validate_scalar(value, "evidence value")
        else:
            if value is not None or reason is None:
                _fail(
                    "unavailable_evidence_invalid",
                    "unavailable evidence requires null value and a reason",
                )
        if eligible:
            _fail(
                "formal_reward_eligibility_not_admitted",
                "v1 observed-outcome evidence cannot assert reward eligibility",
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "evidence_kind", kind)
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "provenance_sha256", digest)
        object.__setattr__(self, "formal_reward_eligible", eligible)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "evidence_kind": self.evidence_kind,
            "available": self.available,
            "value": self.value,
            "reason": self.reason,
            "provenance_sha256": self.provenance_sha256,
            "formal_reward_eligible": self.formal_reward_eligible,
        }


@dataclass(frozen=True, slots=True)
class RuntimePlanWindowReference:
    """Identity, ordering, time-window, and hash binding for one assignment."""

    episode_id: str
    scenario_version: str
    seed: int
    plan_id: str
    plan_version: int
    active_plan_owner: str
    owner_node_id: str
    authority_epoch: int | None
    resource_id: str
    global_track_id: str
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    source_plan_bus_sequence: int
    source_plan_payload_sha256: str
    consumption_bus_sequence: int
    consumption_payload_sha256: str
    ack_bus_sequence: int
    plan_created_at: float
    command_timestamp: float
    consumption_timestamp: float
    ack_timestamp: float
    occurrence_id: str
    occurrence_index: int
    adoption_kind: str
    execution_signature_sha256: str
    window_start_timestamp: float
    window_end_timestamp: float
    window_interval: str
    runtime_ack_evidence_sha256: str
    outcome_join_payload_sha256: str
    source_artifact_sha256s: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _required_text(self.episode_id, "episode_id")
        _required_text(self.scenario_version, "scenario_version")
        _nonnegative_int(self.seed, "seed")
        _required_text(self.plan_id, "plan_id")
        _positive_int(self.plan_version, "plan_version")
        _required_text(self.active_plan_owner, "active_plan_owner")
        _required_text(self.owner_node_id, "owner_node_id")
        _optional_nonnegative_int(self.authority_epoch, "authority_epoch")
        _required_text(self.resource_id, "resource_id")
        _required_text(self.global_track_id, "global_track_id")
        _optional_text(self.coalition_id, "coalition_id")
        _optional_nonnegative_int(self.coalition_version, "coalition_version")
        _required_text(self.member_role, "member_role")
        source = _positive_int(
            self.source_plan_bus_sequence,
            "source plan bus sequence",
        )
        consumption = _positive_int(
            self.consumption_bus_sequence,
            "consumption bus sequence",
        )
        ack = _positive_int(self.ack_bus_sequence, "ACK bus sequence")
        if not source < consumption < ack:
            _fail("runtime_sequence_order_invalid")
        _sha256(self.source_plan_payload_sha256, "source plan payload SHA-256")
        _sha256(self.consumption_payload_sha256, "consumption payload SHA-256")
        _sha256(self.runtime_ack_evidence_sha256, "runtime ACK evidence SHA-256")
        _sha256(self.outcome_join_payload_sha256, "outcome join SHA-256")
        _sha256(self.execution_signature_sha256, "execution signature SHA-256")
        created = _finite_nonnegative(self.plan_created_at, "plan creation time")
        command = _finite_nonnegative(self.command_timestamp, "command timestamp")
        consumed = _finite_nonnegative(
            self.consumption_timestamp,
            "consumption timestamp",
        )
        acknowledged = _finite_nonnegative(self.ack_timestamp, "ACK timestamp")
        start = _finite_nonnegative(
            self.window_start_timestamp,
            "window start timestamp",
        )
        end = _finite_nonnegative(
            self.window_end_timestamp,
            "window end timestamp",
        )
        if created > command or not command == consumed == acknowledged == start:
            _fail("runtime_timestamp_binding_mismatch")
        if end <= start:
            _fail("nonpositive_binding_window")
        interval = _required_text(self.window_interval, "window interval")
        if interval not in {"left_closed_right_open", "closed"}:
            _fail("unsupported_window_interval")
        occurrence = _positive_int(self.occurrence_index, "occurrence index")
        adoption = _required_text(self.adoption_kind, "adoption kind")
        if adoption not in _ADOPTION_KINDS:
            _fail("unsupported_adoption_kind")
        if (occurrence == 1) != (adoption == "new_plan_identity"):
            _fail("refresh_semantics_mismatch")
        _required_text(self.occurrence_id, "occurrence_id")
        artifacts = dict(self.source_artifact_sha256s)
        if len(artifacts) != len(self.source_artifact_sha256s) or set(artifacts) != (
            _D6_SOURCE_ARTIFACT_NAMES
        ):
            _fail("source_artifact_inventory_mismatch")
        for name, digest in artifacts.items():
            _sha256(digest, f"source artifact SHA-256 {name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "scenario_version": self.scenario_version,
            "seed": self.seed,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "active_plan_owner": self.active_plan_owner,
            "owner_node_id": self.owner_node_id,
            "authority_epoch": self.authority_epoch,
            "resource_id": self.resource_id,
            "global_track_id": self.global_track_id,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
            "source_plan_bus_sequence": self.source_plan_bus_sequence,
            "source_plan_payload_sha256": self.source_plan_payload_sha256,
            "consumption_bus_sequence": self.consumption_bus_sequence,
            "consumption_payload_sha256": self.consumption_payload_sha256,
            "ack_bus_sequence": self.ack_bus_sequence,
            "plan_created_at": self.plan_created_at,
            "command_timestamp": self.command_timestamp,
            "consumption_timestamp": self.consumption_timestamp,
            "ack_timestamp": self.ack_timestamp,
            "occurrence_id": self.occurrence_id,
            "occurrence_index": self.occurrence_index,
            "adoption_kind": self.adoption_kind,
            "execution_signature_sha256": self.execution_signature_sha256,
            "window_start_timestamp": self.window_start_timestamp,
            "window_end_timestamp": self.window_end_timestamp,
            "window_interval": self.window_interval,
            "runtime_ack_evidence_sha256": self.runtime_ack_evidence_sha256,
            "outcome_join_payload_sha256": self.outcome_join_payload_sha256,
            "source_artifact_sha256s": {
                name: digest for name, digest in self.source_artifact_sha256s
            },
        }


@dataclass(frozen=True, slots=True)
class RuntimePlanWindowRewardEvidence:
    """Truth-free D3 view of one adopted plan window and reward availability."""

    reference: RuntimePlanWindowReference
    command: EvidenceAvailability
    ack_applied: EvidenceAvailability
    observed_outcomes: tuple[EvidenceAvailability, ...]
    paired_evidence: EvidenceAvailability
    counterfactual_evidence: EvidenceAvailability
    causal_evidence: EvidenceAvailability
    raw_reward_components: tuple[EvidenceAvailability, ...]
    formal_reward: EvidenceAvailability
    status: str = "observed_outcome_only_reward_unavailable"
    schema_version: str = D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1
    reward_component_policy: str = D3_RUNTIME_REWARD_COMPONENT_POLICY_V1

    def __post_init__(self) -> None:
        if self.schema_version != D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1:
            _fail("reward_evidence_schema_mismatch")
        if self.reward_component_policy != D3_RUNTIME_REWARD_COMPONENT_POLICY_V1:
            _fail("reward_component_policy_mismatch")
        if self.status != "observed_outcome_only_reward_unavailable":
            _fail("reward_evidence_status_mismatch")
        expected_observed = (
            "bounded_assigned_pair_best_distance_progress",
            "assigned_pair_five_meter_event",
            "same_resource_other_target_five_meter_event",
        )
        if tuple(item.name for item in self.observed_outcomes) != expected_observed:
            _fail("observed_outcome_inventory_mismatch")
        expected_layers = (
            (self.command, "assignment_command_published", "command"),
            (self.ack_applied, "binding_control_applied", "ack_applied"),
            (
                self.paired_evidence,
                "same_seed_paired_assignment_outcome",
                "paired",
            ),
            (
                self.counterfactual_evidence,
                "counterfactual_assignment_outcome",
                "counterfactual",
            ),
            (
                self.causal_evidence,
                "causal_assignment_attribution",
                "causal",
            ),
            (self.formal_reward, "formal_d3_runtime_reward", "formal_reward"),
        )
        for item, name, kind in expected_layers:
            if item.name != name or item.evidence_kind != kind:
                _fail("evidence_layer_identity_mismatch")
        if not self.command.available:
            _fail("command_evidence_unavailable")
        if any(item.formal_reward_eligible for item in self.observed_outcomes):
            _fail("observed_outcome_promoted_to_reward")
        if tuple(item.name for item in self.raw_reward_components) != (
            FORMAL_REWARD_COMPONENT_NAMES
        ):
            _fail("raw_reward_component_inventory_mismatch")
        if any(
            item.evidence_kind != "reward_component"
            for item in self.raw_reward_components
        ):
            _fail("raw_reward_component_kind_mismatch")
        if any(item.available for item in self.raw_reward_components):
            _fail("formal_reward_component_unexpectedly_available")
        if self.formal_reward.available:
            _fail("formal_reward_unexpectedly_available")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "reward_component_policy": self.reward_component_policy,
            "status": self.status,
            "reference": self.reference.to_dict(),
            "evidence_layers": {
                "command": self.command.to_dict(),
                "ack_applied": self.ack_applied.to_dict(),
                "observed_outcome": {
                    item.name: item.to_dict() for item in self.observed_outcomes
                },
                "paired": self.paired_evidence.to_dict(),
                "counterfactual": self.counterfactual_evidence.to_dict(),
                "causal": self.causal_evidence.to_dict(),
            },
            "raw_reward_components": {
                item.name: item.to_dict() for item in self.raw_reward_components
            },
            "formal_reward": self.formal_reward.to_dict(),
            "admission": {
                "ppo_allowed": False,
                "assist_allowed": False,
                "authority_allowed": False,
                "rule_fallback_required": True,
            },
            "audit": {
                "fail_closed": True,
                "online_truth_use_count": 0,
                "evaluator_identity_exported": False,
                "offline_rule_teacher_components_promoted": False,
                "adjacent_state_change_promoted_to_causal_reward": False,
                "five_meter_event_promoted_to_causal_reward": False,
            },
        }
        _assert_truth_free(payload)
        return payload


def canonical_reward_evidence_payload_sha256(value: Any) -> str:
    """Return the canonical JSON SHA-256 used by this attribution adapter."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimePlanRewardEvidenceError(
            "payload_not_canonical_json",
            "evidence payload is not finite canonical JSON",
        ) from exc
    return sha256(encoded).hexdigest()


def build_runtime_plan_window_reward_evidence(
    *,
    runtime_ack_evidence: AssignmentPlanRuntimeAckEvidence | None,
    ack_bus_sequence: int,
    d6_outcome_join: Mapping[str, Any],
    expected_d6_outcome_join_sha256: str,
    resource_id: str,
    global_track_id: str,
) -> RuntimePlanWindowRewardEvidence:
    """Bind one applied plan occurrence to observed, non-causal D6 evidence.

    The supplied ACK must already have passed
    :func:`validate_assignment_plan_runtime_ack`.  The D6 result is accepted
    only when its complete canonical payload matches the caller-supplied hash.
    No available formal reward is emitted by this v1 adapter.
    """

    ack = _validated_ack(runtime_ack_evidence)
    ack_sequence = _positive_int(ack_bus_sequence, "ACK bus sequence")
    selected_resource = _required_text(resource_id, "resource_id")
    selected_track = _required_text(global_track_id, "global_track_id")
    owner_layer = _required_text(ack.active_plan_owner, "active_plan_owner")
    owner_node = _required_text(ack.owner_node_id, "owner_node_id")
    if not ack.accepted or ack.status_code != "accepted_by_main_runtime":
        _fail("runtime_ack_not_applied")
    if ack.physical_outcome_available or ack.reward_available:
        _fail("runtime_ack_self_claims_outcome_or_reward")

    ack_payload = ack.to_dict()
    _assert_truth_free(ack_payload)
    ack_payload_sha256 = canonical_reward_evidence_payload_sha256(ack_payload)
    binding = _select_ack_binding(ack, selected_resource, selected_track)

    source_sequence = _positive_int(
        ack.source_plan_bus_sequence,
        "source plan bus sequence",
    )
    consumption_sequence = _optional_positive_int(
        ack.source_guidance_bus_sequence,
        "consumption bus sequence",
    )
    if consumption_sequence is None or ack.source_guidance_payload_sha256 is None:
        _fail(
            "guidance_consumption_reference_missing",
            "an adopted assignment window requires a D7 consumption reference",
        )
    if not source_sequence < consumption_sequence < ack_sequence:
        _fail(
            "runtime_sequence_order_invalid",
            "source, consumption, and ACK sequences must be strictly ordered",
        )

    outcome = _strict_mapping(
        d6_outcome_join,
        required_fields=_D6_TOP_LEVEL_FIELDS,
        allowed_fields=(
            _D6_TOP_LEVEL_FIELDS | _D6_OPTIONAL_TOP_LEVEL_FIELDS
        ),
        code="d6_outcome_join_fields_mismatch",
        context="D6 outcome join",
    )
    expected_digest = _sha256(
        expected_d6_outcome_join_sha256,
        "expected D6 outcome join SHA-256",
    )
    actual_digest = canonical_reward_evidence_payload_sha256(outcome)
    if actual_digest != expected_digest:
        _fail("d6_outcome_join_sha256_mismatch")

    episode, artifact_hashes = _validate_d6_report(outcome)
    windows = _validate_all_windows(outcome["binding_windows"])
    _validate_d6_summary_counts(outcome, windows)
    selected = _select_outcome_window(
        windows,
        ack=ack,
        binding=binding,
        ack_bus_sequence=ack_sequence,
    )
    _match_selected_window(ack, binding, selected)

    source_hash = _sha256(
        ack.source_plan_payload_sha256,
        "source plan payload SHA-256",
    )
    consumption_hash = _sha256(
        ack.source_guidance_payload_sha256,
        "consumption payload SHA-256",
    )
    window_start = _finite_nonnegative(
        selected["window_start_timestamp"],
        "window start timestamp",
    )
    window_end = _finite_nonnegative(
        selected["window_end_timestamp"],
        "window end timestamp",
    )
    if window_start != float(ack.ack_timestamp):
        _fail("ack_window_start_mismatch")

    reference = RuntimePlanWindowReference(
        episode_id=_required_text(episode["episode_id"], "episode_id"),
        scenario_version=_required_text(
            episode["scenario_version"],
            "scenario_version",
        ),
        seed=_nonnegative_int(episode["seed"], "episode seed"),
        plan_id=ack.plan_id,
        plan_version=ack.plan_version,
        active_plan_owner=owner_layer,
        owner_node_id=owner_node,
        authority_epoch=ack.authority_epoch,
        resource_id=selected_resource,
        global_track_id=selected_track,
        coalition_id=binding.coalition_id,
        coalition_version=binding.coalition_version,
        member_role=binding.member_role,
        source_plan_bus_sequence=source_sequence,
        source_plan_payload_sha256=source_hash,
        consumption_bus_sequence=consumption_sequence,
        consumption_payload_sha256=consumption_hash,
        ack_bus_sequence=ack_sequence,
        plan_created_at=float(ack.plan_created_at),
        command_timestamp=float(ack.ack_timestamp),
        consumption_timestamp=float(ack.ack_timestamp),
        ack_timestamp=float(ack.ack_timestamp),
        occurrence_id=_required_text(selected["occurrence_id"], "occurrence_id"),
        occurrence_index=_positive_int(
            selected["occurrence_index"],
            "occurrence index",
        ),
        adoption_kind=_required_text(selected["adoption_kind"], "adoption kind"),
        execution_signature_sha256=_sha256(
            selected["execution_signature_sha256"],
            "execution signature SHA-256",
        ),
        window_start_timestamp=window_start,
        window_end_timestamp=window_end,
        window_interval=_required_text(selected["window_interval"], "window interval"),
        runtime_ack_evidence_sha256=ack_payload_sha256,
        outcome_join_payload_sha256=actual_digest,
        source_artifact_sha256s=tuple(sorted(artifact_hashes.items())),
    )

    command = _available(
        "assignment_command_published",
        "command",
        True,
        source_hash,
    )
    ack_applied = _ack_applied_availability(binding, ack_payload_sha256)
    observed = _observed_outcome_evidence(selected, actual_digest)
    paired = _unavailable(
        "same_seed_paired_assignment_outcome",
        "paired",
        _required_text(
            outcome["observed_diagnostics"]["counterfactual_reason"],
            "paired evidence reason",
        ),
        actual_digest,
    )
    counterfactual = _unavailable(
        "counterfactual_assignment_outcome",
        "counterfactual",
        _required_text(
            selected["counterfactual_reason"],
            "counterfactual reason",
        ),
        actual_digest,
    )
    causal = _unavailable(
        "causal_assignment_attribution",
        "causal",
        _required_text(
            selected["causal_attribution_reason"],
            "causal attribution reason",
        ),
        actual_digest,
    )
    components = _unavailable_reward_components(actual_digest)
    formal_reward = _unavailable(
        "formal_d3_runtime_reward",
        "formal_reward",
        "paired_counterfactual_and_causal_evidence_unavailable",
        actual_digest,
    )
    result = RuntimePlanWindowRewardEvidence(
        reference=reference,
        command=command,
        ack_applied=ack_applied,
        observed_outcomes=observed,
        paired_evidence=paired,
        counterfactual_evidence=counterfactual,
        causal_evidence=causal,
        raw_reward_components=components,
        formal_reward=formal_reward,
    )
    result.to_dict()
    return result


def _validated_ack(
    value: AssignmentPlanRuntimeAckEvidence | None,
) -> AssignmentPlanRuntimeAckEvidence:
    if value is None:
        _fail("runtime_ack_missing")
    identity = (type(value).__module__, type(value).__name__)
    field_names = (
        frozenset(item.name for item in fields(value))
        if is_dataclass(value) and not isinstance(value, type)
        else frozenset()
    )
    if (
        not isinstance(value, AssignmentPlanRuntimeAckEvidence)
        and (
            identity not in _RUNTIME_ACK_CLASS_IDENTITIES
            or field_names != _RUNTIME_ACK_FIELD_NAMES
        )
    ):
        _fail(
            "runtime_ack_evidence_type_invalid",
            "runtime ACK input must be verified D3 evidence",
        )
    return value


def _select_ack_binding(
    ack: AssignmentPlanRuntimeAckEvidence,
    resource_id: str,
    global_track_id: str,
) -> RuntimePlanBindingAck:
    matches = tuple(
        item
        for item in ack.binding_acks
        if item.resource_id == resource_id
        and item.global_track_id == global_track_id
    )
    if len(matches) != 1:
        _fail(
            "runtime_ack_binding_missing_or_ambiguous",
            "runtime ACK must contain exactly one selected binding",
        )
    return matches[0]


def _validate_d6_report(
    report: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, str]]:
    report_schema = report["schema_version"]
    if report_schema not in {
        D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V1,
        D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V2,
    }:
        _fail("d6_outcome_join_schema_mismatch")
    if report_schema == D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V2 and not (
        _D6_OPTIONAL_TOP_LEVEL_FIELDS <= set(report)
    ):
        _fail("d6_outcome_join_v2_provenance_fields_missing")
    _required_text(report["evaluation_date"], "D6 evaluation date")
    if report["evaluation_mode"] != "offline_read_only_fail_closed":
        _fail("d6_evaluation_mode_mismatch")

    episode = _strict_mapping(
        report["episode"],
        required_fields=_D6_EPISODE_FIELDS,
        allowed_fields=_D6_EPISODE_FIELDS,
        code="d6_episode_fields_mismatch",
        context="D6 episode",
    )
    _required_text(episode["episode_id"], "episode_id")
    _required_text(episode["scenario_name"], "scenario_name")
    _required_text(episode["scenario_version"], "scenario_version")
    _nonnegative_int(episode["seed"], "episode seed")
    _positive_int(episode["target_count"], "episode target_count")
    _positive_int(episode["resource_count"], "episode resource_count")
    _finite_positive(episode["duration_s"], "episode duration")
    _finite_positive(episode["physics_dt_s"], "episode physics_dt")

    sources = _strict_mapping(
        report["source_artifacts"],
        required_fields=_D6_SOURCE_ARTIFACT_NAMES,
        allowed_fields=_D6_SOURCE_ARTIFACT_NAMES,
        code="d6_source_artifacts_mismatch",
        context="D6 source artifacts",
    )
    artifact_hashes: dict[str, str] = {}
    for name in sorted(_D6_SOURCE_ARTIFACT_NAMES):
        item = _strict_mapping(
            sources[name],
            required_fields={"path", "sha256", "verified"},
            allowed_fields={"path", "sha256", "verified"},
            code="d6_source_artifact_fields_mismatch",
            context=f"D6 source artifact {name}",
        )
        _required_text(item["path"], f"D6 source artifact path {name}")
        if _strict_bool(item["verified"], f"D6 source verified {name}") is not True:
            _fail("d6_source_artifact_not_verified")
        artifact_hashes[name] = _sha256(
            item["sha256"],
            f"D6 source artifact SHA-256 {name}",
        )
    if _sha256(episode["manifest_sha256"], "manifest SHA-256") != artifact_hashes[
        "episode_manifest"
    ]:
        _fail("d6_episode_manifest_hash_mismatch")
    if _sha256(
        episode["scenario_config_sha256"],
        "scenario config SHA-256",
    ) != artifact_hashes["scenario_config"]:
        _fail("d6_scenario_config_hash_mismatch")
    _sha256(episode["config_canonical_sha256"], "config canonical SHA-256")

    runtime = _strict_mapping(
        report["runtime_ack_evidence"],
        required_fields=_D6_RUNTIME_ACK_SUMMARY_FIELDS,
        allowed_fields=_D6_RUNTIME_ACK_SUMMARY_FIELDS,
        code="d6_runtime_ack_summary_fields_mismatch",
        context="D6 runtime ACK evidence",
    )
    if _strict_bool(runtime.get("available"), "D6 runtime ACK available") is not True:
        _fail("d6_runtime_ack_unavailable")
    if runtime.get("reason") is not None:
        _fail("d6_runtime_ack_reason_mismatch")
    if _nonnegative_int(
        runtime.get("online_truth_use_count"),
        "D6 online truth use count",
    ) != 0:
        _fail("online_truth_leakage")
    if _strict_bool(
        runtime.get("source_sequence_and_payload_hash_verified"),
        "D6 source verification",
    ) is not True:
        _fail("d6_source_chain_not_verified")

    observed = _strict_mapping(
        report["observed_diagnostics"],
        required_fields=_D6_OBSERVED_DIAGNOSTIC_FIELDS,
        allowed_fields=_D6_OBSERVED_DIAGNOSTIC_FIELDS,
        code="d6_observed_diagnostic_fields_mismatch",
        context="D6 diagnostics",
    )
    if observed["bounded_pair_progress_name"] != (
        D6_RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_V1
    ):
        _fail("d6_progress_diagnostic_name_mismatch")
    for key in (
        "bounded_pair_progress_available_count",
        "assigned_pair_five_meter_event_count",
        "same_resource_other_target_event_count",
    ):
        _nonnegative_int(observed[key], f"D6 {key}")
    for key in (
        "formal_reward_reason",
        "counterfactual_reason",
        "causal_attribution_reason",
    ):
        _required_text(observed[key], f"D6 {key}")
    _require_unavailable_claim(
        observed,
        available_key="formal_reward_available",
        value_key="formal_reward",
        code="d6_formal_reward_claim_not_supported",
    )
    _require_unavailable_claim(
        observed,
        available_key="counterfactual_available",
        value_key="counterfactual",
        code="d6_counterfactual_claim_not_supported",
    )
    _require_unavailable_claim(
        observed,
        available_key="causal_attribution_available",
        value_key="causal_attribution",
        code="d6_causal_claim_not_supported",
    )

    admission = _strict_mapping(
        report["admission"],
        required_fields=_D6_ADMISSION_FIELDS,
        allowed_fields=(
            _D6_ADMISSION_FIELDS | _D6_OPTIONAL_ADMISSION_FIELDS
        ),
        code="d6_admission_fields_mismatch",
        context="D6 admission",
    )
    for key in ("ppo_allowed", "assist_allowed", "authority_allowed"):
        if _strict_bool(admission.get(key), f"D6 {key}") is not False:
            _fail("d6_learning_admission_open")
    if _strict_bool(
        admission.get("rule_fallback_required"),
        "D6 rule fallback required",
    ) is not True:
        _fail("d6_rule_fallback_not_required")
    if _strict_bool(
        admission.get("runtime_ack_join_available"),
        "D6 runtime ACK join available",
    ) is not True:
        _fail("d6_runtime_ack_join_not_admitted")
    for key in (
        "formal_same_seed_paired_shadow_available",
        "held_out_seed_performance_available",
        "formal_learning_adoption_outcome_available",
    ):
        if _strict_bool(admission.get(key), f"D6 {key}") is not False:
            _fail("d6_unsupported_formal_evidence_admitted")
    _strict_bool(
        admission.get("observed_pair_diagnostic_available"),
        "D6 observed pair diagnostic available",
    )
    if admission.get("status") != (
        "runtime_observed_diagnostic_only_admission_closed"
    ):
        _fail("d6_admission_status_mismatch")
    blockers = admission.get("promotion_blockers")
    if isinstance(blockers, (str, bytes)) or not isinstance(blockers, Sequence):
        _fail("d6_promotion_blockers_invalid")
    if not blockers or any(not isinstance(item, str) or not item for item in blockers):
        _fail("d6_promotion_blockers_invalid")
    provenance_fields_present = (
        _D6_OPTIONAL_ADMISSION_FIELDS & set(admission)
    )
    if (
        report_schema == D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V2
        and provenance_fields_present != _D6_OPTIONAL_ADMISSION_FIELDS
    ):
        _fail("d6_identity_recovery_config_provenance_incomplete")
    if provenance_fields_present:
        if provenance_fields_present != _D6_OPTIONAL_ADMISSION_FIELDS:
            _fail("d6_identity_recovery_config_provenance_incomplete")
        if _strict_bool(
            admission["identity_recovery_config_provenance_required"],
            "D6 identity recovery config provenance required",
        ) is not True:
            _fail("d6_identity_recovery_config_provenance_not_required")
        if _strict_bool(
            admission["identity_recovery_config_provenance_verified"],
            "D6 identity recovery config provenance verified",
        ) is not True:
            _fail("d6_identity_recovery_config_provenance_not_verified")
        if admission["identity_recovery_config_provenance_reason"] is not None:
            _fail("d6_identity_recovery_config_provenance_reason_present")

    audit = _strict_mapping(
        report["audit"],
        required_fields=_D6_AUDIT_FIELDS,
        allowed_fields=_D6_AUDIT_FIELDS,
        code="d6_audit_fields_mismatch",
        context="D6 audit",
    )
    if (
        _strict_bool(audit.get("passed"), "D6 audit passed") is not True
        or _strict_bool(audit.get("fail_closed"), "D6 audit fail_closed")
        is not True
        or _nonnegative_int(audit.get("violation_count"), "D6 violation count")
        != 0
    ):
        _fail("d6_audit_not_clean")
    if (
        _strict_bool(
            audit.get("source_mutation_performed"),
            "D6 source mutation",
        )
        is not False
        or _strict_bool(
            audit.get("frozen_900_episode_data_modified"),
            "D6 frozen data modification",
        )
        is not False
    ):
        _fail("d6_audit_source_mutation")
    violations = audit.get("violations")
    if isinstance(violations, (str, bytes)) or not isinstance(violations, Sequence):
        _fail("d6_audit_violations_invalid")
    if violations:
        _fail("d6_audit_not_clean")
    return episode, artifact_hashes


def _validate_d6_summary_counts(
    report: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
) -> None:
    runtime = _mapping(report["runtime_ack_evidence"], "D6 runtime ACK summary")
    observed = _mapping(report["observed_diagnostics"], "D6 diagnostics")
    occurrences = {
        (int(item["ack_bus_sequence"]), str(item["occurrence_id"]))
        for item in windows
    }
    adoption_by_occurrence = {
        key: next(
            str(item["adoption_kind"])
            for item in windows
            if (int(item["ack_bus_sequence"]), str(item["occurrence_id"])) == key
        )
        for key in occurrences
    }
    ack_count = _positive_int(runtime["ack_count"], "D6 ACK count")
    if ack_count != len(occurrences):
        _fail("d6_ack_count_mismatch")
    if _positive_int(
        runtime["unique_occurrence_count"],
        "D6 unique occurrence count",
    ) != len(occurrences):
        _fail("d6_occurrence_count_mismatch")
    new_count = sum(
        value == "new_plan_identity" for value in adoption_by_occurrence.values()
    )
    evaluation_refresh_count = sum(
        value == "same_identity_evaluation_refresh"
        for value in adoption_by_occurrence.values()
    )
    plan_refresh_count = sum(
        value == "same_identity_plan_refresh"
        for value in adoption_by_occurrence.values()
    )
    refresh_count = evaluation_refresh_count + plan_refresh_count
    expected_counts = {
        "new_plan_identity_occurrence_count": new_count,
        "same_identity_refresh_occurrence_count": refresh_count,
        "same_identity_evaluation_refresh_occurrence_count": (
            evaluation_refresh_count
        ),
        "same_identity_plan_refresh_occurrence_count": plan_refresh_count,
        "binding_count": len(windows),
    }
    for key, expected in expected_counts.items():
        if _nonnegative_int(runtime[key], f"D6 {key}") != expected:
            _fail("d6_summary_count_mismatch", f"D6 count mismatch at {key}")
    for key in (
        "d3_learning_applied_ack_count",
        "d4_regional_applied_ack_count",
    ):
        if _nonnegative_int(runtime[key], f"D6 {key}") > ack_count:
            _fail("d6_applied_ack_count_invalid")

    diagnostic_count = sum(
        bool(item["bounded_pair_progress_diagnostic"]["available"])
        for item in windows
    )
    assigned_event_count = sum(
        item["assigned_pair_proximity_event_observed"] is True for item in windows
    )
    other_event_count = sum(
        bool(item["other_target_proximity_event_observed"]) for item in windows
    )
    observed_counts = {
        "bounded_pair_progress_available_count": diagnostic_count,
        "assigned_pair_five_meter_event_count": assigned_event_count,
        "same_resource_other_target_event_count": other_event_count,
    }
    for key, expected in observed_counts.items():
        if _nonnegative_int(observed[key], f"D6 {key}") != expected:
            _fail("d6_observed_count_mismatch", f"D6 count mismatch at {key}")
    admission = _mapping(report["admission"], "D6 admission")
    if _strict_bool(
        admission["observed_pair_diagnostic_available"],
        "D6 observed diagnostic availability",
    ) != (diagnostic_count > 0):
        _fail("d6_observed_availability_mismatch")


def _validate_all_windows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("d6_binding_windows_not_sequence")
    windows: list[Mapping[str, Any]] = []
    for index, raw in enumerate(value):
        window = _strict_mapping(
            raw,
            required_fields=_D6_WINDOW_FIELDS,
            allowed_fields=_D6_WINDOW_FIELDS,
            code="d6_binding_window_fields_mismatch",
            context=f"D6 binding window {index}",
        )
        _validate_window(window)
        windows.append(window)
    if not windows:
        _fail("d6_binding_windows_empty")
    _validate_window_order_and_refresh_semantics(windows)
    return tuple(windows)


def _validate_window(window: Mapping[str, Any]) -> None:
    _positive_int(window["ack_bus_sequence"], "window ACK sequence")
    plan_id = _required_text(window["plan_id"], "window plan_id")
    plan_version = _positive_int(window["plan_version"], "window plan_version")
    if _required_text(window["decision_id"], "window decision_id") != (
        f"{plan_id}:v{plan_version}"
    ):
        _fail("window_decision_id_mismatch")
    occurrence = _positive_int(window["occurrence_index"], "occurrence index")
    adoption = _required_text(window["adoption_kind"], "adoption kind")
    if adoption not in _ADOPTION_KINDS:
        _fail("unsupported_adoption_kind")
    if occurrence == 1 and adoption != "new_plan_identity":
        _fail("refresh_semantics_mismatch")
    if occurrence > 1 and adoption == "new_plan_identity":
        _fail("refresh_semantics_mismatch")
    _sha256(window["execution_signature_sha256"], "execution signature")
    _required_text(window["resource_id"], "window resource_id")
    _required_text(window["global_track_id"], "window global_track_id")
    _required_text(window["member_role"], "window member_role")
    start = _finite_nonnegative(window["window_start_timestamp"], "window start")
    end = _finite_nonnegative(window["window_end_timestamp"], "window end")
    if end <= start:
        _fail("nonpositive_binding_window")
    interval = _required_text(window["window_interval"], "window interval")
    if interval not in {"left_closed_right_open", "closed"}:
        _fail("unsupported_window_interval")

    for key in (
        "guidance_command_present",
        "control_applied_to_world",
        "held",
        "formal_d3_ppo_reward_available",
        "counterfactual_available",
        "causal_attribution_available",
    ):
        _strict_bool(window[key], f"window {key}")
    if (
        window["formal_d3_ppo_reward_available"] is not False
        or window["formal_d3_ppo_reward"] is not None
    ):
        _fail("d6_formal_reward_claim_not_supported")
    if (
        window["counterfactual_available"] is not False
        or window["counterfactual"] is not None
    ):
        _fail("d6_counterfactual_claim_not_supported")
    if (
        window["causal_attribution_available"] is not False
        or window["causal_attribution"] is not None
    ):
        _fail("d6_causal_claim_not_supported")
    _required_text(window["formal_d3_ppo_reward_reason"], "formal reward reason")
    _required_text(window["counterfactual_reason"], "counterfactual reason")
    _required_text(window["causal_attribution_reason"], "causal reason")
    _validate_progress_diagnostic(window["bounded_pair_progress_diagnostic"])


def _validate_window_order_and_refresh_semantics(
    windows: Sequence[Mapping[str, Any]],
) -> None:
    by_resource: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    occurrences: dict[tuple[int, str], Mapping[str, Any]] = {}
    for window in windows:
        by_resource[str(window["resource_id"])].append(window)
        occurrence_key = (
            int(window["ack_bus_sequence"]),
            str(window["occurrence_id"]),
        )
        previous = occurrences.get(occurrence_key)
        if previous is None:
            occurrences[occurrence_key] = window
        else:
            for key in (
                "plan_id",
                "plan_version",
                "occurrence_index",
                "adoption_kind",
                "execution_signature_sha256",
                "window_start_timestamp",
            ):
                if previous[key] != window[key]:
                    _fail("ack_occurrence_window_mismatch")

    for resource_id, rows in by_resource.items():
        rows.sort(
            key=lambda item: (
                float(item["window_start_timestamp"]),
                int(item["ack_bus_sequence"]),
            )
        )
        for index, row in enumerate(rows):
            is_final = index + 1 == len(rows)
            expected_interval = "closed" if is_final else "left_closed_right_open"
            if row["window_interval"] != expected_interval:
                _fail("window_interval_semantics_mismatch")
            if index == 0:
                continue
            prior = rows[index - 1]
            if float(prior["window_end_timestamp"]) > float(
                row["window_start_timestamp"]
            ):
                _fail(
                    "binding_window_overlap",
                    f"overlapping attribution windows for {resource_id}",
                )
            if int(prior["ack_bus_sequence"]) >= int(row["ack_bus_sequence"]):
                _fail("non_monotonic_ack_sequence")

    ordered_occurrences = sorted(
        occurrences.values(),
        key=lambda item: int(item["ack_bus_sequence"]),
    )
    latest_version: dict[str, int] = {}
    identity_occurrences: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in ordered_occurrences:
        plan_id = str(row["plan_id"])
        version = int(row["plan_version"])
        if version < latest_version.get(plan_id, 0):
            _fail("stale_plan_version")
        latest_version[plan_id] = version
        identity_occurrences[(plan_id, version)].append(row)
    for rows in identity_occurrences.values():
        rows.sort(key=lambda item: int(item["occurrence_index"]))
        expected_indices = list(range(1, len(rows) + 1))
        if [int(item["occurrence_index"]) for item in rows] != expected_indices:
            _fail("noncontiguous_refresh_occurrence")
        if len({str(item["execution_signature_sha256"]) for item in rows}) != 1:
            _fail("same_identity_execution_signature_changed")


def _select_outcome_window(
    windows: Sequence[Mapping[str, Any]],
    *,
    ack: AssignmentPlanRuntimeAckEvidence,
    binding: RuntimePlanBindingAck,
    ack_bus_sequence: int,
) -> Mapping[str, Any]:
    matches = tuple(
        item
        for item in windows
        if int(item["ack_bus_sequence"]) == ack_bus_sequence
        and item["plan_id"] == ack.plan_id
        and int(item["plan_version"]) == ack.plan_version
        and item["resource_id"] == binding.resource_id
        and item["global_track_id"] == binding.global_track_id
    )
    if len(matches) != 1:
        _fail(
            "attribution_window_missing_or_ambiguous",
            "D6 join must contain exactly one matching plan-binding window",
        )
    return matches[0]


def _match_selected_window(
    ack: AssignmentPlanRuntimeAckEvidence,
    binding: RuntimePlanBindingAck,
    window: Mapping[str, Any],
) -> None:
    if window["decision_id"] != ack.decision_id:
        _fail("window_decision_id_mismatch")
    expected = {
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "member_role": binding.member_role,
        "guidance_command_present": binding.guidance_command_present,
        "guidance_mode": binding.guidance_mode,
        "guidance_gate_reason": binding.guidance_gate_reason,
        "control_applied_to_world": binding.control_applied_to_world,
        "held": binding.held,
    }
    for key, value in expected.items():
        if window[key] != value:
            _fail("window_binding_ack_mismatch", f"window mismatch at {key}")

    expected_learning = {
        "mode": ack.d3_learning_evidence.mode,
        "applied": ack.d3_learning_evidence.applied,
        "shadow_only": ack.d3_learning_evidence.shadow_only,
        "bundle_loaded": ack.d3_learning_evidence.bundle_loaded,
        "fallback_reason": ack.d3_learning_evidence.fallback_reason,
        "model_fingerprint": ack.d3_learning_evidence.model_fingerprint,
    }
    actual_learning = dict(
        _mapping(window["d3_learning_evidence"], "window D3 learning")
    )
    if not set(actual_learning).issubset(expected_learning):
        _fail("window_learning_evidence_mismatch")
    if any(expected_learning[key] != value for key, value in actual_learning.items()):
        _fail("window_learning_evidence_mismatch")
    if any(
        value is not None and key not in actual_learning
        for key, value in expected_learning.items()
    ):
        _fail("window_learning_evidence_mismatch")
    if dict(_mapping(window["d4_regional_hint_evidence"], "window D4 regional")) != (
        ack.d4_regional_hint_evidence.to_dict()
    ):
        _fail("window_regional_evidence_mismatch")


def _validate_progress_diagnostic(value: Any) -> None:
    item = _mapping(value, "bounded pair progress diagnostic")
    required = {
        "name",
        "available",
        "value",
        "reason",
        "range",
        "formal_reward",
        "causal",
        "counterfactual",
    }
    allowed = set(required) | {"formula"}
    if not required.issubset(item) or not set(item).issubset(allowed):
        _fail("progress_diagnostic_fields_mismatch")
    if item["name"] != D6_RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_V1:
        _fail("progress_diagnostic_name_mismatch")
    if item["range"] != [-1.0, 1.0]:
        _fail("progress_diagnostic_range_mismatch")
    for key in ("formal_reward", "causal", "counterfactual"):
        if _strict_bool(item[key], f"progress diagnostic {key}") is not False:
            _fail("progress_diagnostic_promoted")
    available = _strict_bool(item["available"], "progress diagnostic available")
    if available:
        score = _finite(item["value"], "progress diagnostic value")
        if not -1.0 <= score <= 1.0 or item["reason"] is not None:
            _fail("available_progress_diagnostic_invalid")
        _required_text(item.get("formula"), "progress diagnostic formula")
    elif item["value"] is not None or _optional_text(
        item["reason"],
        "progress diagnostic reason",
    ) is None:
        _fail("unavailable_progress_diagnostic_invalid")


def _observed_outcome_evidence(
    window: Mapping[str, Any],
    provenance_sha256: str,
) -> tuple[EvidenceAvailability, ...]:
    diagnostic = _mapping(
        window["bounded_pair_progress_diagnostic"],
        "bounded pair progress diagnostic",
    )
    if diagnostic["available"]:
        progress = _available(
            "bounded_assigned_pair_best_distance_progress",
            "observed_outcome",
            float(diagnostic["value"]),
            provenance_sha256,
        )
    else:
        progress = _unavailable(
            "bounded_assigned_pair_best_distance_progress",
            "observed_outcome",
            _required_text(diagnostic["reason"], "progress unavailable reason"),
            provenance_sha256,
        )
    assigned_event = _optional_observed_bool(
        "assigned_pair_five_meter_event",
        window["assigned_pair_proximity_event_observed"],
        "assigned_pair_identity_or_state_unavailable",
        provenance_sha256,
    )
    other_event = _optional_observed_bool(
        "same_resource_other_target_five_meter_event",
        window["other_target_proximity_event_observed"],
        "assigned_pair_identity_or_state_unavailable",
        provenance_sha256,
    )
    return progress, assigned_event, other_event


def _optional_observed_bool(
    name: str,
    value: Any,
    reason: str,
    provenance_sha256: str,
) -> EvidenceAvailability:
    if value is None:
        return _unavailable(
            name,
            "observed_outcome",
            reason,
            provenance_sha256,
        )
    return _available(
        name,
        "observed_outcome",
        _strict_bool(value, name),
        provenance_sha256,
    )


def _ack_applied_availability(
    binding: RuntimePlanBindingAck,
    provenance_sha256: str,
) -> EvidenceAvailability:
    if not binding.guidance_command_present:
        reason = "d7_binding_not_present"
    elif not binding.control_applied_to_world:
        reason = "d7_binding_not_applied_to_world"
    elif binding.held or binding.guidance_mode == "hold":
        reason = "d7_binding_held"
    else:
        return _available(
            "binding_control_applied",
            "ack_applied",
            True,
            provenance_sha256,
        )
    return _unavailable(
        "binding_control_applied",
        "ack_applied",
        reason,
        provenance_sha256,
    )


def _unavailable_reward_components(
    provenance_sha256: str,
) -> tuple[EvidenceAvailability, ...]:
    reasons = {
        "high_threat_coverage": "plan_level_coverage_not_in_binding_outcome_window",
        "rule_total_cost": "offline_rule_teacher_cost_is_not_runtime_outcome",
        "unmet_demand_slots": "plan_level_demand_result_not_in_binding_outcome_window",
        "reassignment_churn": "paired_plan_history_delta_unavailable",
        "plan_expired": "versioned_expiry_outcome_component_unavailable",
        "safety_rejections": "paired_safety_outcome_component_unavailable",
    }
    return tuple(
        _unavailable(
            name,
            "reward_component",
            reasons[name],
            provenance_sha256,
        )
        for name in FORMAL_REWARD_COMPONENT_NAMES
    )


def _available(
    name: str,
    evidence_kind: str,
    value: bool | int | float | str,
    provenance_sha256: str,
) -> EvidenceAvailability:
    return EvidenceAvailability(
        name=name,
        evidence_kind=evidence_kind,
        available=True,
        value=value,
        reason=None,
        provenance_sha256=provenance_sha256,
    )


def _unavailable(
    name: str,
    evidence_kind: str,
    reason: str,
    provenance_sha256: str | None,
) -> EvidenceAvailability:
    return EvidenceAvailability(
        name=name,
        evidence_kind=evidence_kind,
        available=False,
        value=None,
        reason=reason,
        provenance_sha256=provenance_sha256,
    )


def _require_unavailable_claim(
    value: Mapping[str, Any],
    *,
    available_key: str,
    value_key: str,
    code: str,
) -> None:
    if _strict_bool(value.get(available_key), available_key) is not False:
        _fail(code)
    if value.get(value_key) is not None:
        _fail(code)


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key).strip().lower()
            if text in _FORBIDDEN_ONLINE_KEYS or text.startswith("truth_"):
                _fail("online_truth_leakage", f"forbidden key at {path}.{key}")
            _assert_truth_free(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _assert_truth_free(child, f"{path}[{index}]")


def _strict_mapping(
    value: Any,
    *,
    required_fields: set[str] | frozenset[str],
    allowed_fields: set[str] | frozenset[str],
    code: str,
    context: str,
) -> Mapping[str, Any]:
    item = _mapping(value, context)
    keys = set(item)
    if not set(required_fields).issubset(keys) or not keys.issubset(
        set(allowed_fields)
    ):
        _fail(code, f"{context} fields do not match the versioned contract")
    return item


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", f"{context} must be a mapping")
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("required_text_missing", f"{context} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, context)


def _strict_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        _fail("strict_boolean_required", f"{context} must be a boolean")
    return value


def _positive_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("positive_integer_required", f"{context} must be a positive integer")
    return int(value)


def _optional_positive_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, context)


def _optional_nonnegative_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, context)


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(
            "nonnegative_integer_required",
            f"{context} must be a non-negative integer",
        )
    return int(value)


def _finite(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("finite_number_required", f"{context} must be numeric")
    result = float(value)
    if not isfinite(result):
        _fail("finite_number_required", f"{context} must be finite")
    return result


def _finite_nonnegative(value: Any, context: str) -> float:
    result = _finite(value, context)
    if result < 0.0:
        _fail("nonnegative_time_required", f"{context} must be non-negative")
    return result


def _finite_positive(value: Any, context: str) -> float:
    result = _finite(value, context)
    if result <= 0.0:
        _fail("positive_number_required", f"{context} must be positive")
    return result


def _sha256(value: Any, context: str) -> str:
    if not isinstance(value, str):
        _fail("sha256_required", f"{context} must be text")
    match = _SHA256_RE.fullmatch(value.strip().lower())
    if match is None:
        _fail("sha256_required", f"{context} must be a SHA-256")
    return match.group(1)


def _optional_sha256(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, context)


def _validate_scalar(value: Any, context: str) -> None:
    if isinstance(value, bool) or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float) and isfinite(value):
        return
    _fail("scalar_value_required", f"{context} must be a finite JSON scalar")


def _fail(code: str, message: str | None = None) -> None:
    raise RuntimePlanRewardEvidenceError(code, message)


__all__ = [
    "D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1",
    "D3_RUNTIME_REWARD_COMPONENT_POLICY_V1",
    "D6_RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_V1",
    "D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V1",
    "D6_RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_V2",
    "FORMAL_REWARD_COMPONENT_NAMES",
    "EvidenceAvailability",
    "RuntimePlanRewardEvidenceError",
    "RuntimePlanWindowReference",
    "RuntimePlanWindowRewardEvidence",
    "build_runtime_plan_window_reward_evidence",
    "canonical_reward_evidence_payload_sha256",
]
