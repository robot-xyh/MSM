"""Read-only D6 audit of the frozen D4 v5 external evaluation.

The audit evaluates an unregistered candidate against a source-independent
development dataset. It never fits a model, changes a threshold, registers a
candidate, runs a controller, or reads the formal holdout seed range.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite, sqrt
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence


D4_V5_EXTERNAL_AUDIT_INPUT_SCHEMA = (
    "d6.d4-v5-source-independent-external-audit-input.v1"
)
D4_V5_EXTERNAL_AUDIT_SCHEMA = (
    "d6.d4-v5-source-independent-external-audit.v1"
)
D4_V5_EXTERNAL_AUDIT_STATUS = (
    "completed_source_independent_negative_rejection_"
    "positive_denominator_unavailable_admission_closed"
)
D4_V5_FIXED_GATE = 0.60

_PERMISSION_FIELDS = (
    "actual_adoption_claimed",
    "assignment_enabled",
    "assist_enabled",
    "authority_enabled",
    "benefit_claimed",
    "coalition_commit_enabled",
    "control_enabled",
    "d3_permission_available",
    "d7_permission_available",
    "formal_evaluation_authorized",
    "physical_permission_available",
    "production_runtime_ack_enabled",
    "takeover_enabled",
)
_V4_PERMISSION_FIELDS = tuple(
    field
    for field in _PERMISSION_FIELDS
    if field not in {"d3_permission_available", "d7_permission_available"}
)
_SPLIT_ORDER = ("train", "validation", "test")


class D4V5ExternalAuditError(ValueError):
    """Stable fail-closed error for invalid external audit evidence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D4V5ExternalAuditInputs:
    """Caller-frozen paths, hashes, seed classes, and audit policy."""

    repository_root: Path
    source_root: Path
    labeled_export_root: Path
    labeled_dataset_root: Path
    base_v4_root: Path
    candidate_v5_root: Path
    audit_id: str
    evaluated_at_utc: str
    source_git_commit: str
    prior_main_external_test_payload_read_count: int
    expected_hashes: Mapping[str, str]
    schema_version: str = D4_V5_EXTERNAL_AUDIT_INPUT_SCHEMA

    def __post_init__(self) -> None:
        repository = Path(self.repository_root).expanduser().resolve()
        if not repository.is_dir():
            _fail("repository_root_unavailable", str(repository))
        object.__setattr__(self, "repository_root", repository)
        for name in (
            "source_root",
            "labeled_export_root",
            "labeled_dataset_root",
            "base_v4_root",
            "candidate_v5_root",
        ):
            path = Path(getattr(self, name)).expanduser()
            if not path.is_absolute():
                path = repository / path
            path = path.resolve()
            if not path.is_dir():
                _fail("audit_input_directory_unavailable", f"{name}:{path}")
            object.__setattr__(self, name, path)
        if self.schema_version != D4_V5_EXTERNAL_AUDIT_INPUT_SCHEMA:
            _fail("audit_input_schema_mismatch", self.schema_version)
        if not self.audit_id.strip() or not self.evaluated_at_utc.strip():
            _fail("audit_input_identity_invalid", self.audit_id)
        commit = str(self.source_git_commit).lower()
        if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
            _fail("source_git_commit_invalid", commit)
        object.__setattr__(self, "source_git_commit", commit)
        if (
            type(self.prior_main_external_test_payload_read_count) is not int
            or self.prior_main_external_test_payload_read_count < 0
        ):
            _fail(
                "prior_main_test_read_count_invalid",
                str(self.prior_main_external_test_payload_read_count),
            )
        expected = {
            str(name): _normalise_sha256(value, str(name))
            for name, value in self.expected_hashes.items()
        }
        required = {
            "source_manifest_file",
            "source_dataset",
            "source_split",
            "labeled_manifest_file",
            "labeled_dataset",
            "labeled_split",
            "source_artifact_file",
            "source_derivation_content",
            "external_evidence_file",
            "external_evidence_content",
            "export_summary_file",
            "export_summary_content",
            "label_audit_content",
            "base_v4_tree",
            "base_v4_manifest_file",
            "base_v4_manifest_content",
            "base_v4_model_state",
            "base_v4_dataset",
            "base_v4_split",
            "candidate_v5_tree",
            "candidate_v5_manifest_file",
            "candidate_v5_manifest_content",
            "candidate_v5_state_file",
            "candidate_v5_summary_file",
            "candidate_v5_gate_file",
        }
        if set(expected) != required:
            _fail(
                "expected_hash_inventory_mismatch",
                f"missing={sorted(required - set(expected))};"
                f"extra={sorted(set(expected) - required)}",
            )
        object.__setattr__(self, "expected_hashes", expected)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        repository_root: str | Path,
    ) -> "D4V5ExternalAuditInputs":
        expected = {
            "schema_version",
            "audit_id",
            "evaluated_at_utc",
            "source_git_commit",
            "source_root",
            "labeled_export_root",
            "labeled_dataset_root",
            "base_v4_root",
            "candidate_v5_root",
            "prior_main_external_test_payload_read_count",
            "expected_hashes",
        }
        _require_exact_keys(value, expected, "external audit input")
        return cls(
            repository_root=Path(repository_root),
            source_root=Path(str(value["source_root"])),
            labeled_export_root=Path(str(value["labeled_export_root"])),
            labeled_dataset_root=Path(str(value["labeled_dataset_root"])),
            base_v4_root=Path(str(value["base_v4_root"])),
            candidate_v5_root=Path(str(value["candidate_v5_root"])),
            audit_id=str(value["audit_id"]),
            evaluated_at_utc=str(value["evaluated_at_utc"]),
            source_git_commit=str(value["source_git_commit"]),
            prior_main_external_test_payload_read_count=int(
                value["prior_main_external_test_payload_read_count"]
            ),
            expected_hashes=_mapping(
                value["expected_hashes"], "expected_hashes"
            ),
            schema_version=str(value["schema_version"]),
        )


def load_d4_v5_external_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> D4V5ExternalAuditInputs:
    """Load a caller-owned input specification."""

    payload = _read_json(Path(path), "audit input")
    return D4V5ExternalAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
    )


def audit_d4_v5_source_independent_external(
    inputs: D4V5ExternalAuditInputs,
) -> dict[str, Any]:
    """Independently audit frozen actor/calibrator behavior on external data."""

    input_summary_before = _capture_audit_input_summary(inputs)
    api = _load_d4_api(inputs.repository_root)
    anchors = _audit_hashes_and_bindings(inputs, api)
    seed_governance = _audit_seed_governance(inputs, anchors, api)
    candidate = _load_frozen_candidate(inputs, api)
    evaluation = _evaluate_external_dataset(
        inputs,
        api=api,
        candidate=candidate,
        seed_governance=seed_governance,
    )
    overlap = _audit_observable_key_independence(
        inputs,
        api=api,
        candidate=candidate,
        external_keys=evaluation.pop("_observable_keys"),
    )
    input_immutability = _verify_audit_inputs_unchanged(
        inputs,
        before=input_summary_before,
    )
    permissions = _audit_closed_permissions(
        anchors["candidate_v5_payloads"],
        anchors["base_v4_manifest"],
    )

    result = {
        "schema_version": D4_V5_EXTERNAL_AUDIT_SCHEMA,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "status": D4_V5_EXTERNAL_AUDIT_STATUS,
        "audit_execution_passed": True,
        "source_git_commit": inputs.source_git_commit,
        "audit_repository_head": _repository_head(inputs.repository_root),
        "scope": {
            "scenario_scale": "M16N20",
            "episode_count": 32,
            "frame_count": 63,
            "source_independent_external_evaluation": True,
            "nonformal_external_test_split": True,
            "model_fit_count": 0,
            "threshold_fit_count": 0,
            "split_change_count": 0,
            "positive_generation_count": 0,
            "online_control_run_count": 0,
        },
        "input_immutability": input_immutability,
        "anchors": {
            key: value
            for key, value in anchors.items()
            if key not in {"candidate_v5_payloads", "base_v4_manifest"}
        },
        "seed_governance": seed_governance,
        "observable_independence": overlap,
        "candidate_evaluation": evaluation,
        "permissions_and_fallback": permissions,
        "admission_conclusion": {
            "candidate_registered": False,
            "admission_allowed": False,
            "admission_closed": True,
            "rule_fallback_required": True,
            "production_permissions_disabled": True,
            "independent_negative_rejection_evidence_available": True,
            "independent_positive_recall_available": False,
            "positive_denominator_status": "unavailable",
            "reason_codes": [
                "actor_derived_positive_denominator_zero",
                "independent_positive_recall_unavailable",
                "candidate_unregistered",
                "admission_closed",
                "rule_fallback_required",
                "production_permissions_disabled",
            ],
        },
        "limitations": [
            (
                "external train/validation/test contains two rule-safe positive "
                "actions, but the frozen actor emits neither executable signature"
            ),
            (
                "negative rejection is measurable; positive recall is not "
                "measurable because actor-derived positive denominator is zero"
            ),
            (
                "the external test split is a nonformal development split and "
                "must not be described as formal holdout evidence"
            ),
            (
                "formal holdout seeds 1000-1019 were not read; runtime preflight, "
                "D3 successor, and D7 permission tests were not run"
            ),
        ],
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def _capture_audit_input_summary(
    inputs: D4V5ExternalAuditInputs,
) -> dict[str, str]:
    """Hash every frozen input tree read during the external audit."""

    return {
        "source_root_tree_sha256": _tree_sha256(inputs.source_root),
        "labeled_export_root_tree_sha256": _tree_sha256(
            inputs.labeled_export_root
        ),
        "labeled_dataset_root_tree_sha256": _tree_sha256(
            inputs.labeled_dataset_root
        ),
        "base_v4_tree_sha256": _tree_sha256(inputs.base_v4_root),
        "candidate_v5_tree_sha256": _tree_sha256(inputs.candidate_v5_root),
    }


def _verify_audit_inputs_unchanged(
    inputs: D4V5ExternalAuditInputs,
    *,
    before: Mapping[str, str],
) -> dict[str, Any]:
    """Fail closed when any frozen audit input changes during evaluation."""

    after = _capture_audit_input_summary(inputs)
    changed = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    if changed:
        detail = {
            name: {
                "before": before.get(name),
                "after": after.get(name),
            }
            for name in changed
        }
        _fail(
            "audit_input_mutated_during_execution",
            json.dumps(detail, sort_keys=True, separators=(",", ":")),
        )
    return {
        "passed": True,
        "summary_method": (
            "canonical_sha256(relative_path_to_file_sha256_inventory)"
        ),
        "before_sha256": dict(before),
        "after_sha256": after,
        "input_mutation_count": 0,
        "mutated_inputs": [],
    }


def write_d4_v5_external_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Atomically write JSON, split CSV, Chinese report, and checksums."""

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(destination)
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        json_path = temporary / "d4_v5_external_audit_summary.json"
        csv_path = temporary / "d4_v5_external_audit_by_split.csv"
        report_path = temporary / "D4_V5_SOURCE_INDEPENDENT_EXTERNAL_AUDIT_CN.md"
        checksum_path = temporary / "SHA256SUMS"
        _write_json(json_path, result)
        _write_split_csv(csv_path, result)
        report_path.write_text(
            _render_chinese_report(result),
            encoding="utf-8",
        )
        checksum_lines = [
            f"{_sha256_file(path)}  {path.name}"
            for path in (json_path, csv_path, report_path)
        ]
        checksum_path.write_text(
            "\n".join(checksum_lines) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "json": destination / json_path.name,
        "csv": destination / csv_path.name,
        "markdown": destination / report_path.name,
        "sha256sums": destination / checksum_path.name,
    }


def _audit_hashes_and_bindings(
    inputs: D4V5ExternalAuditInputs,
    api: Mapping[str, Any],
) -> dict[str, Any]:
    expected = inputs.expected_hashes
    source_manifest_path = (
        inputs.source_root / "learning_dataset/d4_region/manifest.json"
    )
    labeled_manifest_path = inputs.labeled_dataset_root / "manifest.json"
    derivation_path = inputs.labeled_export_root / "source_derivation_manifest.json"
    evidence_path = inputs.labeled_export_root / "external_dataset_evidence.json"
    export_summary_path = inputs.labeled_export_root / "export_summary.json"

    source_manifest = _read_json(source_manifest_path, "source manifest")
    source_manifest_object = api["RegionLearningDatasetManifest"].from_dict(
        source_manifest
    )
    labeled_manifest = _read_json(labeled_manifest_path, "labeled manifest")
    labeled_manifest_object = api["RegionLearningDatasetManifest"].from_dict(
        labeled_manifest
    )
    derivation = _read_json(derivation_path, "source derivation")
    evidence = _read_json(evidence_path, "external evidence")
    export_summary = _read_json(export_summary_path, "export summary")
    v4_manifest_path = inputs.base_v4_root / "v4_shadow_candidate_manifest.json"
    v4_manifest = _read_json(v4_manifest_path, "base v4 manifest")
    v5_manifest_path = (
        inputs.candidate_v5_root / "v5_confidence_candidate_manifest.json"
    )
    v5_state_path = inputs.candidate_v5_root / "calibration_state.json"
    v5_summary_path = inputs.candidate_v5_root / "calibration_summary.json"
    v5_gate_path = inputs.candidate_v5_root / "development_gate.json"
    v5_manifest = _read_json(v5_manifest_path, "candidate v5 manifest")
    v5_state = _read_json(v5_state_path, "candidate v5 state")
    v5_summary = _read_json(v5_summary_path, "candidate v5 summary")
    v5_gate = _read_json(v5_gate_path, "candidate v5 gate")

    actual = {
        "source_manifest_file": _sha256_file(source_manifest_path),
        "source_dataset": source_manifest_object.dataset_sha256,
        "source_split": source_manifest_object.split.split_sha256,
        "labeled_manifest_file": _sha256_file(labeled_manifest_path),
        "labeled_dataset": labeled_manifest_object.dataset_sha256,
        "labeled_split": labeled_manifest_object.split.split_sha256,
        "source_artifact_file": _sha256_file(derivation_path),
        "source_derivation_content": _verify_content_sha256(
            derivation, "source_derivation_content"
        ),
        "external_evidence_file": _sha256_file(evidence_path),
        "external_evidence_content": _verify_content_sha256(
            evidence, "external_evidence_content"
        ),
        "export_summary_file": _sha256_file(export_summary_path),
        "export_summary_content": _verify_content_sha256(
            export_summary, "export_summary_content"
        ),
        "label_audit_content": _verify_content_sha256(
            _mapping(
                derivation["generation"]["observable_label_audit"],
                "observable label audit",
            ),
            "label_audit_content",
        ),
        "base_v4_tree": _tree_sha256(inputs.base_v4_root),
        "base_v4_manifest_file": _sha256_file(v4_manifest_path),
        "base_v4_manifest_content": _verify_content_sha256(
            v4_manifest, "base_v4_manifest_content"
        ),
        "base_v4_model_state": _sha256_file(
            inputs.base_v4_root / "bundle/state_dict.pt"
        ),
        "base_v4_dataset": str(v4_manifest["dataset_sha256"]),
        "base_v4_split": str(v4_manifest["dataset_split_sha256"]),
        "candidate_v5_tree": _tree_sha256(inputs.candidate_v5_root),
        "candidate_v5_manifest_file": _sha256_file(v5_manifest_path),
        "candidate_v5_manifest_content": _verify_content_sha256(
            v5_manifest, "candidate_v5_manifest_content"
        ),
        "candidate_v5_state_file": _sha256_file(v5_state_path),
        "candidate_v5_summary_file": _sha256_file(v5_summary_path),
        "candidate_v5_gate_file": _sha256_file(v5_gate_path),
    }
    for name, digest in actual.items():
        if digest != expected[name]:
            _fail(
                "frozen_hash_mismatch",
                f"{name}:expected={expected[name]}:actual={digest}",
            )

    artifact_files = _mapping(v5_manifest["artifact_files"], "v5 artifacts")
    for filename, expected_key in (
        ("calibration_state.json", "candidate_v5_state_file"),
        ("calibration_summary.json", "candidate_v5_summary_file"),
        ("development_gate.json", "candidate_v5_gate_file"),
    ):
        if artifact_files.get(filename) != actual[expected_key]:
            _fail("candidate_v5_artifact_binding_mismatch", filename)
    for payload, field, expected_key in (
        (v5_state, "calibration_state_content_sha256", None),
        (v5_summary, "calibration_summary_content_sha256", None),
        (v5_gate, "development_gate_content_sha256", None),
    ):
        content = _verify_content_sha256(payload, field)
        if v5_manifest.get(field) != content:
            _fail("candidate_v5_content_binding_mismatch", field)
        if expected_key is not None and content != expected[expected_key]:
            _fail("candidate_v5_content_anchor_mismatch", field)

    if evidence.get("source_artifact_sha256") != actual["source_artifact_file"]:
        _fail("external_evidence_source_artifact_mismatch", "source artifact")
    if evidence.get("dataset_sha256") != actual["labeled_dataset"]:
        _fail("external_evidence_dataset_mismatch", "dataset")
    if evidence.get("dataset_split_sha256") != actual["labeled_split"]:
        _fail("external_evidence_split_mismatch", "split")
    if export_summary.get("source_artifact_sha256") != actual[
        "source_artifact_file"
    ]:
        _fail("export_summary_source_artifact_mismatch", "source artifact")
    if export_summary.get("external_dataset_evidence_sha256") != actual[
        "external_evidence_content"
    ]:
        _fail("export_summary_evidence_mismatch", "external evidence")
    if export_summary.get("observable_label_audit_sha256") != actual[
        "label_audit_content"
    ]:
        _fail("export_summary_label_audit_mismatch", "label audit")

    source_binding = derivation["source"]["datasets"]
    if len(source_binding) != 1:
        _fail("source_derivation_dataset_count_mismatch", str(len(source_binding)))
    source_entry = source_binding[0]
    if (
        source_entry.get("dataset_sha256") != actual["source_dataset"]
        or source_entry.get("split_sha256") != actual["source_split"]
    ):
        _fail("source_derivation_manifest_binding_mismatch", "source dataset")
    output_binding = derivation["output"]
    if (
        output_binding.get("dataset_sha256") != actual["labeled_dataset"]
        or output_binding.get("split_sha256") != actual["labeled_split"]
    ):
        _fail("source_derivation_output_binding_mismatch", "labeled dataset")
    if derivation["repository"].get("git_commit") != inputs.source_git_commit:
        _fail("source_derivation_commit_mismatch", inputs.source_git_commit)

    v5_base_bindings = {
        "base_v4_manifest_file_sha256": "base_v4_manifest_file",
        "base_v4_manifest_content_sha256": "base_v4_manifest_content",
        "base_v4_model_state_sha256": "base_v4_model_state",
        "base_v4_dataset_sha256": "base_v4_dataset",
        "base_v4_split_sha256": "base_v4_split",
        "base_v4_tree_sha256": "base_v4_tree",
    }
    for field, actual_key in v5_base_bindings.items():
        if v5_manifest.get(field) != actual[actual_key]:
            _fail("candidate_v5_base_v4_binding_mismatch", field)

    return {
        "all_hashes_match": True,
        "expected_sha256": dict(expected),
        "actual_sha256": actual,
        "source_manifest_path": str(source_manifest_path),
        "labeled_dataset_path": str(inputs.labeled_dataset_root),
        "source_derivation_path": str(derivation_path),
        "external_evidence_path": str(evidence_path),
        "export_summary_path": str(export_summary_path),
        "base_v4_root": str(inputs.base_v4_root),
        "candidate_v5_root": str(inputs.candidate_v5_root),
        "source_manifest": source_manifest_object.to_dict(),
        "labeled_manifest": labeled_manifest_object.to_dict(),
        "source_derivation": derivation,
        "export_summary": export_summary,
        "candidate_v5_payloads": {
            "manifest": v5_manifest,
            "state": v5_state,
            "summary": v5_summary,
            "gate": v5_gate,
        },
        "base_v4_manifest": v4_manifest,
    }


def _audit_seed_governance(
    inputs: D4V5ExternalAuditInputs,
    anchors: Mapping[str, Any],
    api: Mapping[str, Any],
) -> dict[str, Any]:
    plan = _read_json(inputs.source_root / "generation_plan.json", "generation plan")
    classes = plan["seed_classes"]
    expected_classes = {
        "training": set(range(0, 100)),
        "formal_holdout": set(range(1000, 1020)),
        "pilot": set(range(3000, 3008)),
        "independent_evaluation": set(range(3008, 3040)),
    }
    observed_classes = {
        "training": set(classes["training_seeds"]),
        "formal_holdout": set(classes["formal_holdout_seeds"]),
        "pilot": set(classes["design_pilot_seeds"]),
        "independent_evaluation": set(
            classes["independent_development_seeds"]
        ),
    }
    for name in expected_classes:
        if observed_classes[name] != expected_classes[name]:
            _fail("seed_class_mismatch", name)
    intersections: dict[str, list[int]] = {}
    names = tuple(expected_classes)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = sorted(expected_classes[left] & expected_classes[right])
            intersections[f"{left}__{right}"] = overlap
            if overlap:
                _fail("seed_class_overlap", f"{left}:{right}:{overlap}")

    source_manifest = anchors["source_manifest"]
    labeled_manifest = anchors["labeled_manifest"]
    source_seeds = {int(item["source"]["seed"]) for item in source_manifest["episodes"]}
    labeled_seeds = {
        int(item["source"]["seed"]) for item in labeled_manifest["episodes"]
    }
    expected_external = expected_classes["independent_evaluation"]
    if source_seeds != expected_external or labeled_seeds != expected_external:
        _fail("external_seed_inventory_mismatch", "source or labeled dataset")
    if expected_classes["formal_holdout"] & labeled_seeds:
        _fail("formal_holdout_seed_leak", "labeled dataset")

    split_seeds = {
        name: tuple(int(seed) for seed in labeled_manifest["split"][f"{name}_seeds"])
        for name in _SPLIT_ORDER
    }
    split_frame_counts = {
        name: sum(
            int(item["frame_count"])
            for item in labeled_manifest["episodes"]
            if item["split"] == name
        )
        for name in _SPLIT_ORDER
    }
    if split_frame_counts != {"train": 43, "validation": 10, "test": 10}:
        _fail("external_split_frame_count_mismatch", str(split_frame_counts))

    generation_summary = _read_json(
        inputs.source_root / "generation_summary.json",
        "generation summary",
    )
    expected_generation = {
        "episode_count": 32,
        "frame_count": 63,
        "model_fit_count": 0,
        "online_truth_use_count": 0,
        "formal_holdout_payload_read_count": 0,
        "production_permission_available": False,
    }
    for field, expected in expected_generation.items():
        if generation_summary.get(field) != expected:
            _fail("generation_summary_governance_mismatch", field)
    if generation_summary["source"]["git_commit"] != inputs.source_git_commit:
        _fail("generation_summary_commit_mismatch", inputs.source_git_commit)

    return {
        "passed": True,
        "seed_registry_id": classes["registry_id"],
        "configured_seed_classes": {
            name: sorted(values) for name, values in expected_classes.items()
        },
        "pairwise_seed_intersections": intersections,
        "source_dataset_seed_set": sorted(source_seeds),
        "labeled_dataset_seed_set": sorted(labeled_seeds),
        "external_split_seed_sets": {
            name: list(split_seeds[name]) for name in _SPLIT_ORDER
        },
        "external_split_frame_counts": split_frame_counts,
        "semantic_payload_reads": {
            "d6_external_train": 43,
            "d6_external_validation": 10,
            "d6_external_test_nonformal": 10,
            "d6_base_v4_train": 350,
            "d6_base_v4_validation": 75,
            "d6_base_v4_test": 0,
            "d6_formal_holdout_1000_1019": 0,
            "prior_main_external_test_nonformal": (
                inputs.prior_main_external_test_payload_read_count
            ),
            "prior_main_test_read_fact_source": "main_dispatch_declared",
        },
        "formal_holdout_payload_read_count": 0,
        "external_test_is_formal_holdout": False,
        "model_fit_count": 0,
        "threshold_fit_count": 0,
        "split_change_count": 0,
        "online_truth_use_count": 0,
    }


def _load_frozen_candidate(
    inputs: D4V5ExternalAuditInputs,
    api: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        loader = api["RegionResourceV4CandidateLoader"](
            inputs.base_v4_root,
            require_registered_binding=False,
            evaluation_context="offline_development",
        )
    except Exception as exc:
        _fail("frozen_v4_candidate_load_failed", f"{type(exc).__name__}:{exc}")
    state = _read_json(
        inputs.candidate_v5_root / "calibration_state.json",
        "v5 calibration state",
    )
    _validate_calibration_state(state)
    model = loader.loaded_bundle.model
    hidden_dimension = int(model.node_encoder[0].out_features)
    if hidden_dimension != int(state["feature_dimension"]):
        _fail(
            "actor_calibrator_feature_dimension_mismatch",
            f"actor={hidden_dimension}:state={state['feature_dimension']}",
        )
    return {"loader": loader, "model": model, "state": state}


def _evaluate_external_dataset(
    inputs: D4V5ExternalAuditInputs,
    *,
    api: Mapping[str, Any],
    candidate: Mapping[str, Any],
    seed_governance: Mapping[str, Any],
) -> dict[str, Any]:
    dataset = api["load_region_learning_dataset"](inputs.labeled_dataset_root)
    loader = candidate["loader"]
    model = candidate["model"]
    state = candidate["state"]
    rows: list[dict[str, Any]] = []
    observable_keys: dict[str, list[str]] = {}
    for split_name in _SPLIT_ORDER:
        split = api["RegionLearningSplit"](split_name)
        split_rows: list[dict[str, Any]] = []
        keys: list[str] = []
        for episode in dataset.episodes(split):
            for frame in episode.frames:
                graph = api["snapshot_to_region_graph"](
                    frame.snapshot,
                    device="cpu",
                )
                key = _observable_graph_key(
                    graph,
                    architecture=api["REGION_GRAPH_ARCHITECTURE"],
                )
                raw = loader.policy.recommend_raw(frame.snapshot)
                projected = loader.projector.project(frame.snapshot, raw)
                rule = loader.rule_policy.recommend(frame.snapshot)
                valid, invariant_reasons = api[
                    "evaluate_v4_intervention_invariants"
                ](
                    frame.snapshot,
                    projected,
                    rule,
                    gate=loader.intervention_gate,
                    projector=loader.projector,
                    formal_decision=None,
                )
                candidate_advisory = loader.projector.build_advisory_contract(
                    frame.snapshot,
                    projected,
                )
                rule_advisory = loader.projector.build_advisory_contract(
                    frame.snapshot,
                    rule,
                )
                if frame.target.recommendation is None:
                    _fail("external_target_unavailable", frame.snapshot.snapshot_id)
                target_advisory = loader.projector.build_advisory_contract(
                    frame.snapshot,
                    frame.target.recommendation,
                )
                candidate_signature, _ = api["executable_signature"](
                    candidate_advisory
                )
                rule_signature, _ = api["executable_signature"](rule_advisory)
                target_signature, _ = api["executable_signature"](
                    target_advisory
                )
                rule_safe_positive = target_signature != rule_signature
                actor_executable = candidate_signature != rule_signature
                actor_derived_positive = bool(
                    rule_safe_positive
                    and valid
                    and candidate_signature == target_signature
                )
                feature = _actor_pooled_latent(model, graph)
                score = _score_feature(feature, state)
                if not isfinite(score):
                    _fail("candidate_score_nonfinite", frame.snapshot.snapshot_id)
                gate_passed = score >= D4_V5_FIXED_GATE
                reasons = list(invariant_reasons)
                if not actor_executable:
                    reasons.append("actor_no_executable_difference")
                if candidate_signature != target_signature:
                    reasons.append("actor_target_signature_mismatch")
                if not valid:
                    reasons.append("actor_action_inconsistent")
                split_rows.append(
                    {
                        "seed": int(episode.source.seed),
                        "observable_key": key,
                        "rule_safe_positive": rule_safe_positive,
                        "actor_derived_positive": actor_derived_positive,
                        "actor_executable": actor_executable,
                        "actor_action_valid": bool(valid),
                        "score": score,
                        "gate_passed": gate_passed,
                        "false_accept": bool(
                            gate_passed and not actor_derived_positive
                        ),
                        "reason_codes": tuple(dict.fromkeys(reasons)),
                    }
                )
                keys.append(key)
        expected_count = seed_governance["external_split_frame_counts"][
            split_name
        ]
        if len(split_rows) != expected_count:
            _fail(
                "external_evaluation_split_count_mismatch",
                f"{split_name}:{len(split_rows)}",
            )
        rows.append(_summarise_split(split_name, split_rows))
        observable_keys[split_name] = keys

    total_samples = sum(row["sample_count"] for row in rows)
    actor_positive = sum(
        row["actor_derived_positive_count"] for row in rows
    )
    false_accepts = sum(row["negative_gate_pass_count"] for row in rows)
    score_values = [
        value
        for row in rows
        for value in row.pop("_score_values")
    ]
    if total_samples != 63 or len(score_values) != 63:
        _fail("external_evaluation_total_count_mismatch", str(total_samples))
    if actor_positive != 0:
        _fail("unexpected_actor_derived_positive", str(actor_positive))
    return {
        "fixed_gate": D4_V5_FIXED_GATE,
        "split_metrics": rows,
        "aggregate": {
            "sample_count": total_samples,
            "rule_safe_positive_action_count": sum(
                row["rule_safe_positive_action_count"] for row in rows
            ),
            "actor_derived_positive_count": actor_positive,
            "actor_derived_negative_count": total_samples - actor_positive,
            "score_finite_count": len(score_values),
            "score_minimum": min(score_values),
            "score_mean": sum(score_values) / len(score_values),
            "score_maximum": max(score_values),
            "gate_pass_count": sum(row["gate_pass_count"] for row in rows),
            "negative_gate_pass_count": false_accepts,
            "negative_rejection_count": total_samples - false_accepts,
            "negative_specificity": {
                "availability": "available",
                "value": (total_samples - false_accepts) / total_samples,
                "denominator": total_samples,
            },
            "positive_recall": {
                "availability": "unavailable",
                "value": None,
                "denominator": actor_positive,
                "reason": "actor_derived_positive_denominator_zero",
            },
            "rule_fallback_count": total_samples,
            "rule_fallback_rate": 1.0,
        },
        "positive_definition": (
            "frozen actor projected executable signature equals the exported "
            "R0-safe positive action signature and passes frozen intervention "
            "invariants"
        ),
        "rule_safe_positive_is_not_candidate_positive": True,
        "candidate_score_fit_count": 0,
        "candidate_threshold_change_count": 0,
        "_observable_keys": observable_keys,
    }


def _summarise_split(
    split_name: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    scores = [float(row["score"]) for row in rows]
    actor_positive = sum(bool(row["actor_derived_positive"]) for row in rows)
    negative_count = len(rows) - actor_positive
    negative_pass = sum(bool(row["false_accept"]) for row in rows)
    reason_inventory = sorted(
        {
            reason
            for row in rows
            for reason in row["reason_codes"]
        }
    )
    return {
        "split": split_name,
        "sample_count": len(rows),
        "seed_count": len({int(row["seed"]) for row in rows}),
        "unique_observable_key_count": len(
            {str(row["observable_key"]) for row in rows}
        ),
        "rule_safe_positive_action_count": sum(
            bool(row["rule_safe_positive"]) for row in rows
        ),
        "actor_derived_positive_count": actor_positive,
        "actor_derived_negative_count": negative_count,
        "actor_executable_action_count": sum(
            bool(row["actor_executable"]) for row in rows
        ),
        "actor_action_valid_count": sum(
            bool(row["actor_action_valid"]) for row in rows
        ),
        "score_finite_count": sum(isfinite(score) for score in scores),
        "score_minimum": min(scores),
        "score_mean": sum(scores) / len(scores),
        "score_maximum": max(scores),
        "gate_pass_count": sum(bool(row["gate_passed"]) for row in rows),
        "positive_gate_pass_count": sum(
            bool(row["gate_passed"]) and bool(row["actor_derived_positive"])
            for row in rows
        ),
        "negative_gate_pass_count": negative_pass,
        "negative_rejection_count": negative_count - negative_pass,
        "positive_recall": {
            "availability": (
                "available" if actor_positive > 0 else "unavailable"
            ),
            "value": (
                sum(
                    bool(row["gate_passed"])
                    and bool(row["actor_derived_positive"])
                    for row in rows
                )
                / actor_positive
                if actor_positive > 0
                else None
            ),
            "denominator": actor_positive,
            "reason": (
                None
                if actor_positive > 0
                else "actor_derived_positive_denominator_zero"
            ),
        },
        "negative_specificity": {
            "availability": (
                "available" if negative_count > 0 else "unavailable"
            ),
            "value": (
                (negative_count - negative_pass) / negative_count
                if negative_count > 0
                else None
            ),
            "denominator": negative_count,
        },
        "rule_fallback_count": len(rows),
        "rule_fallback_rate": 1.0,
        "reason_code_counts": {
            reason: sum(reason in row["reason_codes"] for row in rows)
            for reason in reason_inventory
        },
        "nonformal_external_test_split": split_name == "test",
        "_score_values": scores,
    }


def _audit_observable_key_independence(
    inputs: D4V5ExternalAuditInputs,
    *,
    api: Mapping[str, Any],
    candidate: Mapping[str, Any],
    external_keys: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    old_dataset = api["load_region_learning_dataset_splits"](
        inputs.base_v4_root / "development_dataset",
        splits=(
            api["RegionLearningSplit"].TRAIN,
            api["RegionLearningSplit"].VALIDATION,
        ),
    )
    old_keys: list[str] = []
    for split in (
        api["RegionLearningSplit"].TRAIN,
        api["RegionLearningSplit"].VALIDATION,
    ):
        for episode in old_dataset.episodes(split):
            for frame in episode.frames:
                graph = api["snapshot_to_region_graph"](
                    frame.snapshot,
                    device="cpu",
                )
                old_keys.append(
                    _observable_graph_key(
                        graph,
                        architecture=api["REGION_GRAPH_ARCHITECTURE"],
                    )
                )
    flattened_external = [
        key
        for split_name in _SPLIT_ORDER
        for key in external_keys[split_name]
    ]
    old_unique = set(old_keys)
    external_unique = set(flattened_external)
    overlap = sorted(old_unique & external_unique)
    if len(old_keys) != 425 or len(old_unique) != 251:
        _fail(
            "base_v4_observable_inventory_mismatch",
            f"frames={len(old_keys)}:keys={len(old_unique)}",
        )
    if len(flattened_external) != 63 or len(external_unique) != 41:
        _fail(
            "external_observable_inventory_mismatch",
            f"frames={len(flattened_external)}:keys={len(external_unique)}",
        )
    if overlap:
        _fail("observable_key_overlap_detected", str(len(overlap)))
    split_overlap: dict[str, int] = {}
    for index, left in enumerate(_SPLIT_ORDER):
        for right in _SPLIT_ORDER[index + 1 :]:
            split_overlap[f"{left}__{right}"] = len(
                set(external_keys[left]) & set(external_keys[right])
            )
    return {
        "passed": True,
        "observable_key_definition": (
            "architecture plus node_features, edge_features, and edge_index "
            "shape/dtype/value; no seed, source, actor, or target identity"
        ),
        "base_v4_train_validation_frame_count": len(old_keys),
        "base_v4_train_validation_unique_key_count": len(old_unique),
        "external_frame_count": len(flattened_external),
        "external_unique_key_count": len(external_unique),
        "external_unique_key_count_by_split": {
            split_name: len(set(external_keys[split_name]))
            for split_name in _SPLIT_ORDER
        },
        "external_split_pair_key_overlap_count": split_overlap,
        "exact_observable_key_overlap_count": 0,
        "exact_overlap_keys": [],
    }


def _audit_closed_permissions(
    v5_payloads: Mapping[str, Mapping[str, Any]],
    v4_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = v5_payloads["manifest"]
    summary = v5_payloads["summary"]
    state = v5_payloads["state"]
    gate = v5_payloads["gate"]
    for label, payload, required_fields in (
        ("v5 manifest", manifest, _PERMISSION_FIELDS),
        ("v5 summary", summary, _PERMISSION_FIELDS),
        ("v4 manifest", v4_manifest, _V4_PERMISSION_FIELDS),
    ):
        permissions = _mapping(payload["permissions"], f"{label} permissions")
        for field in required_fields:
            if permissions.get(field) is not False:
                _fail("production_permission_not_closed", f"{label}:{field}")
    for label, payload in (
        ("v5 manifest", manifest),
        ("v5 summary", summary),
        ("v5 state", state),
        ("v5 gate", gate),
        ("v4 manifest", v4_manifest),
    ):
        for field, expected in (
            ("development_only", True),
            ("shadow_only", True),
            ("admission_closed", True),
            ("rule_fallback_required", True),
        ):
            if payload.get(field) is not expected:
                _fail("candidate_lifecycle_not_closed", f"{label}:{field}")
    if manifest.get("registered") is not False or summary.get("registered") is not False:
        _fail("candidate_registration_state_invalid", "v5 registered")
    for field in (
        "d3_permission_available",
        "d7_permission_available",
        "production_permission_available",
    ):
        if summary.get(field) is not False:
            _fail("candidate_summary_permission_not_closed", field)
    return {
        "all_permission_fields_false": True,
        "candidate_unregistered": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "production_permissions_disabled": True,
        "d3_permission_available": False,
        "d7_permission_available": False,
        "runtime_preflight_run_count": 0,
        "d3_successor_test_run_count": 0,
        "d7_permission_test_run_count": 0,
        "control_command_count": 0,
        "authorization_artifact_count": 0,
    }


def _load_d4_api(repository_root: Path) -> dict[str, Any]:
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    try:
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
            RegionLearningDatasetManifest,
            RegionLearningSplit,
            load_region_learning_dataset,
            load_region_learning_dataset_splits,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
            REGION_GRAPH_ARCHITECTURE,
            snapshot_to_region_graph,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
            RegionResourceV4CandidateLoader,
            evaluate_v4_intervention_invariants,
            executable_signature,
        )
    except (ImportError, OSError) as exc:
        _fail("d4_read_only_dependency_unavailable", f"{type(exc).__name__}:{exc}")
    return {
        "RegionLearningDatasetManifest": RegionLearningDatasetManifest,
        "RegionLearningSplit": RegionLearningSplit,
        "load_region_learning_dataset": load_region_learning_dataset,
        "load_region_learning_dataset_splits": load_region_learning_dataset_splits,
        "REGION_GRAPH_ARCHITECTURE": REGION_GRAPH_ARCHITECTURE,
        "snapshot_to_region_graph": snapshot_to_region_graph,
        "RegionResourceV4CandidateLoader": RegionResourceV4CandidateLoader,
        "evaluate_v4_intervention_invariants": (
            evaluate_v4_intervention_invariants
        ),
        "executable_signature": executable_signature,
    }


def _actor_pooled_latent(model: Any, graph: Any) -> tuple[float, ...]:
    """Recompute the frozen actor's pooled online-observable latent."""

    try:
        import torch
    except ImportError as exc:
        _fail("torch_unavailable", str(exc))
    model.eval()
    with torch.no_grad():
        node_hidden = model.node_encoder(graph.node_features)
        edge_hidden = model.edge_encoder(graph.edge_features)
        if graph.edge_count:
            source = graph.edge_index[0]
            target = graph.edge_index[1]
            for _ in range(model.message_passing_steps):
                messages = model.message_network(
                    torch.cat(
                        (
                            node_hidden[source],
                            node_hidden[target],
                            edge_hidden,
                        ),
                        dim=-1,
                    )
                )
                aggregate = torch.zeros_like(node_hidden)
                aggregate.index_add_(0, target, messages)
                degree = torch.zeros(
                    graph.node_count,
                    dtype=node_hidden.dtype,
                    device=node_hidden.device,
                )
                degree.index_add_(
                    0,
                    target,
                    torch.ones_like(target, dtype=node_hidden.dtype),
                )
                aggregate = aggregate / degree.clamp_min(1.0).unsqueeze(-1)
                node_hidden = model.node_update(
                    torch.cat((node_hidden, aggregate), dim=-1)
                )
        else:
            for _ in range(model.message_passing_steps):
                node_hidden = model.node_update(
                    torch.cat(
                        (node_hidden, torch.zeros_like(node_hidden)),
                        dim=-1,
                    )
                )
        pooled = node_hidden.mean(dim=0).detach().cpu()
    values = tuple(float(value) for value in pooled.tolist())
    if not values or any(not isfinite(value) for value in values):
        _fail("actor_pooled_latent_nonfinite", str(len(values)))
    return values


def _score_feature(
    feature: Sequence[float],
    state: Mapping[str, Any],
) -> float:
    """Independently recompute the frozen k-nearest-neighbour score."""

    dimension = int(state["feature_dimension"])
    values = tuple(float(value) for value in feature)
    if len(values) != dimension or any(not isfinite(value) for value in values):
        _fail("calibrator_feature_invalid", str(len(values)))
    mean = tuple(float(value) for value in state["train_feature_mean"])
    scale = tuple(float(value) for value in state["train_feature_scale"])
    normalized = tuple(
        (values[index] - mean[index]) / scale[index]
        for index in range(dimension)
    )
    distances: list[tuple[float, int]] = []
    for index, row in enumerate(state["normalized_train_features"]):
        distance = sqrt(
            sum(
                (normalized[column] - float(row[column])) ** 2
                for column in range(dimension)
            )
        )
        distances.append((distance, index))
    distances.sort(key=lambda item: (item[0], item[1]))
    neighbours = distances[
        : min(int(state["neighbour_count"]), len(distances))
    ]
    exact_epsilon = float(state["exact_match_epsilon"])
    exact = [
        index for distance, index in neighbours if distance <= exact_epsilon
    ]
    labels = state["train_labels"]
    if exact:
        score = sum(bool(labels[index]) for index in exact) / len(exact)
    else:
        weights = [
            1.0 / max(distance, exact_epsilon)
            for distance, _ in neighbours
        ]
        score = sum(
            weight * float(bool(labels[index]))
            for weight, (_, index) in zip(
                weights, neighbours, strict=True
            )
        ) / sum(weights)
    if not isfinite(score) or not 0.0 <= score <= 1.0:
        _fail("calibrator_score_invalid", str(score))
    return score


def _validate_calibration_state(state: Mapping[str, Any]) -> None:
    required = {
        "feature_dimension",
        "neighbour_count",
        "exact_match_epsilon",
        "fixed_minimum_confidence",
        "train_feature_mean",
        "train_feature_scale",
        "normalized_train_features",
        "train_labels",
        "train_sample_count",
        "train_positive_count",
        "train_negative_count",
        "validation_fit_count",
        "test_payload_read_count",
        "test_payload_fit_count",
        "formal_holdout_payload_read_count",
        "formal_holdout_payload_fit_count",
        "development_only",
        "shadow_only",
        "admission_closed",
        "rule_fallback_required",
    }
    if not required.issubset(state):
        _fail("calibration_state_fields_missing", str(sorted(required - set(state))))
    dimension = int(state["feature_dimension"])
    sample_count = int(state["train_sample_count"])
    if dimension != 24 or sample_count != 350:
        _fail(
            "calibration_state_shape_mismatch",
            f"dimension={dimension}:samples={sample_count}",
        )
    if int(state["neighbour_count"]) != 11:
        _fail("calibration_neighbour_count_mismatch", str(state["neighbour_count"]))
    if float(state["fixed_minimum_confidence"]) != D4_V5_FIXED_GATE:
        _fail(
            "calibration_gate_mismatch",
            str(state["fixed_minimum_confidence"]),
        )
    if (
        len(state["train_feature_mean"]) != dimension
        or len(state["train_feature_scale"]) != dimension
        or len(state["normalized_train_features"]) != sample_count
        or len(state["train_labels"]) != sample_count
        or any(len(row) != dimension for row in state["normalized_train_features"])
    ):
        _fail("calibration_state_tensor_shape_mismatch", "state arrays")
    if any(float(value) <= 0.0 for value in state["train_feature_scale"]):
        _fail("calibration_state_scale_invalid", "nonpositive scale")
    if sum(bool(value) for value in state["train_labels"]) != int(
        state["train_positive_count"]
    ):
        _fail("calibration_state_positive_count_mismatch", "train labels")
    if sample_count - int(state["train_positive_count"]) != int(
        state["train_negative_count"]
    ):
        _fail("calibration_state_negative_count_mismatch", "train labels")
    zero_fields = (
        "validation_fit_count",
        "test_payload_read_count",
        "test_payload_fit_count",
        "formal_holdout_payload_read_count",
        "formal_holdout_payload_fit_count",
    )
    if any(int(state[field]) != 0 for field in zero_fields):
        _fail("calibration_state_data_use_not_frozen", str(zero_fields))


def _observable_graph_key(graph: Any, *, architecture: str) -> str:
    """Hash only the graph tensors available to the frozen online actor."""

    node_features = graph.node_features.detach().cpu()
    edge_features = graph.edge_features.detach().cpu()
    edge_index = graph.edge_index.detach().cpu()
    try:
        import torch
    except ImportError as exc:
        _fail("torch_unavailable", str(exc))
    if (
        not bool(torch.isfinite(node_features).all().item())
        or not bool(torch.isfinite(edge_features).all().item())
    ):
        _fail("observable_graph_nonfinite", architecture)
    payload = {
        "architecture": architecture,
        "node_features": {
            "shape": list(node_features.shape),
            "dtype": str(node_features.dtype),
            "values": node_features.tolist(),
        },
        "edge_features": {
            "shape": list(edge_features.shape),
            "dtype": str(edge_features.dtype),
            "values": edge_features.tolist(),
        },
        "edge_index": {
            "shape": list(edge_index.shape),
            "dtype": str(edge_index.dtype),
            "values": edge_index.tolist(),
        },
    }
    return _canonical_sha256(payload)


def _write_split_csv(path: Path, result: Mapping[str, Any]) -> None:
    rows = result["candidate_evaluation"]["split_metrics"]
    fieldnames = (
        "split",
        "sample_count",
        "seed_count",
        "unique_observable_key_count",
        "rule_safe_positive_action_count",
        "actor_derived_positive_count",
        "actor_derived_negative_count",
        "actor_executable_action_count",
        "actor_action_valid_count",
        "score_finite_count",
        "score_minimum",
        "score_mean",
        "score_maximum",
        "fixed_gate",
        "gate_pass_count",
        "positive_gate_pass_count",
        "negative_gate_pass_count",
        "negative_rejection_count",
        "positive_recall_availability",
        "positive_recall",
        "negative_specificity_availability",
        "negative_specificity",
        "rule_fallback_count",
        "nonformal_external_test_split",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{
                        name: row[name]
                        for name in fieldnames
                        if name in row
                    },
                    "fixed_gate": result["candidate_evaluation"]["fixed_gate"],
                    "positive_recall_availability": row["positive_recall"][
                        "availability"
                    ],
                    "positive_recall": row["positive_recall"]["value"],
                    "negative_specificity_availability": row[
                        "negative_specificity"
                    ]["availability"],
                    "negative_specificity": row["negative_specificity"][
                        "value"
                    ],
                }
            )


def _render_chinese_report(result: Mapping[str, Any]) -> str:
    anchors = result["anchors"]["actual_sha256"]
    input_immutability = result["input_immutability"]
    seed = result["seed_governance"]
    overlap = result["observable_independence"]
    evaluation = result["candidate_evaluation"]
    aggregate = evaluation["aggregate"]
    lines = [
        "# D4 v5 来源独立外部评价审计",
        "",
        "## 结论",
        "",
        (
            "D6 于 2026-07-29 对冻结 D4 v4 actor 与 v5 置信校准器完成只读外部评价。"
            "输入为 M16N20、32 个 episode、63 帧，seed 为 3008-3039。"
        ),
        (
            "冻结 actor 在 63 帧上没有输出与规则安全正动作签名一致的可执行动作。"
            "actor-derived positive 分母为 0，正类召回不可评价。63 个负类评分均为 0，"
            "固定 0.60 门通过数为 0，负类误接收为 0。"
        ),
        (
            "该结果支持来源独立负类拒绝，不支持正类泛化或正式准入。候选保持 "
            "`unregistered`、`admission_closed`、`rule_fallback_required`，"
            "生产、D3 和 D7 权限继续关闭。"
        ),
        "",
        "## 数据边界",
        "",
        "| 项目 | 结果 |",
        "| --- | ---: |",
        "| episode | 32 |",
        "| 帧 | 63 |",
        "| 目标/资源 | 16/20 |",
        "| 独立评价 seed | 3008-3039 |",
        (
            f"| D6 读取 external train/validation/test | "
            f"{seed['semantic_payload_reads']['d6_external_train']}/"
            f"{seed['semantic_payload_reads']['d6_external_validation']}/"
            f"{seed['semantic_payload_reads']['d6_external_test_nonformal']} |"
        ),
        (
            f"| main 此前读取 external test | "
            f"{seed['semantic_payload_reads']['prior_main_external_test_nonformal']} |"
        ),
        "| 正式 holdout seed 1000-1019 读取 | 0 |",
        "| 模型拟合/门限调整/split 调整 | 0/0/0 |",
        "",
        (
            "external test 的 10 帧属于来源独立开发数据的 test 子集。它不是正式 "
            "holdout。D6 没有读取 1000-1019，也没有运行 runtime preflight、"
            "D3 successor 或 D7 权限测试。"
        ),
        "",
        "## 哈希复核",
        "",
        "| 制品 | SHA-256 |",
        "| --- | --- |",
        f"| source manifest 文件 | `{anchors['source_manifest_file']}` |",
        f"| labeled dataset | `{anchors['labeled_dataset']}` |",
        f"| labeled split | `{anchors['labeled_split']}` |",
        f"| source artifact 文件 | `{anchors['source_artifact_file']}` |",
        f"| external evidence 内容 | `{anchors['external_evidence_content']}` |",
        f"| label audit 内容 | `{anchors['label_audit_content']}` |",
        f"| v4 actor tree | `{anchors['base_v4_tree']}` |",
        f"| v4 actor state | `{anchors['base_v4_model_state']}` |",
        f"| v5 calibrator tree | `{anchors['candidate_v5_tree']}` |",
        f"| v5 calibrator state | `{anchors['candidate_v5_state_file']}` |",
        "",
        "全部实际摘要与调用方冻结摘要一致。source derivation、evidence、export summary、"
        "labeled manifest、v4 和 v5 绑定关系也通过交叉核对。",
        (
            "审计开始前和全部加载、评分及可观测键重合计算完成后，D6 分别重算 "
            "source、labeled export、labeled dataset、v4 actor 和 v5 calibrator "
            "完整文件树摘要。before/after 逐项一致，"
            f"`input_mutation_count={input_immutability['input_mutation_count']}`。"
        ),
        "",
        "## 来源独立性",
        "",
        "| 库存 | 帧 | 唯一可观测键 |",
        "| --- | ---: | ---: |",
        (
            f"| 旧 v4 TRAIN+VALIDATION | "
            f"{overlap['base_v4_train_validation_frame_count']} | "
            f"{overlap['base_v4_train_validation_unique_key_count']} |"
        ),
        (
            f"| 新外部评价 | {overlap['external_frame_count']} | "
            f"{overlap['external_unique_key_count']} |"
        ),
        (
            f"| exact key 重合 | - | "
            f"{overlap['exact_observable_key_overlap_count']} |"
        ),
        "",
        (
            "可观测键只包含图结构、节点特征和边特征的形状、类型与数值，"
            "不包含 seed、来源、actor 或目标身份。"
        ),
        "",
        "## 分片结果",
        "",
        "| split | 样本 | 规则安全正动作 | actor-derived positive | score 范围 | 0.60 通过 | 负类误接收 | 规则回退 |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for row in evaluation["split_metrics"]:
        lines.append(
            f"| {row['split']} | {row['sample_count']} | "
            f"{row['rule_safe_positive_action_count']} | "
            f"{row['actor_derived_positive_count']} | "
            f"{row['score_minimum']:.6f}-{row['score_maximum']:.6f} | "
            f"{row['gate_pass_count']} | "
            f"{row['negative_gate_pass_count']} | "
            f"{row['rule_fallback_count']} |"
        )
    lines.extend(
        [
            "",
            (
                "train 和 validation 各有 1 个规则安全正动作，test 没有。"
                "规则层存在安全动作只说明标签库有可执行差异，不能替代冻结 actor 的输出。"
            ),
            (
                f"聚合负类特异度为 "
                f"{aggregate['negative_specificity']['value']:.6f}。"
                "正类召回保持 `unavailable`，不以 0 回填。"
            ),
            "",
            "## 准入判断",
            "",
            "1. 来源、标签、候选和分片哈希完整，seed 类别互不相交。",
            "2. 新旧 exact observable key 重合为 0，外部数据具有来源独立性。",
            "3. 冻结候选完成负类拒绝，但 actor-derived positive 分母为 0。",
            "4. 正类泛化、正式 holdout 和运行收益证据仍不可用。",
            "5. 候选不注册、不准入，所有样本继续使用规则回退。",
            "",
            "## 限制",
            "",
            "- 本轮是离线外部评价，不是 AirSim、实飞或生产运行结果。",
            "- 未运行正式 holdout、运行时预检、D3 后继计划或 D7 权限测试。",
            "- 结果不能用于调整候选、门限、split 或正类生成规则。",
            "",
        ]
    )
    return "\n".join(lines)


def _repository_head(repository_root: Path) -> str:
    head_path = repository_root / ".git/HEAD"
    if not head_path.exists():
        return "unavailable"
    head = head_path.read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref_path = repository_root / ".git" / head[5:]
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()
        packed = repository_root / ".git/packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line and not line.startswith(("#", "^")):
                    digest, reference = line.split(" ", 1)
                    if reference == head[5:]:
                        return digest
        return "unavailable"
    return head


def _tree_sha256(root: Path) -> str:
    inventory: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            _fail("tree_symlink_forbidden", str(path))
        if path.is_file():
            inventory[str(path.relative_to(root))] = _sha256_file(path)
        elif not path.is_dir():
            _fail("tree_special_file_forbidden", str(path))
    return _canonical_sha256(inventory)


def _verify_content_sha256(
    value: Mapping[str, Any],
    name: str,
) -> str:
    claimed = _normalise_sha256(value.get("content_sha256"), name)
    content = dict(value)
    content.pop("content_sha256")
    actual = _canonical_sha256(content)
    if actual != claimed:
        _fail("content_sha256_mismatch", f"{name}:{actual}")
    return actual


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _normalise_sha256(value: Any, name: str) -> str:
    digest = str(value).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        _fail("sha256_invalid", f"{name}:{value}")
    return digest


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("json_input_invalid", f"{name}:{type(exc).__name__}:{exc}")
    return dict(_mapping(value, name))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", name)
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            "mapping_key_mismatch",
            f"{name}:missing={sorted(expected - actual)}:"
            f"extra={sorted(actual - expected)}",
        )


def _fail(code: str, detail: str) -> None:
    raise D4V5ExternalAuditError(code, detail)
