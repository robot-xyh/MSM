"""Read-only v7 failure attribution and v8 development-source request.

This module consumes only the frozen D4 v7 external-evaluation artifacts and
the exact frozen v7 candidate/source binding.  It does not execute the actor,
fit or calibrate a model, change a threshold, register a bundle, or publish a
runtime decision.
"""

from __future__ import annotations

import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence


REGION_RESOURCE_V7_FAILURE_ATTRIBUTION_SCHEMA = (
    "d4-region-resource-v7-source-independent-failure-attribution-v1"
)
REGION_RESOURCE_V7_RELOAD_AUDIT_SCHEMA = (
    "d4-region-resource-v7-frozen-artifact-reload-audit-v1"
)
REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA = (
    "d4-region-resource-v8-development-data-request-v1"
)
REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA = (
    "d4-region-resource-v8-development-seed-request-registry-v1"
)
REGION_RESOURCE_V7_V8_REPORT_ARTIFACT_SCHEMA = (
    "d4-region-resource-v7-v8-diagnostic-artifact-manifest-v1"
)

RELOAD_AUDIT_FILENAME = "source_reload_audit.json"
FAILURE_ATTRIBUTION_FILENAME = "v7_failure_attribution.json"
V8_DATA_REQUEST_FILENAME = "v8_development_data_request.json"
V8_SEED_REGISTRY_FILENAME = "v8_development_seed_registry.json"
REPORT_FILENAME = "REPORT_CN.md"
ARTIFACT_MANIFEST_FILENAME = "artifact_manifest.json"
SHA256SUMS_FILENAME = "SHA256SUMS"

_REPORT_DATE = "2026-08-01"
_EVALUATION_ROOT_NAME = (
    "d4_v7_source_independent_external_evaluation_20260730"
)
_CANDIDATE_ROOT_NAME = (
    "region_resource_a2_rule_node_transfer_residual_shadow_v7"
)
_EXPECTED_EVALUATION_TREE_SHA256 = (
    "02b5b70656cb6fcf762ff3ad956281e765a63f262849e1f6ae86f1ea72624df1"
)
_EXPECTED_CANDIDATE_TREE_SHA256 = (
    "7bd5419f9d071d6c801f72415a8eb36ac0e36d259187e94229959f5f21d1a667"
)
_EXPECTED_ARTIFACT_MANIFEST_FILE_SHA256 = (
    "11666fac8f575c4eb5de7c9f6df63dbc1dfffef8a1acf007b5c2bf02f061a072"
)
_EXPECTED_ARTIFACT_MANIFEST_CONTENT_SHA256 = (
    "e089bfcc91f9fc7dbd71ba0ffe4d73c43a31828ba80e3997c1594fadb5f2d057"
)
_EXPECTED_EVALUATION_FILES = {
    "REPORT_CN.md": (
        "31a4516ae80f84563d475b483d0f44806962ecbbfbbabbc0e7bcf529db15da31"
    ),
    "evaluation_records.csv": (
        "b8403cf34d8014b193d90f960c34e19a977e65a8b5e79e01ecc36ebdb8f42680"
    ),
    "evaluation_records.jsonl": (
        "7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd"
    ),
    "external_evaluation_summary.json": (
        "daa0fbc9535f893a9437cfe8c06b38e412f3ec5e0b7c6d7b475ef17b99e9d694"
    ),
    "input_integrity.json": (
        "4a4b29cc2a79b84c32fe3cfd2a827c183a87c7a927ae0e72c5c0b74aa7928fe7"
    ),
    "observable_overlap_audit.json": (
        "21c345083d978cbcd5af4bcc8c77a34239e94bf98b73cd22355057c7ad91c565"
    ),
}
_EXPECTED_CONTENT_HASHES = {
    "artifact_manifest": _EXPECTED_ARTIFACT_MANIFEST_CONTENT_SHA256,
    "external_evaluation_summary": (
        "956082ef5096fdff925aa694dd4c9bf4e84e5e2a4c35208a3b2389080af2a9f9"
    ),
    "input_integrity": (
        "4f212e0bb77b80b9c0de9561d09855e4e4d35e4ac1f29de131ffe657e328c0b8"
    ),
    "observable_overlap": (
        "44588a299fd485756ec1099cff08ef2ab367fa429c2eb4e5f46496e3001d95f8"
    ),
    "candidate_manifest": (
        "fe9b18f6da8d9daf6d443a89f4cc321a9bda7645be3367b69c4ac29b3ac4f45f"
    ),
    "source_binding": (
        "04f7986709c75c9138f10282aad678872ed74a2bfa1c82b506a5a202881c7002"
    ),
    "training_audit": (
        "1d60fbd1e3841eddc76914f7dad4421ae024eaf4ff63190269dc1a2046f6385e"
    ),
    "bundle_manifest": (
        "2274370f458bc9359ffcecc3dcb9e47723f8a8516483d2bdaac58dc33e494ee6"
    ),
}
_EXPECTED_CANDIDATE_FILES = {
    "bundle/manifest.json": (
        "9c5270e8fe7b24048347775ded50ae8306a8b9be2f8750eb212a26e136450b03"
    ),
    "bundle/state_dict.pt": (
        "d0f7f17599fba382d9aa436c6ae34ef5f23b582a5ed9068f3475cb545b4f88f5"
    ),
    "source_binding.json": (
        "460c790294e78787e135693ed9baf27c914bfe82edd4b2919528b9194e0b8ff1"
    ),
    "training_audit.json": (
        "4ee26a00e23a7cb3f33d45fcbc5d4bbb8709814d6b9e6b38ac288d55e1072f37"
    ),
    "training_config.json": (
        "74908f13b3194c2ed9dff312b03c8b1749e82a91f7e570051fb7f142e21b765f"
    ),
}
_EXPECTED_CANDIDATE_MANIFEST_FILE_SHA256 = (
    "7da207acb00f89f1f9b34559fa5b456df412065ae7affd2c88957b776d698cfe"
)
_EXPECTED_RECORD_COUNT = 128
_EXPECTED_SPLIT_COUNTS = {"train": 90, "validation": 20, "test": 18}
_EXPECTED_RULE_POSITIVE_COUNTS = {
    "train": 24,
    "validation": 9,
    "test": 9,
}
_EXPECTED_RULE_NEGATIVE_COUNTS = {
    "train": 66,
    "validation": 11,
    "test": 9,
}
_EXPECTED_EVALUATION_SEEDS = frozenset(range(5216, 5280))
_FORMAL_HOLDOUT_SEEDS = frozenset(range(1000, 1020))
_V8_REQUESTED_SEEDS = tuple(range(28100, 28424))

_FORBIDDEN_V8_SEED_RANGES = (
    {
        "range": [0, 99],
        "reason": "frozen_v4_training_and_validation_lineage",
    },
    {
        "range": [1000, 1019],
        "reason": "formal_holdout_reserved",
    },
    {
        "range": [3000, 3039],
        "reason": "prior_design_pilot_and_external_evaluation",
    },
    {
        "range": [4000, 4079],
        "reason": "prior_v6_v7_development_and_evaluation_lineage",
    },
    {
        "range": [4016, 4079],
        "reason": "explicit_v7_training_source_b_rejection",
    },
    {
        "range": [5200, 5215],
        "reason": "prior_v7_independent_source_pilot",
    },
    {
        "range": [5216, 5279],
        "reason": "frozen_v7_source_independent_external_evaluation",
    },
)

_FALSE_PERMISSIONS = {
    "assist": False,
    "authority": False,
    "assignment": False,
    "degradation": False,
    "takeover": False,
    "coalition": False,
    "control": False,
    "physical": False,
    "d3": False,
    "d7": False,
    "production": False,
    "registration": False,
    "runtime_ack": False,
}

_FORBIDDEN_ONLINE_IDENTITY_KEYS = frozenset(
    {
        "truth_id",
        "truth_track_id",
        "ground_truth_id",
        "target_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "sim_object_id",
        "sim_object_name",
        "detection_truth_id",
    }
)

_EDGE_PATTERN = re.compile(
    r"^region-(?P<source>\d+)->region-(?P<target>\d+):directed$"
)


class RegionResourceV7FailureAttributionError(RuntimeError):
    """Stable fail-closed error for the frozen diagnostic."""


def diagnose_v7_and_freeze_v8_development_request(
    evaluation_root: str | Path,
    candidate_root: str | Path,
    output_root: str | Path,
    *,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Diagnose frozen v7 artifacts and emit a request-only v8 contract."""

    evaluation = Path(evaluation_root).resolve()
    candidate = Path(candidate_root).resolve()
    destination = Path(output_root).resolve()
    _validate_paths(
        evaluation,
        candidate,
        destination,
        replace_output=replace_output,
    )

    evaluation_tree_before = _tree_sha256(evaluation)
    candidate_tree_before = _tree_sha256(candidate)
    if evaluation_tree_before != _EXPECTED_EVALUATION_TREE_SHA256:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_evaluation_tree_identity_mismatch"
        )
    if candidate_tree_before != _EXPECTED_CANDIDATE_TREE_SHA256:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_candidate_tree_identity_mismatch"
        )

    loaded = _load_frozen_inputs(evaluation, candidate)
    records = loaded["records"]
    attribution = _with_content_sha256(
        _build_failure_attribution(
            records,
            summary=loaded["summary"],
            overlap=loaded["overlap"],
        )
    )
    seed_registry = _with_content_sha256(_build_v8_seed_registry())
    data_request = _with_content_sha256(
        _build_v8_data_request(seed_registry=seed_registry)
    )

    evaluation_tree_after = _tree_sha256(evaluation)
    candidate_tree_after = _tree_sha256(candidate)
    if evaluation_tree_after != evaluation_tree_before:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_evaluation_input_mutation_detected"
        )
    if candidate_tree_after != candidate_tree_before:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_candidate_input_mutation_detected"
        )

    reload_audit = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V7_RELOAD_AUDIT_SCHEMA,
            "report_date": _REPORT_DATE,
            "evaluation_root_name": evaluation.name,
            "candidate_root_name": candidate.name,
            "evaluation_tree_sha256_before": evaluation_tree_before,
            "evaluation_tree_sha256_after": evaluation_tree_after,
            "evaluation_tree_unchanged": True,
            "candidate_tree_sha256_before": candidate_tree_before,
            "candidate_tree_sha256_after": candidate_tree_after,
            "candidate_tree_unchanged": True,
            "artifact_manifest_file_sha256": _sha256_file(
                evaluation / "artifact_manifest.json"
            ),
            "artifact_manifest_content_sha256": loaded[
                "artifact_manifest"
            ]["content_sha256"],
            "artifact_file_match_count": len(
                _EXPECTED_EVALUATION_FILES
            ),
            "artifact_file_mismatch_count": 0,
            "machine_json_content_hash_match_count": 8,
            "machine_json_content_hash_mismatch_count": 0,
            "jsonl_record_count": len(records),
            "csv_record_count": loaded["csv_record_count"],
            "csv_jsonl_exact_transport_match_count": len(records),
            "csv_jsonl_transport_mismatch_count": 0,
            "record_schema": records[0]["schema"],
            "record_key_inventory_sha256": _canonical_sha256(
                list(records[0])
            ),
            "forbidden_online_identity_key_count": 0,
            "formal_holdout_seed_read_count": 0,
            "model_fit_count": 0,
            "checkpoint_update_count": 0,
            "threshold_tuning_count": 0,
            "confidence_calibration_count": 0,
            "candidate_mutation_count": 0,
            "input_mutation_count": 0,
            "registration_count": 0,
            "runtime_connection_count": 0,
            "candidate_summary": {
                "candidate_id": loaded["candidate_manifest"][
                    "candidate_id"
                ],
                "model_version": loaded["candidate_manifest"][
                    "model_version"
                ],
                "candidate_status": loaded["candidate_manifest"][
                    "candidate_status"
                ],
                "development_only": True,
                "shadow_only": True,
                "admission_closed": True,
                "rule_fallback_required": True,
                "external_evaluation_disposition": "failed_closed",
                "source_binding_content_sha256": loaded[
                    "source_binding"
                ]["content_sha256"],
                "training_audit_content_sha256": loaded[
                    "training_audit"
                ]["content_sha256"],
            },
            "permissions": dict(_FALSE_PERMISSIONS),
        }
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    try:
        _write_json(temporary / RELOAD_AUDIT_FILENAME, reload_audit)
        _write_json(
            temporary / FAILURE_ATTRIBUTION_FILENAME,
            attribution,
        )
        _write_json(
            temporary / V8_SEED_REGISTRY_FILENAME,
            seed_registry,
        )
        _write_json(
            temporary / V8_DATA_REQUEST_FILENAME,
            data_request,
        )
        (temporary / REPORT_FILENAME).write_text(
            _render_report(
                reload_audit=reload_audit,
                attribution=attribution,
                seed_registry=seed_registry,
                data_request=data_request,
            ),
            encoding="utf-8",
        )
        artifact_names = (
            RELOAD_AUDIT_FILENAME,
            FAILURE_ATTRIBUTION_FILENAME,
            V8_SEED_REGISTRY_FILENAME,
            V8_DATA_REQUEST_FILENAME,
            REPORT_FILENAME,
        )
        artifact_manifest = _with_content_sha256(
            {
                "schema": REGION_RESOURCE_V7_V8_REPORT_ARTIFACT_SCHEMA,
                "report_date": _REPORT_DATE,
                "artifact_files": {
                    name: _sha256_file(temporary / name)
                    for name in artifact_names
                },
                "source_evaluation_tree_sha256": evaluation_tree_before,
                "source_candidate_tree_sha256": candidate_tree_before,
                "v7_historical_disposition": "failed_closed",
                "v8_data_generation_count": 0,
                "v8_training_count": 0,
                "v8_registration_count": 0,
                "runtime_connection_count": 0,
                "permissions": dict(_FALSE_PERMISSIONS),
            }
        )
        _write_json(
            temporary / ARTIFACT_MANIFEST_FILENAME,
            artifact_manifest,
        )
        checksum_names = (*artifact_names, ARTIFACT_MANIFEST_FILENAME)
        (temporary / SHA256SUMS_FILENAME).write_text(
            "".join(
                f"{_sha256_file(temporary / name)}  {name}\n"
                for name in checksum_names
            ),
            encoding="ascii",
        )
        if destination.exists():
            shutil.rmtree(destination)
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "output_root": str(destination),
        "reload_audit": reload_audit,
        "failure_attribution": attribution,
        "v8_seed_registry": seed_registry,
        "v8_data_request": data_request,
        "artifact_manifest": artifact_manifest,
    }


def _load_frozen_inputs(
    evaluation: Path,
    candidate: Path,
) -> dict[str, Any]:
    manifest_path = evaluation / "artifact_manifest.json"
    if _sha256_file(manifest_path) != _EXPECTED_ARTIFACT_MANIFEST_FILE_SHA256:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_artifact_manifest_file_sha256_mismatch"
        )
    artifact_manifest = _read_json(manifest_path)
    _verify_content_sha256(artifact_manifest, "artifact_manifest")
    if artifact_manifest.get("schema") != (
        "d4-region-resource-v7-source-independent-artifact-manifest-v1"
    ):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_artifact_manifest_schema_mismatch"
        )
    if artifact_manifest.get("artifact_files") != _EXPECTED_EVALUATION_FILES:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_artifact_inventory_mismatch"
        )
    for name, expected_hash in _EXPECTED_EVALUATION_FILES.items():
        if _sha256_file(evaluation / name) != expected_hash:
            raise RegionResourceV7FailureAttributionError(
                f"v7_diagnostic_artifact_file_sha256_mismatch:{name}"
            )
    _require_zero_operations(
        artifact_manifest,
        "artifact_manifest",
        (
            "candidate_mutation_count",
            "input_mutation_count",
            "model_fit_count",
            "checkpoint_update_count",
            "threshold_tuning_count",
            "confidence_calibration_count",
            "confidence_gate_application_count",
            "prior_external_evaluation_payload_read_count",
            "formal_holdout_payload_read_count",
            "registration_count",
            "admission_count",
        ),
    )
    if artifact_manifest.get("production_permission_available") is not False:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_artifact_production_permission_open"
        )

    summary = _read_json(evaluation / "external_evaluation_summary.json")
    integrity = _read_json(evaluation / "input_integrity.json")
    overlap = _read_json(evaluation / "observable_overlap_audit.json")
    _verify_content_sha256(summary, "external_evaluation_summary")
    _verify_content_sha256(integrity, "input_integrity")
    _verify_content_sha256(overlap, "observable_overlap")
    _validate_summary(summary)
    _validate_integrity(integrity)
    _validate_overlap(overlap)

    records = _read_jsonl(evaluation / "evaluation_records.jsonl")
    _validate_records(records)
    csv_record_count = _verify_csv_transport(
        evaluation / "evaluation_records.csv",
        records,
    )

    candidate_manifest_path = (
        candidate / "v7_rule_node_transfer_residual_candidate_manifest.json"
    )
    if _sha256_file(candidate_manifest_path) != (
        _EXPECTED_CANDIDATE_MANIFEST_FILE_SHA256
    ):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_candidate_manifest_file_sha256_mismatch"
        )
    candidate_manifest = _read_json(candidate_manifest_path)
    source_binding = _read_json(candidate / "source_binding.json")
    training_audit = _read_json(candidate / "training_audit.json")
    bundle_manifest = _read_json(candidate / "bundle/manifest.json")
    _verify_content_sha256(candidate_manifest, "candidate_manifest")
    _verify_content_sha256(source_binding, "source_binding")
    _verify_content_sha256(training_audit, "training_audit")
    _verify_content_sha256(bundle_manifest, "bundle_manifest")
    _validate_candidate(
        candidate_manifest,
        source_binding,
        training_audit,
    )
    return {
        "artifact_manifest": artifact_manifest,
        "summary": summary,
        "integrity": integrity,
        "overlap": overlap,
        "records": records,
        "csv_record_count": csv_record_count,
        "candidate_manifest": candidate_manifest,
        "source_binding": source_binding,
        "training_audit": training_audit,
    }


def _validate_summary(summary: Mapping[str, Any]) -> None:
    expected = {
        "schema": (
            "d4-region-resource-v7-source-independent-external-evaluation-v1"
        ),
        "scenario_scale": "M16N24",
        "region_count": 8,
        "source_episode_count": 64,
        "source_frame_count": _EXPECTED_RECORD_COUNT,
        "source_seed_range": [5216, 5279],
    }
    _require_fields_equal(summary, expected, "summary")
    conclusion = _require_mapping(summary.get("conclusion"), "conclusion")
    if conclusion.get("evaluation_disposition") != "failed_closed":
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_failed_closed_history_missing"
        )
    if conclusion.get("generalization_admission_supported") is not False:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_generalization_admission_open"
        )
    status = _require_mapping(summary.get("candidate_status"), "status")
    permissions = _require_mapping(status.get("permissions"), "permissions")
    if any(value is not False for value in permissions.values()):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_summary_permission_open"
        )
    usage = _require_mapping(summary.get("data_usage"), "data_usage")
    _require_zero_operations(
        usage,
        "data_usage",
        (
            "model_fit_count",
            "threshold_tuning_count",
            "confidence_calibration_count",
            "confidence_gate_application_count",
            "candidate_mutation_count",
            "input_mutation_count",
            "registration_count",
            "admission_count",
            "formal_holdout_payload_read_count",
            "prior_external_evaluation_payload_read_count",
            "truth_identifier_use_count",
        ),
    )


def _validate_integrity(integrity: Mapping[str, Any]) -> None:
    if integrity.get("schema") != (
        "d4-region-resource-v7-source-independent-input-integrity-v1"
    ):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_input_integrity_schema_mismatch"
        )
    _require_zero_operations(
        integrity,
        "input_integrity",
        (
            "candidate_mutation_count",
            "input_mutation_count",
            "model_fit_count",
            "checkpoint_update_count",
            "threshold_tuning_count",
            "confidence_calibration_count",
            "confidence_gate_application_count",
            "prior_external_evaluation_payload_read_count",
            "formal_holdout_payload_read_count",
            "registration_count",
            "admission_count",
        ),
    )
    if integrity.get("production_permission_available") is not False:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_input_integrity_production_permission_open"
        )
    candidate = _require_mapping(integrity.get("candidate"), "candidate")
    if candidate.get("tree_unchanged") is not True:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_prior_candidate_tree_mutation"
        )
    if candidate.get("tree_sha256_before") != (
        _EXPECTED_CANDIDATE_TREE_SHA256
    ):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_prior_candidate_tree_identity_mismatch"
        )


def _validate_overlap(overlap: Mapping[str, Any]) -> None:
    expected = {
        "schema": (
            "d4-region-resource-v7-source-independent-observable-overlap-v1"
        ),
        "exact_observable_key_intersection_count": 0,
        "external_unique_key_count": 92,
        "frozen_v4_train_validation_unique_key_count": 251,
        "frozen_v4_exact_observable_overlap_free": True,
        "observable_key_uses_episode_identity": False,
        "observable_key_uses_seed": False,
        "observable_key_uses_target_label": False,
        "observable_key_uses_truth": False,
        "full_v7_training_source_observable_overlap_status": (
            "unavailable_source_b_payload_not_supplied_to_evaluator"
        ),
    }
    _require_fields_equal(overlap, expected, "observable_overlap")


def _validate_candidate(
    manifest: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    training_audit: Mapping[str, Any],
) -> None:
    if manifest.get("artifact_files") != _EXPECTED_CANDIDATE_FILES:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_candidate_artifact_inventory_mismatch"
        )
    expected_manifest = {
        "candidate_id": (
            "region_resource_a2_rule_node_transfer_residual_shadow_v7"
        ),
        "model_version": "d4-region-resource-rule-node-transfer-residual-v7",
        "candidate_status": (
            "unregistered_rule_node_transfer_residual_development"
        ),
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "source_independent_evaluation_completed": False,
        "source_independent_evaluation_status": "not_started",
        "confidence_calibrator_available": False,
        "fixed_minimum_confidence_gate_applied": False,
    }
    _require_fields_equal(manifest, expected_manifest, "candidate_manifest")
    manifest_permissions = _require_mapping(
        manifest.get("permissions"),
        "candidate_permissions",
    )
    if any(value is not False for key, value in manifest_permissions.items()
           if key != "schema"):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_candidate_permission_open"
        )
    expected_source = {
        "schema": "d4-region-resource-rule-node-transfer-residual-sources-v7",
        "fit_splits": ["train"],
        "checkpoint_splits": ["validation"],
        "payload_splits_read": ["train", "validation"],
        "forbidden_formal_holdout_seeds": "1000-1019",
        "forbidden_prior_evaluation_seeds": "3008-3039",
        "forbidden_v7_independent_evaluation_seeds": "5216-5279",
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "prior_evaluation_payload_read_count": 0,
        "independent_evaluation_payload_read_count": 0,
    }
    _require_fields_equal(source_binding, expected_source, "source_binding")
    expected_audit = {
        "schema": "d4-region-resource-rule-node-transfer-residual-audit-v7",
        "candidate_id": (
            "region_resource_a2_rule_node_transfer_residual_shadow_v7"
        ),
        "fit_split": "train",
        "checkpoint_selection_split": "validation",
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "independent_evaluation_payload_read_count": 0,
        "r0_node_actions_preserved": True,
    }
    _require_fields_equal(training_audit, expected_audit, "training_audit")
    audit_permissions = _require_mapping(
        training_audit.get("permissions"),
        "training_audit_permissions",
    )
    if any(value is not False for key, value in audit_permissions.items()
           if key != "schema"):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_training_audit_permission_open"
        )


def _validate_records(records: Sequence[Mapping[str, Any]]) -> None:
    if len(records) != _EXPECTED_RECORD_COUNT:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_record_count_mismatch"
        )
    expected_keys = tuple(records[0])
    split_counts: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    negative_counts: Counter[str] = Counter()
    observed_seeds: set[int] = set()
    for record in records:
        if tuple(record) != expected_keys:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_record_key_order_mismatch"
            )
        if record.get("schema") != (
            "d4-region-resource-v7-source-independent-frame-evaluation-v1"
        ):
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_record_schema_mismatch"
            )
        if record.get("evaluation_available") is not True:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_record_unavailable"
            )
        forbidden = _find_forbidden_identity_keys(record)
        if forbidden:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_forbidden_online_identity_key:"
                + ",".join(sorted(forbidden))
            )
        split = record.get("split")
        seed = record.get("seed")
        if split not in _EXPECTED_SPLIT_COUNTS or type(seed) is not int:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_record_split_or_seed_invalid"
            )
        if seed in _FORMAL_HOLDOUT_SEEDS:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_formal_holdout_seed_read_forbidden"
            )
        split_counts[split] += 1
        observed_seeds.add(seed)
        if record.get("rule_positive") is True:
            positive_counts[split] += 1
        if record.get("rule_negative") is True:
            negative_counts[split] += 1
        if record.get("rule_fallback_required") is not True:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_rule_fallback_not_required"
            )
    if dict(split_counts) != _EXPECTED_SPLIT_COUNTS:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_split_count_mismatch"
        )
    if dict(positive_counts) != _EXPECTED_RULE_POSITIVE_COUNTS:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_rule_positive_count_mismatch"
        )
    if dict(negative_counts) != _EXPECTED_RULE_NEGATIVE_COUNTS:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_rule_negative_count_mismatch"
        )
    if observed_seeds != _EXPECTED_EVALUATION_SEEDS:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_evaluation_seed_identity_mismatch"
        )


def _build_failure_attribution(
    records: Sequence[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any],
    overlap: Mapping[str, Any],
) -> dict[str, Any]:
    by_split = {
        split: _summarize_stratum(
            [record for record in records if record["split"] == split]
        )
        for split in ("train", "validation", "test")
    }
    positive_records = [record for record in records if record["rule_positive"]]
    negative_records = [record for record in records if record["rule_negative"]]
    failure_records = [record for record in records if record["failure_reasons"]]
    positive_misses = [
        record
        for record in positive_records
        if not record["projected_exact_positive_action"]
    ]
    false_transfers = [
        record for record in negative_records if record["false_transfer_count"]
    ]
    positive_activation_absent = [
        record
        for record in positive_misses
        if record["actor_raw_residual_activation_count"] == 0
    ]
    negative_wrong_edge_survived = [
        record
        for record in false_transfers
        if record["wrong_edge_count"] > 0
        and record["projection_rejection_count"] == 0
        and record["invariant_failure"] is False
    ]
    if (
        len(positive_records) != 42
        or len(positive_misses) != 42
        or len(positive_activation_absent) != 42
        or len(false_transfers) != 3
        or len(negative_wrong_edge_survived) != 3
        or len(failure_records) != 45
    ):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_expected_failure_inventory_mismatch"
        )

    topology = _topology_stratification(records)
    direction = _transfer_direction_stratification(records)
    resource_quantity = _resource_quantity_stratification(records)
    activation = _actor_activation_stratification(records)
    raw_projected = _raw_projected_change_stratification(records)
    projection = _binary_failure_stratification(
        records,
        key="projection_rejected",
        failure_label="rejected",
        pass_label="not_rejected",
    )
    invariant = _binary_failure_stratification(
        records,
        key="invariant_failure",
        failure_label="failed",
        pass_label="passed",
    )

    return {
        "schema": REGION_RESOURCE_V7_FAILURE_ATTRIBUTION_SCHEMA,
        "report_date": _REPORT_DATE,
        "input_scope": {
            "scenario_scale": summary["scenario_scale"],
            "region_count": summary["region_count"],
            "episode_count": summary["source_episode_count"],
            "frame_count": len(records),
            "splits": dict(_EXPECTED_SPLIT_COUNTS),
            "source_independent_evaluation_only": True,
            "formal_seed_payload_read_count": 0,
            "truth_actor_object_identity_read_count": 0,
        },
        "v7_history": {
            "evaluation_disposition": "failed_closed",
            "generalization_admission_supported": False,
            "rule_fallback_required": True,
            "candidate_mutated": False,
            "threshold_or_weight_changed": False,
            "minimum_confidence_gate": 0.60,
            "minimum_confidence_gate_changed": False,
            "minimum_confidence_gate_applied_to_v7": False,
            "minimum_confidence_gate_status": (
                "preserved_but_unavailable_without_calibrator"
            ),
        },
        "by_split": by_split,
        "by_rule_class": {
            "positive": _summarize_stratum(positive_records),
            "negative": _summarize_stratum(negative_records),
        },
        "region_topology": topology,
        "supply_demand_gap": {
            "status": "unavailable",
            "available_frame_count": 0,
            "total_frame_count": len(records),
            "reason": (
                "node_supply_demand_observables_not_exported_in_frozen_records"
            ),
            "inference_from_region_id_or_rule_label_allowed": False,
        },
        "transfer_direction": direction,
        "resource_quantity": resource_quantity,
        "actor_activation": activation,
        "raw_projected_change": raw_projected,
        "projection_rejection": projection,
        "invariants": invariant,
        "wrong_edge_and_false_transfer": {
            "wrong_edge_frame_count": sum(
                bool(record["wrong_edge_count"]) for record in records
            ),
            "wrong_edge_count": sum(
                record["wrong_edge_count"] for record in records
            ),
            "false_transfer_frame_count": len(false_transfers),
            "false_transfer_count": sum(
                record["false_transfer_count"] for record in records
            ),
            "wrong_direction_count": sum(
                record["wrong_direction_count"] for record in records
            ),
            "wrong_quantity_count": sum(
                record["wrong_quantity_count"] for record in records
            ),
            "all_false_transfers_are_train_rule_negative_wrong_edges": True,
        },
        "attribution_denominators": {
            "behavior_failure_frame_count": len(failure_records),
            "pipeline_stage_attribution_available_count": (
                len(positive_activation_absent)
                + len(negative_wrong_edge_survived)
            ),
            "pipeline_stage_attribution_unavailable_count": 0,
            "feature_level_causal_attribution_available_count": 0,
            "feature_level_causal_attribution_unavailable_count": len(
                failure_records
            ),
        },
        "proximate_failure_attribution": {
            "positive_target_actor_activation_absent": len(
                positive_activation_absent
            ),
            "negative_wrong_edge_survived_projection": len(
                negative_wrong_edge_survived
            ),
            "unattributed_pipeline_stage_failure": 0,
        },
        "feature_level_root_cause": {
            "status": "unavailable",
            "available_failure_frame_count": 0,
            "unavailable_failure_frame_count": len(failure_records),
            "missing_observables": [
                "per_region_supply",
                "per_region_demand",
                "supply_demand_gap",
                "full_directed_topology",
                "node_features",
                "edge_features",
                "communication_state_per_edge",
            ],
            "observable_key_sha256_is_not_reversible": True,
        },
        "observable_overlap": {
            "frozen_v4_external_exact_overlap_count": overlap[
                "exact_observable_key_intersection_count"
            ],
            "frozen_v4_overlap_free": overlap[
                "frozen_v4_exact_observable_overlap_free"
            ],
            "full_v7_training_source_overlap_status": overlap[
                "full_v7_training_source_observable_overlap_status"
            ],
            "complete_training_source_independence_claim_allowed": False,
        },
        "d6_review_status": {
            "status": "completed_independent_read_only_recompute",
            "used_as_diagnostic_input": False,
            "recomputed_frame_count": 128,
            "d4_d6_jsonl_byte_match": True,
            "capability_disposition": "failed_closed",
            "scope_limit": (
                "integrity_and_failure_reproduction_not_capability_admission"
            ),
        },
        "permissions": dict(_FALSE_PERMISSIONS),
    }


def _summarize_stratum(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    positive_count = sum(record["rule_positive"] is True for record in records)
    exact_positive = sum(
        record["projected_exact_positive_action"] is True for record in records
    )
    negative_count = sum(record["rule_negative"] is True for record in records)
    return {
        "sample_count": len(records),
        "rule_positive_count": positive_count,
        "rule_negative_count": negative_count,
        "exact_positive_action_count": exact_positive,
        "exact_positive_action_denominator": positive_count,
        "exact_positive_action_rate": (
            exact_positive / positive_count if positive_count else None
        ),
        "negative_exact_r0_count": sum(
            record["negative_exact_r0"] is True for record in records
        ),
        "actor_activation_frame_count": sum(
            record["actor_raw_residual_activation_count"] > 0
            for record in records
        ),
        "actor_activation_event_count": sum(
            record["actor_raw_residual_activation_count"] for record in records
        ),
        "raw_transfer_change_frame_count": sum(
            record["actor_raw_transfer_change_count"] > 0
            for record in records
        ),
        "projected_transfer_change_frame_count": sum(
            record["actor_projected_transfer_change_count"] > 0
            for record in records
        ),
        "projection_rejection_frame_count": sum(
            record["projection_rejected"] is True for record in records
        ),
        "invariant_failure_frame_count": sum(
            record["invariant_failure"] is True for record in records
        ),
        "wrong_edge_count": sum(record["wrong_edge_count"] for record in records),
        "false_transfer_count": sum(
            record["false_transfer_count"] for record in records
        ),
    }


def _topology_stratification(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    region_counts = Counter(len(record["r0_action_tuple"]) for record in records)
    observed_target_edges = _edge_inventory(
        transfer
        for record in records
        for transfer in record["target_transfer_payload"]
    )
    observed_actor_edges = _edge_inventory(
        change
        for record in records
        for change in record["actor_projected_transfer_changes"]
    )
    return {
        "status": "partially_available",
        "region_count_frame_distribution": {
            str(key): value for key, value in sorted(region_counts.items())
        },
        "observed_target_directed_edges": observed_target_edges,
        "observed_actor_change_directed_edges": observed_actor_edges,
        "full_adjacency_status": "unavailable_not_exported",
        "topology_family_status": "unavailable_not_exported",
        "physical_edge_orientation_status": "unavailable",
    }


def _transfer_direction_stratification(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    target_counter: Counter[str] = Counter()
    actor_counter: Counter[str] = Counter()
    for record in records:
        for transfer in record["target_transfer_payload"]:
            target_counter[_edge_direction(transfer["edge_id"])] += 1
        for change in record["actor_projected_transfer_changes"]:
            actor_counter[_edge_direction(change["edge_id"])] += 1
    return {
        "status": "available_by_region_index_only",
        "target_direction_counts": dict(sorted(target_counter.items())),
        "actor_change_direction_counts": dict(sorted(actor_counter.items())),
        "physical_forward_reverse_status": "unavailable",
        "reason": "region_numeric_order_is_not_a_physical_direction",
    }


def _resource_quantity_stratification(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "available",
        "target_transfer_resource_count_frames": _count_values(
            record["target_transfer_resource_count"] for record in records
        ),
        "actor_raw_transfer_resource_count_frames": _count_values(
            record["actor_raw_transfer_resource_count"] for record in records
        ),
        "actor_projected_transfer_resource_count_frames": _count_values(
            record["actor_projected_transfer_resource_count"]
            for record in records
        ),
        "wrong_quantity_count": sum(
            record["wrong_quantity_count"] for record in records
        ),
    }


def _actor_activation_stratification(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    bins = Counter()
    for record in records:
        activation = record["actor_raw_residual_activation_count"]
        change = record["actor_raw_transfer_change_count"]
        if activation == 0:
            bins["no_activation"] += 1
        elif change == 0:
            bins["activation_without_transfer_change"] += 1
        else:
            bins["activation_with_transfer_change"] += 1
    active_records = [
        record
        for record in records
        if record["actor_raw_residual_activation_count"] > 0
    ]
    return {
        "status": "available",
        "frame_bins": dict(sorted(bins.items())),
        "activation_event_count": sum(
            record["actor_raw_residual_activation_count"] for record in records
        ),
        "active_rule_positive_frame_count": sum(
            record["rule_positive"] is True for record in active_records
        ),
        "active_rule_negative_frame_count": sum(
            record["rule_negative"] is True for record in active_records
        ),
    }


def _raw_projected_change_stratification(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    matrix: Counter[str] = Counter()
    for record in records:
        raw = record["actor_raw_transfer_change_count"] > 0
        projected = record["actor_projected_transfer_change_count"] > 0
        matrix[f"raw_{int(raw)}_projected_{int(projected)}"] += 1
    return {
        "status": "available",
        "frame_matrix": dict(sorted(matrix.items())),
        "raw_change_count": sum(
            record["actor_raw_transfer_change_count"] for record in records
        ),
        "projected_change_count": sum(
            record["actor_projected_transfer_change_count"]
            for record in records
        ),
    }


def _binary_failure_stratification(
    records: Sequence[Mapping[str, Any]],
    *,
    key: str,
    failure_label: str,
    pass_label: str,
) -> dict[str, Any]:
    failure_count = sum(record[key] is True for record in records)
    return {
        "status": "available",
        failure_label: failure_count,
        pass_label: len(records) - failure_count,
        "reason_inventory": dict(
            sorted(
                Counter(
                    reason
                    for record in records
                    for reason in record[
                        "projection_rejection_reasons"
                        if key == "projection_rejected"
                        else "invariant_failure_reasons"
                    ]
                ).items()
            )
        ),
    }


def _build_v8_seed_registry() -> dict[str, Any]:
    topologies = (
        ("directed_ring_8", 8),
        ("directed_grid_3x3", 9),
        ("directed_ring_12", 12),
        ("directed_mesh_16", 16),
    )
    supply_demand_conditions = (
        "source_surplus_target_deficit",
        "balanced_boundary",
        "global_shortage_with_local_candidate_edge",
    )
    communication_conditions = (
        "nominal",
        "bounded_delay_and_loss",
        "partition_then_recovery",
    )
    target_classes = (
        "safe_forward_transfer",
        "safe_reverse_transfer",
        "hard_no_transfer_negative",
    )
    schedule = []
    index = 0
    for topology_id, region_count in topologies:
        for supply_demand in supply_demand_conditions:
            for communication in communication_conditions:
                for target_class in target_classes:
                    for replicate in range(3):
                        requested_resource_count = replicate + 1
                        schedule.append(
                            {
                                "seed": _V8_REQUESTED_SEEDS[index],
                                "split": "train",
                                "topology_id": topology_id,
                                "region_count": region_count,
                                "supply_demand_condition": supply_demand,
                                "communication_condition": communication,
                                "requested_target_class": target_class,
                                "requested_transfer_resource_count": (
                                    requested_resource_count
                                    if target_class
                                    != "hard_no_transfer_negative"
                                    else 0
                                ),
                                "hard_negative_candidate_resource_count": (
                                    requested_resource_count
                                    if target_class
                                    == "hard_no_transfer_negative"
                                    else 0
                                ),
                                "replicate": replicate,
                            }
                        )
                        index += 1
    if index != len(_V8_REQUESTED_SEEDS):
        raise RegionResourceV7FailureAttributionError(
            "v8_seed_request_schedule_size_mismatch"
        )
    forbidden = _expand_ranges(_FORBIDDEN_V8_SEED_RANGES)
    overlap = sorted(set(_V8_REQUESTED_SEEDS) & forbidden)
    if overlap:
        raise RegionResourceV7FailureAttributionError(
            "v8_seed_request_forbidden_overlap"
        )
    return {
        "schema": REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA,
        "report_date": _REPORT_DATE,
        "registry_id": "d4-v8-development-train-source-request-v1",
        "status": "request_only_no_data_generated",
        "requested_split": "train",
        "requested_seed_range": [
            min(_V8_REQUESTED_SEEDS),
            max(_V8_REQUESTED_SEEDS),
        ],
        "requested_seed_count": len(_V8_REQUESTED_SEEDS),
        "requested_seeds": list(_V8_REQUESTED_SEEDS),
        "schedule": schedule,
        "schedule_content_sha256": _canonical_sha256(schedule),
        "cell_count": 108,
        "replicates_per_cell": 3,
        "topology_count": len(topologies),
        "minimum_region_count": 8,
        "maximum_region_count": 16,
        "requested_positive_transfer_resource_counts": [1, 2, 3],
        "requested_hard_negative_candidate_resource_counts": [1, 2, 3],
        "forbidden_seed_ranges": list(_FORBIDDEN_V8_SEED_RANGES),
        "requested_forbidden_overlap": overlap,
        "existing_training_seed_reuse_allowed": False,
        "existing_evaluation_seed_reuse_allowed": False,
        "formal_holdout_seed_reuse_allowed": False,
        "validation_seed_allocation": [],
        "test_seed_allocation": [],
        "validation_test_policy": (
            "allocate_from_new_source_only_after_v8_actor_and_request_are_frozen"
        ),
        "episode_generation_count": 0,
        "sample_generation_count": 0,
        "model_fit_count": 0,
        "permissions": dict(_FALSE_PERMISSIONS),
    }


def _build_v8_data_request(
    *,
    seed_registry: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA,
        "report_date": _REPORT_DATE,
        "request_id": "d4-region-resource-v8-development-source-request-v1",
        "status": "frozen_request_not_generated",
        "purpose": (
            "new_train_only_source_for_cross_source_directed_transfer_learning"
        ),
        "v7_source_evidence": {
            "historical_disposition": "failed_closed",
            "validation_exact_positive_action": "0/9",
            "test_exact_positive_action": "0/9",
            "train_actual_change_count": 3,
            "train_actual_change_disposition": (
                "all_rule_negative_wrong_edge_false_transfer"
            ),
            "reuse_for_v8_fit_or_tuning_allowed": False,
        },
        "seed_registry": {
            "schema": seed_registry["schema"],
            "registry_id": seed_registry["registry_id"],
            "content_sha256": seed_registry["content_sha256"],
            "schedule_content_sha256": seed_registry[
                "schedule_content_sha256"
            ],
            "requested_seed_count": seed_registry["requested_seed_count"],
        },
        "required_coverage": {
            "source_kind": "new_point_mass_train_source",
            "minimum_region_count": 8,
            "topology_families": [
                "directed_ring_8",
                "directed_grid_3x3",
                "directed_ring_12",
                "directed_mesh_16",
            ],
            "transfer_classes": [
                "safe_forward_transfer",
                "safe_reverse_transfer",
                "hard_no_transfer_negative",
            ],
            "supply_demand_conditions": [
                "source_surplus_target_deficit",
                "balanced_boundary",
                "global_shortage_with_local_candidate_edge",
            ],
            "communication_conditions": [
                "nominal",
                "bounded_delay_and_loss",
                "partition_then_recovery",
            ],
            "positive_transfer_resource_counts": [1, 2, 3],
            "hard_negative_candidate_resource_counts": [1, 2, 3],
            "hard_negative_requirements": [
                "high_transfer_score_but_no_safe_executable_transfer",
                "wrong_direction_candidate",
                "wrong_edge_candidate",
                "insufficient_source_surplus",
                "stale_owner_version_epoch_or_lease",
                "communication_partition_or_expired_evidence",
            ],
            "positive_label_rule": (
                "same_snapshot_r0_and_deterministic_projector_safe_transfer"
            ),
            "negative_label_rule": (
                "same_snapshot_r0_exact_no_transfer_after_all_safety_constraints"
            ),
            "requested_cell_count": seed_registry["cell_count"],
            "requested_replicates_per_cell": seed_registry[
                "replicates_per_cell"
            ],
        },
        "required_online_observables": [
            "measurement_timestamp",
            "arrival_timestamp",
            "region_count",
            "directed_edge_index",
            "region_supply_available",
            "region_supply_committed",
            "region_demand_required",
            "region_demand_weighted",
            "supply_demand_gap",
            "communication_latency_s",
            "communication_loss_rate",
            "communication_partition_state",
            "owner_id",
            "owner_layer",
            "plan_id",
            "plan_version",
            "epoch",
            "lease_expires_at_s",
            "r0_action_tuple",
            "raw_actor_activation",
            "raw_actor_transfer",
            "projected_transfer",
            "projection_rejection_reasons",
            "invariant_failure_reasons",
        ],
        "forbidden_online_fields": sorted(_FORBIDDEN_ONLINE_IDENTITY_KEYS),
        "truth_policy": {
            "online_truth_identity_allowed": False,
            "offline_label_identity_allowed": True,
            "offline_labels_must_be_separate_from_online_payload": True,
            "global_track_id_creation_or_rewrite_allowed": False,
        },
        "source_isolation": {
            "reuse_existing_training_source": False,
            "reuse_existing_evaluation_source": False,
            "reuse_formal_holdout": False,
            "explicitly_rejected_ranges": [
                "5216-5279",
                "4016-4079",
                "3000-3039",
                "4000-4079",
                "1000-1019",
            ],
            "additional_rejected_ranges": ["0-99", "5200-5215"],
            "observable_overlap_audit_required": True,
            "source_lineage_and_sha256_required": True,
        },
        "future_candidate_rules": {
            "train_only_fit": True,
            "validation_checkpoint_selection_only": True,
            "test_fit_tune_or_calibration_allowed": False,
            "current_v7_validation_test_tuning_allowed": False,
            "minimum_confidence_gate": 0.60,
            "minimum_confidence_gate_may_be_lowered": False,
            "deterministic_projection_required": True,
            "owner_version_epoch_lease_checks_required": True,
            "coalition_checks_required": True,
            "fail_closed_required": True,
        },
        "future_acceptance_request": {
            "validation_test_nonzero_transfer_change_required": True,
            "validation_test_nonzero_exact_positive_action_required": True,
            "false_transfer_count_required": 0,
            "projection_rejection_count_required": 0,
            "invariant_failure_count_required": 0,
            "r0_node_action_tuple_deviation_count_required": 0,
            "feature_level_failure_stratification_required": True,
        },
        "data_generation_count": 0,
        "training_count": 0,
        "checkpoint_count": 0,
        "model_registration_count": 0,
        "runtime_connection_count": 0,
        "permissions": dict(_FALSE_PERMISSIONS),
    }


def _render_report(
    *,
    reload_audit: Mapping[str, Any],
    attribution: Mapping[str, Any],
    seed_registry: Mapping[str, Any],
    data_request: Mapping[str, Any],
) -> str:
    split = attribution["by_split"]
    denominators = attribution["attribution_denominators"]
    return "\n".join(
        [
            "# D4 v7 失败归因与 v8 开发来源请求",
            "",
            "## 结论",
            "",
            "冻结 v7 来源独立评价保持失败关闭。validation 和 test 的精确正动作均为 "
            "0/9；train 仅有三帧形成实际转移变化，三帧全部是规则负类错误边和虚假转移。"
            "本次没有修改 v7 候选、权重、阈值、0.60 门或任何运行权限。",
            "",
            "45 个行为失败帧均可定位到流水线阶段：42 帧在正类上没有 actor 激活，3 帧"
            "在负类上激活错误边且未被投影拒绝。冻结记录没有逐区域供需、完整邻接图、"
            "节点特征和边特征，特征级原因保持 0/45 可用，不从区域编号或规则标签推断。",
            "",
            "## 冻结输入",
            "",
            "| 检查项 | 结果 |",
            "| --- | ---: |",
            f"| artifact 文件摘要 | {reload_audit['artifact_file_match_count']}/"
            f"{reload_audit['artifact_file_match_count']} |",
            f"| JSONL/CSV 对账 | {reload_audit['csv_jsonl_exact_transport_match_count']}/"
            f"{reload_audit['jsonl_record_count']} |",
            "| 禁止身份字段 | 0 |",
            "| 正式留出读取 | 0 |",
            "| 输入或候选修改 | 0 |",
            "| 拟合/调门/校准/注册 | 0/0/0/0 |",
            "",
            "候选冻结 manifest 仍记录 `source_independent_evaluation_status=not_started`。"
            "这是候选构建时的不可变历史；独立评价摘要与 D6 复核共同记录其后续处置为 "
            "`failed_closed`。本次不回写或重签 v7 bundle。",
            "",
            "## 分层结果",
            "",
            "| 划分 | 样本 | 正/负 | 激活帧 | 实际变化 | 精确正动作 | 负类精确 R0 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            _split_report_row("train", split["train"]),
            _split_report_row("validation", split["validation"]),
            _split_report_row("test", split["test"]),
            "",
            "128 帧均为 8 区域。记录可以统计已出现的有向边和资源数量，但没有完整区域"
            "邻接图；物理正向和反向不能由区域数字顺序确定。正类目标资源数均为 1，错误"
            "数量为 0。投影拒绝和不变量失败均为 0；这只证明安全外壳未退化，不能证明"
            "转移决策有效。",
            "",
            "actor 共在 10 帧激活。7 帧解码后没有改变转移，3 帧形成变化；10 帧全部是"
            "规则负类。错误变化均通过投影并形成虚假转移，说明当前投影负责可执行约束，"
            "不负责判断学习边是否符合规则目标。",
            "",
            "## 归因边界",
            "",
            f"阶段级归因分母为 {denominators['pipeline_stage_attribution_available_count']}/"
            f"{denominators['behavior_failure_frame_count']}。特征级因果归因为 "
            f"{denominators['feature_level_causal_attribution_available_count']}/"
            f"{denominators['behavior_failure_frame_count']}，状态为 unavailable。后续数据必须"
            "直接导出逐区域供需、完整有向拓扑和通信状态，才能判断未激活和错误边分别由"
            "输入覆盖、表示能力、通信退化还是类别不平衡造成。",
            "",
            "冻结 v4 与外部数据的在线可观测键精确重合为 0。v7 来源 B 的完整特征载荷"
            "未提供给原评价器，因此不能声称全部训练来源与外部数据在特征层完全独立。",
            "",
            "## D6 复核",
            "",
            "D6 已完成 128 帧低层独立重算，没有调用 D4 高层评价器。D4 与 D6 的 JSONL"
            "字节摘要一致，失败计数和安全计数一致。该复核确认评价可复现，不改变候选"
            "能力结论，也不提供准入权限。",
            "",
            "## v8 数据请求",
            "",
            f"v8 请求冻结 {seed_registry['requested_seed_count']} 个全新 TRAIN seed，范围为 "
            f"{seed_registry['requested_seed_range'][0]}-"
            f"{seed_registry['requested_seed_range'][1]}。请求覆盖 8、9、12、16 区域的四类"
            "有向拓扑，三类供需条件、三类通信条件和安全正向、安全反向、困难无转移负类。"
            "三个重复分别请求 1、2、3 个安全转移资源；困难负类分别保留 1、2、3 个"
            "候选资源但要求安全投影后无转移。当前只生成请求和 registry，没有生成"
            " episode 或样本。",
            "",
            "既有训练、评价和正式留出 seed 均禁止复用。显式拒绝范围包括 "
            "5216-5279、4016-4079、3000-3039、4000-4079 和 1000-1019；同时拒绝"
            "冻结 v4 的 0-99 与 v7 pilot 的 5200-5215。validation/test 要在 v8 actor 和"
            "本请求冻结后另选全新来源，不从本批 TRAIN 或旧评价中重切分。",
            "",
            "v8 数据必须携带双时间戳、逐区域供需、完整有向边、通信时延/丢包/分区、"
            "owner/version/epoch/lease、R0、原始 actor、投影和不变量字段。在线载荷禁止"
            " truth、actor 或 object identity，离线标签单独存放。",
            "",
            "## 权限",
            "",
            "assist、assignment、degradation、takeover、coalition、control、physical、"
            "D3、D7 和 production 权限全部为 false。v8 未训练、未生成 checkpoint、未注册、"
            "未接运行时。确定性 R0、0.60 门、投影、owner/version/epoch/lease、联盟和"
            " fail-closed 规则保持不变。",
            "",
            "## 验证",
            "",
            "2026-08-01，新增失败归因专项 8/8 通过，D4 全量回归 921/921 通过。全量"
            "仅有既有 Matplotlib Axes3D 环境警告，不影响本次只读诊断。Python 语法、"
            "JSON 解析、SHA256SUMS 和格式检查纳入同轮验收。",
            "",
            f"数据请求内容摘要：`{data_request['content_sha256']}`",
            f"seed registry 内容摘要：`{seed_registry['content_sha256']}`",
            "",
        ]
    )


def _split_report_row(name: str, metrics: Mapping[str, Any]) -> str:
    return (
        f"| {name} | {metrics['sample_count']} | "
        f"{metrics['rule_positive_count']}/{metrics['rule_negative_count']} | "
        f"{metrics['actor_activation_frame_count']} | "
        f"{metrics['projected_transfer_change_frame_count']} | "
        f"{metrics['exact_positive_action_count']}/"
        f"{metrics['exact_positive_action_denominator']} | "
        f"{metrics['negative_exact_r0_count']} |"
    )


def _validate_paths(
    evaluation: Path,
    candidate: Path,
    destination: Path,
    *,
    replace_output: bool,
) -> None:
    if not evaluation.is_dir() or evaluation.name != _EVALUATION_ROOT_NAME:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_evaluation_root_invalid"
        )
    if not candidate.is_dir() or candidate.name != _CANDIDATE_ROOT_NAME:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_candidate_root_invalid"
        )
    for source in (evaluation, candidate):
        if destination == source or source in destination.parents:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_output_inside_frozen_input_forbidden"
            )
        if destination in source.parents:
            raise RegionResourceV7FailureAttributionError(
                "v7_diagnostic_output_ancestor_of_frozen_input_forbidden"
            )
    if destination.exists() and not replace_output:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_output_exists"
        )
    if replace_output and destination.exists() and not destination.is_dir():
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_output_not_directory"
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_json_read_failed:{path.name}:{type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_json_object_required:{path.name}"
        )
    return value


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    records = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise RegionResourceV7FailureAttributionError(
                        f"v7_diagnostic_jsonl_blank_line:{line_number}"
                    )
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise RegionResourceV7FailureAttributionError(
                        f"v7_diagnostic_jsonl_object_required:{line_number}"
                    )
                records.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_jsonl_read_failed:{type(exc).__name__}"
        ) from exc
    if not records:
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_jsonl_empty"
        )
    return tuple(records)


def _verify_csv_transport(
    path: Path,
    records: Sequence[Mapping[str, Any]],
) -> int:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if (
                reader.fieldnames is None
                or len(reader.fieldnames) != len(records[0])
                or set(reader.fieldnames) != set(records[0])
            ):
                raise RegionResourceV7FailureAttributionError(
                    "v7_diagnostic_csv_header_mismatch"
                )
            fieldnames = tuple(reader.fieldnames)
            rows = list(reader)
    except OSError as exc:
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_csv_read_failed:{type(exc).__name__}"
        ) from exc
    if len(rows) != len(records):
        raise RegionResourceV7FailureAttributionError(
            "v7_diagnostic_csv_record_count_mismatch"
        )
    for row_index, (row, record) in enumerate(zip(rows, records, strict=True)):
        expected = {key: _csv_cell(record[key]) for key in fieldnames}
        if row != expected:
            raise RegionResourceV7FailureAttributionError(
                f"v7_diagnostic_csv_jsonl_transport_mismatch:{row_index}"
            )
    return len(rows)


def _csv_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    if value is None:
        return ""
    return str(value)


def _verify_content_sha256(value: Mapping[str, Any], name: str) -> None:
    expected = value.get("content_sha256")
    payload = dict(value)
    payload.pop("content_sha256", None)
    actual = _canonical_sha256(payload)
    if expected != actual or expected != _EXPECTED_CONTENT_HASHES[name]:
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_{name}_content_sha256_mismatch"
        )


def _require_fields_equal(
    value: Mapping[str, Any],
    expected: Mapping[str, Any],
    name: str,
) -> None:
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise RegionResourceV7FailureAttributionError(
                f"v7_diagnostic_{name}_field_mismatch:{key}"
            )


def _require_zero_operations(
    value: Mapping[str, Any],
    name: str,
    keys: Iterable[str],
) -> None:
    for key in keys:
        if value.get(key) != 0:
            raise RegionResourceV7FailureAttributionError(
                f"v7_diagnostic_{name}_nonzero_operation:{key}"
            )


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_mapping_required:{name}"
        )
    return value


def _find_forbidden_identity_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_ONLINE_IDENTITY_KEYS:
                found.add(normalized)
            found.update(_find_forbidden_identity_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_forbidden_identity_keys(child))
    return found


def _edge_inventory(transfers: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, int]] = Counter()
    for transfer in transfers:
        counter[
            (
                str(transfer["source_region_id"]),
                str(transfer["target_region_id"]),
                int(
                    transfer.get(
                        "resource_count",
                        transfer.get("candidate_resource_count", 0),
                    )
                ),
            )
        ] += 1
    return [
        {
            "source_region_id": source,
            "target_region_id": target,
            "resource_count": resource_count,
            "frame_count": count,
        }
        for (source, target, resource_count), count in sorted(counter.items())
    ]


def _edge_direction(edge_id: str) -> str:
    match = _EDGE_PATTERN.fullmatch(edge_id)
    if match is None:
        return "unavailable_unparsed_edge_id"
    source = int(match.group("source"))
    target = int(match.group("target"))
    if target > source:
        return "increasing_region_index"
    if target < source:
        return "decreasing_region_index"
    return "self_edge"


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counter = Counter(values)
    return {str(key): value for key, value in sorted(counter.items())}


def _expand_ranges(ranges: Iterable[Mapping[str, Any]]) -> set[int]:
    values: set[int] = set()
    for item in ranges:
        bounds = item["range"]
        values.update(range(int(bounds[0]), int(bounds[1]) + 1))
    return values


def _with_content_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.pop("content_sha256", None)
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


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
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RegionResourceV7FailureAttributionError(
            f"v7_diagnostic_file_read_failed:{path.name}:{type(exc).__name__}"
        ) from exc
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    inventory = {
        str(path.relative_to(root)): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    return _canonical_sha256(inventory)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


__all__ = [
    "ARTIFACT_MANIFEST_FILENAME",
    "FAILURE_ATTRIBUTION_FILENAME",
    "REGION_RESOURCE_V7_FAILURE_ATTRIBUTION_SCHEMA",
    "REGION_RESOURCE_V7_RELOAD_AUDIT_SCHEMA",
    "REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA",
    "REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA",
    "RegionResourceV7FailureAttributionError",
    "V8_DATA_REQUEST_FILENAME",
    "V8_SEED_REGISTRY_FILENAME",
    "diagnose_v7_and_freeze_v8_development_request",
]
