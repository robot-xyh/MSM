"""Adapters from existing strict evidence schemas to readiness gate facts.

The adapters do not accept caller-provided gate facts.  A small reference
sidecar may name original producer artifacts, but every named file is resolved
below one explicit root, hashed, and then consumed by an existing D6 auditor.
Unsupported gates remain unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import importlib
import json
from math import isfinite
from pathlib import Path
from typing import Any

from .canonical_seed_split_readiness import (
    CANONICAL_SEED_SPLIT_READINESS_SCHEMA_VERSION,
    CanonicalSeedSplitAuditError,
    audit_canonical_seed_split_readiness,
)
from .d5_g1_external_audit import (
    D5_G1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION,
    D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION,
    D5G1ExternalAuditError,
    audit_d5_g1_external_evidence,
    load_d5_g1_external_audit_inputs,
)
from .d5_g1_post_assembly_audit import (
    D5_G1_POST_ASSEMBLY_AUDIT_CONSUMER_SCHEMA_VERSION,
    D5_G1_POST_ASSEMBLY_AUDIT_SCHEMA_VERSION,
    D5G1PostAssemblyAuditError,
    audit_d5_g1_post_assembly_bundle,
    load_d5_g1_post_assembly_audit_inputs,
)


CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION = (
    "d6.learning-run-canonical-seed-source-reference.v1"
)
D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION = (
    "d6.learning-run-d5-g1-model-source-reference.v1"
)
D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION = (
    "d6.learning-run-d4-a2-current-lineage-model-source-reference.v1"
)
D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION = (
    "d6.learning-run-d4-a2-runtime-distribution-source-reference.v1"
)
LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS = {
    "model_source": frozenset(
        {
            D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION,
            D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION,
        }
    ),
    "frozen_unseen_seeds": frozenset(
        {CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION}
    ),
    "runtime_distribution_compatible": frozenset(
        {D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION}
    ),
    "identifiable_adoption": frozenset(),
    "runtime_ack": frozenset(),
    "physical_window": frozenset(),
    "same_key_r0": frozenset(),
    "paired_non_degradation": frozenset(),
    "truth_use": frozenset(),
    "finite_state": frozenset(),
    "external_permission": frozenset(),
}

_MODEL_SOURCE_REFERENCE_FIELDS = frozenset(
    {"schema_version", "variant", "component_references", "content_sha256"}
)
_D4_A2_MODEL_SOURCE_REFERENCE_FIELDS = frozenset(
    {"schema_version", "variant", "candidate_manifest", "content_sha256"}
)
_D4_A2_RUNTIME_DISTRIBUTION_REFERENCE_FIELDS = frozenset(
    {"schema_version", "variant", "shadow_records", "content_sha256"}
)
_MODEL_SOURCE_REQUIRED_COMPONENTS = {
    "G1": frozenset({"d5_graph"}),
    "A1": frozenset({"d3"}),
    "A2": frozenset({"d4"}),
    "A3": frozenset({"d5_active_vision"}),
    "C1": frozenset({"d3", "d4", "d5_graph", "d5_active_vision"}),
    "F1": frozenset({"d3", "d4", "d5_graph", "d5_active_vision"}),
}
_D5_G1_MODEL_SOURCE_ARTIFACT_NAMES = frozenset(
    {
        "external_audit_input",
        "external_audit_output",
        "external_audit_checksums",
        "post_assembly_input",
        "post_assembly_output",
        "post_assembly_checksums",
        "v5_bundle_manifest",
        "v5_bundle_weights",
        "v5_bundle_checksums",
        "v5_heldout_evidence",
        "v5_paired_shadow_evidence",
        "v5_paired_shadow_lineage",
        "v5_external_audit_evidence",
    }
)
_D5_G1_EXTERNAL_ORIGINAL_LAYOUT = {
    "registry_reference": (
        "current_runtime_registry/frozen_bundle_reference.json"
    ),
    "registry_audit_evidence": "current_runtime_registry/audit_evidence.json",
    "registry_checksums": "current_runtime_registry/SHA256SUMS",
    "bundle_manifest": "model_candidate/model_bundle/manifest.json",
    "bundle_weights": "model_candidate/model_bundle/weights.pt",
    "bundle_checksums": "model_candidate/model_bundle/SHA256SUMS",
    "heldout_report": (
        "formal_audit/heldout_evaluation/heldout_evaluation.json"
    ),
    "paired_shadow_report": (
        "formal_audit/paired_shadow/paired_shadow_report.json"
    ),
    "paired_shadow_lineage": (
        "formal_audit/paired_shadow/paired_episode_lineage.jsonl"
    ),
}
_D5_G1_POST_TO_SIDECAR_ARTIFACT = {
    "bundle_manifest": "v5_bundle_manifest",
    "bundle_weights": "v5_bundle_weights",
    "bundle_checksums": "v5_bundle_checksums",
    "heldout_evidence": "v5_heldout_evidence",
    "paired_shadow_evidence": "v5_paired_shadow_evidence",
    "paired_shadow_lineage": "v5_paired_shadow_lineage",
    "d6_external_audit_evidence": "v5_external_audit_evidence",
}
_D5_G1_EXTERNAL_REPORT_CHECKSUM_NAMES = frozenset(
    {
        "D5_G1_EXTERNAL_AUDIT_CN.md",
        "d5_g1_external_audit.json",
        "d5_g1_external_audit_evidence.csv",
    }
)
_D5_G1_POST_REPORT_CHECKSUM_NAMES = frozenset(
    {
        "D5_G1_POST_ASSEMBLY_AUDIT_CN.md",
        "d5_g1_post_assembly_audit.json",
        "d5_g1_post_assembly_audit_evidence.csv",
    }
)
_D5_G1_AUTHORITY_FIELDS = frozenset(
    {
        "model_promotion_granted",
        "g1_assist_granted",
        "default_path_change_granted",
        "assignment_authority_granted",
        "failover_authority_granted",
        "control_authority_granted",
    }
)

_D4_A2_CANDIDATE_ARTIFACT_SHA256 = {
    "bundle/manifest.json": (
        "d9fcdb348b3de8fd139b5052a4e7123a48641975cc7dcc708701a2a72ff7ab00"
    ),
    "bundle/state_dict.pt": (
        "fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047"
    ),
    "bundle/training_dataset_manifest.json": (
        "82819c2470505e61da753d0d24ddf910e154435cd8d2cbd0a979dfb3dd643904"
    ),
    "dataset_summary.json": (
        "2ca394f7673d794cf03627ef4595c3c4c3650687829d760f1305dc8c08d1af26"
    ),
    "source_implementation_summary.json": (
        "d4d678a3f1625e01999dde819641c57a7f29a0055b992cf7c0e8677f268ad9a7"
    ),
    "training_config.json": (
        "a534c9ae4bd4b53613f5618d51d74e66823de31082b71f3c2618069bbc5cd3ce"
    ),
    "training_summary.json": (
        "0fccf4ba2d5323ee6ead0043360c1d902680dc527d0bf2b3ffb24bc45b48402d"
    ),
}
_D4_A2_TRUSTED_MODEL_SOURCE = {
    "variant": "A2",
    "candidate_id": "region_resource_a2_current_lineage_development_v1",
    "model_version": "d4-region-a2-current-lineage-development-v1",
    "candidate_manifest_file_sha256": (
        "7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64"
    ),
    "candidate_manifest_content_sha256": (
        "b51f2ed01d7f8b963166fe1d7e73acd6a481c5359d54ed5c3712371733aa6ba9"
    ),
    "model_state_sha256": (
        "fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047"
    ),
    "source_git_commit": "b0d498d9e76e19e9045e127b6dae26ea164b3fa4",
    "source_git_tree": "8e62257a078d85cc40f62b3f5a8238f9f24079af",
    "source_identity_sha256": (
        "b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf"
    ),
    "source_implementation_sha256": (
        "bcdc7b3cfaea513afabcfae8ffaeb9af130e80e1e5c0beb3adadc2cce0061c2a"
    ),
    "lifecycle_stage": "development",
    "maximum_advisor_mode": "shadow",
    "artifact_sha256": _D4_A2_CANDIDATE_ARTIFACT_SHA256,
}
_D4_A2_PERMISSION_FIELDS = frozenset(
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

# This allow-list is the trust anchor for the one formal D5 G1 v5 candidate
# audited on 2026-07-27. A new model or implementation lineage requires an
# explicit source-adapter revision; a self-signed sidecar cannot replace it.
_D5_G1_TRUSTED_MODEL_SOURCE = {
    "variant": "G1",
    "component_id": "d5_graph",
    "source_root_relative_to_artifact_parent": (
        "MSM-d5-g1-formal-8d5e02e/"
        "research_modules/d5_terminal_association/src/"
        "d5_terminal_association"
    ),
    "artifact_layout": {
        "external_audit_input": "d6_external_audit_input.json",
        "external_audit_output": (
            "d6_external_audit/d5_g1_external_audit.json"
        ),
        "external_audit_checksums": "d6_external_audit/SHA256SUMS",
        "post_assembly_input": "d6_post_assembly_input.json",
        "post_assembly_output": (
            "d6_post_assembly_audit/d5_g1_post_assembly_audit.json"
        ),
        "post_assembly_checksums": "d6_post_assembly_audit/SHA256SUMS",
        "v5_bundle_manifest": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/manifest.json"
        ),
        "v5_bundle_weights": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/weights.pt"
        ),
        "v5_bundle_checksums": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/SHA256SUMS"
        ),
        "v5_heldout_evidence": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/"
            "evidence/heldout_evaluation.json"
        ),
        "v5_paired_shadow_evidence": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/"
            "evidence/paired_shadow_report.json"
        ),
        "v5_paired_shadow_lineage": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/"
            "evidence/paired_episode_lineage.jsonl"
        ),
        "v5_external_audit_evidence": (
            "g1_assist_v5_7fb5db8b_d6_cbd6c72b/"
            "evidence/d6_external_audit.json"
        ),
    },
    "artifact_sha256": {
        "external_audit_input": (
            "f137bcfb5d8f66ef47a2df4553df254e8aea3c95957a72e6f31b08362dbaa02b"
        ),
        "external_audit_output": (
            "cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6"
        ),
        "external_audit_checksums": (
            "eb497ee57aa3b26902258236b8bc98c64ae652871c245b2ca3fcb516e681e81b"
        ),
        "post_assembly_input": (
            "b1f3d570b75c348c7e778671eca1badebe3fc8b690ac7e4ac049eba949354523"
        ),
        "post_assembly_output": (
            "93dd7917810605c98cd11a253014de05fe7da7c0edcbdba330cc44afdb681da6"
        ),
        "post_assembly_checksums": (
            "c9a4051f0a4af62a8cf211a4bbdf703fe6fea1eb847111b810d46ac555a8faef"
        ),
        "v5_bundle_manifest": (
            "b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d"
        ),
        "v5_bundle_weights": (
            "7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71"
        ),
        "v5_bundle_checksums": (
            "0c13b355c659bd6545182469069d6b92bf59a17214a5e4dc8f23623ce0d4b69e"
        ),
        "v5_heldout_evidence": (
            "d6a3b15505a6d5de434a66ac2f5f76bac5b5fe4c0aaf8237dc58055e5f5cbff1"
        ),
        "v5_paired_shadow_evidence": (
            "b08a44908c13fa385b5706bd90a56e79aca501af70490d3552b53104c53ead94"
        ),
        "v5_paired_shadow_lineage": (
            "83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1"
        ),
        "v5_external_audit_evidence": (
            "cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6"
        ),
    },
    "model_fingerprint": (
        "sha256:"
        "7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71"
    ),
    "runtime_implementation_sha256": (
        "b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe"
    ),
    "external_audit_content_sha256": (
        "334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15"
    ),
    "post_assembly_content_sha256": (
        "17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1d"
    ),
}

_REFERENCE_ARTIFACT_NAMES = frozenset(
    {
        "training_seed_registry",
        "shared_seed_split_registry",
        "d3_assignment_manifest",
        "d4_region_manifest",
        "d5_tracklet_graph_manifest",
        "d5_active_vision_manifest",
    }
)
_REFERENCE_FIELDS = frozenset(
    {"schema_version", "variant", "artifacts", "content_sha256"}
)
_ARTIFACT_REFERENCE_FIELDS = frozenset({"path", "file_sha256"})
_REQUIRED_MODULES = {
    "G1": frozenset({"d5_tracklet_graph"}),
    "A1": frozenset({"d3_assignment"}),
    "A2": frozenset({"d4_region"}),
    "A3": frozenset({"d5_active_vision"}),
    "C1": frozenset(
        {
            "d3_assignment",
            "d4_region",
            "d5_tracklet_graph",
            "d5_active_vision",
        }
    ),
    "F1": frozenset(
        {
            "d3_assignment",
            "d4_region",
            "d5_tracklet_graph",
            "d5_active_vision",
        }
    ),
}
_HEX64 = frozenset("0123456789abcdef")


class LearningRunSourceAdapterError(ValueError):
    """Stable failure for an unsupported or invalid source evidence chain."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = str(code)
        self.detail = None if detail is None else str(detail)
        message = self.code if self.detail is None else f"{self.code}: {self.detail}"
        super().__init__(message)


def load_learning_run_source_evidence_bytes(
    data: bytes,
    *,
    artifact_root: str | Path,
    expected_variant: str,
    expected_gate: str,
) -> dict[str, Any]:
    """Validate one source reference and derive facts through a strict auditor."""

    schema = _peek_schema(data)
    supported = LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS.get(
        expected_gate,
        frozenset(),
    )
    if schema not in supported:
        _fail("gate_source_schema_unsupported", schema)
    if schema == D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION:
        return _load_d5_g1_model_source(
            data,
            artifact_root=Path(artifact_root),
            expected_variant=expected_variant,
        )
    if schema == D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION:
        return _load_d4_a2_current_lineage_model_source(
            data,
            artifact_root=Path(artifact_root),
            expected_variant=expected_variant,
        )
    if schema == CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION:
        return _load_canonical_seed_source(
            data,
            artifact_root=Path(artifact_root),
            expected_variant=expected_variant,
        )
    if schema == D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION:
        return _load_d4_a2_runtime_distribution_source(
            data,
            artifact_root=Path(artifact_root),
            expected_variant=expected_variant,
        )
    _fail("gate_source_schema_unsupported", schema)


def _load_d4_a2_current_lineage_model_source(
    data: bytes,
    *,
    artifact_root: Path,
    expected_variant: str,
) -> dict[str, Any]:
    payload = _json_object(data)
    _exact(
        payload,
        _D4_A2_MODEL_SOURCE_REFERENCE_FIELDS,
        "d4_a2_model_source_reference",
    )
    if (
        payload["schema_version"]
        != D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION
    ):
        _fail("gate_source_schema_unsupported", payload["schema_version"])
    variant = _text(payload["variant"], "variant")
    if variant != expected_variant:
        _fail("gate_source_variant_mismatch", f"{variant}!={expected_variant}")
    if variant != "A2":
        _fail("d4_a2_model_source_variant_unsupported", variant)
    reference = _normalize_reference(
        payload["candidate_manifest"],
        context="candidate_manifest",
    )
    body = {
        "schema_version": payload["schema_version"],
        "variant": variant,
        "candidate_manifest": reference,
    }
    claimed_content = _sha256_text(
        payload["content_sha256"],
        "content_sha256",
    )
    if _canonical_sha256(body) != claimed_content:
        _fail("gate_source_content_sha256_mismatch")

    anchor = _D4_A2_TRUSTED_MODEL_SOURCE
    if (
        reference["file_sha256"]
        != anchor["candidate_manifest_file_sha256"]
    ):
        _fail("d4_a2_model_source_trust_anchor_mismatch", "candidate_manifest")
    root = _resolve_artifact_root(artifact_root)
    manifest_path = _resolve_and_verify(
        root,
        reference,
        label="candidate_manifest",
    )
    candidate_root = manifest_path.parent
    if candidate_root.name != anchor["candidate_id"]:
        _fail("d4_a2_candidate_directory_identity_mismatch")

    candidate_module = _import_d4_module(
        "region_resource_current_lineage_candidate"
    )
    learning_module = _import_d4_module("region_resource_learning")
    try:
        manifest = (
            candidate_module
            .load_region_resource_current_lineage_candidate_manifest(
                candidate_root,
                expected_manifest_file_sha256=reference["file_sha256"],
            )
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        _fail(
            "d4_a2_candidate_manifest_rejected",
            type(exc).__name__,
        )
    _validate_d4_a2_manifest(manifest, anchor=anchor)

    source_path = candidate_root / "source_implementation_summary.json"
    try:
        source_summary = (
            candidate_module.RegionResourceCurrentLineageSourceSummary
            .from_mapping(_json_object(source_path.read_bytes()))
        )
    except (OSError, TypeError, ValueError) as exc:
        _fail("d4_a2_source_summary_rejected", type(exc).__name__)
    if (
        source_summary.git_commit != anchor["source_git_commit"]
        or source_summary.git_tree != anchor["source_git_tree"]
        or source_summary.source_identity_sha256
        != anchor["source_identity_sha256"]
        or source_summary.implementation_sha256
        != anchor["source_implementation_sha256"]
        or source_summary.worktree_clean is not True
        or source_summary.dirty_entry_count != 0
    ):
        _fail("d4_a2_source_lineage_mismatch")

    try:
        bundle = learning_module.load_region_resource_model_bundle(
            candidate_root / "bundle",
            expected_model_version=anchor["model_version"],
            expected_state_dict_sha256=anchor["model_state_sha256"],
            map_location="cpu",
            require_training_dataset_manifest=True,
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        _fail("d4_a2_model_bundle_not_loadable", type(exc).__name__)
    _validate_d4_a2_loaded_bundle(bundle, manifest=manifest, anchor=anchor)
    _validate_d4_a2_raw_summaries(candidate_root, manifest=manifest)

    # Re-hash every bound artifact after parser and model-loader execution.
    _verify_file_sha256(
        manifest_path,
        anchor["candidate_manifest_file_sha256"],
        "candidate_manifest",
    )
    for relative, expected_sha in anchor["artifact_sha256"].items():
        _verify_file_sha256(
            candidate_root / relative,
            expected_sha,
            f"candidate_artifact.{relative}",
        )

    return {
        "source_class": "formal_current_lineage_source_audit",
        "source_schema_version": (
            D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "source_content_sha256": claimed_content,
        "formal": True,
        "facts": {
            "component_ids": ["d4"],
            "audit_passed": True,
            "model_identity": f"sha256:{anchor['model_state_sha256']}",
        },
    }


def _validate_d4_a2_manifest(
    manifest: Any,
    *,
    anchor: Mapping[str, Any],
) -> None:
    if (
        manifest.candidate_id != anchor["candidate_id"]
        or manifest.model_version != anchor["model_version"]
        or manifest.content_sha256
        != anchor["candidate_manifest_content_sha256"]
        or manifest.model_state_sha256 != anchor["model_state_sha256"]
        or manifest.source_identity_sha256
        != anchor["source_identity_sha256"]
        or manifest.lifecycle_stage != anchor["lifecycle_stage"]
        or manifest.maximum_advisor_mode != anchor["maximum_advisor_mode"]
        or manifest.development_shadow_candidate is not True
        or manifest.formal_holdout_evaluated is not False
        or dict(manifest.artifact_files) != anchor["artifact_sha256"]
    ):
        _fail("d4_a2_candidate_manifest_trust_anchor_mismatch")
    split = manifest.split_usage
    if (
        split.training_split != "train"
        or split.selection_split != "validation"
        or split.train_payload_read_count <= 0
        or split.validation_payload_read_count <= 0
        or split.test_payload_read_count != 0
        or split.calibration_seed_use_count != 0
        or split.reserved_seed_use_count != 0
        or not split.train_seeds
        or not split.validation_seeds
        or not split.untouched_test_seeds
        or len(split.reserved_evaluation_seeds) != 20
    ):
        _fail("d4_a2_candidate_split_boundary_mismatch")
    catalogs = (
        set(split.train_seeds),
        set(split.validation_seeds),
        set(split.untouched_test_seeds),
        set(split.reserved_evaluation_seeds),
    )
    if any(
        catalogs[left] & catalogs[right]
        for left in range(len(catalogs))
        for right in range(left + 1, len(catalogs))
    ):
        _fail("d4_a2_candidate_split_overlap")
    permissions = manifest.permissions.to_dict()
    if (
        set(permissions) != set(_D4_A2_PERMISSION_FIELDS)
        or any(value is not False for value in permissions.values())
    ):
        _fail("d4_a2_candidate_permission_escalation")


def _validate_d4_a2_loaded_bundle(
    bundle: Any,
    *,
    manifest: Any,
    anchor: Mapping[str, Any],
) -> None:
    bundle_manifest = bundle.manifest
    if (
        bundle_manifest.model_version != anchor["model_version"]
        or bundle_manifest.state_dict_sha256 != anchor["model_state_sha256"]
        or bundle_manifest.lifecycle_stage != anchor["lifecycle_stage"]
        or bundle_manifest.maximum_advisor_mode
        != anchor["maximum_advisor_mode"]
        or bundle_manifest.assist_admitted
        or bundle_manifest.strategy_capability_claim_allowed
        or bundle_manifest.reward_evidence_available
        or bundle_manifest.final_holdout_seed_count != 0
    ):
        _fail("d4_a2_model_bundle_boundary_mismatch")
    embedded = bundle.training_dataset_manifest
    if (
        embedded is None
        or embedded.dataset_sha256 != manifest.dataset_sha256
        or embedded.split.split_sha256 != manifest.dataset_split_sha256
    ):
        _fail("d4_a2_model_bundle_dataset_binding_mismatch")
    try:
        parameters = tuple(bundle.model.parameters())
        finite = all(
            bool(parameter.detach().isfinite().all().item())
            for parameter in parameters
        )
    except (AttributeError, RuntimeError, TypeError) as exc:
        _fail("d4_a2_model_parameter_review_failed", type(exc).__name__)
    if not parameters or not finite:
        _fail("d4_a2_model_parameters_nonfinite_or_empty")


def _validate_d4_a2_raw_summaries(
    candidate_root: Path,
    *,
    manifest: Any,
) -> None:
    dataset = _json_object(
        (candidate_root / "dataset_summary.json").read_bytes()
    )
    training = _json_object(
        (candidate_root / "training_summary.json").read_bytes()
    )
    config = _json_object(
        (candidate_root / "training_config.json").read_bytes()
    )
    if (
        dataset.get("dataset_sha256") != manifest.dataset_sha256
        or dataset.get("dataset_split_sha256")
        != manifest.dataset_split_sha256
        or dataset.get("truth_identifier_use_count") != 0
        or dataset.get("test_payload_verified_during_build") is not False
        or dataset.get("formal_holdout_evaluated") is not False
    ):
        _fail("d4_a2_dataset_summary_boundary_mismatch")
    split_usage = _mapping(dataset.get("split_usage"), "dataset.split_usage")
    if (
        split_usage.get("test_payload_read_count") != 0
        or split_usage.get("calibration_seed_use_count") != 0
        or split_usage.get("reserved_seed_use_count") != 0
    ):
        _fail("d4_a2_dataset_split_usage_mismatch")
    training_permissions = _mapping(
        training.get("permissions"),
        "training.permissions",
    )
    if (
        set(training_permissions) != set(_D4_A2_PERMISSION_FIELDS)
        or any(value is not False for value in training_permissions.values())
        or training.get("lifecycle_stage") != "development"
        or training.get("maximum_advisor_mode") != "shadow"
        or training.get("formal_holdout_evaluated") is not False
        or training.get("model_parameters_finite") is not True
        or training.get("test_sample_count") != 0
        or training.get("reserved_evaluation_sample_count") != 0
        or training.get("calibration_sample_count") != 0
    ):
        _fail("d4_a2_training_summary_boundary_mismatch")
    validation = _mapping(
        training.get("validation_output_review"),
        "training.validation_output_review",
    )
    if (
        validation.get("sample_count") != manifest.validation_sample_count
        or validation.get("nonfinite_output_count") != 0
        or not all(
            isfinite(float(validation[name]))
            for name in ("confidence_min", "confidence_max")
        )
    ):
        _fail("d4_a2_validation_output_review_mismatch")
    if (
        config.get("candidate_id") != manifest.candidate_id
        or config.get("model_version") != manifest.model_version
        or config.get("config_sha256") != manifest.config_sha256
    ):
        _fail("d4_a2_training_config_binding_mismatch")


def _import_d4_module(name: str) -> Any:
    candidates = (
        f"d4_distributed_fallback.{name}",
        (
            "research_modules.d4_distributed_fallback."
            f"d4_distributed_fallback.{name}"
        ),
    )
    failures: list[str] = []
    for module_name in candidates:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            missing = exc.name or ""
            if not (
                missing == module_name
                or module_name.startswith(f"{missing}.")
            ):
                _fail("d4_a2_public_module_import_failed", missing)
            failures.append(module_name)
    _fail("d4_a2_public_module_unavailable", ",".join(failures))


def _load_d4_a2_runtime_distribution_source(
    data: bytes,
    *,
    artifact_root: Path,
    expected_variant: str,
) -> dict[str, Any]:
    payload = _json_object(data)
    _exact(
        payload,
        _D4_A2_RUNTIME_DISTRIBUTION_REFERENCE_FIELDS,
        "d4_a2_runtime_distribution_reference",
    )
    if (
        payload["schema_version"]
        != D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION
    ):
        _fail("gate_source_schema_unsupported", payload["schema_version"])
    variant = _text(payload["variant"], "variant")
    if variant != expected_variant:
        _fail("gate_source_variant_mismatch", f"{variant}!={expected_variant}")
    if variant != "A2":
        _fail("d4_a2_runtime_distribution_variant_unsupported", variant)
    reference = _normalize_reference(
        payload["shadow_records"],
        context="shadow_records",
    )
    body = {
        "schema_version": payload["schema_version"],
        "variant": variant,
        "shadow_records": reference,
    }
    claimed_content = _sha256_text(
        payload["content_sha256"],
        "content_sha256",
    )
    if _canonical_sha256(body) != claimed_content:
        _fail("gate_source_content_sha256_mismatch")

    root = _resolve_artifact_root(artifact_root)
    records_path = _resolve_and_verify(
        root,
        reference,
        label="shadow_records",
    )
    records = _load_d4_a2_shadow_records(records_path)
    facts = _summarize_d4_a2_runtime_distribution(records)
    _verify_file_sha256(
        records_path,
        reference["file_sha256"],
        "shadow_records",
    )
    return {
        "source_class": "persisted_current_lineage_runtime_distribution",
        "source_schema_version": (
            D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "source_content_sha256": claimed_content,
        "formal": True,
        "facts": facts,
    }


def _load_d4_a2_shadow_records(path: Path) -> tuple[Any, ...]:
    shadow_module = _import_d4_module(
        "region_resource_current_lineage_shadow"
    )
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        _fail("d4_a2_shadow_records_unavailable", type(exc).__name__)
    if not lines:
        _fail("d4_a2_shadow_records_empty")
    parsed: list[Any] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            _fail(
                "d4_a2_shadow_record_blank_line",
                str(line_number),
            )
        try:
            value = json.loads(
                line,
                parse_constant=_reject_json_constant,
            )
            if not isinstance(value, Mapping):
                _fail(
                    "d4_a2_shadow_record_mapping_required",
                    str(line_number),
                )
            record = (
                shadow_module.RegionResourceCurrentLineageShadowRecord
                .from_mapping(value)
            )
        except LearningRunSourceAdapterError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            _fail(
                "d4_a2_shadow_record_rejected",
                f"{line_number}:{type(exc).__name__}",
            )
        _validate_d4_a2_shadow_binding(record)
        parsed.append(record)
    record_ids = [str(item.record_id) for item in parsed]
    frame_keys = [
        (
            str(item.input_summary.episode_id),
            int(item.input_summary.frame_index),
        )
        for item in parsed
    ]
    if len(record_ids) != len(set(record_ids)):
        _fail("d4_a2_shadow_record_duplicate")
    if len(frame_keys) != len(set(frame_keys)):
        _fail("d4_a2_shadow_frame_duplicate")
    return tuple(parsed)


def _validate_d4_a2_shadow_binding(record: Any) -> None:
    anchor = _D4_A2_TRUSTED_MODEL_SOURCE
    binding = record.candidate_binding
    if (
        binding.candidate_id != anchor["candidate_id"]
        or binding.model_version != anchor["model_version"]
        or binding.source_git_commit != anchor["source_git_commit"]
        or binding.source_identity_sha256
        != anchor["source_identity_sha256"]
        or binding.candidate_manifest_file_sha256
        != anchor["candidate_manifest_file_sha256"]
        or binding.candidate_manifest_content_sha256
        != anchor["candidate_manifest_content_sha256"]
        or binding.bundle_manifest_sha256
        != anchor["artifact_sha256"]["bundle/manifest.json"]
        or binding.model_state_sha256 != anchor["model_state_sha256"]
    ):
        _fail("d4_a2_shadow_candidate_binding_mismatch")
    permissions = record.permissions.to_dict()
    if any(
        value is not False
        for name, value in permissions.items()
        if name != "schema"
    ):
        _fail("d4_a2_shadow_permission_escalation")
    if (
        record.candidate_executed
        or record.execution_source != "deterministic_rule_fallback"
        or record.rule_fallback_required is not True
    ):
        _fail("d4_a2_shadow_execution_boundary_crossed")


def _summarize_d4_a2_runtime_distribution(
    records: tuple[Any, ...],
) -> dict[str, Any]:
    by_seed: dict[int, list[Any]] = {}
    for record in records:
        by_seed.setdefault(int(record.input_summary.seed), []).append(record)
    aggregate = _summarize_d4_a2_runtime_distribution_group(records)
    binding_ids = {
        str(record.candidate_binding.binding_sha256) for record in records
    }
    if len(binding_ids) != 1:
        _fail("d4_a2_shadow_candidate_binding_mixed")
    aggregate["candidate_binding_sha256"] = next(iter(binding_ids))
    aggregate["seed_diagnostics"] = {
        str(seed): _summarize_d4_a2_runtime_distribution_group(tuple(items))
        for seed, items in sorted(by_seed.items())
    }
    return aggregate


def _summarize_d4_a2_runtime_distribution_group(
    records: tuple[Any, ...],
) -> dict[str, Any]:
    feature_counts: dict[str, int] = {}
    feature_ood_count = 0
    compatible_count = 0
    model_action_count = 0
    rule_fallback_count = 0
    for record in records:
        diagnostic = record.ood_diagnostic
        if diagnostic.feature_ood:
            feature_ood_count += 1
        else:
            compatible_count += 1
        for name, count in diagnostic.feature_violation_counts.items():
            key = str(name)
            feature_counts[key] = feature_counts.get(key, 0) + int(count)
        action_available = bool(
            not diagnostic.feature_ood
            and record.candidate_gate.gate_pass
            and record.projection_structurally_valid
            and record.identifiable_nonzero
            and record.intervention_fields
        )
        model_action_count += int(action_available)
        rule_fallback_count += int(
            record.execution_source == "deterministic_rule_fallback"
            and record.rule_fallback_required
            and not record.candidate_executed
        )
    sample_count = len(records)
    return {
        "audited_snapshot_count": sample_count,
        "finite_record_count": sample_count,
        "nonfinite_record_count": 0,
        "compatible_snapshot_count": compatible_count,
        "feature_ood_snapshot_count": feature_ood_count,
        "model_action_count": model_action_count,
        "missing_model_action_count": sample_count - model_action_count,
        "rule_fallback_count": rule_fallback_count,
        "feature_ood_counts": dict(sorted(feature_counts.items())),
    }


def _load_d5_g1_model_source(
    data: bytes,
    *,
    artifact_root: Path,
    expected_variant: str,
) -> dict[str, Any]:
    payload = _json_object(data)
    _exact(payload, _MODEL_SOURCE_REFERENCE_FIELDS, "model_source_reference")
    if (
        payload["schema_version"]
        != D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION
    ):
        _fail("gate_source_schema_unsupported", payload["schema_version"])
    variant = _text(payload["variant"], "variant")
    if variant != expected_variant:
        _fail("gate_source_variant_mismatch", f"{variant}!={expected_variant}")
    if variant not in _MODEL_SOURCE_REQUIRED_COMPONENTS:
        _fail("model_source_variant_unsupported", variant)

    raw_components = _mapping(
        payload["component_references"],
        "component_references",
    )
    required_components = _MODEL_SOURCE_REQUIRED_COMPONENTS[variant]
    supplied_components = set(raw_components)
    if supplied_components != set(required_components):
        missing = sorted(required_components - supplied_components)
        unexpected = sorted(supplied_components - required_components)
        _fail(
            "model_source_component_coverage_mismatch",
            f"missing={','.join(missing)};unexpected={','.join(unexpected)}",
        )
    if supplied_components != {"d5_graph"}:
        _fail(
            "model_source_component_adapter_unsupported",
            ",".join(sorted(supplied_components)),
        )

    raw_artifacts = _mapping(
        raw_components["d5_graph"],
        "component_references.d5_graph",
    )
    _exact(
        raw_artifacts,
        _D5_G1_MODEL_SOURCE_ARTIFACT_NAMES,
        "component_references.d5_graph",
    )
    artifacts = {
        name: _normalize_reference(
            raw_artifacts[name],
            context=f"component_references.d5_graph.{name}",
        )
        for name in sorted(_D5_G1_MODEL_SOURCE_ARTIFACT_NAMES)
    }
    body = {
        "schema_version": payload["schema_version"],
        "variant": variant,
        "component_references": {"d5_graph": artifacts},
    }
    claimed_content = _sha256_text(
        payload["content_sha256"],
        "content_sha256",
    )
    if _canonical_sha256(body) != claimed_content:
        _fail("gate_source_content_sha256_mismatch")

    root = _resolve_artifact_root(artifact_root)
    resolved = {
        name: _resolve_and_verify(root, reference, label=name)
        for name, reference in artifacts.items()
    }
    anchor = _D5_G1_TRUSTED_MODEL_SOURCE
    if (
        variant != anchor["variant"]
        or anchor["component_id"] != "d5_graph"
    ):
        _fail("d5_g1_model_source_trust_anchor_mismatch", "variant")
    for name, reference in artifacts.items():
        if (
            reference["path"] != anchor["artifact_layout"].get(name)
            or reference["file_sha256"]
            != anchor["artifact_sha256"].get(name)
        ):
            _fail("d5_g1_model_source_trust_anchor_mismatch", name)

    external_inputs = _load_external_inputs(
        resolved["external_audit_input"],
        artifact_root=root,
        anchor=anchor,
    )
    external_originals, source_root = _validate_external_input_layout(
        external_inputs,
        artifact_root=root,
        anchor=anchor,
    )
    try:
        external_result = audit_d5_g1_external_evidence(external_inputs)
    except D5G1ExternalAuditError as exc:
        _fail(f"d5_g1_external_audit.{exc.code}", exc.detail)
    _validate_external_result(external_result, anchor=anchor)
    persisted_external = _json_object(
        resolved["external_audit_output"].read_bytes()
    )
    if persisted_external != external_result:
        _fail("d5_g1_persisted_external_audit_mismatch")
    embedded_external = _json_object(
        resolved["v5_external_audit_evidence"].read_bytes()
    )
    if embedded_external != external_result:
        _fail("d5_g1_embedded_external_audit_mismatch")
    _validate_report_checksums(
        resolved["external_audit_checksums"],
        expected_names=_D5_G1_EXTERNAL_REPORT_CHECKSUM_NAMES,
        json_filename="d5_g1_external_audit.json",
        expected_json_sha256=artifacts["external_audit_output"][
            "file_sha256"
        ],
        label="external_audit",
    )

    post_inputs = _load_post_inputs(
        resolved["post_assembly_input"],
        artifact_root=root,
    )
    post_artifacts = _validate_post_input_layout(
        post_inputs,
        artifact_root=root,
        sidecar_artifacts=artifacts,
        sidecar_resolved=resolved,
    )
    try:
        post_result = audit_d5_g1_post_assembly_bundle(post_inputs)
    except D5G1PostAssemblyAuditError as exc:
        _fail(f"d5_g1_post_assembly_audit.{exc.code}", exc.detail)
    _validate_post_result(post_result, anchor=anchor)
    persisted_post = _json_object(
        resolved["post_assembly_output"].read_bytes()
    )
    if persisted_post != post_result:
        _fail("d5_g1_persisted_post_assembly_audit_mismatch")
    _validate_report_checksums(
        resolved["post_assembly_checksums"],
        expected_names=_D5_G1_POST_REPORT_CHECKSUM_NAMES,
        json_filename="d5_g1_post_assembly_audit.json",
        expected_json_sha256=artifacts["post_assembly_output"][
            "file_sha256"
        ],
        label="post_assembly_audit",
    )
    _validate_d5_g1_cross_audit_identity(
        external_result,
        post_result,
        anchor=anchor,
    )

    # Re-hash every sidecar-named file and every nested producer artifact after
    # both strict auditor calls. This also detects replacement during audit.
    for name, reference in artifacts.items():
        _verify_file_sha256(
            resolved[name],
            reference["file_sha256"],
            name,
        )
    for name, path in external_originals.items():
        _verify_file_sha256(
            path,
            external_inputs.artifacts[name].sha256,
            f"external_original.{name}",
        )
    for name, path in post_artifacts.items():
        _verify_file_sha256(
            path,
            post_inputs.artifacts[name].sha256,
            f"post_assembly_original.{name}",
        )
    _reverify_runtime_source_files(
        source_root,
        external_result,
        anchor=anchor,
    )

    return {
        "source_class": "formal_post_assembly_audit",
        "source_schema_version": (
            D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "source_content_sha256": claimed_content,
        "formal": True,
        "facts": {
            "component_ids": ["d5_graph"],
            "audit_passed": True,
            "model_identity": anchor["model_fingerprint"],
        },
    }


def _load_external_inputs(
    path: Path,
    *,
    artifact_root: Path,
    anchor: Mapping[str, Any],
):
    try:
        inputs = load_d5_g1_external_audit_inputs(
            path,
            repository_root=artifact_root.parent,
        )
    except D5G1ExternalAuditError as exc:
        _fail(f"d5_g1_external_input.{exc.code}", exc.detail)
    if (
        inputs.expected_current_implementation_sha256
        != anchor["runtime_implementation_sha256"]
    ):
        _fail("d5_g1_implementation_lineage_mismatch", "external_input")
    return inputs


def _validate_external_input_layout(
    inputs: Any,
    *,
    artifact_root: Path,
    anchor: Mapping[str, Any],
) -> tuple[dict[str, Path], Path]:
    originals: dict[str, Path] = {}
    prefix = Path(artifact_root.name)
    for name, expected_relative in _D5_G1_EXTERNAL_ORIGINAL_LAYOUT.items():
        artifact = inputs.artifacts[name]
        expected_input_path = (prefix / expected_relative).as_posix()
        if artifact.path != expected_input_path:
            _fail("d5_g1_external_original_layout_mismatch", name)
        path = _resolve_and_verify(
            artifact_root,
            {"path": expected_relative, "file_sha256": artifact.sha256},
            label=f"external_original.{name}",
        )
        if inputs.resolve_artifact(name) != path:
            _fail("d5_g1_external_original_layout_mismatch", name)
        originals[name] = path

    source_relative = anchor["source_root_relative_to_artifact_parent"]
    source_root = _resolve_directory_without_symlink(
        artifact_root.parent,
        source_relative,
        label="d5_runtime_source",
    )
    if inputs.source_root != source_root:
        _fail("d5_g1_source_layout_mismatch")
    return originals, source_root


def _load_post_inputs(path: Path, *, artifact_root: Path):
    try:
        return load_d5_g1_post_assembly_audit_inputs(
            path,
            repository_root=artifact_root,
        )
    except D5G1PostAssemblyAuditError as exc:
        _fail(f"d5_g1_post_assembly_input.{exc.code}", exc.detail)


def _validate_post_input_layout(
    inputs: Any,
    *,
    artifact_root: Path,
    sidecar_artifacts: Mapping[str, Mapping[str, str]],
    sidecar_resolved: Mapping[str, Path],
) -> dict[str, Path]:
    post_artifacts: dict[str, Path] = {}
    for post_name, sidecar_name in _D5_G1_POST_TO_SIDECAR_ARTIFACT.items():
        post_reference = inputs.artifacts[post_name]
        sidecar_reference = sidecar_artifacts[sidecar_name]
        if (
            post_reference.path != sidecar_reference["path"]
            or post_reference.sha256 != sidecar_reference["file_sha256"]
        ):
            _fail("d5_g1_post_assembly_layout_mismatch", post_name)
        path = _resolve_and_verify(
            artifact_root,
            sidecar_reference,
            label=f"post_assembly_original.{post_name}",
        )
        if inputs.resolve_artifact(post_name) != path:
            _fail("d5_g1_post_assembly_layout_mismatch", post_name)
        if path != sidecar_resolved[sidecar_name]:
            _fail("d5_g1_post_assembly_layout_mismatch", post_name)
        post_artifacts[post_name] = path
    return post_artifacts


def _validate_external_result(
    result: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
) -> None:
    if (
        result.get("schema_version") != D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION
        or result.get("status") != "pass"
        or result.get("audit_passed") is not True
        or result.get("fail_closed") is not False
        or result.get("blocker_codes") != []
        or result.get("content_sha256")
        != anchor["external_audit_content_sha256"]
    ):
        _fail("d5_g1_external_audit_not_formal")
    consumer = _mapping(
        result.get("d5_consumer_contract"),
        "external_audit.d5_consumer_contract",
    )
    if (
        consumer.get("schema_version")
        != D5_G1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION
        or consumer.get("d6_external_audit_passed") is not True
        or consumer.get("formal_evaluation") is not True
    ):
        _fail("d5_g1_external_consumer_contract_mismatch")
    _validate_authority_closed(
        result.get("authority"),
        label="external_audit.authority",
    )


def _validate_post_result(
    result: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
) -> None:
    if (
        result.get("schema_version")
        != D5_G1_POST_ASSEMBLY_AUDIT_SCHEMA_VERSION
        or result.get("status") != "pass"
        or result.get("audit_passed") is not True
        or result.get("fail_closed") is not False
        or result.get("blocker_codes") != []
        or result.get("content_sha256")
        != anchor["post_assembly_content_sha256"]
    ):
        _fail("d5_g1_post_assembly_audit_not_formal")
    consumer = _mapping(
        result.get("d5_consumer_contract"),
        "post_assembly.d5_consumer_contract",
    )
    if (
        consumer.get("schema_version")
        != D5_G1_POST_ASSEMBLY_AUDIT_CONSUMER_SCHEMA_VERSION
        or consumer.get("post_assembly_integrity_passed") is not True
    ):
        _fail("d5_g1_post_assembly_consumer_contract_mismatch")
    _validate_authority_closed(
        result.get("authority"),
        label="post_assembly.authority",
    )


def _validate_authority_closed(value: Any, *, label: str) -> None:
    authority = _mapping(value, label)
    for name in _D5_G1_AUTHORITY_FIELDS:
        if authority.get(name) is not False:
            _fail("d5_g1_authority_escalation_attempt", f"{label}.{name}")


def _validate_d5_g1_cross_audit_identity(
    external: Mapping[str, Any],
    post: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
) -> None:
    external_consumer = _mapping(
        external.get("d5_consumer_contract"),
        "external_audit.d5_consumer_contract",
    )
    post_consumer = _mapping(
        post.get("d5_consumer_contract"),
        "post_assembly.d5_consumer_contract",
    )
    expected_model = anchor["model_fingerprint"]
    model_values = {
        external_consumer.get("model_fingerprint"),
        post_consumer.get("model_fingerprint"),
        _mapping(
            post.get("cross_binding"),
            "post_assembly.cross_binding",
        ).get("model_fingerprint"),
    }
    if model_values != {expected_model}:
        _fail("d5_g1_model_identity_mismatch")
    expected_runtime = anchor["runtime_implementation_sha256"]
    runtime_values = {
        external_consumer.get("implementation_sha256"),
        post_consumer.get("runtime_implementation_sha256"),
        _mapping(
            post.get("cross_binding"),
            "post_assembly.cross_binding",
        ).get("runtime_implementation_sha256"),
    }
    if runtime_values != {expected_runtime}:
        _fail("d5_g1_implementation_lineage_mismatch", "cross_audit")


def _validate_report_checksums(
    path: Path,
    *,
    expected_names: frozenset[str],
    json_filename: str,
    expected_json_sha256: str,
    label: str,
) -> None:
    records = _parse_report_checksums(path, label=label)
    if set(records) != set(expected_names):
        _fail(
            "d5_g1_report_checksum_coverage_mismatch",
            label,
        )
    if records.get(json_filename) != expected_json_sha256:
        _fail("d5_g1_report_checksum_json_mismatch", label)


def _parse_report_checksums(path: Path, *, label: str) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        _fail("d5_g1_report_checksums_unavailable", label)
    records: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        parts = line.split("  ")
        if len(parts) != 2:
            _fail(
                "d5_g1_report_checksums_invalid",
                f"{label}:{line_number}",
            )
        digest = _sha256_text(
            parts[0],
            f"{label}.checksums.{line_number}",
        )
        filename = parts[1]
        if (
            not filename
            or Path(filename).name != filename
            or filename in records
        ):
            _fail(
                "d5_g1_report_checksums_invalid",
                f"{label}:{line_number}",
            )
        records[filename] = digest
    return records


def _reverify_runtime_source_files(
    source_root: Path,
    external_result: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
) -> None:
    implementation = _mapping(
        _mapping(
            external_result.get("candidate"),
            "external_audit.candidate",
        ).get("implementation"),
        "external_audit.candidate.implementation",
    )
    if (
        implementation.get("current_implementation_sha256")
        != anchor["runtime_implementation_sha256"]
    ):
        _fail("d5_g1_implementation_lineage_mismatch", "current_runtime")
    source_files = _mapping(
        implementation.get("current_source_files"),
        "external_audit.candidate.implementation.current_source_files",
    )
    for name, digest in source_files.items():
        if Path(name).name != name:
            _fail("d5_g1_runtime_source_filename_invalid", str(name))
        _resolve_and_verify(
            source_root,
            {
                "path": name,
                "file_sha256": _sha256_text(
                    digest,
                    f"runtime_source.{name}",
                ),
            },
            label=f"runtime_source.{name}",
        )


def _load_canonical_seed_source(
    data: bytes,
    *,
    artifact_root: Path,
    expected_variant: str,
) -> dict[str, Any]:
    payload = _json_object(data)
    _exact(payload, _REFERENCE_FIELDS, "canonical_seed_reference")
    if (
        payload["schema_version"]
        != CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION
    ):
        _fail("gate_source_schema_unsupported", payload["schema_version"])
    variant = _text(payload["variant"], "variant")
    if variant != expected_variant:
        _fail("gate_source_variant_mismatch", f"{variant}!={expected_variant}")

    artifacts = _mapping(payload["artifacts"], "artifacts")
    _exact(artifacts, _REFERENCE_ARTIFACT_NAMES, "artifacts")
    normalized_artifacts = {
        name: _normalize_reference(artifacts[name], context=f"artifacts.{name}")
        for name in sorted(_REFERENCE_ARTIFACT_NAMES)
    }
    body = {
        "schema_version": payload["schema_version"],
        "variant": variant,
        "artifacts": normalized_artifacts,
    }
    claimed_content = _sha256_text(
        payload["content_sha256"],
        "content_sha256",
    )
    if _canonical_sha256(body) != claimed_content:
        _fail("gate_source_content_sha256_mismatch")

    root = _resolve_artifact_root(artifact_root)
    resolved = {
        name: _resolve_and_verify(root, reference, label=name)
        for name, reference in normalized_artifacts.items()
    }
    dataset_root = resolved["d3_assignment_manifest"].parents[1]
    expected_paths = {
        "training_seed_registry": (
            dataset_root.parent / "training_seed_registry.json"
        ),
        "d3_assignment_manifest": (
            dataset_root / "d3_assignment" / "dataset_manifest.json"
        ),
        "d4_region_manifest": dataset_root / "d4_region" / "manifest.json",
        "d5_tracklet_graph_manifest": (
            dataset_root / "d5_tracklet_graph" / "manifest.json"
        ),
        "d5_active_vision_manifest": (
            dataset_root / "d5_active_vision" / "manifest.json"
        ),
    }
    for name, expected in expected_paths.items():
        if resolved[name] != expected.resolve(strict=True):
            _fail("canonical_seed_source_layout_mismatch", name)

    try:
        audit = audit_canonical_seed_split_readiness(
            dataset_root,
            resolved["shared_seed_split_registry"],
        )
    except CanonicalSeedSplitAuditError as exc:
        _fail(f"canonical_seed_audit.{exc.code}")
    if (
        audit.get("schema_version")
        != CANONICAL_SEED_SPLIT_READINESS_SCHEMA_VERSION
    ):
        _fail("canonical_seed_audit_schema_mismatch")

    # Detect file replacement during the existing auditor call.
    for name, reference in normalized_artifacts.items():
        _verify_file_sha256(resolved[name], reference["file_sha256"], name)

    training_registry = _json_object(
        resolved["training_seed_registry"].read_bytes()
    )
    repository_dirty = training_registry.get("repository_dirty")
    if not isinstance(repository_dirty, bool):
        _fail("canonical_seed_training_dirty_flag_invalid")

    module_rows = _mapping(audit.get("modules"), "canonical_seed.modules")
    required_modules = _REQUIRED_MODULES[variant]
    module_exact = all(
        _mapping(module_rows.get(name), f"canonical_seed.modules.{name}").get(
            "exact_match"
        )
        is True
        for name in required_modules
    )
    registry = _mapping(audit.get("registry"), "canonical_seed.registry")
    evaluation_count = _nonnegative_int(
        registry.get("reserved_evaluation_seed_count"),
        "canonical_seed.reserved_evaluation_seed_count",
    )
    overlap_count = _nonnegative_int(
        registry.get("training_reserved_overlap_count"),
        "canonical_seed.training_reserved_overlap_count",
    )
    return {
        "source_class": "frozen_seed_registry",
        "source_schema_version": (
            CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "source_content_sha256": claimed_content,
        "formal": repository_dirty is False,
        "facts": {
            "evaluation_seed_count": evaluation_count,
            "training_overlap_count": overlap_count,
            "frozen": module_exact and repository_dirty is False,
        },
    }


def _peek_schema(data: bytes) -> str:
    payload = _json_object(data)
    return _text(payload.get("schema_version"), "schema_version")


def _normalize_reference(value: Any, *, context: str) -> dict[str, str]:
    reference = _mapping(value, context)
    _exact(reference, _ARTIFACT_REFERENCE_FIELDS, context)
    return {
        "path": _text(reference["path"], f"{context}.path"),
        "file_sha256": _sha256_text(
            reference["file_sha256"],
            f"{context}.file_sha256",
        ),
    }


def _resolve_artifact_root(value: Path) -> Path:
    try:
        root = value.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("gate_source_artifact_root_invalid")
    if not root.is_dir():
        _fail("gate_source_artifact_root_not_directory")
    return root


def _resolve_and_verify(
    root: Path,
    reference: Mapping[str, str],
    *,
    label: str,
) -> Path:
    relative = Path(reference["path"])
    if relative.is_absolute() or ".." in relative.parts:
        _fail("gate_source_original_path_escape_rejected", label)
    _reject_symlink_chain(root, relative, label=label)
    unresolved = root / relative
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError:
        _fail("gate_source_original_file_missing", label)
    except (OSError, RuntimeError):
        _fail("gate_source_original_path_invalid", label)
    try:
        resolved.relative_to(root)
    except ValueError:
        _fail("gate_source_original_path_escape_rejected", label)
    if not resolved.is_file():
        _fail("gate_source_original_not_regular_file", label)
    _verify_file_sha256(resolved, reference["file_sha256"], label)
    return resolved


def _resolve_directory_without_symlink(
    root: Path,
    relative_value: str,
    *,
    label: str,
) -> Path:
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        _fail("gate_source_original_path_escape_rejected", label)
    _reject_symlink_chain(root, relative, label=label)
    try:
        resolved = (root / relative).resolve(strict=True)
    except FileNotFoundError:
        _fail("gate_source_original_file_missing", label)
    except (OSError, RuntimeError):
        _fail("gate_source_original_path_invalid", label)
    try:
        resolved.relative_to(root)
    except ValueError:
        _fail("gate_source_original_path_escape_rejected", label)
    if not resolved.is_dir():
        _fail("gate_source_original_not_directory", label)
    return resolved


def _reject_symlink_chain(root: Path, relative: Path, *, label: str) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                _fail("gate_source_original_symlink_rejected", label)
        except OSError:
            _fail("gate_source_original_path_invalid", label)


def _verify_file_sha256(path: Path, expected: str, label: str) -> None:
    try:
        data = path.read_bytes()
    except OSError:
        _fail("gate_source_original_file_read_failed", label)
    if sha256(data).hexdigest() != expected:
        _fail("gate_source_original_file_sha256_mismatch", label)


def _json_object(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail("gate_source_file_invalid", type(exc).__name__)
    if not isinstance(value, dict):
        _fail("gate_source_mapping_required")
    return value


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("gate_source_mapping_required", context)
    return value


def _exact(
    value: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    if set(value) != set(expected):
        _fail(
            "gate_source_fields_mismatch",
            f"{context}:{','.join(sorted(set(value) ^ set(expected)))}",
        )


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("gate_source_text_required", context)
    return value.strip()


def _sha256_text(value: Any, context: str) -> str:
    text = _text(value, context)
    if len(text) != 64 or any(character not in _HEX64 for character in text):
        _fail("gate_source_sha256_required", context)
    return text


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("gate_source_nonnegative_integer_required", context)
    return value


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _reject_json_constant(value: str) -> None:
    _fail("gate_source_nonfinite_json_constant", value)


def _fail(code: str, detail: str | None = None) -> None:
    raise LearningRunSourceAdapterError(code, detail)


__all__ = [
    "CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION",
    "D4_A2_CURRENT_LINEAGE_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION",
    "D4_A2_RUNTIME_DISTRIBUTION_SOURCE_REFERENCE_SCHEMA_VERSION",
    "D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION",
    "LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS",
    "LearningRunSourceAdapterError",
    "load_learning_run_source_evidence_bytes",
]
