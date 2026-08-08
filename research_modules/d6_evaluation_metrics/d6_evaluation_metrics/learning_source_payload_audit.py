"""Authorized, read-only full-payload audit for D3/D4/D5 source data.

The auditor is deliberately independent of producer loaders.  It accepts only
an exact SHA-bound input contract, successful metadata preflight, and an exact
audit-only authorization.  Dataset files are opened only when listed by the
bound producer inventory; directory discovery is never used to admit data.

This module does not train, infer, select checkpoints or thresholds, execute
assignment/degradation/camera/control paths, or create/write global track IDs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import numpy as np

from .learning_source_generation_preflight import (
    EXPECTED_EPISODE_COUNTS,
    LearningSourceGenerationPreflightInputs,
    evaluate_learning_source_generation_preflight,
    load_learning_source_generation_preflight_inputs,
)


LEARNING_SOURCE_PAYLOAD_AUDIT_SCHEMA_VERSION = (
    "d6.learning-source-payload-audit.v1"
)
SOURCE_AUDIT_AUTHORIZATION_SCHEMA_VERSION = (
    "scalable3d-d6-source-audit-authorization-v1"
)
SOURCE_AUDIT_CONFIRMATION = "AUTHORIZE D6 SOURCE AUDIT OF D3 D4 D5 ONLY"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_D3_STAGED = re.compile(
    r"^dataset/\.a1_v3_staging/episodes/episode-(\d{3})\.json$"
)
_D4_ONLINE = re.compile(r"^dataset/online/(\d{3})_(\d+)\.jsonl$")
_D4_LABEL = re.compile(r"^dataset/labels/(\d{3})_(\d+)\.jsonl$")
_D5_DESCRIPTOR = re.compile(
    r"^(development|future_held_out)/episodes/(.+)\.episode\.json$"
)
_D5_ONLINE = re.compile(
    r"^(development|future_held_out)/online/(.+)\.online\.json$"
)
_D5_OFFLINE = re.compile(
    r"^(development|future_held_out)/offline/(.+)\.offline\.json$"
)

_AUTHORIZATION_FIELDS = {
    "schema_version",
    "authorization_id",
    "approved_at_utc",
    "approver_id",
    "approval_reason",
    "confirmation",
    "status",
    "preflight_input_contract_sha256",
    "preflight_report_file_sha256",
    "preflight_result_sha256",
    "sources",
    "permissions",
}
_AUTHORIZATION_PERMISSION_VALUES = {
    "assignment": False,
    "assist": False,
    "camera_command": False,
    "checkpoint_selection": False,
    "coalition": False,
    "control": False,
    "degradation": False,
    "future_held_out_model_consumption": False,
    "global_track_id_create": False,
    "global_track_id_write": False,
    "model_inference": False,
    "optimizer": False,
    "physical": False,
    "production": False,
    "runtime": False,
    "shadow": False,
    "source_integrity_audit": True,
    "source_metadata_read": True,
    "source_payload_integrity_read": True,
    "test_model_consumption": False,
    "threshold_adjustment": False,
    "training": False,
    "validation_model_consumption": False,
}
_AUTHORIZATION_SOURCE_FIELDS = {
    "module",
    "source_root",
    "source_git_commit",
    "generation_authorization_sha256",
    "module_request_sha256",
    "manifest_schema_field",
    "manifest_schema_version",
    "artifact_inventory_tree_sha256",
}
_RESULT_PERMISSION_VALUES = dict(_AUTHORIZATION_PERMISSION_VALUES)
_RESULT_PERMISSION_VALUES.update(
    {
        "validation_consumption": False,
        "test_consumption": False,
        "future_held_out_consumption": False,
        "promotion": False,
        "ppo": False,
    }
)

_D3_PERMISSIONS = {
    "generation",
    "training",
    "optimizer",
    "checkpoint_selection",
    "normalization_refit",
    "threshold_adjustment",
    "runtime",
    "assist",
    "authority",
    "assignment",
    "plan",
    "control",
    "physical",
    "formal_admission",
    "production_admission",
}
_D4_PERMISSIONS = {
    "schema",
    "assignment",
    "assist",
    "authority",
    "coalition",
    "control",
    "d3",
    "d7",
    "degradation",
    "physical",
    "production",
    "registration",
    "runtime_ack",
    "takeover",
}
_D5_AUTHORITY = {
    "assignment",
    "assist",
    "camera_command",
    "control",
    "degradation",
    "global_track_id_create",
    "global_track_id_write",
    "ppo",
    "production",
    "promotion",
    "runtime",
    "shadow",
}

_D3_ONLINE_SCHEMA = "d3_a1_source_independent_v3_online_frame_v1"
_D3_OFFLINE_SCHEMA = "d3_a1_source_independent_v3_offline_label_v1"
_D3_MANIFEST_SCHEMA = "d3_a1_source_independent_v3_dataset_manifest_v1"
_D4_MANIFEST_SCHEMA = "d4-region-resource-v8-train-dataset-manifest-v1"
_D4_ONLINE_SCHEMA = "d4-region-resource-v8-online-frame-v1"
_D4_LABEL_SCHEMA = "d4-region-resource-v8-offline-transfer-label-v1"
_D5_SOURCE_SCHEMA = "d5.active-vision-a3-minority-source-manifest.v1"
_D5_PARTITION_SCHEMA = "d5.active-vision-a3-v3-frozen-partition-manifest.v2"
_D5_DESCRIPTOR_SCHEMA = "d5.active-vision-a3-v3-episode-descriptor.v2"
_D5_ONLINE_SCHEMA = "d5.active-vision-a3-v3-online-episode-evidence.v1"
_D5_SAMPLE_SCHEMA = "d5.active-vision-a3-v3-online-sample-evidence.v1"
_D5_OFFLINE_SCHEMA = "d5.active-vision-a3-v3-offline-episode-audit.v1"
_D5_OFFLINE_SAMPLE_SCHEMA = "d5.active-vision-a3-v3-offline-sample-audit.v1"


class LearningSourcePayloadAuditError(ValueError):
    """Stable fail-closed error for unsafe or inconsistent audit evidence."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class LearningSourcePayloadAuditInputs:
    """Out-of-band bindings required before any source payload is opened."""

    input_contract_path: Path
    input_contract_sha256: str
    preflight_path: Path
    preflight_sha256: str
    authorization_path: Path
    authorization_sha256: str


@dataclass(frozen=True, slots=True)
class _InventoryItem:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(slots=True)
class _SourceContext:
    module: str
    root: Path
    binding: Any
    preflight: Mapping[str, Any]
    authorization: Mapping[str, Any]
    result_path: Path
    result_size_bytes: int
    inventory: tuple[_InventoryItem, ...]
    inventory_by_path: dict[str, _InventoryItem]
    parsed_json: dict[str, Mapping[str, Any]]
    jsonl_records: dict[str, list[Mapping[str, Any]]]
    document_record_count: int = 0
    covariance_matrix_count: int = 0


def audit_learning_source_payloads(
    inputs: LearningSourcePayloadAuditInputs,
) -> dict[str, Any]:
    """Run the authorized audit and return a non-admission result."""

    base = _base_result(inputs)
    try:
        contexts, binding_evidence = _load_and_bind(inputs)
    except (LearningSourcePayloadAuditError, OSError) as exc:
        code, detail = _error_parts(exc)
        base["blocker_codes"] = [code]
        base["blocker_details"] = {code: [detail] if detail else []}
        return base

    base["bindings"] = binding_evidence
    blockers: dict[str, list[str]] = defaultdict(list)
    module_results: dict[str, Any] = {}
    for context in contexts:
        try:
            _verify_inventory_files(context)
            _parse_inventory_documents(context)
            if context.module == "D3":
                module_results[context.module] = _audit_d3(context)
            elif context.module == "D4":
                module_results[context.module] = _audit_d4(context)
            else:
                module_results[context.module] = _audit_d5(context)
        except (LearningSourcePayloadAuditError, OSError) as exc:
            code, detail = _error_parts(exc)
            blockers[code].append(
                f"{context.module}:{detail}" if detail else context.module
            )
            module_results[context.module] = {
                "module": context.module,
                "status": "failed_closed",
                "source_root": context.root.as_posix(),
                "blocker_code": code,
                "permissions": dict(_RESULT_PERMISSION_VALUES),
                "training_permission_granted": False,
            }

    base["sources"] = module_results
    if blockers:
        base["blocker_codes"] = sorted(blockers)
        base["blocker_details"] = {
            code: sorted(details) for code, details in sorted(blockers.items())
        }
        return base

    base.update(
        {
            "status": "source_integrity_audit_passed_not_training_authorized",
            "audit_passed": True,
            "full_payload_audit_performed": True,
            "source_payload_integrity_read": True,
            "blocker_codes": [],
            "blocker_details": {},
            "warning_codes": sorted(
                {
                    warning
                    for result in module_results.values()
                    for warning in result.get("warning_codes", [])
                }
            ),
        }
    )
    return base


def write_learning_source_payload_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, str]:
    """Write deterministic JSON, Chinese Markdown and SHA256SUMS."""

    output = Path(output_dir).expanduser().absolute()
    _reject_symlink_components(output, "output_dir")
    for item in result.get("sources", {}).values():
        if isinstance(item, Mapping) and item.get("source_root"):
            root = Path(str(item["source_root"])).absolute()
            if _is_relative_to(output, root):
                _fail("output_inside_source_root", str(output))
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        _fail("output_dir_not_empty", str(output))
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "source_audit.json"
    markdown_path = output / "SOURCE_AUDIT_REPORT_CN.md"
    json_path.write_bytes(_canonical_json_line(dict(result)))
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    hashes = {
        json_path.name: _hash_file(json_path),
        markdown_path.name: _hash_file(markdown_path),
    }
    checksum_path = output / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
        encoding="ascii",
    )
    hashes[checksum_path.name] = _hash_file(checksum_path)
    return hashes


def _base_result(inputs: LearningSourcePayloadAuditInputs) -> dict[str, Any]:
    return {
        "schema_version": LEARNING_SOURCE_PAYLOAD_AUDIT_SCHEMA_VERSION,
        "status": "failed_closed",
        "audit_passed": False,
        "full_payload_audit_performed": False,
        "source_payload_integrity_read": False,
        "input_contract_sha256_expected": str(inputs.input_contract_sha256),
        "preflight_sha256_expected": str(inputs.preflight_sha256),
        "authorization_sha256_expected": str(inputs.authorization_sha256),
        "bindings": {},
        "sources": {},
        "blocker_codes": [],
        "blocker_details": {},
        "warning_codes": [],
        "permissions": dict(_RESULT_PERMISSION_VALUES),
        "non_audit_permissions_all_false": True,
        "d6_control_participation": False,
        "training_permission_granted": False,
        "model_consumption_performed": False,
        "future_held_out_model_consumption_performed": False,
        "audit_result_is_training_authorization": False,
    }


def _load_and_bind(
    inputs: LearningSourcePayloadAuditInputs,
) -> tuple[tuple[_SourceContext, ...], dict[str, Any]]:
    contract_sha = _sha(inputs.input_contract_sha256, "input_contract_sha256")
    preflight_sha = _sha(inputs.preflight_sha256, "preflight_sha256")
    authorization_sha = _sha(inputs.authorization_sha256, "authorization_sha256")
    contract = load_learning_source_generation_preflight_inputs(
        inputs.input_contract_path,
        expected_sha256=contract_sha,
    )
    preflight = _load_bound_json_file(
        inputs.preflight_path, preflight_sha, "preflight"
    )
    authorization = _load_bound_json_file(
        inputs.authorization_path, authorization_sha, "authorization"
    )
    _validate_preflight(preflight, contract, preflight_sha)
    _validate_authorization(
        authorization,
        contract=contract,
        preflight=preflight,
        contract_sha=contract_sha,
        preflight_sha=preflight_sha,
    )

    # Re-run the metadata-only gate before opening any inventory payload.
    current_preflight = evaluate_learning_source_generation_preflight(contract)
    if current_preflight.get("metadata_preflight_passed") is not True:
        _fail(
            "metadata_preflight_recheck_failed",
            ",".join(current_preflight.get("blocker_codes", [])),
        )
    if current_preflight != preflight:
        _fail("preflight_current_state_mismatch")

    auth_sources = _module_map(authorization["sources"], "authorization_sources")
    contexts: list[_SourceContext] = []
    for binding in contract.sources:
        module_preflight = _mapping(preflight["sources"].get(binding.module), "preflight_source")
        module_auth = auth_sources[binding.module]
        result_binding = binding.files["result"]
        result_path = _resolve_inventory_file(
            binding.source_root,
            result_binding.relative_path,
            "generation_result",
        )
        result_bytes = result_path.read_bytes()
        if sha256(result_bytes).hexdigest() != result_binding.sha256:
            _fail("generation_result_sha256_mismatch", binding.module)
        result_payload = _decode_json_object(result_bytes, "generation_result")
        inventory = _normalize_inventory(
            result_payload.get("artifact_inventory"), binding.artifact_inventory_sha256
        )
        if inventory[-1] != module_preflight["artifact_inventory_tree_sha256"]:
            _fail("inventory_preflight_tree_mismatch", binding.module)
        if inventory[-1] != module_auth["artifact_inventory_tree_sha256"]:
            _fail("inventory_authorization_tree_mismatch", binding.module)
        records = inventory[0]
        contexts.append(
            _SourceContext(
                module=binding.module,
                root=_resolve_source_root(binding.source_root),
                binding=binding,
                preflight=module_preflight,
                authorization=module_auth,
                result_path=result_path,
                result_size_bytes=len(result_bytes),
                inventory=records,
                inventory_by_path={item.relative_path: item for item in records},
                parsed_json={"generation_result.json": result_payload},
                jsonl_records={},
            )
        )
    return tuple(contexts), {
        "input_contract_sha256": contract_sha,
        "preflight_file_sha256": preflight_sha,
        "authorization_file_sha256": authorization_sha,
        "contract_id": contract.contract_id,
        "authorization_id": authorization["authorization_id"],
        "authorization_status": authorization["status"],
        "permission_contract_exact": True,
        "metadata_preflight_rechecked": True,
    }


def _validate_preflight(
    value: Mapping[str, Any],
    contract: LearningSourceGenerationPreflightInputs,
    digest: str,
) -> None:
    del digest
    required = {
        "schema_version": "d6.learning-source-generation-preflight.v1",
        "input_contract_sha256": contract.input_contract_sha256,
        "contract_id": contract.contract_id,
        "status": "ready_for_explicit_d6_source_audit_authorization",
        "metadata_preflight_passed": True,
        "full_payload_audit_performed": False,
        "formal_source_data_read": False,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            _fail("preflight_contract_mismatch", f"{key}:{value.get(key)!r}")
    if value.get("blocker_codes") != [] or value.get("blocker_details") != {}:
        _fail("preflight_contains_blocker")
    permissions = _mapping(value.get("permissions"), "preflight_permissions")
    if any(item is not False for item in permissions.values()):
        _fail("preflight_permission_not_false")
    if set(value.get("sources", {})) != set(EXPECTED_EPISODE_COUNTS):
        _fail("preflight_source_set_mismatch")


def _validate_authorization(
    value: Mapping[str, Any],
    *,
    contract: LearningSourceGenerationPreflightInputs,
    preflight: Mapping[str, Any],
    contract_sha: str,
    preflight_sha: str,
) -> None:
    _exact_keys(value, _AUTHORIZATION_FIELDS, "authorization_fields")
    expected = {
        "schema_version": SOURCE_AUDIT_AUTHORIZATION_SCHEMA_VERSION,
        "confirmation": SOURCE_AUDIT_CONFIRMATION,
        "status": "approved_for_source_integrity_audit_only",
        "preflight_input_contract_sha256": contract_sha,
        "preflight_report_file_sha256": preflight_sha,
        "preflight_result_sha256": preflight_sha,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            _fail("authorization_binding_mismatch", key)
    for key in ("authorization_id", "approved_at_utc", "approver_id", "approval_reason"):
        if not isinstance(value.get(key), str) or not str(value[key]).strip():
            _fail("authorization_identity_invalid", key)
    permissions = _mapping(value.get("permissions"), "authorization_permissions")
    if dict(permissions) != _AUTHORIZATION_PERMISSION_VALUES:
        _fail("authorization_permissions_not_exact_audit_only")

    auth_sources = _module_map(value["sources"], "authorization_sources")
    for binding in contract.sources:
        item = auth_sources[binding.module]
        _exact_keys(item, _AUTHORIZATION_SOURCE_FIELDS, "authorization_source_fields")
        preflight_source = _mapping(preflight["sources"][binding.module], "preflight_source")
        expected_source = {
            "module": binding.module,
            "source_root": binding.source_root.as_posix(),
            "source_git_commit": binding.source_git_commit,
            "generation_authorization_sha256": binding.generation_authorization_sha256,
            "module_request_sha256": binding.module_request_sha256,
            "manifest_schema_field": preflight_source["manifest_schema_field"],
            "manifest_schema_version": preflight_source["manifest_schema_version"],
            "artifact_inventory_tree_sha256": preflight_source[
                "artifact_inventory_tree_sha256"
            ],
        }
        if dict(item) != expected_source:
            _fail("authorization_source_binding_mismatch", binding.module)


def _normalize_inventory(
    value: Any,
    expected_content_sha256: str,
) -> tuple[tuple[_InventoryItem, ...], int, str]:
    inventory = _mapping(value, "artifact_inventory")
    _exact_keys(
        inventory,
        {"file_count", "total_size_bytes", "files", "tree_sha256"},
        "artifact_inventory_fields",
    )
    files = inventory["files"]
    if not isinstance(files, list):
        _fail("artifact_inventory_files_invalid")
    records: list[_InventoryItem] = []
    previous = ""
    total = 0
    for index, value_item in enumerate(files):
        item = _mapping(value_item, "artifact_inventory_file")
        _exact_keys(item, {"path", "size_bytes", "sha256"}, "inventory_file_fields")
        relative = _safe_relative(item["path"], f"inventory_path[{index}]")
        if relative <= previous:
            _fail("artifact_inventory_unsorted_or_duplicate", relative)
        previous = relative
        size = _nonnegative_int(item["size_bytes"], "inventory_size")
        digest = _sha(item["sha256"], "inventory_sha256")
        records.append(_InventoryItem(relative, size, digest))
        total += size
    if inventory["file_count"] != len(records):
        _fail("artifact_inventory_file_count_mismatch")
    if inventory["total_size_bytes"] != total:
        _fail("artifact_inventory_total_size_mismatch")
    normalized_files = [
        {"path": item.relative_path, "size_bytes": item.size_bytes, "sha256": item.sha256}
        for item in records
    ]
    tree = _sha(inventory["tree_sha256"], "inventory_tree_sha256")
    if tree != _canonical_line_sha256({"files": normalized_files}):
        _fail("artifact_inventory_tree_sha256_mismatch")
    normalized = {
        "file_count": len(records),
        "total_size_bytes": total,
        "files": normalized_files,
        "tree_sha256": tree,
    }
    if _canonical_line_sha256(normalized) != _sha(
        expected_content_sha256, "artifact_inventory_content_sha256"
    ):
        _fail("artifact_inventory_content_sha256_mismatch")
    return tuple(records), total, tree


def _verify_inventory_files(context: _SourceContext) -> None:
    identities: set[tuple[int, int]] = set()
    for item in context.inventory:
        path = _resolve_inventory_file(context.root, item.relative_path, "inventory_payload")
        info = path.stat(follow_symlinks=False)
        identity = (int(info.st_dev), int(info.st_ino))
        if identity in identities:
            _fail("inventory_file_identity_reused", item.relative_path)
        identities.add(identity)
        if info.st_size != item.size_bytes:
            _fail("inventory_file_size_mismatch", item.relative_path)
        if _hash_file(path) != item.sha256:
            _fail("inventory_file_sha256_mismatch", item.relative_path)


def _parse_inventory_documents(context: _SourceContext) -> None:
    for item in context.inventory:
        path = _resolve_inventory_file(context.root, item.relative_path, "inventory_payload")
        if item.relative_path.endswith(".json"):
            payload = _decode_json_object(path.read_bytes(), item.relative_path)
            _validate_finite_tree(payload, item.relative_path)
            context.document_record_count += 1
            context.covariance_matrix_count += _validate_covariances(
                payload, item.relative_path
            )
            _collect_document(context, item.relative_path, payload, None)
        elif item.relative_path.endswith(".jsonl"):
            with path.open("rb") as stream:
                for line_number, raw in enumerate(stream, start=1):
                    if not raw.endswith(b"\n") or not raw.strip():
                        _fail("jsonl_record_encoding_invalid", f"{item.relative_path}:{line_number}")
                    payload = _decode_json_object(raw[:-1], f"{item.relative_path}:{line_number}")
                    _validate_finite_tree(payload, f"{item.relative_path}:{line_number}")
                    context.covariance_matrix_count += _validate_covariances(
                        payload, f"{item.relative_path}:{line_number}"
                    )
                    context.document_record_count += 1
                    _collect_document(context, item.relative_path, payload, line_number)
        else:
            _fail("inventory_payload_extension_forbidden", item.relative_path)


def _collect_document(
    context: _SourceContext,
    relative: str,
    payload: Mapping[str, Any],
    line_number: int | None,
) -> None:
    if line_number is None and relative in {
        "dataset/dataset_manifest.json",
        "dataset/manifest.json",
        "main_schedule.json",
        "source_manifest.json",
        "development/manifest.json",
        "future_held_out/manifest.json",
        "dataset/.a1_v3_staging/session.json",
    }:
        context.parsed_json[relative] = payload
    # Large per-episode and JSONL payloads are intentionally discarded here.
    # Producer-specific semantic passes reopen one inventory-bound file at a
    # time, keeping peak memory bounded by the largest single document.


def _audit_d3(context: _SourceContext) -> dict[str, Any]:
    expected_paths = {
        "dataset/.a1_v3_staging/session.json",
        "dataset/dataset_manifest.json",
        "dataset/offline_labels.jsonl",
        "dataset/online_frames.jsonl",
        "episode_progress.jsonl",
        "generation_checkpoint.json",
        "generation_session.json",
    }
    expected_paths.update(
        f"dataset/.a1_v3_staging/episodes/episode-{index:03d}.json"
        for index in range(300)
    )
    _require_inventory_exact(context, expected_paths)
    manifest = _required_json(context, "dataset/dataset_manifest.json")
    if manifest.get("schema_version") != _D3_MANIFEST_SCHEMA:
        _fail("d3_manifest_schema_mismatch")
    counts = _mapping(manifest.get("counts"), "d3_manifest_counts")
    expected_counts = {
        "episode_count": 300,
        "frame_count": 3086,
        "unique_seed_count": 300,
        "online_truth_use_count": 0,
        "learning_created_global_track_id_count": 0,
        "learning_rewritten_global_track_id_count": 0,
        "duplicate_episode_count": 0,
        "duplicate_frame_count": 0,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            _fail("d3_manifest_count_mismatch", key)
    _false_mapping(manifest.get("permissions"), _D3_PERMISSIONS, "d3_manifest_permissions")
    split = _mapping(manifest.get("split"), "d3_split")
    seed_values = _mapping(split.get("seed_values"), "d3_split_seed_values")
    split_sets = {
        name: _integer_set(seed_values.get(name), f"d3_{name}_seeds")
        for name in ("train", "validation", "test")
    }
    _require_disjoint(split_sets, "d3_split")
    if {key: len(value) for key, value in split_sets.items()} != {
        "train": 180,
        "validation": 60,
        "test": 60,
    }:
        _fail("d3_split_count_mismatch")
    artifacts = _mapping(manifest.get("artifacts"), "d3_artifacts")
    for key, relative in (
        ("online_frames", "dataset/online_frames.jsonl"),
        ("offline_labels", "dataset/offline_labels.jsonl"),
    ):
        if artifacts.get(f"{key}_path") != PurePosixPath(relative).name:
            _fail("d3_manifest_artifact_path_mismatch", key)
        if artifacts.get(f"{key}_sha256") != context.inventory_by_path[relative].sha256:
            _fail("d3_manifest_artifact_hash_mismatch", key)

    online_by_key: dict[tuple[str, int, str, int], str] = {}
    latency: list[float] = []
    observed_scales: Counter[str] = Counter()
    online_count = 0
    for row in _iter_jsonl_again(context, "dataset/online_frames.jsonl"):
        key, digest, delay, scale = _validate_d3_online(row)
        if key in online_by_key:
            _fail("d3_online_frame_key_duplicate", repr(key))
        online_by_key[key] = digest
        latency.append(delay)
        observed_scales[scale] += 1
        online_count += 1
    offline_keys: set[tuple[str, int, str, int]] = set()
    classes: Counter[str] = Counter()
    offline_count = 0
    for row in _iter_jsonl_again(context, "dataset/offline_labels.jsonl"):
        key, online_digest, frame_class = _validate_d3_offline(row)
        if key in offline_keys:
            _fail("d3_offline_frame_key_duplicate", repr(key))
        offline_keys.add(key)
        if online_by_key.get(key) != online_digest:
            _fail("d3_online_offline_hash_binding_mismatch", repr(key))
        classes[frame_class] += 1
        offline_count += 1
    if online_count != 3086 or offline_count != 3086:
        _fail("d3_global_frame_count_mismatch")
    if set(online_by_key) != offline_keys:
        _fail("d3_online_offline_frame_inventory_mismatch")

    staged_keys: set[tuple[str, int, str, int]] = set()
    staged_episode_keys: set[tuple[str, int, str]] = set()
    staged_frame_count = 0
    for index in range(300):
        relative = f"dataset/.a1_v3_staging/episodes/episode-{index:03d}.json"
        episode = _load_json_again(context, relative)
        if episode.get("schema_version") != "d3_a1_v3_staged_episode_v1":
            _fail("d3_staged_episode_schema_mismatch", relative)
        if episode.get("schedule_index") != index:
            _fail("d3_staged_schedule_index_mismatch", relative)
        scheduled = _mapping(episode.get("scheduled_episode"), "d3_scheduled_episode")
        episode_key = (
            str(scheduled.get("split")),
            _int(scheduled.get("seed"), "d3_seed"),
            str(scheduled.get("episode_id")),
        )
        if episode_key in staged_episode_keys:
            _fail("d3_episode_key_duplicate", repr(episode_key))
        staged_episode_keys.add(episode_key)
        embedded_online = _mapping_list(episode.get("online_frames"), "d3_embedded_online")
        embedded_offline = _mapping_list(episode.get("offline_labels"), "d3_embedded_offline")
        frame_count = _int(_mapping(episode.get("counts"), "d3_counts").get("frame_count"), "d3_frame_count")
        if len(embedded_online) != frame_count or len(embedded_offline) != frame_count:
            _fail("d3_staged_frame_count_mismatch", relative)
        if _canonical_jsonl_sha256(embedded_online) != _mapping(
            episode.get("artifacts"), "d3_episode_artifacts"
        ).get("online_frames_sha256"):
            _fail("d3_staged_online_hash_mismatch", relative)
        if _canonical_jsonl_sha256(embedded_offline) != _mapping(
            episode.get("artifacts"), "d3_episode_artifacts"
        ).get("offline_labels_sha256"):
            _fail("d3_staged_offline_hash_mismatch", relative)
        for online_row, offline_row in zip(embedded_online, embedded_offline, strict=True):
            key, digest, _, _ = _validate_d3_online(online_row)
            offline_key, bound_digest, _ = _validate_d3_offline(offline_row)
            if key != offline_key or digest != bound_digest:
                _fail("d3_staged_online_offline_binding_mismatch", relative)
            if key in staged_keys:
                _fail("d3_staged_frame_key_duplicate", repr(key))
            staged_keys.add(key)
        staged_frame_count += frame_count
    if staged_keys != set(online_by_key) or staged_frame_count != 3086:
        _fail("d3_staged_global_frame_inventory_mismatch")
    if {key[1] for key in staged_episode_keys} != set().union(*split_sets.values()):
        _fail("d3_episode_split_seed_mismatch")

    warnings = [
        "d3_six_dimensional_state_not_in_a1_v3_assignment_source_contract",
        "d3_covariance_matrix_not_in_a1_v3_assignment_source_contract",
    ]
    return _module_result(
        context,
        episode_count=300,
        record_count=3086,
        truth_leakage_count=0,
        split_leakage_count=0,
        latency=latency,
        coverage={
            "split": {name: len(values) for name, values in split_sets.items()},
            "frame_class": dict(sorted(classes.items())),
            "observed_scale": dict(sorted(observed_scales.items())),
        },
        warnings=warnings,
        contract_notes={
            "online_offline_physically_separate": True,
            "candidate_edge_and_demand_contract_checked": True,
            "six_dimensional_state_availability": "not_in_producer_contract",
            "covariance_availability": "not_in_producer_contract",
        },
    )


def _validate_d3_online(
    row: Mapping[str, Any],
) -> tuple[tuple[str, int, str, int], str, float, str]:
    if row.get("schema_version") != _D3_ONLINE_SCHEMA:
        _fail("d3_online_schema_mismatch")
    if row.get("record_kind") != "online_identity_free_diagnostic_frame":
        _fail("d3_online_record_kind_mismatch")
    _reject_online_truth(row, "D3")
    _false_mapping(row.get("permissions"), _D3_PERMISSIONS, "d3_online_permissions")
    if row.get("online_truth_use_count") != 0:
        _fail("d3_online_truth_counter_nonzero")
    owner = _mapping(row.get("center_identity_ownership"), "d3_center_identity")
    if owner != {
        "owner": "center",
        "learning_create_allowed": False,
        "learning_rewrite_allowed": False,
    }:
        _fail("d3_center_identity_ownership_invalid")
    source = _mapping(row.get("source"), "d3_source")
    split = str(source.get("split"))
    if split not in {"train", "validation", "test"}:
        _fail("d3_online_split_invalid", split)
    seed = _int(source.get("seed"), "d3_online_seed")
    episode_id = _nonempty(source.get("episode_id"), "d3_episode_id")
    frame_index = _nonnegative_int(source.get("frame_index"), "d3_frame_index")
    delay = _validate_timestamp_pair(
        source.get("measurement_timestamp_s"),
        source.get("arrival_timestamp_s"),
        "d3_online_timestamp",
    )
    scale = _mapping(row.get("observed_scale"), "d3_observed_scale")
    target_count = _nonnegative_int(scale.get("anonymous_target_count"), "d3_target_count")
    resource_count = _nonnegative_int(scale.get("anonymous_resource_count"), "d3_resource_count")
    action_mask = _mapping(row.get("action_mask"), "d3_action_mask")
    if action_mask.get("shape") != [target_count, resource_count]:
        _fail("d3_action_mask_shape_mismatch")
    edges = _edge_set(row.get("candidate_edge_indices"), target_count, resource_count, "d3_candidate")
    if action_mask.get("true_count") != len(edges):
        _fail("d3_action_mask_true_count_mismatch")
    if row.get("candidate_edge_indices_sha256") != _canonical_sha256(
        [list(edge) for edge in edges]
    ):
        _fail("d3_candidate_edge_hash_mismatch")
    demand = row.get("anonymous_target_demand_slots")
    if not isinstance(demand, list) or len(demand) != target_count:
        _fail("d3_target_demand_length_mismatch")
    if any(type(item) is not int or item < 0 for item in demand):
        _fail("d3_target_demand_invalid")
    if row.get("target_demand_slots_sha256") != _canonical_sha256(demand):
        _fail("d3_target_demand_hash_mismatch")
    return (
        (split, seed, episode_id, frame_index),
        _canonical_sha256(row),
        delay,
        f"{target_count}t{resource_count}r",
    )


def _validate_d3_offline(
    row: Mapping[str, Any],
) -> tuple[tuple[str, int, str, int], str, str]:
    if row.get("schema_version") != _D3_OFFLINE_SCHEMA:
        _fail("d3_offline_schema_mismatch")
    if row.get("record_kind") != "offline_d6_audit_label":
        _fail("d3_offline_record_kind_mismatch")
    _false_mapping(row.get("permissions"), _D3_PERMISSIONS, "d3_offline_permissions")
    identity = _mapping(row.get("identity_provenance"), "d3_identity_provenance")
    if identity != {
        "global_track_id_owner": "center",
        "learning_path_created_global_track_id_count": 0,
        "learning_path_rewritten_global_track_id_count": 0,
    }:
        _fail("d3_offline_identity_provenance_invalid")
    ref = _mapping(row.get("source_ref"), "d3_source_ref")
    key = (
        str(ref.get("split")),
        _int(ref.get("seed"), "d3_offline_seed"),
        _nonempty(ref.get("episode_id"), "d3_offline_episode"),
        _nonnegative_int(ref.get("frame_index"), "d3_offline_frame"),
    )
    digest = _sha(ref.get("online_payload_sha256"), "d3_online_payload_sha256")
    classification = _mapping(row.get("classification"), "d3_classification")
    frame_class = str(classification.get("frame_class"))
    if frame_class not in {"positive", "negative"}:
        _fail("d3_frame_class_invalid")
    return key, digest, frame_class


def _audit_d4(context: _SourceContext) -> dict[str, Any]:
    expected_paths = {
        "dataset/manifest.json",
        "main_schedule.json",
        "episode_progress.jsonl",
        "generation_checkpoint.json",
        "generation_session.json",
    }
    expected_paths.update(
        f"dataset/online/{index:03d}_{28100 + index}.jsonl" for index in range(324)
    )
    expected_paths.update(
        f"dataset/labels/{index:03d}_{28100 + index}.jsonl" for index in range(324)
    )
    _require_inventory_exact(context, expected_paths)
    manifest = _required_json(context, "dataset/manifest.json")
    if "schema_version" in manifest or manifest.get("schema") != _D4_MANIFEST_SCHEMA:
        _fail("d4_manifest_schema_field_mismatch")
    required_manifest = {
        "episode_count": 324,
        "frame_count": 921,
        "online_feature_file_count": 324,
        "offline_label_file_count": 324,
        "online_labels_separate": True,
        "split": "train",
        "train_only": True,
        "training_count": 0,
        "checkpoint_count": 0,
        "model_registration_count": 0,
        "runtime_connection_count": 0,
    }
    for key, expected in required_manifest.items():
        if manifest.get(key) != expected:
            _fail("d4_manifest_contract_mismatch", key)
    if manifest.get("validation_seed_allocation") != [] or manifest.get("test_seed_allocation") != []:
        _fail("d4_non_train_seed_allocation_present")
    _false_mapping(manifest.get("permissions"), _D4_PERMISSIONS, "d4_permissions", string_fields={"schema"})

    episodes = _mapping_list(manifest.get("episodes"), "d4_episodes")
    if len(episodes) != 324:
        _fail("d4_episode_count_mismatch")
    seen_episode: set[str] = set()
    seen_seed: set[int] = set()
    latency: list[float] = []
    target_classes: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()
    total_frames = 0
    for index, episode in enumerate(episodes):
        seed = 28100 + index
        episode_id = f"d4-a2-v8-train-seed-{seed}"
        if episode.get("schema") != "d4-region-resource-v8-train-episode-manifest-v1":
            _fail("d4_episode_manifest_schema_mismatch", str(index))
        if episode.get("schedule_index") != index or episode.get("seed") != seed:
            _fail("d4_episode_schedule_mismatch", str(index))
        if episode.get("episode_id") != episode_id:
            _fail("d4_episode_id_mismatch", str(index))
        if episode_id in seen_episode or seed in seen_seed:
            _fail("d4_episode_or_seed_duplicate", episode_id)
        seen_episode.add(episode_id)
        seen_seed.add(seed)
        online_rel = f"dataset/{_safe_relative(episode.get('online_features_relative_path'), 'd4_online_ref')}"
        label_rel = f"dataset/{_safe_relative(episode.get('offline_labels_relative_path'), 'd4_label_ref')}"
        _require_listed_reference(context, online_rel)
        _require_listed_reference(context, label_rel)
        if context.inventory_by_path[online_rel].sha256 != episode.get("online_features_sha256"):
            _fail("d4_online_manifest_hash_mismatch", episode_id)
        if context.inventory_by_path[label_rel].sha256 != episode.get("offline_labels_sha256"):
            _fail("d4_label_manifest_hash_mismatch", episode_id)
        online_rows = list(_iter_jsonl_again(context, online_rel))
        label_rows = list(_iter_jsonl_again(context, label_rel))
        frame_count = _int(episode.get("frame_count"), "d4_episode_frame_count")
        if len(online_rows) != frame_count or len(label_rows) != frame_count:
            _fail("d4_online_label_frame_count_mismatch", episode_id)
        frame_hashes: dict[tuple[str, int, int], str] = {}
        first_measurement = None
        last_arrival = None
        for expected_frame, row in enumerate(online_rows):
            key, digest, delay, measurement, arrival, reasons = _validate_d4_online(
                row, episode_id, seed, expected_frame
            )
            if key in frame_hashes:
                _fail("d4_online_frame_duplicate", repr(key))
            frame_hashes[key] = digest
            latency.append(delay)
            first_measurement = measurement if first_measurement is None else min(first_measurement, measurement)
            last_arrival = arrival if last_arrival is None else max(last_arrival, arrival)
            failure_reasons.update(reasons)
        label_keys: set[tuple[str, int, int]] = set()
        for expected_frame, row in enumerate(label_rows):
            key, digest, target_class, reasons = _validate_d4_label(
                row, episode_id, seed, expected_frame
            )
            if key in label_keys:
                _fail("d4_label_frame_duplicate", repr(key))
            label_keys.add(key)
            if frame_hashes.get(key) != digest:
                _fail("d4_online_label_hash_binding_mismatch", repr(key))
            target_classes[target_class] += 1
            failure_reasons.update(reasons)
        if set(frame_hashes) != label_keys:
            _fail("d4_online_label_inventory_mismatch", episode_id)
        if first_measurement != episode.get("first_measurement_timestamp"):
            _fail("d4_first_measurement_mismatch", episode_id)
        if last_arrival != episode.get("last_arrival_timestamp"):
            _fail("d4_last_arrival_mismatch", episode_id)
        total_frames += frame_count
    if total_frames != 921:
        _fail("d4_total_frame_count_mismatch")
    return _module_result(
        context,
        episode_count=324,
        record_count=921,
        truth_leakage_count=0,
        split_leakage_count=0,
        latency=latency,
        coverage={
            "split": {"train": 324, "validation": 0, "test": 0},
            "target_class": dict(sorted(target_classes.items())),
            "failure_reason": dict(sorted(failure_reasons.items())),
        },
        warnings=["d4_covariance_not_in_region_resource_v8_source_contract"],
        contract_notes={
            "manifest_schema_field": "schema",
            "online_offline_physically_separate": True,
            "epoch_lease_plan_version_checked": True,
            "covariance_availability": "not_in_producer_contract",
        },
    )


def _validate_d4_online(
    row: Mapping[str, Any],
    episode_id: str,
    seed: int,
    frame_index: int,
) -> tuple[tuple[str, int, int], str, float, float, float, list[str]]:
    if row.get("schema") != _D4_ONLINE_SCHEMA or "schema_version" in row:
        _fail("d4_online_schema_field_mismatch")
    if row.get("episode_id") != episode_id or row.get("seed") != seed or row.get("frame_index") != frame_index:
        _fail("d4_online_frame_binding_mismatch", episode_id)
    if row.get("split") != "train":
        _fail("d4_online_split_mismatch")
    _reject_online_truth(row, "D4")
    _false_mapping(row.get("permissions"), _D4_PERMISSIONS, "d4_online_permissions", string_fields={"schema"})
    measurement = _finite(row.get("measurement_timestamp"), "d4_measurement_timestamp")
    arrival = _finite(row.get("arrival_timestamp"), "d4_arrival_timestamp")
    delay = _validate_timestamp_pair(measurement, arrival, "d4_timestamp")
    regions = _mapping_list(row.get("regions"), "d4_regions")
    region_count = _nonnegative_int(row.get("region_count"), "d4_region_count")
    if len(regions) != region_count:
        _fail("d4_region_count_mismatch")
    region_indices: set[int] = set()
    for region in regions:
        index = _nonnegative_int(region.get("region_index"), "d4_region_index")
        if index >= region_count or index in region_indices:
            _fail("d4_region_index_invalid")
        region_indices.add(index)
        _nonnegative_int(region.get("epoch"), "d4_epoch")
        _nonnegative_int(region.get("plan_version"), "d4_plan_version")
        lease = _finite(region.get("lease_expires_at_s"), "d4_lease")
        if region.get("owner_active") is True and lease < measurement:
            _fail("d4_active_owner_lease_expired")
        for key in ("region_id", "owner_id", "owner_layer", "plan_id"):
            _nonempty(region.get(key), f"d4_{key}")
    edge_indices: set[int] = set()
    for edge in _mapping_list(row.get("directed_edges"), "d4_edges"):
        edge_index = _nonnegative_int(edge.get("edge_index"), "d4_edge_index")
        if edge_index in edge_indices:
            _fail("d4_edge_index_duplicate")
        edge_indices.add(edge_index)
        source = _nonnegative_int(edge.get("source_region_index"), "d4_edge_source")
        target = _nonnegative_int(edge.get("target_region_index"), "d4_edge_target")
        if source >= region_count or target >= region_count or source == target:
            _fail("d4_edge_endpoint_invalid")
    reasons = [str(item) for item in row.get("projection_rejection_reasons", [])]
    reasons.extend(str(item) for item in row.get("invariant_failure_reasons", []))
    return (
        (episode_id, seed, frame_index),
        _canonical_sha256(row),
        delay,
        measurement,
        arrival,
        reasons,
    )


def _validate_d4_label(
    row: Mapping[str, Any], episode_id: str, seed: int, frame_index: int
) -> tuple[tuple[str, int, int], str, str, list[str]]:
    if row.get("schema") != _D4_LABEL_SCHEMA or "schema_version" in row:
        _fail("d4_label_schema_field_mismatch")
    if row.get("episode_id") != episode_id or row.get("seed") != seed or row.get("frame_index") != frame_index:
        _fail("d4_label_frame_binding_mismatch", episode_id)
    if row.get("split") != "train":
        _fail("d4_label_split_mismatch")
    digest = _sha(row.get("online_frame_sha256"), "d4_online_frame_sha256")
    target_class = _nonempty(row.get("target_class"), "d4_target_class")
    reasons = [str(item) for item in row.get("hard_negative_reasons", [])]
    return (episode_id, seed, frame_index), digest, target_class, reasons


def _audit_d5(context: _SourceContext) -> dict[str, Any]:
    expected_paths = {
        "source_manifest.json",
        "development/manifest.json",
        "future_held_out/manifest.json",
        "episode_progress.jsonl",
        "generation_checkpoint.json",
        "generation_session.json",
    }
    descriptors = [path for path in context.inventory_by_path if _D5_DESCRIPTOR.fullmatch(path)]
    online_paths = [path for path in context.inventory_by_path if _D5_ONLINE.fullmatch(path)]
    offline_paths = [path for path in context.inventory_by_path if _D5_OFFLINE.fullmatch(path)]
    expected_paths.update(descriptors)
    expected_paths.update(online_paths)
    expected_paths.update(offline_paths)
    _require_inventory_exact(context, expected_paths)
    if len(descriptors) != 104 or len(online_paths) != 104 or len(offline_paths) != 104:
        _fail("d5_episode_artifact_count_mismatch")
    source_manifest = _required_json(context, "source_manifest.json")
    if source_manifest.get("schema_version") != _D5_SOURCE_SCHEMA:
        _fail("d5_source_manifest_schema_mismatch")
    _false_mapping(source_manifest.get("authority"), _D5_AUTHORITY, "d5_source_authority")
    identity = _mapping(source_manifest.get("identity"), "d5_source_identity")
    _validate_d5_source_identity(identity)
    _validate_d5_source_provenance(
        _mapping(source_manifest.get("provenance"), "d5_source_provenance")
    )
    catalogs = _mapping(source_manifest.get("seed_catalogs"), "d5_seed_catalogs")
    split_sets = {
        split: _integer_set(catalogs.get(split), f"d5_{split}_seeds")
        for split in ("train", "validation", "future_held_out")
    }
    _require_disjoint(split_sets, "d5_split")
    if {key: len(value) for key, value in split_sets.items()} != {
        "train": 48,
        "validation": 24,
        "future_held_out": 32,
    }:
        _fail("d5_split_count_mismatch")

    partition_manifests = {
        partition: _required_json(context, f"{partition}/manifest.json")
        for partition in ("development", "future_held_out")
    }
    expected_partition_counts = {"development": 72, "future_held_out": 32}
    descriptors_by_episode: dict[str, Mapping[str, Any]] = {}
    split_episode_ids: dict[str, set[str]] = defaultdict(set)
    split_samples: dict[str, set[str]] = defaultdict(set)
    latency: list[float] = []
    intents: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    treatment_failures: Counter[str] = Counter()
    sample_count = 0

    for relative in sorted(descriptors):
        descriptor = _load_json_again(context, relative)
        match = _D5_DESCRIPTOR.fullmatch(relative)
        assert match is not None
        partition = match.group(1)
        if descriptor.get("schema_version") != _D5_DESCRIPTOR_SCHEMA:
            _fail("d5_descriptor_schema_mismatch", relative)
        if descriptor.get("partition") != partition:
            _fail("d5_descriptor_partition_mismatch", relative)
        content = dict(descriptor)
        declared_content_sha = _sha(content.pop("content_sha256", None), "d5_descriptor_content_sha256")
        if _d5_producer_canonical_line_sha256(content) != declared_content_sha:
            _fail("d5_descriptor_self_hash_mismatch", relative)
        split = str(descriptor.get("split"))
        if split not in split_sets or descriptor.get("seed") not in split_sets[split]:
            _fail("d5_descriptor_split_seed_mismatch", relative)
        expected_partition = "future_held_out" if split == "future_held_out" else "development"
        if partition != expected_partition:
            _fail("d5_descriptor_split_partition_mismatch", relative)
        episode_id = _nonempty(descriptor.get("episode_id"), "d5_episode_id")
        if episode_id in descriptors_by_episode:
            _fail("d5_episode_id_duplicate", episode_id)
        descriptors_by_episode[episode_id] = descriptor
        split_episode_ids[split].add(episode_id)
        online_rel = f"{partition}/{_safe_relative(descriptor.get('online_file'), 'd5_online_ref')}"
        offline_rel = f"{partition}/{_safe_relative(descriptor.get('offline_file'), 'd5_offline_ref')}"
        _require_listed_reference(context, online_rel)
        _require_listed_reference(context, offline_rel)
        if context.inventory_by_path[online_rel].sha256 != descriptor.get("online_sha256"):
            _fail("d5_descriptor_online_hash_mismatch", episode_id)
        if context.inventory_by_path[offline_rel].sha256 != descriptor.get("offline_sha256"):
            _fail("d5_descriptor_offline_hash_mismatch", episode_id)
        online = _load_json_again(context, online_rel)
        offline = _load_json_again(context, offline_rel)
        samples, delays, sample_intents, sample_roles = _validate_d5_online(
            online, descriptor
        )
        failures = _validate_d5_offline(offline, descriptor, samples)
        latency.extend(delays)
        intents.update(sample_intents)
        roles.update(sample_roles)
        treatment_failures.update(failures)
        split_samples[split].update(samples)
        sample_count += len(samples)

    _require_disjoint(split_episode_ids, "d5_episode_split")
    _require_disjoint(split_samples, "d5_sample_split")
    for partition, manifest in partition_manifests.items():
        if manifest.get("schema_version") != _D5_PARTITION_SCHEMA:
            _fail("d5_partition_manifest_schema_mismatch", partition)
        if manifest.get("partition") != partition or manifest.get("status") != "frozen_partition_complete":
            _fail("d5_partition_manifest_state_mismatch", partition)
        if manifest.get("episode_count") != expected_partition_counts[partition]:
            _fail("d5_partition_episode_count_mismatch", partition)
        if manifest.get("schedule_complete") is not True:
            _fail("d5_partition_schedule_incomplete", partition)
        _false_mapping(manifest.get("authority"), _D5_AUTHORITY, "d5_partition_authority")
        _validate_d5_partition_identity(
            _mapping(manifest.get("identity"), "d5_partition_identity")
        )
        manifest_fingerprints = manifest.get("sample_fingerprints")
        if not isinstance(manifest_fingerprints, list) or len(manifest_fingerprints) != len(set(manifest_fingerprints)):
            _fail("d5_partition_sample_fingerprint_duplicate", partition)
        expected_splits = {"future_held_out"} if partition == "future_held_out" else {"train", "validation"}
        computed = set().union(*(split_samples[name] for name in expected_splits))
        if set(manifest_fingerprints) != computed:
            _fail("d5_partition_sample_inventory_mismatch", partition)
        if manifest.get("unique_sample_count") != len(computed):
            _fail("d5_partition_unique_sample_count_mismatch", partition)
        summaries = _mapping_list(manifest.get("episode_summaries"), "d5_episode_summaries")
        if len(summaries) != expected_partition_counts[partition]:
            _fail("d5_partition_episode_summary_count_mismatch", partition)
        for summary in summaries:
            episode_id = str(summary.get("episode_id"))
            descriptor = descriptors_by_episode.get(episode_id)
            if descriptor is None or summary.get("online_sha256") != descriptor.get("online_sha256") or summary.get("offline_sha256") != descriptor.get("offline_sha256"):
                _fail("d5_partition_episode_summary_binding_mismatch", episode_id)
    partition_hashes = _mapping(
        source_manifest.get("dataset_manifest_sha256_by_partition"),
        "d5_partition_hashes",
    )
    for partition in ("development", "future_held_out"):
        relative = f"{partition}/manifest.json"
        if partition_hashes.get(partition) != context.inventory_by_path[relative].sha256:
            _fail("d5_source_partition_hash_mismatch", partition)
    if len(split_episode_ids["train"]) != 48 or len(split_episode_ids["validation"]) != 24 or len(split_episode_ids["future_held_out"]) != 32:
        _fail("d5_episode_split_count_mismatch")

    warnings = [
        "d5_explicit_bbox_geometry_not_in_a3_active_vision_source_contract",
        "d5_future_held_out_integrity_only_not_model_consumption",
    ]
    return _module_result(
        context,
        episode_count=104,
        record_count=sample_count,
        truth_leakage_count=0,
        split_leakage_count=0,
        latency=latency,
        coverage={
            "split_episode": {name: len(values) for name, values in split_episode_ids.items()},
            "split_sample": {name: len(values) for name, values in split_samples.items()},
            "intent": dict(sorted(intents.items())),
            "camera_role": dict(sorted(roles.items())),
            "failure_reason": dict(sorted(treatment_failures.items())),
        },
        warnings=warnings,
        contract_notes={
            "development_episode_count": 72,
            "future_held_out_episode_count": 32,
            "future_held_out_audit_scope": "integrity_only_not_model_consumption",
            "online_offline_physically_separate": True,
            "global_track_id_ownership": "center_read_only",
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
            "online_truth_identity_use_count": 0,
            "candidate_geometry_representation": "opaque_candidate_feature_fingerprint",
            "explicit_bbox_or_local_track_geometry_availability": "not_in_producer_contract",
        },
    )


def _validate_d5_online(
    payload: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> tuple[set[str], list[float], Counter[str], Counter[str]]:
    if payload.get("schema_version") != _D5_ONLINE_SCHEMA:
        _fail("d5_online_schema_mismatch")
    _reject_online_truth(payload, "D5")
    _validate_d5_online_identity(
        _mapping(payload.get("identity"), "d5_online_identity")
    )
    recipe = _mapping(payload.get("recipe"), "d5_recipe")
    for key in ("episode_id", "seed", "split", "allocation_id"):
        if recipe.get(key) != descriptor.get(key):
            _fail("d5_online_recipe_descriptor_mismatch", key)
    controls = _mapping(recipe.get("generation_controls"), "d5_generation_controls")
    for key in (
        "direct_label_control_allowed",
        "sample_copying_allowed",
        "sample_oversampling_allowed",
        "truth_identity_available_to_online_policy",
        "truth_online_injection_allowed",
    ):
        if controls.get(key) is not False:
            _fail("d5_generation_control_not_false", key)
    center_ids = payload.get("center_global_track_ids")
    if not isinstance(center_ids, list) or len(center_ids) != len(set(center_ids)):
        _fail("d5_center_global_track_id_inventory_invalid")
    samples = _mapping_list(payload.get("samples"), "d5_samples")
    fingerprints: set[str] = set()
    latency: list[float] = []
    intents: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    for sample in samples:
        if sample.get("schema_version") != _D5_SAMPLE_SCHEMA:
            _fail("d5_sample_schema_mismatch")
        fingerprint = _sha(sample.get("sample_fingerprint"), "d5_sample_fingerprint")
        if fingerprint in fingerprints:
            _fail("d5_sample_fingerprint_duplicate")
        fingerprints.add(fingerprint)
        if sample.get("global_track_id") not in center_ids:
            _fail("d5_sample_center_track_binding_missing")
        latency.append(
            _validate_timestamp_pair(
                sample.get("measurement_timestamp"),
                sample.get("arrival_timestamp"),
                "d5_sample_timestamp",
            )
        )
        intent = _nonempty(sample.get("intent"), "d5_intent")
        role = _nonempty(sample.get("camera_role"), "d5_camera_role")
        intents[intent] += 1
        roles[role] += 1
        _sha(sample.get("candidate_feature_fingerprint"), "d5_candidate_feature_fingerprint")
    return fingerprints, latency, intents, roles


def _validate_d5_offline(
    payload: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    online_samples: set[str],
) -> Counter[str]:
    if payload.get("schema_version") != _D5_OFFLINE_SCHEMA:
        _fail("d5_offline_schema_mismatch")
    for key in ("episode_id", "split", "allocation_id"):
        if payload.get(key) != descriptor.get(key):
            _fail("d5_offline_descriptor_mismatch", key)
    audits = _mapping_list(payload.get("sample_audits"), "d5_sample_audits")
    fingerprints: set[str] = set()
    failures: Counter[str] = Counter()
    for audit in audits:
        if audit.get("schema_version") != _D5_OFFLINE_SAMPLE_SCHEMA:
            _fail("d5_offline_sample_schema_mismatch")
        fingerprint = _sha(audit.get("sample_fingerprint"), "d5_offline_sample_fingerprint")
        if fingerprint in fingerprints:
            _fail("d5_offline_sample_fingerprint_duplicate")
        fingerprints.add(fingerprint)
        if audit.get("treatment_achieved") is not True:
            failures["treatment_not_achieved"] += 1
        if audit.get("evaluation_available") is not False or audit.get("evaluation") is not None:
            _fail("d5_offline_evaluation_unexpectedly_consumed")
    if fingerprints != online_samples:
        _fail("d5_online_offline_sample_inventory_mismatch")
    return failures


def _validate_d5_source_identity(value: Mapping[str, Any]) -> None:
    expected = {
        "global_track_id_created_count": 0,
        "global_track_id_ownership": "center_read_only",
        "global_track_id_rewritten_count": 0,
    }
    if dict(value) != expected:
        _fail("d5_source_identity_contract_mismatch")


def _validate_d5_source_provenance(value: Mapping[str, Any]) -> None:
    expected = {
        "formal_seed_1000_1019_episode_read_count": 0,
        "online_truth_id_use_count": 0,
        "source_domain": "scalable_3d_point_mass_runtime",
        "synthetic_fixture_episode_count": 0,
        "v2_episode_or_sample_reuse": False,
        "v2_test_episode_or_sample_read_count": 0,
    }
    if dict(value) != expected:
        _fail("d5_source_provenance_contract_mismatch")


def _validate_d5_partition_identity(value: Mapping[str, Any]) -> None:
    expected = {
        "global_track_id_created_count": 0,
        "global_track_id_ownership": "center_read_only",
        "global_track_id_rewritten_count": 0,
        "online_truth_identity_use_count": 0,
    }
    if dict(value) != expected:
        _fail("d5_partition_identity_contract_mismatch")


def _validate_d5_online_identity(value: Mapping[str, Any]) -> None:
    expected = {
        "global_track_id_created_count": 0,
        "global_track_id_ownership": "center_read_only",
        "global_track_id_rewritten_count": 0,
        "online_truth_identity_use_count": 0,
    }
    if dict(value) != expected:
        _fail("d5_online_identity_contract_mismatch")


def _module_result(
    context: _SourceContext,
    *,
    episode_count: int,
    record_count: int,
    truth_leakage_count: int,
    split_leakage_count: int,
    latency: Sequence[float],
    coverage: Mapping[str, Any],
    warnings: Sequence[str],
    contract_notes: Mapping[str, Any],
) -> dict[str, Any]:
    payload_paths = [
        item for item in context.inventory if not item.relative_path.startswith("generation_") and item.relative_path != "episode_progress.jsonl"
    ]
    return {
        "module": context.module,
        "status": "source_integrity_audit_passed_not_training_authorized",
        "source_root": context.root.as_posix(),
        "source_git_commit": context.binding.source_git_commit,
        "module_request_sha256": context.binding.module_request_sha256,
        "generation_authorization_sha256": context.binding.generation_authorization_sha256,
        "manifest_schema_field": context.preflight["manifest_schema_field"],
        "manifest_schema_version": context.preflight["manifest_schema_version"],
        "inventory_content_sha256": context.binding.artifact_inventory_sha256,
        "inventory_tree_sha256": context.preflight["artifact_inventory_tree_sha256"],
        "inventory_file_count": len(context.inventory),
        "inventory_total_size_bytes": sum(item.size_bytes for item in context.inventory),
        "source_file_open_count": len(context.inventory) + 1,
        "source_bytes_read_scope": sum(item.size_bytes for item in context.inventory) + context.result_size_bytes,
        "payload_file_open_count": len(payload_paths),
        "payload_bytes_read_scope": sum(item.size_bytes for item in payload_paths),
        "parsed_document_record_count": context.document_record_count + 1,
        "semantic_episode_count": episode_count,
        "semantic_record_count": record_count,
        "hash_gate_passed": True,
        "schema_gate_passed": True,
        "count_gate_passed": True,
        "path_gate_passed": True,
        "finite_numeric_gate_passed": True,
        "timestamp_gate_passed": True,
        "covariance_matrix_count": context.covariance_matrix_count,
        "covariance_gate_passed": True,
        "truth_leakage_count": truth_leakage_count,
        "truth_leakage_gate_passed": truth_leakage_count == 0,
        "split_leakage_count": split_leakage_count,
        "split_leakage_gate_passed": split_leakage_count == 0,
        "missing_required_field_count": 0,
        "required_field_missing_rate": 0.0,
        "latency_seconds": _distribution(latency),
        "coverage": dict(coverage),
        "warning_codes": sorted(set(warnings)),
        "contract_notes": dict(contract_notes),
        "permissions": dict(_RESULT_PERMISSION_VALUES),
        "training_permission_granted": False,
        "model_consumption_performed": False,
    }


def _reject_online_truth(value: Any, module: str, path: str = "online") -> None:
    forbidden_keys = {
        "truth",
        "truth_id",
        "truth_entity_id",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "target_truth_id",
        "airsim_id",
    }
    allowed_truth_policy = {
        "online_truth_use_count",
        "online_truth_identity_use_count",
        "truth_identity_available_to_online_policy",
        "truth_online_injection_allowed",
    }
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            child_path = f"{path}.{raw_key}"
            if key in forbidden_keys or key.endswith(("_actor_id", "_actor_name", "_object_id", "_object_name", "_truth_id")):
                _fail("online_truth_leakage", f"{module}:{child_path}")
            if key in allowed_truth_policy and child not in (0, False):
                _fail("online_truth_policy_nonzero", f"{module}:{child_path}")
            if module == "D3" and key in {"global_track_id", "track_id", "target_id", "resource_id", "vehicle_id"}:
                _fail("d3_online_identity_leakage", child_path)
            _reject_online_truth(child, module, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_online_truth(child, module, f"{path}[{index}]")
    elif module == "D3" and isinstance(value, str):
        lowered = value.lower()
        if lowered.startswith(("actor_", "object_", "truth_", "gt3d-", "global-track-")):
            _fail("d3_online_identity_value_leakage", path)


def _validate_timestamp_pair(measurement: Any, arrival: Any, label: str) -> float:
    measurement_value = _finite(measurement, f"{label}_measurement")
    arrival_value = _finite(arrival, f"{label}_arrival")
    if arrival_value < measurement_value:
        _fail("arrival_before_measurement", label)
    return arrival_value - measurement_value


def _validate_covariances(value: Any, path: str) -> int:
    count = 0
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower().replace("-", "_")
            child_path = f"{path}.{raw_key}"
            if "covariance" in key and _looks_like_matrix(child):
                _validate_covariance_matrix(child, child_path)
                count += 1
            count += _validate_covariances(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            count += _validate_covariances(child, f"{path}[{index}]")
    return count


def _validate_covariance_matrix(value: Any, label: str) -> None:
    if not _looks_like_matrix(value):
        _fail("covariance_matrix_shape_invalid", label)
    matrix = np.asarray(value, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        _fail("covariance_matrix_shape_invalid", label)
    if not np.isfinite(matrix).all():
        _fail("covariance_nonfinite", label)
    if not np.allclose(matrix, matrix.T, atol=1e-9, rtol=1e-9):
        _fail("covariance_not_symmetric", label)
    if np.any(np.diag(matrix) < -1e-10):
        _fail("covariance_negative_diagonal", label)
    if float(np.min(np.linalg.eigvalsh(matrix))) < -1e-8:
        _fail("covariance_not_psd", label)


def _looks_like_matrix(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(row, list) for row in value)
    )


def _validate_finite_tree(value: Any, path: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            _fail("nonfinite_numeric_value", path)
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _validate_finite_tree(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_finite_tree(child, f"{path}[{index}]")


def _false_mapping(
    value: Any,
    expected_fields: set[str],
    label: str,
    *,
    string_fields: set[str] | None = None,
) -> None:
    payload = _mapping(value, label)
    _exact_keys(payload, expected_fields, f"{label}_fields")
    string_fields = string_fields or set()
    for key, item in payload.items():
        if key in string_fields:
            if not isinstance(item, str) or not item:
                _fail(f"{label}_string_invalid", key)
        elif item is not False:
            _fail(f"{label}_permission_not_false", key)


def _edge_set(value: Any, rows: int, columns: int, label: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, list):
        _fail(f"{label}_edges_invalid")
    result: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            _fail(f"{label}_edge_invalid")
        row = _nonnegative_int(item[0], f"{label}_row")
        column = _nonnegative_int(item[1], f"{label}_column")
        if row >= rows or column >= columns:
            _fail(f"{label}_edge_out_of_range")
        result.append((row, column))
    if len(result) != len(set(result)):
        _fail(f"{label}_edge_duplicate")
    return tuple(result)


def _require_inventory_exact(context: _SourceContext, expected: set[str]) -> None:
    actual = set(context.inventory_by_path)
    if actual != expected:
        missing = sorted(expected - actual)[:3]
        extra = sorted(actual - expected)[:3]
        _fail("inventory_payload_set_mismatch", f"missing={missing};extra={extra}")


def _require_listed_reference(context: _SourceContext, relative: str) -> None:
    _safe_relative(relative, "manifest_reference")
    if relative not in context.inventory_by_path:
        _fail("manifest_references_unlisted_payload", relative)


def _required_json(context: _SourceContext, relative: str) -> Mapping[str, Any]:
    value = context.parsed_json.get(relative)
    if value is None:
        _fail("required_json_not_parsed", relative)
    return value


def _load_json_again(
    context: _SourceContext, relative: str
) -> Mapping[str, Any]:
    """Reopen one inventory-bound JSON document for the semantic pass."""

    _require_listed_reference(context, relative)
    path = _resolve_inventory_file(context.root, relative, "semantic_payload")
    payload = _decode_json_object(path.read_bytes(), relative)
    _validate_finite_tree(payload, relative)
    return payload


def _iter_jsonl_again(
    context: _SourceContext, relative: str
) -> Iterable[Mapping[str, Any]]:
    """Stream one inventory-bound JSONL file without retaining its records."""

    _require_listed_reference(context, relative)
    path = _resolve_inventory_file(context.root, relative, "semantic_payload")
    with path.open("rb") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.endswith(b"\n") or not raw.strip():
                _fail("jsonl_record_encoding_invalid", f"{relative}:{line_number}")
            payload = _decode_json_object(raw[:-1], f"{relative}:{line_number}")
            _validate_finite_tree(payload, f"{relative}:{line_number}")
            yield payload


def _require_disjoint(values: Mapping[str, set[Any]], label: str) -> None:
    names = sorted(values)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = values[left].intersection(values[right])
            if overlap:
                _fail("split_leakage", f"{label}:{left}:{right}:{len(overlap)}")


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"available": False, "count": 0, "reason": "field_not_in_contract"}
    array = np.asarray(values, dtype=float)
    return {
        "available": True,
        "count": int(array.size),
        "minimum": float(np.min(array)),
        "mean": float(np.mean(array)),
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(np.max(array)),
    }


def _load_bound_json_file(path: Path, expected_sha: str, label: str) -> Mapping[str, Any]:
    source = Path(path).expanduser().absolute()
    _reject_symlink_components(source, label)
    if not source.is_file():
        _fail(f"{label}_missing", str(source))
    content = source.read_bytes()
    if sha256(content).hexdigest() != expected_sha:
        _fail(f"{label}_sha256_mismatch")
    return _decode_json_object(content, label)


def _resolve_source_root(path: Path) -> Path:
    root = Path(path).expanduser().absolute()
    _reject_symlink_components(root, "source_root")
    if not root.is_dir():
        _fail("source_root_invalid", str(root))
    return root


def _resolve_inventory_file(root: Path, relative: str, label: str) -> Path:
    safe = _safe_relative(relative, label)
    base = Path(root).expanduser().absolute()
    path = base.joinpath(*PurePosixPath(safe).parts)
    _reject_symlink_components(path, label)
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        _fail(f"{label}_missing", str(exc))
    if not stat.S_ISREG(info.st_mode):
        _fail(f"{label}_not_regular", safe)
    if not _is_relative_to(path.absolute(), base):
        _fail(f"{label}_outside_source_root", safe)
    return path


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail(f"{label}_invalid", repr(value))
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{label}_invalid", value)
    if path.as_posix() != value:
        _fail(f"{label}_not_canonical", value)
    return value


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = Path(path).expanduser().absolute()
    for component in (absolute, *absolute.parents):
        if component.exists() and component.is_symlink():
            _fail(f"{label}_symlink_forbidden", str(component))


def _decode_json_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(f"{label}_json_invalid", str(exc))
    if not isinstance(value, dict):
        _fail(f"{label}_json_object_required")
    return value


def _unique_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _module_map(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != 3:
        _fail(f"{label}_invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in value:
        payload = _mapping(item, label)
        module = str(payload.get("module"))
        if module in result:
            _fail(f"{label}_duplicate", module)
        result[module] = payload
    if set(result) != set(EXPECTED_EPISODE_COUNTS):
        _fail(f"{label}_module_set_mismatch")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_mapping_required")
    return value


def _mapping_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        _fail(f"{label}_mapping_list_required")
    return list(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        _fail(label, ",".join(sorted(set(value).symmetric_difference(expected))))


def _integer_set(value: Any, label: str) -> set[int]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        _fail(f"{label}_invalid")
    result = set(value)
    if len(result) != len(value):
        _fail(f"{label}_duplicate")
    return result


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        _fail(f"{label}_invalid", repr(value))
    return float(value)


def _int(value: Any, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label}_invalid", repr(value))
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    result = _int(value, label)
    if result < 0:
        _fail(f"{label}_invalid", str(result))
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label}_invalid", repr(value))
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        _fail(f"{label}_invalid", str(value))
    return value


def _nonnegative_int_from_any(value: Any, label: str) -> int:
    return _nonnegative_int(value, label)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json_line(value: Any) -> bytes:
    return _canonical_json(value) + b"\n"


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _canonical_line_sha256(value: Any) -> str:
    """Match the newline-terminated canonical metadata digest used by preflight."""

    return sha256(_canonical_json_line(value)).hexdigest()


def _d5_producer_canonical_line_sha256(value: Any) -> str:
    """Match the D5 producer's ASCII-escaped canonical JSON line digest."""

    content = (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return sha256(content).hexdigest()


def _canonical_jsonl_sha256(values: Iterable[Mapping[str, Any]]) -> str:
    digest = sha256()
    for value in values:
        digest.update(_canonical_json_line(value))
    return digest.hexdigest()


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _error_parts(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, LearningSourcePayloadAuditError):
        return exc.code, exc.detail
    return "source_audit_io_error", str(exc)


def _fail(code: str, detail: str = "") -> None:
    raise LearningSourcePayloadAuditError(code, detail)


def _render_markdown(result: Mapping[str, Any]) -> str:
    passed = result.get("audit_passed") is True
    lines = [
        "# D3/D4/D5 来源载荷完整性审计",
        "",
        f"- 审计状态：`{'通过' if passed else '未通过'}`",
        f"- 结果代码：`{result.get('status', 'failed_closed')}`",
        "- 审计范围：来源、路径、哈希、结构、计数、时间戳、数值、真值隔离和切分隔离。",
        "- 训练、优化、检查点选择、阈值调整、模型推理、影子、辅助、分配、降级、",
        "  联盟、相机命令、运行、物理和控制权限：`全部关闭`",
        "- 本报告是来源完整性证据，`不是训练许可或模型准入结论`。",
        "",
        "## 模块结果",
        "",
        "| 模块 | 状态 | episode | 语义记录 | 打开文件 | 读取范围字节 | 真值泄漏 | 切分泄漏 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for module, item in sorted(result.get("sources", {}).items()):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(module),
                    str(item.get("status", "failed_closed")),
                    str(item.get("semantic_episode_count", 0)),
                    str(item.get("semantic_record_count", 0)),
                    str(item.get("source_file_open_count", 0)),
                    str(item.get("source_bytes_read_scope", 0)),
                    str(item.get("truth_leakage_count", "未完成")),
                    str(item.get("split_leakage_count", "未完成")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 门控", ""])
    if result.get("blocker_codes"):
        lines.append("硬阻断：")
        for code in result["blocker_codes"]:
            details = result.get("blocker_details", {}).get(code, [])
            lines.append(f"- `{code}`：{'; '.join(map(str, details)) or '无附加信息'}")
    else:
        lines.append("路径、哈希、schema、计数、有限数值、时间戳、真值隔离和切分隔离硬门均通过。")
    warnings = result.get("warning_codes", [])
    if warnings:
        lines.extend(["", "## 合同边界", ""])
        lines.extend(f"- `{warning}`" for warning in warnings)
    lines.extend(
        [
            "",
            "## 权限结论",
            "",
            "D6 只完成只读来源完整性审计。未来保留集只做哈希、结构、计数和隔离核验，",
            "没有用于训练、验证、测试、模型选择、阈值选择或推理。后续任何模型消费均需",
            "新的显式授权和独立准入门。",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "LEARNING_SOURCE_PAYLOAD_AUDIT_SCHEMA_VERSION",
    "SOURCE_AUDIT_AUTHORIZATION_SCHEMA_VERSION",
    "SOURCE_AUDIT_CONFIRMATION",
    "LearningSourcePayloadAuditError",
    "LearningSourcePayloadAuditInputs",
    "audit_learning_source_payloads",
    "write_learning_source_payload_audit_report",
]
