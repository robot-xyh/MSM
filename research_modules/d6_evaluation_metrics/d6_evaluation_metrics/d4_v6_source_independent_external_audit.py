"""Independent, read-only D6 audit of the frozen D4 v6 actor.

The D4 summary is treated only as a claim to reconcile. Metrics are rebuilt
from the frozen labeled dataset, the exact v6 model bundle, and the common D4
domain contracts. The audit never fits a model, applies a confidence gate,
registers a candidate, or grants runtime authority.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence


D4_V6_EXTERNAL_AUDIT_INPUT_SCHEMA = (
    "d6.d4-v6-source-independent-external-audit-input.v1"
)
D4_V6_EXTERNAL_AUDIT_SCHEMA = (
    "d6.d4-v6-source-independent-external-audit.v1"
)
D4_V6_EXTERNAL_RECORD_SCHEMA = (
    "d4-region-resource-v6-source-independent-frame-evaluation-v1"
)
D4_V6_EXTERNAL_AUDIT_STATUS = (
    "completed_independent_recomputation_zero_of_42_positive_actions_"
    "confidence_calibration_not_allowed"
)

_SPLIT_ORDER = ("train", "validation", "test")
_EXPECTED_FRAME_COUNTS = {"train": 89, "validation": 20, "test": 17}
_EXPECTED_POSITIVE_COUNTS = {"train": 24, "validation": 9, "test": 9}
_EXPECTED_NEGATIVE_COUNTS = {"train": 65, "validation": 11, "test": 8}
_EXPECTED_SEEDS = tuple(range(4016, 4080))
_EXPECTED_TRAINING_SEEDS = frozenset(range(0, 100))
_EXPECTED_FORMAL_HOLDOUT_SEEDS = frozenset(range(1000, 1020))
_EXPECTED_PRIOR_EVALUATION_SEEDS = frozenset(range(3000, 3040))
_EXPECTED_PILOT_SEEDS = frozenset(range(4000, 4016))
_EXPECTED_INDEPENDENT_SEEDS = frozenset(_EXPECTED_SEEDS)
_EXPECTED_SCALE = "M16N24"
_EXPECTED_REGION_COUNT = 8
_EXPECTED_EPISODE_COUNT = 64
_EXPECTED_FRAME_COUNT = 126
_EXPECTED_OLD_FRAME_COUNT = 425
_EXPECTED_OLD_UNIQUE_KEY_COUNT = 251
_EXPECTED_EXTERNAL_UNIQUE_KEY_COUNT = 94
_EXPECTED_CANDIDATE_ID = "region_resource_a2_edge_transfer_shadow_v6"
_EXPECTED_MODEL_VERSION = "d4-region-resource-graph-bc-edge-transfer-v6"

_REQUIRED_HASHES = {
    "source_tree",
    "source_manifest_file",
    "source_dataset",
    "source_split",
    "generation_plan_file",
    "generation_summary_file",
    "labeled_export_tree",
    "labeled_dataset_tree",
    "labeled_manifest_file",
    "labeled_dataset",
    "labeled_split",
    "derivation_file",
    "derivation_content",
    "evidence_file",
    "evidence_content",
    "export_summary_file",
    "export_summary_content",
    "label_audit_content",
    "frozen_v4_tree",
    "frozen_v4_manifest_file",
    "frozen_v4_manifest_content",
    "frozen_v4_dataset",
    "frozen_v4_split",
    "candidate_tree",
    "candidate_manifest_file",
    "candidate_manifest_content",
    "candidate_bundle_manifest_file",
    "candidate_bundle_manifest_content",
    "candidate_state_file",
    "candidate_state_content",
    "candidate_training_audit_file",
    "candidate_training_audit_content",
    "candidate_source_binding_file",
    "candidate_training_config_file",
    "d4_evaluation_tree",
    "d4_artifact_manifest_file",
    "d4_artifact_manifest_content",
    "d4_records_jsonl_file",
    "d4_records_csv_file",
    "d4_integrity_file",
    "d4_integrity_content",
    "d4_overlap_file",
    "d4_overlap_content",
    "d4_summary_file",
    "d4_summary_content",
    "d4_report_file",
}

_D4_METRIC_FIELDS = (
    "sample_count",
    "available_sample_count",
    "unavailable_sample_count",
    "rule_positive_count",
    "rule_negative_count",
    "actor_raw_transfer_count",
    "actor_raw_transfer_resource_count",
    "actor_projected_transfer_count",
    "actor_projected_transfer_resource_count",
    "correct_directed_edge_count",
    "correct_directed_edge_frame_count",
    "projected_exact_positive_action_count",
    "positive_exact_action_recall",
    "positive_exact_action_recall_status",
    "negative_exact_r0_count",
    "negative_exact_r0_rate",
    "negative_exact_r0_rate_status",
    "wrong_direction_count",
    "wrong_quantity_count",
    "wrong_edge_count",
    "false_transfer_count",
    "projection_rejection_count",
    "projection_rejection_frame_count",
    "invariant_failure_count",
    "actor_derived_positive_denominator_count",
    "actor_derived_positive_denominator_available",
    "actor_derived_exact_positive_count",
    "actor_derived_exact_positive_rate",
    "actor_derived_exact_positive_rate_status",
    "confidence_gate_available",
    "confidence_gate_application_count",
    "admission_evaluation_count",
    "all_frames_rule_fallback_required",
    "unavailable_reasons",
    "failure_reasons",
    "projection_rejection_reasons",
    "invariant_failure_reasons",
)


class D4V6ExternalAuditError(ValueError):
    """Stable fail-closed error for invalid v6 audit evidence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D4V6ExternalAuditInputs:
    """Caller-frozen paths, commits, seed inventory, and hash anchors."""

    repository_root: Path
    source_root: Path
    labeled_export_root: Path
    labeled_dataset_root: Path
    frozen_v4_root: Path
    candidate_v6_root: Path
    d4_evaluation_root: Path
    audit_id: str
    evaluated_at_utc: str
    source_git_commit: str
    exporter_git_commit: str
    expected_seeds: tuple[int, ...]
    expected_hashes: Mapping[str, str]
    schema_version: str = D4_V6_EXTERNAL_AUDIT_INPUT_SCHEMA

    def __post_init__(self) -> None:
        repository = Path(self.repository_root).expanduser().resolve()
        if not repository.is_dir():
            _fail("repository_root_unavailable", str(repository))
        object.__setattr__(self, "repository_root", repository)
        for name in (
            "source_root",
            "labeled_export_root",
            "labeled_dataset_root",
            "frozen_v4_root",
            "candidate_v6_root",
            "d4_evaluation_root",
        ):
            path = Path(getattr(self, name)).expanduser()
            if not path.is_absolute():
                path = repository / path
            path = path.resolve()
            if not path.is_dir():
                _fail("audit_input_directory_unavailable", f"{name}:{path}")
            object.__setattr__(self, name, path)
        if self.schema_version != D4_V6_EXTERNAL_AUDIT_INPUT_SCHEMA:
            _fail("audit_input_schema_mismatch", self.schema_version)
        if not self.audit_id.strip() or not self.evaluated_at_utc.strip():
            _fail("audit_input_identity_invalid", self.audit_id)
        for field in ("source_git_commit", "exporter_git_commit"):
            commit = str(getattr(self, field)).lower()
            if len(commit) != 40 or any(
                character not in "0123456789abcdef" for character in commit
            ):
                _fail("git_commit_invalid", f"{field}:{commit}")
            object.__setattr__(self, field, commit)
        seeds = tuple(int(seed) for seed in self.expected_seeds)
        if seeds != _EXPECTED_SEEDS:
            _fail("expected_seed_inventory_mismatch", str(seeds))
        object.__setattr__(self, "expected_seeds", seeds)
        expected = {
            str(name): _normalise_sha256(value, str(name))
            for name, value in self.expected_hashes.items()
        }
        if set(expected) != _REQUIRED_HASHES:
            _fail(
                "expected_hash_inventory_mismatch",
                f"missing={sorted(_REQUIRED_HASHES - set(expected))};"
                f"extra={sorted(set(expected) - _REQUIRED_HASHES)}",
            )
        object.__setattr__(self, "expected_hashes", expected)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        repository_root: str | Path,
    ) -> "D4V6ExternalAuditInputs":
        expected = {
            "schema_version",
            "audit_id",
            "evaluated_at_utc",
            "source_git_commit",
            "exporter_git_commit",
            "source_root",
            "labeled_export_root",
            "labeled_dataset_root",
            "frozen_v4_root",
            "candidate_v6_root",
            "d4_evaluation_root",
            "expected_seeds",
            "expected_hashes",
        }
        _require_exact_keys(value, expected, "v6 external audit input")
        return cls(
            repository_root=Path(repository_root),
            source_root=Path(str(value["source_root"])),
            labeled_export_root=Path(str(value["labeled_export_root"])),
            labeled_dataset_root=Path(str(value["labeled_dataset_root"])),
            frozen_v4_root=Path(str(value["frozen_v4_root"])),
            candidate_v6_root=Path(str(value["candidate_v6_root"])),
            d4_evaluation_root=Path(str(value["d4_evaluation_root"])),
            audit_id=str(value["audit_id"]),
            evaluated_at_utc=str(value["evaluated_at_utc"]),
            source_git_commit=str(value["source_git_commit"]),
            exporter_git_commit=str(value["exporter_git_commit"]),
            expected_seeds=tuple(int(seed) for seed in value["expected_seeds"]),
            expected_hashes=_mapping(
                value["expected_hashes"],
                "expected_hashes",
            ),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class _PolicyIdentity:
    model_version: str
    state_dict_sha256: str


def load_d4_v6_external_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> D4V6ExternalAuditInputs:
    """Load the caller-owned frozen input specification."""

    payload = _read_json(Path(path), "v6 external audit input")
    return D4V6ExternalAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
    )


def audit_d4_v6_source_independent_external(
    inputs: D4V6ExternalAuditInputs,
) -> dict[str, Any]:
    """Recompute the D4 v6 external evaluation without trusting its summary."""

    before = _capture_input_summaries(inputs)
    api = _load_d4_api(inputs.repository_root)
    anchors = _audit_hashes_bindings_and_load(inputs, api=api)
    seed_governance = _audit_seed_and_truth_governance(
        inputs,
        anchors=anchors,
        api=api,
    )
    recomputed_records = _recompute_records(
        anchors["labeled_dataset"],
        model=anchors["candidate_model"],
        candidate_manifest=anchors["candidate_manifest"],
        api=api,
    )
    split_metrics = {
        split: _summarise_records(
            tuple(row for row in recomputed_records if row["split"] == split)
        )
        for split in _SPLIT_ORDER
    }
    aggregate = _summarise_records(recomputed_records)
    _validate_recomputed_inventory(split_metrics, aggregate)
    observable = _audit_observable_independence(
        anchors["frozen_v4_dataset"],
        anchors["labeled_dataset"],
        recomputed_records=recomputed_records,
        d4_overlap=anchors["d4_overlap"],
        api=api,
    )
    reconciliation = _reconcile_d4_evaluation(
        anchors,
        recomputed_records=recomputed_records,
        split_metrics=split_metrics,
        aggregate=aggregate,
    )
    confidence = _audit_no_confidence_gate(
        candidate_manifest=anchors["candidate_manifest"],
        bundle_manifest=anchors["candidate_bundle_manifest"],
        d4_integrity=anchors["d4_integrity"],
        d4_summary=anchors["d4_summary"],
        records=recomputed_records,
    )
    permissions = _audit_closed_permissions(
        anchors["candidate_manifest"],
        anchors["d4_summary"],
    )
    immutability = _verify_inputs_unchanged(inputs, before=before)

    public_anchors = {
        key: value
        for key, value in anchors.items()
        if key
        not in {
            "source_dataset",
            "labeled_dataset",
            "frozen_v4_dataset",
            "candidate_model",
            "candidate_manifest",
            "candidate_bundle_manifest",
            "candidate_training_audit",
            "candidate_source_binding",
            "generation_plan",
            "generation_summary",
            "derivation",
            "evidence",
            "export_summary",
            "d4_artifact_manifest",
            "d4_integrity",
            "d4_overlap",
            "d4_summary",
            "d4_jsonl_records",
        }
    }
    result = {
        "schema_version": D4_V6_EXTERNAL_AUDIT_SCHEMA,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "status": D4_V6_EXTERNAL_AUDIT_STATUS,
        "audit_execution_passed": True,
        "scope": {
            "scenario_scale": _EXPECTED_SCALE,
            "region_count": _EXPECTED_REGION_COUNT,
            "episode_count": _EXPECTED_EPISODE_COUNT,
            "frame_count": _EXPECTED_FRAME_COUNT,
            "seed_first": min(inputs.expected_seeds),
            "seed_last": max(inputs.expected_seeds),
            "source_independent_external_evaluation": True,
            "read_only_recomputation": True,
            "d4_summary_used_as_metric_source": False,
            "model_fit_count": 0,
            "checkpoint_update_count": 0,
            "threshold_tuning_count": 0,
            "confidence_gate_application_count": 0,
            "formal_holdout_payload_read_count": 0,
            "old_evaluation_3008_3039_payload_read_count": 0,
        },
        "input_immutability": immutability,
        "anchors": public_anchors,
        "seed_and_truth_governance": seed_governance,
        "observable_independence": observable,
        "independent_recomputation": {
            "split_metrics": split_metrics,
            "aggregate": aggregate,
            "rule_positive_definition": (
                "exported safe target executable signature differs from "
                "same-snapshot deterministic R0 signature"
            ),
            "actor_derived_positive_definition": (
                "frozen actor has an executable difference, passes intervention "
                "invariants, and has no projection rejection"
            ),
            "rule_positive_is_not_actor_derived_positive": True,
        },
        "d4_artifact_reconciliation": reconciliation,
        "confidence_boundary": confidence,
        "permissions_and_fallback": permissions,
        "admission_conclusion": {
            "candidate_registered": False,
            "admission_allowed": False,
            "admission_closed": True,
            "rule_fallback_required": True,
            "actor_freeze_supported": False,
            "confidence_calibration_allowed": False,
            "formal_holdout_allowed": False,
            "runtime_preflight_allowed": False,
            "d3_permission_available": False,
            "d7_permission_available": False,
            "rule_positive_exact_action_recall": {
                "availability": "available",
                "value": 0.0,
                "numerator": 0,
                "denominator": 42,
            },
            "actor_derived_positive_denominator": {
                "availability": "unavailable",
                "value": None,
                "denominator": 0,
                "reason": "actor_derived_positive_denominator_zero",
            },
            "reason_codes": [
                "source_independent_exact_positive_action_zero_of_42",
                "actor_transfer_activation_absent",
                "actor_derived_positive_denominator_zero",
                "confidence_calibrator_absent",
                "candidate_unregistered",
                "admission_closed",
                "rule_fallback_required",
                "all_runtime_permissions_disabled",
            ],
            "next_gate": (
                "create_a_new_versioned_actor_with_nonzero_source_independent_"
                "exact_positive_actions_before_any_confidence_calibration"
            ),
        },
        "recomputed_records": list(recomputed_records),
        "limitations": [
            "evaluation_is_offline_development_evidence_not_runtime_or_physical",
            "external_positive_exact_action_recall_is_zero_of_42",
            "actor_derived_positive_denominator_is_zero_and_rate_is_unavailable",
            "no_confidence_calibrator_exists_and_the_reserved_0_60_value_was_not_used",
            "formal_holdout_1000_1019_and_old_evaluation_3008_3039_were_not_read",
        ],
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def write_d4_v6_external_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Atomically write full JSON, split CSV, frame JSONL, report, and hashes."""

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(destination)
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        json_path = temporary / "d4_v6_external_audit_summary.json"
        csv_path = temporary / "d4_v6_external_audit_by_split.csv"
        records_path = temporary / "d4_v6_recomputed_records.jsonl"
        report_path = temporary / "D4_V6_SOURCE_INDEPENDENT_EXTERNAL_AUDIT_CN.md"
        checksum_path = temporary / "SHA256SUMS"
        _write_json(json_path, result)
        _write_split_csv(csv_path, result)
        _write_jsonl(records_path, result["recomputed_records"])
        report_path.write_text(
            _render_chinese_report(result),
            encoding="utf-8",
        )
        output_files = (json_path, csv_path, records_path, report_path)
        checksum_path.write_text(
            "\n".join(
                f"{_sha256_file(path)}  {path.name}" for path in output_files
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "json": destination / json_path.name,
        "csv": destination / csv_path.name,
        "records_jsonl": destination / records_path.name,
        "markdown": destination / report_path.name,
        "sha256sums": destination / checksum_path.name,
    }


def _capture_input_summaries(
    inputs: D4V6ExternalAuditInputs,
) -> dict[str, str]:
    return {
        "source_tree_sha256": _tree_sha256(inputs.source_root),
        "labeled_export_tree_sha256": _tree_sha256(
            inputs.labeled_export_root
        ),
        "labeled_dataset_tree_sha256": _tree_sha256(
            inputs.labeled_dataset_root
        ),
        "frozen_v4_tree_sha256": _tree_sha256(inputs.frozen_v4_root),
        "candidate_v6_tree_sha256": _tree_sha256(inputs.candidate_v6_root),
        "d4_evaluation_tree_sha256": _tree_sha256(
            inputs.d4_evaluation_root
        ),
    }


def _verify_inputs_unchanged(
    inputs: D4V6ExternalAuditInputs,
    *,
    before: Mapping[str, str],
) -> dict[str, Any]:
    after = _capture_input_summaries(inputs)
    changed = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    if changed:
        _fail(
            "audit_input_mutated_during_execution",
            json.dumps(
                {
                    name: {
                        "before": before.get(name),
                        "after": after.get(name),
                    }
                    for name in changed
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
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


def _audit_hashes_bindings_and_load(
    inputs: D4V6ExternalAuditInputs,
    *,
    api: Mapping[str, Any],
) -> dict[str, Any]:
    source_manifest_path = (
        inputs.source_root / "learning_dataset/d4_region/manifest.json"
    )
    source_dataset = api["load_region_learning_dataset_splits"](
        source_manifest_path.parent,
        splits=tuple(api["RegionLearningSplit"]),
    )
    labeled_manifest_path = inputs.labeled_dataset_root / "manifest.json"
    labeled_dataset = api["load_region_learning_dataset_splits"](
        inputs.labeled_dataset_root,
        splits=tuple(api["RegionLearningSplit"]),
    )
    frozen_v4_manifest_path = (
        inputs.frozen_v4_root / "v4_shadow_candidate_manifest.json"
    )
    frozen_v4_manifest = _read_json(
        frozen_v4_manifest_path,
        "frozen v4 manifest",
    )
    frozen_v4_dataset = api["load_region_learning_dataset_splits"](
        inputs.frozen_v4_root / "development_dataset",
        splits=(
            api["RegionLearningSplit"].TRAIN,
            api["RegionLearningSplit"].VALIDATION,
        ),
    )

    generation_plan_path = inputs.source_root / "generation_plan.json"
    generation_summary_path = inputs.source_root / "generation_summary.json"
    derivation_path = inputs.labeled_export_root / "source_derivation_manifest.json"
    evidence_path = inputs.labeled_export_root / "external_dataset_evidence.json"
    export_summary_path = inputs.labeled_export_root / "export_summary.json"
    generation_plan = _read_json(generation_plan_path, "generation plan")
    generation_summary = _read_json(
        generation_summary_path,
        "generation summary",
    )
    derivation = _read_json(derivation_path, "source derivation")
    evidence = _read_json(evidence_path, "external evidence")
    export_summary = _read_json(export_summary_path, "export summary")

    candidate_manifest_path = (
        inputs.candidate_v6_root / "v6_edge_transfer_candidate_manifest.json"
    )
    candidate_bundle_manifest_path = (
        inputs.candidate_v6_root / "bundle/manifest.json"
    )
    candidate_state_path = inputs.candidate_v6_root / "bundle/state_dict.pt"
    candidate_training_audit_path = (
        inputs.candidate_v6_root / "training_audit.json"
    )
    candidate_source_binding_path = (
        inputs.candidate_v6_root / "source_binding.json"
    )
    candidate_training_config_path = (
        inputs.candidate_v6_root / "training_config.json"
    )
    candidate_manifest = _read_json(
        candidate_manifest_path,
        "candidate v6 manifest",
    )
    candidate_bundle_manifest = _read_json(
        candidate_bundle_manifest_path,
        "candidate v6 bundle manifest",
    )
    candidate_training_audit = _read_json(
        candidate_training_audit_path,
        "candidate v6 training audit",
    )
    candidate_source_binding = _read_json(
        candidate_source_binding_path,
        "candidate v6 source binding",
    )
    candidate_model, loaded_bundle_manifest = api["_load_v6_model_bundle"](
        inputs.candidate_v6_root / "bundle",
        expected_model_version=_EXPECTED_MODEL_VERSION,
        expected_state_file_sha256=_sha256_file(candidate_state_path),
    )
    if candidate_bundle_manifest != loaded_bundle_manifest:
        _fail("candidate_bundle_loader_manifest_mismatch", "bundle manifest")
    candidate_state_content = _model_state_content_sha256(candidate_model)

    d4_artifact_path = inputs.d4_evaluation_root / "artifact_manifest.json"
    d4_integrity_path = inputs.d4_evaluation_root / "input_integrity.json"
    d4_overlap_path = (
        inputs.d4_evaluation_root / "observable_overlap_audit.json"
    )
    d4_summary_path = (
        inputs.d4_evaluation_root / "external_evaluation_summary.json"
    )
    d4_records_jsonl_path = (
        inputs.d4_evaluation_root / "evaluation_records.jsonl"
    )
    d4_records_csv_path = (
        inputs.d4_evaluation_root / "evaluation_records.csv"
    )
    d4_report_path = inputs.d4_evaluation_root / "REPORT_CN.md"
    d4_artifact_manifest = _read_json(
        d4_artifact_path,
        "D4 artifact manifest",
    )
    d4_integrity = _read_json(d4_integrity_path, "D4 input integrity")
    d4_overlap = _read_json(d4_overlap_path, "D4 observable overlap")
    d4_summary = _read_json(d4_summary_path, "D4 evaluation summary")
    d4_jsonl_records = _read_jsonl(
        d4_records_jsonl_path,
        "D4 evaluation records",
    )

    actual = {
        "source_tree": _tree_sha256(inputs.source_root),
        "source_manifest_file": _sha256_file(source_manifest_path),
        "source_dataset": source_dataset.manifest.dataset_sha256,
        "source_split": source_dataset.manifest.split.split_sha256,
        "generation_plan_file": _sha256_file(generation_plan_path),
        "generation_summary_file": _sha256_file(generation_summary_path),
        "labeled_export_tree": _tree_sha256(inputs.labeled_export_root),
        "labeled_dataset_tree": _tree_sha256(inputs.labeled_dataset_root),
        "labeled_manifest_file": _sha256_file(labeled_manifest_path),
        "labeled_dataset": labeled_dataset.manifest.dataset_sha256,
        "labeled_split": labeled_dataset.manifest.split.split_sha256,
        "derivation_file": _sha256_file(derivation_path),
        "derivation_content": _verify_content_sha256(
            derivation,
            "source derivation",
        ),
        "evidence_file": _sha256_file(evidence_path),
        "evidence_content": _verify_content_sha256(
            evidence,
            "external evidence",
        ),
        "export_summary_file": _sha256_file(export_summary_path),
        "export_summary_content": _verify_content_sha256(
            export_summary,
            "export summary",
        ),
        "label_audit_content": _verify_content_sha256(
            _mapping(
                derivation["generation"]["observable_label_audit"],
                "observable label audit",
            ),
            "observable label audit",
        ),
        "frozen_v4_tree": _tree_sha256(inputs.frozen_v4_root),
        "frozen_v4_manifest_file": _sha256_file(frozen_v4_manifest_path),
        "frozen_v4_manifest_content": _verify_content_sha256(
            frozen_v4_manifest,
            "frozen v4 manifest",
        ),
        "frozen_v4_dataset": frozen_v4_dataset.manifest.dataset_sha256,
        "frozen_v4_split": frozen_v4_dataset.manifest.split.split_sha256,
        "candidate_tree": _tree_sha256(inputs.candidate_v6_root),
        "candidate_manifest_file": _sha256_file(candidate_manifest_path),
        "candidate_manifest_content": _verify_content_sha256(
            candidate_manifest,
            "candidate v6 manifest",
        ),
        "candidate_bundle_manifest_file": _sha256_file(
            candidate_bundle_manifest_path
        ),
        "candidate_bundle_manifest_content": _verify_content_sha256(
            candidate_bundle_manifest,
            "candidate v6 bundle manifest",
        ),
        "candidate_state_file": _sha256_file(candidate_state_path),
        "candidate_state_content": candidate_state_content,
        "candidate_training_audit_file": _sha256_file(
            candidate_training_audit_path
        ),
        "candidate_training_audit_content": _verify_content_sha256(
            candidate_training_audit,
            "candidate v6 training audit",
        ),
        "candidate_source_binding_file": _sha256_file(
            candidate_source_binding_path
        ),
        "candidate_training_config_file": _sha256_file(
            candidate_training_config_path
        ),
        "d4_evaluation_tree": _tree_sha256(inputs.d4_evaluation_root),
        "d4_artifact_manifest_file": _sha256_file(d4_artifact_path),
        "d4_artifact_manifest_content": _verify_content_sha256(
            d4_artifact_manifest,
            "D4 artifact manifest",
        ),
        "d4_records_jsonl_file": _sha256_file(d4_records_jsonl_path),
        "d4_records_csv_file": _sha256_file(d4_records_csv_path),
        "d4_integrity_file": _sha256_file(d4_integrity_path),
        "d4_integrity_content": _verify_content_sha256(
            d4_integrity,
            "D4 input integrity",
        ),
        "d4_overlap_file": _sha256_file(d4_overlap_path),
        "d4_overlap_content": _verify_content_sha256(
            d4_overlap,
            "D4 observable overlap",
        ),
        "d4_summary_file": _sha256_file(d4_summary_path),
        "d4_summary_content": _verify_content_sha256(
            d4_summary,
            "D4 evaluation summary",
        ),
        "d4_report_file": _sha256_file(d4_report_path),
    }
    _verify_expected_hashes(inputs.expected_hashes, actual)
    _verify_candidate_bindings(
        candidate_manifest=candidate_manifest,
        bundle_manifest=candidate_bundle_manifest,
        training_audit=candidate_training_audit,
        source_binding=candidate_source_binding,
        frozen_v4_manifest=frozen_v4_manifest,
        actual=actual,
    )
    _verify_external_lineage_bindings(
        inputs,
        source_dataset=source_dataset,
        labeled_dataset=labeled_dataset,
        derivation=derivation,
        evidence=evidence,
        export_summary=export_summary,
        actual=actual,
    )
    _verify_d4_artifact_manifest(
        inputs.d4_evaluation_root,
        d4_artifact_manifest,
        actual=actual,
    )
    _verify_d4_artifact_content_bindings(
        d4_summary=d4_summary,
        d4_integrity=d4_integrity,
        d4_overlap=d4_overlap,
        actual=actual,
    )
    _verify_csv_matches_jsonl(
        d4_records_csv_path,
        d4_jsonl_records,
    )
    return {
        "all_hashes_match": True,
        "expected_sha256": dict(inputs.expected_hashes),
        "actual_sha256": actual,
        "source_git_commit": inputs.source_git_commit,
        "exporter_git_commit": inputs.exporter_git_commit,
        "source_dataset": source_dataset,
        "labeled_dataset": labeled_dataset,
        "frozen_v4_dataset": frozen_v4_dataset,
        "candidate_model": candidate_model,
        "candidate_manifest": candidate_manifest,
        "candidate_bundle_manifest": candidate_bundle_manifest,
        "candidate_training_audit": candidate_training_audit,
        "candidate_source_binding": candidate_source_binding,
        "generation_plan": generation_plan,
        "generation_summary": generation_summary,
        "derivation": derivation,
        "evidence": evidence,
        "export_summary": export_summary,
        "d4_artifact_manifest": d4_artifact_manifest,
        "d4_integrity": d4_integrity,
        "d4_overlap": d4_overlap,
        "d4_summary": d4_summary,
        "d4_jsonl_records": d4_jsonl_records,
        "d4_artifact_manifest_verified": True,
        "d4_jsonl_csv_transport_match": True,
    }


def _verify_expected_hashes(
    expected: Mapping[str, str],
    actual: Mapping[str, str],
) -> None:
    if set(expected) != set(actual):
        _fail(
            "actual_hash_inventory_mismatch",
            f"missing={sorted(set(expected) - set(actual))};"
            f"extra={sorted(set(actual) - set(expected))}",
        )
    for name in sorted(expected):
        if str(actual[name]) != str(expected[name]):
            _fail(
                "frozen_hash_mismatch",
                f"{name}:expected={expected[name]}:actual={actual[name]}",
            )


def _verify_candidate_bindings(
    *,
    candidate_manifest: Mapping[str, Any],
    bundle_manifest: Mapping[str, Any],
    training_audit: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    frozen_v4_manifest: Mapping[str, Any],
    actual: Mapping[str, str],
) -> None:
    if (
        candidate_manifest.get("candidate_id") != _EXPECTED_CANDIDATE_ID
        or candidate_manifest.get("model_version") != _EXPECTED_MODEL_VERSION
        or candidate_manifest.get("candidate_status")
        != "unregistered_edge_transfer_development"
    ):
        _fail("candidate_identity_mismatch", _EXPECTED_CANDIDATE_ID)
    expected_artifacts = {
        "bundle/manifest.json": actual["candidate_bundle_manifest_file"],
        "bundle/state_dict.pt": actual["candidate_state_file"],
        "source_binding.json": actual["candidate_source_binding_file"],
        "training_audit.json": actual["candidate_training_audit_file"],
        "training_config.json": actual["candidate_training_config_file"],
    }
    if candidate_manifest.get("artifact_files") != expected_artifacts:
        _fail("candidate_artifact_binding_mismatch", "artifact_files")
    candidate_bindings = {
        "content_sha256": actual["candidate_manifest_content"],
        "training_audit_content_sha256": actual[
            "candidate_training_audit_content"
        ],
        "model_state_content_sha256": actual["candidate_state_content"],
        "bundle_state_file_sha256": actual["candidate_state_file"],
        "dataset_sha256": actual["frozen_v4_dataset"],
        "dataset_split_sha256": actual["frozen_v4_split"],
        "base_v4_manifest_content_sha256": actual[
            "frozen_v4_manifest_content"
        ],
    }
    for field, expected in candidate_bindings.items():
        if candidate_manifest.get(field) != expected:
            _fail("candidate_manifest_binding_mismatch", field)
    bundle_bindings = {
        "content_sha256": actual["candidate_bundle_manifest_content"],
        "state_dict_file_sha256": actual["candidate_state_file"],
        "model_state_content_sha256": actual["candidate_state_content"],
        "training_audit_content_sha256": actual[
            "candidate_training_audit_content"
        ],
    }
    for field, expected in bundle_bindings.items():
        if bundle_manifest.get(field) != expected:
            _fail("candidate_bundle_binding_mismatch", field)
    if (
        training_audit.get("content_sha256")
        != actual["candidate_training_audit_content"]
        or training_audit.get("model_state_content_sha256")
        != actual["candidate_state_content"]
    ):
        _fail("candidate_training_audit_binding_mismatch", "content or model")
    source_bindings = {
        "dataset_sha256": actual["frozen_v4_dataset"],
        "dataset_split_sha256": actual["frozen_v4_split"],
        "base_v4_manifest_file_sha256": actual[
            "frozen_v4_manifest_file"
        ],
        "base_v4_manifest_content_sha256": actual[
            "frozen_v4_manifest_content"
        ],
        "base_v4_model_state_sha256": str(
            frozen_v4_manifest["base_v3_model_state_sha256"]
            if "base_v3_model_state_sha256" in frozen_v4_manifest
            else candidate_manifest["base_v4_model_state_sha256"]
        ),
    }
    for field, expected in source_bindings.items():
        if source_binding.get(field) != expected:
            _fail("candidate_source_binding_mismatch", field)
    if (
        source_binding.get("payload_splits_read") != ["train", "validation"]
        or source_binding.get("test_payload_read_count") != 0
        or source_binding.get("formal_holdout_payload_read_count") != 0
        or source_binding.get("source_evaluation_payload_read_count") != 0
        or source_binding.get("v5_candidate_consumed") is not False
    ):
        _fail("candidate_source_use_boundary_invalid", "source_binding")


def _verify_external_lineage_bindings(
    inputs: D4V6ExternalAuditInputs,
    *,
    source_dataset: Any,
    labeled_dataset: Any,
    derivation: Mapping[str, Any],
    evidence: Mapping[str, Any],
    export_summary: Mapping[str, Any],
    actual: Mapping[str, str],
) -> None:
    source_entries = derivation.get("source", {}).get("datasets", [])
    if len(source_entries) != 1:
        _fail("derivation_source_dataset_count_mismatch", str(len(source_entries)))
    source_entry = source_entries[0]
    if (
        source_entry.get("dataset_sha256")
        != source_dataset.manifest.dataset_sha256
        or source_entry.get("split_sha256")
        != source_dataset.manifest.split.split_sha256
    ):
        _fail("derivation_source_binding_mismatch", "source dataset")
    output = derivation.get("output", {})
    if (
        output.get("dataset_sha256")
        != labeled_dataset.manifest.dataset_sha256
        or output.get("split_sha256")
        != labeled_dataset.manifest.split.split_sha256
        or output.get("frame_count") != _EXPECTED_FRAME_COUNT
        or derivation.get("repository", {}).get("git_commit")
        != inputs.exporter_git_commit
        or derivation.get("repository", {}).get("source_worktree_dirty")
        is not False
    ):
        _fail("derivation_output_binding_mismatch", "labeled dataset")
    for label, payload in (
        ("external evidence", evidence),
        ("export summary", export_summary),
    ):
        if (
            payload.get("dataset_sha256") != actual["labeled_dataset"]
            or payload.get("dataset_split_sha256") != actual["labeled_split"]
            or payload.get("source_artifact_sha256")
            != actual["derivation_file"]
        ):
            _fail("external_lineage_binding_mismatch", label)
    if (
        export_summary.get("external_dataset_evidence_sha256")
        != actual["evidence_content"]
        or export_summary.get("observable_label_audit_sha256")
        != actual["label_audit_content"]
    ):
        _fail("export_summary_content_binding_mismatch", "evidence or label")


def _verify_d4_artifact_manifest(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    actual: Mapping[str, str],
) -> None:
    expected_files = {
        "REPORT_CN.md": actual["d4_report_file"],
        "evaluation_records.csv": actual["d4_records_csv_file"],
        "evaluation_records.jsonl": actual["d4_records_jsonl_file"],
        "external_evaluation_summary.json": actual["d4_summary_file"],
        "input_integrity.json": actual["d4_integrity_file"],
        "observable_overlap_audit.json": actual["d4_overlap_file"],
    }
    if manifest.get("artifact_files") != expected_files:
        _fail("d4_artifact_manifest_file_binding_mismatch", "artifact_files")
    actual_inventory = {
        path.name
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_inventory != set(expected_files) | {"artifact_manifest.json"}:
        _fail(
            "d4_artifact_file_inventory_mismatch",
            str(sorted(actual_inventory)),
        )
    for field in (
        "candidate_mutation_count",
        "input_mutation_count",
        "model_fit_count",
        "confidence_gate_application_count",
        "formal_holdout_payload_read_count",
    ):
        if manifest.get(field) != 0:
            _fail("d4_artifact_boundary_not_closed", field)
    if manifest.get("production_permission_available") is not False:
        _fail("d4_artifact_permission_not_closed", "production")


def _verify_d4_artifact_content_bindings(
    *,
    d4_summary: Mapping[str, Any],
    d4_integrity: Mapping[str, Any],
    d4_overlap: Mapping[str, Any],
    actual: Mapping[str, str],
) -> None:
    bindings = {
        "evaluation_records_jsonl_sha256": actual["d4_records_jsonl_file"],
        "evaluation_records_csv_sha256": actual["d4_records_csv_file"],
        "input_integrity_content_sha256": actual["d4_integrity_content"],
        "observable_overlap_content_sha256": actual["d4_overlap_content"],
    }
    for field, expected in bindings.items():
        if d4_summary.get(field) != expected:
            _fail("d4_summary_artifact_binding_mismatch", field)
    if (
        d4_integrity.get("content_sha256") != actual["d4_integrity_content"]
        or d4_overlap.get("content_sha256") != actual["d4_overlap_content"]
        or d4_summary.get("content_sha256") != actual["d4_summary_content"]
    ):
        _fail("d4_artifact_content_binding_mismatch", "content sha")


def _audit_seed_and_truth_governance(
    inputs: D4V6ExternalAuditInputs,
    *,
    anchors: Mapping[str, Any],
    api: Mapping[str, Any],
) -> dict[str, Any]:
    plan = anchors["generation_plan"]
    classes = _mapping(plan["seed_classes"], "seed classes")
    observed_classes = {
        "training": set(int(seed) for seed in classes["training_seeds"]),
        "formal_holdout": set(
            int(seed) for seed in classes["formal_holdout_seeds"]
        ),
        "prior_evaluation": set(
            int(seed) for seed in classes["prior_design_and_evaluation_seeds"]
        ),
        "pilot": set(int(seed) for seed in classes["design_pilot_seeds"]),
        "independent": set(
            int(seed) for seed in classes["independent_development_seeds"]
        ),
    }
    expected_classes = {
        "training": set(_EXPECTED_TRAINING_SEEDS),
        "formal_holdout": set(_EXPECTED_FORMAL_HOLDOUT_SEEDS),
        "prior_evaluation": set(_EXPECTED_PRIOR_EVALUATION_SEEDS),
        "pilot": set(_EXPECTED_PILOT_SEEDS),
        "independent": set(_EXPECTED_INDEPENDENT_SEEDS),
    }
    intersections = _validate_disjoint_seed_classes(
        observed_classes,
        expected_classes=expected_classes,
    )
    if set(int(seed) for seed in classes["requested_seeds"]) != set(
        inputs.expected_seeds
    ):
        _fail("requested_seed_inventory_mismatch", "generation plan")

    source_dataset = anchors["source_dataset"]
    labeled_dataset = anchors["labeled_dataset"]
    source_seeds = {
        int(episode.source.seed) for episode in source_dataset.episode_records
    }
    labeled_seeds = {
        int(episode.source.seed) for episode in labeled_dataset.episode_records
    }
    if (
        source_seeds != set(inputs.expected_seeds)
        or labeled_seeds != set(inputs.expected_seeds)
    ):
        _fail("external_dataset_seed_inventory_mismatch", "source or labeled")
    split_seed_sets = {
        split: {
            int(episode.source.seed)
            for episode in labeled_dataset.episodes(
                api["RegionLearningSplit"](split)
            )
        }
        for split in _SPLIT_ORDER
    }
    if set().union(*split_seed_sets.values()) != set(inputs.expected_seeds):
        _fail("external_split_seed_union_mismatch", "labeled dataset")
    for index, left in enumerate(_SPLIT_ORDER):
        for right in _SPLIT_ORDER[index + 1 :]:
            if split_seed_sets[left] & split_seed_sets[right]:
                _fail("external_split_seed_overlap", f"{left}:{right}")
    split_frame_counts = {
        split: sum(
            len(episode.frames)
            for episode in labeled_dataset.episodes(
                api["RegionLearningSplit"](split)
            )
        )
        for split in _SPLIT_ORDER
    }
    if split_frame_counts != _EXPECTED_FRAME_COUNTS:
        _fail("external_split_frame_count_mismatch", str(split_frame_counts))
    for dataset_name, dataset in (
        ("source", source_dataset),
        ("labeled", labeled_dataset),
    ):
        for episode in dataset.episode_records:
            if (
                episode.source.git_commit != inputs.source_git_commit
                or episode.source.git_dirty
                or episode.source.scenario_scale != _EXPECTED_SCALE
            ):
                _fail(
                    "external_episode_lineage_mismatch",
                    f"{dataset_name}:{episode.source.episode_id}",
                )

    generation_summary = anchors["generation_summary"]
    expected_generation = {
        "episode_count": _EXPECTED_EPISODE_COUNT,
        "frame_count": _EXPECTED_FRAME_COUNT,
        "model_fit_count": 0,
        "online_truth_use_count": 0,
        "prior_evaluation_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "production_permission_available": False,
        "repository_dirty_episode_count": 0,
    }
    for field, expected in expected_generation.items():
        if generation_summary.get(field) != expected:
            _fail("generation_summary_governance_mismatch", field)
    if (
        generation_summary.get("source", {}).get("git_commit")
        != inputs.source_git_commit
        or generation_summary.get("source", {}).get("repository_dirty")
        is not False
        or plan.get("source", {}).get("git_commit")
        != inputs.source_git_commit
        or plan.get("source", {}).get("repository_dirty") is not False
        or plan.get("online_truth_policy") != "forbidden"
        or plan.get("model_fit_allowed") is not False
        or plan.get("candidate_registration_allowed") is not False
    ):
        _fail("source_governance_boundary_mismatch", "plan or summary")

    derivation = anchors["derivation"]
    evidence = anchors["evidence"]
    export_summary = anchors["export_summary"]
    candidate_source = anchors["candidate_source_binding"]
    training_audit = anchors["candidate_training_audit"]
    d4_integrity = anchors["d4_integrity"]
    d4_summary = anchors["d4_summary"]
    _reject_truth_pollution(
        {
            "generation_summary": generation_summary,
            "derivation": derivation,
            "evidence": evidence,
            "export_summary": export_summary,
            "d4_integrity": d4_integrity,
            "d4_summary": d4_summary,
        }
    )
    label_audit = derivation.get("generation", {}).get(
        "observable_label_audit",
        {},
    )
    if (
        label_audit.get("model_input_key_scope")
        != "node_features_edge_features_edge_index_shape_dtype_values"
        or label_audit.get(
            "observable_key_uses_source_seed_episode_or_target"
        )
        is not False
        or label_audit.get("test_label_used_for_model_fit") is not False
        or label_audit.get(
            "validation_or_test_label_used_for_weight_fit"
        )
        is not False
        or evidence.get("truth_free_online_features") is not True
    ):
        _fail("online_observable_truth_boundary_invalid", "label audit")
    for label, payload in (
        ("candidate source binding", candidate_source),
        ("candidate training audit", training_audit),
        ("D4 input integrity", d4_integrity),
        ("D4 data usage", d4_summary.get("data_usage", {})),
    ):
        for field in (
            "formal_holdout_payload_read_count",
            "source_evaluation_payload_read_count",
            "old_external_evaluation_payload_read_count",
        ):
            if field in payload and payload.get(field) != 0:
                _fail("forbidden_payload_read_detected", f"{label}:{field}")
    if (
        training_audit.get("formal_holdout_payload_fit_count") != 0
        or training_audit.get("source_evaluation_payload_fit_count") != 0
        or d4_integrity.get("model_fit_count") != 0
        or d4_integrity.get("checkpoint_update_count") != 0
        or d4_integrity.get("threshold_tuning_count") != 0
    ):
        _fail("evaluation_data_fit_boundary_invalid", "fit or tuning")
    return {
        "passed": True,
        "seed_registry_id": classes["registry_id"],
        "configured_seed_classes": {
            name: sorted(values) for name, values in observed_classes.items()
        },
        "pairwise_seed_intersections": intersections,
        "source_dataset_seed_set": sorted(source_seeds),
        "labeled_dataset_seed_set": sorted(labeled_seeds),
        "external_split_seed_sets": {
            split: sorted(seeds) for split, seeds in split_seed_sets.items()
        },
        "external_split_frame_counts": split_frame_counts,
        "source_clean_commit": inputs.source_git_commit,
        "exporter_clean_commit": inputs.exporter_git_commit,
        "online_truth_use_count": 0,
        "truth_identifier_use_count": 0,
        "old_evaluation_3008_3039_payload_read_count": 0,
        "formal_holdout_1000_1019_payload_read_count": 0,
        "model_fit_count": 0,
        "checkpoint_update_count": 0,
        "threshold_tuning_count": 0,
    }


def _validate_disjoint_seed_classes(
    observed: Mapping[str, set[int]],
    *,
    expected_classes: Mapping[str, set[int]],
) -> dict[str, list[int]]:
    if set(observed) != set(expected_classes):
        _fail("seed_class_name_mismatch", str(sorted(observed)))
    for name in expected_classes:
        if set(observed[name]) != set(expected_classes[name]):
            _fail("seed_class_mismatch", name)
    intersections: dict[str, list[int]] = {}
    names = tuple(expected_classes)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = sorted(set(observed[left]) & set(observed[right]))
            intersections[f"{left}__{right}"] = overlap
            if overlap:
                _fail("seed_class_overlap", f"{left}:{right}:{overlap}")
    return intersections


def _reject_truth_pollution(
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    count_fields = {
        "online_truth_use_count",
        "truth_identifier_use_count",
        "future_outcome_use_count",
    }
    forbidden_true_fields = {
        "observable_key_uses_truth",
        "observable_key_uses_source_seed_episode_or_target",
    }

    def walk(name: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if key in count_fields and nested != 0:
                    _fail("online_truth_pollution_detected", f"{name}:{key}")
                if key in forbidden_true_fields and nested is not False:
                    _fail("online_truth_pollution_detected", f"{name}:{key}")
                walk(f"{name}.{key}", nested)
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                walk(f"{name}[{index}]", nested)

    for name, payload in payloads.items():
        walk(name, payload)


def _recompute_records(
    loaded: Any,
    *,
    model: Any,
    candidate_manifest: Mapping[str, Any],
    api: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    projector = api["DeterministicResourceProjector"](api["_V4_PROJECTION"])
    rule_policy = api["RuleRegionResourcePolicy"](
        api["_V4_RULE_CONFIG"],
        projector=projector,
    )
    actor = api["LearnedRegionResourcePolicy"](
        model,
        _PolicyIdentity(
            _EXPECTED_MODEL_VERSION,
            str(candidate_manifest["bundle_state_file_sha256"]),
        ),
    )
    records: list[dict[str, Any]] = []
    for split_name in _SPLIT_ORDER:
        split = api["RegionLearningSplit"](split_name)
        for episode in loaded.episodes(split):
            for frame in episode.frames:
                if (
                    frame.target.availability
                    != api["RegionLearningAvailability"].AVAILABLE
                    or frame.target.recommendation is None
                ):
                    _fail(
                        "external_target_unavailable",
                        f"{episode.source.episode_id}:{frame.frame_index}",
                    )
                target = frame.target.recommendation
                r0 = rule_policy.recommend(frame.snapshot)
                raw = actor.recommend_raw(frame.snapshot)
                projected = projector.project(frame.snapshot, raw)
                target_signature, target_payload = api["executable_signature"](
                    projector.build_advisory_contract(frame.snapshot, target)
                )
                r0_signature, r0_payload = api["executable_signature"](
                    projector.build_advisory_contract(frame.snapshot, r0)
                )
                actor_signature, actor_payload = api["executable_signature"](
                    projector.build_advisory_contract(frame.snapshot, projected)
                )
                rule_positive = target_signature != r0_signature
                if rule_positive:
                    target_valid, target_reasons = api[
                        "evaluate_v4_intervention_invariants"
                    ](
                        frame.snapshot,
                        target,
                        r0,
                        gate=api["REGION_RESOURCE_V4_INTERVENTION_GATE"],
                        projector=projector,
                        formal_decision=None,
                    )
                    if not target_valid:
                        _fail(
                            "unsafe_rule_positive_target",
                            ",".join(target_reasons),
                        )
                actor_executable = actor_signature != r0_signature
                actor_valid = True
                invariant_reasons: tuple[str, ...] = ()
                if actor_executable:
                    actor_valid, invariant_reasons = api[
                        "evaluate_v4_intervention_invariants"
                    ](
                        frame.snapshot,
                        projected,
                        r0,
                        gate=api["REGION_RESOURCE_V4_INTERVENTION_GATE"],
                        projector=projector,
                        formal_decision=None,
                    )
                rejection_reasons = tuple(projected.projection_rejections)
                transfer_errors = _classify_transfer_errors(
                    _transfer_map(target_payload),
                    _transfer_map(actor_payload),
                )
                raw_transfer_count = len(raw.transfers)
                projected_transfer_count = len(projected.transfers)
                exact_target = actor_signature == target_signature
                exact_positive = bool(
                    rule_positive
                    and exact_target
                    and actor_executable
                    and actor_valid
                    and not rejection_reasons
                )
                negative_exact_r0 = bool(
                    not rule_positive
                    and actor_signature == r0_signature
                    and not rejection_reasons
                )
                actor_derived_positive = bool(
                    actor_executable
                    and actor_valid
                    and not rejection_reasons
                )
                failure_reasons: list[str] = []
                if rejection_reasons:
                    failure_reasons.append("projection_rejected")
                if actor_executable and not actor_valid:
                    failure_reasons.append("invariant_failure")
                if rule_positive and not exact_positive:
                    failure_reasons.append("positive_exact_action_missed")
                if not rule_positive and not negative_exact_r0:
                    failure_reasons.append("negative_r0_missed")
                if transfer_errors["wrong_direction_count"]:
                    failure_reasons.append("wrong_direction")
                if transfer_errors["wrong_quantity_count"]:
                    failure_reasons.append("wrong_quantity")
                if not rule_positive and projected_transfer_count > 0:
                    failure_reasons.append("false_transfer")
                graph = api["snapshot_to_region_graph"](
                    frame.snapshot,
                    device="cpu",
                )
                records.append(
                    {
                        "schema": D4_V6_EXTERNAL_RECORD_SCHEMA,
                        "evaluation_available": True,
                        "unavailable_reason": None,
                        "split": split_name,
                        "source_episode_id": episode.source.episode_id,
                        "seed": int(episode.source.seed),
                        "frame_index": int(frame.frame_index),
                        "snapshot_id": frame.snapshot.snapshot_id,
                        "observable_key_sha256": _observable_graph_key(
                            graph,
                            architecture=api["REGION_GRAPH_ARCHITECTURE"],
                        ),
                        "rule_positive": rule_positive,
                        "rule_negative": not rule_positive,
                        "target_transfer_count": len(target.transfers),
                        "target_transfer_resource_count": sum(
                            item.resource_count for item in target.transfers
                        ),
                        "actor_raw_transfer_count": raw_transfer_count,
                        "actor_raw_transfer_resource_count": sum(
                            item.resource_count for item in raw.transfers
                        ),
                        "actor_projected_transfer_count": (
                            projected_transfer_count
                        ),
                        "actor_projected_transfer_resource_count": sum(
                            item.resource_count
                            for item in projected.transfers
                        ),
                        "correct_directed_edge_count": transfer_errors[
                            "correct_directed_edge_count"
                        ],
                        "correct_directed_edge_frame": bool(
                            rule_positive
                            and transfer_errors["correct_directed_edge_count"]
                            == len(target.transfers)
                            and len(target.transfers) > 0
                        ),
                        "projected_exact_positive_action": exact_positive,
                        "negative_exact_r0": negative_exact_r0,
                        "wrong_direction_count": transfer_errors[
                            "wrong_direction_count"
                        ],
                        "wrong_quantity_count": transfer_errors[
                            "wrong_quantity_count"
                        ],
                        "wrong_edge_count": transfer_errors[
                            "wrong_edge_count"
                        ],
                        "false_transfer_count": (
                            projected_transfer_count
                            if not rule_positive
                            else 0
                        ),
                        "projection_rejection_count": len(rejection_reasons),
                        "projection_rejected": bool(rejection_reasons),
                        "projection_rejection_reasons": list(
                            rejection_reasons
                        ),
                        "invariant_failure": bool(
                            actor_executable and not actor_valid
                        ),
                        "invariant_failure_reasons": list(invariant_reasons),
                        "actor_executable_difference": actor_executable,
                        "actor_derived_positive": actor_derived_positive,
                        "confidence_gate_available": False,
                        "confidence_gate_applied": False,
                        "confidence_threshold_passed": None,
                        "admission_evaluated": False,
                        "rule_fallback_required": True,
                        "failure_reasons": list(
                            dict.fromkeys(failure_reasons)
                        ),
                    }
                )
    if len(records) != _EXPECTED_FRAME_COUNT:
        _fail("recomputed_frame_count_mismatch", str(len(records)))
    return tuple(records)


def _transfer_map(
    advisory_payload: Mapping[str, Any],
) -> dict[tuple[str, str, str], int]:
    result: dict[tuple[str, str, str], int] = {}
    for item in advisory_payload["transfer_allowances"]:
        key = (
            str(item["source_region_id"]),
            str(item["target_region_id"]),
            str(item["edge_id"]),
        )
        result[key] = result.get(key, 0) + int(item["resource_count"])
    return result


def _classify_transfer_errors(
    target: Mapping[tuple[str, str, str], int],
    predicted: Mapping[tuple[str, str, str], int],
) -> dict[str, int]:
    target_keys = set(target)
    predicted_keys = set(predicted)
    correct = target_keys & predicted_keys
    wrong_direction = 0
    wrong_edge = 0
    for source, destination, _edge_id in predicted_keys - target_keys:
        reversed_direction = any(
            target_source == destination and target_destination == source
            for target_source, target_destination, _ in target_keys
        )
        if reversed_direction:
            wrong_direction += 1
        else:
            wrong_edge += 1
    wrong_quantity = sum(
        int(predicted[key] != target[key]) for key in correct
    )
    return {
        "correct_directed_edge_count": len(correct),
        "wrong_direction_count": wrong_direction,
        "wrong_quantity_count": wrong_quantity,
        "wrong_edge_count": wrong_edge,
    }


def _summarise_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    available = tuple(row for row in records if row["evaluation_available"])
    positives = tuple(row for row in available if row["rule_positive"])
    negatives = tuple(row for row in available if row["rule_negative"])
    actor_derived = tuple(
        row for row in available if row["actor_derived_positive"]
    )
    exact_positive = sum(
        bool(row["projected_exact_positive_action"]) for row in available
    )
    negative_exact = sum(bool(row["negative_exact_r0"]) for row in available)
    actor_exact = sum(
        bool(row["actor_derived_positive"])
        and bool(row["projected_exact_positive_action"])
        for row in available
    )
    positive_rate = _rate_metric(exact_positive, len(positives))
    negative_rate = _rate_metric(negative_exact, len(negatives))
    actor_rate = _rate_metric(actor_exact, len(actor_derived))
    return {
        "sample_count": len(records),
        "available_sample_count": len(available),
        "unavailable_sample_count": len(records) - len(available),
        "rule_positive_count": len(positives),
        "rule_negative_count": len(negatives),
        "actor_raw_transfer_count": sum(
            int(row["actor_raw_transfer_count"]) for row in available
        ),
        "actor_raw_transfer_resource_count": sum(
            int(row["actor_raw_transfer_resource_count"]) for row in available
        ),
        "actor_projected_transfer_count": sum(
            int(row["actor_projected_transfer_count"]) for row in available
        ),
        "actor_projected_transfer_resource_count": sum(
            int(row["actor_projected_transfer_resource_count"])
            for row in available
        ),
        "correct_directed_edge_count": sum(
            int(row["correct_directed_edge_count"]) for row in available
        ),
        "correct_directed_edge_frame_count": sum(
            bool(row["correct_directed_edge_frame"]) for row in available
        ),
        "projected_exact_positive_action_count": exact_positive,
        "positive_exact_action_recall": positive_rate["value"],
        "positive_exact_action_recall_status": (
            "available"
            if positive_rate["availability"] == "available"
            else "unavailable_zero_rule_positive_denominator"
        ),
        "rule_positive_exact_action_recall_metric": positive_rate,
        "negative_exact_r0_count": negative_exact,
        "negative_exact_r0_rate": negative_rate["value"],
        "negative_exact_r0_rate_status": (
            "available"
            if negative_rate["availability"] == "available"
            else "unavailable_zero_rule_negative_denominator"
        ),
        "negative_exact_r0_rate_metric": negative_rate,
        "wrong_direction_count": sum(
            int(row["wrong_direction_count"]) for row in available
        ),
        "wrong_quantity_count": sum(
            int(row["wrong_quantity_count"]) for row in available
        ),
        "wrong_edge_count": sum(
            int(row["wrong_edge_count"]) for row in available
        ),
        "false_transfer_count": sum(
            int(row["false_transfer_count"]) for row in available
        ),
        "projection_rejection_count": sum(
            int(row["projection_rejection_count"]) for row in available
        ),
        "projection_rejection_frame_count": sum(
            bool(row["projection_rejected"]) for row in available
        ),
        "invariant_failure_count": sum(
            bool(row["invariant_failure"]) for row in available
        ),
        "actor_derived_positive_denominator_count": len(actor_derived),
        "actor_derived_positive_denominator_available": bool(actor_derived),
        "actor_derived_exact_positive_count": actor_exact,
        "actor_derived_exact_positive_rate": actor_rate["value"],
        "actor_derived_exact_positive_rate_status": (
            "available"
            if actor_rate["availability"] == "available"
            else "unavailable_zero_actor_derived_positive_denominator"
        ),
        "actor_derived_exact_positive_rate_metric": actor_rate,
        "confidence_gate_available": False,
        "confidence_gate_application_count": 0,
        "admission_evaluation_count": 0,
        "all_frames_rule_fallback_required": all(
            bool(row["rule_fallback_required"]) for row in records
        ),
        "unavailable_reasons": _reason_inventory(
            row["unavailable_reason"]
            for row in records
            if not row["evaluation_available"]
        ),
        "failure_reasons": _reason_inventory(
            reason
            for row in available
            for reason in row["failure_reasons"]
        ),
        "projection_rejection_reasons": _reason_inventory(
            reason
            for row in available
            for reason in row["projection_rejection_reasons"]
        ),
        "invariant_failure_reasons": _reason_inventory(
            reason
            for row in available
            for reason in row["invariant_failure_reasons"]
        ),
    }


def _rate_metric(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator <= 0:
        return {
            "availability": "unavailable",
            "value": None,
            "numerator": int(numerator),
            "denominator": int(denominator),
        }
    return {
        "availability": "available",
        "value": float(numerator) / float(denominator),
        "numerator": int(numerator),
        "denominator": int(denominator),
    }


def _validate_recomputed_inventory(
    split_metrics: Mapping[str, Mapping[str, Any]],
    aggregate: Mapping[str, Any],
) -> None:
    frame_counts = {
        split: int(metrics["sample_count"])
        for split, metrics in split_metrics.items()
    }
    positive_counts = {
        split: int(metrics["rule_positive_count"])
        for split, metrics in split_metrics.items()
    }
    negative_counts = {
        split: int(metrics["rule_negative_count"])
        for split, metrics in split_metrics.items()
    }
    if (
        frame_counts != _EXPECTED_FRAME_COUNTS
        or positive_counts != _EXPECTED_POSITIVE_COUNTS
        or negative_counts != _EXPECTED_NEGATIVE_COUNTS
    ):
        _fail(
            "recomputed_action_inventory_mismatch",
            f"frames={frame_counts}:positive={positive_counts}:"
            f"negative={negative_counts}",
        )
    expected_aggregate = {
        "sample_count": 126,
        "rule_positive_count": 42,
        "rule_negative_count": 84,
        "actor_raw_transfer_count": 0,
        "actor_projected_transfer_count": 0,
        "projected_exact_positive_action_count": 0,
        "negative_exact_r0_count": 77,
        "wrong_direction_count": 0,
        "wrong_quantity_count": 0,
        "wrong_edge_count": 0,
        "false_transfer_count": 0,
        "projection_rejection_count": 0,
        "invariant_failure_count": 15,
        "actor_derived_positive_denominator_count": 0,
    }
    for field, expected in expected_aggregate.items():
        if aggregate.get(field) != expected:
            _fail("recomputed_aggregate_mismatch", f"{field}:{aggregate.get(field)}")
    actor_metric = aggregate["actor_derived_exact_positive_rate_metric"]
    if (
        actor_metric["availability"] != "unavailable"
        or actor_metric["value"] is not None
        or actor_metric["denominator"] != 0
    ):
        _fail("actor_derived_zero_denominator_misreported", str(actor_metric))
    positive_metric = aggregate["rule_positive_exact_action_recall_metric"]
    if (
        positive_metric["availability"] != "available"
        or positive_metric["value"] != 0.0
        or positive_metric["numerator"] != 0
        or positive_metric["denominator"] != 42
    ):
        _fail("rule_positive_recall_misreported", str(positive_metric))


def _audit_observable_independence(
    frozen_v4: Any,
    external: Any,
    *,
    recomputed_records: Sequence[Mapping[str, Any]],
    d4_overlap: Mapping[str, Any],
    api: Mapping[str, Any],
) -> dict[str, Any]:
    old_keys: list[str] = []
    for split in (
        api["RegionLearningSplit"].TRAIN,
        api["RegionLearningSplit"].VALIDATION,
    ):
        for episode in frozen_v4.episodes(split):
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
    external_by_split: dict[str, list[str]] = {}
    record_index = {
        (
            str(row["split"]),
            str(row["source_episode_id"]),
            int(row["frame_index"]),
        ): str(row["observable_key_sha256"])
        for row in recomputed_records
    }
    for split_name in _SPLIT_ORDER:
        values: list[str] = []
        split = api["RegionLearningSplit"](split_name)
        for episode in external.episodes(split):
            for frame in episode.frames:
                graph = api["snapshot_to_region_graph"](
                    frame.snapshot,
                    device="cpu",
                )
                key = _observable_graph_key(
                    graph,
                    architecture=api["REGION_GRAPH_ARCHITECTURE"],
                )
                record_key = (
                    split_name,
                    episode.source.episode_id,
                    int(frame.frame_index),
                )
                if record_index.get(record_key) != key:
                    _fail("recomputed_observable_key_mismatch", str(record_key))
                values.append(key)
        external_by_split[split_name] = values
    old_unique = set(old_keys)
    external_flat = [
        key
        for split_name in _SPLIT_ORDER
        for key in external_by_split[split_name]
    ]
    external_unique = set(external_flat)
    overlap = old_unique & external_unique
    if (
        len(old_keys) != _EXPECTED_OLD_FRAME_COUNT
        or len(old_unique) != _EXPECTED_OLD_UNIQUE_KEY_COUNT
        or len(external_flat) != _EXPECTED_FRAME_COUNT
        or len(external_unique) != _EXPECTED_EXTERNAL_UNIQUE_KEY_COUNT
        or overlap
    ):
        _fail(
            "observable_independence_inventory_mismatch",
            f"old={len(old_keys)}/{len(old_unique)}:"
            f"external={len(external_flat)}/{len(external_unique)}:"
            f"overlap={len(overlap)}",
        )
    expected_d4 = {
        "observable_key_scope": (
            "node_features_edge_features_edge_index_shape_dtype_values"
        ),
        "observable_key_uses_seed": False,
        "observable_key_uses_episode_identity": False,
        "observable_key_uses_target_label": False,
        "observable_key_uses_truth": False,
        "frozen_v4_train_validation_unique_key_count": len(old_unique),
        "external_unique_key_count": len(external_unique),
        "exact_observable_key_intersection_count": 0,
        "source_independent_exact_observable_keys": True,
    }
    for field, expected in expected_d4.items():
        if d4_overlap.get(field) != expected:
            _fail("d4_observable_overlap_claim_mismatch", field)
    return {
        "passed": True,
        "observable_key_definition": (
            "architecture plus node_features, edge_features, and edge_index "
            "shape/dtype/value"
        ),
        "forbidden_identity_fields": [
            "seed",
            "episode_id",
            "source_episode_id",
            "target",
            "target_label",
            "truth",
        ],
        "forbidden_identity_field_count": 0,
        "frozen_v4_train_validation_frame_count": len(old_keys),
        "frozen_v4_train_validation_unique_key_count": len(old_unique),
        "external_frame_count": len(external_flat),
        "external_unique_key_count": len(external_unique),
        "external_unique_key_count_by_split": {
            split: len(set(keys))
            for split, keys in external_by_split.items()
        },
        "exact_observable_key_overlap_count": 0,
        "exact_overlap_keys": [],
    }


def _reconcile_d4_evaluation(
    anchors: Mapping[str, Any],
    *,
    recomputed_records: Sequence[Mapping[str, Any]],
    split_metrics: Mapping[str, Mapping[str, Any]],
    aggregate: Mapping[str, Any],
) -> dict[str, Any]:
    persisted = anchors["d4_jsonl_records"]
    if len(persisted) != len(recomputed_records):
        _fail(
            "d4_record_count_mismatch",
            f"persisted={len(persisted)}:recomputed={len(recomputed_records)}",
        )
    record_mismatches: list[dict[str, Any]] = []
    for index, (claimed, recomputed) in enumerate(
        zip(persisted, recomputed_records, strict=True)
    ):
        if claimed != recomputed:
            differing = sorted(
                field
                for field in set(claimed) | set(recomputed)
                if claimed.get(field) != recomputed.get(field)
            )
            record_mismatches.append(
                {
                    "index": index,
                    "identity": {
                        "split": recomputed.get("split"),
                        "source_episode_id": recomputed.get(
                            "source_episode_id"
                        ),
                        "frame_index": recomputed.get("frame_index"),
                    },
                    "fields": differing,
                }
            )
    if record_mismatches:
        _fail(
            "d4_frame_record_recomputation_mismatch",
            json.dumps(
                record_mismatches[:3],
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    persisted_metrics = {
        split: _summarise_records(
            tuple(row for row in persisted if row["split"] == split)
        )
        for split in _SPLIT_ORDER
    }
    persisted_aggregate = _summarise_records(persisted)
    if (
        persisted_metrics != split_metrics
        or persisted_aggregate != aggregate
    ):
        _fail("d4_record_metric_recomputation_mismatch", "records")
    summary_reconciliation = _compare_d4_summary_claims(
        split_metrics,
        aggregate,
        anchors["d4_summary"],
        fail_on_mismatch=True,
    )
    return {
        "passed": True,
        "d4_summary_used_as_metric_source": False,
        "d4_jsonl_record_count": len(persisted),
        "d4_csv_record_count": len(persisted),
        "recomputed_record_count": len(recomputed_records),
        "frame_record_mismatch_count": 0,
        "d4_jsonl_csv_transport_mismatch_count": 0,
        "d4_summary_claim_mismatch_count": 0,
        "artifact_manifest_file_sha256": anchors["actual_sha256"][
            "d4_artifact_manifest_file"
        ],
        "artifact_manifest_content_sha256": anchors["actual_sha256"][
            "d4_artifact_manifest_content"
        ],
        "evaluation_records_jsonl_sha256": anchors["actual_sha256"][
            "d4_records_jsonl_file"
        ],
        "evaluation_records_csv_sha256": anchors["actual_sha256"][
            "d4_records_csv_file"
        ],
        "summary_reconciliation": summary_reconciliation,
    }


def _compare_d4_summary_claims(
    split_metrics: Mapping[str, Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    d4_summary: Mapping[str, Any],
    *,
    fail_on_mismatch: bool,
) -> dict[str, Any]:
    expected_by_split = {
        split: _d4_metric_view(split_metrics[split])
        for split in _SPLIT_ORDER
    }
    expected_aggregate = _d4_metric_view(aggregate)
    mismatches: list[str] = []
    if d4_summary.get("metrics_by_split") != expected_by_split:
        mismatches.append("metrics_by_split")
    if d4_summary.get("aggregate_metrics") != expected_aggregate:
        mismatches.append("aggregate_metrics")
    fixed_claims = {
        "scenario_scale": _EXPECTED_SCALE,
        "region_count": _EXPECTED_REGION_COUNT,
        "source_episode_count": _EXPECTED_EPISODE_COUNT,
        "source_frame_count": _EXPECTED_FRAME_COUNT,
        "source_seed_range": [min(_EXPECTED_SEEDS), max(_EXPECTED_SEEDS)],
    }
    for field, expected in fixed_claims.items():
        if d4_summary.get(field) != expected:
            mismatches.append(field)
    data_usage = d4_summary.get("data_usage", {})
    usage_expected = {
        "payload_read_count_by_split": dict(_EXPECTED_FRAME_COUNTS),
        "model_fit_count": 0,
        "checkpoint_update_count": 0,
        "threshold_tuning_count": 0,
        "confidence_gate_application_count": 0,
        "old_external_evaluation_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "truth_identifier_use_count": 0,
        "production_permission_available": False,
    }
    for field, expected in usage_expected.items():
        if data_usage.get(field) != expected:
            mismatches.append(f"data_usage.{field}")
    if mismatches and fail_on_mismatch:
        _fail("d4_summary_claim_mismatch", ",".join(sorted(set(mismatches))))
    return {
        "passed": not mismatches,
        "summary_used_as_metric_source": False,
        "mismatch_count": len(set(mismatches)),
        "mismatched_fields": sorted(set(mismatches)),
        "recomputed_rule_positive_count": int(
            aggregate["rule_positive_count"]
        ),
        "recomputed_projected_exact_positive_action_count": int(
            aggregate["projected_exact_positive_action_count"]
        ),
    }


def _d4_metric_view(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {field: metrics[field] for field in _D4_METRIC_FIELDS}


def _audit_no_confidence_gate(
    *,
    candidate_manifest: Mapping[str, Any],
    bundle_manifest: Mapping[str, Any],
    d4_integrity: Mapping[str, Any],
    d4_summary: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    status = d4_summary.get("candidate_status", {})
    data_usage = d4_summary.get("data_usage", {})
    invalid = []
    if (
        candidate_manifest.get("confidence_calibration_status")
        != "not_started_actor_must_freeze_first"
    ):
        invalid.append("candidate_confidence_calibration_status")
    if bundle_manifest.get("runtime_confidence_gate_available") is not False:
        invalid.append("bundle_runtime_confidence_gate_available")
    if status.get("confidence_calibration_available") is not False:
        invalid.append("summary_confidence_calibration_available")
    if status.get("confidence_gate_available") is not False:
        invalid.append("summary_confidence_gate_available")
    if status.get("uncalibrated_confidence_head_used_for_gate") is not False:
        invalid.append("summary_uncalibrated_head_gate")
    if data_usage.get("confidence_gate_application_count") != 0:
        invalid.append("summary_confidence_gate_application_count")
    if d4_integrity.get("confidence_gate_application_count") != 0:
        invalid.append("integrity_confidence_gate_application_count")
    for index, row in enumerate(records):
        if (
            row.get("confidence_gate_available") is not False
            or row.get("confidence_gate_applied") is not False
            or row.get("confidence_threshold_passed") is not None
            or row.get("admission_evaluated") is not False
        ):
            invalid.append(f"record_{index}_confidence_or_admission")
            break
    if invalid:
        _fail("uncalibrated_confidence_gate_forbidden", ",".join(invalid))
    return {
        "passed": True,
        "confidence_calibrator_available": False,
        "confidence_gate_available": False,
        "confidence_gate_application_count": 0,
        "threshold_decision_count": 0,
        "admission_evaluation_count": 0,
        "reserved_manifest_value": candidate_manifest.get(
            "fixed_minimum_confidence"
        ),
        "reserved_0_60_gate_applied": False,
        "reason": (
            "v6 actor has no frozen confidence calibrator; the manifest value "
            "is not an executable gate"
        ),
    }


def _audit_closed_permissions(
    candidate_manifest: Mapping[str, Any],
    d4_summary: Mapping[str, Any],
) -> dict[str, Any]:
    permissions = _mapping(
        candidate_manifest.get("permissions"),
        "candidate permissions",
    )
    permission_values = {
        name: value for name, value in permissions.items() if name != "schema"
    }
    if (
        not permission_values
        or any(type(value) is not bool or value for value in permission_values.values())
    ):
        _fail("candidate_permission_not_closed", "candidate manifest")
    for field, expected in (
        ("development_only", True),
        ("shadow_only", True),
        ("admission_closed", True),
        ("rule_fallback_required", True),
        ("formal_holdout_evaluated", False),
        ("runtime_preflight_completed", False),
    ):
        if candidate_manifest.get(field) is not expected:
            _fail("candidate_lifecycle_not_closed", field)
    summary_permissions = d4_summary.get("candidate_status", {}).get(
        "permissions",
        {},
    )
    if (
        not summary_permissions
        or any(value is not False for value in summary_permissions.values())
    ):
        _fail("d4_summary_permission_not_closed", "candidate status")
    return {
        "all_permission_fields_false": True,
        "candidate_unregistered": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "assist_enabled": False,
        "assignment_enabled": False,
        "degradation_enabled": False,
        "takeover_enabled": False,
        "coalition_commit_enabled": False,
        "control_enabled": False,
        "physical_permission_available": False,
        "d3_permission_available": False,
        "d7_permission_available": False,
        "runtime_preflight_run_count": 0,
        "control_command_count": 0,
        "authorization_artifact_count": 0,
    }


def _verify_csv_matches_jsonl(
    csv_path: Path,
    jsonl_records: Sequence[Mapping[str, Any]],
) -> None:
    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        csv_rows = list(reader)
    if len(csv_rows) != len(jsonl_records):
        _fail(
            "d4_csv_jsonl_count_mismatch",
            f"csv={len(csv_rows)}:jsonl={len(jsonl_records)}",
        )
    expected_fields = set(jsonl_records[0]) if jsonl_records else set()
    if reader.fieldnames is None or set(reader.fieldnames) != expected_fields:
        _fail("d4_csv_header_mismatch", str(reader.fieldnames))
    for index, (csv_row, json_row) in enumerate(
        zip(csv_rows, jsonl_records, strict=True)
    ):
        encoded = {
            name: _csv_transport_value(value)
            for name, value in json_row.items()
        }
        if csv_row != encoded:
            differing = sorted(
                name
                for name in set(csv_row) | set(encoded)
                if csv_row.get(name) != encoded.get(name)
            )
            _fail(
                "d4_csv_jsonl_transport_mismatch",
                f"row={index}:fields={differing}",
            )


def _csv_transport_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    return str(value)


def _observable_graph_key(graph: Any, *, architecture: str) -> str:
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


def _model_state_content_sha256(model: Any) -> str:
    digest = sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(
            json.dumps(list(value.shape), separators=(",", ":")).encode(
                "ascii"
            )
        )
        digest.update(value.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _reason_inventory(values: Sequence[Any] | Any) -> dict[str, int]:
    inventory: dict[str, int] = {}
    for value in values:
        if value is None:
            continue
        key = str(value)
        inventory[key] = inventory.get(key, 0) + 1
    return dict(sorted(inventory.items()))


def _write_split_csv(path: Path, result: Mapping[str, Any]) -> None:
    rows = result["independent_recomputation"]["split_metrics"]
    fieldnames = (
        "split",
        "sample_count",
        "rule_positive_count",
        "rule_negative_count",
        "actor_raw_transfer_count",
        "actor_projected_transfer_count",
        "projected_exact_positive_action_count",
        "rule_positive_recall_availability",
        "rule_positive_recall",
        "rule_positive_recall_numerator",
        "rule_positive_recall_denominator",
        "negative_exact_r0_count",
        "negative_exact_r0_rate",
        "actor_derived_positive_denominator_count",
        "actor_derived_rate_availability",
        "actor_derived_rate",
        "wrong_direction_count",
        "wrong_quantity_count",
        "wrong_edge_count",
        "false_transfer_count",
        "projection_rejection_count",
        "invariant_failure_count",
        "confidence_gate_application_count",
        "rule_fallback_required",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for split in _SPLIT_ORDER:
            row = rows[split]
            positive = row["rule_positive_exact_action_recall_metric"]
            actor = row["actor_derived_exact_positive_rate_metric"]
            writer.writerow(
                {
                    "split": split,
                    "sample_count": row["sample_count"],
                    "rule_positive_count": row["rule_positive_count"],
                    "rule_negative_count": row["rule_negative_count"],
                    "actor_raw_transfer_count": row[
                        "actor_raw_transfer_count"
                    ],
                    "actor_projected_transfer_count": row[
                        "actor_projected_transfer_count"
                    ],
                    "projected_exact_positive_action_count": row[
                        "projected_exact_positive_action_count"
                    ],
                    "rule_positive_recall_availability": positive[
                        "availability"
                    ],
                    "rule_positive_recall": positive["value"],
                    "rule_positive_recall_numerator": positive["numerator"],
                    "rule_positive_recall_denominator": positive[
                        "denominator"
                    ],
                    "negative_exact_r0_count": row["negative_exact_r0_count"],
                    "negative_exact_r0_rate": row["negative_exact_r0_rate"],
                    "actor_derived_positive_denominator_count": row[
                        "actor_derived_positive_denominator_count"
                    ],
                    "actor_derived_rate_availability": actor["availability"],
                    "actor_derived_rate": actor["value"],
                    "wrong_direction_count": row["wrong_direction_count"],
                    "wrong_quantity_count": row["wrong_quantity_count"],
                    "wrong_edge_count": row["wrong_edge_count"],
                    "false_transfer_count": row["false_transfer_count"],
                    "projection_rejection_count": row[
                        "projection_rejection_count"
                    ],
                    "invariant_failure_count": row[
                        "invariant_failure_count"
                    ],
                    "confidence_gate_application_count": row[
                        "confidence_gate_application_count"
                    ],
                    "rule_fallback_required": row[
                        "all_frames_rule_fallback_required"
                    ],
                }
            )


def _render_chinese_report(result: Mapping[str, Any]) -> str:
    aggregate = result["independent_recomputation"]["aggregate"]
    split_metrics = result["independent_recomputation"]["split_metrics"]
    anchors = result["anchors"]["actual_sha256"]
    observable = result["observable_independence"]
    immutability = result["input_immutability"]
    lines = [
        "# D4 v6 来源独立评价 D6 盲审",
        "",
        "## 结论",
        "",
        (
            "D6 从冻结标签数据、v6 模型参数和同快照规则策略重新计算 126 帧动作，"
            "没有采用 D4 汇总字段作为指标来源。逐帧重算结果与 D4 JSONL、CSV 一致，"
            "D4 artifact manifest 的文件摘要和内容摘要均通过。"
        ),
        (
            "规则正类为 42 帧，冻结 actor 精确命中 0 帧，规则正类精确动作召回为 "
            "0/42。actor 没有形成任何通过约束的可执行正动作，actor-derived positive "
            "分母为 0，对应比率保持 unavailable。"
        ),
        (
            "v6 没有置信校准器，0.60 只是在 manifest 中保留的数值，本轮没有应用该门。"
            "候选不得冻结、不得进入置信校准、不得读取正式留出集，也不得产生 D3、D7 "
            "或控制权限。全部 126 帧继续规则回退。"
        ),
        "",
        "## 数据边界",
        "",
        "| 项目 | 结果 |",
        "| --- | ---: |",
        "| 规模 | M16N24，8 区域 |",
        "| episode | 64 |",
        "| 帧 | 126 |",
        "| seed | 4016-4079 |",
        "| train/validation/test 帧 | 89/20/17 |",
        "| 正式留出 seed 1000-1019 读取 | 0 |",
        "| 旧评价 seed 3008-3039 读取 | 0 |",
        "| 模型拟合/检查点更新/阈值调整 | 0/0/0 |",
        "| 置信门应用 | 0 |",
        "",
        "## 独立重算",
        "",
        (
            "| 划分 | 样本 | 规则正/负 | 原始/投影转移 | 精确正动作 | "
            "负类精确 R0 | 约束失败 | actor-derived 分母 |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in _SPLIT_ORDER:
        row = split_metrics[split]
        lines.append(
            f"| {split} | {row['sample_count']} | "
            f"{row['rule_positive_count']}/{row['rule_negative_count']} | "
            f"{row['actor_raw_transfer_count']}/"
            f"{row['actor_projected_transfer_count']} | "
            f"{row['projected_exact_positive_action_count']} | "
            f"{row['negative_exact_r0_count']} | "
            f"{row['invariant_failure_count']} | "
            f"{row['actor_derived_positive_denominator_count']} |"
        )
    lines.extend(
        [
            "",
            (
                f"聚合负类精确保持 R0 为 "
                f"{aggregate['negative_exact_r0_count']}/"
                f"{aggregate['rule_negative_count']}，比率 "
                f"{aggregate['negative_exact_r0_rate']:.6f}。"
                "错误方向、错误数量、错误边、虚假转移和投影拒绝均为 0。"
            ),
            (
                f"约束失败共 {aggregate['invariant_failure_count']} 帧。"
                "这些帧出现节点动作差异，但缺少对应转移，不能作为可执行正动作。"
            ),
            "",
            "## 来源独立性",
            "",
            "| 数据 | 帧 | 唯一可观测键 |",
            "| --- | ---: | ---: |",
            (
                f"| 冻结 v4 train+validation | "
                f"{observable['frozen_v4_train_validation_frame_count']} | "
                f"{observable['frozen_v4_train_validation_unique_key_count']} |"
            ),
            (
                f"| v6 外部数据 | {observable['external_frame_count']} | "
                f"{observable['external_unique_key_count']} |"
            ),
            (
                f"| 精确重合 | - | "
                f"{observable['exact_observable_key_overlap_count']} |"
            ),
            "",
            (
                "可观测键只包含图架构、节点特征、边特征和边索引的形状、类型和值。"
                "seed、episode、目标标签和真值不进入键。"
            ),
            "",
            "## 完整性",
            "",
            f"- source tree：`{anchors['source_tree']}`",
            f"- labeled export tree：`{anchors['labeled_export_tree']}`",
            f"- candidate tree：`{anchors['candidate_tree']}`",
            f"- D4 evaluation tree：`{anchors['d4_evaluation_tree']}`",
            (
                f"- D4 artifact manifest 文件："
                f"`{anchors['d4_artifact_manifest_file']}`"
            ),
            (
                f"- D4 artifact manifest 内容："
                f"`{anchors['d4_artifact_manifest_content']}`"
            ),
            "",
            (
                "审计前后分别计算 source、标签导出、标签数据、冻结 v4、v6 候选和 "
                "D4 评价树摘要。全部一致，"
                f"`input_mutation_count={immutability['input_mutation_count']}`。"
            ),
            "",
            "## 下一门",
            "",
            (
                "当前 v6 不进入置信校准。D4 需要另立候选版本，先在全新训练数据上形成"
                "可复现的安全转移动作，再冻结 actor。冻结后使用全新未见开发数据复核"
                "精确正动作召回；只有正类分母和命中数均充分，才可建立训练划分专用"
                "置信校准器。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _load_d4_api(repository_root: Path) -> dict[str, Any]:
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    try:
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
            DeterministicResourceProjector,
            RuleRegionResourcePolicy,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
            RegionLearningAvailability,
            RegionLearningSplit,
            load_region_learning_dataset_splits,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
            LearnedRegionResourcePolicy,
            REGION_GRAPH_ARCHITECTURE,
            snapshot_to_region_graph,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
            REGION_RESOURCE_V4_INTERVENTION_GATE,
            _V4_PROJECTION,
            _V4_RULE_CONFIG,
            evaluate_v4_intervention_invariants,
            executable_signature,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v6_transfer_candidate import (
            _load_v6_model_bundle,
        )
    except (ImportError, OSError) as exc:
        _fail("d4_read_only_dependency_unavailable", f"{type(exc).__name__}:{exc}")
    return {
        "DeterministicResourceProjector": DeterministicResourceProjector,
        "RuleRegionResourcePolicy": RuleRegionResourcePolicy,
        "RegionLearningAvailability": RegionLearningAvailability,
        "RegionLearningSplit": RegionLearningSplit,
        "load_region_learning_dataset_splits": (
            load_region_learning_dataset_splits
        ),
        "LearnedRegionResourcePolicy": LearnedRegionResourcePolicy,
        "REGION_GRAPH_ARCHITECTURE": REGION_GRAPH_ARCHITECTURE,
        "snapshot_to_region_graph": snapshot_to_region_graph,
        "REGION_RESOURCE_V4_INTERVENTION_GATE": (
            REGION_RESOURCE_V4_INTERVENTION_GATE
        ),
        "_V4_PROJECTION": _V4_PROJECTION,
        "_V4_RULE_CONFIG": _V4_RULE_CONFIG,
        "evaluate_v4_intervention_invariants": (
            evaluate_v4_intervention_invariants
        ),
        "executable_signature": executable_signature,
        "_load_v6_model_bundle": _load_v6_model_bundle,
    }


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
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_sha256(value: Any, name: str) -> str:
    digest = str(value).lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        _fail("sha256_invalid", f"{name}:{value}")
    return digest


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("json_input_invalid", f"{name}:{type(exc).__name__}:{exc}")
    return dict(_mapping(value, name))


def _read_jsonl(path: Path, name: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            rows.append(dict(_mapping(value, f"{name}:{line_number}")))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("jsonl_input_invalid", f"{name}:{type(exc).__name__}:{exc}")
    if not rows:
        _fail("jsonl_input_empty", name)
    return tuple(rows)


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


def _write_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.write_text(
        "".join(
            json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
            for row in rows
        ),
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
    raise D4V6ExternalAuditError(code, detail)
