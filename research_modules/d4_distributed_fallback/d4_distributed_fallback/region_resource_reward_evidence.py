"""Fail-closed regional outcome and observational reward evidence for D4.

This module freezes the first auditable D4 regional reward definition.  It
does not train a policy and it does not grant assist or authority.  A valid
runtime advisory acknowledgement anchors an observation window; independently
hashed, truth-free regional snapshots and raw component observations then
describe what was observed during that window.

The resulting reward is temporal-window attribution only.  It is not a
counterfactual or causal gain estimate, a CoalitionMemberAck, or proof of
physical execution.  Evaluation-only refreshes may carry an observed cost but
never receive an action-attributed reward because their execution signature did
not change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isclose, isfinite
import re
from typing import Any

from .region_resource import (
    RecommendationSource,
    RegionResourceAdvisoryContract,
    RegionResourceSnapshot,
)
from .region_resource_runtime_ack import (
    RegionResourceRuntimeAckEvidence,
    RegionResourceRuntimeAdoptionKind,
    canonical_runtime_payload_sha256,
)


REGION_RESOURCE_OUTCOME_WINDOW_SCHEMA = "d4-region-resource-outcome-window-v1"
REGION_RESOURCE_OUTCOME_PROVENANCE_SCHEMA = (
    "d4-region-resource-outcome-provenance-v1"
)
REGION_RESOURCE_REWARD_COMPONENT_SCHEMA = (
    "d4-region-resource-reward-component-v1"
)
REGION_RESOURCE_REWARD_EVIDENCE_SCHEMA = (
    "d4-region-resource-reward-evidence-v1"
)
REGION_RESOURCE_REWARD_DEFINITION_VERSION = (
    "d4-region-resource-observational-reward-v1"
)
REGION_RESOURCE_REWARD_NORMALIZATION = "min(raw/denominator,1)"
REGION_RESOURCE_REWARD_FORMULA = "-sum(weight*normalized_cost)/sum(weight)"


class RegionResourceRewardComponentName(str, Enum):
    HIGH_THREAT_BACKLOG = "high_threat_backlog"
    QUOTA_SATISFACTION_SHORTFALL = "quota_satisfaction_shortfall"
    TRANSFER_COMPLETION_SHORTFALL = "transfer_completion_shortfall"
    RESERVE_SHORTFALL = "reserve_shortfall"
    COMMUNICATION_LOAD = "communication_load"
    ASSIGNMENT_CONFLICTS = "assignment_conflicts"
    DEGRADATION_FAILURES = "degradation_failures"
    PLAN_JITTER = "plan_jitter"


REGION_RESOURCE_REWARD_WEIGHTS: dict[str, float] = {
    RegionResourceRewardComponentName.HIGH_THREAT_BACKLOG.value: 3.0,
    RegionResourceRewardComponentName.QUOTA_SATISFACTION_SHORTFALL.value: 2.0,
    RegionResourceRewardComponentName.TRANSFER_COMPLETION_SHORTFALL.value: 1.0,
    RegionResourceRewardComponentName.RESERVE_SHORTFALL.value: 2.0,
    RegionResourceRewardComponentName.COMMUNICATION_LOAD.value: 0.5,
    RegionResourceRewardComponentName.ASSIGNMENT_CONFLICTS.value: 3.0,
    RegionResourceRewardComponentName.DEGRADATION_FAILURES.value: 5.0,
    RegionResourceRewardComponentName.PLAN_JITTER.value: 1.0,
}


class RegionResourceRewardEvidenceCode(str, Enum):
    AVAILABLE = "window_attributed_observational_reward_available"
    REFRESH_ONLY = "evaluation_refresh_observation_only"
    COMPONENTS_UNAVAILABLE = "required_reward_components_unavailable"
    RUNTIME_ACK_MISSING = "runtime_advisory_ack_missing"
    RUNTIME_ACK_UNAVAILABLE = "runtime_advisory_ack_unavailable"
    SCHEMA_MISMATCH = "schema_mismatch"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    UNEXPECTED_FIELD = "unexpected_field"
    INVALID_FIELD = "invalid_field"
    TRUTH_LEAKAGE = "online_truth_leakage"
    ADVISORY_BINDING_MISMATCH = "advisory_binding_mismatch"
    MODEL_FINGERPRINT_MISMATCH = "model_fingerprint_mismatch"
    PLAN_BINDING_MISMATCH = "plan_binding_mismatch"
    ACK_BINDING_MISMATCH = "ack_binding_mismatch"
    SNAPSHOT_BINDING_MISMATCH = "snapshot_binding_mismatch"
    AUTHORITY_BINDING_MISMATCH = "authority_binding_mismatch"
    STALE_GENERATION = "stale_authority_or_fault_generation"
    LEASE_EXPIRED = "authority_lease_expired_in_outcome_window"
    WINDOW_INVALID = "outcome_window_invalid"
    WINDOW_OVERLAP = "outcome_window_overlap"
    EXECUTION_BINDING_CHANGED = "execution_binding_changed_in_window"
    COALITION_BINDING_CHANGED = "coalition_binding_changed_in_window"
    PROVENANCE_INVALID = "outcome_provenance_invalid"
    PAYLOAD_HASH_MISMATCH = "payload_sha256_mismatch"


class RegionResourceComponentAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "actor_truth_id",
        "evaluator_truth",
        "evaluator_truth_id",
        "ground_truth",
        "offline_truth",
        "object_id",
        "object_name",
        "object_truth_id",
        "segmentation_id",
        "target_id",
        "target_truth_id",
        "truth",
        "truth_id",
        "truth_target_id",
    }
)


@dataclass(frozen=True)
class RegionResourceRewardComponentEvidence:
    """One raw, normalized and source-bound reward component."""

    name: str
    availability: str
    raw_value: float | None
    unit: str | None
    normalization_denominator: float | None
    normalized_cost: float | None
    source_artifact: str | None
    source_artifact_sha256: str | None
    reason: str | None
    schema: str = REGION_RESOURCE_REWARD_COMPONENT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_REWARD_COMPONENT_SCHEMA:
            raise ValueError("unsupported reward component schema")
        if self.name not in REGION_RESOURCE_REWARD_WEIGHTS:
            raise ValueError(f"unsupported reward component: {self.name}")
        availability = RegionResourceComponentAvailability(str(self.availability))
        object.__setattr__(self, "availability", availability.value)
        source_pair = (self.source_artifact, self.source_artifact_sha256)
        if (source_pair[0] is None) != (source_pair[1] is None):
            raise ValueError("component source artifact identity is incomplete")
        if self.source_artifact_sha256 is not None:
            _require_sha256(self.source_artifact_sha256, "component source SHA256")
        if availability == RegionResourceComponentAvailability.AVAILABLE:
            if not self.unit or not self.source_artifact:
                raise ValueError("available component requires unit and source artifact")
            raw = _nonnegative_float(self.raw_value, "component raw value")
            denominator = _positive_float(
                self.normalization_denominator,
                "component normalization denominator",
            )
            normalized = _unit_float(self.normalized_cost, "component normalized cost")
            expected = min(raw / denominator, 1.0)
            if not isclose(normalized, expected, rel_tol=0.0, abs_tol=1.0e-12):
                raise ValueError("component normalized cost does not match raw evidence")
            if self.reason is not None:
                raise ValueError("available component cannot carry an unavailable reason")
            object.__setattr__(self, "raw_value", raw)
            object.__setattr__(self, "normalization_denominator", denominator)
            object.__setattr__(self, "normalized_cost", normalized)
        else:
            if any(
                value is not None
                for value in (
                    self.raw_value,
                    self.unit,
                    self.normalization_denominator,
                    self.normalized_cost,
                )
            ):
                raise ValueError("unavailable component cannot carry measured values")
            if not self.reason:
                raise ValueError("unavailable component requires a reason")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceRewardComponentEvidence":
        _require_exact_keys(
            value,
            {
                "schema",
                "name",
                "availability",
                "raw_value",
                "unit",
                "normalization_denominator",
                "normalized_cost",
                "source_artifact",
                "source_artifact_sha256",
                "reason",
            },
            "reward component",
        )
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceRewardEvidence:
    """Fail-closed verdict for one ACK-anchored regional outcome window."""

    code: str
    reason: str
    outcome_window_available: bool
    observational_cost_available: bool = False
    observational_cost: float | None = None
    window_attributed_reward_available: bool = False
    window_attributed_reward: float | None = None
    attribution_scope: str = "unavailable"
    advisory_id: str | None = None
    advisory_version: int | None = None
    advisory_fingerprint_sha256: str | None = None
    model_sha256: str | None = None
    source_plan_id: str | None = None
    source_plan_version: int | None = None
    applied_plan_id: str | None = None
    applied_plan_version: int | None = None
    adoption_kind: str | None = None
    ack_bus_sequence: int | None = None
    ack_timestamp_s: float | None = None
    owner_layer: str | None = None
    owner_node_id: str | None = None
    authority_epoch: int | None = None
    lease_expires_at_s: float | None = None
    window_id: str | None = None
    window_start_s: float | None = None
    window_end_s: float | None = None
    window_payload_sha256: str | None = None
    source_snapshot_payload_sha256: str | None = None
    outcome_snapshot_payload_sha256: str | None = None
    components: tuple[RegionResourceRewardComponentEvidence, ...] = ()
    unavailable_components: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    reward_definition_version: str = REGION_RESOURCE_REWARD_DEFINITION_VERSION
    reward_normalization: str = REGION_RESOURCE_REWARD_NORMALIZATION
    reward_formula: str = REGION_RESOURCE_REWARD_FORMULA
    reward_weights: Mapping[str, float] | None = None
    coalition_member_ack_available: bool = False
    physical_execution_outcome_available: bool = False
    causal_attribution_available: bool = False
    paired_shadow_available: bool = False
    on_policy_evidence_available: bool = False
    ppo_admission_allowed: bool = False
    assist_admission_allowed: bool = False
    authority_admission_allowed: bool = False
    rule_fallback_required: bool = True
    schema: str = REGION_RESOURCE_REWARD_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_REWARD_EVIDENCE_SCHEMA:
            raise ValueError("unsupported regional reward evidence schema")
        if not self.code or not self.reason:
            raise ValueError("reward evidence code and reason must not be empty")
        weights = dict(self.reward_weights or REGION_RESOURCE_REWARD_WEIGHTS)
        if weights != REGION_RESOURCE_REWARD_WEIGHTS:
            raise ValueError("reward evidence weights differ from frozen v1 weights")
        object.__setattr__(self, "reward_weights", weights)
        if self.observational_cost_available:
            _nonnegative_float(self.observational_cost, "observational cost")
        elif self.observational_cost is not None:
            raise ValueError("unavailable observational cost cannot carry a value")
        if self.window_attributed_reward_available:
            if not self.observational_cost_available:
                raise ValueError("attributed reward requires an observed cost")
            if self.adoption_kind != (
                RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
            ):
                raise ValueError("only a new execution plan can receive window attribution")
            if self.window_attributed_reward is None or not isfinite(
                float(self.window_attributed_reward)
            ):
                raise ValueError("available attributed reward must be finite")
        elif self.window_attributed_reward is not None:
            raise ValueError("unavailable attributed reward cannot carry a value")
        if any(
            (
                self.coalition_member_ack_available,
                self.physical_execution_outcome_available,
                self.causal_attribution_available,
                self.paired_shadow_available,
                self.on_policy_evidence_available,
                self.ppo_admission_allowed,
                self.assist_admission_allowed,
                self.authority_admission_allowed,
            )
        ):
            raise ValueError("regional reward evidence cannot grant execution or learning authority")
        if self.rule_fallback_required is not True:
            raise ValueError("rule fallback remains mandatory for this evidence version")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["components"] = [item.to_dict() for item in self.components]
        payload["reward_weights"] = dict(self.reward_weights or {})
        return payload


@dataclass
class _EvidenceContext:
    advisory_id: str | None = None
    advisory_version: int | None = None
    advisory_fingerprint_sha256: str | None = None
    model_sha256: str | None = None
    source_plan_id: str | None = None
    source_plan_version: int | None = None
    applied_plan_id: str | None = None
    applied_plan_version: int | None = None
    adoption_kind: str | None = None
    ack_bus_sequence: int | None = None
    ack_timestamp_s: float | None = None
    owner_layer: str | None = None
    owner_node_id: str | None = None
    authority_epoch: int | None = None
    lease_expires_at_s: float | None = None
    window_id: str | None = None
    window_start_s: float | None = None
    window_end_s: float | None = None
    window_payload_sha256: str | None = None
    source_snapshot_payload_sha256: str | None = None
    outcome_snapshot_payload_sha256: str | None = None
    components: tuple[RegionResourceRewardComponentEvidence, ...] = ()


class _ValidationFailure(ValueError):
    def __init__(self, code: RegionResourceRewardEvidenceCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class RegionResourceRewardEvidenceAdapter:
    """Validate non-overlapping regional outcome windows once.

    Successful windows, including valid windows with unavailable components,
    are retained to prevent a later overlapping sample from entering a dataset.
    Invalid input never changes D4 authority or learning mode.
    """

    def __init__(self) -> None:
        self._accepted_window_ids: set[str] = set()
        self._intervals: dict[tuple[str, str], list[tuple[float, float]]] = {}
        self._highest_generations: dict[tuple[str, str], tuple[int, int | None]] = {}

    @property
    def accepted_window_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._accepted_window_ids))

    def evaluate(
        self,
        *,
        runtime_ack: RegionResourceRuntimeAckEvidence | None,
        advisory_source: RegionResourceAdvisoryContract | Mapping[str, Any],
        source_snapshot_source: RegionResourceSnapshot | Mapping[str, Any],
        outcome_snapshot_source: RegionResourceSnapshot | Mapping[str, Any],
        outcome_window_source: Mapping[str, Any],
    ) -> RegionResourceRewardEvidence:
        """Return strict evidence without authorizing PPO, assist or execution."""

        context = _EvidenceContext()
        try:
            if runtime_ack is None:
                _fail(
                    RegionResourceRewardEvidenceCode.RUNTIME_ACK_MISSING,
                    "runtime advisory acknowledgement is missing",
                )
            if not isinstance(runtime_ack, RegionResourceRuntimeAckEvidence):
                _fail(
                    RegionResourceRewardEvidenceCode.RUNTIME_ACK_UNAVAILABLE,
                    "runtime ACK must be validated D4 ACK evidence",
                )
            if not runtime_ack.runtime_advisory_applied_ack_available:
                _fail(
                    RegionResourceRewardEvidenceCode.RUNTIME_ACK_UNAVAILABLE,
                    "runtime advisory acknowledgement is unavailable",
                )
            _bind_ack_context(runtime_ack, context)

            advisory = _parse_advisory(advisory_source)
            source_snapshot = _parse_snapshot(source_snapshot_source, "source snapshot")
            outcome_snapshot = _parse_snapshot(
                outcome_snapshot_source,
                "outcome snapshot",
            )
            window = _mapping(outcome_window_source, "outcome window")
            _reject_truth_keys(window)
            self._validate_window(
                ack=runtime_ack,
                advisory=advisory,
                source_snapshot=source_snapshot,
                outcome_snapshot=outcome_snapshot,
                window=window,
                context=context,
            )
            self._register_window(window=window, advisory=advisory, context=context)
            return _available_or_partial_evidence(context)
        except _ValidationFailure as error:
            return _rejected_evidence(context, error)
        except (KeyError, TypeError, ValueError) as error:
            return _rejected_evidence(
                context,
                _ValidationFailure(
                    RegionResourceRewardEvidenceCode.INVALID_FIELD,
                    f"regional outcome parser rejected malformed input: {type(error).__name__}",
                ),
            )

    def _validate_window(
        self,
        *,
        ack: RegionResourceRuntimeAckEvidence,
        advisory: RegionResourceAdvisoryContract,
        source_snapshot: RegionResourceSnapshot,
        outcome_snapshot: RegionResourceSnapshot,
        window: Mapping[str, Any],
        context: _EvidenceContext,
    ) -> None:
        _require_exact_keys(
            window,
            {
                "schema",
                "window_id",
                "window_version",
                "episode_id",
                "scenario_id",
                "scenario_version",
                "seed",
                "advisory_id",
                "advisory_version",
                "advisory_fingerprint_sha256",
                "model_sha256",
                "source_plan_id",
                "source_plan_version",
                "applied_plan_id",
                "applied_plan_version",
                "adoption_kind",
                "ack_bus_sequence",
                "ack_timestamp_s",
                "owner_layer",
                "owner_node_id",
                "authority_epoch",
                "lease_expires_at_s",
                "window_start_s",
                "window_end_s",
                "window_interval",
                "source_snapshot_id",
                "source_snapshot_version",
                "source_snapshot_timestamp_s",
                "source_snapshot_payload_sha256",
                "outcome_snapshot_id",
                "outcome_snapshot_version",
                "outcome_snapshot_timestamp_s",
                "outcome_snapshot_payload_sha256",
                "execution_binding_sha256_start",
                "execution_binding_sha256_end",
                "coalition_binding_sha256_start",
                "coalition_binding_sha256_end",
                "region_generations",
                "provenance",
                "components",
                "window_payload_sha256",
            },
            "outcome window",
        )
        if window.get("schema") != REGION_RESOURCE_OUTCOME_WINDOW_SCHEMA:
            _fail(
                RegionResourceRewardEvidenceCode.SCHEMA_MISMATCH,
                "outcome window schema is unsupported",
            )
        if _positive_int(window.get("window_version"), "window version") != 1:
            _fail(
                RegionResourceRewardEvidenceCode.SCHEMA_MISMATCH,
                "outcome window version is unsupported",
            )
        window_id = _text(window.get("window_id"), "window id")
        context.window_id = window_id
        if window_id in self._accepted_window_ids:
            _fail(
                RegionResourceRewardEvidenceCode.WINDOW_OVERLAP,
                "outcome window identity was already consumed",
            )

        declared_hash = _sha256_text(
            window.get("window_payload_sha256"),
            "window payload SHA256",
        )
        actual_hash = canonical_region_resource_outcome_window_sha256(window)
        context.window_payload_sha256 = actual_hash
        if declared_hash != actual_hash:
            _fail(
                RegionResourceRewardEvidenceCode.PAYLOAD_HASH_MISMATCH,
                "outcome window payload hash is invalid",
            )

        _validate_advisory_binding(ack, advisory, window, context)
        _validate_plan_and_ack_binding(ack, window)
        _validate_snapshot_binding(
            ack=ack,
            advisory=advisory,
            source_snapshot=source_snapshot,
            outcome_snapshot=outcome_snapshot,
            window=window,
            context=context,
        )
        _validate_provenance(window)
        components = _parse_components(window)
        provenance_artifacts = _provenance_artifacts(window)
        for component in components:
            if component.source_artifact is None:
                continue
            expected = provenance_artifacts.get(component.source_artifact)
            if expected != component.source_artifact_sha256:
                _fail(
                    RegionResourceRewardEvidenceCode.PROVENANCE_INVALID,
                    f"component {component.name} is not bound to a provenance artifact",
                )
        context.components = components

    def _register_window(
        self,
        *,
        window: Mapping[str, Any],
        advisory: RegionResourceAdvisoryContract,
        context: _EvidenceContext,
    ) -> None:
        assert context.window_id is not None
        assert context.window_start_s is not None
        assert context.window_end_s is not None
        episode_id = str(window["episode_id"])
        for region in advisory.regions:
            key = (episode_id, region.region_id)
            intervals = self._intervals.setdefault(key, [])
            if any(
                context.window_start_s < end and start < context.window_end_s
                for start, end in intervals
            ):
                _fail(
                    RegionResourceRewardEvidenceCode.WINDOW_OVERLAP,
                    f"outcome window overlaps an accepted window for {region.region_id}",
                )
        bindings = _region_generation_bindings(window)
        for region in advisory.regions:
            source = region.source_version
            binding = bindings[region.region_id]
            fault_generation = binding["fault_generation"]
            key = (episode_id, region.region_id)
            previous = self._highest_generations.get(key)
            generation = (int(binding["epoch"]), fault_generation)
            if previous is not None and _generation_is_stale(generation, previous):
                _fail(
                    RegionResourceRewardEvidenceCode.STALE_GENERATION,
                    f"outcome window carries stale generation for {region.region_id}",
                )
            if int(binding["epoch"]) != int(source.epoch):
                _fail(
                    RegionResourceRewardEvidenceCode.STALE_GENERATION,
                    f"outcome window epoch differs from advisory for {region.region_id}",
                )
        for region in advisory.regions:
            key = (episode_id, region.region_id)
            binding = bindings[region.region_id]
            self._intervals[key].append(
                (context.window_start_s, context.window_end_s)
            )
            self._highest_generations[key] = (
                int(binding["epoch"]),
                binding["fault_generation"],
            )
        self._accepted_window_ids.add(context.window_id)


def canonical_region_resource_outcome_window_sha256(value: Mapping[str, Any]) -> str:
    """Hash an outcome-window payload while excluding its self-hash field."""

    payload = dict(value)
    payload.pop("window_payload_sha256", None)
    try:
        encoded = json.dumps(
            _jsonable(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail(
            RegionResourceRewardEvidenceCode.PAYLOAD_HASH_MISMATCH,
            f"outcome payload is not canonically hashable: {type(error).__name__}",
        )
    return sha256(encoded).hexdigest()


def region_resource_advisory_fingerprint_sha256(
    advisory: RegionResourceAdvisoryContract,
) -> str:
    """Bind policy, model, projector and complete advisory payload identity."""

    payload = {
        "advisory_id": advisory.advisory_id,
        "advisory_payload_sha256": canonical_runtime_payload_sha256(advisory.to_dict()),
        "policy_name": advisory.policy_name,
        "policy_version": advisory.policy_version,
        "source": advisory.source.value,
        "model_sha256": advisory.model_sha256,
        "projector_name": advisory.projector_name,
        "projector_version": advisory.projector_version,
    }
    return _canonical_sha256(payload)


def _bind_ack_context(
    ack: RegionResourceRuntimeAckEvidence,
    context: _EvidenceContext,
) -> None:
    context.advisory_id = ack.advisory_id
    context.advisory_version = ack.advisory_version
    context.source_plan_id = ack.source_plan_id
    context.source_plan_version = ack.source_plan_version
    context.applied_plan_id = ack.applied_plan_id
    context.applied_plan_version = ack.applied_plan_version
    context.adoption_kind = ack.adoption_kind
    context.ack_bus_sequence = ack.ack_bus_sequence
    context.ack_timestamp_s = ack.acknowledged_at_s
    context.owner_layer = ack.owner_layer
    context.owner_node_id = ack.owner_node_id
    context.authority_epoch = ack.authority_epoch
    context.lease_expires_at_s = ack.lease_expires_at_s
    required = (
        ack.advisory_id,
        ack.advisory_version,
        ack.source_plan_id,
        ack.source_plan_version,
        ack.applied_plan_id,
        ack.applied_plan_version,
        ack.adoption_kind,
        ack.ack_bus_sequence,
        ack.acknowledged_at_s,
        ack.owner_layer,
        ack.owner_node_id,
        ack.authority_epoch,
        ack.lease_expires_at_s,
        ack.advisory_payload_sha256,
        ack.source_plan_payload_sha256,
    )
    if any(value is None for value in required):
        _fail(
            RegionResourceRewardEvidenceCode.RUNTIME_ACK_UNAVAILABLE,
            "runtime ACK lacks fields required for reward-window attribution",
        )


def _validate_advisory_binding(
    ack: RegionResourceRuntimeAckEvidence,
    advisory: RegionResourceAdvisoryContract,
    window: Mapping[str, Any],
    context: _EvidenceContext,
) -> None:
    advisory_hash = canonical_runtime_payload_sha256(advisory.to_dict())
    if advisory_hash != ack.advisory_payload_sha256:
        _fail(
            RegionResourceRewardEvidenceCode.ADVISORY_BINDING_MISMATCH,
            "runtime ACK advisory hash differs from the supplied advisory",
        )
    expected_fingerprint = region_resource_advisory_fingerprint_sha256(advisory)
    context.advisory_fingerprint_sha256 = expected_fingerprint
    context.model_sha256 = advisory.model_sha256
    if advisory.source == RecommendationSource.LEARNED:
        if advisory.model_sha256 is None:
            _fail(
                RegionResourceRewardEvidenceCode.MODEL_FINGERPRINT_MISMATCH,
                "learned advisory lacks a model SHA256",
            )
        _require_sha256(advisory.model_sha256, "advisory model SHA256")
    elif advisory.model_sha256 is not None:
        _require_sha256(advisory.model_sha256, "advisory model SHA256")
    expected = {
        "advisory_id": ack.advisory_id,
        "advisory_version": ack.advisory_version,
        "advisory_fingerprint_sha256": expected_fingerprint,
        "model_sha256": advisory.model_sha256,
    }
    if any(window.get(name) != value for name, value in expected.items()):
        _fail(
            RegionResourceRewardEvidenceCode.MODEL_FINGERPRINT_MISMATCH,
            "outcome window advisory or model fingerprint differs from runtime evidence",
        )


def _validate_plan_and_ack_binding(
    ack: RegionResourceRuntimeAckEvidence,
    window: Mapping[str, Any],
) -> None:
    expected = {
        "source_plan_id": ack.source_plan_id,
        "source_plan_version": ack.source_plan_version,
        "applied_plan_id": ack.applied_plan_id,
        "applied_plan_version": ack.applied_plan_version,
        "adoption_kind": ack.adoption_kind,
    }
    if any(window.get(name) != value for name, value in expected.items()):
        _fail(
            RegionResourceRewardEvidenceCode.PLAN_BINDING_MISMATCH,
            "outcome window source/current plan or adoption kind differs from ACK",
        )
    if (
        window.get("ack_bus_sequence") != ack.ack_bus_sequence
        or not _same_time(window.get("ack_timestamp_s"), ack.acknowledged_at_s)
    ):
        _fail(
            RegionResourceRewardEvidenceCode.ACK_BINDING_MISMATCH,
            "outcome window ACK sequence or timestamp differs from runtime evidence",
        )
    expected_authority = {
        "owner_layer": ack.owner_layer,
        "owner_node_id": ack.owner_node_id,
        "authority_epoch": ack.authority_epoch,
        "lease_expires_at_s": ack.lease_expires_at_s,
    }
    if any(window.get(name) != value for name, value in expected_authority.items()):
        _fail(
            RegionResourceRewardEvidenceCode.AUTHORITY_BINDING_MISMATCH,
            "outcome window owner, epoch, or lease differs from runtime ACK",
        )
    start = _nonnegative_float(window.get("window_start_s"), "window start")
    end = _positive_float(window.get("window_end_s"), "window end")
    if not _same_time(start, ack.acknowledged_at_s) or end <= start:
        _fail(
            RegionResourceRewardEvidenceCode.WINDOW_INVALID,
            "outcome window must begin at ACK time and have positive duration",
        )
    if window.get("window_interval") != "left_closed_right_open":
        _fail(
            RegionResourceRewardEvidenceCode.WINDOW_INVALID,
            "outcome window interval must be left-closed/right-open",
        )
    assert ack.lease_expires_at_s is not None
    if end >= float(ack.lease_expires_at_s):
        _fail(
            RegionResourceRewardEvidenceCode.LEASE_EXPIRED,
            "outcome window reaches or exceeds the active authority lease",
        )
    execution_start = _sha256_text(
        window.get("execution_binding_sha256_start"),
        "execution binding start SHA256",
    )
    execution_end = _sha256_text(
        window.get("execution_binding_sha256_end"),
        "execution binding end SHA256",
    )
    if execution_start != ack.source_plan_payload_sha256:
        _fail(
            RegionResourceRewardEvidenceCode.PLAN_BINDING_MISMATCH,
            "window execution binding does not match the applied D3 plan payload",
        )
    if execution_start != execution_end:
        _fail(
            RegionResourceRewardEvidenceCode.EXECUTION_BINDING_CHANGED,
            "execution binding changed inside the outcome window",
        )
    coalition_start = _sha256_text(
        window.get("coalition_binding_sha256_start"),
        "coalition binding start SHA256",
    )
    coalition_end = _sha256_text(
        window.get("coalition_binding_sha256_end"),
        "coalition binding end SHA256",
    )
    if coalition_start != coalition_end:
        _fail(
            RegionResourceRewardEvidenceCode.COALITION_BINDING_CHANGED,
            "coalition binding changed inside the outcome window",
        )


def _validate_snapshot_binding(
    *,
    ack: RegionResourceRuntimeAckEvidence,
    advisory: RegionResourceAdvisoryContract,
    source_snapshot: RegionResourceSnapshot,
    outcome_snapshot: RegionResourceSnapshot,
    window: Mapping[str, Any],
    context: _EvidenceContext,
) -> None:
    if (
        source_snapshot.snapshot_id != advisory.snapshot_id
        or source_snapshot.snapshot_version != advisory.snapshot_version
        or source_snapshot.authority_digest != advisory.authority_digest
        or not _same_time(source_snapshot.timestamp_s, advisory.snapshot_timestamp_s)
    ):
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            "source snapshot differs from the advisory source identity",
        )
    common_identity = (
        source_snapshot.scenario_id,
        source_snapshot.scenario_version,
        source_snapshot.seed,
    )
    if common_identity != (
        outcome_snapshot.scenario_id,
        outcome_snapshot.scenario_version,
        outcome_snapshot.seed,
    ) or common_identity != (
        window.get("scenario_id"),
        window.get("scenario_version"),
        window.get("seed"),
    ):
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            "source/outcome snapshots and window belong to different scenarios",
        )
    if not _text(window.get("episode_id"), "episode id"):
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            "episode identity is empty",
        )
    source_hash = canonical_runtime_payload_sha256(source_snapshot.to_dict())
    outcome_hash = canonical_runtime_payload_sha256(outcome_snapshot.to_dict())
    context.source_snapshot_payload_sha256 = source_hash
    context.outcome_snapshot_payload_sha256 = outcome_hash
    source_expected = {
        "source_snapshot_id": source_snapshot.snapshot_id,
        "source_snapshot_version": source_snapshot.snapshot_version,
        "source_snapshot_timestamp_s": source_snapshot.timestamp_s,
        "source_snapshot_payload_sha256": source_hash,
    }
    outcome_expected = {
        "outcome_snapshot_id": outcome_snapshot.snapshot_id,
        "outcome_snapshot_version": outcome_snapshot.snapshot_version,
        "outcome_snapshot_timestamp_s": outcome_snapshot.timestamp_s,
        "outcome_snapshot_payload_sha256": outcome_hash,
    }
    if any(window.get(name) != value for name, value in source_expected.items()) or any(
        window.get(name) != value for name, value in outcome_expected.items()
    ):
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            "outcome window snapshot identity or payload hash is invalid",
        )
    if not _same_time(outcome_snapshot.timestamp_s, window.get("window_end_s")):
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            "outcome snapshot does not close the declared observation window",
        )
    if source_snapshot.timestamp_s > float(window["window_start_s"]):
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            "advisory source snapshot was recorded after the ACK window start",
        )
    source_regions = source_snapshot.region_by_id
    outcome_regions = outcome_snapshot.region_by_id
    advisory_regions = {item.region_id: item for item in advisory.regions}
    if set(source_regions) != set(outcome_regions) or set(source_regions) != set(
        advisory_regions
    ):
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            "regional inventory changed inside the attributed window",
        )
    bindings = _region_generation_bindings(window)
    if set(bindings) != set(advisory_regions):
        _fail(
            RegionResourceRewardEvidenceCode.AUTHORITY_BINDING_MISMATCH,
            "region generation bindings do not cover the advisory regions exactly",
        )
    for region_id, advisory_region in advisory_regions.items():
        source_version = advisory_region.source_version
        source_node = source_regions[region_id]
        outcome_node = outcome_regions[region_id]
        binding = bindings[region_id]
        expected = {
            "owner_layer": source_version.owner_layer.value,
            "owner_node_id": source_version.owner_id,
            "epoch": source_version.epoch,
            "lease_expires_at_s": source_version.lease_expires_at_s,
            "fault_generation": source_version.fault_fence_epoch,
        }
        if any(binding.get(name) != value for name, value in expected.items()):
            _fail(
                RegionResourceRewardEvidenceCode.AUTHORITY_BINDING_MISMATCH,
                f"region authority generation mismatch for {region_id}",
            )
        if binding["lease_expires_at_s"] <= float(window["window_end_s"]):
            _fail(
                RegionResourceRewardEvidenceCode.LEASE_EXPIRED,
                f"regional lease expires inside the outcome window for {region_id}",
            )
        if (
            source_node.current_owner_layer.value != binding["owner_layer"]
            or source_node.current_owner_id != binding["owner_node_id"]
            or source_node.epoch != binding["epoch"]
            or source_node.lease_expires_at_s != binding["lease_expires_at_s"]
            or source_node.fault_fence_epoch != binding["fault_generation"]
            or outcome_node.current_owner_layer.value != binding["owner_layer"]
            or outcome_node.current_owner_id != binding["owner_node_id"]
            or outcome_node.epoch != binding["epoch"]
            or outcome_node.lease_expires_at_s != binding["lease_expires_at_s"]
            or outcome_node.fault_fence_epoch != binding["fault_generation"]
        ):
            _fail(
                RegionResourceRewardEvidenceCode.STALE_GENERATION,
                f"source or outcome snapshot carries a changed generation for {region_id}",
            )
        if (
            not outcome_node.owner_active
            or outcome_node.fault_fenced
            or not outcome_node.coalition_ack_complete
        ):
            _fail(
                RegionResourceRewardEvidenceCode.AUTHORITY_BINDING_MISMATCH,
                f"outcome authority is inactive, fenced, or unacknowledged for {region_id}",
            )
        if (
            outcome_node.plan_id != ack.applied_plan_id
            or outcome_node.plan_version != ack.applied_plan_version
        ):
            _fail(
                RegionResourceRewardEvidenceCode.PLAN_BINDING_MISMATCH,
                f"outcome snapshot plan generation differs for {region_id}",
            )
    context.window_start_s = float(window["window_start_s"])
    context.window_end_s = float(window["window_end_s"])


def _validate_provenance(window: Mapping[str, Any]) -> None:
    provenance = _mapping(window.get("provenance"), "outcome provenance")
    _require_exact_keys(
        provenance,
        {
            "schema",
            "producer_name",
            "producer_version",
            "episode_id",
            "clock",
            "online_truth_use_count",
            "source_artifacts",
        },
        "outcome provenance",
    )
    if provenance.get("schema") != REGION_RESOURCE_OUTCOME_PROVENANCE_SCHEMA:
        _fail(
            RegionResourceRewardEvidenceCode.SCHEMA_MISMATCH,
            "outcome provenance schema is unsupported",
        )
    if (
        not _text(provenance.get("producer_name"), "provenance producer")
        or not _text(provenance.get("producer_version"), "provenance version")
        or provenance.get("episode_id") != window.get("episode_id")
        or provenance.get("clock") != "episode_clock"
    ):
        _fail(
            RegionResourceRewardEvidenceCode.PROVENANCE_INVALID,
            "outcome producer, episode, or clock provenance is invalid",
        )
    if _nonnegative_int(
        provenance.get("online_truth_use_count"),
        "online truth use count",
    ) != 0:
        _fail(
            RegionResourceRewardEvidenceCode.TRUTH_LEAKAGE,
            "outcome provenance reports online truth use",
        )
    _provenance_artifacts(window)


def _provenance_artifacts(window: Mapping[str, Any]) -> dict[str, str]:
    provenance = _mapping(window.get("provenance"), "outcome provenance")
    values = _sequence(provenance.get("source_artifacts"), "source artifacts")
    if not values:
        _fail(
            RegionResourceRewardEvidenceCode.PROVENANCE_INVALID,
            "outcome provenance requires source artifacts",
        )
    artifacts: dict[str, str] = {}
    for raw in values:
        item = _mapping(raw, "source artifact")
        _require_exact_keys(item, {"name", "schema", "sha256"}, "source artifact")
        name = _text(item.get("name"), "source artifact name")
        if name in artifacts or not _text(item.get("schema"), "source artifact schema"):
            _fail(
                RegionResourceRewardEvidenceCode.PROVENANCE_INVALID,
                "source artifact identity is empty or duplicated",
            )
        artifacts[name] = _sha256_text(item.get("sha256"), "source artifact SHA256")
    return artifacts


def _parse_components(
    window: Mapping[str, Any],
) -> tuple[RegionResourceRewardComponentEvidence, ...]:
    raw_components = _sequence(window.get("components"), "reward components")
    parsed: dict[str, RegionResourceRewardComponentEvidence] = {}
    for raw in raw_components:
        try:
            component = RegionResourceRewardComponentEvidence.from_mapping(
                _mapping(raw, "reward component")
            )
        except _ValidationFailure:
            raise
        except (TypeError, ValueError) as error:
            _fail(
                RegionResourceRewardEvidenceCode.INVALID_FIELD,
                f"reward component is invalid: {type(error).__name__}",
            )
        if component.name in parsed:
            _fail(
                RegionResourceRewardEvidenceCode.INVALID_FIELD,
                f"reward component {component.name} is duplicated",
            )
        parsed[component.name] = component
    required = set(REGION_RESOURCE_REWARD_WEIGHTS)
    if set(parsed) != required:
        missing = sorted(required - set(parsed))
        extra = sorted(set(parsed) - required)
        _fail(
            RegionResourceRewardEvidenceCode.REQUIRED_FIELD_MISSING,
            f"reward component inventory mismatch; missing={missing}, extra={extra}",
        )
    return tuple(parsed[name] for name in sorted(parsed))


def _region_generation_bindings(
    window: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    values = _sequence(window.get("region_generations"), "region generations")
    result: dict[str, dict[str, Any]] = {}
    for raw in values:
        item = _mapping(raw, "region generation")
        _require_exact_keys(
            item,
            {
                "region_id",
                "owner_layer",
                "owner_node_id",
                "epoch",
                "lease_expires_at_s",
                "fault_generation",
            },
            "region generation",
        )
        region_id = _text(item.get("region_id"), "region id")
        if region_id in result:
            _fail(
                RegionResourceRewardEvidenceCode.AUTHORITY_BINDING_MISMATCH,
                "region generation inventory contains duplicates",
            )
        owner_node_id = item.get("owner_node_id")
        if owner_node_id is not None:
            owner_node_id = _text(owner_node_id, "region owner node id")
        fault_generation = item.get("fault_generation")
        if fault_generation is not None:
            fault_generation = _nonnegative_int(
                fault_generation,
                "fault generation",
            )
        result[region_id] = {
            "owner_layer": _text(item.get("owner_layer"), "region owner layer"),
            "owner_node_id": owner_node_id,
            "epoch": _nonnegative_int(item.get("epoch"), "region epoch"),
            "lease_expires_at_s": _positive_float(
                item.get("lease_expires_at_s"),
                "region lease expiry",
            ),
            "fault_generation": fault_generation,
        }
    return result


def _available_or_partial_evidence(
    context: _EvidenceContext,
) -> RegionResourceRewardEvidence:
    unavailable = tuple(
        item.name
        for item in context.components
        if item.availability == RegionResourceComponentAvailability.UNAVAILABLE.value
    )
    all_available = not unavailable
    observational_cost = None
    if all_available:
        weighted = sum(
            REGION_RESOURCE_REWARD_WEIGHTS[item.name] * float(item.normalized_cost)
            for item in context.components
        )
        observational_cost = weighted / sum(REGION_RESOURCE_REWARD_WEIGHTS.values())
    new_execution = context.adoption_kind == (
        RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
    )
    attributed = bool(all_available and new_execution)
    if not all_available:
        code = RegionResourceRewardEvidenceCode.COMPONENTS_UNAVAILABLE
        reason = (
            "outcome window is valid but required reward components are explicitly "
            f"unavailable: {', '.join(unavailable)}"
        )
        scope = "validated_window_components_incomplete"
    elif not new_execution:
        code = RegionResourceRewardEvidenceCode.REFRESH_ONLY
        reason = (
            "evaluation refresh has a valid observed regional cost but no changed "
            "execution signature to receive action attribution"
        )
        scope = "evaluation_refresh_observation_only_noncausal"
    else:
        code = RegionResourceRewardEvidenceCode.AVAILABLE
        reason = (
            "all frozen v1 components are source-bound to a non-overlapping new-plan "
            "observation window; attribution is temporal and noncausal"
        )
        scope = "new_execution_plan_temporal_window_only_noncausal"
    values = asdict(context)
    values["components"] = tuple(context.components)
    return RegionResourceRewardEvidence(
        code=code.value,
        reason=reason,
        outcome_window_available=True,
        observational_cost_available=all_available,
        observational_cost=observational_cost,
        window_attributed_reward_available=attributed,
        window_attributed_reward=(-observational_cost if attributed else None),
        attribution_scope=scope,
        unavailable_components=unavailable,
        rejection_reasons=(),
        **values,
    )


def _rejected_evidence(
    context: _EvidenceContext,
    error: _ValidationFailure,
) -> RegionResourceRewardEvidence:
    values = asdict(context)
    values["components"] = tuple(context.components)
    return RegionResourceRewardEvidence(
        code=error.code.value,
        reason=error.reason,
        outcome_window_available=False,
        attribution_scope="unavailable_fail_closed",
        rejection_reasons=(error.code.value,),
        **values,
    )


def _parse_advisory(
    value: RegionResourceAdvisoryContract | Mapping[str, Any],
) -> RegionResourceAdvisoryContract:
    if isinstance(value, RegionResourceAdvisoryContract):
        return value
    mapping = _mapping(value, "advisory")
    _reject_truth_keys(mapping)
    try:
        return RegionResourceAdvisoryContract.from_dict(mapping)
    except (KeyError, TypeError, ValueError) as error:
        _fail(
            RegionResourceRewardEvidenceCode.ADVISORY_BINDING_MISMATCH,
            f"advisory contract is invalid: {type(error).__name__}",
        )


def _parse_snapshot(
    value: RegionResourceSnapshot | Mapping[str, Any],
    name: str,
) -> RegionResourceSnapshot:
    if isinstance(value, RegionResourceSnapshot):
        return value
    mapping = _mapping(value, name)
    _reject_truth_keys(mapping)
    try:
        return RegionResourceSnapshot.from_dict(mapping)
    except (KeyError, TypeError, ValueError) as error:
        _fail(
            RegionResourceRewardEvidenceCode.SNAPSHOT_BINDING_MISMATCH,
            f"{name} is invalid: {type(error).__name__}",
        )


def _generation_is_stale(
    current: tuple[int, int | None],
    previous: tuple[int, int | None],
) -> bool:
    if current[0] < previous[0]:
        return True
    if previous[1] is None:
        return False
    return current[1] is None or current[1] < previous[1]


def _reject_truth_keys(value: Any, path: str = "outcome_window") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_KEYS or "ground_truth" in normalized:
                _fail(
                    RegionResourceRewardEvidenceCode.TRUTH_LEAKAGE,
                    f"truth-bearing field is forbidden at {path}.{key}",
                )
            _reject_truth_keys(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, item in enumerate(value):
            _reject_truth_keys(item, f"{path}[{index}]")


def _require_exact_keys(
    mapping: Mapping[str, Any],
    expected: set[str],
    path: str,
) -> None:
    missing = sorted(expected - set(mapping))
    extra = sorted(set(mapping) - expected)
    if missing:
        _fail(
            RegionResourceRewardEvidenceCode.REQUIRED_FIELD_MISSING,
            f"{path} is missing required fields: {missing}",
        )
    if extra:
        _fail(
            RegionResourceRewardEvidenceCode.UNEXPECTED_FIELD,
            f"{path} contains unsupported fields: {extra}",
        )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a mapping",
        )
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a sequence",
        )
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be non-empty text",
        )
    return value.strip()


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a non-negative integer",
        )
    return int(value)


def _positive_int(value: Any, path: str) -> int:
    result = _nonnegative_int(value, path)
    if result <= 0:
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be positive",
        )
    return result


def _nonnegative_float(value: Any, path: str) -> float:
    if isinstance(value, bool):
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a finite non-negative number",
        )
    try:
        result = float(value)
    except (TypeError, ValueError):
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a finite non-negative number",
        )
    if not isfinite(result) or result < 0.0:
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a finite non-negative number",
        )
    return result


def _positive_float(value: Any, path: str) -> float:
    result = _nonnegative_float(value, path)
    if result <= 0.0:
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be positive",
        )
    return result


def _unit_float(value: Any, path: str) -> float:
    result = _nonnegative_float(value, path)
    if result > 1.0:
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be in [0, 1]",
        )
    return result


def _sha256_text(value: Any, path: str) -> str:
    text = _text(value, path).lower()
    _require_sha256(text, path)
    return text


def _require_sha256(value: str, path: str) -> None:
    if _SHA256.fullmatch(str(value).lower()) is None:
        _fail(
            RegionResourceRewardEvidenceCode.INVALID_FIELD,
            f"{path} must be a lowercase SHA256 digest",
        )


def _same_time(left: Any, right: Any) -> bool:
    try:
        return isclose(float(left), float(right), rel_tol=0.0, abs_tol=1.0e-9)
    except (TypeError, ValueError):
        return False


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _fail(code: RegionResourceRewardEvidenceCode, reason: str) -> None:
    raise _ValidationFailure(code, reason)
