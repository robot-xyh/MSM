"""Strict D4 A2 to D3 successor-plan evidence for offline shadow evaluation.

This module is deliberately outside the assignment solve path.  It verifies
that one current-lineage D4 A2 recommendation survived deterministic
projection, entered the existing D3 regional-hint contract, and produced an
execution signature distinct from both its predecessor and a same-input R0
shadow plan.  The resulting record is structural evidence only: it does not
claim runtime acknowledgement, owner or coalition acknowledgement, a physical
window, D7 execution, benefit, authority, or learning admission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil, isfinite
from pathlib import Path
from typing import Any

from .models import AssignmentPlan
from .regional_hint import (
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
    REGIONAL_PLANNING_HINT_SUCCESSOR_SCHEMA_V1,
    RegionalPlanningHint,
)
from .runtime_plan_ack import (
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)


A2_CURRENT_LINEAGE_IDENTITY_SCHEMA_V1 = (
    "d3_a2_current_lineage_identity_v1"
)
A2_SUCCESSOR_EVIDENCE_SCHEMA_V1 = "d3_a2_successor_evidence_v1"
A2_SUCCESSOR_EVIDENCE_KIND = (
    "a2_same_input_r0_strict_successor_shadow_evidence"
)
A2_SUCCESSOR_EVIDENCE_BATCH_SCHEMA_V1 = (
    "d3_a2_successor_evidence_batch_v1"
)
A2_SUCCESSOR_EVIDENCE_BATCH_KIND = (
    "a2_strict_successor_shadow_evidence_batch"
)
A2_ATTRIBUTION_SCOPE = (
    "candidate_vs_same_input_r0_execution_delta_only"
)

_D4_CURRENT_LINEAGE_SCHEMA = (
    "d4-region-resource-current-lineage-candidate-v1"
)
_D4_ACTUAL_POLICY_SAMPLE_SCHEMA = (
    "d4-region-resource-actual-policy-sample-diagnostic-v1"
)
_D4_ACTION_SCHEMA = (
    "d4-region-resource-actual-policy-action-diagnostic-v1"
)
_D4_TRANSFER_SCHEMA = (
    "d4-region-resource-actual-policy-transfer-diagnostic-v1"
)
_D4_SAFE_NONZERO_OUTCOME = "safe_nonzero_actual_model"

_CURRENT_LINEAGE_PERMISSION_FIELDS = frozenset(
    {
        "a2_admitted",
        "actual_adoption_claimed",
        "assignment_enabled",
        "assist_enabled",
        "authority_enabled",
        "benefit_claimed",
        "coalition_commit_enabled",
        "control_enabled",
        "takeover_enabled",
    }
)
_D4_SAMPLE_FIELDS = frozenset(
    {
        "schema",
        "scenario_id",
        "scenario_version",
        "seed",
        "frame_index",
        "snapshot_id",
        "snapshot_sha256",
        "candidate_id",
        "model_sha256",
        "confidence",
        "minimum_confidence",
        "latency_ms",
        "latency_limit_ms",
        "candidate_gate_passed",
        "candidate_ood_passed",
        "candidate_finite",
        "policy_output_structure_valid",
        "safety_projection_passed",
        "advisory_consumable",
        "actual_model_identity_verified",
        "identifiable_intervention_available",
        "intervention_fields",
        "raw_executable_signature_sha256",
        "outcome",
        "reason_codes",
        "safe_nonzero_actual_model",
        "actions",
        "transfers",
    }
)
_D4_ACTION_FIELDS = frozenset(
    {
        "schema",
        "region_id",
        "resources_before",
        "committed_resources",
        "baseline_reserve_resources",
        "raw_resource_quota_delta",
        "raw_requested_reserve_resources",
        "raw_hold",
        "raw_request_replan",
        "projected_resource_quota_delta",
        "projected_reserve_resources",
        "projected_hold",
        "projected_request_replan",
        "raw_effect_fields",
        "projected_effect_fields",
        "reason_codes",
    }
)
_D4_TRANSFER_FIELDS = frozenset(
    {
        "schema",
        "source_region_id",
        "target_region_id",
        "edge_id",
        "requested_resource_count",
        "projected_resource_count",
        "reason_codes",
    }
)
_EVIDENCE_FALSE_FIELDS = (
    "runtime_plan_ack_available",
    "owner_ack_available",
    "coalition_ack_available",
    "physical_window_available",
    "d7_execution_available",
    "benefit_available",
    "learning_assist_enabled",
    "assignment_authority_granted",
    "control_authority_granted",
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "actor_truth_id",
        "ground_truth",
        "ground_truth_id",
        "offline_truth_labels",
        "object_truth_id",
        "target_truth_id",
        "truth",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
    }
)


class A2SuccessorEvidenceError(ValueError):
    """Stable fail-closed error raised by the A2 successor boundary."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = str(reason)


@dataclass(frozen=True, slots=True)
class A2CurrentLineageIdentity:
    """Verified identity of one non-authoritative D4 current-lineage model."""

    candidate_id: str
    model_version: str
    candidate_manifest_file_sha256: str
    candidate_manifest_content_sha256: str
    model_state_sha256: str
    source_identity_sha256: str
    schema_version: str = A2_CURRENT_LINEAGE_IDENTITY_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A2_CURRENT_LINEAGE_IDENTITY_SCHEMA_V1:
            _fail("candidate_identity_schema_unsupported")
        _required_text(self.candidate_id, "candidate_id")
        _required_text(self.model_version, "model_version")
        for name in (
            "candidate_manifest_file_sha256",
            "candidate_manifest_content_sha256",
            "model_state_sha256",
            "source_identity_sha256",
        ):
            _sha256_text(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "model_version": self.model_version,
            "candidate_manifest_file_sha256": (
                self.candidate_manifest_file_sha256
            ),
            "candidate_manifest_content_sha256": (
                self.candidate_manifest_content_sha256
            ),
            "model_state_sha256": self.model_state_sha256,
            "source_identity_sha256": self.source_identity_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A2CurrentLineageIdentity":
        fields = frozenset(cls.__dataclass_fields__)
        item = _strict_mapping(value, fields, "candidate_identity")
        return cls(**item)


@dataclass(frozen=True, slots=True)
class A2SuccessorPlanEvidence:
    """Hash-bound structural evidence for one A2-specific D3 successor."""

    scenario_id: str
    scenario_version: str
    episode_id: str
    seed: int
    frame_index: int
    comparison_key: str
    candidate_identity: A2CurrentLineageIdentity
    observed_input_summary_sha256: str
    d4_decision_summary_sha256: str
    projected_action_summary_sha256: str
    regional_hint_payload_sha256: str
    advisory_id: str
    advisory_version: int
    source_plan_id: str
    source_plan_version: int
    source_plan_payload_sha256: str
    source_execution_signature_sha256: str
    source_owner_layer: str
    source_owner_id: str
    source_owner_epoch: int
    source_lease_expires_at_s: float
    r0_plan_id: str
    r0_plan_version: int
    r0_previous_plan_id: str | None
    r0_plan_payload_sha256: str
    r0_execution_signature_sha256: str
    successor_plan_id: str
    successor_plan_version: int
    successor_previous_plan_id: str
    successor_plan_payload_sha256: str
    successor_execution_signature_sha256: str
    ordinary_periodic_replan_changed: bool
    candidate_specific_execution_changed: bool
    same_input_r0_verified: bool
    strict_successor_verified: bool
    attribution_scope: str
    runtime_plan_ack_available: bool
    owner_ack_available: bool
    coalition_ack_available: bool
    physical_window_available: bool
    d7_execution_available: bool
    benefit_available: bool
    learning_assist_enabled: bool
    assignment_authority_granted: bool
    control_authority_granted: bool
    content_sha256: str
    evidence_kind: str = A2_SUCCESSOR_EVIDENCE_KIND
    schema_version: str = A2_SUCCESSOR_EVIDENCE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A2_SUCCESSOR_EVIDENCE_SCHEMA_V1:
            _fail("successor_evidence_schema_unsupported")
        if self.evidence_kind != A2_SUCCESSOR_EVIDENCE_KIND:
            _fail("successor_evidence_kind_invalid")
        for name in (
            "scenario_id",
            "scenario_version",
            "episode_id",
            "comparison_key",
            "advisory_id",
            "source_plan_id",
            "source_owner_layer",
            "source_owner_id",
            "r0_plan_id",
            "successor_plan_id",
            "successor_previous_plan_id",
            "attribution_scope",
        ):
            _required_text(getattr(self, name), name)
        _nonnegative_int(self.seed, "seed")
        _nonnegative_int(self.frame_index, "frame_index")
        _positive_int(self.advisory_version, "advisory_version")
        _positive_int(self.source_plan_version, "source_plan_version")
        _positive_int(self.r0_plan_version, "r0_plan_version")
        _positive_int(
            self.successor_plan_version, "successor_plan_version"
        )
        _nonnegative_int(self.source_owner_epoch, "source_owner_epoch")
        lease = _finite_nonnegative(
            self.source_lease_expires_at_s,
            "source_lease_expires_at_s",
        )
        if lease <= 0.0:
            _fail("source_lease_invalid")
        if not isinstance(
            self.candidate_identity, A2CurrentLineageIdentity
        ):
            _fail("candidate_identity_type_invalid")
        for name in (
            "observed_input_summary_sha256",
            "d4_decision_summary_sha256",
            "projected_action_summary_sha256",
            "regional_hint_payload_sha256",
            "source_plan_payload_sha256",
            "source_execution_signature_sha256",
            "r0_plan_payload_sha256",
            "r0_execution_signature_sha256",
            "successor_plan_payload_sha256",
            "successor_execution_signature_sha256",
            "content_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        if self.r0_previous_plan_id is not None:
            _required_text(self.r0_previous_plan_id, "r0_previous_plan_id")
        for name in (
            "ordinary_periodic_replan_changed",
            "candidate_specific_execution_changed",
            "same_input_r0_verified",
            "strict_successor_verified",
            *_EVIDENCE_FALSE_FIELDS,
        ):
            _strict_bool(getattr(self, name), name)
        if (
            not self.candidate_specific_execution_changed
            or not self.same_input_r0_verified
            or not self.strict_successor_verified
        ):
            _fail("strict_successor_flags_invalid")
        if any(getattr(self, name) for name in _EVIDENCE_FALSE_FIELDS):
            _fail("successor_evidence_runtime_or_authority_claim_forbidden")
        if self.attribution_scope != A2_ATTRIBUTION_SCOPE:
            _fail("attribution_scope_invalid")
        if (
            self.successor_plan_version != self.source_plan_version + 1
            or self.successor_previous_plan_id != self.source_plan_id
            or self.successor_plan_id == self.source_plan_id
        ):
            _fail("strict_successor_lineage_invalid")
        if self.ordinary_periodic_replan_changed:
            if (
                self.r0_plan_version != self.source_plan_version + 1
                or self.r0_previous_plan_id != self.source_plan_id
                or self.r0_plan_id == self.source_plan_id
            ):
                _fail("r0_periodic_replan_lineage_invalid")
        elif (
            self.r0_plan_version != self.source_plan_version
            or self.r0_plan_id != self.source_plan_id
        ):
            _fail("r0_noop_lineage_invalid")
        if (
            self.successor_execution_signature_sha256
            == self.source_execution_signature_sha256
        ):
            _fail("successor_execution_signature_unchanged")
        if (
            self.successor_execution_signature_sha256
            == self.r0_execution_signature_sha256
        ):
            _fail("a2_effect_not_distinct_from_r0")
        expected_key = _comparison_key(
            scenario_id=self.scenario_id,
            scenario_version=self.scenario_version,
            episode_id=self.episode_id,
            seed=self.seed,
            frame_index=self.frame_index,
            observed_input_summary_sha256=(
                self.observed_input_summary_sha256
            ),
            source_plan_id=self.source_plan_id,
            source_plan_version=self.source_plan_version,
        )
        if self.comparison_key != expected_key:
            _fail("comparison_key_mismatch")
        if self.content_sha256 != _evidence_content_sha256(self):
            _fail("successor_evidence_content_sha256_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "frame_index": self.frame_index,
            "comparison_key": self.comparison_key,
            "candidate_identity": self.candidate_identity.to_dict(),
            "observed_input_summary_sha256": (
                self.observed_input_summary_sha256
            ),
            "d4_decision_summary_sha256": (
                self.d4_decision_summary_sha256
            ),
            "projected_action_summary_sha256": (
                self.projected_action_summary_sha256
            ),
            "regional_hint_payload_sha256": (
                self.regional_hint_payload_sha256
            ),
            "advisory_id": self.advisory_id,
            "advisory_version": self.advisory_version,
            "source_plan_id": self.source_plan_id,
            "source_plan_version": self.source_plan_version,
            "source_plan_payload_sha256": (
                self.source_plan_payload_sha256
            ),
            "source_execution_signature_sha256": (
                self.source_execution_signature_sha256
            ),
            "source_owner_layer": self.source_owner_layer,
            "source_owner_id": self.source_owner_id,
            "source_owner_epoch": self.source_owner_epoch,
            "source_lease_expires_at_s": self.source_lease_expires_at_s,
            "r0_plan_id": self.r0_plan_id,
            "r0_plan_version": self.r0_plan_version,
            "r0_previous_plan_id": self.r0_previous_plan_id,
            "r0_plan_payload_sha256": self.r0_plan_payload_sha256,
            "r0_execution_signature_sha256": (
                self.r0_execution_signature_sha256
            ),
            "successor_plan_id": self.successor_plan_id,
            "successor_plan_version": self.successor_plan_version,
            "successor_previous_plan_id": self.successor_previous_plan_id,
            "successor_plan_payload_sha256": (
                self.successor_plan_payload_sha256
            ),
            "successor_execution_signature_sha256": (
                self.successor_execution_signature_sha256
            ),
            "ordinary_periodic_replan_changed": (
                self.ordinary_periodic_replan_changed
            ),
            "candidate_specific_execution_changed": (
                self.candidate_specific_execution_changed
            ),
            "same_input_r0_verified": self.same_input_r0_verified,
            "strict_successor_verified": self.strict_successor_verified,
            "attribution_scope": self.attribution_scope,
            **{
                name: getattr(self, name)
                for name in _EVIDENCE_FALSE_FIELDS
            },
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A2SuccessorPlanEvidence":
        item = _strict_mapping(
            value,
            frozenset(cls.__dataclass_fields__),
            "successor_evidence",
        )
        item["candidate_identity"] = A2CurrentLineageIdentity.from_dict(
            _mapping(item["candidate_identity"], "candidate_identity")
        )
        return cls(**item)


@dataclass(frozen=True, slots=True)
class A2SuccessorEvidenceBatch:
    """One candidate-homogeneous set of independent A2/R0 shadow records."""

    candidate_identity: A2CurrentLineageIdentity
    records: tuple[A2SuccessorPlanEvidence, ...]
    seed_values: tuple[int, ...]
    record_count: int
    runtime_plan_ack_available: bool
    owner_ack_available: bool
    coalition_ack_available: bool
    physical_window_available: bool
    d7_execution_available: bool
    benefit_available: bool
    learning_assist_enabled: bool
    assignment_authority_granted: bool
    control_authority_granted: bool
    content_sha256: str
    evidence_kind: str = A2_SUCCESSOR_EVIDENCE_BATCH_KIND
    schema_version: str = A2_SUCCESSOR_EVIDENCE_BATCH_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A2_SUCCESSOR_EVIDENCE_BATCH_SCHEMA_V1:
            _fail("successor_batch_schema_unsupported")
        if self.evidence_kind != A2_SUCCESSOR_EVIDENCE_BATCH_KIND:
            _fail("successor_batch_kind_invalid")
        if not isinstance(
            self.candidate_identity, A2CurrentLineageIdentity
        ):
            _fail("candidate_identity_type_invalid")
        records = tuple(self.records)
        if not records:
            _fail("successor_batch_empty")
        if any(
            not isinstance(item, A2SuccessorPlanEvidence)
            for item in records
        ):
            _fail("successor_batch_record_type_invalid")
        if any(
            item.candidate_identity != self.candidate_identity
            for item in records
        ):
            _fail("successor_batch_candidate_identity_mismatch")
        keys = tuple(item.comparison_key for item in records)
        if len(keys) != len(set(keys)):
            _fail("successor_batch_comparison_key_duplicate")
        expected_seeds = tuple(sorted({item.seed for item in records}))
        seeds = tuple(
            _nonnegative_int(value, "seed_value")
            for value in self.seed_values
        )
        if seeds != expected_seeds:
            _fail("successor_batch_seed_inventory_mismatch")
        if self.record_count != len(records):
            _fail("successor_batch_record_count_mismatch")
        for name in _EVIDENCE_FALSE_FIELDS:
            _strict_bool(getattr(self, name), name)
        if any(getattr(self, name) for name in _EVIDENCE_FALSE_FIELDS):
            _fail("successor_batch_runtime_or_authority_claim_forbidden")
        object.__setattr__(
            self,
            "records",
            tuple(sorted(records, key=_record_sort_key)),
        )
        object.__setattr__(self, "seed_values", seeds)
        _sha256_text(self.content_sha256, "content_sha256")
        if self.content_sha256 != _batch_content_sha256(self):
            _fail("successor_batch_content_sha256_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "candidate_identity": self.candidate_identity.to_dict(),
            "records": [item.to_dict() for item in self.records],
            "seed_values": list(self.seed_values),
            "record_count": self.record_count,
            **{
                name: getattr(self, name)
                for name in _EVIDENCE_FALSE_FIELDS
            },
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A2SuccessorEvidenceBatch":
        item = _strict_mapping(
            value,
            frozenset(cls.__dataclass_fields__),
            "successor_batch",
        )
        item["candidate_identity"] = A2CurrentLineageIdentity.from_dict(
            _mapping(item["candidate_identity"], "candidate_identity")
        )
        item["records"] = tuple(
            A2SuccessorPlanEvidence.from_dict(
                _mapping(record, "successor_record")
            )
            for record in _sequence(item["records"], "records")
        )
        item["seed_values"] = tuple(
            _nonnegative_int(seed, "seed")
            for seed in _sequence(item["seed_values"], "seed_values")
        )
        return cls(**item)


def load_a2_current_lineage_identity(
    manifest_path: str | Path,
    *,
    expected_file_sha256: str | None = None,
) -> A2CurrentLineageIdentity:
    """Load and verify one D4 current-lineage development manifest."""

    path, payload, file_digest = _load_json_file(
        manifest_path,
        expected_file_sha256=expected_file_sha256,
    )
    del path
    _assert_truth_free(payload)
    if payload.get("schema") != _D4_CURRENT_LINEAGE_SCHEMA:
        _fail("candidate_manifest_schema_unsupported")
    content_digest = _sha256_text(
        payload.get("content_sha256"),
        "candidate_manifest.content_sha256",
    )
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    if canonical_runtime_payload_sha256(unsigned) != content_digest:
        _fail("candidate_manifest_content_sha256_mismatch")
    permissions = _strict_mapping(
        payload.get("permissions"),
        _CURRENT_LINEAGE_PERMISSION_FIELDS,
        "candidate_manifest.permissions",
    )
    if any(
        _strict_bool(value, f"candidate_manifest.permissions.{name}")
        for name, value in permissions.items()
    ):
        _fail("candidate_manifest_permission_open")
    if (
        payload.get("lifecycle_stage") != "development"
        or payload.get("maximum_advisor_mode") != "shadow"
        or payload.get("development_shadow_candidate") is not True
        or payload.get("formal_holdout_evaluated") is not False
    ):
        _fail("candidate_manifest_crossed_shadow_boundary")
    artifacts = _mapping(
        payload.get("artifact_files"),
        "candidate_manifest.artifact_files",
    )
    model_sha = _sha256_text(
        payload.get("model_state_sha256"),
        "candidate_manifest.model_state_sha256",
    )
    if artifacts.get("bundle/state_dict.pt") != model_sha:
        _fail("candidate_manifest_model_artifact_mismatch")
    return A2CurrentLineageIdentity(
        candidate_id=_required_text(
            payload.get("candidate_id"),
            "candidate_manifest.candidate_id",
        ),
        model_version=_required_text(
            payload.get("model_version"),
            "candidate_manifest.model_version",
        ),
        candidate_manifest_file_sha256=file_digest,
        candidate_manifest_content_sha256=content_digest,
        model_state_sha256=model_sha,
        source_identity_sha256=_sha256_text(
            payload.get("source_identity_sha256"),
            "candidate_manifest.source_identity_sha256",
        ),
    )


def build_a2_successor_plan_evidence(
    *,
    candidate_identity: A2CurrentLineageIdentity,
    d4_decision_summary: Mapping[str, Any],
    regional_hint: RegionalPlanningHint | Mapping[str, Any],
    source_plan: AssignmentPlan,
    r0_plan: AssignmentPlan,
    successor_plan: AssignmentPlan,
    r0_input_summary_sha256: str,
    episode_id: str,
) -> A2SuccessorPlanEvidence:
    """Verify and bind one same-input A2/R0 D3 shadow comparison."""

    if not isinstance(
        candidate_identity, A2CurrentLineageIdentity
    ):
        _fail("candidate_identity_type_invalid")
    for name, plan in (
        ("source_plan", source_plan),
        ("r0_plan", r0_plan),
        ("successor_plan", successor_plan),
    ):
        if not isinstance(plan, AssignmentPlan):
            _fail(f"{name}_type_invalid")
        _assert_truth_free(plan.metadata)
    _assert_truth_free(d4_decision_summary)
    decision = _strict_mapping(
        d4_decision_summary,
        _D4_SAMPLE_FIELDS,
        "d4_decision_summary",
    )
    _validate_decision_identity(decision, candidate_identity)
    hint = (
        regional_hint
        if isinstance(regional_hint, RegionalPlanningHint)
        else RegionalPlanningHint.from_mapping(regional_hint)
    )
    if hint.schema != REGIONAL_PLANNING_HINT_SCHEMA_V1:
        _fail("regional_hint_schema_unsupported")

    scenario_id = _required_text(decision["scenario_id"], "scenario_id")
    scenario_version = _required_text(
        decision["scenario_version"], "scenario_version"
    )
    seed = _nonnegative_int(decision["seed"], "seed")
    frame_index = _nonnegative_int(
        decision["frame_index"], "frame_index"
    )
    observed_input_sha = _sha256_text(
        decision["snapshot_sha256"], "snapshot_sha256"
    )
    if (
        _sha256_text(
            r0_input_summary_sha256, "r0_input_summary_sha256"
        )
        != observed_input_sha
    ):
        _fail("candidate_r0_input_summary_mismatch")

    action_summary = _validated_action_summary(decision, hint)
    source_authority = _source_authority(source_plan)
    _validate_hint_source_and_authority(
        hint,
        source_plan=source_plan,
        source_authority=source_authority,
    )
    _validate_successor_contract(
        successor_plan,
        source_plan=source_plan,
        hint=hint,
        source_authority=source_authority,
    )
    _validate_r0_contract(r0_plan, source_plan=source_plan)

    source_signature = _execution_signature_sha256(source_plan)
    r0_signature = _execution_signature_sha256(r0_plan)
    successor_signature = _execution_signature_sha256(successor_plan)
    ordinary_changed = r0_signature != source_signature
    if successor_signature == source_signature:
        _fail("a2_successor_is_noop")
    if successor_signature == r0_signature:
        _fail("a2_effect_not_distinct_from_r0")

    values: dict[str, Any] = {
        "scenario_id": scenario_id,
        "scenario_version": scenario_version,
        "episode_id": _required_text(episode_id, "episode_id"),
        "seed": seed,
        "frame_index": frame_index,
        "candidate_identity": candidate_identity,
        "observed_input_summary_sha256": observed_input_sha,
        "d4_decision_summary_sha256": (
            canonical_runtime_payload_sha256(decision)
        ),
        "projected_action_summary_sha256": (
            canonical_runtime_payload_sha256(action_summary)
        ),
        "regional_hint_payload_sha256": (
            canonical_runtime_payload_sha256(_hint_payload(hint))
        ),
        "advisory_id": hint.advisory_id,
        "advisory_version": hint.advisory_version,
        "source_plan_id": source_plan.plan_id,
        "source_plan_version": source_plan.version,
        "source_plan_payload_sha256": (
            validated_assignment_plan_payload_sha256(source_plan)
        ),
        "source_execution_signature_sha256": source_signature,
        "source_owner_layer": source_authority[0],
        "source_owner_id": source_authority[1],
        "source_owner_epoch": source_authority[2],
        "source_lease_expires_at_s": source_authority[3],
        "r0_plan_id": r0_plan.plan_id,
        "r0_plan_version": r0_plan.version,
        "r0_previous_plan_id": r0_plan.previous_plan_id,
        "r0_plan_payload_sha256": (
            validated_assignment_plan_payload_sha256(r0_plan)
        ),
        "r0_execution_signature_sha256": r0_signature,
        "successor_plan_id": successor_plan.plan_id,
        "successor_plan_version": successor_plan.version,
        "successor_previous_plan_id": str(
            successor_plan.previous_plan_id
        ),
        "successor_plan_payload_sha256": (
            validated_assignment_plan_payload_sha256(successor_plan)
        ),
        "successor_execution_signature_sha256": successor_signature,
        "ordinary_periodic_replan_changed": ordinary_changed,
        "candidate_specific_execution_changed": True,
        "same_input_r0_verified": True,
        "strict_successor_verified": True,
        "attribution_scope": A2_ATTRIBUTION_SCOPE,
        **{name: False for name in _EVIDENCE_FALSE_FIELDS},
        "evidence_kind": A2_SUCCESSOR_EVIDENCE_KIND,
        "schema_version": A2_SUCCESSOR_EVIDENCE_SCHEMA_V1,
    }
    values["comparison_key"] = _comparison_key(
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        episode_id=values["episode_id"],
        seed=seed,
        frame_index=frame_index,
        observed_input_summary_sha256=observed_input_sha,
        source_plan_id=source_plan.plan_id,
        source_plan_version=source_plan.version,
    )
    values["content_sha256"] = canonical_runtime_payload_sha256(
        _serialize_evidence_values(values)
    )
    return A2SuccessorPlanEvidence(**values)


def build_a2_successor_evidence_batch(
    records: Sequence[A2SuccessorPlanEvidence],
) -> A2SuccessorEvidenceBatch:
    """Build one candidate-homogeneous batch without adding runtime claims."""

    items = tuple(records)
    if not items:
        _fail("successor_batch_empty")
    identity = items[0].candidate_identity
    values: dict[str, Any] = {
        "candidate_identity": identity,
        "records": items,
        "seed_values": tuple(sorted({item.seed for item in items})),
        "record_count": len(items),
        **{name: False for name in _EVIDENCE_FALSE_FIELDS},
        "evidence_kind": A2_SUCCESSOR_EVIDENCE_BATCH_KIND,
        "schema_version": A2_SUCCESSOR_EVIDENCE_BATCH_SCHEMA_V1,
    }
    values["content_sha256"] = canonical_runtime_payload_sha256(
        _serialize_batch_values(values)
    )
    return A2SuccessorEvidenceBatch(**values)


def validate_a2_successor_plan_evidence(
    value: A2SuccessorPlanEvidence | Mapping[str, Any],
) -> A2SuccessorPlanEvidence:
    """Re-parse one record so all hashes and closed claims are rechecked."""

    payload = (
        value.to_dict()
        if isinstance(value, A2SuccessorPlanEvidence)
        else _mapping(value, "successor_evidence")
    )
    _assert_truth_free(payload)
    return A2SuccessorPlanEvidence.from_dict(payload)


def validate_a2_successor_evidence_batch(
    value: A2SuccessorEvidenceBatch | Mapping[str, Any],
) -> A2SuccessorEvidenceBatch:
    """Re-parse one batch and verify its complete record inventory."""

    payload = (
        value.to_dict()
        if isinstance(value, A2SuccessorEvidenceBatch)
        else _mapping(value, "successor_batch")
    )
    _assert_truth_free(payload)
    return A2SuccessorEvidenceBatch.from_dict(payload)


def write_a2_successor_evidence_batch(
    batch: A2SuccessorEvidenceBatch,
    output_path: str | Path,
) -> Path:
    """Write one deterministic JSON batch for later independent loading."""

    if not isinstance(batch, A2SuccessorEvidenceBatch):
        _fail("successor_batch_type_invalid")
    path = Path(output_path)
    if path.exists() and path.is_symlink():
        _fail("successor_batch_output_symlink_forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            batch.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load_a2_successor_evidence_batch(
    input_path: str | Path,
    *,
    expected_file_sha256: str | None = None,
    expected_candidate_id: str | None = None,
    expected_model_state_sha256: str | None = None,
    expected_source_identity_sha256: str | None = None,
    expected_seed_values: Sequence[int] | None = None,
) -> A2SuccessorEvidenceBatch:
    """Strictly load a persisted A2 successor batch and optional identity fence."""

    _, payload, _ = _load_json_file(
        input_path,
        expected_file_sha256=expected_file_sha256,
    )
    _assert_truth_free(payload)
    batch = validate_a2_successor_evidence_batch(payload)
    identity = batch.candidate_identity
    if (
        expected_candidate_id is not None
        and identity.candidate_id
        != _required_text(expected_candidate_id, "expected_candidate_id")
    ):
        _fail("successor_batch_candidate_id_mismatch")
    if (
        expected_model_state_sha256 is not None
        and identity.model_state_sha256
        != _sha256_text(
            expected_model_state_sha256,
            "expected_model_state_sha256",
        )
    ):
        _fail("successor_batch_model_state_mismatch")
    if (
        expected_source_identity_sha256 is not None
        and identity.source_identity_sha256
        != _sha256_text(
            expected_source_identity_sha256,
            "expected_source_identity_sha256",
        )
    ):
        _fail("successor_batch_source_identity_mismatch")
    if expected_seed_values is not None:
        expected = tuple(
            sorted(
                {
                    _nonnegative_int(value, "expected_seed")
                    for value in expected_seed_values
                }
            )
        )
        if batch.seed_values != expected:
            _fail("successor_batch_expected_seed_inventory_mismatch")
    return batch


def _validate_decision_identity(
    decision: Mapping[str, Any],
    identity: A2CurrentLineageIdentity,
) -> None:
    if decision.get("schema") != _D4_ACTUAL_POLICY_SAMPLE_SCHEMA:
        _fail("d4_decision_schema_unsupported")
    if decision.get("candidate_id") != identity.candidate_id:
        _fail("d4_candidate_identity_mismatch")
    if decision.get("model_sha256") != identity.model_state_sha256:
        _fail("d4_model_state_identity_mismatch")
    required_true = (
        "candidate_gate_passed",
        "candidate_ood_passed",
        "candidate_finite",
        "policy_output_structure_valid",
        "safety_projection_passed",
        "advisory_consumable",
        "actual_model_identity_verified",
        "identifiable_intervention_available",
        "safe_nonzero_actual_model",
    )
    if any(decision.get(name) is not True for name in required_true):
        _fail("d4_decision_not_safe_nonzero")
    if decision.get("outcome") != _D4_SAFE_NONZERO_OUTCOME:
        _fail("d4_decision_not_safe_nonzero")
    _required_text(decision.get("snapshot_id"), "snapshot_id")
    _sha256_text(
        decision.get("raw_executable_signature_sha256"),
        "raw_executable_signature_sha256",
    )
    if not _sequence(decision.get("intervention_fields"), "intervention_fields"):
        _fail("d4_decision_intervention_fields_empty")
    confidence = _unit_interval(decision.get("confidence"), "confidence")
    minimum = _unit_interval(
        decision.get("minimum_confidence"), "minimum_confidence"
    )
    latency = _finite_nonnegative(decision.get("latency_ms"), "latency_ms")
    latency_limit = _finite_nonnegative(
        decision.get("latency_limit_ms"), "latency_limit_ms"
    )
    if (
        abs(minimum - 0.60) > 1.0e-12
        or abs(latency_limit - 50.0) > 1.0e-12
        or confidence < minimum
        or latency > latency_limit
    ):
        _fail("d4_decision_gate_measurement_inconsistent")


def _validated_action_summary(
    decision: Mapping[str, Any],
    hint: RegionalPlanningHint,
) -> dict[str, Any]:
    actions = tuple(
        _strict_mapping(
            _mapping(value, "d4_action"),
            _D4_ACTION_FIELDS,
            "d4_action",
        )
        for value in _sequence(decision.get("actions"), "actions")
    )
    if not actions:
        _fail("d4_projected_action_inventory_empty")
    normalized_actions: list[dict[str, Any]] = []
    resources_before: dict[str, int] = {}
    action_regions: set[str] = set()
    nonzero = False
    for action in actions:
        if action.get("schema") != _D4_ACTION_SCHEMA:
            _fail("d4_action_schema_unsupported")
        region_id = _required_text(action.get("region_id"), "region_id")
        if region_id in action_regions:
            _fail("d4_action_region_duplicate")
        action_regions.add(region_id)
        before = _nonnegative_int(
            action.get("resources_before"), "resources_before"
        )
        committed = _nonnegative_int(
            action.get("committed_resources"), "committed_resources"
        )
        baseline_reserve = _nonnegative_int(
            action.get("baseline_reserve_resources"),
            "baseline_reserve_resources",
        )
        if (
            committed > before
            or baseline_reserve > max(0, before - committed)
        ):
            _fail("d4_projected_action_resource_infeasible")
        quota = _strict_int(
            action.get("projected_resource_quota_delta"),
            "projected_resource_quota_delta",
        )
        reserve = _nonnegative_int(
            action.get("projected_reserve_resources"),
            "projected_reserve_resources",
        )
        hold = _strict_bool(action.get("projected_hold"), "projected_hold")
        replan = _strict_bool(
            action.get("projected_request_replan"),
            "projected_request_replan",
        )
        expected_effect_fields = {
            *({"resource_quota"} if quota != 0 else set()),
            *(
                {"reserve_resources"}
                if reserve != baseline_reserve
                else set()
            ),
            *({"hold"} if hold else set()),
            *({"request_replan"} if replan else set()),
        }
        actual_effect_fields = {
            _required_text(value, "projected_effect_field")
            for value in _sequence(
                action.get("projected_effect_fields"),
                "projected_effect_fields",
            )
        }
        if actual_effect_fields != expected_effect_fields:
            _fail("d4_projected_effect_fields_inconsistent")
        after = before + quota
        if after < 0 or reserve > max(0, after - committed):
            _fail("d4_projected_action_resource_infeasible")
        resources_before[region_id] = before
        normalized_actions.append(
            {
                "region_id": region_id,
                "resource_quota_delta": quota,
                "reserve_resources": reserve,
                "hold": hold,
                "request_replan": replan,
            }
        )
        nonzero = bool(
            nonzero
            or quota != 0
            or reserve != baseline_reserve
            or hold
            or replan
        )

    normalized_transfers: list[dict[str, Any]] = []
    for value in _sequence(decision.get("transfers"), "transfers"):
        transfer = _strict_mapping(
            _mapping(value, "d4_transfer"),
            _D4_TRANSFER_FIELDS,
            "d4_transfer",
        )
        if transfer.get("schema") != _D4_TRANSFER_SCHEMA:
            _fail("d4_transfer_schema_unsupported")
        count = _nonnegative_int(
            transfer.get("projected_resource_count"),
            "projected_resource_count",
        )
        if count == 0:
            continue
        normalized_transfers.append(
            {
                "source_region_id": _required_text(
                    transfer.get("source_region_id"),
                    "source_region_id",
                ),
                "target_region_id": _required_text(
                    transfer.get("target_region_id"),
                    "target_region_id",
                ),
                "edge_id": _required_text(
                    transfer.get("edge_id"), "edge_id"
                ),
                "resource_count": count,
            }
        )
        nonzero = True
    if not nonzero:
        _fail("d4_projected_action_noop")

    hint_actions = []
    for constraint in hint.constraints:
        if constraint.region_id not in resources_before:
            _fail("d4_hint_action_region_mismatch")
        resources_after = max(
            0,
            resources_before[constraint.region_id]
            + constraint.resource_quota_delta,
        )
        hint_actions.append(
            {
                "region_id": constraint.region_id,
                "resource_quota_delta": constraint.resource_quota_delta,
                "reserve_resources": int(
                    ceil(constraint.reserve_ratio * resources_after)
                ),
                "hold": constraint.hold,
                "request_replan": constraint.request_replan,
            }
        )
    hint_transfers = [
        {
            "source_region_id": item.source_region_id,
            "target_region_id": item.target_region_id,
            "edge_id": item.edge_id,
            "resource_count": item.resource_count,
        }
        for item in hint.transfer_allowances
    ]
    quota_by_region = {
        item["region_id"]: int(item["resource_quota_delta"])
        for item in hint_actions
    }
    if sum(quota_by_region.values()) != 0:
        _fail("d4_hint_resource_conservation_violation")
    transfer_net = {region_id: 0 for region_id in quota_by_region}
    for item in hint_transfers:
        source_region = item["source_region_id"]
        target_region = item["target_region_id"]
        if (
            source_region not in transfer_net
            or target_region not in transfer_net
            or source_region == target_region
        ):
            _fail("d4_hint_transfer_region_invalid")
        transfer_net[source_region] -= int(item["resource_count"])
        transfer_net[target_region] += int(item["resource_count"])
    if transfer_net != quota_by_region:
        _fail("d4_hint_transfer_quota_mismatch")
    if any(
        item.hold and item.resource_quota_delta != 0
        for item in hint.constraints
    ):
        _fail("d4_hint_hold_quota_invalid")
    diagnostic_summary = {
        "regions": sorted(
            normalized_actions, key=lambda item: item["region_id"]
        ),
        "transfers": sorted(
            normalized_transfers,
            key=lambda item: (
                item["source_region_id"],
                item["target_region_id"],
                item["edge_id"],
            ),
        ),
    }
    hint_summary = {
        "regions": sorted(
            hint_actions, key=lambda item: item["region_id"]
        ),
        "transfers": sorted(
            hint_transfers,
            key=lambda item: (
                item["source_region_id"],
                item["target_region_id"],
                item["edge_id"],
            ),
        ),
    }
    if diagnostic_summary != hint_summary:
        _fail("d4_d3_projected_action_binding_mismatch")
    return diagnostic_summary


def _source_authority(
    plan: AssignmentPlan,
) -> tuple[str, str, int, float]:
    metadata = plan.metadata
    owner_layer = _required_text(
        metadata.get("plan_owner"), "source_plan.plan_owner"
    )
    owner_id = _required_text(
        metadata.get("owner_node_id"), "source_plan.owner_node_id"
    )
    epoch = _nonnegative_int(
        metadata.get("authority_epoch"), "source_plan.authority_epoch"
    )
    lease = _finite_nonnegative(
        metadata.get("lease_expires_at_s"),
        "source_plan.lease_expires_at_s",
    )
    if lease <= float(plan.created_at):
        _fail("source_plan_lease_expired")
    for name in ("active_plan_owner", "current_plan_owner"):
        if name in metadata and metadata.get(name) != owner_layer:
            _fail("source_plan_owner_fields_inconsistent")
    for name in (
        "current_plan_owner_node_id",
    ):
        if name in metadata and metadata.get(name) != owner_id:
            _fail("source_plan_owner_fields_inconsistent")
    return owner_layer, owner_id, epoch, lease


def _validate_hint_source_and_authority(
    hint: RegionalPlanningHint,
    *,
    source_plan: AssignmentPlan,
    source_authority: tuple[str, str, int, float],
) -> None:
    owner_layer, owner_id, epoch, lease = source_authority
    if (
        hint.source_plan_id != source_plan.plan_id
        or hint.source_plan_version != source_plan.version
    ):
        _fail("regional_hint_source_plan_mismatch")
    if (
        hint.created_at_s < float(source_plan.created_at)
        or hint.expires_at_s > lease
    ):
        _fail("regional_hint_source_time_window_invalid")
    for constraint in hint.constraints:
        if (
            constraint.source_plan_id != source_plan.plan_id
            or constraint.source_plan_version != source_plan.version
            or constraint.owner_layer != owner_layer
            or constraint.owner_id != owner_id
            or constraint.owner_epoch != epoch
            or constraint.lease_expires_at_s != lease
        ):
            _fail("regional_hint_source_authority_mismatch")


def _validate_successor_contract(
    plan: AssignmentPlan,
    *,
    source_plan: AssignmentPlan,
    hint: RegionalPlanningHint,
    source_authority: tuple[str, str, int, float],
) -> None:
    metadata = plan.metadata
    if (
        plan.plan_id == source_plan.plan_id
        or plan.version != source_plan.version + 1
        or plan.previous_plan_id != source_plan.plan_id
    ):
        _fail("a2_successor_plan_version_invalid")
    if float(plan.created_at) < hint.created_at_s:
        _fail("a2_successor_precedes_decision")
    expected = {
        "regional_hint_successor_schema": (
            REGIONAL_PLANNING_HINT_SUCCESSOR_SCHEMA_V1
        ),
        "regional_hint_successor_state": "successor_published",
        "regional_hint_successor_plan_available": True,
        "regional_hint_successor_plan_id": plan.plan_id,
        "regional_hint_successor_plan_version": plan.version,
        "regional_hint_successor_source_plan_id": source_plan.plan_id,
        "regional_hint_successor_source_plan_version": source_plan.version,
        "regional_hint_successor_advisory_id": hint.advisory_id,
        "regional_hint_successor_advisory_version": hint.advisory_version,
        "regional_hint_successor_owner_layer": source_authority[0],
        "regional_hint_successor_owner_id": source_authority[1],
        "regional_hint_successor_owner_epoch": source_authority[2],
        "regional_hint_successor_lease_expires_at_s": source_authority[3],
        "regional_hint_constraint_applied": True,
        "regional_hint_applied": True,
        "regional_hint_rejected": False,
    }
    if any(metadata.get(name) != value for name, value in expected.items()):
        _fail("a2_successor_metadata_contract_invalid")
    if (
        metadata.get("plan_owner") != source_authority[0]
        or metadata.get("owner_node_id") != source_authority[1]
        or metadata.get("authority_epoch") != source_authority[2]
        or metadata.get("lease_expires_at_s") != source_authority[3]
    ):
        _fail("a2_successor_authority_mismatch")


def _validate_r0_contract(
    plan: AssignmentPlan,
    *,
    source_plan: AssignmentPlan,
) -> None:
    metadata = plan.metadata
    if (
        metadata.get("regional_hint_available") is True
        or metadata.get("regional_hint_constraint_applied") is True
        or metadata.get("regional_hint_applied") is True
        or metadata.get("regional_hint_successor_plan_available") is True
        or metadata.get("learning_applied") is True
        or metadata.get("learning_assist_enabled") is True
    ):
        _fail("candidate_r0_arm_mixed")
    source_signature = _execution_signature_sha256(source_plan)
    r0_signature = _execution_signature_sha256(plan)
    if r0_signature == source_signature:
        if (
            plan.plan_id != source_plan.plan_id
            or plan.version != source_plan.version
        ):
            _fail("r0_noop_identity_advanced")
    elif (
        plan.plan_id == source_plan.plan_id
        or plan.version != source_plan.version + 1
        or plan.previous_plan_id != source_plan.plan_id
    ):
        _fail("r0_periodic_replan_lineage_invalid")


def _hint_payload(hint: RegionalPlanningHint) -> dict[str, Any]:
    return {
        "schema": hint.schema,
        "advisory_id": hint.advisory_id,
        "advisory_version": hint.advisory_version,
        "created_at_s": hint.created_at_s,
        "expires_at_s": hint.expires_at_s,
        "source_plan_id": hint.source_plan_id,
        "source_plan_version": hint.source_plan_version,
        "projected": hint.projected,
        "constraints": [
            {
                "region_id": item.region_id,
                "owner_id": item.owner_id,
                "owner_layer": item.owner_layer,
                "owner_epoch": item.owner_epoch,
                "lease_expires_at_s": item.lease_expires_at_s,
                "source_plan_id": item.source_plan_id,
                "source_plan_version": item.source_plan_version,
                "resource_quota_delta": item.resource_quota_delta,
                "reserve_ratio": item.reserve_ratio,
                "hold": item.hold,
                "request_replan": item.request_replan,
            }
            for item in hint.constraints
        ],
        "transfer_allowances": [
            {
                "source_region_id": item.source_region_id,
                "target_region_id": item.target_region_id,
                "resource_count": item.resource_count,
                "edge_id": item.edge_id,
                "expected_transfer_time_s": item.expected_transfer_time_s,
            }
            for item in hint.transfer_allowances
        ],
    }


def _execution_signature_sha256(plan: AssignmentPlan) -> str:
    return canonical_runtime_payload_sha256(plan.execution_signature())


def _comparison_key(
    *,
    scenario_id: str,
    scenario_version: str,
    episode_id: str,
    seed: int,
    frame_index: int,
    observed_input_summary_sha256: str,
    source_plan_id: str,
    source_plan_version: int,
) -> str:
    digest = canonical_runtime_payload_sha256(
        {
            "scenario_id": scenario_id,
            "scenario_version": scenario_version,
            "episode_id": episode_id,
            "seed": seed,
            "frame_index": frame_index,
            "observed_input_summary_sha256": (
                observed_input_summary_sha256
            ),
            "source_plan_id": source_plan_id,
            "source_plan_version": source_plan_version,
        }
    )
    return f"a2-r0-{digest[:24]}"


def _serialize_evidence_values(values: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(values)
    identity = payload.get("candidate_identity")
    if isinstance(identity, A2CurrentLineageIdentity):
        payload["candidate_identity"] = identity.to_dict()
    payload.pop("content_sha256", None)
    return payload


def _serialize_batch_values(values: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(values)
    identity = payload.get("candidate_identity")
    if isinstance(identity, A2CurrentLineageIdentity):
        payload["candidate_identity"] = identity.to_dict()
    raw_records = tuple(payload.get("records", ()))
    serialized_records = [
        item.to_dict()
        if isinstance(item, A2SuccessorPlanEvidence)
        else dict(_mapping(item, "successor_record"))
        for item in raw_records
    ]
    payload["records"] = sorted(
        serialized_records,
        key=_record_mapping_sort_key,
    )
    payload["seed_values"] = list(payload.get("seed_values", ()))
    payload.pop("content_sha256", None)
    return payload


def _evidence_content_sha256(value: A2SuccessorPlanEvidence) -> str:
    return canonical_runtime_payload_sha256(
        _serialize_evidence_values(value.to_dict())
    )


def _batch_content_sha256(value: A2SuccessorEvidenceBatch) -> str:
    return canonical_runtime_payload_sha256(
        _serialize_batch_values(value.to_dict())
    )


def _record_sort_key(
    value: A2SuccessorPlanEvidence,
) -> tuple[str, int, int, str]:
    return (
        value.episode_id,
        value.seed,
        value.frame_index,
        value.comparison_key,
    )


def _record_mapping_sort_key(
    value: Mapping[str, Any],
) -> tuple[str, int, int, str]:
    return (
        str(value.get("episode_id", "")),
        int(value.get("seed", -1)),
        int(value.get("frame_index", -1)),
        str(value.get("comparison_key", "")),
    )


def _load_json_file(
    input_path: str | Path,
    *,
    expected_file_sha256: str | None,
) -> tuple[Path, Mapping[str, Any], str]:
    path = Path(input_path)
    if path.is_symlink():
        _fail("json_input_symlink_forbidden")
    if not path.is_file():
        _fail("json_input_missing")
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    if (
        expected_file_sha256 is not None
        and digest
        != _sha256_text(expected_file_sha256, "expected_file_sha256")
    ):
        _fail("json_input_file_sha256_mismatch")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise A2SuccessorEvidenceError(
            "json_input_invalid", str(error)
        ) from error
    return path, _mapping(payload, "json_input"), digest


def _reject_duplicate_json_keys(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            _fail("json_duplicate_key", key)
        output[key] = value
    return output


def _reject_nonfinite_json_constant(value: str) -> Any:
    _fail("json_nonfinite_value", value)


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key).strip().lower()
            parts = tuple(part for part in text.split("_") if part)
            if (
                text in _FORBIDDEN_ONLINE_KEYS
                or "truth" in parts
                or "actor" in parts
            ):
                _fail(
                    "online_truth_leakage",
                    f"forbidden field at {path}.{key}",
                )
            _assert_truth_free(child, f"{path}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            _assert_truth_free(child, f"{path}[{index}]")
        return
    if isinstance(value, float) and not isfinite(value):
        _fail("nonfinite_value", path)


def _strict_mapping(
    value: Any,
    expected_fields: frozenset[str],
    context: str,
) -> dict[str, Any]:
    item = _mapping(value, context)
    keys = {str(key) for key in item}
    if keys != expected_fields:
        missing = sorted(expected_fields - keys)
        extra = sorted(keys - expected_fields)
        _fail(
            f"{context}_fields_mismatch",
            f"missing={missing}, extra={extra}",
        )
    return {str(key): child for key, child in item.items()}


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{context}_mapping_required")
    return value


def _sequence(value: Any, context: str) -> tuple[Any, ...]:
    if not isinstance(value, (tuple, list)):
        _fail(f"{context}_sequence_required")
    return tuple(value)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name}_text_invalid")
    return value.strip()


def _sha256_text(value: Any, name: str) -> str:
    text = _required_text(value, name).lower()
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail(f"{name}_sha256_invalid")
    return text


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        _fail(f"{name}_boolean_invalid")
    return bool(value)


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name}_integer_invalid")
    return int(value)


def _nonnegative_int(value: Any, name: str) -> int:
    output = _strict_int(value, name)
    if output < 0:
        _fail(f"{name}_integer_invalid")
    return output


def _positive_int(value: Any, name: str) -> int:
    output = _strict_int(value, name)
    if output <= 0:
        _fail(f"{name}_integer_invalid")
    return output


def _finite_nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{name}_numeric_invalid")
    output = float(value)
    if not isfinite(output) or output < 0.0:
        _fail(f"{name}_numeric_invalid")
    return output


def _unit_interval(value: Any, name: str) -> float:
    output = _finite_nonnegative(value, name)
    if output > 1.0:
        _fail(f"{name}_numeric_invalid")
    return output


def _fail(reason: str, message: str | None = None) -> None:
    raise A2SuccessorEvidenceError(reason, message)


__all__ = [
    "A2_ATTRIBUTION_SCOPE",
    "A2_CURRENT_LINEAGE_IDENTITY_SCHEMA_V1",
    "A2_SUCCESSOR_EVIDENCE_BATCH_KIND",
    "A2_SUCCESSOR_EVIDENCE_BATCH_SCHEMA_V1",
    "A2_SUCCESSOR_EVIDENCE_KIND",
    "A2_SUCCESSOR_EVIDENCE_SCHEMA_V1",
    "A2CurrentLineageIdentity",
    "A2SuccessorEvidenceBatch",
    "A2SuccessorEvidenceError",
    "A2SuccessorPlanEvidence",
    "build_a2_successor_evidence_batch",
    "build_a2_successor_plan_evidence",
    "load_a2_current_lineage_identity",
    "load_a2_successor_evidence_batch",
    "validate_a2_successor_evidence_batch",
    "validate_a2_successor_plan_evidence",
    "write_a2_successor_evidence_batch",
]
