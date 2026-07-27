"""Fail-closed D4 A2 evidence assembly and strict loading.

The existing regional model bundle remains a development/shadow artifact.
This module wraps that immutable source bundle with externally produced
evidence.  A successful assembly grants only ``a2_assist_eligible``.  It never
grants default-model, PPO, failover, assignment, or control authority.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from hashlib import sha256
import json
from math import isclose, isfinite
import os
from pathlib import Path
import re
import shutil
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .coalition_safety import CoalitionCommitState, CoalitionMemberAck
from .region_resource import REGION_RESOURCE_ADVISORY_SCHEMA
from .region_resource_learning import (
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    LoadedRegionResourceModelBundle,
    ModelBundleValidationError,
    RegionResourceModelManifest,
    load_region_resource_model_bundle,
)
from .region_resource_runtime_ack import (
    REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA,
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckEvidence,
    RegionResourceRuntimeAdoptionKind,
)


REGION_RESOURCE_A2_EVIDENCE_BUNDLE_SCHEMA = (
    "d4-region-resource-a2-evidence-bundle-v1"
)
REGION_RESOURCE_A2_RUNTIME_CHAIN_SCHEMA = (
    "d4-region-resource-a2-runtime-chain-v1"
)
REGION_RESOURCE_A2_PHYSICAL_WINDOW_SCHEMA = (
    "d4-region-resource-a2-physical-window-v1"
)
REGION_RESOURCE_A2_R0_REFERENCE_SCHEMA = (
    "d4-region-resource-a2-r0-reference-v1"
)
REGION_RESOURCE_A2_PAIRED_RESULT_SCHEMA = (
    "d4-region-resource-a2-paired-nondegradation-v1"
)
REGION_RESOURCE_A2_MINIMUM_CONFIDENCE = 0.60
REGION_RESOURCE_A2_RESERVED_SEEDS = tuple(range(1000, 1020))

D6_A2_EXTERNAL_AUDIT_SCHEMA = "d6.d4-a2-external-audit.v1"
D6_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA = (
    "d6.d4-a2-external-audit-consumer.v1"
)
D6_A2_FORMAL_PROFILE = "d6.d4-a2-formal-pre-admission.v1"
D6_IMPLEMENTATION_EVIDENCE_SCHEMA = (
    "d6.learning-module-implementation-evidence.v1"
)
D6_FORMAL_SCOPE_AUDIT_SCHEMA = (
    "d6.learning-scope-formal-evidence-audit.v1"
)

MANIFEST_FILENAME = "manifest.json"
CHECKSUMS_FILENAME = "SHA256SUMS"
SOURCE_DIRECTORY = "source"
EVIDENCE_DIRECTORY = "evidence"
SOURCE_MANIFEST_FILENAME = f"{SOURCE_DIRECTORY}/manifest.json"
SOURCE_WEIGHTS_FILENAME = f"{SOURCE_DIRECTORY}/state_dict.pt"
SOURCE_TRAINING_MANIFEST_FILENAME = (
    f"{SOURCE_DIRECTORY}/training_dataset_manifest.json"
)
IMPLEMENTATION_EVIDENCE_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/implementation_evidence.json"
)
D6_EXTERNAL_AUDIT_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/d6_external_audit.json"
)
FORMAL_SCOPE_AUDIT_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/learning_scope_formal_audit.json"
)
FORMAL_SCOPE_CHECKSUMS_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/formal_scope_SHA256SUMS"
)
RUNTIME_CHAIN_EVIDENCE_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/runtime_chain_evidence.json"
)

_BUNDLE_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        SOURCE_MANIFEST_FILENAME,
        SOURCE_WEIGHTS_FILENAME,
        SOURCE_TRAINING_MANIFEST_FILENAME,
        IMPLEMENTATION_EVIDENCE_FILENAME,
        D6_EXTERNAL_AUDIT_FILENAME,
        FORMAL_SCOPE_AUDIT_FILENAME,
        FORMAL_SCOPE_CHECKSUMS_FILENAME,
        RUNTIME_CHAIN_EVIDENCE_FILENAME,
    }
)
_ALL_BUNDLE_FILES = _BUNDLE_FILES | {CHECKSUMS_FILENAME}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

_D4_IMPLEMENTATION_FILES = (
    "canonical_seed_split.py",
    "coalition_safety.py",
    "communication_causal_evidence.py",
    "region_resource.py",
    "region_resource_a2_benefit_audit.py",
    "region_resource_dataset.py",
    "region_resource_isolated_rollout.py",
    "region_resource_learning.py",
    "region_resource_paired_intervention.py",
    "region_resource_reward_evidence.py",
    "region_resource_runtime_ack.py",
    "region_resource_safe_adoption.py",
    "region_resource_training.py",
    "regional_failover.py",
)

_D6_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_evidence",
        "audit_id",
        "audit_passed",
        "authority",
        "availability_policy",
        "blocker_codes",
        "blocker_details",
        "candidate",
        "consumer_contract",
        "content_sha256",
        "evaluated_at_utc",
        "evidence_audit_only",
        "fail_closed",
        "formal_profile_version",
        "formal_scope",
        "frozen_thresholds",
        "implementation",
        "role",
        "schema_version",
        "status",
        "variant",
    }
)
_D6_AUTHORITY_FIELDS = frozenset(
    {
        "model_promotion_granted",
        "assist_granted",
        "assignment_authority_granted",
        "failover_authority_granted",
        "control_authority_granted",
        "default_path_change_granted",
        "reason",
    }
)
_D6_CONSUMER_FIELDS = frozenset(
    {
        "schema_version",
        "role",
        "variant",
        "formal_profile_version",
        "adoption_evidence_kind",
        "adoption_source_metric",
        "candidate_fingerprint",
        "dataset_manifest_sha256",
        "dataset_content_sha256",
        "dataset_split_sha256",
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "implementation_sha256",
        "source_git_commit",
        "formal_scope_audit_sha256",
        "formal_scope_checksums_sha256",
        "formal_scope_checksum_verified",
        "unseen_seed_count",
        "formal_episode_count",
        "actual_adoption_count",
        "physical_window_count",
        "unique_r0_pair_count",
        "paired_non_degraded_count",
        "safety_hard_constraint_passed",
        "formal_scope_audit_passed",
        "field_availability",
        "d6_external_audit_passed",
        "failure_reasons",
    }
)
_D6_CONSUMER_EVIDENCE_FIELDS = _D6_CONSUMER_FIELDS - {
    "schema_version",
    "role",
    "variant",
    "formal_profile_version",
    "field_availability",
    "d6_external_audit_passed",
    "failure_reasons",
}

_RUNTIME_CHAIN_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_fingerprint",
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "implementation_sha256",
        "source_git_commit",
        "formal_scope_audit_sha256",
        "formal_scope_checksums_sha256",
        "formal_profile_version",
        "minimum_confidence",
        "seed_values",
        "records",
        "summary",
        "permissions",
        "content_sha256",
    }
)
_RUNTIME_RECORD_FIELDS = frozenset(
    {
        "seed",
        "scenario_id",
        "scale",
        "comparison_key",
        "candidate_fingerprint",
        "advisory",
        "authority_bindings",
        "d3_successor_plan",
        "runtime_ack",
        "physical_window",
        "same_key_r0",
        "paired_non_degradation",
        "coalition_integrity",
        "safety",
    }
)
_ADVISORY_FIELDS = frozenset(
    {
        "schema",
        "advisory_id",
        "advisory_version",
        "payload_sha256",
        "model_state_sha256",
        "candidate_confidence",
        "minimum_confidence",
        "requested_mode",
        "effective_mode",
        "projected",
        "actual_safe_adoption",
        "rule_fallback_used",
        "nominal_rule_arm_used",
        "active_risk_rule_arm_used",
        "source_plan_id",
        "source_plan_version",
    }
)
_AUTHORITY_BINDING_FIELDS = frozenset(
    {
        "region_id",
        "owner_layer",
        "owner_node_id",
        "authority_epoch",
        "fault_generation",
        "lease_expires_at_s",
        "evidence_timestamp_s",
    }
)
_D3_SUCCESSOR_FIELDS = frozenset(
    {
        "schema_version",
        "plan_id",
        "plan_version",
        "previous_plan_id",
        "previous_plan_version",
        "created_at_s",
        "valid_until_s",
        "payload_sha256",
        "accepted",
        "regional_hint_applied",
        "stale_version_rejected",
        "source_advisory_id",
        "source_advisory_version",
        "source_advisory_payload_sha256",
    }
)
_RUNTIME_ACK_WRAPPER_FIELDS = frozenset({"payload", "payload_sha256"})
_PHYSICAL_WINDOW_FIELDS = frozenset(
    {
        "schema",
        "window_id",
        "available",
        "window_start_s",
        "window_end_s",
        "advisory_id",
        "advisory_version",
        "applied_plan_id",
        "applied_plan_version",
        "runtime_ack_sha256",
        "source_snapshot_payload_sha256",
        "outcome_snapshot_payload_sha256",
        "physical_execution_observed",
        "hard_constraint_violation_count",
    }
)
_R0_FIELDS = frozenset(
    {
        "schema",
        "cell_id",
        "comparison_key",
        "unique_reference",
        "physical_window_available",
        "physical_window_payload_sha256",
        "rule_policy_name",
        "rule_policy_version",
    }
)
_PAIRED_FIELDS = frozenset(
    {
        "schema",
        "available",
        "candidate_window_id",
        "r0_cell_id",
        "non_degraded",
        "hard_constraint_non_degraded",
        "required_metric_results",
    }
)
_COALITION_FIELDS = frozenset(
    {
        "commit_state",
        "commit_state_sha256",
        "member_acks",
        "member_acks_sha256",
        "fault_generation",
        "complete",
    }
)
_SAFETY_FIELDS = frozenset(
    {
        "hard_constraint_violation_count",
        "online_truth_use_count",
        "global_track_id_rewrite_count",
        "rule_fallback_available",
        "coalition_integrity_passed",
    }
)
_SUMMARY_FIELDS = frozenset(
    {
        "episode_count",
        "actual_safe_adoption_count",
        "strict_successor_plan_count",
        "runtime_ack_count",
        "physical_window_count",
        "unique_r0_count",
        "paired_non_degraded_count",
        "hard_constraint_violation_count",
        "coalition_integrity_pass_count",
    }
)
_PERMISSION_FIELDS = frozenset(
    {
        "a2_assist_eligible_requested",
        "default_model",
        "ppo_enabled",
        "model_promotion",
        "failover_authority",
        "assignment_authority",
        "control_authority",
        "rule_fallback_required",
    }
)


class RegionResourceA2EvidenceError(ValueError):
    """Stable rejection from A2 assembly or strict loading."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class RegionResourceA2EvidenceInputs:
    """Caller-frozen inputs for one immutable A2 evidence assembly."""

    development_bundle_dir: Path
    expected_development_manifest_sha256: str
    expected_development_weights_sha256: str
    expected_development_training_manifest_sha256: str
    implementation_evidence_path: Path
    expected_implementation_evidence_sha256: str
    d6_external_audit_path: Path
    expected_d6_external_audit_sha256: str
    formal_scope_audit_path: Path
    expected_formal_scope_audit_sha256: str
    formal_scope_checksums_path: Path
    expected_formal_scope_checksums_sha256: str
    runtime_chain_evidence_path: Path
    expected_runtime_chain_evidence_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "development_bundle_dir",
            "implementation_evidence_path",
            "d6_external_audit_path",
            "formal_scope_audit_path",
            "formal_scope_checksums_path",
            "runtime_chain_evidence_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise RegionResourceA2EvidenceError(
                    "input_path_type_invalid", name
                )
            object.__setattr__(self, name, value.expanduser().resolve())
        for name in (
            "expected_development_manifest_sha256",
            "expected_development_weights_sha256",
            "expected_development_training_manifest_sha256",
            "expected_implementation_evidence_sha256",
            "expected_d6_external_audit_sha256",
            "expected_formal_scope_audit_sha256",
            "expected_formal_scope_checksums_sha256",
            "expected_runtime_chain_evidence_sha256",
        ):
            _strict_sha256(getattr(self, name), f"inputs.{name}")


@dataclass(frozen=True, slots=True)
class RegionResourceA2AssemblyResult:
    """Identity and deliberately limited permissions of one assembled bundle."""

    bundle_dir: Path
    bundle_manifest_sha256: str
    candidate_fingerprint: str
    source_model_state_sha256: str
    implementation_sha256: str
    a2_assist_eligible: bool = True
    default_model: bool = False
    ppo_enabled: bool = False
    failover_authority: bool = False
    assignment_authority: bool = False
    control_authority: bool = False
    rule_fallback_required: bool = True

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "bundle_dir": str(self.bundle_dir),
                "bundle_manifest_sha256": self.bundle_manifest_sha256,
                "candidate_fingerprint": self.candidate_fingerprint,
                "source_model_state_sha256": (
                    self.source_model_state_sha256
                ),
                "implementation_sha256": self.implementation_sha256,
                "a2_assist_eligible": self.a2_assist_eligible,
                "default_model": self.default_model,
                "ppo_enabled": self.ppo_enabled,
                "failover_authority": self.failover_authority,
                "assignment_authority": self.assignment_authority,
                "control_authority": self.control_authority,
                "rule_fallback_required": self.rule_fallback_required,
            }
        )


@dataclass(frozen=True, slots=True)
class LoadedRegionResourceA2EvidenceBundle:
    """Strictly validated source model and its A2 assist-only admission."""

    bundle_dir: Path
    source_bundle: LoadedRegionResourceModelBundle
    candidate_fingerprint: str
    implementation_sha256: str
    source_git_commit: str
    unseen_seed_values: tuple[int, ...]
    a2_assist_eligible: bool = True
    default_model: bool = False
    ppo_enabled: bool = False
    failover_authority: bool = False
    assignment_authority: bool = False
    control_authority: bool = False
    rule_fallback_required: bool = True

    @property
    def model(self) -> Any:
        return self.source_bundle.model

    @property
    def source_manifest(self) -> RegionResourceModelManifest:
        return self.source_bundle.manifest


@dataclass(frozen=True, slots=True)
class _JsonArtifact:
    path: Path
    payload: Mapping[str, Any]
    file_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    root: Path
    manifest: RegionResourceModelManifest
    manifest_payload: Mapping[str, Any]
    manifest_sha256: str
    weights_sha256: str
    training_manifest_sha256: str
    dataset_content_sha256: str
    dataset_split_sha256: str


def assemble_region_resource_a2_evidence_bundle(
    output_bundle_dir: str | Path,
    inputs: RegionResourceA2EvidenceInputs,
) -> RegionResourceA2AssemblyResult:
    """Validate all evidence and atomically publish one assist-only bundle."""

    if not isinstance(inputs, RegionResourceA2EvidenceInputs):
        raise RegionResourceA2EvidenceError(
            "input_contract_type_invalid",
            "inputs must be RegionResourceA2EvidenceInputs",
        )
    output = Path(output_bundle_dir).expanduser().resolve()
    _validate_output_destination(output)
    _validate_output_separation(output, inputs)

    source = _preflight_development_bundle(inputs)
    audit = _read_json_artifact(
        inputs.d6_external_audit_path,
        inputs.expected_d6_external_audit_sha256,
        "d6_external_audit",
        require_internal_content=True,
    )
    _validate_d6_audit_base(audit.payload)

    implementation = _read_json_artifact(
        inputs.implementation_evidence_path,
        inputs.expected_implementation_evidence_sha256,
        "implementation_evidence",
        require_internal_content=True,
    )
    formal_scope = _read_json_artifact(
        inputs.formal_scope_audit_path,
        inputs.expected_formal_scope_audit_sha256,
        "formal_scope_audit",
        require_internal_content=False,
    )
    formal_checksums_sha256 = _validate_formal_scope_checksums(
        inputs.formal_scope_checksums_path,
        inputs.expected_formal_scope_checksums_sha256,
        formal_scope.file_sha256,
    )
    runtime_chain = _read_json_artifact(
        inputs.runtime_chain_evidence_path,
        inputs.expected_runtime_chain_evidence_sha256,
        "runtime_chain_evidence",
        require_internal_content=True,
    )

    implementation_contract = _validate_implementation_evidence(
        implementation.payload, source
    )
    candidate_fingerprint = _candidate_fingerprint(
        source, implementation_contract["implementation_sha256"]
    )
    d6_contract = _validate_positive_d6_contract(
        audit.payload,
        source=source,
        implementation=implementation_contract,
        candidate_fingerprint=candidate_fingerprint,
        formal_scope_audit_sha256=formal_scope.file_sha256,
        formal_scope_checksums_sha256=formal_checksums_sha256,
    )
    formal_index = _validate_formal_scope(
        formal_scope.payload,
        source=source,
        d6_contract=d6_contract,
    )
    _validate_runtime_chain(
        runtime_chain.payload,
        source=source,
        implementation=implementation_contract,
        d6_contract=d6_contract,
        candidate_fingerprint=candidate_fingerprint,
        formal_scope_audit_sha256=formal_scope.file_sha256,
        formal_scope_checksums_sha256=formal_checksums_sha256,
        formal_index=formal_index,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.staging-",
            dir=output.parent,
        )
    )
    try:
        _stage_bundle(
            staging,
            source=source,
            implementation=implementation,
            audit=audit,
            formal_scope=formal_scope,
            formal_scope_checksums_path=inputs.formal_scope_checksums_path,
            formal_scope_checksums_sha256=formal_checksums_sha256,
            runtime_chain=runtime_chain,
            candidate_fingerprint=candidate_fingerprint,
            implementation_contract=implementation_contract,
        )
        load_region_resource_a2_evidence_bundle(staging)
        _recheck_inputs(inputs, source)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return RegionResourceA2AssemblyResult(
        bundle_dir=output,
        bundle_manifest_sha256=_sha256_file(output / MANIFEST_FILENAME),
        candidate_fingerprint=candidate_fingerprint,
        source_model_state_sha256=source.weights_sha256,
        implementation_sha256=implementation_contract[
            "implementation_sha256"
        ],
    )


def load_region_resource_a2_evidence_bundle(
    bundle_dir: str | Path,
    *,
    map_location: Any = "cpu",
) -> LoadedRegionResourceA2EvidenceBundle:
    """Strictly revalidate an assembled A2 bundle before loading its model."""

    root = Path(bundle_dir).expanduser().resolve()
    if not root.is_dir():
        raise RegionResourceA2EvidenceError("bundle_missing", str(root))
    _reject_symlinks(root)
    checksums = _read_bundle_checksums(root / CHECKSUMS_FILENAME)
    if set(checksums) != _BUNDLE_FILES:
        raise RegionResourceA2EvidenceError(
            "bundle_checksum_inventory_mismatch",
            _set_difference_text(set(checksums), _BUNDLE_FILES),
        )
    inventory = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if inventory != _ALL_BUNDLE_FILES:
        raise RegionResourceA2EvidenceError(
            "bundle_file_inventory_mismatch",
            _set_difference_text(inventory, _ALL_BUNDLE_FILES),
        )
    for filename, expected in checksums.items():
        actual = _sha256_file(root / filename)
        if actual != expected:
            raise RegionResourceA2EvidenceError(
                f"bundle_sha256_mismatch.{filename}",
                f"expected {expected}, received {actual}",
            )

    manifest_artifact = _read_json_artifact(
        root / MANIFEST_FILENAME,
        checksums[MANIFEST_FILENAME],
        "assembled_manifest",
        require_internal_content=True,
    )
    manifest = manifest_artifact.payload
    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "bundle_id",
            "candidate",
            "source_development_bundle",
            "evidence",
            "admission",
            "content_sha256",
        },
        "assembled_manifest",
    )
    if (
        manifest.get("schema_version")
        != REGION_RESOURCE_A2_EVIDENCE_BUNDLE_SCHEMA
    ):
        raise RegionResourceA2EvidenceError(
            "assembled_manifest_schema_mismatch",
            str(manifest.get("schema_version")),
        )

    source = _load_packaged_source(root, manifest, checksums)
    evidence = _strict_mapping(manifest.get("evidence"), "manifest.evidence")
    expected_evidence_names = {
        "implementation_evidence": IMPLEMENTATION_EVIDENCE_FILENAME,
        "d6_external_audit": D6_EXTERNAL_AUDIT_FILENAME,
        "formal_scope_audit": FORMAL_SCOPE_AUDIT_FILENAME,
        "formal_scope_checksums": FORMAL_SCOPE_CHECKSUMS_FILENAME,
        "runtime_chain_evidence": RUNTIME_CHAIN_EVIDENCE_FILENAME,
    }
    if set(evidence) != set(expected_evidence_names):
        raise RegionResourceA2EvidenceError(
            "assembled_evidence_inventory_mismatch",
            _set_difference_text(set(evidence), set(expected_evidence_names)),
        )
    artifacts: dict[str, _JsonArtifact] = {}
    for name in (
        "implementation_evidence",
        "d6_external_audit",
        "formal_scope_audit",
        "runtime_chain_evidence",
    ):
        filename = expected_evidence_names[name]
        record = _validate_artifact_record(
            evidence[name],
            filename=filename,
            file_sha256=checksums[filename],
            name=f"manifest.evidence.{name}",
        )
        artifacts[name] = _read_json_artifact(
            root / filename,
            record["sha256"],
            name,
            require_internal_content=name != "formal_scope_audit",
            expected_content_sha256=record["content_sha256"],
        )
    checksum_record = _strict_mapping(
        evidence["formal_scope_checksums"],
        "manifest.evidence.formal_scope_checksums",
    )
    _require_exact_keys(
        checksum_record,
        {"filename", "sha256"},
        "manifest.evidence.formal_scope_checksums",
    )
    if (
        checksum_record["filename"] != FORMAL_SCOPE_CHECKSUMS_FILENAME
        or checksum_record["sha256"]
        != checksums[FORMAL_SCOPE_CHECKSUMS_FILENAME]
    ):
        raise RegionResourceA2EvidenceError(
            "formal_scope_checksums_record_mismatch",
            str(checksum_record),
        )
    formal_checksums_sha256 = _validate_formal_scope_checksums(
        root / FORMAL_SCOPE_CHECKSUMS_FILENAME,
        checksums[FORMAL_SCOPE_CHECKSUMS_FILENAME],
        artifacts["formal_scope_audit"].file_sha256,
    )

    _validate_d6_audit_base(artifacts["d6_external_audit"].payload)
    implementation_contract = _validate_implementation_evidence(
        artifacts["implementation_evidence"].payload, source
    )
    candidate_fingerprint = _candidate_fingerprint(
        source, implementation_contract["implementation_sha256"]
    )
    d6_contract = _validate_positive_d6_contract(
        artifacts["d6_external_audit"].payload,
        source=source,
        implementation=implementation_contract,
        candidate_fingerprint=candidate_fingerprint,
        formal_scope_audit_sha256=artifacts[
            "formal_scope_audit"
        ].file_sha256,
        formal_scope_checksums_sha256=formal_checksums_sha256,
    )
    formal_index = _validate_formal_scope(
        artifacts["formal_scope_audit"].payload,
        source=source,
        d6_contract=d6_contract,
    )
    _validate_runtime_chain(
        artifacts["runtime_chain_evidence"].payload,
        source=source,
        implementation=implementation_contract,
        d6_contract=d6_contract,
        candidate_fingerprint=candidate_fingerprint,
        formal_scope_audit_sha256=artifacts[
            "formal_scope_audit"
        ].file_sha256,
        formal_scope_checksums_sha256=formal_checksums_sha256,
        formal_index=formal_index,
    )
    _validate_assembled_manifest_semantics(
        manifest,
        source=source,
        implementation=implementation_contract,
        candidate_fingerprint=candidate_fingerprint,
        evidence=artifacts,
        formal_scope_checksums_sha256=formal_checksums_sha256,
    )

    try:
        loaded_source = load_region_resource_model_bundle(
            root / SOURCE_DIRECTORY,
            expected_model_version=source.manifest.model_version,
            expected_state_dict_sha256=source.weights_sha256,
            map_location=map_location,
            require_training_dataset_manifest=True,
        )
    except ModelBundleValidationError as exc:
        raise RegionResourceA2EvidenceError(
            "source_bundle_strict_load_failed", str(exc)
        ) from exc
    return LoadedRegionResourceA2EvidenceBundle(
        bundle_dir=root,
        source_bundle=loaded_source,
        candidate_fingerprint=candidate_fingerprint,
        implementation_sha256=implementation_contract[
            "implementation_sha256"
        ],
        source_git_commit=implementation_contract["source_git_commit"],
        unseen_seed_values=REGION_RESOURCE_A2_RESERVED_SEEDS,
    )


def _preflight_development_bundle(
    inputs: RegionResourceA2EvidenceInputs,
) -> _SourceIdentity:
    root = inputs.development_bundle_dir
    if not root.is_dir():
        raise RegionResourceA2EvidenceError(
            "development_bundle_missing", str(root)
        )
    manifest_path = root / "manifest.json"
    weights_path = root / "state_dict.pt"
    training_path = root / "training_dataset_manifest.json"
    expected = {
        manifest_path: inputs.expected_development_manifest_sha256,
        weights_path: inputs.expected_development_weights_sha256,
        training_path: (
            inputs.expected_development_training_manifest_sha256
        ),
    }
    for path, expected_sha in expected.items():
        if not path.is_file():
            raise RegionResourceA2EvidenceError(
                "development_bundle_file_missing", str(path)
            )
        actual = _sha256_file(path)
        if actual != expected_sha:
            raise RegionResourceA2EvidenceError(
                f"development_bundle_sha256_mismatch.{path.name}",
                f"expected {expected_sha}, received {actual}",
            )
    payload = _read_json(manifest_path, "development_manifest")
    try:
        manifest = RegionResourceModelManifest.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceA2EvidenceError(
            "development_manifest_invalid", str(exc)
        ) from exc
    if (
        manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        or manifest.final_holdout_seed_count != 0
        or manifest.assist_admitted
    ):
        raise RegionResourceA2EvidenceError(
            "development_boundary_crossed",
            "source bundle must remain development/shadow only",
        )
    if (
        manifest.state_dict_file != "state_dict.pt"
        or manifest.state_dict_sha256
        != inputs.expected_development_weights_sha256
    ):
        raise RegionResourceA2EvidenceError(
            "development_weights_binding_mismatch",
            manifest.state_dict_file,
        )
    if (
        manifest.training_dataset_available is not True
        or manifest.training_manifest_file
        != "training_dataset_manifest.json"
        or manifest.training_manifest_sha256
        != inputs.expected_development_training_manifest_sha256
        or manifest.training_dataset_sha256 is None
        or manifest.training_split_sha256 is None
    ):
        raise RegionResourceA2EvidenceError(
            "development_training_binding_incomplete",
            "A2 evidence requires the source training manifest",
        )
    return _SourceIdentity(
        root=root,
        manifest=manifest,
        manifest_payload=MappingProxyType(payload),
        manifest_sha256=inputs.expected_development_manifest_sha256,
        weights_sha256=inputs.expected_development_weights_sha256,
        training_manifest_sha256=(
            inputs.expected_development_training_manifest_sha256
        ),
        dataset_content_sha256=_strict_sha256(
            manifest.training_dataset_sha256,
            "development_manifest.training_dataset_sha256",
        ),
        dataset_split_sha256=_strict_sha256(
            manifest.training_split_sha256,
            "development_manifest.training_split_sha256",
        ),
    )


def _load_packaged_source(
    root: Path,
    manifest: Mapping[str, Any],
    checksums: Mapping[str, str],
) -> _SourceIdentity:
    record = _strict_mapping(
        manifest.get("source_development_bundle"),
        "manifest.source_development_bundle",
    )
    _require_exact_keys(
        record,
        {
            "schema",
            "manifest",
            "weights",
            "training_manifest",
            "lifecycle_stage",
            "maximum_advisor_mode",
        },
        "manifest.source_development_bundle",
    )
    if (
        record.get("schema") != "d4-region-resource-model-bundle-v2"
        or record.get("lifecycle_stage") != MODEL_LIFECYCLE_DEVELOPMENT
        or record.get("maximum_advisor_mode") != MODEL_MAXIMUM_MODE_SHADOW
    ):
        raise RegionResourceA2EvidenceError(
            "packaged_source_boundary_invalid", str(record)
        )
    manifest_record = _validate_source_record(
        record["manifest"],
        filename=SOURCE_MANIFEST_FILENAME,
        expected_sha256=checksums[SOURCE_MANIFEST_FILENAME],
        name="source_development_bundle.manifest",
    )
    weights_record = _validate_source_record(
        record["weights"],
        filename=SOURCE_WEIGHTS_FILENAME,
        expected_sha256=checksums[SOURCE_WEIGHTS_FILENAME],
        name="source_development_bundle.weights",
    )
    training_record = _validate_source_record(
        record["training_manifest"],
        filename=SOURCE_TRAINING_MANIFEST_FILENAME,
        expected_sha256=checksums[SOURCE_TRAINING_MANIFEST_FILENAME],
        name="source_development_bundle.training_manifest",
    )
    payload = _read_json(
        root / SOURCE_MANIFEST_FILENAME, "packaged_source_manifest"
    )
    try:
        source_manifest = RegionResourceModelManifest.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceA2EvidenceError(
            "packaged_source_manifest_invalid", str(exc)
        ) from exc
    if (
        source_manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or source_manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        or source_manifest.final_holdout_seed_count != 0
        or source_manifest.assist_admitted
    ):
        raise RegionResourceA2EvidenceError(
            "packaged_source_boundary_crossed",
            "source model must remain development/shadow",
        )
    if (
        source_manifest.state_dict_sha256 != weights_record["sha256"]
        or source_manifest.training_manifest_sha256
        != training_record["sha256"]
        or source_manifest.training_dataset_available is not True
        or source_manifest.training_dataset_sha256 is None
        or source_manifest.training_split_sha256 is None
    ):
        raise RegionResourceA2EvidenceError(
            "packaged_source_cross_binding_mismatch",
            "source manifest does not bind weights and training manifest",
        )
    return _SourceIdentity(
        root=root / SOURCE_DIRECTORY,
        manifest=source_manifest,
        manifest_payload=MappingProxyType(payload),
        manifest_sha256=manifest_record["sha256"],
        weights_sha256=weights_record["sha256"],
        training_manifest_sha256=training_record["sha256"],
        dataset_content_sha256=_strict_sha256(
            source_manifest.training_dataset_sha256,
            "packaged_source.training_dataset_sha256",
        ),
        dataset_split_sha256=_strict_sha256(
            source_manifest.training_split_sha256,
            "packaged_source.training_split_sha256",
        ),
    )


def _validate_implementation_evidence(
    payload: Mapping[str, Any],
    source: _SourceIdentity,
) -> Mapping[str, Any]:
    expected_fields = {
        "schema_version",
        "role",
        "source_git_commit",
        "source_files",
        "implementation_sha256",
        "dataset_manifest_sha256",
        "dataset_content_sha256",
        "dataset_split_sha256",
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "content_sha256",
    }
    _require_exact_keys(payload, expected_fields, "implementation_evidence")
    if (
        payload.get("schema_version")
        != D6_IMPLEMENTATION_EVIDENCE_SCHEMA
        or payload.get("role") != "D4_A2"
    ):
        raise RegionResourceA2EvidenceError(
            "implementation_evidence_identity_mismatch",
            f"{payload.get('schema_version')}:{payload.get('role')}",
        )
    source_commit = payload.get("source_git_commit")
    if (
        not isinstance(source_commit, str)
        or _GIT_COMMIT_RE.fullmatch(source_commit) is None
    ):
        raise RegionResourceA2EvidenceError(
            "implementation_source_commit_invalid", str(source_commit)
        )
    source_files = _strict_mapping(
        payload.get("source_files"), "implementation_evidence.source_files"
    )
    if set(source_files) != set(_D4_IMPLEMENTATION_FILES):
        raise RegionResourceA2EvidenceError(
            "implementation_source_inventory_mismatch",
            _set_difference_text(
                set(source_files), set(_D4_IMPLEMENTATION_FILES)
            ),
        )
    normalized_files = {
        name: _strict_sha256(
            source_files[name], f"implementation_evidence.source_files.{name}"
        )
        for name in sorted(source_files)
    }
    implementation_sha256 = _sha256_json(normalized_files)
    if payload.get("implementation_sha256") != implementation_sha256:
        raise RegionResourceA2EvidenceError(
            "implementation_aggregate_sha256_mismatch",
            f"{payload.get('implementation_sha256')}!={implementation_sha256}",
        )
    current_files = _current_implementation_files()
    if normalized_files != current_files:
        changed = sorted(
            name
            for name in normalized_files
            if normalized_files.get(name) != current_files.get(name)
        )
        raise RegionResourceA2EvidenceError(
            "implementation_lineage_stale", ",".join(changed)
        )
    current_implementation_sha256 = _sha256_json(current_files)
    if implementation_sha256 != current_implementation_sha256:
        raise RegionResourceA2EvidenceError(
            "current_implementation_sha256_mismatch",
            current_implementation_sha256,
        )
    expected_candidate = {
        "dataset_manifest_sha256": source.training_manifest_sha256,
        "dataset_content_sha256": source.dataset_content_sha256,
        "dataset_split_sha256": source.dataset_split_sha256,
        "bundle_manifest_sha256": source.manifest_sha256,
        "bundle_weights_sha256": source.weights_sha256,
    }
    for name, expected in expected_candidate.items():
        if payload.get(name) != expected:
            raise RegionResourceA2EvidenceError(
                f"implementation_candidate_binding_mismatch.{name}",
                f"expected {expected}, received {payload.get(name)}",
            )
    return MappingProxyType(
        {
            "implementation_sha256": implementation_sha256,
            "source_git_commit": source_commit,
            **expected_candidate,
        }
    )


def _validate_d6_audit_base(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, _D6_TOP_LEVEL_FIELDS, "d6_external_audit")
    if payload.get("schema_version") != D6_A2_EXTERNAL_AUDIT_SCHEMA:
        raise RegionResourceA2EvidenceError(
            "d6_external_audit_schema_mismatch",
            str(payload.get("schema_version")),
        )
    if (
        payload.get("role") != "D4_A2"
        or payload.get("variant") != "A2"
        or payload.get("formal_profile_version") != D6_A2_FORMAL_PROFILE
        or payload.get("evidence_audit_only") is not True
    ):
        raise RegionResourceA2EvidenceError(
            "d6_external_audit_identity_mismatch",
            f"{payload.get('role')}:{payload.get('variant')}",
        )
    authority = _strict_mapping(
        payload.get("authority"), "d6_external_audit.authority"
    )
    _require_exact_keys(
        authority, _D6_AUTHORITY_FIELDS, "d6_external_audit.authority"
    )
    for name in _D6_AUTHORITY_FIELDS - {"reason"}:
        if authority.get(name) is not False:
            raise RegionResourceA2EvidenceError(
                f"d6_authority_not_closed.{name}", str(authority.get(name))
            )
    if not isinstance(authority.get("reason"), str) or not authority["reason"]:
        raise RegionResourceA2EvidenceError(
            "d6_authority_reason_invalid", str(authority.get("reason"))
        )
    if (
        payload.get("audit_passed") is not True
        or payload.get("status") != "pass"
        or payload.get("fail_closed") is not False
        or payload.get("blocker_codes") not in ([], ())
    ):
        blockers = payload.get("blocker_codes")
        raise RegionResourceA2EvidenceError(
            "d6_external_audit_fail_closed",
            ",".join(str(item) for item in blockers or ("audit_not_passed",)),
        )


def _validate_positive_d6_contract(
    payload: Mapping[str, Any],
    *,
    source: _SourceIdentity,
    implementation: Mapping[str, Any],
    candidate_fingerprint: str,
    formal_scope_audit_sha256: str,
    formal_scope_checksums_sha256: str,
) -> Mapping[str, Any]:
    contract = _strict_mapping(
        payload.get("consumer_contract"),
        "d6_external_audit.consumer_contract",
    )
    _require_exact_keys(
        contract, _D6_CONSUMER_FIELDS, "d6_external_audit.consumer_contract"
    )
    if (
        contract.get("schema_version")
        != D6_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA
        or contract.get("role") != "D4_A2"
        or contract.get("variant") != "A2"
        or contract.get("formal_profile_version") != D6_A2_FORMAL_PROFILE
        or contract.get("adoption_evidence_kind") != "runtime_ack"
        or contract.get("adoption_source_metric")
        != "d4_advice_control_adoption_count"
        or contract.get("d6_external_audit_passed") is not True
        or contract.get("failure_reasons") not in ([], ())
    ):
        raise RegionResourceA2EvidenceError(
            "d6_consumer_identity_or_state_invalid", str(contract)
        )
    expected = {
        "candidate_fingerprint": candidate_fingerprint,
        "dataset_manifest_sha256": source.training_manifest_sha256,
        "dataset_content_sha256": source.dataset_content_sha256,
        "dataset_split_sha256": source.dataset_split_sha256,
        "bundle_manifest_sha256": source.manifest_sha256,
        "bundle_weights_sha256": source.weights_sha256,
        "implementation_sha256": implementation["implementation_sha256"],
        "source_git_commit": implementation["source_git_commit"],
        "formal_scope_audit_sha256": formal_scope_audit_sha256,
        "formal_scope_checksums_sha256": formal_scope_checksums_sha256,
        "formal_scope_checksum_verified": True,
        "unseen_seed_count": 20,
        "formal_episode_count": 20,
        "actual_adoption_count": 20,
        "physical_window_count": 20,
        "unique_r0_pair_count": 20,
        "paired_non_degraded_count": 20,
        "safety_hard_constraint_passed": True,
        "formal_scope_audit_passed": True,
    }
    for name, expected_value in expected.items():
        if contract.get(name) != expected_value:
            raise RegionResourceA2EvidenceError(
                f"d6_consumer_cross_binding_mismatch.{name}",
                f"expected {expected_value}, received {contract.get(name)}",
            )
    availability = _strict_mapping(
        contract.get("field_availability"),
        "d6_external_audit.consumer_contract.field_availability",
    )
    if set(availability) != _D6_CONSUMER_EVIDENCE_FIELDS:
        raise RegionResourceA2EvidenceError(
            "d6_field_availability_inventory_mismatch",
            _set_difference_text(
                set(availability), _D6_CONSUMER_EVIDENCE_FIELDS
            ),
        )
    for name in sorted(_D6_CONSUMER_EVIDENCE_FIELDS):
        record = _strict_mapping(
            availability[name],
            f"d6_external_audit.field_availability.{name}",
        )
        _require_exact_keys(
            record,
            {"availability", "unavailable_reason", "value"},
            f"d6_external_audit.field_availability.{name}",
        )
        if (
            record.get("availability") != "available"
            or record.get("unavailable_reason") is not None
            or record.get("value") != contract[name]
        ):
            raise RegionResourceA2EvidenceError(
                f"d6_field_unavailable_or_inconsistent.{name}", str(record)
            )
    candidate = _strict_mapping(
        payload.get("candidate"), "d6_external_audit.candidate"
    )
    if (
        candidate.get("candidate_lifecycle") != "development"
        or candidate.get("candidate_maximum_mode") != "shadow"
    ):
        raise RegionResourceA2EvidenceError(
            "d6_candidate_boundary_invalid", str(candidate)
        )
    for name in (
        "dataset_manifest_sha256",
        "dataset_content_sha256",
        "dataset_split_sha256",
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
    ):
        if candidate.get(name) != expected[name]:
            raise RegionResourceA2EvidenceError(
                f"d6_candidate_cross_binding_mismatch.{name}",
                str(candidate.get(name)),
            )
    implementation_record = _strict_mapping(
        payload.get("implementation"), "d6_external_audit.implementation"
    )
    if (
        implementation_record.get("available") is not True
        or implementation_record.get("lineage_verified") is not True
        or implementation_record.get("evidence_implementation_sha256")
        != implementation["implementation_sha256"]
        or implementation_record.get("current_implementation_sha256")
        != implementation["implementation_sha256"]
        or implementation_record.get("source_git_commit")
        != implementation["source_git_commit"]
    ):
        raise RegionResourceA2EvidenceError(
            "d6_implementation_lineage_invalid",
            str(implementation_record),
        )
    formal = _strict_mapping(
        payload.get("formal_scope"), "d6_external_audit.formal_scope"
    )
    formal_expected = {
        "available": True,
        "audit_passed": True,
        "checksums_verified": True,
        "audit_file_sha256": formal_scope_audit_sha256,
        "checksums_file_sha256": formal_scope_checksums_sha256,
        "unseen_seed_count": 20,
        "formal_episode_count": 20,
        "actual_adoption_count": 20,
        "physical_window_count": 20,
        "unique_r0_pair_count": 20,
        "paired_non_degraded_count": 20,
        "safety_hard_constraint_passed": True,
        "source_git_commit": implementation["source_git_commit"],
    }
    for name, expected_value in formal_expected.items():
        if formal.get(name) != expected_value:
            raise RegionResourceA2EvidenceError(
                f"d6_formal_scope_cross_binding_mismatch.{name}",
                f"expected {expected_value}, received {formal.get(name)}",
            )
    return MappingProxyType(dict(contract))


def _validate_formal_scope(
    payload: Mapping[str, Any],
    *,
    source: _SourceIdentity,
    d6_contract: Mapping[str, Any],
) -> Mapping[str, Mapping[str, Any]]:
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "verdict",
            "fail_closed",
            "formal_evidence_eligible",
            "evidence_admission_allowed",
            "model_promotion",
            "default_control_path_modified",
            "learned_scope",
            "r0_scopes",
            "r0_pairing",
            "blockers",
        },
        "formal_scope_audit",
    )
    if (
        payload.get("schema_version") != D6_FORMAL_SCOPE_AUDIT_SCHEMA
        or payload.get("verdict") != "pass"
        or payload.get("fail_closed") is not False
        or payload.get("formal_evidence_eligible") is not True
        or payload.get("evidence_admission_allowed") is not True
        or payload.get("default_control_path_modified") is not False
        or payload.get("blockers") not in ([], ())
    ):
        raise RegionResourceA2EvidenceError(
            "formal_scope_state_invalid", str(payload)
        )
    promotion = _strict_mapping(
        payload.get("model_promotion"), "formal_scope.model_promotion"
    )
    if (
        promotion.get("allowed") is not False
        or promotion.get("availability") != "unavailable"
    ):
        raise RegionResourceA2EvidenceError(
            "formal_scope_model_promotion_open", str(promotion)
        )
    learned = _strict_mapping(
        payload.get("learned_scope"), "formal_scope.learned_scope"
    )
    if (
        learned.get("source_git_commit")
        != d6_contract["source_git_commit"]
        or learned.get("scope_variants") != ["A2"]
        or learned.get("expected_cell_count") != 20
        or learned.get("accepted_cell_count") != 20
        or learned.get("formal_evidence_eligible") is not True
        or learned.get("bundle_binding_status") != "available_and_valid"
        or learned.get("scope_completeness_status") != "complete"
        or learned.get("blockers") not in ([], ())
    ):
        raise RegionResourceA2EvidenceError(
            "formal_learned_scope_invalid", str(learned)
        )
    binding = _strict_mapping(
        learned.get("bundle_binding"), "formal_scope.bundle_binding"
    )
    components = _strict_mapping(
        binding.get("components"), "formal_scope.bundle_binding.components"
    )
    if set(components) != {"d4"}:
        raise RegionResourceA2EvidenceError(
            "formal_bundle_component_inventory_mismatch",
            str(sorted(components)),
        )
    component = _strict_mapping(
        components["d4"], "formal_scope.bundle_binding.components.d4"
    )
    actual = _strict_mapping(
        component.get("actual"),
        "formal_scope.bundle_binding.components.d4.actual",
    )
    if (
        component.get("available") is not True
        or component.get("manifest_sha256_match") is not True
        or component.get("tree_sha256_match") is not True
        or component.get("file_count_match") is not True
        or component.get("total_size_bytes_match") is not True
        or actual.get("manifest_sha256") != source.manifest_sha256
    ):
        raise RegionResourceA2EvidenceError(
            "formal_bundle_binding_invalid", str(component)
        )

    raw_cells = _strict_sequence(
        learned.get("cells"), "formal_scope.learned_scope.cells"
    )
    if len(raw_cells) != 20:
        raise RegionResourceA2EvidenceError(
            "formal_learned_cell_count_mismatch", str(len(raw_cells))
        )
    learned_by_key: dict[str, Mapping[str, Any]] = {}
    seeds: set[int] = set()
    for index, value in enumerate(raw_cells):
        cell = _strict_mapping(value, f"formal_scope.learned.cells[{index}]")
        seed = _strict_nonnegative_int(
            cell.get("seed"), f"formal_scope.learned.cells[{index}].seed"
        )
        comparison_key = _strict_text(
            cell.get("comparison_key"),
            f"formal_scope.learned.cells[{index}].comparison_key",
        )
        learning_evidence = _strict_mapping(
            cell.get("learning_evidence"),
            f"formal_scope.learned.cells[{index}].learning_evidence",
        )
        if (
            cell.get("variant") != "A2"
            or cell.get("evidence_status") != "accepted"
            or cell.get("assist_adoption_status")
            != "actual_assist_adopted"
            or cell.get("online_truth_status") != "zero_verified"
            or cell.get("physical_result_status") != "available"
            or cell.get("failure_reasons") not in ([], ())
            or learning_evidence.get("status")
            != "preflight_and_episode_consistent"
            or learning_evidence.get("required_components") != ["d4"]
        ):
            raise RegionResourceA2EvidenceError(
                "formal_learned_cell_invalid", f"{index}:{cell}"
            )
        if comparison_key in learned_by_key or seed in seeds:
            raise RegionResourceA2EvidenceError(
                "formal_learned_cell_duplicate",
                f"{comparison_key}:{seed}",
            )
        learned_by_key[comparison_key] = cell
        seeds.add(seed)
    if tuple(sorted(seeds)) != REGION_RESOURCE_A2_RESERVED_SEEDS:
        raise RegionResourceA2EvidenceError(
            "formal_unseen_seed_catalog_mismatch", str(sorted(seeds))
        )

    r0_by_key: dict[str, Mapping[str, Any]] = {}
    for scope_index, scope_value in enumerate(
        _strict_sequence(
            payload.get("r0_scopes"), "formal_scope.r0_scopes"
        )
    ):
        scope = _strict_mapping(
            scope_value, f"formal_scope.r0_scopes[{scope_index}]"
        )
        if scope.get("blockers") not in ([], ()):
            raise RegionResourceA2EvidenceError(
                "formal_r0_scope_blocked", str(scope.get("blockers"))
            )
        for cell_index, value in enumerate(
            _strict_sequence(
                scope.get("cells"),
                f"formal_scope.r0_scopes[{scope_index}].cells",
            )
        ):
            cell = _strict_mapping(
                value,
                f"formal_scope.r0_scopes[{scope_index}].cells[{cell_index}]",
            )
            key = _strict_text(
                cell.get("comparison_key"), "formal_scope.r0.comparison_key"
            )
            if (
                cell.get("variant") != "R0"
                or cell.get("evidence_status") != "accepted"
                or cell.get("failure_reasons") not in ([], ())
                or key in r0_by_key
            ):
                raise RegionResourceA2EvidenceError(
                    "formal_r0_cell_invalid", str(cell)
                )
            r0_by_key[key] = cell
    if set(r0_by_key) != set(learned_by_key):
        raise RegionResourceA2EvidenceError(
            "formal_r0_key_inventory_mismatch",
            _set_difference_text(set(r0_by_key), set(learned_by_key)),
        )

    pairing = _strict_mapping(
        payload.get("r0_pairing"), "formal_scope.r0_pairing"
    )
    if (
        pairing.get("availability") != "available"
        or pairing.get("expected_pair_count") != 20
        or pairing.get("available_pair_count") != 20
        or pairing.get("non_degraded_pair_count") != 20
        or pairing.get("all_required_pairs_available") is not True
        or pairing.get("all_required_pairs_non_degraded") is not True
        or pairing.get("blockers") not in ([], ())
    ):
        raise RegionResourceA2EvidenceError(
            "formal_pairing_summary_invalid", str(pairing)
        )
    pair_by_key: dict[str, Mapping[str, Any]] = {}
    for index, value in enumerate(
        _strict_sequence(
            pairing.get("pairs"), "formal_scope.r0_pairing.pairs"
        )
    ):
        pair = _strict_mapping(
            value, f"formal_scope.r0_pairing.pairs[{index}]"
        )
        key = _strict_text(
            pair.get("comparison_key"),
            f"formal_scope.r0_pairing.pairs[{index}].comparison_key",
        )
        metrics = _strict_mapping(
            pair.get("metric_comparisons"),
            f"formal_scope.r0_pairing.pairs[{index}].metric_comparisons",
        )
        if (
            pair.get("variant") != "A2"
            or pair.get("availability") != "available"
            or pair.get("unavailable_reason") is not None
            or pair.get("non_degraded") is not True
            or pair.get("failure_reasons") not in ([], ())
            or key in pair_by_key
            or set(metrics)
            != {
                "intercepted_target_count",
                "offline_proximity_unique_target_count",
            }
            or any(
                metric.get("availability") != "available"
                or metric.get("non_degraded") is not True
                or metric.get("required") is not True
                for metric in (
                    _strict_mapping(
                        metrics[name],
                        f"formal_scope.pair.metrics.{name}",
                    )
                    for name in metrics
                )
            )
        ):
            raise RegionResourceA2EvidenceError(
                "formal_pair_record_invalid", str(pair)
            )
        if (
            pair.get("learned_cell_id")
            != learned_by_key[key].get("cell_id")
            or pair.get("r0_cell_id") != r0_by_key[key].get("cell_id")
        ):
            raise RegionResourceA2EvidenceError(
                "formal_pair_cell_binding_mismatch", key
            )
        pair_by_key[key] = pair
    if set(pair_by_key) != set(learned_by_key):
        raise RegionResourceA2EvidenceError(
            "formal_pair_key_inventory_mismatch",
            _set_difference_text(set(pair_by_key), set(learned_by_key)),
        )
    return MappingProxyType(
        {
            key: MappingProxyType(
                {
                    "learned": learned_by_key[key],
                    "r0": r0_by_key[key],
                    "pair": pair_by_key[key],
                }
            )
            for key in sorted(learned_by_key)
        }
    )


def _validate_runtime_chain(
    payload: Mapping[str, Any],
    *,
    source: _SourceIdentity,
    implementation: Mapping[str, Any],
    d6_contract: Mapping[str, Any],
    candidate_fingerprint: str,
    formal_scope_audit_sha256: str,
    formal_scope_checksums_sha256: str,
    formal_index: Mapping[str, Mapping[str, Any]],
) -> None:
    _require_exact_keys(
        payload, _RUNTIME_CHAIN_FIELDS, "runtime_chain_evidence"
    )
    expected_top = {
        "schema_version": REGION_RESOURCE_A2_RUNTIME_CHAIN_SCHEMA,
        "candidate_fingerprint": candidate_fingerprint,
        "bundle_manifest_sha256": source.manifest_sha256,
        "bundle_weights_sha256": source.weights_sha256,
        "implementation_sha256": implementation["implementation_sha256"],
        "source_git_commit": implementation["source_git_commit"],
        "formal_scope_audit_sha256": formal_scope_audit_sha256,
        "formal_scope_checksums_sha256": formal_scope_checksums_sha256,
        "formal_profile_version": D6_A2_FORMAL_PROFILE,
        "minimum_confidence": REGION_RESOURCE_A2_MINIMUM_CONFIDENCE,
        "seed_values": list(REGION_RESOURCE_A2_RESERVED_SEEDS),
    }
    for name, expected in expected_top.items():
        if payload.get(name) != expected:
            raise RegionResourceA2EvidenceError(
                f"runtime_chain_cross_binding_mismatch.{name}",
                f"expected {expected}, received {payload.get(name)}",
            )
    permissions = _strict_mapping(
        payload.get("permissions"), "runtime_chain.permissions"
    )
    _require_exact_keys(
        permissions, _PERMISSION_FIELDS, "runtime_chain.permissions"
    )
    expected_permissions = {
        "a2_assist_eligible_requested": True,
        "default_model": False,
        "ppo_enabled": False,
        "model_promotion": False,
        "failover_authority": False,
        "assignment_authority": False,
        "control_authority": False,
        "rule_fallback_required": True,
    }
    if dict(permissions) != expected_permissions:
        raise RegionResourceA2EvidenceError(
            "runtime_chain_permissions_not_closed", str(permissions)
        )
    records = _strict_sequence(
        payload.get("records"), "runtime_chain.records"
    )
    if len(records) != 20:
        raise RegionResourceA2EvidenceError(
            "runtime_chain_record_count_mismatch", str(len(records))
        )
    seen_seeds: set[int] = set()
    seen_keys: set[str] = set()
    for index, value in enumerate(records):
        record = _strict_mapping(value, f"runtime_chain.records[{index}]")
        _validate_runtime_record(
            record,
            index=index,
            source=source,
            candidate_fingerprint=candidate_fingerprint,
            formal_index=formal_index,
        )
        seed = int(record["seed"])
        key = str(record["comparison_key"])
        if seed in seen_seeds or key in seen_keys:
            raise RegionResourceA2EvidenceError(
                "runtime_chain_record_duplicate", f"{seed}:{key}"
            )
        seen_seeds.add(seed)
        seen_keys.add(key)
    if tuple(sorted(seen_seeds)) != REGION_RESOURCE_A2_RESERVED_SEEDS:
        raise RegionResourceA2EvidenceError(
            "runtime_chain_seed_catalog_mismatch", str(sorted(seen_seeds))
        )
    if seen_keys != set(formal_index):
        raise RegionResourceA2EvidenceError(
            "runtime_chain_formal_key_inventory_mismatch",
            _set_difference_text(seen_keys, set(formal_index)),
        )
    summary = _strict_mapping(
        payload.get("summary"), "runtime_chain.summary"
    )
    _require_exact_keys(summary, _SUMMARY_FIELDS, "runtime_chain.summary")
    expected_summary = {
        "episode_count": 20,
        "actual_safe_adoption_count": 20,
        "strict_successor_plan_count": 20,
        "runtime_ack_count": 20,
        "physical_window_count": 20,
        "unique_r0_count": 20,
        "paired_non_degraded_count": 20,
        "hard_constraint_violation_count": 0,
        "coalition_integrity_pass_count": 20,
    }
    if dict(summary) != expected_summary:
        raise RegionResourceA2EvidenceError(
            "runtime_chain_summary_invalid", str(summary)
        )
    for name in (
        "unseen_seed_count",
        "formal_episode_count",
        "actual_adoption_count",
        "physical_window_count",
        "unique_r0_pair_count",
        "paired_non_degraded_count",
    ):
        if d6_contract[name] != 20:
            raise RegionResourceA2EvidenceError(
                f"runtime_chain_d6_count_mismatch.{name}",
                str(d6_contract[name]),
            )


def _validate_runtime_record(
    record: Mapping[str, Any],
    *,
    index: int,
    source: _SourceIdentity,
    candidate_fingerprint: str,
    formal_index: Mapping[str, Mapping[str, Any]],
) -> None:
    context = f"runtime_chain.records[{index}]"
    _require_exact_keys(record, _RUNTIME_RECORD_FIELDS, context)
    seed = _strict_nonnegative_int(record.get("seed"), f"{context}.seed")
    if seed not in REGION_RESOURCE_A2_RESERVED_SEEDS:
        raise RegionResourceA2EvidenceError(
            "runtime_record_seed_not_reserved", str(seed)
        )
    scenario_id = _strict_text(
        record.get("scenario_id"), f"{context}.scenario_id"
    )
    scale = _strict_positive_int(record.get("scale"), f"{context}.scale")
    comparison_key = _strict_text(
        record.get("comparison_key"), f"{context}.comparison_key"
    )
    if (
        comparison_key != f"{scenario_id}|{scale}|{seed}"
        or comparison_key not in formal_index
        or record.get("candidate_fingerprint") != candidate_fingerprint
    ):
        raise RegionResourceA2EvidenceError(
            "runtime_record_identity_mismatch", comparison_key
        )
    formal_cell = formal_index[comparison_key]["learned"]
    if (
        formal_cell.get("scenario") != scenario_id
        or formal_cell.get("scale") != scale
        or formal_cell.get("seed") != seed
    ):
        raise RegionResourceA2EvidenceError(
            "runtime_record_formal_cell_mismatch", comparison_key
        )

    advisory = _validate_advisory(
        record.get("advisory"), context=context, source=source
    )
    authority = _validate_authority_bindings(
        record.get("authority_bindings"), context=context
    )
    successor = _validate_successor_plan(
        record.get("d3_successor_plan"),
        context=context,
        advisory=advisory,
        authority=authority,
    )
    runtime_ack, runtime_ack_sha256 = _validate_runtime_ack(
        record.get("runtime_ack"),
        context=context,
        advisory=advisory,
        successor=successor,
        authority=authority,
    )
    physical = _validate_physical_window(
        record.get("physical_window"),
        context=context,
        advisory=advisory,
        successor=successor,
        runtime_ack=runtime_ack,
        runtime_ack_sha256=runtime_ack_sha256,
        authority=authority,
    )
    r0 = _validate_same_key_r0(
        record.get("same_key_r0"),
        context=context,
        comparison_key=comparison_key,
        formal_reference=formal_index[comparison_key]["r0"],
    )
    _validate_paired_non_degradation(
        record.get("paired_non_degradation"),
        context=context,
        physical=physical,
        r0=r0,
    )
    _validate_coalition_integrity(
        record.get("coalition_integrity"),
        context=context,
        successor=successor,
        runtime_ack=runtime_ack,
        physical=physical,
        authority=authority,
    )
    safety = _strict_mapping(record.get("safety"), f"{context}.safety")
    _require_exact_keys(safety, _SAFETY_FIELDS, f"{context}.safety")
    expected_safety = {
        "hard_constraint_violation_count": 0,
        "online_truth_use_count": 0,
        "global_track_id_rewrite_count": 0,
        "rule_fallback_available": True,
        "coalition_integrity_passed": True,
    }
    if dict(safety) != expected_safety:
        raise RegionResourceA2EvidenceError(
            "runtime_record_safety_invalid", f"{comparison_key}:{safety}"
        )


def _validate_advisory(
    value: Any,
    *,
    context: str,
    source: _SourceIdentity,
) -> Mapping[str, Any]:
    advisory = _strict_mapping(value, f"{context}.advisory")
    _require_exact_keys(advisory, _ADVISORY_FIELDS, f"{context}.advisory")
    confidence = _strict_unit_float(
        advisory.get("candidate_confidence"),
        f"{context}.advisory.candidate_confidence",
    )
    minimum = _strict_unit_float(
        advisory.get("minimum_confidence"),
        f"{context}.advisory.minimum_confidence",
    )
    if not isclose(
        minimum,
        REGION_RESOURCE_A2_MINIMUM_CONFIDENCE,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise RegionResourceA2EvidenceError(
            "minimum_confidence_changed", str(minimum)
        )
    if confidence < REGION_RESOURCE_A2_MINIMUM_CONFIDENCE:
        raise RegionResourceA2EvidenceError(
            "candidate_confidence_below_0_6", str(confidence)
        )
    expected = {
        "schema": REGION_RESOURCE_ADVISORY_SCHEMA,
        "model_state_sha256": source.weights_sha256,
        "requested_mode": "assist",
        "effective_mode": "assist",
        "projected": True,
        "actual_safe_adoption": True,
        "rule_fallback_used": False,
        "nominal_rule_arm_used": False,
        "active_risk_rule_arm_used": False,
    }
    for name, expected_value in expected.items():
        if advisory.get(name) != expected_value:
            raise RegionResourceA2EvidenceError(
                f"advisory_safe_adoption_invalid.{name}",
                f"expected {expected_value}, received {advisory.get(name)}",
            )
    _strict_text(advisory.get("advisory_id"), f"{context}.advisory_id")
    _strict_positive_int(
        advisory.get("advisory_version"), f"{context}.advisory_version"
    )
    _strict_sha256(
        advisory.get("payload_sha256"), f"{context}.advisory.payload_sha256"
    )
    _strict_text(
        advisory.get("source_plan_id"), f"{context}.advisory.source_plan_id"
    )
    _strict_nonnegative_int(
        advisory.get("source_plan_version"),
        f"{context}.advisory.source_plan_version",
    )
    return advisory


def _validate_authority_bindings(
    value: Any,
    *,
    context: str,
) -> tuple[Mapping[str, Any], ...]:
    raw_bindings = _strict_sequence(
        value, f"{context}.authority_bindings"
    )
    if not raw_bindings:
        raise RegionResourceA2EvidenceError(
            "authority_binding_empty", context
        )
    bindings: list[Mapping[str, Any]] = []
    regions: set[str] = set()
    generation: tuple[str, str, int, int, float] | None = None
    for index, raw in enumerate(raw_bindings):
        item_context = f"{context}.authority_bindings[{index}]"
        binding = _strict_mapping(raw, item_context)
        _require_exact_keys(
            binding, _AUTHORITY_BINDING_FIELDS, item_context
        )
        region_id = _strict_text(binding.get("region_id"), item_context)
        owner_layer = _strict_text(
            binding.get("owner_layer"), f"{item_context}.owner_layer"
        )
        owner_node_id = _strict_text(
            binding.get("owner_node_id"), f"{item_context}.owner_node_id"
        )
        if owner_layer not in {"center", "secondary", "distributed"}:
            raise RegionResourceA2EvidenceError(
                "authority_owner_layer_invalid", owner_layer
            )
        epoch = _strict_nonnegative_int(
            binding.get("authority_epoch"),
            f"{item_context}.authority_epoch",
        )
        fault_generation = _strict_nonnegative_int(
            binding.get("fault_generation"),
            f"{item_context}.fault_generation",
        )
        lease = _strict_nonnegative_float(
            binding.get("lease_expires_at_s"),
            f"{item_context}.lease_expires_at_s",
        )
        timestamp = _strict_nonnegative_float(
            binding.get("evidence_timestamp_s"),
            f"{item_context}.evidence_timestamp_s",
        )
        if lease <= timestamp:
            raise RegionResourceA2EvidenceError(
                "authority_lease_expired", item_context
            )
        current = (
            owner_layer,
            owner_node_id,
            epoch,
            fault_generation,
            lease,
        )
        if generation is not None and current != generation:
            raise RegionResourceA2EvidenceError(
                "authority_generation_inconsistent", item_context
            )
        if region_id in regions:
            raise RegionResourceA2EvidenceError(
                "authority_region_duplicate", region_id
            )
        generation = current
        regions.add(region_id)
        bindings.append(binding)
    return tuple(bindings)


def _validate_successor_plan(
    value: Any,
    *,
    context: str,
    advisory: Mapping[str, Any],
    authority: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    plan = _strict_mapping(value, f"{context}.d3_successor_plan")
    _require_exact_keys(
        plan, _D3_SUCCESSOR_FIELDS, f"{context}.d3_successor_plan"
    )
    previous_version = _strict_nonnegative_int(
        plan.get("previous_plan_version"),
        f"{context}.d3_successor_plan.previous_plan_version",
    )
    version = _strict_positive_int(
        plan.get("plan_version"),
        f"{context}.d3_successor_plan.plan_version",
    )
    created = _strict_nonnegative_float(
        plan.get("created_at_s"),
        f"{context}.d3_successor_plan.created_at_s",
    )
    valid_until = _strict_nonnegative_float(
        plan.get("valid_until_s"),
        f"{context}.d3_successor_plan.valid_until_s",
    )
    minimum_lease = min(
        float(item["lease_expires_at_s"]) for item in authority
    )
    if (
        plan.get("schema_version") != "assignment_plan_v2"
        or plan.get("previous_plan_id") != advisory["source_plan_id"]
        or previous_version != advisory["source_plan_version"]
        or version <= previous_version
        or valid_until <= created
        or valid_until > minimum_lease
        or plan.get("accepted") is not True
        or plan.get("regional_hint_applied") is not True
        or plan.get("stale_version_rejected") is not True
        or plan.get("source_advisory_id") != advisory["advisory_id"]
        or plan.get("source_advisory_version")
        != advisory["advisory_version"]
        or plan.get("source_advisory_payload_sha256")
        != advisory["payload_sha256"]
    ):
        raise RegionResourceA2EvidenceError(
            "d3_strict_successor_plan_invalid", str(plan)
        )
    _strict_text(plan.get("plan_id"), f"{context}.d3_successor_plan.plan_id")
    _strict_sha256(
        plan.get("payload_sha256"),
        f"{context}.d3_successor_plan.payload_sha256",
    )
    return plan


def _validate_runtime_ack(
    value: Any,
    *,
    context: str,
    advisory: Mapping[str, Any],
    successor: Mapping[str, Any],
    authority: Sequence[Mapping[str, Any]],
) -> tuple[RegionResourceRuntimeAckEvidence, str]:
    wrapper = _strict_mapping(value, f"{context}.runtime_ack")
    _require_exact_keys(
        wrapper, _RUNTIME_ACK_WRAPPER_FIELDS, f"{context}.runtime_ack"
    )
    payload = _strict_mapping(
        wrapper.get("payload"), f"{context}.runtime_ack.payload"
    )
    expected_fields = {field.name for field in fields(
        RegionResourceRuntimeAckEvidence
    )}
    _require_exact_keys(
        payload, expected_fields, f"{context}.runtime_ack.payload"
    )
    digest = _sha256_json(payload)
    if wrapper.get("payload_sha256") != digest:
        raise RegionResourceA2EvidenceError(
            "runtime_ack_content_sha256_mismatch",
            f"{wrapper.get('payload_sha256')}!={digest}",
        )
    try:
        ack = RegionResourceRuntimeAckEvidence(
            **{
                **dict(payload),
                "rejection_reasons": tuple(
                    payload.get("rejection_reasons", ())
                ),
            }
        )
    except (TypeError, ValueError) as exc:
        raise RegionResourceA2EvidenceError(
            "runtime_ack_contract_invalid", str(exc)
        ) from exc
    owner = authority[0]
    if (
        ack.schema != REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA
        or ack.code != RegionResourceRuntimeAckCode.APPLIED.value
        or ack.runtime_advisory_applied_ack_available is not True
        or ack.adoption_kind
        != RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
        or ack.advisory_id != advisory["advisory_id"]
        or ack.advisory_version != advisory["advisory_version"]
        or ack.advisory_payload_sha256 != advisory["payload_sha256"]
        or ack.source_plan_id != advisory["source_plan_id"]
        or ack.source_plan_version != advisory["source_plan_version"]
        or ack.applied_plan_id != successor["plan_id"]
        or ack.applied_plan_version != successor["plan_version"]
        or ack.owner_layer != owner["owner_layer"]
        or ack.owner_node_id != owner["owner_node_id"]
        or ack.authority_epoch != owner["authority_epoch"]
        or ack.lease_expires_at_s != owner["lease_expires_at_s"]
        or ack.acknowledged_at_s is None
        or ack.acknowledged_at_s < successor["created_at_s"]
        or ack.acknowledged_at_s >= owner["lease_expires_at_s"]
    ):
        raise RegionResourceA2EvidenceError(
            "runtime_ack_cross_binding_invalid", str(payload)
        )
    return ack, digest


def _validate_physical_window(
    value: Any,
    *,
    context: str,
    advisory: Mapping[str, Any],
    successor: Mapping[str, Any],
    runtime_ack: RegionResourceRuntimeAckEvidence,
    runtime_ack_sha256: str,
    authority: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    window = _strict_mapping(value, f"{context}.physical_window")
    _require_exact_keys(
        window, _PHYSICAL_WINDOW_FIELDS, f"{context}.physical_window"
    )
    start = _strict_nonnegative_float(
        window.get("window_start_s"),
        f"{context}.physical_window.window_start_s",
    )
    end = _strict_nonnegative_float(
        window.get("window_end_s"),
        f"{context}.physical_window.window_end_s",
    )
    minimum_lease = min(
        float(item["lease_expires_at_s"]) for item in authority
    )
    if (
        window.get("schema") != REGION_RESOURCE_A2_PHYSICAL_WINDOW_SCHEMA
        or window.get("available") is not True
        or window.get("physical_execution_observed") is not True
        or window.get("hard_constraint_violation_count") != 0
        or window.get("advisory_id") != advisory["advisory_id"]
        or window.get("advisory_version")
        != advisory["advisory_version"]
        or window.get("applied_plan_id") != successor["plan_id"]
        or window.get("applied_plan_version") != successor["plan_version"]
        or window.get("runtime_ack_sha256") != runtime_ack_sha256
        or runtime_ack.acknowledged_at_s is None
        or start < runtime_ack.acknowledged_at_s
        or end <= start
        or end >= minimum_lease
    ):
        raise RegionResourceA2EvidenceError(
            "physical_window_invalid", str(window)
        )
    _strict_text(window.get("window_id"), f"{context}.physical_window.window_id")
    for name in (
        "source_snapshot_payload_sha256",
        "outcome_snapshot_payload_sha256",
    ):
        _strict_sha256(
            window.get(name), f"{context}.physical_window.{name}"
        )
    return window


def _validate_same_key_r0(
    value: Any,
    *,
    context: str,
    comparison_key: str,
    formal_reference: Mapping[str, Any],
) -> Mapping[str, Any]:
    r0 = _strict_mapping(value, f"{context}.same_key_r0")
    _require_exact_keys(r0, _R0_FIELDS, f"{context}.same_key_r0")
    if (
        r0.get("schema") != REGION_RESOURCE_A2_R0_REFERENCE_SCHEMA
        or r0.get("cell_id") != formal_reference.get("cell_id")
        or r0.get("comparison_key") != comparison_key
        or r0.get("unique_reference") is not True
        or r0.get("physical_window_available") is not True
        or r0.get("rule_policy_name") != "d4-region-resource-rule"
        or r0.get("rule_policy_version") != "v1"
    ):
        raise RegionResourceA2EvidenceError(
            "same_key_r0_invalid", str(r0)
        )
    _strict_sha256(
        r0.get("physical_window_payload_sha256"),
        f"{context}.same_key_r0.physical_window_payload_sha256",
    )
    return r0


def _validate_paired_non_degradation(
    value: Any,
    *,
    context: str,
    physical: Mapping[str, Any],
    r0: Mapping[str, Any],
) -> None:
    paired = _strict_mapping(
        value, f"{context}.paired_non_degradation"
    )
    _require_exact_keys(
        paired, _PAIRED_FIELDS, f"{context}.paired_non_degradation"
    )
    metrics = _strict_mapping(
        paired.get("required_metric_results"),
        f"{context}.paired_non_degradation.required_metric_results",
    )
    expected_metrics = {
        "intercepted_target_count": True,
        "offline_proximity_unique_target_count": True,
    }
    if (
        paired.get("schema") != REGION_RESOURCE_A2_PAIRED_RESULT_SCHEMA
        or paired.get("available") is not True
        or paired.get("candidate_window_id") != physical["window_id"]
        or paired.get("r0_cell_id") != r0["cell_id"]
        or paired.get("non_degraded") is not True
        or paired.get("hard_constraint_non_degraded") is not True
        or dict(metrics) != expected_metrics
    ):
        raise RegionResourceA2EvidenceError(
            "paired_non_degradation_invalid", str(paired)
        )


def _validate_coalition_integrity(
    value: Any,
    *,
    context: str,
    successor: Mapping[str, Any],
    runtime_ack: RegionResourceRuntimeAckEvidence,
    physical: Mapping[str, Any],
    authority: Sequence[Mapping[str, Any]],
) -> None:
    coalition = _strict_mapping(
        value, f"{context}.coalition_integrity"
    )
    _require_exact_keys(
        coalition, _COALITION_FIELDS, f"{context}.coalition_integrity"
    )
    state_payload = _strict_mapping(
        coalition.get("commit_state"),
        f"{context}.coalition_integrity.commit_state",
    )
    state_fields = {field.name for field in fields(CoalitionCommitState)}
    _require_exact_keys(
        state_payload,
        state_fields,
        f"{context}.coalition_integrity.commit_state",
    )
    state_digest = _sha256_json(state_payload)
    if coalition.get("commit_state_sha256") != state_digest:
        raise RegionResourceA2EvidenceError(
            "coalition_state_sha256_mismatch", context
        )
    try:
        state = CoalitionCommitState(
            **{
                **dict(state_payload),
                "required_member_ids": tuple(
                    state_payload.get("required_member_ids", ())
                ),
                "acked_member_ids": tuple(
                    state_payload.get("acked_member_ids", ())
                ),
            }
        )
    except (TypeError, ValueError) as exc:
        raise RegionResourceA2EvidenceError(
            "coalition_state_invalid", str(exc)
        ) from exc
    raw_acks = _strict_sequence(
        coalition.get("member_acks"),
        f"{context}.coalition_integrity.member_acks",
    )
    ack_payloads: list[Mapping[str, Any]] = []
    acks: list[CoalitionMemberAck] = []
    ack_fields = {field.name for field in fields(CoalitionMemberAck)}
    for index, raw_ack in enumerate(raw_acks):
        ack_payload = _strict_mapping(
            raw_ack,
            f"{context}.coalition_integrity.member_acks[{index}]",
        )
        _require_exact_keys(
            ack_payload,
            ack_fields,
            f"{context}.coalition_integrity.member_acks[{index}]",
        )
        try:
            ack = CoalitionMemberAck(**dict(ack_payload))
        except (TypeError, ValueError) as exc:
            raise RegionResourceA2EvidenceError(
                "coalition_member_ack_invalid", str(exc)
            ) from exc
        ack_payloads.append(ack_payload)
        acks.append(ack)
    if coalition.get("member_acks_sha256") != _sha256_json(ack_payloads):
        raise RegionResourceA2EvidenceError(
            "coalition_member_acks_sha256_mismatch", context
        )
    owner = authority[0]
    required = tuple(state.required_member_ids)
    acked = tuple(state.acked_member_ids)
    ack_ids = tuple(sorted(ack.resource_id for ack in acks))
    if (
        coalition.get("complete") is not True
        or state.state != "executing"
        or required != acked
        or tuple(sorted(required)) != ack_ids
        or state.plan_id != successor["plan_id"]
        or state.plan_version != successor["plan_version"]
        or state.epoch != owner["authority_epoch"]
        or state.lease_expires_at != owner["lease_expires_at_s"]
        or coalition.get("fault_generation") != owner["fault_generation"]
        or state.executing_at is None
        or runtime_ack.acknowledged_at_s is None
        or state.executing_at < runtime_ack.acknowledged_at_s
        or state.executing_at > physical["window_start_s"]
        or physical["window_end_s"] >= state.lease_expires_at
    ):
        raise RegionResourceA2EvidenceError(
            "coalition_integrity_incomplete_or_stale", str(coalition)
        )
    for ack in acks:
        if (
            ack.resource_id not in required
            or ack.global_track_id != state.global_track_id
            or ack.coalition_id != state.coalition_id
            or ack.coalition_version != state.coalition_version
            or ack.plan_id != state.plan_id
            or ack.plan_version != state.plan_version
            or ack.epoch != state.epoch
            or ack.can_execute is not True
            or ack.valid_until < physical["window_end_s"]
            or ack.evidence_timestamp > state.executing_at
        ):
            raise RegionResourceA2EvidenceError(
                "coalition_member_ack_cross_binding_invalid",
                ack.resource_id,
            )


def _validate_assembled_manifest_semantics(
    manifest: Mapping[str, Any],
    *,
    source: _SourceIdentity,
    implementation: Mapping[str, Any],
    candidate_fingerprint: str,
    evidence: Mapping[str, _JsonArtifact],
    formal_scope_checksums_sha256: str,
) -> None:
    bundle_id = _strict_text(manifest.get("bundle_id"), "manifest.bundle_id")
    expected_bundle_id = (
        f"d4-a2-assist-{candidate_fingerprint.removeprefix('sha256:')[:12]}-"
        f"{evidence['d6_external_audit'].content_sha256[:12]}"
    )
    if bundle_id != expected_bundle_id:
        raise RegionResourceA2EvidenceError(
            "assembled_bundle_id_mismatch",
            f"{bundle_id}!={expected_bundle_id}",
        )
    candidate = _strict_mapping(
        manifest.get("candidate"), "manifest.candidate"
    )
    _require_exact_keys(
        candidate,
        {
            "candidate_fingerprint",
            "model_version",
            "model_state_sha256",
            "implementation_sha256",
            "source_git_commit",
            "formal_profile_version",
            "unseen_seed_values",
        },
        "manifest.candidate",
    )
    expected_candidate = {
        "candidate_fingerprint": candidate_fingerprint,
        "model_version": source.manifest.model_version,
        "model_state_sha256": source.weights_sha256,
        "implementation_sha256": implementation["implementation_sha256"],
        "source_git_commit": implementation["source_git_commit"],
        "formal_profile_version": D6_A2_FORMAL_PROFILE,
        "unseen_seed_values": list(REGION_RESOURCE_A2_RESERVED_SEEDS),
    }
    if dict(candidate) != expected_candidate:
        raise RegionResourceA2EvidenceError(
            "assembled_candidate_record_mismatch", str(candidate)
        )
    admission = _strict_mapping(
        manifest.get("admission"), "manifest.admission"
    )
    _require_exact_keys(admission, _PERMISSION_FIELDS, "manifest.admission")
    expected_admission = {
        "a2_assist_eligible_requested": True,
        "default_model": False,
        "ppo_enabled": False,
        "model_promotion": False,
        "failover_authority": False,
        "assignment_authority": False,
        "control_authority": False,
        "rule_fallback_required": True,
    }
    if dict(admission) != expected_admission:
        raise RegionResourceA2EvidenceError(
            "assembled_admission_not_assist_only", str(admission)
        )
    evidence_records = _strict_mapping(
        manifest.get("evidence"), "manifest.evidence"
    )
    for name, artifact in evidence.items():
        record = _strict_mapping(
            evidence_records[name], f"manifest.evidence.{name}"
        )
        if (
            record.get("sha256") != artifact.file_sha256
            or record.get("content_sha256") != artifact.content_sha256
        ):
            raise RegionResourceA2EvidenceError(
                f"assembled_evidence_record_mismatch.{name}", str(record)
            )
    checksum_record = _strict_mapping(
        evidence_records.get("formal_scope_checksums"),
        "manifest.evidence.formal_scope_checksums",
    )
    if (
        checksum_record.get("sha256")
        != formal_scope_checksums_sha256
    ):
        raise RegionResourceA2EvidenceError(
            "assembled_formal_checksum_record_mismatch",
            str(checksum_record),
        )


def _stage_bundle(
    staging: Path,
    *,
    source: _SourceIdentity,
    implementation: _JsonArtifact,
    audit: _JsonArtifact,
    formal_scope: _JsonArtifact,
    formal_scope_checksums_path: Path,
    formal_scope_checksums_sha256: str,
    runtime_chain: _JsonArtifact,
    candidate_fingerprint: str,
    implementation_contract: Mapping[str, Any],
) -> None:
    (staging / SOURCE_DIRECTORY).mkdir(parents=True, exist_ok=False)
    (staging / EVIDENCE_DIRECTORY).mkdir(parents=True, exist_ok=False)
    copy_pairs = {
        source.root / "manifest.json": staging / SOURCE_MANIFEST_FILENAME,
        source.root / "state_dict.pt": staging / SOURCE_WEIGHTS_FILENAME,
        source.root / "training_dataset_manifest.json": (
            staging / SOURCE_TRAINING_MANIFEST_FILENAME
        ),
        implementation.path: staging / IMPLEMENTATION_EVIDENCE_FILENAME,
        audit.path: staging / D6_EXTERNAL_AUDIT_FILENAME,
        formal_scope.path: staging / FORMAL_SCOPE_AUDIT_FILENAME,
        formal_scope_checksums_path: (
            staging / FORMAL_SCOPE_CHECKSUMS_FILENAME
        ),
        runtime_chain.path: staging / RUNTIME_CHAIN_EVIDENCE_FILENAME,
    }
    for source_path, destination in copy_pairs.items():
        shutil.copyfile(source_path, destination)

    source_record = {
        "schema": source.manifest.schema,
        "manifest": {
            "filename": SOURCE_MANIFEST_FILENAME,
            "sha256": source.manifest_sha256,
        },
        "weights": {
            "filename": SOURCE_WEIGHTS_FILENAME,
            "sha256": source.weights_sha256,
        },
        "training_manifest": {
            "filename": SOURCE_TRAINING_MANIFEST_FILENAME,
            "sha256": source.training_manifest_sha256,
        },
        "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
        "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
    }
    evidence = {
        "implementation_evidence": _artifact_record(
            IMPLEMENTATION_EVIDENCE_FILENAME, implementation
        ),
        "d6_external_audit": _artifact_record(
            D6_EXTERNAL_AUDIT_FILENAME, audit
        ),
        "formal_scope_audit": _artifact_record(
            FORMAL_SCOPE_AUDIT_FILENAME, formal_scope
        ),
        "formal_scope_checksums": {
            "filename": FORMAL_SCOPE_CHECKSUMS_FILENAME,
            "sha256": formal_scope_checksums_sha256,
        },
        "runtime_chain_evidence": _artifact_record(
            RUNTIME_CHAIN_EVIDENCE_FILENAME, runtime_chain
        ),
    }
    admission = {
        "a2_assist_eligible_requested": True,
        "default_model": False,
        "ppo_enabled": False,
        "model_promotion": False,
        "failover_authority": False,
        "assignment_authority": False,
        "control_authority": False,
        "rule_fallback_required": True,
    }
    manifest = {
        "schema_version": REGION_RESOURCE_A2_EVIDENCE_BUNDLE_SCHEMA,
        "bundle_id": (
            f"d4-a2-assist-"
            f"{candidate_fingerprint.removeprefix('sha256:')[:12]}-"
            f"{audit.content_sha256[:12]}"
        ),
        "candidate": {
            "candidate_fingerprint": candidate_fingerprint,
            "model_version": source.manifest.model_version,
            "model_state_sha256": source.weights_sha256,
            "implementation_sha256": implementation_contract[
                "implementation_sha256"
            ],
            "source_git_commit": implementation_contract[
                "source_git_commit"
            ],
            "formal_profile_version": D6_A2_FORMAL_PROFILE,
            "unseen_seed_values": list(REGION_RESOURCE_A2_RESERVED_SEEDS),
        },
        "source_development_bundle": source_record,
        "evidence": evidence,
        "admission": admission,
    }
    manifest["content_sha256"] = _content_sha256(manifest)
    _write_json(staging / MANIFEST_FILENAME, manifest)
    checksums = {
        filename: _sha256_file(staging / filename)
        for filename in sorted(_BUNDLE_FILES)
    }
    checksum_text = "".join(
        f"{checksums[filename]}  {filename}\n"
        for filename in sorted(checksums)
    )
    (staging / CHECKSUMS_FILENAME).write_text(
        checksum_text, encoding="ascii"
    )


def _artifact_record(
    filename: str, artifact: _JsonArtifact
) -> dict[str, str]:
    return {
        "filename": filename,
        "sha256": artifact.file_sha256,
        "content_sha256": artifact.content_sha256,
    }


def _validate_artifact_record(
    value: Any,
    *,
    filename: str,
    file_sha256: str,
    name: str,
) -> Mapping[str, str]:
    record = _strict_mapping(value, name)
    _require_exact_keys(
        record, {"filename", "sha256", "content_sha256"}, name
    )
    if record.get("filename") != filename:
        raise RegionResourceA2EvidenceError(
            f"artifact_filename_mismatch.{name}", str(record.get("filename"))
        )
    sha_value = _strict_sha256(record.get("sha256"), f"{name}.sha256")
    content_value = _strict_sha256(
        record.get("content_sha256"), f"{name}.content_sha256"
    )
    if sha_value != file_sha256:
        raise RegionResourceA2EvidenceError(
            f"artifact_sha256_record_mismatch.{name}",
            f"{sha_value}!={file_sha256}",
        )
    return MappingProxyType(
        {
            "filename": filename,
            "sha256": sha_value,
            "content_sha256": content_value,
        }
    )


def _validate_source_record(
    value: Any,
    *,
    filename: str,
    expected_sha256: str,
    name: str,
) -> Mapping[str, str]:
    record = _strict_mapping(value, name)
    _require_exact_keys(record, {"filename", "sha256"}, name)
    if record.get("filename") != filename:
        raise RegionResourceA2EvidenceError(
            f"source_filename_mismatch.{name}", str(record.get("filename"))
        )
    digest = _strict_sha256(record.get("sha256"), f"{name}.sha256")
    if digest != expected_sha256:
        raise RegionResourceA2EvidenceError(
            f"source_sha256_record_mismatch.{name}",
            f"{digest}!={expected_sha256}",
        )
    return MappingProxyType({"filename": filename, "sha256": digest})


def _validate_formal_scope_checksums(
    path: Path,
    expected_file_sha256: str,
    expected_formal_scope_sha256: str,
) -> str:
    if not path.is_file():
        raise RegionResourceA2EvidenceError(
            "formal_scope_checksums_missing", str(path)
        )
    actual_file_sha = _sha256_file(path)
    if actual_file_sha != expected_file_sha256:
        raise RegionResourceA2EvidenceError(
            "formal_scope_checksums_sha256_mismatch",
            f"{actual_file_sha}!={expected_file_sha256}",
        )
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RegionResourceA2EvidenceError(
            "formal_scope_checksums_invalid", str(path)
        ) from exc
    expected_line = (
        f"{expected_formal_scope_sha256}  "
        "learning_scope_formal_audit.json"
    )
    if lines != [expected_line]:
        raise RegionResourceA2EvidenceError(
            "formal_scope_checksums_inventory_invalid", str(lines)
        )
    return actual_file_sha


def _recheck_inputs(
    inputs: RegionResourceA2EvidenceInputs,
    source: _SourceIdentity,
) -> None:
    expected = {
        source.root / "manifest.json": source.manifest_sha256,
        source.root / "state_dict.pt": source.weights_sha256,
        source.root
        / "training_dataset_manifest.json": source.training_manifest_sha256,
        inputs.implementation_evidence_path: (
            inputs.expected_implementation_evidence_sha256
        ),
        inputs.d6_external_audit_path: (
            inputs.expected_d6_external_audit_sha256
        ),
        inputs.formal_scope_audit_path: (
            inputs.expected_formal_scope_audit_sha256
        ),
        inputs.formal_scope_checksums_path: (
            inputs.expected_formal_scope_checksums_sha256
        ),
        inputs.runtime_chain_evidence_path: (
            inputs.expected_runtime_chain_evidence_sha256
        ),
    }
    for path, digest in expected.items():
        if not path.is_file() or _sha256_file(path) != digest:
            raise RegionResourceA2EvidenceError(
                "input_changed_during_assembly", str(path)
            )


def _validate_output_destination(output: Path) -> None:
    if output.exists():
        raise RegionResourceA2EvidenceError(
            "output_exists_no_overwrite", str(output)
        )


def _validate_output_separation(
    output: Path,
    inputs: RegionResourceA2EvidenceInputs,
) -> None:
    sources = (
        inputs.development_bundle_dir,
        inputs.implementation_evidence_path,
        inputs.d6_external_audit_path,
        inputs.formal_scope_audit_path,
        inputs.formal_scope_checksums_path,
        inputs.runtime_chain_evidence_path,
    )
    for source in sources:
        if (
            output == source
            or output.is_relative_to(source)
            or source.is_relative_to(output)
        ):
            raise RegionResourceA2EvidenceError(
                "output_overlaps_input", str(source)
            )


def _read_json_artifact(
    path: Path,
    expected_sha256: str,
    artifact_id: str,
    *,
    require_internal_content: bool,
    expected_content_sha256: str | None = None,
) -> _JsonArtifact:
    _strict_sha256(expected_sha256, f"{artifact_id}.expected_sha256")
    if not path.is_file():
        raise RegionResourceA2EvidenceError(
            f"input_missing.{artifact_id}", str(path)
        )
    actual_sha = _sha256_file(path)
    if actual_sha != expected_sha256:
        raise RegionResourceA2EvidenceError(
            f"input_sha256_mismatch.{artifact_id}",
            f"expected {expected_sha256}, received {actual_sha}",
        )
    payload = _read_json(path, artifact_id)
    calculated_content = _content_sha256(payload)
    if require_internal_content:
        claimed = _strict_sha256(
            payload.get("content_sha256"),
            f"{artifact_id}.content_sha256",
        )
        if claimed != calculated_content:
            raise RegionResourceA2EvidenceError(
                f"input_content_sha256_mismatch.{artifact_id}",
                f"expected {claimed}, received {calculated_content}",
            )
    if (
        expected_content_sha256 is not None
        and calculated_content != expected_content_sha256
    ):
        raise RegionResourceA2EvidenceError(
            f"packaged_content_sha256_mismatch.{artifact_id}",
            f"expected {expected_content_sha256}, received "
            f"{calculated_content}",
        )
    return _JsonArtifact(
        path=path,
        payload=MappingProxyType(payload),
        file_sha256=actual_sha,
        content_sha256=calculated_content,
    )


def _candidate_fingerprint(
    source: _SourceIdentity, implementation_sha256: str
) -> str:
    payload = {
        "role": "D4_A2",
        "variant": "A2",
        "dataset_manifest_sha256": source.training_manifest_sha256,
        "dataset_content_sha256": source.dataset_content_sha256,
        "dataset_split_sha256": source.dataset_split_sha256,
        "bundle_manifest_sha256": source.manifest_sha256,
        "bundle_weights_sha256": source.weights_sha256,
        "implementation_sha256": implementation_sha256,
    }
    return f"sha256:{_sha256_json(payload)}"


def _current_implementation_files() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    result: dict[str, str] = {}
    for name in _D4_IMPLEMENTATION_FILES:
        path = root / name
        if not path.is_file():
            raise RegionResourceA2EvidenceError(
                "current_implementation_source_missing", name
            )
        result[name] = _sha256_file(path)
    return result


def _read_bundle_checksums(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RegionResourceA2EvidenceError(
            "bundle_checksums_missing", str(path)
        )
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RegionResourceA2EvidenceError(
            "bundle_checksums_invalid", str(path)
        ) from exc
    result: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2:
            raise RegionResourceA2EvidenceError(
                "bundle_checksums_invalid", line
            )
        digest, filename = parts
        _strict_sha256(digest, f"bundle_checksums.{filename}")
        candidate = Path(filename)
        if (
            filename in result
            or candidate.is_absolute()
            or ".." in candidate.parts
            or filename == CHECKSUMS_FILENAME
        ):
            raise RegionResourceA2EvidenceError(
                "bundle_checksums_invalid", filename
            )
        result[filename] = digest
    return result


def _reject_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RegionResourceA2EvidenceError(
                "bundle_symlink_forbidden", str(path)
            )


def _read_json(path: Path, artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_json_constant(token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RegionResourceA2EvidenceError(
            f"input_json_invalid.{artifact_id}", str(path)
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceA2EvidenceError(
            f"input_json_invalid.{artifact_id}",
            "root must be an object",
        )
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(_canonical_json_bytes(value))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json_bytes(value, newline=False)).hexdigest()


def _content_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    return _sha256_json(payload)


def _canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if newline:
        text += "\n"
    return text.encode("utf-8")


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str] | frozenset[str],
    name: str,
) -> None:
    actual = set(value)
    if actual != set(expected):
        raise RegionResourceA2EvidenceError(
            f"fields_mismatch.{name}",
            _set_difference_text(actual, set(expected)),
        )


def _strict_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be an object"
        )
    return value


def _strict_sequence(value: Any, name: str) -> Sequence[Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be an array"
        )
    return value


def _strict_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise RegionResourceA2EvidenceError(
            f"hash_invalid.{name}", "must be lowercase SHA-256"
        )
    return value


def _strict_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be non-empty text"
        )
    return value


def _strict_nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be a non-negative int"
        )
    return value


def _strict_positive_int(value: Any, name: str) -> int:
    result = _strict_nonnegative_int(value, name)
    if result <= 0:
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be a positive int"
        )
    return result


def _strict_nonnegative_float(value: Any, name: str) -> float:
    if type(value) not in {int, float}:
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be numeric"
        )
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be finite and non-negative"
        )
    return result


def _strict_unit_float(value: Any, name: str) -> float:
    result = _strict_nonnegative_float(value, name)
    if result > 1.0:
        raise RegionResourceA2EvidenceError(
            f"type_invalid.{name}", "must be in [0, 1]"
        )
    return result


def _set_difference_text(
    actual: set[str], expected: set[str] | frozenset[str]
) -> str:
    return (
        f"missing={sorted(set(expected) - actual)};"
        f"extra={sorted(actual - set(expected))}"
    )


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


__all__ = [
    "CHECKSUMS_FILENAME",
    "D6_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA",
    "D6_A2_EXTERNAL_AUDIT_SCHEMA",
    "D6_A2_FORMAL_PROFILE",
    "D6_EXTERNAL_AUDIT_FILENAME",
    "D6_FORMAL_SCOPE_AUDIT_SCHEMA",
    "D6_IMPLEMENTATION_EVIDENCE_SCHEMA",
    "FORMAL_SCOPE_AUDIT_FILENAME",
    "FORMAL_SCOPE_CHECKSUMS_FILENAME",
    "IMPLEMENTATION_EVIDENCE_FILENAME",
    "LoadedRegionResourceA2EvidenceBundle",
    "MANIFEST_FILENAME",
    "REGION_RESOURCE_A2_EVIDENCE_BUNDLE_SCHEMA",
    "REGION_RESOURCE_A2_MINIMUM_CONFIDENCE",
    "REGION_RESOURCE_A2_PAIRED_RESULT_SCHEMA",
    "REGION_RESOURCE_A2_PHYSICAL_WINDOW_SCHEMA",
    "REGION_RESOURCE_A2_R0_REFERENCE_SCHEMA",
    "REGION_RESOURCE_A2_RESERVED_SEEDS",
    "REGION_RESOURCE_A2_RUNTIME_CHAIN_SCHEMA",
    "RUNTIME_CHAIN_EVIDENCE_FILENAME",
    "RegionResourceA2AssemblyResult",
    "RegionResourceA2EvidenceError",
    "RegionResourceA2EvidenceInputs",
    "SOURCE_MANIFEST_FILENAME",
    "SOURCE_TRAINING_MANIFEST_FILENAME",
    "SOURCE_WEIGHTS_FILENAME",
    "assemble_region_resource_a2_evidence_bundle",
    "load_region_resource_a2_evidence_bundle",
]
