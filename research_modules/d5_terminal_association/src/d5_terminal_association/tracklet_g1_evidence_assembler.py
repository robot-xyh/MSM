"""Fail-closed assembly of D5 G1 model bundles from external evidence files."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
from typing import Any, Mapping

from .tracklet_dataset import sha256_file, sha256_json
from .tracklet_model_bundle import (
    CHECKSUMS_FILENAME,
    G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION,
    MANIFEST_FILENAME,
    MODEL_BUNDLE_SCHEMA_VERSION,
    TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION,
    TRACKLET_G1_EXTERNAL_AUTHORITY_FIELDS,
    TRACKLET_G1_MINIMUM_HELDOUT_EPISODES,
    TRACKLET_G1_MINIMUM_SCENARIO_SCALE_CELLS,
    TRACKLET_G1_MINIMUM_UNSEEN_SEEDS,
    TRACKLET_G1_REQUIRED_PAIRED_LINEAGE_RECORD_COUNT,
    TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS,
    WEIGHTS_FILENAME,
    ModelBundleValidationError,
    TrackletG1AdmissionReport,
    TrackletG1AuthorityContract,
    load_tracklet_model_bundle,
)


D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION = (
    "d6.d5-g1-external-audit.v1"
)
D6_EXTERNAL_AUDIT_SCHEMA_VERSION = "d6.d5-g1-external-audit.v2"
D6_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION = (
    "d6.d5-g1-external-audit-consumer.v1"
)
D6_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION = (
    "d6.d5-g1-external-audit-input.v1"
)
D6_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION = (
    "d6.d5-g1-formal-heldout-paired-shadow.v1"
)
HELDOUT_REPORT_SCHEMA_VERSION = "d5.tracklet-heldout-model-evaluation.v1"
PAIRED_SHADOW_REPORT_SCHEMA_VERSION = "d5.tracklet-paired-shadow.v2"
PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION = (
    "d5.tracklet-paired-shadow-lineage.v1"
)

EVIDENCE_DIRECTORY = "evidence"
HELDOUT_EVIDENCE_FILENAME = f"{EVIDENCE_DIRECTORY}/heldout_evaluation.json"
PAIRED_SHADOW_EVIDENCE_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/paired_shadow_report.json"
)
PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/paired_episode_lineage.jsonl"
)
D6_AUDIT_EVIDENCE_FILENAME = (
    f"{EVIDENCE_DIRECTORY}/d6_external_audit.json"
)
G1_BUNDLE_CHECKSUM_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        WEIGHTS_FILENAME,
        HELDOUT_EVIDENCE_FILENAME,
        PAIRED_SHADOW_EVIDENCE_FILENAME,
        PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
        D6_AUDIT_EVIDENCE_FILENAME,
    }
)

_SHA256_LENGTH = 64
_D6_CONSUMER_EVIDENCE_FIELDS = frozenset(
    {
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "dataset_manifest_sha256",
        "formal_evaluation",
        "global_track_id_rewrite_count",
        "heldout_episode_count",
        "heldout_passed",
        "heldout_report_content_sha256",
        "heldout_report_sha256",
        "implementation_sha256",
        "model_fingerprint",
        "online_truth_feature_count",
        "paired_shadow_passed",
        "paired_shadow_report_content_sha256",
        "paired_shadow_report_sha256",
        "same_camera_mutual_exclusion_violation_count",
        "scenario_scale_cell_count",
        "split_sha256",
        "training_set_sha256",
        "unseen_seed_count",
    }
)
_D6_CONSUMER_FIELDS = _D6_CONSUMER_EVIDENCE_FIELDS | frozenset(
    {
        "schema_version",
        "d6_external_audit_passed",
        "failure_reasons",
        "field_availability",
    }
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
        "content_sha256",
        "d5_consumer_contract",
        "evaluated_at_utc",
        "evidence_audit_only",
        "fail_closed",
        "formal_profile_version",
        "input_contract",
        "limitations",
        "schema_version",
        "status",
    }
)
_D6_BOOLEAN_FIELDS = frozenset(
    {
        "formal_evaluation",
        "heldout_passed",
        "paired_shadow_passed",
        "d6_external_audit_passed",
    }
)
_D6_INTEGER_FIELDS = frozenset(
    {
        "unseen_seed_count",
        "heldout_episode_count",
        "scenario_scale_cell_count",
        "online_truth_feature_count",
        "global_track_id_rewrite_count",
        "same_camera_mutual_exclusion_violation_count",
    }
)
_D6_SHA_FIELDS = _D6_CONSUMER_EVIDENCE_FIELDS - _D6_BOOLEAN_FIELDS - _D6_INTEGER_FIELDS - {
    "model_fingerprint"
}


class TrackletG1EvidenceAssemblyError(ValueError):
    """Stable rejection from the D5-specific G1 evidence assembler."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class TrackletG1EvidenceInputs:
    """Explicit source artifacts and caller-frozen file digests."""

    development_bundle_dir: Path
    expected_bundle_manifest_sha256: str
    expected_bundle_weights_sha256: str
    expected_bundle_checksums_sha256: str
    heldout_report_path: Path
    expected_heldout_report_sha256: str
    paired_shadow_report_path: Path
    expected_paired_shadow_report_sha256: str
    paired_shadow_lineage_path: Path
    expected_paired_shadow_lineage_sha256: str
    d6_audit_path: Path
    expected_d6_audit_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "development_bundle_dir",
            "heldout_report_path",
            "paired_shadow_report_path",
            "paired_shadow_lineage_path",
            "d6_audit_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise TrackletG1EvidenceAssemblyError(
                    "input_path_type_invalid", name
                )
            object.__setattr__(self, name, value.expanduser().resolve())
        for name in (
            "expected_bundle_manifest_sha256",
            "expected_bundle_weights_sha256",
            "expected_bundle_checksums_sha256",
            "expected_heldout_report_sha256",
            "expected_paired_shadow_report_sha256",
            "expected_paired_shadow_lineage_sha256",
            "expected_d6_audit_sha256",
        ):
            _strict_sha256(getattr(self, name), f"inputs.{name}")


@dataclass(frozen=True, slots=True)
class TrackletG1AssemblyResult:
    """Published v5 bundle identity."""

    bundle_dir: Path
    manifest_sha256: str
    weights_sha256: str
    heldout_report_sha256: str
    paired_shadow_report_sha256: str
    paired_shadow_lineage_sha256: str
    paired_shadow_lineage_record_count: int
    paired_shadow_lineage_unique_episode_uid_count: int
    d6_external_audit_sha256: str
    g1_assist_eligible: bool = True
    authority_contract_schema_version: str = (
        TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION
    )
    default_model: bool = False
    global_track_id_authority: bool = False
    model_promotion_granted: bool = False
    g1_assist_granted: bool = False
    default_path_change_granted: bool = False
    assignment_authority_granted: bool = False
    failover_authority_granted: bool = False
    control_authority_granted: bool = False

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "bundle_dir": str(self.bundle_dir),
                "manifest_sha256": self.manifest_sha256,
                "weights_sha256": self.weights_sha256,
                "heldout_report_sha256": self.heldout_report_sha256,
                "paired_shadow_report_sha256": (
                    self.paired_shadow_report_sha256
                ),
                "paired_shadow_lineage_sha256": (
                    self.paired_shadow_lineage_sha256
                ),
                "paired_shadow_lineage_record_count": (
                    self.paired_shadow_lineage_record_count
                ),
                "paired_shadow_lineage_unique_episode_uid_count": (
                    self.paired_shadow_lineage_unique_episode_uid_count
                ),
                "d6_external_audit_sha256": self.d6_external_audit_sha256,
                "g1_assist_eligible": self.g1_assist_eligible,
                "authority_contract_schema_version": (
                    self.authority_contract_schema_version
                ),
                "default_model": self.default_model,
                "global_track_id_authority": (
                    self.global_track_id_authority
                ),
                "model_promotion_granted": self.model_promotion_granted,
                "g1_assist_granted": self.g1_assist_granted,
                "default_path_change_granted": (
                    self.default_path_change_granted
                ),
                "assignment_authority_granted": (
                    self.assignment_authority_granted
                ),
                "failover_authority_granted": (
                    self.failover_authority_granted
                ),
                "control_authority_granted": (
                    self.control_authority_granted
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class _JsonArtifact:
    path: Path
    payload: Mapping[str, Any]
    file_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class _LineageArtifact:
    path: Path
    file_sha256: str
    record_count: int
    unique_episode_uid_count: int


@dataclass(frozen=True, slots=True)
class _DevelopmentBundleIdentity:
    root: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    weights_sha256: str
    checksums_sha256: str
    model_fingerprint: str
    implementation_sha256: str
    dataset_manifest_sha256: str
    split_sha256: str
    training_set_sha256: str


def assemble_tracklet_g1_bundle(
    output_bundle_dir: str | Path,
    inputs: TrackletG1EvidenceInputs,
) -> TrackletG1AssemblyResult:
    """Validate five explicit evidence classes and atomically publish one v5."""

    if not isinstance(inputs, TrackletG1EvidenceInputs):
        raise TrackletG1EvidenceAssemblyError(
            "input_contract_type_invalid",
            "inputs must be TrackletG1EvidenceInputs",
        )
    output = Path(output_bundle_dir).expanduser().resolve()
    _validate_output_destination(output)
    _validate_output_separation(output, inputs)

    source = _preflight_development_bundle(inputs)
    heldout = _read_json_artifact(
        inputs.heldout_report_path,
        inputs.expected_heldout_report_sha256,
        "heldout_report",
    )
    paired = _read_json_artifact(
        inputs.paired_shadow_report_path,
        inputs.expected_paired_shadow_report_sha256,
        "paired_shadow_report",
    )
    lineage = _read_lineage_artifact(
        inputs.paired_shadow_lineage_path,
        inputs.expected_paired_shadow_lineage_sha256,
        "paired_shadow_lineage",
    )
    audit = _read_json_artifact(
        inputs.d6_audit_path,
        inputs.expected_d6_audit_sha256,
        "d6_external_audit",
    )
    contract, authority_contract = _validate_evidence_chain(
        source=source,
        heldout=heldout,
        paired=paired,
        lineage=lineage,
        audit=audit,
        require_audit_pass=True,
    )

    try:
        scorer = load_tracklet_model_bundle(source.root)
    except ModelBundleValidationError as exc:
        raise TrackletG1EvidenceAssemblyError(
            f"development_bundle_{exc.code}", str(exc)
        ) from exc
    if scorer.bundle_manifest_sha256 != source.manifest_sha256:
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_manifest_changed",
            source.manifest_sha256,
        )
    if scorer.bundle_weights_sha256 != source.weights_sha256:
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_weights_changed",
            source.weights_sha256,
        )

    report = TrackletG1AdmissionReport(
        model_fingerprint=source.model_fingerprint,
        implementation_sha256=source.implementation_sha256,
        dataset_manifest_sha256=source.dataset_manifest_sha256,
        split_sha256=source.split_sha256,
        training_set_sha256=source.training_set_sha256,
        heldout_report_sha256=heldout.file_sha256,
        heldout_report_content_sha256=heldout.content_sha256,
        paired_shadow_report_sha256=paired.file_sha256,
        paired_shadow_report_content_sha256=paired.content_sha256,
        paired_shadow_lineage_sha256=lineage.file_sha256,
        paired_shadow_lineage_record_count=lineage.record_count,
        paired_shadow_lineage_unique_episode_uid_count=(
            lineage.unique_episode_uid_count
        ),
        d6_external_audit_sha256=audit.file_sha256,
        d6_external_audit_content_sha256=audit.content_sha256,
        formal_evaluation=contract["formal_evaluation"],
        heldout_passed=contract["heldout_passed"],
        paired_shadow_passed=contract["paired_shadow_passed"],
        d6_external_audit_passed=contract["d6_external_audit_passed"],
        unseen_seed_count=contract["unseen_seed_count"],
        heldout_episode_count=contract["heldout_episode_count"],
        scenario_scale_cell_count=contract["scenario_scale_cell_count"],
        online_truth_feature_count=contract["online_truth_feature_count"],
        global_track_id_rewrite_count=contract[
            "global_track_id_rewrite_count"
        ],
        same_camera_mutual_exclusion_violation_count=contract[
            "same_camera_mutual_exclusion_violation_count"
        ],
        failure_reasons=tuple(contract["failure_reasons"]),
        g1_assist_eligible=True,
        authority_contract=authority_contract,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.staging-",
            dir=output.parent,
        )
    )
    try:
        _stage_admitted_bundle(
            staging,
            source=source,
            heldout=heldout,
            paired=paired,
            lineage=lineage,
            audit=audit,
            report=report,
            authority_contract=authority_contract,
        )
        try:
            load_tracklet_model_bundle(staging)
        except ModelBundleValidationError as exc:
            raise TrackletG1EvidenceAssemblyError(
                f"assembled_bundle_{exc.code}", str(exc)
            ) from exc
        _recheck_input_files(source, heldout, paired, lineage, audit)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return TrackletG1AssemblyResult(
        bundle_dir=output,
        manifest_sha256=sha256_file(output / MANIFEST_FILENAME),
        weights_sha256=source.weights_sha256,
        heldout_report_sha256=heldout.file_sha256,
        paired_shadow_report_sha256=paired.file_sha256,
        paired_shadow_lineage_sha256=lineage.file_sha256,
        paired_shadow_lineage_record_count=lineage.record_count,
        paired_shadow_lineage_unique_episode_uid_count=(
            lineage.unique_episode_uid_count
        ),
        d6_external_audit_sha256=audit.file_sha256,
    )


def validate_admitted_bundle_evidence(
    bundle_root: str | Path,
    manifest: Mapping[str, Any],
    admission_report: TrackletG1AdmissionReport,
) -> None:
    """Revalidate every packaged v5 evidence file during each public load."""

    root = Path(bundle_root)
    if not isinstance(manifest, Mapping):
        raise TrackletG1EvidenceAssemblyError(
            "manifest_type_invalid", "v5 manifest must be a mapping"
        )
    source_record = _strict_mapping(
        manifest.get("source_development_bundle"),
        "manifest.source_development_bundle",
    )
    if set(source_record) != {
        "schema_version",
        "manifest_sha256",
        "weights_sha256",
        "checksums_sha256",
        "admission_status",
    }:
        raise TrackletG1EvidenceAssemblyError(
            "source_bundle_fields_mismatch",
            "source development bundle fields differ",
        )
    if source_record["schema_version"] != MODEL_BUNDLE_SCHEMA_VERSION:
        raise TrackletG1EvidenceAssemblyError(
            "source_bundle_schema_mismatch",
            str(source_record["schema_version"]),
        )
    for name in ("manifest_sha256", "weights_sha256", "checksums_sha256"):
        _strict_sha256(source_record[name], f"source_bundle.{name}")
    if source_record["admission_status"] not in {
        "research_candidate_not_default",
        "development_only_fail_closed",
    }:
        raise TrackletG1EvidenceAssemblyError(
            "source_bundle_admission_invalid",
            str(source_record["admission_status"]),
        )

    evidence = _strict_mapping(manifest.get("evidence"), "manifest.evidence")
    if set(evidence) != {
        "heldout",
        "paired_shadow",
        "paired_shadow_lineage",
        "d6_external_audit",
    }:
        raise TrackletG1EvidenceAssemblyError(
            "evidence_fields_mismatch", "v5 evidence fields differ"
        )
    heldout = _read_packaged_json_artifact(
        root,
        evidence["heldout"],
        HELDOUT_EVIDENCE_FILENAME,
        "heldout_report",
    )
    paired = _read_packaged_json_artifact(
        root,
        evidence["paired_shadow"],
        PAIRED_SHADOW_EVIDENCE_FILENAME,
        "paired_shadow_report",
    )
    lineage = _read_packaged_lineage_artifact(
        root,
        evidence["paired_shadow_lineage"],
    )
    audit = _read_packaged_json_artifact(
        root,
        evidence["d6_external_audit"],
        D6_AUDIT_EVIDENCE_FILENAME,
        "d6_external_audit",
    )

    training = _strict_mapping(
        manifest.get("training_dataset"), "manifest.training_dataset"
    )
    code_provenance = _strict_mapping(
        manifest.get("code_provenance"), "manifest.code_provenance"
    )
    weights = _strict_mapping(manifest.get("weights"), "manifest.weights")
    identity = _DevelopmentBundleIdentity(
        root=root,
        manifest=manifest,
        manifest_sha256=source_record["manifest_sha256"],
        weights_sha256=source_record["weights_sha256"],
        checksums_sha256=source_record["checksums_sha256"],
        model_fingerprint=_strict_model_fingerprint(
            weights.get("model_fingerprint"),
            "manifest.weights.model_fingerprint",
        ),
        implementation_sha256=_strict_sha256(
            code_provenance.get("runtime_implementation_sha256"),
            "manifest.code_provenance.runtime_implementation_sha256",
        ),
        dataset_manifest_sha256=_strict_sha256(
            training.get("dataset_manifest_sha256"),
            "manifest.training_dataset.dataset_manifest_sha256",
        ),
        split_sha256=_strict_sha256(
            training.get("split_sha256"),
            "manifest.training_dataset.split_sha256",
        ),
        training_set_sha256=_strict_sha256(
            training.get("training_set_sha256"),
            "manifest.training_dataset.training_set_sha256",
        ),
    )
    if identity.weights_sha256 != sha256_file(root / WEIGHTS_FILENAME):
        raise TrackletG1EvidenceAssemblyError(
            "source_bundle_weights_mismatch",
            identity.weights_sha256,
        )
    contract, authority_contract = _validate_evidence_chain(
        source=identity,
        heldout=heldout,
        paired=paired,
        lineage=lineage,
        audit=audit,
        require_audit_pass=True,
    )
    report = admission_report.to_manifest()
    expected_report = {
        "schema_version": admission_report.schema_version,
        "model_fingerprint": identity.model_fingerprint,
        "implementation_sha256": identity.implementation_sha256,
        "dataset_manifest_sha256": identity.dataset_manifest_sha256,
        "split_sha256": identity.split_sha256,
        "training_set_sha256": identity.training_set_sha256,
        "heldout_report_sha256": heldout.file_sha256,
        "heldout_report_content_sha256": heldout.content_sha256,
        "paired_shadow_report_sha256": paired.file_sha256,
        "paired_shadow_report_content_sha256": paired.content_sha256,
        "paired_shadow_lineage_sha256": lineage.file_sha256,
        "paired_shadow_lineage_record_count": lineage.record_count,
        "paired_shadow_lineage_unique_episode_uid_count": (
            lineage.unique_episode_uid_count
        ),
        "d6_external_audit_sha256": audit.file_sha256,
        "d6_external_audit_content_sha256": audit.content_sha256,
        "formal_evaluation": contract["formal_evaluation"],
        "heldout_passed": contract["heldout_passed"],
        "paired_shadow_passed": contract["paired_shadow_passed"],
        "d6_external_audit_passed": contract["d6_external_audit_passed"],
        "unseen_seed_count": contract["unseen_seed_count"],
        "heldout_episode_count": contract["heldout_episode_count"],
        "scenario_scale_cell_count": contract["scenario_scale_cell_count"],
        "online_truth_feature_count": contract["online_truth_feature_count"],
        "global_track_id_rewrite_count": contract[
            "global_track_id_rewrite_count"
        ],
        "same_camera_mutual_exclusion_violation_count": contract[
            "same_camera_mutual_exclusion_violation_count"
        ],
        "failure_reasons": contract["failure_reasons"],
        "g1_assist_eligible": True,
        "authority_contract": dict(authority_contract.to_manifest()),
    }
    if dict(report) != expected_report:
        raise TrackletG1EvidenceAssemblyError(
            "admission_report_cross_binding_mismatch",
            "embedded report differs from packaged evidence",
        )
    admission = _strict_mapping(
        manifest.get("admission"), "manifest.admission"
    )
    try:
        embedded_authority = TrackletG1AuthorityContract.from_manifest(
            _strict_mapping(
                admission.get("authority_contract"),
                "manifest.admission.authority_contract",
            )
        )
    except (TypeError, ValueError) as exc:
        raise TrackletG1EvidenceAssemblyError(
            "authority_contract_manifest_invalid",
            str(exc),
        ) from exc
    if (
        embedded_authority != authority_contract
        or admission_report.authority_contract != authority_contract
    ):
        raise TrackletG1EvidenceAssemblyError(
            "authority_contract_cross_binding_mismatch",
            "manifest, report, and packaged D6 audit differ",
        )


def _preflight_development_bundle(
    inputs: TrackletG1EvidenceInputs,
) -> _DevelopmentBundleIdentity:
    root = inputs.development_bundle_dir
    if not root.is_dir():
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_missing", str(root)
        )
    paths = {
        "manifest": root / MANIFEST_FILENAME,
        "weights": root / WEIGHTS_FILENAME,
        "checksums": root / CHECKSUMS_FILENAME,
    }
    expected = {
        "manifest": inputs.expected_bundle_manifest_sha256,
        "weights": inputs.expected_bundle_weights_sha256,
        "checksums": inputs.expected_bundle_checksums_sha256,
    }
    actual: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise TrackletG1EvidenceAssemblyError(
                f"development_bundle_{name}_missing", str(path)
            )
        actual[name] = sha256_file(path)
        if actual[name] != expected[name]:
            raise TrackletG1EvidenceAssemblyError(
                f"development_bundle_{name}_sha256_mismatch",
                f"expected {expected[name]}, received {actual[name]}",
            )
    checksums = _read_source_checksums(paths["checksums"])
    if checksums != {
        MANIFEST_FILENAME: actual["manifest"],
        WEIGHTS_FILENAME: actual["weights"],
    }:
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_checksums_invalid",
            "source SHA256SUMS does not bind manifest and weights",
        )
    manifest = _read_json(paths["manifest"], "development_bundle_manifest")
    if manifest.get("schema_version") != MODEL_BUNDLE_SCHEMA_VERSION:
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_schema_mismatch",
            str(manifest.get("schema_version")),
        )
    admission = _strict_mapping(
        manifest.get("admission"), "development_bundle.admission"
    )
    if (
        admission.get("status")
        not in {
            "research_candidate_not_default",
            "development_only_fail_closed",
        }
        or admission.get("default_model") is not False
        or admission.get("g1_assist_eligible") is not False
    ):
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_admission_invalid",
            "source must remain development/shadow only",
        )
    weights = _strict_mapping(
        manifest.get("weights"), "development_bundle.weights"
    )
    if (
        weights.get("filename") != WEIGHTS_FILENAME
        or weights.get("sha256") != actual["weights"]
    ):
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_weights_metadata_mismatch",
            "source weights metadata differs from file",
        )
    training = _strict_mapping(
        manifest.get("training_dataset"),
        "development_bundle.training_dataset",
    )
    code_provenance = _strict_mapping(
        manifest.get("code_provenance"),
        "development_bundle.code_provenance",
    )
    return _DevelopmentBundleIdentity(
        root=root,
        manifest=manifest,
        manifest_sha256=actual["manifest"],
        weights_sha256=actual["weights"],
        checksums_sha256=actual["checksums"],
        model_fingerprint=f"sha256:{actual['weights']}",
        implementation_sha256=_strict_sha256(
            code_provenance.get("runtime_implementation_sha256"),
            "development_bundle.code_provenance.runtime_implementation_sha256",
        ),
        dataset_manifest_sha256=_strict_sha256(
            training.get("dataset_manifest_sha256"),
            "development_bundle.training_dataset.dataset_manifest_sha256",
        ),
        split_sha256=_strict_sha256(
            training.get("split_sha256"),
            "development_bundle.training_dataset.split_sha256",
        ),
        training_set_sha256=_strict_sha256(
            training.get("training_set_sha256"),
            "development_bundle.training_dataset.training_set_sha256",
        ),
    )


def _validate_evidence_chain(
    *,
    source: _DevelopmentBundleIdentity,
    heldout: _JsonArtifact,
    paired: _JsonArtifact,
    lineage: _LineageArtifact,
    audit: _JsonArtifact,
    require_audit_pass: bool,
) -> tuple[Mapping[str, Any], TrackletG1AuthorityContract]:
    _validate_report_schemas(heldout, paired)
    contract, runtime_authority, authority_reason = (
        _validate_d6_contract_structure(audit.payload)
    )
    _validate_paired_lineage_bindings(
        lineage=lineage,
        paired=paired.payload,
        audit=audit.payload,
        contract=contract,
    )
    authority_contract = TrackletG1AuthorityContract(
        d6_external_audit_sha256=audit.file_sha256,
        d6_external_audit_content_sha256=audit.content_sha256,
        evidence_audit_passed=contract["d6_external_audit_passed"],
        evidence_eligible=contract["d6_external_audit_passed"],
        runtime_authority=runtime_authority,
        reason=authority_reason,
    )
    if not contract["d6_external_audit_passed"]:
        if require_audit_pass:
            reasons = ",".join(contract["failure_reasons"])
            raise TrackletG1EvidenceAssemblyError(
                "d6_external_audit_fail_closed", reasons
            )
        return contract, authority_contract

    expected = {
        "bundle_manifest_sha256": source.manifest_sha256,
        "bundle_weights_sha256": source.weights_sha256,
        "model_fingerprint": source.model_fingerprint,
        "implementation_sha256": source.implementation_sha256,
        "dataset_manifest_sha256": source.dataset_manifest_sha256,
        "split_sha256": source.split_sha256,
        "training_set_sha256": source.training_set_sha256,
        "heldout_report_sha256": heldout.file_sha256,
        "heldout_report_content_sha256": heldout.content_sha256,
        "paired_shadow_report_sha256": paired.file_sha256,
        "paired_shadow_report_content_sha256": paired.content_sha256,
    }
    for name, expected_value in expected.items():
        if contract[name] != expected_value:
            raise TrackletG1EvidenceAssemblyError(
                f"evidence_cross_binding_mismatch.{name}",
                f"expected {expected_value}, received {contract[name]}",
            )
    _validate_report_lineage(source, heldout.payload, paired.payload, contract)
    return contract, authority_contract


def _validate_d6_contract_structure(
    audit: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, bool], str]:
    if set(audit) != _D6_TOP_LEVEL_FIELDS:
        raise TrackletG1EvidenceAssemblyError(
            "d6_top_level_fields_mismatch", "external audit fields differ"
        )
    audit_schema = audit.get("schema_version")
    if audit_schema == D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION:
        raise TrackletG1EvidenceAssemblyError(
            "legacy_d6_external_audit_schema_unsupported",
            (
                f"{D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION} retains its "
                "historical authority semantics"
            ),
        )
    if audit_schema != D6_EXTERNAL_AUDIT_SCHEMA_VERSION:
        raise TrackletG1EvidenceAssemblyError(
            "d6_schema_mismatch", str(audit_schema)
        )
    if (
        audit.get("formal_profile_version")
        != D6_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_formal_profile_mismatch",
            str(audit.get("formal_profile_version")),
        )
    if audit.get("evidence_audit_only") is not True:
        raise TrackletG1EvidenceAssemblyError(
            "d6_evidence_scope_invalid",
            "D6 result must be evidence-audit-only",
        )
    for name in ("audit_id", "evaluated_at_utc"):
        if not isinstance(audit.get(name), str) or not audit[name].strip():
            raise TrackletG1EvidenceAssemblyError(
                "d6_string_field_invalid", name
            )

    authority = _strict_mapping(audit.get("authority"), "d6.authority")
    if set(authority) != TRACKLET_G1_EXTERNAL_AUTHORITY_FIELDS:
        raise TrackletG1EvidenceAssemblyError(
            "d6_authority_fields_mismatch", "authority fields differ"
        )
    runtime_authority: dict[str, bool] = {}
    for name in TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS:
        if type(authority[name]) is not bool:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_type_invalid.authority.{name}", "must be bool"
            )
        if authority[name] is not False:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_authority_not_closed.{name}", "must remain false"
            )
        runtime_authority[name] = authority[name]
    if (
        not isinstance(authority["reason"], str)
        or not authority["reason"].strip()
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_authority_reason_invalid", "reason must be non-empty"
        )

    contract = _strict_mapping(
        audit.get("d5_consumer_contract"), "d6.d5_consumer_contract"
    )
    if set(contract) != _D6_CONSUMER_FIELDS:
        raise TrackletG1EvidenceAssemblyError(
            "d6_consumer_fields_mismatch", "consumer fields differ"
        )
    if (
        contract.get("schema_version")
        != D6_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_consumer_schema_mismatch",
            str(contract.get("schema_version")),
        )
    for name in _D6_BOOLEAN_FIELDS:
        if type(contract[name]) is not bool:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_type_invalid.{name}", "must be bool"
            )
    for name in _D6_INTEGER_FIELDS:
        if type(contract[name]) is not int or contract[name] < 0:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_type_invalid.{name}", "must be a non-negative int"
            )
    for name in _D6_SHA_FIELDS:
        _strict_sha256(contract[name], f"d6.consumer.{name}")
    _strict_model_fingerprint(
        contract["model_fingerprint"], "d6.consumer.model_fingerprint"
    )

    availability = _strict_mapping(
        contract.get("field_availability"),
        "d6.consumer.field_availability",
    )
    if set(availability) != _D6_CONSUMER_EVIDENCE_FIELDS:
        raise TrackletG1EvidenceAssemblyError(
            "d6_field_availability_fields_mismatch",
            "field availability fields differ",
        )
    for name in sorted(_D6_CONSUMER_EVIDENCE_FIELDS):
        record = _strict_mapping(
            availability[name], f"d6.field_availability.{name}"
        )
        if set(record) != {"available", "reason"}:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_field_availability_invalid.{name}",
                "availability record fields differ",
            )
        if type(record["available"]) is not bool:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_type_invalid.field_availability.{name}",
                "available must be bool",
            )
        if record["reason"] is not None and not isinstance(
            record["reason"], str
        ):
            raise TrackletG1EvidenceAssemblyError(
                f"d6_type_invalid.field_availability_reason.{name}",
                "reason must be str or null",
            )
        if record["available"] is not True:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_field_unavailable.{name}",
                str(record["reason"]),
            )

    blocker_codes = _strict_string_list(
        audit.get("blocker_codes"), "d6.blocker_codes"
    )
    failure_reasons = _strict_string_list(
        contract.get("failure_reasons"), "d6.failure_reasons"
    )
    if blocker_codes != failure_reasons:
        raise TrackletG1EvidenceAssemblyError(
            "d6_failure_reasons_mismatch",
            "blocker_codes and failure_reasons differ",
        )
    audit_passed = audit.get("audit_passed")
    fail_closed = audit.get("fail_closed")
    if type(audit_passed) is not bool or type(fail_closed) is not bool:
        raise TrackletG1EvidenceAssemblyError(
            "d6_type_invalid.audit_state", "state fields must be bool"
        )
    if contract["d6_external_audit_passed"] is not audit_passed:
        raise TrackletG1EvidenceAssemblyError(
            "d6_audit_state_mismatch",
            "consumer and top-level pass flags differ",
        )
    if audit_passed:
        if (
            audit.get("status") != "pass"
            or fail_closed is not False
            or failure_reasons
        ):
            raise TrackletG1EvidenceAssemblyError(
                "d6_audit_state_invalid", "positive audit state is inconsistent"
            )
    elif (
        audit.get("status") != "fail_closed"
        or fail_closed is not True
        or not failure_reasons
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_audit_state_invalid", "negative audit state is inconsistent"
        )

    input_contract = _strict_mapping(
        audit.get("input_contract"), "d6.input_contract"
    )
    if (
        input_contract.get("schema_version")
        != D6_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_input_contract_schema_mismatch",
            str(input_contract.get("schema_version")),
        )
    implementation = _strict_sha256(
        input_contract.get("expected_current_implementation_sha256"),
        "d6.input_contract.expected_current_implementation_sha256",
    )
    if implementation != contract["implementation_sha256"]:
        raise TrackletG1EvidenceAssemblyError(
            "d6_current_implementation_mismatch",
            "input and consumer implementation digests differ",
        )

    if contract["unseen_seed_count"] < TRACKLET_G1_MINIMUM_UNSEEN_SEEDS:
        raise TrackletG1EvidenceAssemblyError(
            "d6_unseen_seed_count_insufficient",
            str(contract["unseen_seed_count"]),
        )
    if (
        contract["heldout_episode_count"]
        < TRACKLET_G1_MINIMUM_HELDOUT_EPISODES
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_heldout_episode_count_insufficient",
            str(contract["heldout_episode_count"]),
        )
    if (
        contract["scenario_scale_cell_count"]
        < TRACKLET_G1_MINIMUM_SCENARIO_SCALE_CELLS
    ):
        raise TrackletG1EvidenceAssemblyError(
            "d6_scenario_scale_cell_count_insufficient",
            str(contract["scenario_scale_cell_count"]),
        )
    for name in (
        "online_truth_feature_count",
        "global_track_id_rewrite_count",
        "same_camera_mutual_exclusion_violation_count",
    ):
        if contract[name] != 0:
            raise TrackletG1EvidenceAssemblyError(
                f"d6_safety_count_nonzero.{name}", str(contract[name])
            )
    return (
        contract,
        MappingProxyType(runtime_authority),
        authority["reason"],
    )


def _validate_report_schemas(
    heldout: _JsonArtifact,
    paired: _JsonArtifact,
) -> None:
    if heldout.payload.get("schema_version") != HELDOUT_REPORT_SCHEMA_VERSION:
        raise TrackletG1EvidenceAssemblyError(
            "heldout_report_schema_mismatch",
            str(heldout.payload.get("schema_version")),
        )
    if (
        paired.payload.get("schema_version")
        != PAIRED_SHADOW_REPORT_SCHEMA_VERSION
    ):
        raise TrackletG1EvidenceAssemblyError(
            "paired_shadow_report_schema_mismatch",
            str(paired.payload.get("schema_version")),
        )


def _validate_paired_lineage_bindings(
    *,
    lineage: _LineageArtifact,
    paired: Mapping[str, Any],
    audit: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    if (
        lineage.record_count
        != TRACKLET_G1_REQUIRED_PAIRED_LINEAGE_RECORD_COUNT
    ):
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_formal_record_count_mismatch",
            (
                f"{lineage.record_count}!="
                f"{TRACKLET_G1_REQUIRED_PAIRED_LINEAGE_RECORD_COUNT}"
            ),
        )
    if lineage.unique_episode_uid_count != lineage.record_count:
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_unique_episode_uid_count_mismatch",
            (
                f"{lineage.unique_episode_uid_count}!="
                f"{lineage.record_count}"
            ),
        )
    if contract["heldout_episode_count"] != lineage.record_count:
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_d6_consumer_count_mismatch",
            (
                f"{lineage.record_count}!="
                f"{contract['heldout_episode_count']}"
            ),
        )

    paired_lineage = _strict_mapping(
        paired.get("paired_lineage"), "paired.paired_lineage"
    )
    expected_paired_fields = {
        "schema_version",
        "filename",
        "record_count",
        "sha256",
    }
    if set(paired_lineage) != expected_paired_fields:
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_fields_mismatch",
            ",".join(sorted(set(paired_lineage) ^ expected_paired_fields)),
        )
    if (
        paired_lineage.get("schema_version")
        != PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION
    ):
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_schema_mismatch",
            str(paired_lineage.get("schema_version")),
        )
    if (
        paired_lineage.get("filename")
        != Path(PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME).name
    ):
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_filename_mismatch",
            str(paired_lineage.get("filename")),
        )
    paired_sha = _strict_sha256(
        paired_lineage.get("sha256"),
        "paired.paired_lineage.sha256",
    )
    if paired_sha != lineage.file_sha256:
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_sha256_mismatch",
            f"{paired_sha}!={lineage.file_sha256}",
        )
    paired_count = _strict_nonnegative_int(
        paired_lineage.get("record_count"),
        "paired.paired_lineage.record_count",
    )
    if paired_count != lineage.record_count:
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_record_count_mismatch",
            f"{paired_count}!={lineage.record_count}",
        )

    candidate = _strict_mapping(audit.get("candidate"), "d6.candidate")
    d6_lineage = _strict_mapping(
        candidate.get("paired_lineage"),
        "d6.candidate.paired_lineage",
    )
    expected_d6_fields = {
        "available",
        "sha256",
        "record_count",
        "unique_episode_uid_count",
    }
    if set(d6_lineage) != expected_d6_fields:
        raise TrackletG1EvidenceAssemblyError(
            "d6_paired_lineage_fields_mismatch",
            ",".join(sorted(set(d6_lineage) ^ expected_d6_fields)),
        )
    if d6_lineage.get("available") is not True:
        raise TrackletG1EvidenceAssemblyError(
            "d6_paired_lineage_unavailable",
            str(d6_lineage.get("available")),
        )
    d6_sha = _strict_sha256(
        d6_lineage.get("sha256"),
        "d6.candidate.paired_lineage.sha256",
    )
    if d6_sha != lineage.file_sha256:
        raise TrackletG1EvidenceAssemblyError(
            "d6_paired_lineage_sha256_mismatch",
            f"{d6_sha}!={lineage.file_sha256}",
        )
    d6_record_count = _strict_nonnegative_int(
        d6_lineage.get("record_count"),
        "d6.candidate.paired_lineage.record_count",
    )
    if d6_record_count != lineage.record_count:
        raise TrackletG1EvidenceAssemblyError(
            "d6_paired_lineage_record_count_mismatch",
            f"{d6_record_count}!={lineage.record_count}",
        )
    d6_unique_count = _strict_nonnegative_int(
        d6_lineage.get("unique_episode_uid_count"),
        "d6.candidate.paired_lineage.unique_episode_uid_count",
    )
    if d6_unique_count != lineage.unique_episode_uid_count:
        raise TrackletG1EvidenceAssemblyError(
            "d6_paired_lineage_unique_episode_uid_count_mismatch",
            f"{d6_unique_count}!={lineage.unique_episode_uid_count}",
        )


def _validate_report_lineage(
    source: _DevelopmentBundleIdentity,
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    development = _strict_mapping(
        heldout.get("development_model"), "heldout.development_model"
    )
    if development.get("admission_status") not in {
        "research_candidate_not_default",
        "development_only_fail_closed",
    }:
        raise TrackletG1EvidenceAssemblyError(
            "heldout_development_status_invalid",
            str(development.get("admission_status")),
        )
    heldout_expected = {
        "bundle_manifest_sha256": source.manifest_sha256,
        "weights_sha256": source.weights_sha256,
    }
    for name, value in heldout_expected.items():
        if development.get(name) != value:
            raise TrackletG1EvidenceAssemblyError(
                f"heldout_cross_binding_mismatch.{name}",
                f"expected {value}, received {development.get(name)}",
            )
    heldout_training = _strict_mapping(
        development.get("training_dataset"),
        "heldout.development_model.training_dataset",
    )
    for name, value in (
        ("dataset_manifest_sha256", source.dataset_manifest_sha256),
        ("split_sha256", source.split_sha256),
        ("training_set_sha256", source.training_set_sha256),
    ):
        if heldout_training.get(name) != value:
            raise TrackletG1EvidenceAssemblyError(
                f"heldout_cross_binding_mismatch.{name}",
                f"expected {value}, received {heldout_training.get(name)}",
            )
    corpus = _strict_mapping(
        heldout.get("heldout_corpus"), "heldout.heldout_corpus"
    )
    seed_values = corpus.get("seed_values")
    if (
        not isinstance(seed_values, list)
        or any(type(value) is not int for value in seed_values)
        or len(seed_values) != contract["unseen_seed_count"]
        or len(seed_values) != len(set(seed_values))
    ):
        raise TrackletG1EvidenceAssemblyError(
            "heldout_seed_catalog_mismatch",
            "held-out seed catalog differs from D6 contract",
        )
    for report_name, contract_name in (
        ("episode_count", "heldout_episode_count"),
        ("scenario_scale_cell_count", "scenario_scale_cell_count"),
    ):
        if (
            type(corpus.get(report_name)) is not int
            or corpus[report_name] != contract[contract_name]
        ):
            raise TrackletG1EvidenceAssemblyError(
                f"heldout_count_mismatch.{report_name}",
                str(corpus.get(report_name)),
            )
    assessment = _strict_mapping(
        heldout.get("heldout_assessment"), "heldout.heldout_assessment"
    )
    if (
        assessment.get("passed") is not contract["heldout_passed"]
        or assessment.get("authority_enabled") is not False
    ):
        raise TrackletG1EvidenceAssemblyError(
            "heldout_assessment_mismatch",
            "held-out pass or authority state differs",
        )
    safety = _strict_mapping(
        heldout.get("identity_and_truth_safety"),
        "heldout.identity_and_truth_safety",
    )
    if (
        safety.get("online_truth_feature_count")
        != contract["online_truth_feature_count"]
        or safety.get("global_track_id_created_or_rebound") is not False
    ):
        raise TrackletG1EvidenceAssemblyError(
            "heldout_safety_mismatch",
            "held-out truth or identity safety differs",
        )

    input_spec = _strict_mapping(
        paired.get("input_spec"), "paired.input_spec"
    )
    input_hashes = _strict_mapping(
        input_spec.get("expected_hashes"),
        "paired.input_spec.expected_hashes",
    )
    paired_expected = {
        "bundle_manifest_sha256": source.manifest_sha256,
        "bundle_weights_sha256": source.weights_sha256,
        "heldout_report_sha256": contract["heldout_report_sha256"],
        "heldout_report_content_sha256": contract[
            "heldout_report_content_sha256"
        ],
    }
    for name, value in paired_expected.items():
        if input_hashes.get(name) != value:
            raise TrackletG1EvidenceAssemblyError(
                f"paired_cross_binding_mismatch.{name}",
                f"expected {value}, received {input_hashes.get(name)}",
            )
    if (
        input_spec.get("require_full_profile") is not True
        or paired.get("execution_completed") is not True
        or paired.get("input_artifacts_unchanged") is not True
    ):
        raise TrackletG1EvidenceAssemblyError(
            "paired_formal_state_invalid",
            "paired-shadow execution is not authoritative and complete",
        )
    totals = _strict_mapping(paired.get("totals"), "paired.totals")
    for report_name, contract_name in (
        ("seed_count", "unseen_seed_count"),
        ("episode_count", "heldout_episode_count"),
        ("scenario_scale_cell_count", "scenario_scale_cell_count"),
    ):
        if (
            type(totals.get(report_name)) is not int
            or totals[report_name] != contract[contract_name]
        ):
            raise TrackletG1EvidenceAssemblyError(
                f"paired_count_mismatch.{report_name}",
                str(totals.get(report_name)),
            )
    paired_assessment = _strict_mapping(
        paired.get("paired_shadow_assessment"),
        "paired.paired_shadow_assessment",
    )
    if paired_assessment.get("passed") is not contract["paired_shadow_passed"]:
        raise TrackletG1EvidenceAssemblyError(
            "paired_assessment_mismatch",
            "paired-shadow pass differs from D6 contract",
        )
    paired_safety = _strict_mapping(
        paired.get("identity_and_truth_safety"),
        "paired.identity_and_truth_safety",
    )
    for name in (
        "online_truth_feature_count",
        "global_track_id_rewrite_count",
        "same_camera_mutual_exclusion_violation_count",
    ):
        if paired_safety.get(name) != contract[name]:
            raise TrackletG1EvidenceAssemblyError(
                f"paired_safety_mismatch.{name}",
                str(paired_safety.get(name)),
            )
    authority = _strict_mapping(
        paired.get("authority"), "paired.authority"
    )
    for name in ("g1", "assist", "authority"):
        if authority.get(name) is not False:
            raise TrackletG1EvidenceAssemblyError(
                f"paired_authority_not_closed.{name}", str(authority.get(name))
            )


def _stage_admitted_bundle(
    staging: Path,
    *,
    source: _DevelopmentBundleIdentity,
    heldout: _JsonArtifact,
    paired: _JsonArtifact,
    lineage: _LineageArtifact,
    audit: _JsonArtifact,
    report: TrackletG1AdmissionReport,
    authority_contract: TrackletG1AuthorityContract,
) -> None:
    evidence_dir = staging / EVIDENCE_DIRECTORY
    evidence_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source.root / WEIGHTS_FILENAME, staging / WEIGHTS_FILENAME)
    shutil.copyfile(heldout.path, staging / HELDOUT_EVIDENCE_FILENAME)
    shutil.copyfile(paired.path, staging / PAIRED_SHADOW_EVIDENCE_FILENAME)
    shutil.copyfile(
        lineage.path,
        staging / PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
    )
    shutil.copyfile(audit.path, staging / D6_AUDIT_EVIDENCE_FILENAME)

    manifest = json.loads(_canonical_json_bytes(source.manifest))
    manifest["schema_version"] = G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION
    manifest["source_development_bundle"] = {
        "schema_version": MODEL_BUNDLE_SCHEMA_VERSION,
        "manifest_sha256": source.manifest_sha256,
        "weights_sha256": source.weights_sha256,
        "checksums_sha256": source.checksums_sha256,
        "admission_status": source.manifest["admission"]["status"],
    }
    manifest["weights"]["model_fingerprint"] = source.model_fingerprint
    manifest["evidence"] = {
        "heldout": _evidence_record(HELDOUT_EVIDENCE_FILENAME, heldout),
        "paired_shadow": _evidence_record(
            PAIRED_SHADOW_EVIDENCE_FILENAME, paired
        ),
        "paired_shadow_lineage": {
            "filename": PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
            "sha256": lineage.file_sha256,
            "record_count": lineage.record_count,
            "unique_episode_uid_count": (
                lineage.unique_episode_uid_count
            ),
        },
        "d6_external_audit": _evidence_record(
            D6_AUDIT_EVIDENCE_FILENAME, audit
        ),
    }
    manifest["admission"] = {
        "status": "g1_evidence_eligible_not_authorized",
        "default_model": False,
        "g1_assist_eligible": True,
        "global_track_id_authority": False,
        "authority_contract": dict(authority_contract.to_manifest()),
        "report": dict(report.to_manifest()),
    }
    _write_bytes(staging / MANIFEST_FILENAME, _canonical_json_bytes(manifest))
    checksums = {
        filename: sha256_file(staging / filename)
        for filename in sorted(G1_BUNDLE_CHECKSUM_FILES)
    }
    checksum_text = "".join(
        f"{checksums[filename]}  {filename}\n"
        for filename in sorted(checksums)
    )
    _write_bytes(
        staging / CHECKSUMS_FILENAME, checksum_text.encode("ascii")
    )


def _evidence_record(
    filename: str, artifact: _JsonArtifact
) -> dict[str, str]:
    return {
        "filename": filename,
        "sha256": artifact.file_sha256,
        "content_sha256": artifact.content_sha256,
    }


def _read_packaged_json_artifact(
    root: Path,
    record_value: Any,
    required_filename: str,
    artifact_id: str,
) -> _JsonArtifact:
    record = _strict_mapping(record_value, f"evidence.{artifact_id}")
    if set(record) != {"filename", "sha256", "content_sha256"}:
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_record_fields_mismatch.{artifact_id}",
            "evidence record fields differ",
        )
    if record.get("filename") != required_filename:
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_filename_mismatch.{artifact_id}",
            str(record.get("filename")),
        )
    artifact = _read_json_artifact(
        root / required_filename,
        _strict_sha256(record.get("sha256"), f"evidence.{artifact_id}.sha256"),
        artifact_id,
    )
    expected_content = _strict_sha256(
        record.get("content_sha256"),
        f"evidence.{artifact_id}.content_sha256",
    )
    if artifact.content_sha256 != expected_content:
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_content_cross_binding_mismatch.{artifact_id}",
            f"expected {expected_content}, received {artifact.content_sha256}",
        )
    return artifact


def _read_packaged_lineage_artifact(
    root: Path,
    record_value: Any,
) -> _LineageArtifact:
    artifact_id = "paired_shadow_lineage"
    record = _strict_mapping(record_value, f"evidence.{artifact_id}")
    required_fields = {
        "filename",
        "sha256",
        "record_count",
        "unique_episode_uid_count",
    }
    if set(record) != required_fields:
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_record_fields_mismatch.{artifact_id}",
            "evidence record fields differ",
        )
    if (
        record.get("filename")
        != PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME
    ):
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_filename_mismatch.{artifact_id}",
            str(record.get("filename")),
        )
    artifact = _read_lineage_artifact(
        root / PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
        _strict_sha256(
            record.get("sha256"),
            f"evidence.{artifact_id}.sha256",
        ),
        artifact_id,
    )
    expected_record_count = _strict_nonnegative_int(
        record.get("record_count"),
        f"evidence.{artifact_id}.record_count",
    )
    expected_unique_count = _strict_nonnegative_int(
        record.get("unique_episode_uid_count"),
        f"evidence.{artifact_id}.unique_episode_uid_count",
    )
    if artifact.record_count != expected_record_count:
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_record_count_mismatch.{artifact_id}",
            f"{artifact.record_count}!={expected_record_count}",
        )
    if artifact.unique_episode_uid_count != expected_unique_count:
        raise TrackletG1EvidenceAssemblyError(
            f"evidence_unique_episode_uid_count_mismatch.{artifact_id}",
            (
                f"{artifact.unique_episode_uid_count}!="
                f"{expected_unique_count}"
            ),
        )
    return artifact


def _read_json_artifact(
    path: Path,
    expected_sha256: str,
    artifact_id: str,
) -> _JsonArtifact:
    _strict_sha256(expected_sha256, f"{artifact_id}.expected_sha256")
    if not path.is_file():
        raise TrackletG1EvidenceAssemblyError(
            f"input_missing.{artifact_id}", str(path)
        )
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha256:
        raise TrackletG1EvidenceAssemblyError(
            f"input_sha256_mismatch.{artifact_id}",
            f"expected {expected_sha256}, received {actual_sha}",
        )
    payload = _read_json(path, artifact_id)
    claimed_content = _strict_sha256(
        payload.get("content_sha256"), f"{artifact_id}.content_sha256"
    )
    calculated_content = _content_sha256(payload)
    if claimed_content != calculated_content:
        raise TrackletG1EvidenceAssemblyError(
            f"input_content_sha256_mismatch.{artifact_id}",
            f"expected {claimed_content}, received {calculated_content}",
        )
    return _JsonArtifact(
        path=path,
        payload=MappingProxyType(payload),
        file_sha256=actual_sha,
        content_sha256=calculated_content,
    )


def _read_lineage_artifact(
    path: Path,
    expected_sha256: str,
    artifact_id: str,
) -> _LineageArtifact:
    _strict_sha256(expected_sha256, f"{artifact_id}.expected_sha256")
    if not path.is_file():
        raise TrackletG1EvidenceAssemblyError(
            f"input_missing.{artifact_id}", str(path)
        )
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha256:
        raise TrackletG1EvidenceAssemblyError(
            f"input_sha256_mismatch.{artifact_id}",
            f"expected {expected_sha256}, received {actual_sha}",
        )

    episode_uids: set[str] = set()
    record_count = 0
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    raise TrackletG1EvidenceAssemblyError(
                        "paired_lineage_blank_record",
                        f"line {line_number}",
                    )
                try:
                    record = json.loads(
                        line,
                        parse_constant=lambda token: _reject_json_constant(
                            token
                        ),
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    raise TrackletG1EvidenceAssemblyError(
                        "paired_lineage_record_json_invalid",
                        f"line {line_number}: {exc}",
                    ) from exc
                if not isinstance(record, dict):
                    raise TrackletG1EvidenceAssemblyError(
                        "paired_lineage_record_type_invalid",
                        f"line {line_number}",
                    )
                episode_uid = record.get("episode_uid")
                if (
                    not isinstance(episode_uid, str)
                    or not episode_uid.strip()
                ):
                    raise TrackletG1EvidenceAssemblyError(
                        "paired_lineage_episode_uid_invalid",
                        f"line {line_number}",
                    )
                if episode_uid in episode_uids:
                    raise TrackletG1EvidenceAssemblyError(
                        "paired_lineage_duplicate_episode_uid",
                        f"line {line_number}: {episode_uid}",
                    )
                episode_uids.add(episode_uid)
                record_count += 1
    except TrackletG1EvidenceAssemblyError:
        raise
    except (OSError, UnicodeError) as exc:
        raise TrackletG1EvidenceAssemblyError(
            "paired_lineage_read_failed", str(path)
        ) from exc
    return _LineageArtifact(
        path=path,
        file_sha256=actual_sha,
        record_count=record_count,
        unique_episode_uid_count=len(episode_uids),
    )


def _recheck_input_files(
    source: _DevelopmentBundleIdentity,
    heldout: _JsonArtifact,
    paired: _JsonArtifact,
    lineage: _LineageArtifact,
    audit: _JsonArtifact,
) -> None:
    expected = {
        source.root / MANIFEST_FILENAME: source.manifest_sha256,
        source.root / WEIGHTS_FILENAME: source.weights_sha256,
        source.root / CHECKSUMS_FILENAME: source.checksums_sha256,
        heldout.path: heldout.file_sha256,
        paired.path: paired.file_sha256,
        lineage.path: lineage.file_sha256,
        audit.path: audit.file_sha256,
    }
    for path, digest in expected.items():
        if not path.is_file() or sha256_file(path) != digest:
            raise TrackletG1EvidenceAssemblyError(
                "input_changed_during_assembly", str(path)
            )


def _validate_output_destination(output: Path) -> None:
    if output.exists():
        if not output.is_dir():
            raise TrackletG1EvidenceAssemblyError(
                "output_not_directory", str(output)
            )
        try:
            nonempty = next(output.iterdir(), None) is not None
        except OSError as exc:
            raise TrackletG1EvidenceAssemblyError(
                "output_unreadable", str(output)
            ) from exc
        if nonempty:
            raise TrackletG1EvidenceAssemblyError(
                "output_not_empty", str(output)
            )


def _validate_output_separation(
    output: Path,
    inputs: TrackletG1EvidenceInputs,
) -> None:
    source_paths = (
        inputs.development_bundle_dir,
        inputs.heldout_report_path,
        inputs.paired_shadow_report_path,
        inputs.paired_shadow_lineage_path,
        inputs.d6_audit_path,
    )
    for source in source_paths:
        if (
            output == source
            or output.is_relative_to(source)
            or source.is_relative_to(output)
        ):
            raise TrackletG1EvidenceAssemblyError(
                "output_overlaps_input", str(source)
            )


def _read_source_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise TrackletG1EvidenceAssemblyError(
            "development_bundle_checksums_invalid", str(path)
        ) from exc
    result: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2:
            raise TrackletG1EvidenceAssemblyError(
                "development_bundle_checksums_invalid", line
            )
        digest, filename = parts
        _strict_sha256(digest, f"development_bundle.checksums.{filename}")
        if filename in result or filename not in {
            MANIFEST_FILENAME,
            WEIGHTS_FILENAME,
        }:
            raise TrackletG1EvidenceAssemblyError(
                "development_bundle_checksums_invalid", filename
            )
        result[filename] = digest
    return result


def _read_json(path: Path, artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_json_constant(token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise TrackletG1EvidenceAssemblyError(
            f"input_json_invalid.{artifact_id}", str(path)
        ) from exc
    if not isinstance(value, dict):
        raise TrackletG1EvidenceAssemblyError(
            f"input_json_invalid.{artifact_id}", "root must be an object"
        )
    return value


def _content_sha256(payload: Mapping[str, Any]) -> str:
    value = dict(payload)
    value.pop("content_sha256", None)
    return sha256_json(value)


def _strict_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrackletG1EvidenceAssemblyError(
            f"type_invalid.{name}", "must be an object"
        )
    return value


def _strict_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TrackletG1EvidenceAssemblyError(
            f"hash_invalid.{name}", "must be lowercase SHA-256"
        )
    return value


def _strict_nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise TrackletG1EvidenceAssemblyError(
            f"type_invalid.{name}", "must be a non-negative int"
        )
    return value


def _strict_model_fingerprint(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise TrackletG1EvidenceAssemblyError(
            f"model_fingerprint_invalid.{name}",
            "must start with sha256:",
        )
    _strict_sha256(value.removeprefix("sha256:"), name)
    return value


def _strict_string_list(value: Any, name: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise TrackletG1EvidenceAssemblyError(
            f"type_invalid.{name}",
            "must be a unique list of non-empty strings",
        )
    return list(value)


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, value: bytes) -> None:
    path.write_bytes(value)


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


__all__ = [
    "D6_AUDIT_EVIDENCE_FILENAME",
    "D6_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION",
    "D6_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION",
    "D6_EXTERNAL_AUDIT_SCHEMA_VERSION",
    "D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION",
    "EVIDENCE_DIRECTORY",
    "G1_BUNDLE_CHECKSUM_FILES",
    "HELDOUT_EVIDENCE_FILENAME",
    "PAIRED_SHADOW_EVIDENCE_FILENAME",
    "PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME",
    "PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION",
    "TrackletG1AssemblyResult",
    "TrackletG1EvidenceAssemblyError",
    "TrackletG1EvidenceInputs",
    "assemble_tracklet_g1_bundle",
    "validate_admitted_bundle_evidence",
]
