"""Strict, read-only D6 audit for A1/A2/A3 learning adoption evidence.

The audit consumes only explicitly supplied records.  It never executes a
policy, publishes a plan, adopts advice, moves a camera, changes a track ID, or
grants runtime authority.  Missing public module validators and missing
runtime lineage remain unavailable rather than being inferred from counters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields
from hashlib import sha256
import importlib
import json
from math import isfinite
from pathlib import Path
from typing import Any


LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION = (
    "d6.strict-learning-adoption-audit-input.v1"
)
LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2 = (
    "d6.strict-learning-adoption-audit-input.v2"
)
LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION_V1 = (
    "d6.strict-learning-adoption-audit.v1"
)
LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION_V2 = (
    "d6.strict-learning-adoption-audit.v2"
)
LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION_V3 = (
    "d6.strict-learning-adoption-audit.v3"
)
LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION = (
    "d6.strict-learning-adoption-audit.v4"
)
LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION_V1 = (
    "d6.strict-learning-adoption-audit-consumer.v1"
)
LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION_V2 = (
    "d6.strict-learning-adoption-audit-consumer.v2"
)
LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION_V3 = (
    "d6.strict-learning-adoption-audit-consumer.v3"
)
LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION = (
    "d6.strict-learning-adoption-audit-consumer.v4"
)
LEARNING_ADOPTION_EPISODE_RECORDS_SCHEMA_VERSION = (
    "scalable3d-learning-adoption-evidence-records-v1"
)

_INPUT_FIELDS_BY_SCHEMA = {
    LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION: frozenset(
        {"schema_version", "a1", "a2", "a3", "content_sha256"}
    ),
    LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2: frozenset(
        {
            "schema_version",
            "a1",
            "a2",
            "a3",
            "a3_pairing_dispositions",
            "content_sha256",
        }
    ),
}
_EPISODE_RECORD_FIELDS = frozenset(
    {"schema_version", "episode_id", "records", "content_sha256"}
)
_AUDIT_OUTPUT_FIELDS = frozenset(
    {
        "schema_version",
        "consumer_schema_version",
        "input_schema_version",
        "input_content_sha256",
        "scope",
        "availability",
        "variants",
        "aggregate",
        "blocker_codes",
        "permissions",
        "content_sha256",
    }
)
_A3_PAIRING_INVENTORY_SCHEMA_VERSION_V1 = (
    "d6.a3-pairing-disposition-inventory.v1"
)
_A3_PAIRING_INVENTORY_SCHEMA_VERSION = (
    "d6.a3-pairing-disposition-inventory.v2"
)
_A3_PAIRING_INVENTORY_FIELDS = frozenset(
    {
        "schema_version",
        "declared",
        "scope",
        "availability",
        "complete_model_evidence_claimed",
        "record_count",
        "validated_record_count",
        "candidate_count",
        "pairable_count",
        "unpairable_count",
        "pairing_coverage",
        "reason_code_counts",
        "top_level_reason_code_counts",
        "disposition_schema_version_counts",
        "candidate_stage_evidence_count",
        "candidate_stage_evidence_missing_count",
        "detail_reason_record_count",
        "detail_reasonless_record_count",
        "detail_reason_assignment_count",
        "detail_reason_code_counts",
        "top_level_detail_reason_counts",
        "physical_window_missing_detail_scope_count",
        "physical_window_missing_detail_evidenced_count",
        "physical_window_missing_detail_unresolved_count",
        "physical_window_missing_detail_completeness",
        "inventory_completeness",
        "paired_evidence_completeness",
    }
)
_A3_TOP_LEVEL_DETAIL_ROW_FIELDS = frozenset(
    {
        "record_count",
        "records_with_detail_reason_count",
        "records_without_detail_reason_count",
        "detail_reason_assignment_count",
        "detail_reason_code_counts",
    }
)
_A3_OBSERVATION_OUTCOME_INVENTORY_SCHEMA_VERSION = (
    "d6.a3-observation-outcome-inventory.v1"
)
_A3_OBSERVATION_OUTCOME_INVENTORY_FIELDS = frozenset(
    {
        "schema_version",
        "scope",
        "availability",
        "reason_codes",
        "candidate_window_count",
        "observation_frame_count",
        "tracklets_observed_frame_count",
        "processed_zero_detection_frame_count",
        "association_outcome_available",
        "association_evaluable_frame_count",
        "association_locked_count",
        "association_ambiguous_count",
        "association_hold_count",
        "association_reacquire_count",
        "coverage_outcome_available",
        "assigned_reference_count",
        "visible_assigned_reference_count",
        "coverage_fraction",
        "zero_detection_locked_or_ambiguous_count",
    }
)
_A3_FRAME_OBSERVATION_STATES = frozenset(
    {"tracklets_observed", "processed_zero_detections"}
)
_VARIANTS = ("A1", "A2", "A3")
_AUTHORITY_FIELDS = (
    "model_promotion_authority",
    "assist_authority",
    "a2_assist_authority",
    "active_vision_assist_authority",
    "g1_authorization_granted",
    "default_path_authority",
    "assignment_authority",
    "failover_authority",
    "camera_command_authority",
    "control_authority",
    "global_track_id_mutation_authority",
)
_A1_VALIDATORS = {
    "d3.a1-intervention-preregistration.v1": (
        "preregistration",
        "validate_a1_intervention_preregistration",
    ),
    "d3.a1-intervention-candidate-evidence.v1": (
        "candidate",
        "validate_a1_intervention_candidate_evidence",
    ),
    "d3.a1-intervention-selection-decision.v1": (
        "selection",
        "validate_a1_intervention_selection_decision",
    ),
    "d3.a1-plan-publication-evidence.v1": (
        "publication",
        "validate_a1_plan_publication_evidence",
    ),
    "d3.a1-intervention-lifecycle-evidence.v1": (
        "lifecycle",
        "validate_a1_intervention_lifecycle_evidence",
    ),
}
_A1_BATCH_SCHEMAS = frozenset(
    {
        "d3.a1-isolated-intervention-batch-result.v1",
        "d3.a1-isolated-intervention-candidate-evidence.v1",
        "d3.a1-isolated-intervention-candidate-inventory.v1",
        "d3.a1-isolated-intervention-selection-decision.v1",
        "d3.a1-isolated-intervention-selection-inventory.v1",
    }
)
_A2_SAFE_ADOPTION_SCHEMA = "d4-region-resource-safe-adoption-evidence-v1"
_A2_PAIR_SCHEMA = "d4-region-resource-a2-benefit-audit-input-v1"
_A2_PAIR_BATCH_SCHEMA = "d4-region-resource-a2-benefit-audit-batch-v1"
_A3_PAIR_SCHEMA = "d5.active-vision-a3-benefit-audit-input.v1"
_A1_FORBIDDEN_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "airsim_id",
        "ground_truth",
        "ground_truth_id",
        "intercept_success",
        "object_id",
        "object_name",
        "offline_truth_labels",
        "physical_outcome",
        "reward",
        "truth",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
    }
)
_A2_FORBIDDEN_KEYS = _A1_FORBIDDEN_KEYS | frozenset(
    {"offline_outcome", "offline_reward", "outcome", "outcome_value"}
)
_A3_FORBIDDEN_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "airsim_id",
        "ground_truth",
        "ground_truth_id",
        "object_id",
        "object_name",
        "offline_truth_labels",
        "truth",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
    }
)
_A1_STAGE_RANK = {
    "unavailable": 0,
    "preregistered": 1,
    "candidate_validated": 2,
    "candidate_selected": 3,
    "plan_published": 4,
    "runtime_ack_claim_validated": 5,
    "physical_window_claim_validated": 6,
    "r0_pair_claim_validated": 7,
}
_A2_STAGE_RANK = {
    "unavailable": 0,
    "candidate_rejected": 1,
    "applied_recommendation_prepared": 2,
    "awaiting_d3_plan": 2,
    "awaiting_runtime_ack": 3,
    "awaiting_owner_ack": 4,
    "awaiting_coalition_commit": 5,
    "awaiting_physical_window": 6,
    "safe_adoption_rejected": 6,
    "physical_window_available": 7,
    "same_key_r0_validated": 8,
    "auditable_benefit_input": 9,
}
_A3_STAGE_RANK = {
    "unavailable": 0,
    "policy_evaluated": 1,
    "command_proposed": 2,
    "command_issued": 3,
    "runtime_ack_applied": 4,
    "camera_pose_applied": 5,
    "physical_window_validated": 6,
    "same_key_r0_validated": 7,
    "auditable_benefit_input": 8,
}
_PUBLIC_MODULE_LAYOUTS = {
    "d3_assignment_planner.a1_intervention_selection": (
        "research_modules.d3_assignment_planner.src."
        "d3_assignment_planner.a1_intervention_selection"
    ),
    "d4_distributed_fallback.region_resource_safe_adoption": (
        "research_modules.d4_distributed_fallback."
        "d4_distributed_fallback.region_resource_safe_adoption"
    ),
    "d4_distributed_fallback.region_resource_a2_benefit_audit": (
        "research_modules.d4_distributed_fallback."
        "d4_distributed_fallback.region_resource_a2_benefit_audit"
    ),
    "d4_distributed_fallback.region_resource": (
        "research_modules.d4_distributed_fallback."
        "d4_distributed_fallback.region_resource"
    ),
    "d4_distributed_fallback.region_resource_runtime_ack": (
        "research_modules.d4_distributed_fallback."
        "d4_distributed_fallback.region_resource_runtime_ack"
    ),
    "d4_distributed_fallback.communication_causal_evidence": (
        "research_modules.d4_distributed_fallback."
        "d4_distributed_fallback.communication_causal_evidence"
    ),
    "d5_terminal_association.active_vision_a3_evidence_assembler": (
        "research_modules.d5_terminal_association.src."
        "d5_terminal_association.active_vision_a3_evidence_assembler"
    ),
}


class StrictLearningAdoptionAuditError(ValueError):
    """Stable request-level validation error."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = str(code)
        self.detail = None if detail is None else str(detail)
        message = self.code if self.detail is None else f"{self.code}: {self.detail}"
        super().__init__(message)


class _PublicModuleUnavailable(ImportError):
    """Raised only when neither supported layout contains the requested module."""


def _import_public_module(module_name: str) -> Any:
    """Resolve installed/PYTHONPATH and repository-root package layouts.

    A fallback is attempted only when the requested module or one of its
    package parents is absent. Missing dependencies and other import-time
    failures are real module errors and remain visible to the caller.
    """

    repository_name = _PUBLIC_MODULE_LAYOUTS[module_name]
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if not _requested_module_missing(exc, module_name):
            raise
    try:
        return importlib.import_module(repository_name)
    except ModuleNotFoundError as exc:
        if not _requested_module_missing(exc, repository_name):
            raise
        raise _PublicModuleUnavailable(module_name) from exc


def _requested_module_missing(
    exc: ModuleNotFoundError,
    requested_name: str,
) -> bool:
    missing_name = exc.name
    return bool(
        missing_name
        and (
            missing_name == requested_name
            or requested_name.startswith(f"{missing_name}.")
        )
    )


def _validate_a3_pairing_inventory_output(
    inventory: Mapping[str, Any],
) -> None:
    """Import-stable entry point for the strict A3 inventory validator."""

    _validate_a3_pairing_inventory_output_impl(inventory)


def build_learning_adoption_audit_input(
    *,
    a1: Sequence[Mapping[str, Any]] = (),
    a2: Sequence[Mapping[str, Any]] = (),
    a3: Sequence[Mapping[str, Any]] = (),
    a3_pairing_dispositions: (
        Sequence[Mapping[str, Any]] | None
    ) = None,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Build one immutable, inline audit request."""

    selected_schema = (
        (
            LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2
            if a3_pairing_dispositions is not None
            else LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION
        )
        if schema_version is None
        else str(schema_version)
    )
    if selected_schema not in _INPUT_FIELDS_BY_SCHEMA:
        _fail("audit_input_schema_unsupported")
    if (
        selected_schema == LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION
        and a3_pairing_dispositions is not None
    ):
        _fail("audit_input_v1_pairing_dispositions_forbidden")
    payload: dict[str, Any] = {
        "schema_version": selected_schema,
        "a1": [_strict_json_mapping(item, "a1") for item in a1],
        "a2": [_strict_json_mapping(item, "a2") for item in a2],
        "a3": [_strict_json_mapping(item, "a3") for item in a3],
    }
    if selected_schema == LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2:
        payload["a3_pairing_dispositions"] = [
            _strict_json_mapping(item, "a3_pairing_dispositions")
            for item in (a3_pairing_dispositions or ())
        ]
    _assert_finite(payload)
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def validate_learning_adoption_audit_input(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact fields and the request content digest."""

    payload = _strict_mapping(value, "audit_input")
    schema_version = payload.get("schema_version")
    if (
        not isinstance(schema_version, str)
        or schema_version not in _INPUT_FIELDS_BY_SCHEMA
    ):
        _fail("audit_input_schema_unsupported")
    expected_fields = _INPUT_FIELDS_BY_SCHEMA[str(schema_version)]
    if set(payload) != expected_fields:
        _fail(
            "audit_input_fields_mismatch",
            ",".join(sorted(set(payload) ^ expected_fields)),
        )
    result: dict[str, Any] = {
        "schema_version": schema_version,
        "a1": _strict_record_sequence(payload["a1"], "a1"),
        "a2": _strict_record_sequence(payload["a2"], "a2"),
        "a3": _strict_record_sequence(payload["a3"], "a3"),
    }
    if schema_version == LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2:
        result["a3_pairing_dispositions"] = _strict_record_sequence(
            payload["a3_pairing_dispositions"],
            "a3_pairing_dispositions",
        )
    _assert_finite(result)
    claimed = _sha256_text(payload["content_sha256"], "content_sha256")
    actual = _canonical_sha256(result)
    if claimed != actual:
        _fail("audit_input_content_sha256_mismatch")
    result["content_sha256"] = claimed
    return result


def load_learning_adoption_audit_input(path: str | Path) -> dict[str, Any]:
    """Load one request without adjacent-file discovery."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("audit_input_file_invalid", type(exc).__name__)
    if not isinstance(value, Mapping):
        _fail("audit_input_type_invalid")
    return validate_learning_adoption_audit_input(value)


def validate_learning_adoption_audit_output(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly reload one current-schema D6 audit output."""

    payload = _strict_json_mapping(value, "audit_output")
    if set(payload) != _AUDIT_OUTPUT_FIELDS:
        _fail(
            "audit_output_fields_mismatch",
            ",".join(sorted(set(payload) ^ _AUDIT_OUTPUT_FIELDS)),
        )
    if payload["schema_version"] != LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION:
        _fail("audit_output_schema_unsupported")
    if (
        payload["consumer_schema_version"]
        != LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION
    ):
        _fail("audit_output_consumer_schema_unsupported")
    if payload["input_schema_version"] not in _INPUT_FIELDS_BY_SCHEMA:
        _fail("audit_output_input_schema_unsupported")
    _sha256_text(
        payload["input_content_sha256"],
        "audit_output.input_content_sha256",
    )
    if payload["scope"] != "read-only-evaluation-no-runtime-authority":
        _fail("audit_output_scope_invalid")
    if payload["availability"] not in {"available", "unavailable"}:
        _fail("audit_output_availability_invalid")

    variants = _strict_mapping(payload["variants"], "audit_output.variants")
    if set(variants) != set(_VARIANTS):
        _fail("audit_output_variants_mismatch")
    for name in _VARIANTS:
        row = _strict_mapping(
            variants[name],
            f"audit_output.variants.{name}",
        )
        if row.get("variant") != name:
            _fail("audit_output_variant_identity_mismatch", name)
    a3 = _strict_mapping(
        variants["A3"],
        "audit_output.variants.A3",
    )
    inventory = _strict_mapping(
        a3.get("pairing_disposition_inventory"),
        "audit_output.variants.A3.pairing_disposition_inventory",
    )
    _validate_a3_pairing_inventory_output(inventory)
    observation_inventory = _strict_mapping(
        a3.get("observation_outcome_inventory"),
        "audit_output.variants.A3.observation_outcome_inventory",
    )
    _validate_a3_observation_outcome_inventory(observation_inventory)

    _strict_mapping(payload["aggregate"], "audit_output.aggregate")
    blockers = _strict_text_tuple(
        payload["blocker_codes"],
        "audit_output.blocker_codes",
    )
    if list(blockers) != payload["blocker_codes"]:
        _fail("audit_output_blocker_order_invalid")
    permissions = _strict_mapping(
        payload["permissions"],
        "audit_output.permissions",
    )
    if set(permissions) != set(_AUTHORITY_FIELDS):
        _fail("audit_output_permissions_fields_mismatch")
    if any(value is not False for value in permissions.values()):
        _fail("audit_output_authority_escalation_attempt")

    claimed = _sha256_text(
        payload["content_sha256"],
        "audit_output.content_sha256",
    )
    body = dict(payload)
    body.pop("content_sha256")
    if _canonical_sha256(body) != claimed:
        _fail("audit_output_content_sha256_mismatch")
    _assert_finite(payload)
    return payload


def load_learning_adoption_audit_output(path: str | Path) -> dict[str, Any]:
    """Load one current-schema D6 audit output without file discovery."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("audit_output_file_invalid", type(exc).__name__)
    if not isinstance(value, Mapping):
        _fail("audit_output_type_invalid")
    return validate_learning_adoption_audit_output(value)


def load_learning_adoption_episode_evidence(
    path: str | Path,
) -> dict[str, Any]:
    """Load one explicit runtime evidence envelope without directory discovery."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(
            "episode_evidence_file_invalid",
            f"{source}:{type(exc).__name__}",
        )
    payload = _strict_mapping(value, "episode_evidence")
    if set(payload) != _EPISODE_RECORD_FIELDS:
        _fail(
            "episode_evidence_fields_mismatch",
            ",".join(sorted(set(payload) ^ _EPISODE_RECORD_FIELDS)),
        )
    if (
        payload["schema_version"]
        != LEARNING_ADOPTION_EPISODE_RECORDS_SCHEMA_VERSION
    ):
        _fail("episode_evidence_schema_unsupported")
    episode_id = _required_text_alias(
        payload,
        ("episode_id",),
        "episode_evidence.episode_id",
    )
    records = _strict_mapping(payload["records"], "episode_evidence.records")
    if set(records) != {"a1", "a2", "a3"}:
        _fail("episode_evidence_record_variants_mismatch")
    normalized = {
        "schema_version": payload["schema_version"],
        "episode_id": episode_id,
        "records": {
            name: _strict_record_sequence(
                records[name],
                f"episode_evidence.records.{name}",
            )
            for name in ("a1", "a2", "a3")
        },
    }
    claimed = _sha256_text(
        payload["content_sha256"],
        "episode_evidence.content_sha256",
    )
    if claimed != _canonical_sha256(normalized):
        _fail("episode_evidence_content_sha256_mismatch", episode_id)
    normalized["content_sha256"] = claimed
    return normalized


def build_learning_adoption_audit_input_from_episode_files(
    paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Combine explicitly named episode envelopes after pair assembly.

    D6 does not infer or manufacture A2/A3 pairs. Callers must first use the
    public D4/D5 assemblers and persist each resulting wrapper exactly once.
    Legacy single-arm records remain accepted and stop at their proved stage.
    """

    if isinstance(paths, (str, bytes, bytearray)) or not isinstance(
        paths,
        Sequence,
    ):
        _fail("episode_evidence_path_sequence_invalid")
    envelopes = [
        load_learning_adoption_episode_evidence(path) for path in paths
    ]
    episode_ids = [item["episode_id"] for item in envelopes]
    if len(episode_ids) != len(set(episode_ids)):
        _fail("episode_evidence_duplicate_episode_id")
    content_ids = [item["content_sha256"] for item in envelopes]
    if len(content_ids) != len(set(content_ids)):
        _fail("episode_evidence_duplicate_content")
    _validate_episode_pair_sources(envelopes)
    records = {
        name: [
            record
            for envelope in envelopes
            for record in envelope["records"][name]
        ]
        for name in ("a1", "a2", "a3")
    }
    return build_learning_adoption_audit_input(**records)


def _validate_episode_pair_sources(
    envelopes: Sequence[Mapping[str, Any]],
) -> None:
    """Check that persisted pair references resolve to explicit episode files."""

    episode_ids = {str(item["episode_id"]) for item in envelopes}
    safe_source_episodes: dict[str, str] = {}
    for envelope in envelopes:
        episode_id = str(envelope["episode_id"])
        for record in envelope["records"]["a2"]:
            if record.get("schema") != _A2_SAFE_ADOPTION_SCHEMA:
                continue
            digest = _sha256_text(
                record.get("content_sha256"),
                "episode_evidence.a2.safe_adoption.content_sha256",
            )
            previous = safe_source_episodes.setdefault(digest, episode_id)
            if previous != episode_id:
                _fail("episode_a2_safe_adoption_source_duplicate", digest)

    a2_event_log_episode_owners: dict[str, str] = {}
    a2_episode_event_logs: dict[str, str] = {}
    a3_event_log_episode_owners: dict[str, str] = {}
    a3_episode_event_logs: dict[str, str] = {}
    for envelope in envelopes:
        for record in envelope["records"]["a2"]:
            schema = record.get("schema")
            pair_records: Sequence[Mapping[str, Any]]
            if schema == _A2_PAIR_SCHEMA:
                pair_records = (record,)
            elif schema == _A2_PAIR_BATCH_SCHEMA:
                pair_records = _strict_record_sequence(
                    record.get("records"),
                    "episode_evidence.a2.pair_batch.records",
                )
            else:
                continue
            for pair in pair_records:
                source_sha = _sha256_text(
                    pair.get("safe_adoption_evidence_sha256"),
                    "episode_evidence.a2.safe_adoption_evidence_sha256",
                )
                source_episode = safe_source_episodes.get(source_sha)
                if source_episode is None:
                    _fail(
                        "episode_a2_safe_adoption_source_missing",
                        source_sha,
                    )
                candidate = pair.get("candidate_window")
                r0_window = pair.get("same_key_r0_window")
                if candidate is not None:
                    candidate_mapping = _strict_mapping(
                        candidate,
                        "episode_evidence.a2.candidate_window",
                    )
                    candidate_episode = _required_text_alias(
                        candidate_mapping,
                        ("execution_arm_id",),
                        "episode_evidence.a2.candidate_episode",
                    )
                    if candidate_episode != source_episode:
                        _fail(
                            "episode_a2_candidate_source_episode_mismatch"
                        )
                    _validate_persisted_event_log_reference(
                        candidate_mapping,
                        candidate_episode,
                        episode_ids=episode_ids,
                        event_log_episode_owners=(
                            a2_event_log_episode_owners
                        ),
                        episode_event_logs=a2_episode_event_logs,
                        variant="a2",
                    )
                if r0_window is not None:
                    r0_mapping = _strict_mapping(
                        r0_window,
                        "episode_evidence.a2.r0_window",
                    )
                    r0_episode = _required_text_alias(
                        r0_mapping,
                        ("execution_arm_id",),
                        "episode_evidence.a2.r0_episode",
                    )
                    _validate_persisted_event_log_reference(
                        r0_mapping,
                        r0_episode,
                        episode_ids=episode_ids,
                        event_log_episode_owners=(
                            a2_event_log_episode_owners
                        ),
                        episode_event_logs=a2_episode_event_logs,
                        variant="a2",
                    )

        for record in envelope["records"]["a3"]:
            if record.get("schema_version") != _A3_PAIR_SCHEMA:
                continue
            trace = _strict_mapping(
                record.get("adoption_trace"),
                "episode_evidence.a3.adoption_trace",
            )
            _validate_persisted_a3_event_log_reference(
                trace,
                episode_ids=episode_ids,
                event_log_episode_owners=a3_event_log_episode_owners,
                episode_event_logs=a3_episode_event_logs,
            )
            for field in ("candidate_window", "same_key_r0_window"):
                window = record.get(field)
                if window is None:
                    continue
                _validate_persisted_a3_event_log_reference(
                    _strict_mapping(
                        window,
                        f"episode_evidence.a3.{field}",
                    ),
                    episode_ids=episode_ids,
                    event_log_episode_owners=a3_event_log_episode_owners,
                    episode_event_logs=a3_episode_event_logs,
                )


def _validate_persisted_event_log_reference(
    window: Mapping[str, Any],
    episode_id: str,
    *,
    episode_ids: set[str],
    event_log_episode_owners: dict[str, str],
    episode_event_logs: dict[str, str],
    variant: str,
) -> None:
    if episode_id not in episode_ids:
        _fail(f"episode_{variant}_source_episode_missing", episode_id)
    _required_text_alias(
        window,
        ("source_event_log_id",),
        f"episode_evidence.{variant}.source_event_log_id",
    )
    digest = _sha256_text(
        window.get("source_event_log_sha256"),
        f"episode_evidence.{variant}.source_event_log_sha256",
    )
    _bind_event_log_digest_to_episode(
        digest,
        episode_id,
        event_log_episode_owners,
        episode_event_logs,
        f"episode_{variant}_event_log_digest_mismatch",
    )


def _validate_persisted_a3_event_log_reference(
    value: Mapping[str, Any],
    *,
    episode_ids: set[str],
    event_log_episode_owners: dict[str, str],
    episode_event_logs: dict[str, str],
) -> None:
    episode_id = _a3_episode_id(
        _alias_value(
            value,
            ("sample_key",),
            "episode_evidence.a3.sample_key",
        )
    )
    if episode_id not in episode_ids:
        _fail("episode_a3_source_episode_missing", episode_id)
    digest = _sha256_text(
        value.get("source_event_log_sha256"),
        "episode_evidence.a3.source_event_log_sha256",
    )
    _bind_event_log_digest_to_episode(
        digest,
        episode_id,
        event_log_episode_owners,
        episode_event_logs,
        "episode_a3_event_log_digest_mismatch",
    )


def _bind_event_log_digest_to_episode(
    digest: str,
    episode_id: str,
    digest_owners: dict[str, str],
    episode_digests: dict[str, str],
    error_code: str,
) -> None:
    owner = digest_owners.setdefault(digest, episode_id)
    episode_digest = episode_digests.setdefault(episode_id, digest)
    if owner != episode_id or episode_digest != digest:
        _fail(error_code, episode_id)


def audit_learning_adoption_evidence(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit A1/A2/A3 records without granting any runtime authority."""

    payload = validate_learning_adoption_audit_input(value)
    disposition_inventory_declared = (
        payload["schema_version"]
        == LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2
    )
    variants = {
        "A1": _audit_a1(payload["a1"]),
        "A2": _audit_a2(payload["a2"]),
        "A3": _audit_a3(
            payload["a3"],
            payload.get("a3_pairing_dispositions", ()),
            inventory_declared=disposition_inventory_declared,
        ),
    }
    blockers = _dedupe(
        code
        for variant in _VARIANTS
        for code in variants[variant]["blocker_codes"]
    )
    result: dict[str, Any] = {
        "schema_version": LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION,
        "consumer_schema_version": (
            LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION
        ),
        "input_schema_version": payload["schema_version"],
        "input_content_sha256": payload["content_sha256"],
        "scope": "read-only-evaluation-no-runtime-authority",
        "availability": (
            "available"
            if all(
                variants[name]["availability"] == "available"
                for name in _VARIANTS
            )
            else "unavailable"
        ),
        "variants": variants,
        "aggregate": _aggregate_metrics(variants),
        "blocker_codes": list(blockers),
        "permissions": {name: False for name in _AUTHORITY_FIELDS},
    }
    result["content_sha256"] = _canonical_sha256(result)
    return validate_learning_adoption_audit_output(result)


def _audit_a1(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        return _empty_variant("A1", "a1_evidence_missing")
    blockers: list[str] = []
    validated: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "preregistration",
            "candidate",
            "selection",
            "publication",
            "lifecycle",
        )
    }
    highest = "unavailable"
    try:
        module = _import_public_module(
            "d3_assignment_planner.a1_intervention_selection"
        )
    except _PublicModuleUnavailable:
        return _unavailable_variant(
            "A1",
            len(records),
            ("a1_public_validator_unavailable",),
        )

    for index, record in enumerate(records):
        if _contains_forbidden_key(record, _A1_FORBIDDEN_KEYS):
            blockers.append(f"a1_truth_or_outcome_leakage.record_{index}")
            continue
        if _synthetic_fixture_claimed(record):
            blockers.append(f"a1_synthetic_runtime_rejected.record_{index}")
            continue
        if _authority_escalation_requested(record):
            blockers.append(
                f"a1_authority_escalation_attempt.record_{index}"
            )
            continue
        schema = record.get("schema_version")
        if schema in _A1_BATCH_SCHEMAS:
            blockers.append("a1_batch_public_strict_loader_unavailable")
            continue
        contract = _A1_VALIDATORS.get(schema)
        if contract is None:
            blockers.append(f"a1_schema_unsupported.record_{index}")
            continue
        kind, validator_name = contract
        validator = getattr(module, validator_name, None)
        if not callable(validator):
            blockers.append(f"a1_public_validator_unavailable.{kind}")
            continue
        try:
            parsed = validator(record)
            normalized = _strict_json_mapping(parsed.to_dict(), kind)
        except (TypeError, ValueError) as exc:
            blockers.append(
                f"a1_contract_validation_failed.{_exception_code(exc)}"
            )
            continue
        if normalized != record:
            blockers.append(f"a1_contract_roundtrip_mismatch.{kind}")
            continue
        validated[kind].append(normalized)
        if kind == "preregistration":
            highest = _max_stage(highest, "preregistered", _A1_STAGE_RANK)
        elif kind == "candidate":
            highest = _max_stage(
                highest, "candidate_validated", _A1_STAGE_RANK
            )
        elif kind == "selection" and normalized["selected"]:
            highest = _max_stage(
                highest, "candidate_selected", _A1_STAGE_RANK
            )
        elif kind == "publication":
            highest = _max_stage(
                highest, "plan_published", _A1_STAGE_RANK
            )
        elif kind == "lifecycle":
            highest = _max_stage(
                highest,
                _a1_lifecycle_stage(normalized),
                _A1_STAGE_RANK,
            )

    lifecycle_records = validated["lifecycle"]
    comparison_keys = [_a1_comparison_key(item) for item in lifecycle_records]
    if len(comparison_keys) != len(set(comparison_keys)):
        blockers.append("a1_duplicate_comparison_key")
    candidate_keys = [
        item["content_sha256"] for item in validated["candidate"]
    ]
    if len(candidate_keys) != len(set(candidate_keys)):
        blockers.append("a1_duplicate_candidate_evidence")
    selection_keys = [
        item["content_sha256"] for item in validated["selection"]
    ]
    if len(selection_keys) != len(set(selection_keys)):
        blockers.append("a1_duplicate_selection_decision")
    blockers.extend(_audit_a1_linkage(validated))
    blockers.extend(_audit_a1_selection_linkage(validated))

    candidate_selected = any(
        item["selected_for_paired_evaluation"]
        for item in validated["candidate"]
    )
    decision_selected = any(
        item["selected"] for item in validated["selection"]
    )
    runtime_path_started = bool(
        decision_selected or validated["publication"] or lifecycle_records
    )
    explicit_rejection = bool(
        validated["candidate"] or validated["selection"]
    ) and not candidate_selected and not decision_selected

    if candidate_selected and not validated["selection"]:
        blockers.append("a1_selection_decision_missing")
    if runtime_path_started and not lifecycle_records:
        blockers.append("a1_lifecycle_evidence_missing")
    if lifecycle_records:
        for item in lifecycle_records:
            if not item["runtime_ack"]:
                blockers.append("a1_runtime_ack_missing")
            else:
                blockers.append("a1_runtime_provenance_not_serialized")
            if item["physical_window_available"]:
                blockers.append("a1_physical_window_payload_not_serialized")
            else:
                blockers.append("a1_physical_window_missing")
            if item["r0_pair_available"]:
                blockers.append("a1_same_key_r0_identity_not_serialized")
            else:
                blockers.append("a1_same_key_r0_missing")

    blockers = list(_dedupe(blockers))
    if explicit_rejection and not blockers:
        absence = ("a1_actual_adoption_absent",)
        return _variant_result(
            variant="A1",
            record_count=len(records),
            validated_record_count=sum(
                len(items) for items in validated.values()
            ),
            availability="unavailable",
            highest_stage=highest,
            blocker_codes=absence,
            actual=_metric_available(0),
            physical=_metric_unavailable(absence),
            r0=_metric_unavailable(absence),
            benefit=_metric_unavailable(absence),
        )

    unavailable_reasons = tuple(blockers) or (
        "a1_adoption_decision_evidence_missing",
    )
    return _variant_result(
        variant="A1",
        record_count=len(records),
        validated_record_count=sum(len(items) for items in validated.values()),
        availability="unavailable",
        highest_stage=highest,
        blocker_codes=unavailable_reasons,
        actual=_metric_unavailable(unavailable_reasons),
        physical=_metric_unavailable(unavailable_reasons),
        r0=_metric_unavailable(unavailable_reasons),
        benefit=_metric_unavailable(unavailable_reasons),
    )


def _audit_a2(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        return _empty_variant("A2", "a2_evidence_missing")
    try:
        safe_module = _import_public_module(
            "d4_distributed_fallback.region_resource_safe_adoption"
        )
    except _PublicModuleUnavailable:
        return _unavailable_variant(
            "A2",
            len(records),
            ("a2_public_contract_unavailable",),
        )

    try:
        pair_module = _import_public_module(
            "d4_distributed_fallback.region_resource_a2_benefit_audit"
        )
    except _PublicModuleUnavailable:
        pair_module = None

    blockers: list[str] = []
    safe_sources: dict[str, tuple[Any, Mapping[str, Any]]] = {}
    safe_source_ids: set[str] = set()
    pair_records: list[tuple[int, Mapping[str, Any]]] = []
    pair_batches: list[tuple[int, Mapping[str, Any]]] = []
    validated_record_count = 0
    highest = "unavailable"
    for index, record in enumerate(records):
        if _contains_forbidden_key(record, _A2_FORBIDDEN_KEYS):
            blockers.append(f"a2_truth_or_outcome_leakage.record_{index}")
            continue
        if _synthetic_fixture_claimed(record):
            blockers.append(f"a2_synthetic_runtime_rejected.record_{index}")
            continue
        if _authority_escalation_requested(record):
            blockers.append(
                f"a2_authority_escalation_attempt.record_{index}"
            )
            continue
        schema = record.get("schema")
        legacy_schema = getattr(
            safe_module,
            "REGION_RESOURCE_SAFE_ADOPTION_EVIDENCE_SCHEMA",
            None,
        )
        if schema == legacy_schema:
            try:
                evidence = _load_a2_safe_adoption_record(
                    record,
                    safe_module,
                )
                _validate_a2_cross_bindings(evidence)
            except (TypeError, ValueError) as exc:
                blockers.append(
                    f"a2_contract_validation_failed.{_exception_code(exc)}"
                )
                continue
            digest = str(evidence.content_sha256)
            evidence_id = str(evidence.evidence_id)
            if digest in safe_sources:
                blockers.append("a2_duplicate_safe_adoption_content")
                blockers.append("a2_duplicate_comparison_key")
                blockers.append("a2_duplicate_evidence_id")
                continue
            if evidence_id in safe_source_ids:
                blockers.append("a2_duplicate_evidence_id")
                continue
            safe_sources[digest] = (evidence, record)
            safe_source_ids.add(evidence_id)
            validated_record_count += 1
            continue
        if schema == _A2_PAIR_SCHEMA:
            pair_records.append((index, record))
            continue
        if schema == _A2_PAIR_BATCH_SCHEMA:
            pair_batches.append((index, record))
            continue
        blockers.append(f"a2_schema_unsupported.record_{index}")

    referenced_source_hashes: set[str] = set()
    validated: list[dict[str, Any]] = []
    if pair_records or pair_batches:
        if pair_module is None:
            blockers.append("a2_same_key_r0_public_validator_unavailable")
        else:
            validator = getattr(
                pair_module,
                "validate_region_resource_a2_benefit_audit_input",
                None,
            )
            if not callable(validator):
                blockers.append(
                    "a2_same_key_r0_public_validator_unavailable"
                )
            else:
                for index, record in pair_records:
                    source_sha = _a2_pair_source_sha256(
                        record,
                        f"a2[{index}]",
                        blockers,
                    )
                    if source_sha is None:
                        continue
                    source_entry = safe_sources.get(source_sha)
                    if source_entry is None:
                        blockers.append(
                            f"a2_safe_adoption_source_missing.record_{index}"
                        )
                        continue
                    try:
                        parsed = validator(
                            record,
                            safe_adoption_evidence=source_entry[1],
                        )
                        normalized = _strict_json_mapping(
                            parsed.to_dict(),
                            "a2_pair_evidence",
                        )
                    except (TypeError, ValueError) as exc:
                        blockers.append(
                            "a2_pair_public_validation_failed."
                            f"{_exception_code(exc)}"
                        )
                        continue
                    if normalized != record:
                        blockers.append(
                            "a2_pair_contract_roundtrip_mismatch"
                        )
                        continue
                    if source_sha in referenced_source_hashes:
                        blockers.append(
                            "a2_candidate_safe_adoption_multi_pair_reuse"
                        )
                    else:
                        referenced_source_hashes.add(source_sha)
                    try:
                        validated.append(
                            _a2_pair_view(
                                parsed,
                                source_entry[0],
                            )
                        )
                    except (TypeError, ValueError) as exc:
                        blockers.append(
                            "a2_pair_independent_recomputation_failed."
                            f"{_exception_code(exc)}"
                        )
                        continue
                    validated_record_count += 1

                batch_cls = getattr(
                    pair_module,
                    "RegionResourceA2BenefitAuditBatch",
                    None,
                )
                for index, record in pair_batches:
                    if batch_cls is None or not callable(
                        getattr(batch_cls, "from_mapping", None)
                    ):
                        blockers.append(
                            "a2_pair_batch_public_validator_unavailable"
                        )
                        continue
                    try:
                        parsed_batch = batch_cls.from_mapping(
                            record,
                            safe_adoption_evidence_by_sha256={
                                digest: source[1]
                                for digest, source in safe_sources.items()
                            },
                        )
                        normalized = _strict_json_mapping(
                            parsed_batch.to_dict(),
                            "a2_pair_batch",
                        )
                    except (TypeError, ValueError) as exc:
                        blockers.append(
                            "a2_pair_batch_public_validation_failed."
                            f"{_exception_code(exc)}"
                        )
                        continue
                    if normalized != record:
                        blockers.append(
                            "a2_pair_batch_contract_roundtrip_mismatch"
                        )
                        continue
                    batch_valid = True
                    batch_views: list[dict[str, Any]] = []
                    for parsed in parsed_batch.records:
                        source_sha = str(
                            parsed.safe_adoption_evidence_sha256
                        )
                        source_entry = safe_sources.get(source_sha)
                        if source_entry is None:
                            blockers.append(
                                "a2_safe_adoption_source_missing."
                                f"batch_record_{index}"
                            )
                            batch_valid = False
                            continue
                        if source_sha in referenced_source_hashes:
                            blockers.append(
                                "a2_candidate_safe_adoption_multi_pair_reuse"
                            )
                            batch_valid = False
                            continue
                        try:
                            batch_views.append(
                                _a2_pair_view(
                                    parsed,
                                    source_entry[0],
                                )
                            )
                        except (TypeError, ValueError) as exc:
                            blockers.append(
                                "a2_pair_independent_recomputation_failed."
                                f"{_exception_code(exc)}"
                            )
                            batch_valid = False
                    if not batch_valid:
                        continue
                    for parsed in parsed_batch.records:
                        referenced_source_hashes.add(
                            str(parsed.safe_adoption_evidence_sha256)
                        )
                    validated.extend(batch_views)
                    validated_record_count += 1

    for digest, (evidence, _) in safe_sources.items():
        if digest not in referenced_source_hashes:
            validated.append(_a2_legacy_view(evidence))

    for item in validated:
        highest = _max_stage(
            highest,
            item["highest_stage"],
            _A2_STAGE_RANK,
        )
    blockers.extend(_audit_a2_pair_uniqueness(validated))

    if not validated or blockers:
        reasons = tuple(_dedupe(blockers)) or (
            "a2_validated_evidence_missing",
        )
        return _variant_result(
            variant="A2",
            record_count=len(records),
            validated_record_count=validated_record_count,
            availability="unavailable",
            highest_stage=highest,
            blocker_codes=reasons,
            actual=_metric_unavailable(reasons),
            physical=_metric_unavailable(reasons),
            r0=_metric_unavailable(reasons),
            benefit=_metric_unavailable(reasons),
        )

    rejected = [item for item in validated if item["candidate_rejected"]]
    incomplete = [
        item
        for item in validated
        if not item["actual_adoption"] and item not in rejected
    ]
    if incomplete:
        reasons = tuple(
            _dedupe(
                (
                    "a2_adoption_evidence_incomplete",
                    *(
                        f"a2_stage_incomplete.{item['highest_stage']}"
                        for item in incomplete
                    ),
                    *(
                        f"a2.{reason}"
                        for item in incomplete
                        for reason in item["reason_codes"]
                    ),
                )
            )
        )
        return _variant_result(
            variant="A2",
            record_count=len(records),
            validated_record_count=validated_record_count,
            availability="unavailable",
            highest_stage=highest,
            blocker_codes=reasons,
            actual=_metric_unavailable(reasons),
            physical=_metric_unavailable(reasons),
            r0=_metric_unavailable(reasons),
            benefit=_metric_unavailable(reasons),
        )

    adopted = [item for item in validated if item["actual_adoption"]]
    actual = _metric_available(len(adopted))
    if not adopted:
        absence = ("a2_actual_adoption_absent",)
        return _variant_result(
            variant="A2",
            record_count=len(records),
            validated_record_count=validated_record_count,
            availability="unavailable",
            highest_stage=highest,
            blocker_codes=absence,
            actual=actual,
            physical=_metric_unavailable(absence),
            r0=_metric_unavailable(absence),
            benefit=_metric_unavailable(absence),
        )

    physical_complete = all(item["physical_window"] for item in adopted)
    r0_complete = physical_complete and all(
        item["same_key_r0_pair"] for item in adopted
    )
    benefit_complete = r0_complete and all(
        item["benefit_auditable"] for item in adopted
    )
    physical_reasons = ("a2_candidate_physical_window_incomplete",)
    r0_reasons = (
        (
            "a2_same_key_r0_contract_unavailable",
        )
        if any(
            item["record_kind"] == "legacy_safe_adoption"
            for item in adopted
        )
        else ("a2_same_key_r0_incomplete",)
    )
    benefit_reasons = ("a2_benefit_audit_input_incomplete",)
    physical_metric = (
        _metric_available(sum(item["physical_window"] for item in adopted))
        if physical_complete
        else _metric_unavailable(physical_reasons)
    )
    r0_metric = (
        _metric_available(
            sum(item["same_key_r0_pair"] for item in adopted)
        )
        if r0_complete
        else _metric_unavailable(r0_reasons)
    )
    benefit_metric = (
        _metric_available(
            sum(item["benefit_auditable"] for item in adopted)
        )
        if benefit_complete
        else _metric_unavailable(benefit_reasons)
    )
    if not physical_complete:
        blockers.extend(physical_reasons)
    if not r0_complete:
        blockers.extend(r0_reasons)
    if not benefit_complete:
        blockers.extend(benefit_reasons)
    for item in adopted:
        if not item["benefit_auditable"]:
            blockers.extend(
                f"a2.{code}" for code in item["reason_codes"]
            )
    availability = (
        "available"
        if physical_complete and r0_complete and benefit_complete
        else "unavailable"
    )
    return _variant_result(
        variant="A2",
        record_count=len(records),
        validated_record_count=validated_record_count,
        availability=availability,
        highest_stage=highest,
        blocker_codes=tuple(_dedupe(blockers)),
        actual=actual,
        physical=physical_metric,
        r0=r0_metric,
        benefit=benefit_metric,
    )


def _audit_a3_pairing_inventory(
    dispositions: Sequence[Mapping[str, Any]],
    validated_a3: Sequence[Any],
    module: Any,
    *,
    declared: bool,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    if not declared:
        return (
            _a3_pairing_inventory_unavailable(
                declared=False,
                record_count=0,
                validated_record_count=0,
                reasons=(
                    "a3_pairing_disposition_inventory_not_declared_v1",
                ),
            ),
            (),
        )

    validator = getattr(
        module,
        "validate_active_vision_a3_pairing_disposition",
        None,
    )
    reason_enum = getattr(
        module,
        "ActiveVisionA3PairingDispositionCode",
        None,
    )
    stage_reason_enum = getattr(
        module,
        "ActiveVisionA3CandidateStageReasonCode",
        None,
    )
    legacy_disposition_schema = getattr(
        module,
        "ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION",
        None,
    )
    current_disposition_schema = getattr(
        module,
        "ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION",
        None,
    )
    if not callable(validator) or reason_enum is None:
        reasons = ("a3_pairing_disposition_public_validator_unavailable",)
        return (
            _a3_pairing_inventory_unavailable(
                declared=True,
                record_count=len(dispositions),
                validated_record_count=0,
                reasons=reasons,
            ),
            reasons,
        )

    blockers: list[str] = []
    validated: list[Any] = []
    for index, record in enumerate(dispositions):
        try:
            parsed = validator(record)
            normalized = _strict_json_mapping(
                parsed.to_dict(),
                "a3_pairing_disposition",
            )
        except (TypeError, ValueError) as exc:
            blockers.append(
                "a3_pairing_disposition_contract_validation_failed."
                f"{_exception_code(exc)}"
            )
            continue
        if normalized != record:
            blockers.append(
                "a3_pairing_disposition_contract_roundtrip_mismatch"
            )
            continue
        validated.append(parsed)

    disposition_trace_owners: dict[str, int] = {}
    pairable_by_trace: dict[str, Any] = {}
    for index, disposition in enumerate(validated):
        trace_sha = disposition.adoption_trace_sha256
        if trace_sha is None:
            blockers.append(
                "a3_pairing_disposition_trace_reference_unavailable"
            )
            continue
        owner = disposition_trace_owners.setdefault(trace_sha, index)
        if owner != index:
            blockers.append(
                "a3_pairing_disposition_duplicate_adoption_trace"
            )
        if disposition.pairable:
            if trace_sha in pairable_by_trace:
                blockers.append(
                    "a3_pairing_disposition_duplicate_pairable_trace"
                )
            else:
                pairable_by_trace[trace_sha] = disposition

    top_level_by_trace: dict[str, Any] = {}
    for item in validated_a3:
        trace_sha = str(item.adoption_trace.trace_sha256)
        if trace_sha in top_level_by_trace:
            blockers.append(
                "a3_pairing_disposition_duplicate_top_level_trace"
            )
        else:
            top_level_by_trace[trace_sha] = item

    for trace_sha, disposition in pairable_by_trace.items():
        top_level = top_level_by_trace.get(trace_sha)
        if top_level is None:
            blockers.append(
                "a3_pairing_disposition_pairable_evidence_missing"
            )
            continue
        nested = disposition.paired_evidence
        if nested is None or nested.to_dict() != top_level.to_dict():
            blockers.append(
                "a3_pairing_disposition_pairable_evidence_mismatch"
            )

    if set(top_level_by_trace) - set(pairable_by_trace):
        blockers.append(
            "a3_pairing_disposition_top_level_evidence_unmatched"
        )

    candidate_count = len(validated)
    pairable_count = sum(item.pairable for item in validated)
    unpairable_count = candidate_count - pairable_count
    if candidate_count != pairable_count + unpairable_count:
        blockers.append(
            "a3_pairing_disposition_count_conservation_invalid"
        )

    reason_values = tuple(item.value for item in reason_enum)
    if len(reason_values) != len(set(reason_values)):
        blockers.append(
            "a3_pairing_disposition_reason_registry_duplicate"
        )
    reason_counts = {code: 0 for code in reason_values}
    stage_reason_values = (
        ()
        if stage_reason_enum is None
        else tuple(item.value for item in stage_reason_enum)
    )
    if len(stage_reason_values) != len(set(stage_reason_values)):
        blockers.append(
            "a3_pairing_disposition_stage_reason_registry_duplicate"
        )
    detail_reason_counts = {code: 0 for code in stage_reason_values}
    schema_counts: dict[str, int] = {}
    top_level_detail_counts = {
        code: {
            "record_count": 0,
            "records_with_detail_reason_count": 0,
            "records_without_detail_reason_count": 0,
            "detail_reason_assignment_count": 0,
            "detail_reason_code_counts": {
                detail: 0 for detail in stage_reason_values
            },
        }
        for code in reason_values
    }
    candidate_stage_evidence_count = 0
    detail_reason_record_count = 0
    detail_reason_assignment_count = 0
    physical_window_missing_detail_evidenced_count = 0
    for disposition in validated:
        code = disposition.reason_code.value
        if code not in reason_counts:
            blockers.append(
                "a3_pairing_disposition_reason_code_unsupported"
            )
            continue
        reason_counts[code] += 1
        row = top_level_detail_counts[code]
        row["record_count"] += 1

        disposition_schema = str(disposition.schema_version)
        schema_counts[disposition_schema] = (
            schema_counts.get(disposition_schema, 0) + 1
        )
        stage_reasons_raw = getattr(
            disposition,
            "candidate_stage_reason_codes",
            (),
        )
        stage_evidence = getattr(
            disposition,
            "candidate_stage_evidence",
            None,
        )
        if disposition_schema == legacy_disposition_schema:
            if stage_reasons_raw or stage_evidence is not None:
                blockers.append(
                    "a3_pairing_disposition_legacy_stage_detail_present"
                )
        elif disposition_schema == current_disposition_schema:
            if stage_reason_enum is None:
                blockers.append(
                    "a3_pairing_disposition_stage_reason_registry_unavailable"
                )
        else:
            blockers.append(
                "a3_pairing_disposition_schema_unsupported"
            )

        stage_codes: list[str] = []
        for raw_detail in stage_reasons_raw:
            detail = getattr(raw_detail, "value", None)
            if not isinstance(detail, str) or detail not in detail_reason_counts:
                blockers.append(
                    "a3_pairing_disposition_stage_reason_unsupported"
                )
                continue
            stage_codes.append(detail)
        if len(stage_codes) != len(set(stage_codes)):
            blockers.append(
                "a3_pairing_disposition_stage_reason_duplicate"
            )
        if stage_codes and stage_evidence is None:
            blockers.append(
                "a3_pairing_disposition_stage_reason_evidence_missing"
            )
        if disposition.pairable and stage_codes:
            blockers.append(
                "a3_pairing_disposition_pairable_stage_reason_conflict"
            )

        physical_status = getattr(
            getattr(stage_evidence, "physical_window_status", None),
            "value",
            None,
        )
        if (
            code == "candidate_physical_window_missing"
            and physical_status == "complete"
        ):
            blockers.append(
                "a3_pairing_disposition_stage_status_conflicts_with_top_level"
            )
        if disposition.pairable and physical_status in {
            "missing",
            "incomplete",
        }:
            blockers.append(
                "a3_pairing_disposition_stage_status_conflicts_with_pairable"
            )

        if stage_evidence is not None:
            candidate_stage_evidence_count += 1
        if stage_codes:
            detail_reason_record_count += 1
            row["records_with_detail_reason_count"] += 1
        else:
            row["records_without_detail_reason_count"] += 1
        row["detail_reason_assignment_count"] += len(stage_codes)
        detail_reason_assignment_count += len(stage_codes)
        for detail in stage_codes:
            detail_reason_counts[detail] += 1
            row["detail_reason_code_counts"][detail] += 1
        if (
            code == "candidate_physical_window_missing"
            and stage_evidence is not None
            and stage_codes
        ):
            physical_window_missing_detail_evidenced_count += 1
    if sum(reason_counts.values()) != candidate_count:
        blockers.append(
            "a3_pairing_disposition_reason_count_conservation_invalid"
        )
    if sum(schema_counts.values()) != candidate_count:
        blockers.append(
            "a3_pairing_disposition_schema_count_conservation_invalid"
        )
    if (
        candidate_stage_evidence_count
        + (candidate_count - candidate_stage_evidence_count)
        != candidate_count
    ):
        blockers.append(
            "a3_pairing_disposition_stage_evidence_count_conservation_invalid"
        )
    if (
        detail_reason_record_count
        + (candidate_count - detail_reason_record_count)
        != candidate_count
    ):
        blockers.append(
            "a3_pairing_disposition_stage_reason_record_conservation_invalid"
        )
    if sum(detail_reason_counts.values()) != detail_reason_assignment_count:
        blockers.append(
            "a3_pairing_disposition_stage_reason_assignment_conservation_invalid"
        )
    for code, row in top_level_detail_counts.items():
        if (
            row["records_with_detail_reason_count"]
            + row["records_without_detail_reason_count"]
            != row["record_count"]
            or row["record_count"] != reason_counts[code]
            or sum(row["detail_reason_code_counts"].values())
            != row["detail_reason_assignment_count"]
        ):
            blockers.append(
                "a3_pairing_disposition_reason_detail_conservation_invalid"
            )

    normalized_blockers = tuple(_dedupe(blockers))
    if normalized_blockers:
        return (
            _a3_pairing_inventory_unavailable(
                declared=True,
                record_count=len(dispositions),
                validated_record_count=len(validated),
                reasons=normalized_blockers,
            ),
            normalized_blockers,
        )

    coverage = (
        _audit_value_available(pairable_count / candidate_count)
        if candidate_count
        else _audit_value_unavailable(
            ("a3_pairing_candidate_denominator_zero",)
        )
    )
    stage_evidence_missing_count = (
        candidate_count - candidate_stage_evidence_count
    )
    detail_reasonless_record_count = (
        candidate_count - detail_reason_record_count
    )
    physical_window_missing_detail_scope_count = reason_counts.get(
        "candidate_physical_window_missing",
        0,
    )
    physical_window_missing_detail_unresolved_count = (
        physical_window_missing_detail_scope_count
        - physical_window_missing_detail_evidenced_count
    )
    return (
        {
            "schema_version": _A3_PAIRING_INVENTORY_SCHEMA_VERSION,
            "declared": True,
            "scope": "explicit-a3-pairing-disposition-inventory",
            "availability": "available",
            "complete_model_evidence_claimed": False,
            "record_count": len(dispositions),
            "validated_record_count": len(validated),
            "candidate_count": _metric_available(candidate_count),
            "pairable_count": _metric_available(pairable_count),
            "unpairable_count": _metric_available(unpairable_count),
            "pairing_coverage": coverage,
            "reason_code_counts": _audit_value_available(reason_counts),
            "top_level_reason_code_counts": _audit_value_available(
                reason_counts
            ),
            "disposition_schema_version_counts": _audit_value_available(
                dict(sorted(schema_counts.items()))
            ),
            "candidate_stage_evidence_count": _metric_available(
                candidate_stage_evidence_count
            ),
            "candidate_stage_evidence_missing_count": _metric_available(
                stage_evidence_missing_count
            ),
            "detail_reason_record_count": _metric_available(
                detail_reason_record_count
            ),
            "detail_reasonless_record_count": _metric_available(
                detail_reasonless_record_count
            ),
            "detail_reason_assignment_count": _metric_available(
                detail_reason_assignment_count
            ),
            "detail_reason_code_counts": _audit_value_available(
                detail_reason_counts
            ),
            "top_level_detail_reason_counts": _audit_value_available(
                top_level_detail_counts
            ),
            "physical_window_missing_detail_scope_count": _metric_available(
                physical_window_missing_detail_scope_count
            ),
            "physical_window_missing_detail_evidenced_count": (
                _metric_available(
                    physical_window_missing_detail_evidenced_count
                )
            ),
            "physical_window_missing_detail_unresolved_count": (
                _metric_available(
                    physical_window_missing_detail_unresolved_count
                )
            ),
            "physical_window_missing_detail_completeness": (
                _audit_value_available(
                    physical_window_missing_detail_unresolved_count == 0
                )
            ),
            "inventory_completeness": _audit_value_available(True),
            "paired_evidence_completeness": _audit_value_available(
                candidate_count > 0 and unpairable_count == 0
            ),
        },
        (),
    )


def _a3_pairing_inventory_unavailable(
    *,
    declared: bool,
    record_count: int,
    validated_record_count: int,
    reasons: Sequence[str],
) -> dict[str, Any]:
    normalized = tuple(_dedupe(reasons))
    unavailable = _audit_value_unavailable(normalized)
    return {
        "schema_version": _A3_PAIRING_INVENTORY_SCHEMA_VERSION,
        "declared": bool(declared),
        "scope": (
            "explicit-a3-pairing-disposition-inventory"
            if declared
            else "legacy-pairable-record-scope-only"
        ),
        "availability": "unavailable",
        "complete_model_evidence_claimed": False,
        "record_count": int(record_count),
        "validated_record_count": int(validated_record_count),
        "candidate_count": dict(unavailable),
        "pairable_count": dict(unavailable),
        "unpairable_count": dict(unavailable),
        "pairing_coverage": dict(unavailable),
        "reason_code_counts": dict(unavailable),
        "top_level_reason_code_counts": dict(unavailable),
        "disposition_schema_version_counts": dict(unavailable),
        "candidate_stage_evidence_count": dict(unavailable),
        "candidate_stage_evidence_missing_count": dict(unavailable),
        "detail_reason_record_count": dict(unavailable),
        "detail_reasonless_record_count": dict(unavailable),
        "detail_reason_assignment_count": dict(unavailable),
        "detail_reason_code_counts": dict(unavailable),
        "top_level_detail_reason_counts": dict(unavailable),
        "physical_window_missing_detail_scope_count": dict(unavailable),
        "physical_window_missing_detail_evidenced_count": dict(unavailable),
        "physical_window_missing_detail_unresolved_count": dict(unavailable),
        "physical_window_missing_detail_completeness": dict(unavailable),
        "inventory_completeness": dict(unavailable),
        "paired_evidence_completeness": dict(unavailable),
    }


def _validate_a3_pairing_inventory_output_impl(
    inventory: Mapping[str, Any],
) -> None:
    if set(inventory) != _A3_PAIRING_INVENTORY_FIELDS:
        _fail(
            "audit_output_a3_pairing_inventory_fields_mismatch",
            ",".join(
                sorted(set(inventory) ^ _A3_PAIRING_INVENTORY_FIELDS)
            ),
        )
    if inventory["schema_version"] != _A3_PAIRING_INVENTORY_SCHEMA_VERSION:
        _fail("audit_output_a3_pairing_inventory_schema_unsupported")
    if type(inventory["declared"]) is not bool:
        _fail("audit_output_a3_pairing_inventory_declared_invalid")
    if inventory["scope"] not in {
        "explicit-a3-pairing-disposition-inventory",
        "legacy-pairable-record-scope-only",
    }:
        _fail("audit_output_a3_pairing_inventory_scope_invalid")
    if inventory["availability"] not in {"available", "unavailable"}:
        _fail("audit_output_a3_pairing_inventory_availability_invalid")
    if inventory["complete_model_evidence_claimed"] is not False:
        _fail("audit_output_a3_complete_model_evidence_forbidden")
    for name in ("record_count", "validated_record_count"):
        _strict_nonnegative_int_value(
            inventory[name],
            f"audit_output.a3_pairing_inventory.{name}",
        )

    metric_names = (
        "candidate_count",
        "pairable_count",
        "unpairable_count",
        "pairing_coverage",
        "reason_code_counts",
        "top_level_reason_code_counts",
        "disposition_schema_version_counts",
        "candidate_stage_evidence_count",
        "candidate_stage_evidence_missing_count",
        "detail_reason_record_count",
        "detail_reasonless_record_count",
        "detail_reason_assignment_count",
        "detail_reason_code_counts",
        "top_level_detail_reason_counts",
        "physical_window_missing_detail_scope_count",
        "physical_window_missing_detail_evidenced_count",
        "physical_window_missing_detail_unresolved_count",
        "physical_window_missing_detail_completeness",
        "inventory_completeness",
        "paired_evidence_completeness",
    )
    audited = {
        name: _validate_output_audit_value(
            inventory[name],
            f"audit_output.a3_pairing_inventory.{name}",
        )
        for name in metric_names
    }
    if inventory["availability"] == "unavailable":
        if any(available for available, _ in audited.values()):
            _fail(
                "audit_output_a3_unavailable_inventory_metric_available"
            )
        return
    if not inventory["declared"]:
        _fail("audit_output_a3_available_inventory_not_declared")

    required_available = set(metric_names) - {"pairing_coverage"}
    if any(not audited[name][0] for name in required_available):
        _fail("audit_output_a3_available_inventory_metric_unavailable")

    candidate_count = _output_nonnegative_int_metric(
        audited["candidate_count"],
        "candidate_count",
    )
    pairable_count = _output_nonnegative_int_metric(
        audited["pairable_count"],
        "pairable_count",
    )
    unpairable_count = _output_nonnegative_int_metric(
        audited["unpairable_count"],
        "unpairable_count",
    )
    if candidate_count != pairable_count + unpairable_count:
        _fail("audit_output_a3_pairing_count_conservation_invalid")
    if (
        inventory["record_count"] != candidate_count
        or inventory["validated_record_count"] != candidate_count
    ):
        _fail("audit_output_a3_validated_candidate_count_mismatch")

    coverage_available, coverage_value = audited["pairing_coverage"]
    if candidate_count:
        if (
            not coverage_available
            or type(coverage_value) not in (int, float)
            or isinstance(coverage_value, bool)
            or not isfinite(float(coverage_value))
            or abs(
                float(coverage_value)
                - pairable_count / candidate_count
            )
            > 1.0e-12
        ):
            _fail("audit_output_a3_pairing_coverage_invalid")
    elif coverage_available:
        _fail("audit_output_a3_zero_denominator_coverage_available")

    reason_counts = _output_count_mapping(
        audited["reason_code_counts"],
        "reason_code_counts",
    )
    top_level_counts = _output_count_mapping(
        audited["top_level_reason_code_counts"],
        "top_level_reason_code_counts",
    )
    if reason_counts != top_level_counts:
        _fail("audit_output_a3_top_level_reason_alias_mismatch")
    if sum(top_level_counts.values()) != candidate_count:
        _fail(
            "audit_output_a3_top_level_reason_count_conservation_invalid"
        )

    schema_counts = _output_count_mapping(
        audited["disposition_schema_version_counts"],
        "disposition_schema_version_counts",
    )
    if sum(schema_counts.values()) != candidate_count:
        _fail("audit_output_a3_schema_count_conservation_invalid")

    stage_evidence_count = _output_nonnegative_int_metric(
        audited["candidate_stage_evidence_count"],
        "candidate_stage_evidence_count",
    )
    stage_evidence_missing_count = _output_nonnegative_int_metric(
        audited["candidate_stage_evidence_missing_count"],
        "candidate_stage_evidence_missing_count",
    )
    if (
        stage_evidence_count + stage_evidence_missing_count
        != candidate_count
    ):
        _fail(
            "audit_output_a3_stage_evidence_count_conservation_invalid"
        )

    detail_record_count = _output_nonnegative_int_metric(
        audited["detail_reason_record_count"],
        "detail_reason_record_count",
    )
    detail_reasonless_count = _output_nonnegative_int_metric(
        audited["detail_reasonless_record_count"],
        "detail_reasonless_record_count",
    )
    if detail_record_count + detail_reasonless_count != candidate_count:
        _fail(
            "audit_output_a3_detail_record_count_conservation_invalid"
        )
    detail_assignment_count = _output_nonnegative_int_metric(
        audited["detail_reason_assignment_count"],
        "detail_reason_assignment_count",
    )
    detail_counts = _output_count_mapping(
        audited["detail_reason_code_counts"],
        "detail_reason_code_counts",
    )
    if sum(detail_counts.values()) != detail_assignment_count:
        _fail(
            "audit_output_a3_pairing_detail_assignment_count_conservation_invalid"
        )

    try:
        module = _import_public_module(
            "d5_terminal_association.active_vision_a3_evidence_assembler"
        )
    except _PublicModuleUnavailable:
        _fail("audit_output_a3_public_reason_registry_unavailable")
    top_reason_enum = getattr(
        module,
        "ActiveVisionA3PairingDispositionCode",
        None,
    )
    detail_reason_enum = getattr(
        module,
        "ActiveVisionA3CandidateStageReasonCode",
        None,
    )
    if top_reason_enum is None or detail_reason_enum is None:
        _fail("audit_output_a3_public_reason_registry_unavailable")
    expected_top_reasons = {item.value for item in top_reason_enum}
    expected_detail_reasons = {item.value for item in detail_reason_enum}
    expected_disposition_schemas = {
        value
        for value in (
            getattr(
                module,
                "ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION",
                None,
            ),
            getattr(
                module,
                "ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION",
                None,
            ),
        )
        if isinstance(value, str)
    }
    if (
        not expected_disposition_schemas
        or not set(schema_counts).issubset(expected_disposition_schemas)
    ):
        _fail("audit_output_a3_disposition_schema_registry_mismatch")
    if set(top_level_counts) != expected_top_reasons:
        _fail("audit_output_a3_top_level_reason_registry_mismatch")
    if set(detail_counts) != expected_detail_reasons:
        _fail("audit_output_a3_detail_reason_registry_mismatch")

    hierarchy_available, hierarchy_value = audited[
        "top_level_detail_reason_counts"
    ]
    if not hierarchy_available:
        _fail("audit_output_a3_reason_detail_hierarchy_unavailable")
    hierarchy = _strict_mapping(
        hierarchy_value,
        "audit_output.a3_pairing_inventory.top_level_detail_reason_counts",
    )
    if set(hierarchy) != expected_top_reasons:
        _fail("audit_output_a3_reason_detail_hierarchy_keys_mismatch")
    aggregate_with_detail = 0
    aggregate_without_detail = 0
    aggregate_detail_assignments = 0
    aggregate_detail_counts = {
        code: 0 for code in expected_detail_reasons
    }
    for top_reason, raw_row in hierarchy.items():
        row = _strict_mapping(
            raw_row,
            "audit_output.a3_pairing_inventory."
            f"top_level_detail_reason_counts.{top_reason}",
        )
        if set(row) != _A3_TOP_LEVEL_DETAIL_ROW_FIELDS:
            _fail("audit_output_a3_reason_detail_row_fields_mismatch")
        row_record_count = _strict_nonnegative_int_value(
            row["record_count"],
            f"audit_output.a3_reason_detail.{top_reason}.record_count",
        )
        row_with_detail = _strict_nonnegative_int_value(
            row["records_with_detail_reason_count"],
            f"audit_output.a3_reason_detail.{top_reason}.with_detail",
        )
        row_without_detail = _strict_nonnegative_int_value(
            row["records_without_detail_reason_count"],
            f"audit_output.a3_reason_detail.{top_reason}.without_detail",
        )
        row_assignments = _strict_nonnegative_int_value(
            row["detail_reason_assignment_count"],
            f"audit_output.a3_reason_detail.{top_reason}.assignments",
        )
        row_detail_counts = _strict_count_mapping_value(
            row["detail_reason_code_counts"],
            f"audit_output.a3_reason_detail.{top_reason}.counts",
        )
        if set(row_detail_counts) != expected_detail_reasons:
            _fail("audit_output_a3_reason_detail_registry_mismatch")
        if (
            row_record_count != top_level_counts[top_reason]
            or row_with_detail + row_without_detail != row_record_count
            or sum(row_detail_counts.values()) != row_assignments
        ):
            _fail(
                "audit_output_a3_reason_detail_count_conservation_invalid"
            )
        aggregate_with_detail += row_with_detail
        aggregate_without_detail += row_without_detail
        aggregate_detail_assignments += row_assignments
        for detail, count in row_detail_counts.items():
            aggregate_detail_counts[detail] += count
    if (
        aggregate_with_detail != detail_record_count
        or aggregate_without_detail != detail_reasonless_count
        or aggregate_detail_assignments != detail_assignment_count
        or aggregate_detail_counts != detail_counts
    ):
        _fail("audit_output_a3_reason_detail_aggregate_mismatch")

    physical_scope_count = _output_nonnegative_int_metric(
        audited["physical_window_missing_detail_scope_count"],
        "physical_window_missing_detail_scope_count",
    )
    physical_evidenced_count = _output_nonnegative_int_metric(
        audited["physical_window_missing_detail_evidenced_count"],
        "physical_window_missing_detail_evidenced_count",
    )
    physical_unresolved_count = _output_nonnegative_int_metric(
        audited["physical_window_missing_detail_unresolved_count"],
        "physical_window_missing_detail_unresolved_count",
    )
    if physical_scope_count != top_level_counts.get(
        "candidate_physical_window_missing",
        0,
    ):
        _fail("audit_output_a3_physical_detail_scope_mismatch")
    if (
        physical_evidenced_count + physical_unresolved_count
        != physical_scope_count
    ):
        _fail("audit_output_a3_physical_detail_count_conservation_invalid")
    detail_complete = _output_bool_metric(
        audited["physical_window_missing_detail_completeness"],
        "physical_window_missing_detail_completeness",
    )
    if detail_complete != (physical_unresolved_count == 0):
        _fail("audit_output_a3_physical_detail_completeness_mismatch")
    if not _output_bool_metric(
        audited["inventory_completeness"],
        "inventory_completeness",
    ):
        _fail("audit_output_a3_inventory_completeness_invalid")
    paired_complete = _output_bool_metric(
        audited["paired_evidence_completeness"],
        "paired_evidence_completeness",
    )
    if paired_complete != (
        candidate_count > 0 and unpairable_count == 0
    ):
        _fail("audit_output_a3_paired_evidence_completeness_mismatch")


def _validate_a3_observation_outcome_inventory(
    inventory: Mapping[str, Any],
) -> None:
    if set(inventory) != _A3_OBSERVATION_OUTCOME_INVENTORY_FIELDS:
        _fail(
            "audit_output_a3_observation_inventory_fields_mismatch",
            ",".join(
                sorted(
                    set(inventory)
                    ^ _A3_OBSERVATION_OUTCOME_INVENTORY_FIELDS
                )
            ),
        )
    if (
        inventory["schema_version"]
        != _A3_OBSERVATION_OUTCOME_INVENTORY_SCHEMA_VERSION
    ):
        _fail("audit_output_a3_observation_inventory_schema_unsupported")
    if inventory["scope"] != "validated-candidate-window-outcomes":
        _fail("audit_output_a3_observation_inventory_scope_invalid")
    if inventory["availability"] not in {"available", "unavailable"}:
        _fail("audit_output_a3_observation_inventory_availability_invalid")
    reasons = _strict_text_tuple(
        inventory["reason_codes"],
        "audit_output.a3_observation_inventory.reason_codes",
    )
    if list(reasons) != inventory["reason_codes"]:
        _fail("audit_output_a3_observation_inventory_reason_order_invalid")

    candidate_count = _strict_nonnegative_int_value(
        inventory["candidate_window_count"],
        "audit_output.a3_observation_inventory.candidate_window_count",
    )
    frame_count = _strict_nonnegative_int_value(
        inventory["observation_frame_count"],
        "audit_output.a3_observation_inventory.observation_frame_count",
    )
    tracklet_frame_count = _strict_nonnegative_int_value(
        inventory["tracklets_observed_frame_count"],
        "audit_output.a3_observation_inventory.tracklets_observed_frame_count",
    )
    zero_detection_count = _strict_nonnegative_int_value(
        inventory["processed_zero_detection_frame_count"],
        "audit_output.a3_observation_inventory."
        "processed_zero_detection_frame_count",
    )
    if tracklet_frame_count + zero_detection_count != frame_count:
        _fail("audit_output_a3_observation_frame_count_conservation_invalid")

    invalid_zero_count = _strict_nonnegative_int_value(
        inventory["zero_detection_locked_or_ambiguous_count"],
        "audit_output.a3_observation_inventory."
        "zero_detection_locked_or_ambiguous_count",
    )
    if invalid_zero_count:
        _fail("audit_output_a3_zero_detection_positive_state_forbidden")

    association_available = inventory["association_outcome_available"]
    coverage_available = inventory["coverage_outcome_available"]
    if type(association_available) is not bool:
        _fail("audit_output_a3_association_availability_invalid")
    if type(coverage_available) is not bool:
        _fail("audit_output_a3_coverage_availability_invalid")
    association_names = (
        "association_evaluable_frame_count",
        "association_locked_count",
        "association_ambiguous_count",
        "association_hold_count",
        "association_reacquire_count",
    )
    association_values = tuple(inventory[name] for name in association_names)
    association_evaluable: int | None = None
    if association_available:
        if any(value is None for value in association_values):
            _fail("audit_output_a3_association_counts_incomplete")
        normalized_association = tuple(
            _strict_nonnegative_int_value(
                value,
                f"audit_output.a3_observation_inventory.{name}",
            )
            for name, value in zip(
                association_names,
                association_values,
                strict=True,
            )
        )
        evaluable, locked, ambiguous, hold, reacquire = (
            normalized_association
        )
        association_evaluable = evaluable
        if locked + ambiguous + hold + reacquire != evaluable:
            _fail("audit_output_a3_association_count_conservation_invalid")
        if locked + ambiguous + hold > tracklet_frame_count:
            _fail("audit_output_a3_zero_detection_positive_state_forbidden")
        if coverage_available and reacquire < zero_detection_count:
            _fail("audit_output_a3_zero_detection_reacquire_count_invalid")
        if evaluable > frame_count:
            _fail("audit_output_a3_association_frame_scope_invalid")
    elif any(value is not None for value in association_values):
        _fail("audit_output_a3_unavailable_association_counts_present")

    coverage_names = (
        "assigned_reference_count",
        "visible_assigned_reference_count",
    )
    coverage_values = tuple(inventory[name] for name in coverage_names)
    coverage_fraction = inventory["coverage_fraction"]
    if coverage_available:
        if any(value is None for value in coverage_values):
            _fail("audit_output_a3_coverage_counts_incomplete")
        assigned, visible = tuple(
            _strict_nonnegative_int_value(
                value,
                f"audit_output.a3_observation_inventory.{name}",
            )
            for name, value in zip(
                coverage_names,
                coverage_values,
                strict=True,
            )
        )
        if assigned != frame_count or visible > assigned or assigned < 1:
            _fail("audit_output_a3_coverage_count_conservation_invalid")
        if (
            type(coverage_fraction) not in (int, float)
            or isinstance(coverage_fraction, bool)
            or not isfinite(float(coverage_fraction))
            or abs(float(coverage_fraction) - visible / assigned) > 1.0e-12
        ):
            _fail("audit_output_a3_coverage_fraction_invalid")
    elif any(value is not None for value in (*coverage_values, coverage_fraction)):
        _fail("audit_output_a3_unavailable_coverage_values_present")

    expected_available = bool(
        candidate_count > 0
        and frame_count > 0
        and association_available
        and coverage_available
    )
    if (inventory["availability"] == "available") != expected_available:
        _fail("audit_output_a3_observation_inventory_state_mismatch")
    if expected_available and association_evaluable != frame_count:
        _fail("audit_output_a3_association_frame_scope_invalid")
    if expected_available and reasons:
        _fail("audit_output_a3_available_observation_inventory_has_reasons")
    if not expected_available and not reasons:
        _fail("audit_output_a3_unavailable_observation_inventory_no_reason")


def _validate_output_audit_value(
    value: Any,
    name: str,
) -> tuple[bool, Any]:
    payload = _strict_mapping(value, name)
    if set(payload) != {"availability", "value", "reason_codes"}:
        _fail("audit_output_metric_fields_mismatch", name)
    availability = payload["availability"]
    if availability not in {"available", "unavailable"}:
        _fail("audit_output_metric_availability_invalid", name)
    reasons = _strict_text_tuple(
        payload["reason_codes"],
        f"{name}.reason_codes",
    )
    if availability == "available":
        if reasons:
            _fail("audit_output_available_metric_has_reasons", name)
        return True, payload["value"]
    if payload["value"] is not None or not reasons:
        _fail("audit_output_unavailable_metric_invalid", name)
    return False, None


def _output_nonnegative_int_metric(
    audited: tuple[bool, Any],
    name: str,
) -> int:
    available, value = audited
    if not available:
        _fail("audit_output_required_metric_unavailable", name)
    return _strict_nonnegative_int_value(value, f"audit_output.{name}")


def _output_bool_metric(
    audited: tuple[bool, Any],
    name: str,
) -> bool:
    available, value = audited
    if not available or type(value) is not bool:
        _fail("audit_output_bool_metric_invalid", name)
    return value


def _output_count_mapping(
    audited: tuple[bool, Any],
    name: str,
) -> dict[str, int]:
    available, value = audited
    if not available:
        _fail("audit_output_required_metric_unavailable", name)
    return _strict_count_mapping_value(value, f"audit_output.{name}")


def _strict_count_mapping_value(
    value: Any,
    name: str,
) -> dict[str, int]:
    payload = _strict_mapping(value, name)
    result: dict[str, int] = {}
    for key, raw_count in payload.items():
        if not isinstance(key, str) or not key:
            _fail("audit_output_count_mapping_key_invalid", name)
        result[key] = _strict_nonnegative_int_value(
            raw_count,
            f"{name}.{key}",
        )
    return result


def _a3_observation_outcome_inventory_unavailable(
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": _A3_OBSERVATION_OUTCOME_INVENTORY_SCHEMA_VERSION,
        "scope": "validated-candidate-window-outcomes",
        "availability": "unavailable",
        "reason_codes": list(_dedupe(reasons)),
        "candidate_window_count": 0,
        "observation_frame_count": 0,
        "tracklets_observed_frame_count": 0,
        "processed_zero_detection_frame_count": 0,
        "association_outcome_available": False,
        "association_evaluable_frame_count": None,
        "association_locked_count": None,
        "association_ambiguous_count": None,
        "association_hold_count": None,
        "association_reacquire_count": None,
        "coverage_outcome_available": False,
        "assigned_reference_count": None,
        "visible_assigned_reference_count": None,
        "coverage_fraction": None,
        "zero_detection_locked_or_ambiguous_count": 0,
    }


def _audit_a3_observation_outcomes(
    validated: Sequence[Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    windows = tuple(
        item.candidate_window
        for item in validated
        if item.candidate_window is not None
    )
    if not windows:
        reasons = ("a3_candidate_observation_window_missing",)
        return _a3_observation_outcome_inventory_unavailable(reasons), reasons

    frames = tuple(
        frame
        for window in windows
        for frame in window.observation_frames
    )
    state_counts = {
        state: sum(
            frame.frame_observation_state == state for frame in frames
        )
        for state in _A3_FRAME_OBSERVATION_STATES
    }
    invalid_zero_count = sum(
        frame.frame_observation_state == "processed_zero_detections"
        and (
            frame.association_state in {"locked", "ambiguous", "hold"}
            or (
                frame.target_global_track_id is not None
                and frame.assigned_reference_visible is not False
            )
            or (
                frame.target_global_track_id is None
                and (
                    frame.association_state is not None
                    or frame.assigned_reference_visible is not None
                )
            )
        )
        for frame in frames
    )

    association_available = all(
        window.outcome.association_outcome_available
        for window in windows
    )
    coverage_available = all(
        window.outcome.coverage_outcome_available
        for window in windows
    )
    reasons: list[str] = []
    if not association_available:
        reasons.append("a3_candidate_association_outcome_unavailable")
    if not coverage_available:
        reasons.append("a3_candidate_coverage_outcome_unavailable")
    if invalid_zero_count:
        reasons.append("a3_zero_detection_positive_state_forbidden")

    association_values: dict[str, int | None]
    if association_available:
        association_values = {
            "association_evaluable_frame_count": sum(
                int(window.outcome.association_evaluable_frame_count)
                for window in windows
            ),
            "association_locked_count": sum(
                int(window.outcome.association_locked_count)
                for window in windows
            ),
            "association_ambiguous_count": sum(
                int(window.outcome.association_ambiguous_count)
                for window in windows
            ),
            "association_hold_count": sum(
                int(window.outcome.association_hold_count)
                for window in windows
            ),
            "association_reacquire_count": sum(
                int(window.outcome.association_reacquire_count)
                for window in windows
            ),
        }
    else:
        association_values = {
            "association_evaluable_frame_count": None,
            "association_locked_count": None,
            "association_ambiguous_count": None,
            "association_hold_count": None,
            "association_reacquire_count": None,
        }

    if coverage_available:
        assigned_reference_count: int | None = sum(
            int(window.outcome.assigned_reference_count)
            for window in windows
        )
        visible_assigned_reference_count: int | None = sum(
            int(window.outcome.visible_assigned_reference_count)
            for window in windows
        )
        coverage_fraction: float | None = (
            visible_assigned_reference_count / assigned_reference_count
        )
    else:
        assigned_reference_count = None
        visible_assigned_reference_count = None
        coverage_fraction = None

    available = bool(
        frames
        and association_available
        and coverage_available
        and invalid_zero_count == 0
    )
    if not frames:
        reasons.append("a3_candidate_observation_frame_missing")
    inventory = {
        "schema_version": _A3_OBSERVATION_OUTCOME_INVENTORY_SCHEMA_VERSION,
        "scope": "validated-candidate-window-outcomes",
        "availability": "available" if available else "unavailable",
        "reason_codes": [] if available else list(_dedupe(reasons)),
        "candidate_window_count": len(windows),
        "observation_frame_count": len(frames),
        "tracklets_observed_frame_count": state_counts[
            "tracklets_observed"
        ],
        "processed_zero_detection_frame_count": state_counts[
            "processed_zero_detections"
        ],
        "association_outcome_available": association_available,
        **association_values,
        "coverage_outcome_available": coverage_available,
        "assigned_reference_count": assigned_reference_count,
        "visible_assigned_reference_count": (
            visible_assigned_reference_count
        ),
        "coverage_fraction": coverage_fraction,
        "zero_detection_locked_or_ambiguous_count": invalid_zero_count,
    }
    blockers = (
        ("a3_zero_detection_positive_state_forbidden",)
        if invalid_zero_count
        else ()
    )
    return inventory, blockers


def _with_a3_pairing_inventory(
    result: Mapping[str, Any],
    inventory: Mapping[str, Any],
    observation_inventory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(result)
    enriched["pairing_disposition_inventory"] = dict(inventory)
    enriched["observation_outcome_inventory"] = dict(
        observation_inventory
        if observation_inventory is not None
        else _a3_observation_outcome_inventory_unavailable(
            ("a3_validated_observation_evidence_missing",)
        )
    )
    return enriched


def _audit_a3(
    records: Sequence[Mapping[str, Any]],
    dispositions: Sequence[Mapping[str, Any]],
    *,
    inventory_declared: bool,
) -> dict[str, Any]:
    legacy_inventory = _a3_pairing_inventory_unavailable(
        declared=False,
        record_count=0,
        validated_record_count=0,
        reasons=("a3_pairing_disposition_inventory_not_declared_v1",),
    )
    if not records and not inventory_declared:
        return _with_a3_pairing_inventory(
            _empty_variant("A3", "a3_evidence_missing"),
            legacy_inventory,
        )
    try:
        module = _import_public_module(
            "d5_terminal_association.active_vision_a3_evidence_assembler"
        )
    except _PublicModuleUnavailable:
        reasons = ("a3_public_validator_unavailable",)
        return _with_a3_pairing_inventory(
            _unavailable_variant("A3", len(records), reasons),
            _a3_pairing_inventory_unavailable(
                declared=inventory_declared,
                record_count=len(dispositions),
                validated_record_count=0,
                reasons=reasons,
            ),
        )
    validator = getattr(module, "validate_active_vision_a3_evidence", None)
    if not callable(validator):
        reasons = ("a3_public_validator_unavailable",)
        return _with_a3_pairing_inventory(
            _unavailable_variant("A3", len(records), reasons),
            _a3_pairing_inventory_unavailable(
                declared=inventory_declared,
                record_count=len(dispositions),
                validated_record_count=0,
                reasons=reasons,
            ),
        )

    blockers: list[str] = []
    validated: list[Any] = []
    highest = "unavailable"
    for index, record in enumerate(records):
        if _contains_forbidden_key(record, _A3_FORBIDDEN_KEYS):
            blockers.append(f"a3_truth_leakage.record_{index}")
            continue
        if _authority_escalation_requested(record):
            blockers.append(f"a3_authority_escalation_attempt.record_{index}")
            continue
        try:
            parsed = validator(record)
            normalized = _strict_json_mapping(
                parsed.to_dict(),
                "a3_evidence",
            )
        except (TypeError, ValueError) as exc:
            blockers.append(
                f"a3_contract_validation_failed.{_exception_code(exc)}"
            )
            continue
        if normalized != record:
            blockers.append("a3_contract_roundtrip_mismatch")
            continue
        validated.append(parsed)
        highest = _max_stage(
            highest,
            _a3_highest_stage(parsed),
            _A3_STAGE_RANK,
        )
        trace = parsed.adoption_trace
        if trace.synthetic_fixture:
            blockers.append("a3_synthetic_runtime_rejected")
        if trace.online_truth_use_count:
            blockers.append("a3_online_truth_use_rejected")
        if trace.global_track_id_rewrite_count:
            blockers.append("a3_global_track_id_rewrite_rejected")
        blockers.extend(f"a3.{code}" for code in parsed.blocker_codes)

    pairing_inventory, inventory_blockers = (
        _audit_a3_pairing_inventory(
            dispositions,
            validated,
            module,
            declared=inventory_declared,
        )
    )
    blockers.extend(inventory_blockers)
    observation_inventory, observation_blockers = (
        _audit_a3_observation_outcomes(validated)
    )
    blockers.extend(observation_blockers)

    keys = [item.adoption_trace.comparison_key for item in validated]
    if len(keys) != len(set(keys)):
        blockers.append("a3_duplicate_comparison_key")
    window_owners: dict[str, str] = {}
    sample_key_owners: dict[str, str] = {}
    trace_sample_key_owners: dict[str, str] = {}
    event_log_episode_owners: dict[str, str] = {}
    episode_event_logs: dict[str, str] = {}
    r0_window_owners: dict[str, str] = {}
    r0_sample_key_owners: dict[str, str] = {}
    for item in validated:
        key = item.adoption_trace.comparison_key
        trace = item.adoption_trace
        trace_identity = _a3_trace_comparison_identity(trace)
        trace_episode = _a3_episode_id(trace.sample_key)
        trace_owner = trace_sample_key_owners.setdefault(
            trace.sample_key,
            key,
        )
        if trace_owner != key:
            blockers.append("a3_cross_key_trace_reuse")
        trace_log_owner = event_log_episode_owners.setdefault(
            trace.source_event_log_sha256,
            trace_episode,
        )
        trace_episode_log = episode_event_logs.setdefault(
            trace_episode,
            trace.source_event_log_sha256,
        )
        if (
            trace_log_owner != trace_episode
            or trace_episode_log != trace.source_event_log_sha256
        ):
            blockers.append("a3_event_log_episode_binding_mismatch")
        candidate = item.candidate_window
        r0_window = item.same_key_r0_window
        if candidate is not None and (
            candidate.comparison_identity != trace_identity
            or candidate.sample_key != trace.sample_key
            or candidate.source_event_log_sha256
            != trace.source_event_log_sha256
        ):
            blockers.append("a3_candidate_trace_binding_mismatch")
        if (
            candidate is not None
            and r0_window is not None
            and candidate.comparison_identity != r0_window.comparison_identity
        ):
            blockers.append("a3_same_key_identity_mismatch")
        if candidate is not None and r0_window is not None:
            candidate_episode = _a3_episode_id(candidate.sample_key)
            r0_episode = _a3_episode_id(r0_window.sample_key)
            if candidate_episode == r0_episode:
                blockers.append("a3_candidate_r0_episode_reuse")
        for arm, window in (
            ("candidate", candidate),
            ("r0", r0_window),
        ):
            if window is None:
                continue
            digest = window.window_sha256
            owner = window_owners.setdefault(digest, key)
            if owner != key:
                blockers.append("a3_cross_key_window_reuse")
            sample_owner = sample_key_owners.setdefault(
                window.sample_key,
                key,
            )
            if sample_owner != key:
                blockers.append("a3_cross_key_window_reuse")
            log_digest = window.source_event_log_sha256
            episode_id = _a3_episode_id(window.sample_key)
            log_owner = event_log_episode_owners.setdefault(
                log_digest,
                episode_id,
            )
            if log_owner != episode_id:
                blockers.append("a3_event_log_episode_binding_mismatch")
            episode_log = episode_event_logs.setdefault(
                episode_id,
                log_digest,
            )
            if episode_log != log_digest:
                blockers.append("a3_event_log_episode_binding_mismatch")
            if arm == "r0":
                if digest in r0_window_owners:
                    blockers.append("a3_r0_multi_pair_reuse")
                else:
                    r0_window_owners[digest] = key
                if window.sample_key in r0_sample_key_owners:
                    blockers.append("a3_r0_multi_pair_reuse")
                else:
                    r0_sample_key_owners[window.sample_key] = key

    hard_prefixes = (
        "a3_truth_",
        "a3_authority_",
        "a3_contract_",
        "a3_public_",
        "a3_synthetic_",
        "a3_online_truth_",
        "a3_global_track_id_",
        "a3_duplicate_",
        "a3_cross_key_",
        "a3_event_log_",
        "a3_r0_multi_",
        "a3_same_key_",
        "a3_candidate_r0_",
        "a3_candidate_trace_",
        "a3_pairing_disposition_",
        "a3_zero_detection_",
    )
    hard_blockers = tuple(
        code for code in _dedupe(blockers) if code.startswith(hard_prefixes)
    )
    if not validated or hard_blockers:
        reasons = hard_blockers or ("a3_validated_evidence_missing",)
        return _with_a3_pairing_inventory(
            _variant_result(
                variant="A3",
                record_count=len(records),
                validated_record_count=len(validated),
                availability="unavailable",
                highest_stage=highest,
                blocker_codes=tuple(_dedupe(blockers)) or reasons,
                actual=_metric_unavailable(reasons),
                physical=_metric_unavailable(reasons),
                r0=_metric_unavailable(reasons),
                benefit=_metric_unavailable(reasons),
            ),
            pairing_inventory,
            observation_inventory,
        )

    adopted = [item for item in validated if item.model_action_adopted]
    actual_metric = _metric_available(len(adopted))
    if not adopted:
        absence = ("a3_actual_adoption_absent",)
        return _with_a3_pairing_inventory(
            _variant_result(
                variant="A3",
                record_count=len(records),
                validated_record_count=len(validated),
                availability="unavailable",
                highest_stage=highest,
                blocker_codes=tuple(_dedupe((*blockers, *absence))),
                actual=actual_metric,
                physical=_metric_unavailable(absence),
                r0=_metric_unavailable(absence),
                benefit=_metric_unavailable(absence),
            ),
            pairing_inventory,
            observation_inventory,
        )

    inventory_unpairable = (
        inventory_declared
        and pairing_inventory["availability"] == "available"
        and pairing_inventory["unpairable_count"]["value"] > 0
    )
    if inventory_unpairable:
        reasons = ("a3_pairing_inventory_contains_unpairable",)
        return _with_a3_pairing_inventory(
            _variant_result(
                variant="A3",
                record_count=len(records),
                validated_record_count=len(validated),
                availability="unavailable",
                highest_stage=highest,
                blocker_codes=tuple(_dedupe((*blockers, *reasons))),
                actual=_metric_unavailable(reasons),
                physical=_metric_unavailable(reasons),
                r0=_metric_unavailable(reasons),
                benefit=_metric_unavailable(reasons),
            ),
            pairing_inventory,
            observation_inventory,
        )

    physical_complete = all(
        item.candidate_window is not None
        and item.candidate_window.runtime_physical_chain_complete
        for item in adopted
    )
    r0_complete = physical_complete and all(
        item.same_key_r0_window is not None
        and item.same_key_r0_window.runtime_physical_chain_complete
        for item in adopted
    )
    benefit_complete = r0_complete and all(
        item.d6_benefit_audit_eligible for item in adopted
    )
    physical_metric = (
        _metric_available(len(adopted))
        if physical_complete
        else _metric_unavailable(("a3_candidate_physical_window_incomplete",))
    )
    r0_metric = (
        _metric_available(len(adopted))
        if r0_complete
        else _metric_unavailable(("a3_same_key_r0_incomplete",))
    )
    benefit_metric = (
        _metric_available(len(adopted))
        if benefit_complete
        else _metric_unavailable(("a3_auditable_benefit_incomplete",))
    )
    availability = (
        "available"
        if physical_complete and r0_complete and benefit_complete
        else "unavailable"
    )
    if not physical_complete:
        blockers.append("a3_candidate_physical_window_incomplete")
    if not r0_complete:
        blockers.append("a3_same_key_r0_incomplete")
    if not benefit_complete:
        blockers.append("a3_auditable_benefit_incomplete")
    return _with_a3_pairing_inventory(
        _variant_result(
            variant="A3",
            record_count=len(records),
            validated_record_count=len(validated),
            availability=availability,
            highest_stage=highest,
            blocker_codes=tuple(_dedupe(blockers)),
            actual=actual_metric,
            physical=physical_metric,
            r0=r0_metric,
            benefit=benefit_metric,
        ),
        pairing_inventory,
        observation_inventory,
    )


def _audit_a1_linkage(
    validated: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[str, ...]:
    candidates = {
        item["content_sha256"]: item for item in validated["candidate"]
    }
    selections = {
        item["content_sha256"]: item for item in validated["selection"]
    }
    publications = {
        item["content_sha256"]: item for item in validated["publication"]
    }
    blockers: list[str] = []
    for lifecycle in validated["lifecycle"]:
        candidate = candidates.get(lifecycle["candidate_evidence_sha256"])
        selection = selections.get(lifecycle["selection_decision_sha256"])
        publication_sha = lifecycle["publication_evidence_sha256"]
        publication = (
            None
            if publication_sha is None
            else publications.get(publication_sha)
        )
        if candidate is None:
            blockers.append("a1_linked_candidate_missing")
        if selection is None:
            blockers.append("a1_linked_selection_missing")
        if lifecycle["plan_published"] and publication is None:
            blockers.append("a1_linked_publication_missing")
        if candidate is not None and selection is not None:
            if (
                selection["selected_candidate_content_sha256"]
                != candidate["content_sha256"]
            ):
                blockers.append("a1_candidate_selection_cross_key_mismatch")
            if (
                selection["preregistration"]["content_sha256"]
                != candidate["preregistration"]["content_sha256"]
            ):
                blockers.append("a1_preregistration_cross_key_mismatch")
            if (
                selection["selected_treatment_plan_payload_sha256"]
                != lifecycle["assignment_plan_payload_sha256"]
                or candidate["eligibility"]["treatment_plan_payload_sha256"]
                != lifecycle["assignment_plan_payload_sha256"]
            ):
                blockers.append("a1_plan_payload_cross_key_mismatch")
        if (
            publication is not None
            and publication["assignment_plan_payload_sha256"]
            != lifecycle["assignment_plan_payload_sha256"]
        ):
            blockers.append("a1_publication_cross_key_mismatch")
    return _dedupe(blockers)


def _audit_a1_selection_linkage(
    validated: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[str, ...]:
    candidates = {
        item["content_sha256"]: item for item in validated["candidate"]
    }
    blockers: list[str] = []
    for selection in validated["selection"]:
        candidate_digests = tuple(selection["candidate_content_sha256s"])
        linked = [
            candidates[digest]
            for digest in candidate_digests
            if digest in candidates
        ]
        if len(linked) != len(candidate_digests):
            blockers.append("a1_selection_candidate_inventory_missing")
            continue
        if any(
            item["seed"] != selection["seed"]
            or item["preregistration"]["content_sha256"]
            != selection["preregistration"]["content_sha256"]
            for item in linked
        ):
            blockers.append("a1_selection_candidate_scope_mismatch")
        expected_counts = {
            "candidate_count": len(linked),
            "policy_evaluated_count": sum(
                bool(item["policy_evaluated"]) for item in linked
            ),
            "cost_correction_accepted_count": sum(
                bool(item["cost_correction_accepted"]) for item in linked
            ),
            "assignment_changed_count": sum(
                bool(item["assignment_changed"]) for item in linked
            ),
            "near_competitive_count": sum(
                bool(item["near_competitive"]) for item in linked
            ),
        }
        if any(
            selection[name] != expected
            for name, expected in expected_counts.items()
        ):
            blockers.append("a1_selection_stage_count_mismatch")
        if selection["selected"]:
            selected = candidates.get(
                selection["selected_candidate_content_sha256"]
            )
            if selected is None:
                blockers.append("a1_selected_candidate_missing")
            elif (
                not selected["selected_for_paired_evaluation"]
                or selected["eligibility"]["treatment_plan_payload_sha256"]
                != selection["selected_treatment_plan_payload_sha256"]
            ):
                blockers.append("a1_selected_candidate_cross_binding_invalid")
    return _dedupe(blockers)


def _a2_legacy_view(evidence: Any) -> dict[str, Any]:
    window = evidence.physical_window
    return {
        "record_kind": "legacy_safe_adoption",
        "evidence_id": str(evidence.evidence_id),
        "comparison_key": _a2_comparison_key(evidence),
        "highest_stage": evidence.stage.value,
        "candidate_rejected": (
            evidence.stage.value
            in ("candidate_rejected", "safe_adoption_rejected")
        ),
        "reason_codes": tuple(evidence.reason_codes),
        "actual_adoption": bool(evidence.available),
        "physical_window": bool(
            evidence.available
            and evidence.physical_window_available
            and window is not None
            and window.available
            and window.physical_execution_observed
        ),
        "same_key_r0_pair": False,
        "benefit_auditable": False,
        "candidate_window_sha256": (
            None
            if window is None
            else _canonical_sha256(window.to_dict())
        ),
        "r0_window_sha256": None,
        "candidate_episode_id": None,
        "r0_episode_id": None,
        "candidate_event_log_sha256": None,
        "r0_event_log_sha256": None,
        "candidate_event_log_id": None,
        "r0_event_log_id": None,
        "candidate_window_id": (
            None if window is None else str(window.window_id)
        ),
        "r0_window_id": None,
        "candidate_physical_payload_sha256": (
            None
            if window is None
            else _canonical_sha256(window.to_dict())
        ),
        "r0_physical_payload_sha256": None,
        "candidate_execution_arm_id": None,
        "r0_execution_arm_id": None,
        "safe_adoption_evidence_sha256": str(evidence.content_sha256),
        "context_identity": None,
    }


def _a2_pair_source_sha256(
    record: Mapping[str, Any],
    context: str,
    blockers: list[str],
) -> str | None:
    try:
        return _sha256_text(
            record["safe_adoption_evidence_sha256"],
            f"{context}.safe_adoption_evidence_sha256",
        )
    except (KeyError, TypeError, ValueError) as exc:
        blockers.append(
            "a2_pair_source_reference_invalid."
            f"{_exception_code(exc)}"
        )
        return None


def _a2_pair_view(
    parsed: Any,
    safe_adoption: Any,
) -> dict[str, Any]:
    context = parsed.context
    candidate = parsed.candidate_window
    r0_window = parsed.same_key_r0_window
    if (
        str(parsed.safe_adoption_evidence_sha256)
        != str(safe_adoption.content_sha256)
    ):
        _fail("a2_candidate_safe_adoption_binding_mismatch")
    context_identity = _a2_context_identity(context)
    if candidate is not None:
        if _a2_window_identity(candidate) != context_identity:
            _fail("a2_candidate_comparison_identity_mismatch")
        _validate_a2_event_log_episode_binding(candidate)
    if r0_window is not None:
        if _a2_window_identity(r0_window) != context_identity:
            _fail("a2_same_key_r0_identity_mismatch")
        _validate_a2_event_log_episode_binding(r0_window)
    if candidate is not None and r0_window is not None:
        if (
            candidate.execution_arm_id == r0_window.execution_arm_id
            or candidate.source_event_log_id
            == r0_window.source_event_log_id
            or candidate.source_event_log_sha256
            == r0_window.source_event_log_sha256
        ):
            _fail("a2_candidate_r0_episode_or_event_log_reuse")

    actual_adoption = bool(
        safe_adoption.available
        and safe_adoption.safe_adoption_available
        and not safe_adoption.a2_benefit_available
        and not safe_adoption.authority_granted
        and not safe_adoption.online_truth_used
    )
    physical_available = bool(
        actual_adoption
        and candidate is not None
        and _a2_window_execution_complete(candidate)
    )
    r0_available = bool(
        physical_available
        and r0_window is not None
        and _a2_window_execution_complete(r0_window)
        and candidate is not None
        and _a2_window_identity(candidate)
        == _a2_window_identity(r0_window)
    )
    wrapper_blockers = tuple(str(item) for item in parsed.blocker_codes)
    benefit_auditable = bool(
        r0_available
        and not wrapper_blockers
        and parsed.d6_benefit_audit_eligible
    )
    expected_hard_constraints = bool(
        candidate is not None
        and r0_window is not None
        and candidate.hard_constraint_violation_count == 0
        and r0_window.hard_constraint_violation_count == 0
    )
    expected_unique_r0 = bool(
        candidate is not None and r0_window is not None
    )
    if (
        parsed.candidate_physical_window_available
        != (candidate is not None)
        or parsed.same_key_r0_window_available != (r0_window is not None)
        or parsed.unique_same_key_r0_available != expected_unique_r0
        or parsed.hard_constraints_satisfied
        != expected_hard_constraints
        or parsed.d6_benefit_audit_eligible != benefit_auditable
    ):
        _fail("a2_pair_summary_recomputation_mismatch")
    permissions = parsed.permissions
    if (
        permissions.d6_benefit_audit_input_allowed
        != benefit_auditable
        or permissions.a2_assist_authority
        or permissions.model_promotion_authority
        or permissions.assignment_authority
        or permissions.failover_authority
        or permissions.control_authority
        or parsed.a2_benefit_available
        or parsed.authority_granted
        or parsed.final_benefit_computed
        or parsed.online_truth_used
    ):
        _fail("a2_pair_authority_or_result_escalation")

    highest_stage = safe_adoption.stage.value
    if physical_available:
        highest_stage = "physical_window_available"
    if r0_available:
        highest_stage = "same_key_r0_validated"
    if benefit_auditable:
        highest_stage = "auditable_benefit_input"
    return {
        "record_kind": "pair",
        "evidence_id": str(parsed.audit_input_id),
        "comparison_key": str(context.comparison_key),
        "highest_stage": highest_stage,
        "candidate_rejected": (
            safe_adoption.stage.value == "candidate_rejected"
        ),
        "reason_codes": tuple(
            dict.fromkeys(
                (*safe_adoption.reason_codes, *wrapper_blockers)
            )
        ),
        "actual_adoption": actual_adoption,
        "physical_window": physical_available,
        "same_key_r0_pair": r0_available,
        "benefit_auditable": benefit_auditable,
        "candidate_window_sha256": (
            None if candidate is None else str(candidate.content_sha256)
        ),
        "r0_window_sha256": (
            None if r0_window is None else str(r0_window.content_sha256)
        ),
        "candidate_episode_id": (
            None if candidate is None else str(candidate.execution_arm_id)
        ),
        "r0_episode_id": (
            None
            if r0_window is None
            else str(r0_window.execution_arm_id)
        ),
        "candidate_event_log_sha256": (
            None
            if candidate is None
            else str(candidate.source_event_log_sha256)
        ),
        "r0_event_log_sha256": (
            None
            if r0_window is None
            else str(r0_window.source_event_log_sha256)
        ),
        "candidate_event_log_id": (
            None
            if candidate is None
            else str(candidate.source_event_log_id)
        ),
        "r0_event_log_id": (
            None
            if r0_window is None
            else str(r0_window.source_event_log_id)
        ),
        "candidate_window_id": (
            None if candidate is None else str(candidate.window_id)
        ),
        "r0_window_id": (
            None if r0_window is None else str(r0_window.window_id)
        ),
        "candidate_physical_payload_sha256": (
            None
            if candidate is None
            else str(candidate.physical_window_payload_sha256)
        ),
        "r0_physical_payload_sha256": (
            None
            if r0_window is None
            else str(r0_window.physical_window_payload_sha256)
        ),
        "candidate_execution_arm_id": (
            None
            if candidate is None
            else str(candidate.execution_arm_id)
        ),
        "r0_execution_arm_id": (
            None
            if r0_window is None
            else str(r0_window.execution_arm_id)
        ),
        "safe_adoption_evidence_sha256": str(
            parsed.safe_adoption_evidence_sha256
        ),
        "context_identity": context_identity,
    }


def _a2_context_identity(context: Any) -> tuple[Any, ...]:
    return (
        str(context.comparison_key),
        str(context.scenario_id),
        str(context.scenario_version),
        int(context.scale),
        int(context.seed),
        str(context.paired_window_id),
        str(context.paired_exogenous_config_sha256),
        float(context.required_window_duration_s),
    )


def _a2_window_identity(window: Any) -> tuple[Any, ...]:
    return (
        str(window.comparison_key),
        str(window.scenario_id),
        str(window.scenario_version),
        int(window.scale),
        int(window.seed),
        str(window.paired_window_id),
        str(window.paired_exogenous_config_sha256),
        float(window.duration_s),
    )


def _a2_window_execution_complete(window: Any) -> bool:
    return bool(
        window.physical_execution_observed
        and window.window_complete
        and window.hard_constraint_violation_count == 0
        and window.window_end_s < window.plan_valid_until_s
        and window.window_end_s < window.authority_lease_expires_at_s
        and not window.online_truth_used
    )


def _validate_a2_event_log_episode_binding(window: Any) -> None:
    if not str(window.execution_arm_id).strip():
        _fail("a2_event_log_episode_binding_mismatch")
    if not str(window.source_event_log_id).strip():
        _fail("a2_event_log_episode_binding_mismatch")


def _audit_a2_pair_uniqueness(
    records: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    blockers: list[str] = []
    comparison_keys: set[str] = set()
    evidence_ids: set[str] = set()
    candidate_window_owners: dict[tuple[str, str], str] = {}
    r0_references: dict[tuple[str, str], str] = {}
    event_log_episode_owners: dict[str, str] = {}
    episode_event_logs: dict[str, str] = {}
    for item in records:
        key = str(item["comparison_key"])
        evidence_id = str(item["evidence_id"])
        if key in comparison_keys:
            blockers.append("a2_duplicate_comparison_key")
        comparison_keys.add(key)
        if evidence_id in evidence_ids:
            blockers.append("a2_duplicate_evidence_id")
        evidence_ids.add(evidence_id)

        for field in (
            "candidate_window_sha256",
            "candidate_window_id",
            "candidate_physical_payload_sha256",
        ):
            value = item.get(field)
            if value is None:
                continue
            identity = (field, str(value))
            owner = candidate_window_owners.setdefault(identity, key)
            if owner != key:
                blockers.append("a2_cross_key_candidate_window_reuse")

        for field in (
            "r0_window_sha256",
            "r0_window_id",
            "r0_physical_payload_sha256",
            "r0_event_log_id",
            "r0_event_log_sha256",
            "r0_execution_arm_id",
        ):
            value = item.get(field)
            if value is None:
                continue
            identity = (field, str(value))
            if identity in r0_references:
                blockers.append("a2_r0_multi_pair_reuse")
            else:
                r0_references[identity] = key

        candidate_episode = item.get("candidate_episode_id")
        r0_episode = item.get("r0_episode_id")
        if (
            candidate_episode is not None
            and r0_episode is not None
            and candidate_episode == r0_episode
        ):
            blockers.append("a2_candidate_r0_episode_reuse")
        for episode_id, digest in (
            (candidate_episode, item.get("candidate_event_log_sha256")),
            (r0_episode, item.get("r0_event_log_sha256")),
        ):
            if digest is None or episode_id is None:
                continue
            episode_id = str(episode_id)
            digest = str(digest)
            owner = event_log_episode_owners.setdefault(digest, episode_id)
            if owner != episode_id:
                blockers.append("a2_event_log_episode_binding_mismatch")
            episode_log = episode_event_logs.setdefault(episode_id, digest)
            if episode_log != digest:
                blockers.append("a2_event_log_episode_binding_mismatch")
    return _dedupe(blockers)


def _load_a2_safe_adoption_record(
    record: Mapping[str, Any],
    module: Any,
) -> Any:
    """Rebuild the public D4 DTO graph and require an exact JSON round trip."""

    evidence_cls = getattr(module, "RegionResourceSafeAdoptionEvidence", None)
    preparation_cls = getattr(
        module,
        "RegionResourceSafeAdoptionPreparation",
        None,
    )
    applied_cls = getattr(
        module,
        "RegionResourceAppliedRecommendation",
        None,
    )
    required_classes = (evidence_cls, preparation_cls, applied_cls)
    if any(item is None for item in required_classes):
        _fail("a2_public_contract_unavailable")

    payload = _strict_dataclass_payload(
        evidence_cls,
        record,
        "a2_evidence",
        extra_fields=("content_sha256",),
    )
    expected_schema = getattr(
        module,
        "REGION_RESOURCE_SAFE_ADOPTION_EVIDENCE_SCHEMA",
        None,
    )
    if payload["schema"] != expected_schema:
        _fail("a2_schema_unsupported")

    preparation_payload = _strict_dataclass_payload(
        preparation_cls,
        payload["preparation"],
        "a2_preparation",
    )
    applied_value = preparation_payload["applied_recommendation"]
    applied = (
        None
        if applied_value is None
        else _load_a2_applied_recommendation(applied_value, module)
    )
    preparation_payload["reason_codes"] = _strict_text_tuple(
        preparation_payload["reason_codes"],
        "a2_preparation.reason_codes",
    )
    preparation_payload["applied_recommendation"] = applied
    _strict_bool_value(
        preparation_payload["available"],
        "a2_preparation.available",
    )
    preparation = preparation_cls(**preparation_payload)

    plan_value = payload["d3_successor_plan"]
    plan = (
        None
        if plan_value is None
        else module.RegionResourceD3PlanReference.from_value(plan_value)
    )
    runtime_ack = _load_a2_runtime_ack(payload["runtime_ack"])
    owner_value = payload["owner_ack_delivery"]
    owner_delivery = (
        None
        if owner_value is None
        else module.RegionResourceOwnerAckDelivery.from_value(owner_value)
    )
    commits = tuple(
        module.RegionResourceCoalitionCommitEvidence.from_value(item)
        for item in _strict_sequence(
            payload["coalition_commits"],
            "a2_evidence.coalition_commits",
        )
    )
    window_value = payload["physical_window"]
    window = (
        None
        if window_value is None
        else module.RegionResourcePhysicalWindowEvidence.from_value(
            window_value
        )
    )
    for name in (
        "available",
        "projection_available",
        "d3_successor_plan_available",
        "runtime_ack_available",
        "owner_ack_available",
        "coalition_commit_required",
        "coalition_commit_available",
        "physical_window_available",
        "safe_adoption_available",
        "a2_benefit_available",
        "authority_granted",
        "online_truth_used",
    ):
        _strict_bool_value(payload[name], f"a2_evidence.{name}")

    claimed_sha256 = _sha256_text(
        payload.pop("content_sha256"),
        "a2_evidence.content_sha256",
    )
    payload["reason_codes"] = _strict_text_tuple(
        payload["reason_codes"],
        "a2_evidence.reason_codes",
    )
    payload["preparation"] = preparation
    payload["d3_successor_plan"] = plan
    payload["runtime_ack"] = runtime_ack
    payload["owner_ack_delivery"] = owner_delivery
    payload["coalition_commits"] = commits
    payload["physical_window"] = window
    parsed = evidence_cls(**payload)
    if claimed_sha256 != parsed.content_sha256:
        _fail("a2_content_sha256_mismatch")
    normalized = _strict_json_mapping(parsed.to_dict(), "a2_evidence")
    if normalized != record:
        _fail("a2_contract_roundtrip_mismatch")
    return parsed


def _load_a2_applied_recommendation(value: Any, module: Any) -> Any:
    applied_cls = module.RegionResourceAppliedRecommendation
    payload = _strict_dataclass_payload(
        applied_cls,
        value,
        "a2_applied_recommendation",
    )
    try:
        region_module = _import_public_module(
            "d4_distributed_fallback.region_resource"
        )
    except _PublicModuleUnavailable:
        _fail("a2_public_advisory_loader_unavailable")
    advisory_cls = getattr(
        region_module,
        "RegionResourceAdvisoryContract",
        None,
    )
    if advisory_cls is None or not callable(
        getattr(advisory_cls, "from_dict", None)
    ):
        _fail("a2_public_advisory_loader_unavailable")
    payload["advisory"] = advisory_cls.from_dict(
        _strict_mapping(payload["advisory"], "a2_advisory")
    )
    payload["region_ids"] = _strict_text_tuple(
        payload["region_ids"],
        "a2_applied_recommendation.region_ids",
    )
    for name in (
        "deterministic_projection_applied",
        "execution_authority_granted",
        "a2_benefit_claimed",
    ):
        _strict_bool_value(
            payload[name],
            f"a2_applied_recommendation.{name}",
        )
    return applied_cls(**payload)


def _load_a2_runtime_ack(value: Any) -> Any | None:
    if value is None:
        return None
    try:
        runtime_module = _import_public_module(
            "d4_distributed_fallback.region_resource_runtime_ack"
        )
    except _PublicModuleUnavailable:
        _fail("a2_public_runtime_ack_contract_unavailable")
    runtime_cls = getattr(
        runtime_module,
        "RegionResourceRuntimeAckEvidence",
        None,
    )
    if runtime_cls is None:
        _fail("a2_public_runtime_ack_contract_unavailable")
    payload = _strict_dataclass_payload(
        runtime_cls,
        value,
        "a2_runtime_ack",
    )
    payload["rejection_reasons"] = _strict_text_tuple(
        payload["rejection_reasons"],
        "a2_runtime_ack.rejection_reasons",
    )
    for name in (
        "runtime_advisory_applied_ack_available",
        "coalition_member_ack_available",
        "physical_outcome_available",
        "attributable_reward_available",
        "paired_shadow_available",
        "ppo_admission_allowed",
        "assist_admission_allowed",
        "authority_admission_allowed",
    ):
        _strict_bool_value(payload[name], f"a2_runtime_ack.{name}")
    return runtime_cls(**payload)


def _validate_a2_cross_bindings(evidence: Any) -> None:
    preparation = evidence.preparation
    applied = preparation.applied_recommendation
    stage = evidence.stage.value
    if stage == "candidate_rejected":
        if (
            evidence.available
            or preparation.available
            or applied is not None
            or preparation.stage.value != "candidate_rejected"
            or tuple(evidence.reason_codes) != tuple(preparation.reason_codes)
            or evidence.d3_successor_plan is not None
            or evidence.runtime_ack is not None
            or evidence.owner_ack_delivery is not None
            or evidence.coalition_commits
            or evidence.physical_window is not None
            or any(
                (
                    evidence.projection_available,
                    evidence.d3_successor_plan_available,
                    evidence.runtime_ack_available,
                    evidence.owner_ack_available,
                    evidence.coalition_commit_required,
                    evidence.coalition_commit_available,
                    evidence.physical_window_available,
                    evidence.safe_adoption_available,
                )
            )
        ):
            _fail("a2_candidate_rejection_contract_invalid")
        return

    if (
        not preparation.available
        or applied is None
        or preparation.stage.value != "applied_recommendation_prepared"
        or not evidence.projection_available
    ):
        _fail("a2_projection_contract_incomplete")
    _validate_a2_applied_recommendation(applied, evidence.evaluated_at_s)

    if stage == "safe_adoption_rejected":
        if (
            evidence.available
            or not evidence.reason_codes
            or evidence.d3_successor_plan is not None
            or evidence.runtime_ack is not None
            or evidence.owner_ack_delivery is not None
            or evidence.coalition_commits
            or evidence.physical_window is not None
            or any(
                (
                    evidence.d3_successor_plan_available,
                    evidence.runtime_ack_available,
                    evidence.owner_ack_available,
                    evidence.coalition_commit_required,
                    evidence.physical_window_available,
                    evidence.safe_adoption_available,
                )
            )
            or not evidence.coalition_commit_available
        ):
            _fail("a2_post_projection_rejection_contract_invalid")
        return

    plan = evidence.d3_successor_plan
    if plan is None:
        if (
            stage != "awaiting_d3_plan"
            or evidence.d3_successor_plan_available
            or evidence.runtime_ack is not None
            or evidence.owner_ack_delivery is not None
            or evidence.coalition_commits
            or evidence.physical_window is not None
        ):
            _fail("a2_d3_plan_stage_contradiction")
        return
    if not evidence.d3_successor_plan_available:
        _fail("a2_d3_plan_availability_flag_invalid")
    _validate_a2_successor_plan(applied, plan)

    runtime_ack = evidence.runtime_ack
    if runtime_ack is None:
        if (
            stage != "awaiting_runtime_ack"
            or evidence.runtime_ack_available
            or evidence.owner_ack_delivery is not None
            or evidence.coalition_commits
            or evidence.physical_window is not None
        ):
            _fail("a2_runtime_ack_stage_contradiction")
        return
    if not evidence.runtime_ack_available:
        _fail("a2_runtime_ack_availability_flag_invalid")
    _validate_a2_runtime_ack_binding(applied, plan, runtime_ack)

    owner_delivery = evidence.owner_ack_delivery
    if owner_delivery is None:
        if (
            stage != "awaiting_owner_ack"
            or evidence.owner_ack_available
            or evidence.coalition_commits
            or evidence.physical_window is not None
        ):
            _fail("a2_owner_ack_stage_contradiction")
        return
    if not evidence.owner_ack_available:
        _fail("a2_owner_ack_availability_flag_invalid")
    _validate_a2_owner_ack(
        applied,
        plan,
        runtime_ack,
        owner_delivery,
        evidence.evaluated_at_s,
    )

    requirements = tuple(plan.coalition_requirements)
    if evidence.coalition_commit_required != bool(requirements):
        _fail("a2_coalition_required_flag_invalid")
    if requirements and not evidence.coalition_commits:
        if (
            stage != "awaiting_coalition_commit"
            or evidence.coalition_commit_available
            or evidence.physical_window is not None
        ):
            _fail("a2_coalition_stage_contradiction")
        return
    _validate_a2_coalition_commits(
        applied,
        plan,
        tuple(evidence.coalition_commits),
        evidence.evaluated_at_s,
    )
    if not evidence.coalition_commit_available:
        _fail("a2_coalition_availability_flag_invalid")

    window = evidence.physical_window
    if window is None:
        if stage != "awaiting_physical_window" or evidence.physical_window_available:
            _fail("a2_physical_window_stage_contradiction")
        return
    if (
        not evidence.available
        or not evidence.safe_adoption_available
        or not evidence.physical_window_available
        or stage != "physical_window_available"
    ):
        _fail("a2_safe_adoption_availability_invalid")
    _validate_a2_physical_window(
        applied,
        plan,
        runtime_ack,
        owner_delivery,
        tuple(evidence.coalition_commits),
        window,
        evidence.evaluated_at_s,
    )


def _validate_a2_applied_recommendation(
    applied: Any,
    evaluated_at_s: float,
) -> None:
    advisory = applied.advisory
    if applied.advisory_payload_sha256 != _canonical_sha256(
        advisory.to_dict()
    ):
        _fail("a2_advisory_payload_sha256_mismatch")
    source = getattr(advisory.source, "value", advisory.source)
    if (
        source != "learned"
        or not advisory.projected
        or advisory.publication_rejections
    ):
        _fail("a2_learned_projection_not_established")
    if advisory.confidence < 0.60:
        _fail("a2_advisory_confidence_below_contract")
    if not (
        advisory.valid_from_s
        <= applied.consumption_timestamp_s
        <= advisory.valid_until_s
    ):
        _fail("a2_advisory_consumption_time_invalid")
    if not (
        applied.consumption_timestamp_s
        <= evaluated_at_s
        < applied.lease_expires_at_s
    ):
        _fail("a2_evaluation_time_scope_invalid")
    regions = tuple(sorted(item.region_id for item in advisory.regions))
    if regions != tuple(applied.region_ids):
        _fail("a2_applied_region_scope_mismatch")
    domains = {
        (
            item.source_version.owner_id,
            item.source_version.owner_layer,
            item.source_version.plan_id,
            item.source_version.plan_version,
            item.source_version.epoch,
            item.source_version.lease_expires_at_s,
        )
        for item in advisory.regions
    }
    expected_domain = {
        (
            applied.owner_node_id,
            applied.owner_layer,
            applied.source_plan_id,
            applied.source_plan_version,
            applied.epoch,
            applied.lease_expires_at_s,
        )
    }
    if domains != expected_domain:
        _fail("a2_applied_authority_domain_mismatch")


def _validate_a2_successor_plan(applied: Any, plan: Any) -> None:
    if (
        plan.previous_plan_id != applied.source_plan_id
        or plan.previous_plan_version != applied.source_plan_version
        or plan.plan_id == applied.source_plan_id
        or plan.plan_version <= applied.source_plan_version
    ):
        _fail("a2_successor_plan_generation_invalid")
    if (
        plan.owner_node_id != applied.owner_node_id
        or plan.owner_layer != applied.owner_layer
        or plan.epoch != applied.epoch
    ):
        _fail("a2_successor_plan_authority_mismatch")
    if (
        plan.source_advisory_id != applied.advisory.advisory_id
        or plan.source_advisory_version != applied.advisory_version
        or plan.source_advisory_payload_sha256
        != applied.advisory_payload_sha256
    ):
        _fail("a2_successor_plan_advisory_mismatch")
    if not (
        plan.accepted_by_main_runtime
        and plan.regional_hint_applied
        and plan.stale_version_rejected
    ):
        _fail("a2_successor_plan_not_applied")
    if (
        plan.created_at_s < applied.consumption_timestamp_s
        or plan.valid_until_s > applied.lease_expires_at_s
    ):
        _fail("a2_successor_plan_time_scope_invalid")


def _validate_a2_runtime_ack_binding(
    applied: Any,
    plan: Any,
    runtime_ack: Any,
) -> None:
    if (
        runtime_ack.schema != "d4-region-resource-runtime-ack-evidence-v2"
        or runtime_ack.code
        != "runtime_advisory_applied_ack_available"
        or not runtime_ack.runtime_advisory_applied_ack_available
        or runtime_ack.adoption_kind != "new_execution_plan_applied"
        or runtime_ack.assignment_plan_ack_payload_sha256 is None
        or runtime_ack.ack_bus_sequence is None
    ):
        _fail("a2_runtime_ack_unavailable")
    expected = {
        "advisory_id": applied.advisory.advisory_id,
        "advisory_version": applied.advisory_version,
        "advisory_payload_sha256": applied.advisory_payload_sha256,
        "source_plan_id": applied.source_plan_id,
        "source_plan_version": applied.source_plan_version,
        "applied_plan_id": plan.plan_id,
        "applied_plan_version": plan.plan_version,
        "owner_layer": applied.owner_layer.value,
        "owner_node_id": applied.owner_node_id,
        "authority_epoch": applied.epoch,
        "lease_expires_at_s": applied.lease_expires_at_s,
        "source_plan_bus_sequence": plan.plan_bus_sequence,
        "source_plan_payload_sha256": plan.plan_payload_sha256,
    }
    if any(
        getattr(runtime_ack, name) != expected_value
        for name, expected_value in expected.items()
    ):
        _fail("a2_runtime_ack_cross_binding_invalid")
    if (
        runtime_ack.acknowledged_at_s is None
        or runtime_ack.acknowledged_at_s < plan.created_at_s
        or runtime_ack.acknowledged_at_s >= applied.lease_expires_at_s
    ):
        _fail("a2_runtime_ack_timestamp_invalid")


def _validate_a2_owner_ack(
    applied: Any,
    plan: Any,
    runtime_ack: Any,
    delivery: Any,
    evaluated_at_s: float,
) -> None:
    try:
        communication = _import_public_module(
            "d4_distributed_fallback.communication_causal_evidence"
        )
    except _PublicModuleUnavailable:
        _fail("a2_public_communication_contract_unavailable")
    ack = delivery.ack
    receipt = delivery.receipt
    expected = {
        "owner_node_id": applied.owner_node_id,
        "owner_layer": applied.owner_layer,
        "region_ids": applied.region_ids,
        "advisory_id": applied.advisory.advisory_id,
        "advisory_version": applied.advisory_version,
        "advisory_payload_sha256": applied.advisory_payload_sha256,
        "source_plan_id": applied.source_plan_id,
        "source_plan_version": applied.source_plan_version,
        "applied_plan_id": plan.plan_id,
        "applied_plan_version": plan.plan_version,
        "applied_plan_payload_sha256": plan.plan_payload_sha256,
        "applied_plan_bus_sequence": plan.plan_bus_sequence,
        "runtime_assignment_ack_payload_sha256": (
            runtime_ack.assignment_plan_ack_payload_sha256
        ),
        "runtime_assignment_ack_bus_sequence": runtime_ack.ack_bus_sequence,
        "epoch": applied.epoch,
        "lease_expires_at_s": applied.lease_expires_at_s,
    }
    if any(
        getattr(ack, name) != expected_value
        for name, expected_value in expected.items()
    ) or not ack.accepted:
        _fail("a2_owner_ack_cross_binding_invalid")
    if (
        ack.acknowledged_at_s < plan.created_at_s
        or ack.acknowledged_at_s > evaluated_at_s
        or receipt.arrival_timestamp_s > evaluated_at_s
    ):
        _fail("a2_owner_ack_timestamp_invalid")
    expected_receipt_id = communication.expected_delivery_receipt_id(receipt)
    if (
        receipt.receipt_id != expected_receipt_id
        or receipt.transport_topic
        != "d4.regional_plan_owner_ack.v1"
        or receipt.message_id != ack.message_id
        or receipt.source_node_id != applied.owner_node_id
        or receipt.authority_id != applied.owner_node_id
        or receipt.plan_version != plan.plan_version
        or receipt.epoch != applied.epoch
        or receipt.lease_expires_at_s != applied.lease_expires_at_s
        or receipt.partition_generation != ack.partition_generation
        or abs(receipt.sent_timestamp_s - ack.acknowledged_at_s) > 1.0e-9
        or receipt.payload_digest
        != communication.canonical_payload_digest(
            ack.to_transport_payload()
        )
    ):
        _fail("a2_owner_ack_delivery_invalid")


def _validate_a2_coalition_commits(
    applied: Any,
    plan: Any,
    commits: tuple[Any, ...],
    evaluated_at_s: float,
) -> None:
    try:
        communication = _import_public_module(
            "d4_distributed_fallback.communication_causal_evidence"
        )
    except _PublicModuleUnavailable:
        _fail("a2_public_communication_contract_unavailable")
    required = {
        (
            item.global_track_id,
            item.coalition_id,
            item.coalition_version,
        ): item
        for item in plan.coalition_requirements
    }
    actual = {
        (
            item.state.global_track_id,
            item.state.coalition_id,
            item.state.coalition_version,
        ): item
        for item in commits
    }
    if len(actual) != len(commits) or set(actual) != set(required):
        _fail("a2_coalition_commit_set_mismatch")
    for key, requirement in required.items():
        evidence = actual[key]
        state = evidence.state
        if (
            state.plan_id != plan.plan_id
            or state.plan_version != plan.plan_version
            or state.epoch != applied.epoch
            or state.coordinator_id != applied.owner_node_id
            or state.lease_expires_at != applied.lease_expires_at_s
            or state.state != "executing"
            or state.required_member_ids != requirement.required_member_ids
            or state.acked_member_ids != requirement.required_member_ids
            or state.missing_member_ids
            or state.committed_at is None
            or state.executing_at is None
            or state.executing_at > evaluated_at_s
        ):
            _fail("a2_coalition_commit_incomplete_or_stale")
        deliveries = {
            item.member_ack.resource_id: item
            for item in evidence.member_ack_deliveries
        }
        if (
            len(deliveries) != len(evidence.member_ack_deliveries)
            or set(deliveries) != set(requirement.required_member_ids)
        ):
            _fail("a2_coalition_member_ack_set_mismatch")
        for member_id in requirement.required_member_ids:
            delivery = deliveries[member_id]
            ack = delivery.member_ack
            receipt = delivery.receipt
            if (
                delivery.authority_id != applied.owner_node_id
                or delivery.plan_payload_sha256 != plan.plan_payload_sha256
                or delivery.plan_bus_sequence != plan.plan_bus_sequence
                or delivery.lease_expires_at_s
                != applied.lease_expires_at_s
                or ack.global_track_id != requirement.global_track_id
                or ack.coalition_id != requirement.coalition_id
                or ack.coalition_version != requirement.coalition_version
                or ack.plan_id != plan.plan_id
                or ack.plan_version != plan.plan_version
                or ack.epoch != applied.epoch
                or not ack.can_execute
                or ack.valid_until < state.lease_expires_at
                or ack.evidence_timestamp > state.committed_at
                or receipt.receipt_id
                != communication.expected_delivery_receipt_id(receipt)
                or receipt.transport_topic != "d4.coalition_member_ack.v1"
                or receipt.message_id != delivery.message_id
                or receipt.source_node_id != member_id
                or receipt.destination_node_id != applied.owner_node_id
                or receipt.authority_id != applied.owner_node_id
                or receipt.plan_version != plan.plan_version
                or receipt.epoch != applied.epoch
                or receipt.lease_expires_at_s
                != applied.lease_expires_at_s
                or receipt.partition_generation
                != delivery.partition_generation
                or abs(receipt.sent_timestamp_s - ack.evidence_timestamp)
                > 1.0e-9
                or receipt.payload_digest
                != communication.canonical_payload_digest(
                    delivery.to_transport_payload()
                )
            ):
                _fail("a2_coalition_member_ack_cross_binding_invalid")


def _validate_a2_physical_window(
    applied: Any,
    plan: Any,
    runtime_ack: Any,
    owner_delivery: Any,
    commits: tuple[Any, ...],
    window: Any,
    evaluated_at_s: float,
) -> None:
    if (
        not window.available
        or not window.physical_execution_observed
        or window.hard_constraint_violation_count != 0
    ):
        _fail("a2_physical_window_unavailable")
    if (
        window.advisory_id != applied.advisory.advisory_id
        or window.advisory_version != applied.advisory_version
        or window.advisory_payload_sha256
        != applied.advisory_payload_sha256
        or window.applied_plan_id != plan.plan_id
        or window.applied_plan_version != plan.plan_version
        or window.runtime_ack_sha256
        != _canonical_sha256(runtime_ack.to_dict())
        or window.owner_ack_receipt_id
        != owner_delivery.receipt.receipt_id
    ):
        _fail("a2_physical_window_cross_binding_invalid")
    expected_commits = tuple(
        sorted(item.immutable_digest for item in commits)
    )
    if tuple(window.coalition_commit_sha256) != expected_commits:
        _fail("a2_physical_window_coalition_binding_invalid")
    required_start = max(
        plan.created_at_s,
        runtime_ack.acknowledged_at_s or 0.0,
        owner_delivery.receipt.arrival_timestamp_s,
        *(item.state.executing_at or 0.0 for item in commits),
    )
    if (
        window.window_start_s < required_start
        or window.window_end_s > evaluated_at_s
        or window.window_end_s >= applied.lease_expires_at_s
        or window.window_end_s > plan.valid_until_s
    ):
        _fail("a2_physical_window_time_scope_invalid")


def _a2_comparison_key(evidence: Any) -> str:
    applied = evidence.preparation.applied_recommendation
    if applied is None:
        return str(evidence.evidence_id)
    return str(applied.application_id)


def _a1_lifecycle_stage(payload: Mapping[str, Any]) -> str:
    if payload["r0_pair_available"]:
        return "r0_pair_claim_validated"
    if payload["physical_window_available"]:
        return "physical_window_claim_validated"
    if payload["runtime_ack"]:
        return "runtime_ack_claim_validated"
    if payload["plan_published"]:
        return "plan_published"
    return "candidate_selected"


def _a1_comparison_key(payload: Mapping[str, Any]) -> str:
    return ":".join(
        (
            str(payload["registration_id"]),
            str(payload["plan_id"]),
            str(payload["plan_version"]),
            str(payload["assignment_plan_payload_sha256"]),
        )
    )


def _a3_highest_stage(item: Any) -> str:
    trace = item.adoption_trace
    if item.d6_benefit_audit_eligible:
        return "auditable_benefit_input"
    if item.same_key_r0_window is not None:
        return "same_key_r0_validated"
    if item.candidate_window is not None:
        return "physical_window_validated"
    if trace.pose_applied:
        return "camera_pose_applied"
    if trace.runtime_ack_applied:
        return "runtime_ack_applied"
    if trace.command_issued:
        return "command_issued"
    if trace.command_proposed:
        return "command_proposed"
    if trace.policy_evaluated:
        return "policy_evaluated"
    return "unavailable"


def _a3_trace_comparison_identity(trace: Any) -> tuple[Any, ...]:
    """Recompute the public window identity from serialized trace fields."""

    action = trace.decision.effective_action
    return (
        str(trace.comparison_key),
        str(trace.scenario_id),
        int(trace.scale),
        int(trace.seed),
        int(trace.window_index),
        str(trace.camera_id),
        str(trace.resource_id),
        action.target_global_track_id,
        str(trace.pairing_context_sha256),
        int(action.plan_version),
        int(action.coalition_version),
        int(action.communication_version),
    )


def _a3_episode_id(sample_key: Any) -> str:
    value = str(sample_key).strip()
    episode_id, separator, _ = value.partition(":")
    if not separator or not episode_id:
        _fail("a3_sample_key_episode_binding_invalid")
    return episode_id


def _aggregate_metrics(
    variants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "highest_evidence_stage_by_variant": {
            name: variants[name]["highest_evidence_stage"]
            for name in _VARIANTS
        }
    }
    for field in (
        "actual_adoption_count",
        "physical_window_count",
        "same_key_r0_pair_count",
        "benefit_auditable_count",
    ):
        metrics = [variants[name][field] for name in _VARIANTS]
        if all(item["availability"] == "available" for item in metrics):
            result[field] = _metric_available(
                sum(int(item["value"]) for item in metrics)
            )
        else:
            reasons = _dedupe(
                code
                for item in metrics
                for code in item["reason_codes"]
            )
            result[field] = _metric_unavailable(reasons)
    result["auditable_benefit_count"] = dict(
        result["benefit_auditable_count"]
    )
    return result


def _empty_variant(variant: str, reason: str) -> dict[str, Any]:
    return _unavailable_variant(variant, 0, (reason,))


def _unavailable_variant(
    variant: str,
    record_count: int,
    reasons: Sequence[str],
) -> dict[str, Any]:
    normalized = tuple(_dedupe(reasons))
    return _variant_result(
        variant=variant,
        record_count=record_count,
        validated_record_count=0,
        availability="unavailable",
        highest_stage="unavailable",
        blocker_codes=normalized,
        actual=_metric_unavailable(normalized),
        physical=_metric_unavailable(normalized),
        r0=_metric_unavailable(normalized),
        benefit=_metric_unavailable(normalized),
    )


def _variant_result(
    *,
    variant: str,
    record_count: int,
    validated_record_count: int,
    availability: str,
    highest_stage: str,
    blocker_codes: Sequence[str],
    actual: Mapping[str, Any],
    physical: Mapping[str, Any],
    r0: Mapping[str, Any],
    benefit: Mapping[str, Any],
) -> dict[str, Any]:
    benefit_metric = dict(benefit)
    return {
        "variant": variant,
        "availability": availability,
        "record_count": int(record_count),
        "validated_record_count": int(validated_record_count),
        "highest_evidence_stage": highest_stage,
        "blocker_codes": list(_dedupe(blocker_codes)),
        "actual_adoption_count": dict(actual),
        "physical_window_count": dict(physical),
        "same_key_r0_pair_count": dict(r0),
        "benefit_auditable_count": benefit_metric,
        # Compatibility alias retained for existing main/D6 consumers.
        "auditable_benefit_count": dict(benefit_metric),
        "benefit_audit_status": (
            "audit_input_available"
            if benefit_metric.get("availability") == "available"
            else "unavailable"
        ),
        "positive_benefit_claimed": False,
        "non_degradation_claimed": False,
        "permissions": {name: False for name in _AUTHORITY_FIELDS},
    }


def _metric_available(value: int) -> dict[str, Any]:
    return {
        "availability": "available",
        "value": int(value),
        "reason_codes": [],
    }


def _metric_unavailable(reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "value": None,
        "reason_codes": list(_dedupe(reasons)),
    }


def _audit_value_available(value: Any) -> dict[str, Any]:
    return {
        "availability": "available",
        "value": value,
        "reason_codes": [],
    }


def _audit_value_unavailable(reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "value": None,
        "reason_codes": list(_dedupe(reasons)),
    }


def _max_stage(
    current: str,
    candidate: str,
    ranks: Mapping[str, int],
) -> str:
    return candidate if ranks[candidate] > ranks[current] else current


def _strict_record_sequence(value: Any, name: str) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        _fail("audit_input_record_sequence_invalid", name)
    return [
        _strict_json_mapping(item, f"{name}[{index}]")
        for index, item in enumerate(value)
    ]


def _strict_json_mapping(value: Any, name: str) -> dict[str, Any]:
    mapping = _strict_mapping(value, name)
    try:
        encoded = json.dumps(
            mapping,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        _fail("audit_input_record_not_json", f"{name}:{type(exc).__name__}")
    if not isinstance(decoded, dict):
        _fail("audit_input_record_type_invalid", name)
    return decoded


def _strict_dataclass_payload(
    cls: Any,
    value: Any,
    name: str,
    *,
    extra_fields: Sequence[str] = (),
) -> dict[str, Any]:
    mapping = _strict_mapping(value, name)
    expected = {item.name for item in fields(cls)} | set(extra_fields)
    if set(mapping) != expected:
        _fail(
            f"{name}_fields_mismatch",
            ",".join(sorted(set(mapping) ^ expected)),
        )
    return dict(mapping)


def _alias_value(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> Any:
    present = [(name, mapping[name]) for name in names if name in mapping]
    if not present:
        _fail("audit_input_required_field_missing", context)
    first = present[0][1]
    if any(value != first for _, value in present[1:]):
        _fail("audit_input_alias_fields_disagree", context)
    return first


def _optional_alias_value(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> Any | None:
    present = [(name, mapping[name]) for name in names if name in mapping]
    if not present:
        return None
    first = present[0][1]
    if any(value != first for _, value in present[1:]):
        _fail("audit_input_alias_fields_disagree", context)
    return first


def _mapping_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> Mapping[str, Any]:
    return _strict_mapping(_alias_value(mapping, names, context), context)


def _optional_mapping_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> Mapping[str, Any] | None:
    value = _optional_alias_value(mapping, names, context)
    if value is None:
        return None
    return _strict_mapping(value, context)


def _required_text_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> str:
    value = _alias_value(mapping, names, context)
    if not isinstance(value, str) or not value.strip():
        _fail("audit_input_text_invalid", context)
    return value.strip()


def _optional_text_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> str | None:
    value = _optional_alias_value(mapping, names, context)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail("audit_input_text_invalid", context)
    return value.strip()


def _optional_text_tuple_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> tuple[str, ...]:
    value = _optional_alias_value(mapping, names, context)
    if value is None:
        return ()
    return _strict_text_tuple(value, context)


def _optional_bool_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> bool | None:
    value = _optional_alias_value(mapping, names, context)
    if value is None:
        return None
    return _strict_bool_value(value, context)


def _validate_optional_bool_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    expected: bool,
    context: str,
) -> None:
    observed = _optional_bool_alias(mapping, names, context)
    if observed is not None and observed is not expected:
        _fail("a2_pair_summary_recomputation_mismatch", context)


def _optional_sha256_alias(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    context: str,
) -> str | None:
    value = _optional_alias_value(mapping, names, context)
    if value is None:
        return None
    return _sha256_text(value, context)


def _strict_nonnegative_int_value(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("audit_input_nonnegative_int_invalid", context)
    return value


def _strict_positive_int_value(value: Any, context: str) -> int:
    result = _strict_nonnegative_int_value(value, context)
    if result < 1:
        _fail("audit_input_positive_int_invalid", context)
    return result


def _strict_sequence(value: Any, name: str) -> tuple[Any, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        _fail("audit_input_sequence_invalid", name)
    return tuple(value)


def _strict_text_tuple(value: Any, name: str) -> tuple[str, ...]:
    result = _strict_sequence(value, name)
    if any(not isinstance(item, str) or not item for item in result):
        _fail("audit_input_text_sequence_invalid", name)
    if len(result) != len(set(result)):
        _fail("audit_input_text_sequence_duplicate", name)
    return tuple(result)


def _strict_bool_value(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        _fail("audit_input_bool_invalid", name)
    return value


def _strict_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("audit_input_mapping_required", name)
    if any(not isinstance(key, str) for key in value):
        _fail("audit_input_key_type_invalid", name)
    return value


def _authority_escalation_requested(record: Mapping[str, Any]) -> bool:
    permissions = record.get("permissions")
    if not isinstance(permissions, Mapping):
        return False
    return any(permissions.get(name) is True for name in _AUTHORITY_FIELDS)


def _synthetic_fixture_claimed(value: Any) -> bool:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if key in {
                "synthetic_fixture",
                "synthetic_runtime",
                "is_synthetic",
            } and item is True:
                return True
            if key.endswith("evidence_kind") and str(item).strip().lower() in {
                "synthetic",
                "synthetic_fixture",
                "test_fixture",
            }:
                return True
            if _synthetic_fixture_claimed(item):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return any(_synthetic_fixture_claimed(item) for item in value)
    return False


def _contains_forbidden_key(
    value: Any,
    forbidden: frozenset[str],
) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in forbidden:
                return True
            if _contains_forbidden_key(item, forbidden):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def _exception_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and reason:
        return reason
    text = str(exc).split(":", 1)[0].strip()
    return text or type(exc).__name__.lower()


def _assert_finite(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_finite(item)
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for item in value:
            _assert_finite(item)
        return
    if isinstance(value, float) and not isfinite(value):
        _fail("audit_input_nonfinite_number")


def _sha256_text(value: Any, name: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        _fail("audit_input_sha256_invalid", name)
    return text


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _dedupe(values: Sequence[str] | Any) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _fail(code: str, detail: str | None = None) -> None:
    raise StrictLearningAdoptionAuditError(code, detail)


__all__ = [
    "LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION",
    "LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION_V1",
    "LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION_V2",
    "LEARNING_ADOPTION_AUDIT_CONSUMER_SCHEMA_VERSION_V3",
    "LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION",
    "LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2",
    "LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION",
    "LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION_V1",
    "LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION_V2",
    "LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION_V3",
    "LEARNING_ADOPTION_EPISODE_RECORDS_SCHEMA_VERSION",
    "StrictLearningAdoptionAuditError",
    "audit_learning_adoption_evidence",
    "build_learning_adoption_audit_input",
    "build_learning_adoption_audit_input_from_episode_files",
    "load_learning_adoption_audit_input",
    "load_learning_adoption_audit_output",
    "load_learning_adoption_episode_evidence",
    "validate_learning_adoption_audit_input",
    "validate_learning_adoption_audit_output",
]
