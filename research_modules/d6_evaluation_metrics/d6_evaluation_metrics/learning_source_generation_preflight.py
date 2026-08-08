"""Metadata-only preflight for D3/D4/D5 learning-source generation outputs.

This module deliberately stops before payload inspection.  It reads only the
explicitly bound generation session, checkpoint, result, progress and manifest
files.  Dataset episode/sample files are represented by producer inventory
metadata but are never opened here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Sequence


LEARNING_SOURCE_GENERATION_PREFLIGHT_INPUT_SCHEMA_VERSION = (
    "d6.learning-source-generation-preflight-input.v1"
)
LEARNING_SOURCE_GENERATION_PREFLIGHT_SCHEMA_VERSION = (
    "d6.learning-source-generation-preflight.v1"
)
SOURCE_GENERATION_SESSION_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-session-v1"
)
SOURCE_GENERATION_CHECKPOINT_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-checkpoint-v1"
)
SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-progress-v1"
)
SOURCE_GENERATION_RESULT_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-result-v1"
)

EXPECTED_EPISODE_COUNTS = {"D3": 300, "D4": 324, "D5": 104}
_FILE_ROLES = ("session", "checkpoint", "result", "progress", "manifest")
_FIXED_METADATA_NAMES = {
    "session": "generation_session.json",
    "checkpoint": "generation_checkpoint.json",
    "result": "generation_result.json",
    "progress": "episode_progress.jsonl",
}
_MANIFEST_NAMES = frozenset(
    {"dataset_manifest.json", "manifest.json", "source_manifest.json"}
)
_MANIFEST_SCHEMA_FIELD_BY_MODULE = {
    "D3": "schema_version",
    "D4": "schema",
    "D5": "schema_version",
}
_MANIFEST_SCHEMA_FIELDS = frozenset(_MANIFEST_SCHEMA_FIELD_BY_MODULE.values())
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")

_NO_AUTHORITY = {
    "training": False,
    "validation_consumption": False,
    "test_consumption": False,
    "future_held_out_consumption": False,
    "model_inference": False,
    "shadow": False,
    "assist": False,
    "promotion": False,
    "ppo": False,
    "assignment": False,
    "degradation": False,
    "camera_command": False,
    "runtime": False,
    "production": False,
    "control": False,
    "global_track_id_create": False,
    "global_track_id_write": False,
}


class LearningSourceGenerationPreflightError(ValueError):
    """Stable failure for malformed inputs or unsafe generation metadata."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class MetadataFileBinding:
    """One explicitly named metadata file and its out-of-band SHA-256."""

    relative_path: str
    sha256: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        role: str,
    ) -> "MetadataFileBinding":
        payload = _exact_mapping(value, {"relative_path", "sha256"}, f"{role}_binding")
        relative = _safe_relative(payload["relative_path"], f"{role}_relative_path")
        if role in _FIXED_METADATA_NAMES and relative != _FIXED_METADATA_NAMES[role]:
            _fail(f"{role}_path_mismatch", relative)
        if role == "manifest" and PurePosixPath(relative).name not in _MANIFEST_NAMES:
            _fail("manifest_path_not_metadata", relative)
        return cls(relative_path=relative, sha256=_sha(payload["sha256"], f"{role}_sha256"))

    def to_dict(self) -> dict[str, str]:
        return {"relative_path": self.relative_path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class GenerationSourceBinding:
    """Frozen metadata contract for one explicitly declared module root."""

    module: str
    source_root: Path
    expected_episode_count: int
    source_git_commit: str
    generation_authorization_sha256: str
    module_request_sha256: str
    files: Mapping[str, MetadataFileBinding]
    artifact_inventory_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GenerationSourceBinding":
        payload = _exact_mapping(
            value,
            {
                "module",
                "source_root",
                "expected_episode_count",
                "source_git_commit",
                "generation_authorization_sha256",
                "module_request_sha256",
                "files",
                "artifact_inventory_sha256",
            },
            "source_binding",
        )
        module = str(payload["module"])
        if module not in EXPECTED_EPISODE_COUNTS:
            _fail("source_module_invalid", module)
        count = _positive_int(payload["expected_episode_count"], "expected_episode_count")
        if count != EXPECTED_EPISODE_COUNTS[module]:
            _fail("source_episode_count_contract_mismatch", f"{module}:{count}")
        root_text = payload["source_root"]
        if not isinstance(root_text, str) or not root_text.strip():
            _fail("source_root_declaration_invalid")
        root = Path(root_text).expanduser()
        if not root.is_absolute():
            _fail("source_root_must_be_absolute", root_text)
        raw_files = _exact_mapping(payload["files"], set(_FILE_ROLES), "source_files")
        files = {
            role: MetadataFileBinding.from_mapping(raw_files[role], role=role)
            for role in _FILE_ROLES
        }
        paths = [item.relative_path for item in files.values()]
        if len(set(paths)) != len(paths):
            _fail("source_metadata_path_reused", module)
        return cls(
            module=module,
            source_root=root.absolute(),
            expected_episode_count=count,
            source_git_commit=_commit(payload["source_git_commit"]),
            generation_authorization_sha256=_sha(
                payload["generation_authorization_sha256"],
                "generation_authorization_sha256",
            ),
            module_request_sha256=_sha(
                payload["module_request_sha256"], "module_request_sha256"
            ),
            files=files,
            artifact_inventory_sha256=_sha(
                payload["artifact_inventory_sha256"],
                "artifact_inventory_sha256",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "source_root": self.source_root.as_posix(),
            "expected_episode_count": self.expected_episode_count,
            "source_git_commit": self.source_git_commit,
            "generation_authorization_sha256": self.generation_authorization_sha256,
            "module_request_sha256": self.module_request_sha256,
            "files": {role: self.files[role].to_dict() for role in _FILE_ROLES},
            "artifact_inventory_sha256": self.artifact_inventory_sha256,
        }


@dataclass(frozen=True, slots=True)
class LearningSourceGenerationPreflightInputs:
    """Exact three-module request loaded from one SHA-bound JSON contract."""

    contract_id: str
    sources: tuple[GenerationSourceBinding, ...]
    input_contract_sha256: str
    schema_version: str = LEARNING_SOURCE_GENERATION_PREFLIGHT_INPUT_SCHEMA_VERSION

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        input_contract_sha256: str,
    ) -> "LearningSourceGenerationPreflightInputs":
        payload = _exact_mapping(value, {"schema_version", "contract_id", "sources"}, "input")
        if payload["schema_version"] != LEARNING_SOURCE_GENERATION_PREFLIGHT_INPUT_SCHEMA_VERSION:
            _fail("input_schema_mismatch", str(payload["schema_version"]))
        contract_id = str(payload["contract_id"])
        if _IDENTIFIER.fullmatch(contract_id) is None:
            _fail("contract_id_invalid", contract_id)
        raw_sources = payload["sources"]
        if not isinstance(raw_sources, list) or len(raw_sources) != 3:
            _fail("source_inventory_must_contain_d3_d4_d5")
        sources = tuple(GenerationSourceBinding.from_mapping(item) for item in raw_sources)
        if {item.module for item in sources} != set(EXPECTED_EPISODE_COUNTS):
            _fail("source_module_inventory_mismatch")
        return cls(
            contract_id=contract_id,
            sources=tuple(sorted(sources, key=lambda item: item.module)),
            input_contract_sha256=_sha(input_contract_sha256, "input_contract_sha256"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "sources": [item.to_dict() for item in self.sources],
        }


def load_learning_source_generation_preflight_inputs(
    path: str | Path,
    *,
    expected_sha256: str,
) -> LearningSourceGenerationPreflightInputs:
    """Load a regular, non-symlink contract and verify its raw file digest."""

    source = Path(path).expanduser().absolute()
    _reject_symlink_components(source, "input_contract")
    if not source.is_file():
        _fail("input_contract_missing", str(source))
    content = source.read_bytes()
    actual = sha256(content).hexdigest()
    if actual != _sha(expected_sha256, "expected_input_contract_sha256"):
        _fail("input_contract_sha256_mismatch")
    payload = _decode_json_object(content, "input_contract")
    return LearningSourceGenerationPreflightInputs.from_mapping(
        payload,
        input_contract_sha256=actual,
    )


def evaluate_learning_source_generation_preflight(
    inputs: LearningSourceGenerationPreflightInputs,
) -> dict[str, Any]:
    """Evaluate only frozen metadata; never open an episode/sample payload."""

    result: dict[str, Any] = {
        "schema_version": LEARNING_SOURCE_GENERATION_PREFLIGHT_SCHEMA_VERSION,
        "input_schema_version": inputs.schema_version,
        "input_contract_sha256": inputs.input_contract_sha256,
        "contract_id": inputs.contract_id,
        "status": "failed_closed",
        "metadata_preflight_passed": False,
        "full_payload_audit_performed": False,
        "formal_source_data_read": False,
        "blocker_codes": [],
        "blocker_details": {},
        "sources": {},
        "permissions": dict(_NO_AUTHORITY),
        "d6_control_participation": False,
    }
    blockers: dict[str, list[str]] = {}
    source_results: dict[str, Any] = {}
    for binding in inputs.sources:
        try:
            source_results[binding.module] = _evaluate_source(binding)
        except (LearningSourceGenerationPreflightError, OSError) as exc:
            if isinstance(exc, LearningSourceGenerationPreflightError):
                code, detail = exc.code, exc.detail
            else:  # pragma: no cover - uncommon platform I/O failure.
                code, detail = "metadata_io_error", str(exc)
            blockers.setdefault(code, []).append(
                f"{binding.module}:{detail}" if detail else binding.module
            )
            source_results[binding.module] = {
                "module": binding.module,
                "source_root": binding.source_root.as_posix(),
                "status": "failed_closed",
                "blocker_code": code,
                "payload_file_open_count": 0,
                "full_payload_audit_performed": False,
                "permissions": dict(_NO_AUTHORITY),
            }
    result["sources"] = source_results
    if blockers:
        result["blocker_codes"] = sorted(blockers)
        result["blocker_details"] = {
            key: sorted(values) for key, values in sorted(blockers.items())
        }
        return result
    result.update(
        {
            "status": "ready_for_explicit_d6_source_audit_authorization",
            "metadata_preflight_passed": True,
            "blocker_codes": [],
            "blocker_details": {},
        }
    )
    return result


def write_learning_source_generation_preflight_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, str]:
    """Write machine JSON, Chinese Markdown and their SHA256SUMS."""

    output = Path(output_dir).expanduser().absolute()
    _reject_symlink_components(output, "output_dir")
    source_roots = [
        Path(item["source_root"]).absolute()
        for item in result.get("sources", {}).values()
        if isinstance(item, Mapping) and item.get("source_root")
    ]
    if any(_is_relative_to(output, root) for root in source_roots):
        _fail("output_inside_source_root", str(output))
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        _fail("output_dir_not_empty", str(output))
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "preflight.json"
    markdown_path = output / "PREFLIGHT_REPORT_CN.md"
    json_path.write_bytes(_canonical_json_bytes(dict(result)))
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
    return {**hashes, checksum_path.name: _hash_file(checksum_path)}


def _evaluate_source(binding: GenerationSourceBinding) -> dict[str, Any]:
    root = _resolve_source_root(binding.source_root)
    paths = {
        role: _resolve_bound_file(root, binding.files[role], role)
        for role in _FILE_ROLES
    }
    payloads: dict[str, Any] = {}
    for role in ("session", "checkpoint", "result", "manifest"):
        payloads[role] = _load_bound_json(paths[role], binding.files[role], role)
    progress_bytes = _load_bound_bytes(paths["progress"], binding.files["progress"], "progress")
    progress = _decode_json_lines(progress_bytes, "progress")

    session = payloads["session"]
    checkpoint = payloads["checkpoint"]
    result = payloads["result"]
    manifest = payloads["manifest"]
    _validate_common_binding(session, binding, "session")
    _validate_common_binding(checkpoint, binding, "checkpoint")
    _validate_common_binding(result, binding, "result")
    _require_equal(
        session.get("schema_version"),
        SOURCE_GENERATION_SESSION_SCHEMA_VERSION,
        "session_schema_mismatch",
    )
    _require_equal(
        checkpoint.get("schema_version"),
        SOURCE_GENERATION_CHECKPOINT_SCHEMA_VERSION,
        "checkpoint_schema_mismatch",
    )
    _require_equal(
        result.get("schema_version"),
        SOURCE_GENERATION_RESULT_SCHEMA_VERSION,
        "result_schema_mismatch",
    )
    manifest_schema_field, manifest_schema_version = _validate_manifest_schema(
        manifest,
        binding.module,
    )
    if "module" in manifest and manifest["module"] != binding.module:
        _fail("manifest_module_mismatch")

    _validate_session_boundary(session)
    _validate_finalized_checkpoint(checkpoint, binding.expected_episode_count)
    _validate_finalized_result(result, binding.expected_episode_count)
    seeds = _validate_progress(progress, binding)
    _validate_forbidden_states(manifest, "manifest")
    inventory = _validate_producer_inventory_metadata(
        result.get("artifact_inventory"),
        binding,
    )

    inventory_by_path = {item["path"]: item for item in inventory["files"]}
    for role, file_binding in binding.files.items():
        if role == "result":
            continue
        item = inventory_by_path.get(file_binding.relative_path)
        if item is None:
            _fail("bound_metadata_missing_from_inventory", f"{binding.module}:{role}")
        if item["sha256"] != file_binding.sha256:
            _fail("bound_metadata_inventory_sha256_mismatch", f"{binding.module}:{role}")

    return {
        "module": binding.module,
        "source_root": root.as_posix(),
        "status": "metadata_ready",
        "expected_episode_count": binding.expected_episode_count,
        "progress_record_count": len(progress),
        "unique_seed_count": len(seeds),
        "sequence_first": 0,
        "sequence_last": binding.expected_episode_count - 1,
        "source_git_commit": binding.source_git_commit,
        "generation_authorization_sha256": binding.generation_authorization_sha256,
        "module_request_sha256": binding.module_request_sha256,
        "manifest_schema_field": manifest_schema_field,
        "manifest_schema_version": manifest_schema_version,
        "artifact_inventory_file_count": inventory["file_count"],
        "artifact_inventory_total_size_bytes": inventory["total_size_bytes"],
        "artifact_inventory_tree_sha256": inventory["tree_sha256"],
        "artifact_inventory_verification_scope": (
            "producer_metadata_self_consistency_only"
        ),
        "artifact_inventory_producer_metadata_self_consistent": True,
        "artifact_inventory_payload_content_verified": False,
        "payload_file_open_count": 0,
        "full_payload_audit_performed": False,
        "permissions": dict(_NO_AUTHORITY),
    }


def _validate_manifest_schema(
    manifest: Mapping[str, Any],
    module: str,
) -> tuple[str, str]:
    """Read only the schema field explicitly assigned to one producer."""

    expected_field = _MANIFEST_SCHEMA_FIELD_BY_MODULE[module]
    present_fields = sorted(_MANIFEST_SCHEMA_FIELDS.intersection(manifest))
    if len(present_fields) > 1:
        _fail(
            "manifest_schema_fields_conflict",
            f"{module}:{','.join(present_fields)}",
        )
    if not present_fields:
        _fail("manifest_schema_missing", f"{module}:{expected_field}")
    actual_field = present_fields[0]
    if actual_field != expected_field:
        _fail(
            "manifest_schema_field_module_mismatch",
            f"{module}:expected={expected_field};actual={actual_field}",
        )
    value = manifest[actual_field]
    if not isinstance(value, str):
        _fail(
            "manifest_schema_type_invalid",
            f"{module}:{actual_field}:{type(value).__name__}",
        )
    if not value.strip():
        _fail("manifest_schema_empty", f"{module}:{actual_field}")
    if value != value.strip():
        _fail("manifest_schema_format_invalid", f"{module}:{actual_field}")
    return actual_field, value


def _validate_common_binding(
    payload: Mapping[str, Any],
    binding: GenerationSourceBinding,
    label: str,
) -> None:
    expected = {
        "module": binding.module,
        "source_git_commit": binding.source_git_commit,
        "authorization_sha256": binding.generation_authorization_sha256,
        "module_request_sha256": binding.module_request_sha256,
        "planned_episode_count": binding.expected_episode_count,
    }
    for name, value in expected.items():
        _require_equal(payload.get(name), value, f"{label}_{name}_mismatch")


def _validate_session_boundary(payload: Mapping[str, Any]) -> None:
    required = {
        "dataset_generation": True,
        "training": False,
        "future_held_out_model_consumption": False,
        "runtime": False,
        "control": False,
        "global_track_id_create": False,
        "global_track_id_write": False,
    }
    for name, expected in required.items():
        _require_equal(payload.get(name), expected, f"session_{name}_invalid")
    _validate_forbidden_states(payload, "session")


def _validate_finalized_checkpoint(payload: Mapping[str, Any], count: int) -> None:
    required = {
        "state": "finalized",
        "completed_episode_count": count,
        "remaining_episode_count": 0,
        "next_sequence": count,
        "dataset_generation": True,
        "training_started": False,
        "runtime_authority_granted": False,
        "control_authority_granted": False,
        "formal_seed_payload_read_count": 0,
        "future_held_out_model_consumption_count": 0,
    }
    for name, expected in required.items():
        _require_equal(payload.get(name), expected, f"checkpoint_{name}_invalid")
    _finite_nonnegative(payload.get("last_invocation_wall_s"), "checkpoint_wall_time")
    _validate_forbidden_states(payload, "checkpoint")


def _validate_finalized_result(payload: Mapping[str, Any], count: int) -> None:
    required = {
        "state": "finalized",
        "completed_episode_count": count,
        "remaining_episode_count": 0,
        "next_sequence": count,
        "dataset_generation": True,
        "training_started": False,
        "runtime_authority_granted": False,
        "control_authority_granted": False,
        "formal_seed_payload_read_count": 0,
        "future_held_out_model_consumption_count": 0,
    }
    for name, expected in required.items():
        _require_equal(payload.get(name), expected, f"result_{name}_invalid")
    _validate_forbidden_states(payload, "result")


def _validate_progress(
    rows: Sequence[Mapping[str, Any]],
    binding: GenerationSourceBinding,
) -> set[int]:
    if len(rows) != binding.expected_episode_count:
        _fail(
            "progress_record_count_mismatch",
            f"{binding.module}:{len(rows)}/{binding.expected_episode_count}",
        )
    seeds: set[int] = set()
    for expected_sequence, row in enumerate(rows):
        _require_equal(
            row.get("schema_version"),
            SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION,
            "progress_schema_mismatch",
        )
        _validate_progress_binding(row, binding)
        _require_equal(row.get("sequence"), expected_sequence, "progress_sequence_mismatch")
        seed = row.get("seed")
        if type(seed) is not int:
            _fail("progress_seed_invalid", str(seed))
        if seed in seeds:
            _fail("progress_seed_duplicate", f"{binding.module}:{seed}")
        seeds.add(seed)
        if not isinstance(row.get("episode_id"), str) or not row["episode_id"]:
            _fail("progress_episode_id_invalid", f"{binding.module}:{expected_sequence}")
        required = {
            "finite_state": True,
            "online_truth_use_count": 0,
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
            "training_started": False,
            "runtime_authority_granted": False,
            "control_authority_granted": False,
        }
        for name, expected in required.items():
            _require_equal(row.get(name), expected, f"progress_{name}_invalid")
        _validate_forbidden_states(row, f"progress[{expected_sequence}]")
    return seeds


def _validate_progress_binding(
    payload: Mapping[str, Any],
    binding: GenerationSourceBinding,
) -> None:
    expected = {
        "module": binding.module,
        "source_git_commit": binding.source_git_commit,
        "authorization_sha256": binding.generation_authorization_sha256,
        "module_request_sha256": binding.module_request_sha256,
    }
    for name, value in expected.items():
        _require_equal(payload.get(name), value, f"progress_{name}_mismatch")


def _validate_producer_inventory_metadata(
    value: Any,
    binding: GenerationSourceBinding,
) -> dict[str, Any]:
    """Validate producer claims without resolving or opening inventory paths."""

    inventory = _exact_mapping(
        value,
        {"file_count", "total_size_bytes", "files", "tree_sha256"},
        "artifact_inventory",
    )
    files = inventory["files"]
    if not isinstance(files, list):
        _fail("artifact_inventory_files_invalid")
    records: list[dict[str, Any]] = []
    previous = ""
    total_size = 0
    for index, raw in enumerate(files):
        item = _exact_mapping(raw, {"path", "size_bytes", "sha256"}, "inventory_file")
        path = _safe_relative(item["path"], f"inventory_path[{index}]")
        if path <= previous:
            _fail("artifact_inventory_unsorted_or_duplicate", path)
        previous = path
        size = _nonnegative_int(item["size_bytes"], "inventory_size")
        digest = _sha(item["sha256"], "inventory_file_sha256")
        records.append({"path": path, "size_bytes": size, "sha256": digest})
        total_size += size
    if inventory["file_count"] != len(records):
        _fail("artifact_inventory_file_count_mismatch")
    if inventory["total_size_bytes"] != total_size:
        _fail("artifact_inventory_total_size_mismatch")
    tree_sha = _sha(inventory["tree_sha256"], "artifact_inventory_tree_sha256")
    if tree_sha != _canonical_sha256({"files": records}):
        _fail("artifact_inventory_tree_sha256_mismatch")
    normalized = {
        "file_count": len(records),
        "total_size_bytes": total_size,
        "files": records,
        "tree_sha256": tree_sha,
    }
    if _canonical_sha256(normalized) != binding.artifact_inventory_sha256:
        _fail("artifact_inventory_content_sha256_mismatch", binding.module)
    return normalized


def _validate_forbidden_states(value: Any, path: str) -> None:
    truth_counter_names = {
        "online_truth_use_count",
        "online_truth_identity_use_count",
        "formal_seed_payload_read_count",
    }
    id_counter_names = {
        "global_track_id_created_count",
        "global_track_id_rewritten_count",
        "global_track_id_create_count",
        "global_track_id_write_count",
    }
    forbidden_true_names = {
        "training",
        "training_started",
        "validation_consumption",
        "test_consumption",
        "future_held_out_consumption",
        "future_held_out_model_consumption",
        "runtime",
        "runtime_authority_granted",
        "control",
        "control_authority_granted",
        "global_track_id_create",
        "global_track_id_write",
        "assignment_authority",
        "degradation_authority",
        "camera_command_authority",
    }
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            child_path = f"{path}.{raw_key}"
            if key in truth_counter_names | id_counter_names and child != 0:
                _fail("forbidden_counter_nonzero", child_path)
            if key in forbidden_true_names and child is not False:
                _fail("forbidden_authority_or_consumption", child_path)
            if "authority" in key and isinstance(child, bool) and child:
                _fail("authority_true", child_path)
            _validate_forbidden_states(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_forbidden_states(child, f"{path}[{index}]")


def _resolve_source_root(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    _reject_symlink_components(absolute, "source_root")
    if not absolute.is_dir():
        _fail("source_root_invalid", str(absolute))
    return absolute


def _resolve_bound_file(root: Path, binding: MetadataFileBinding, role: str) -> Path:
    path = root.joinpath(*PurePosixPath(binding.relative_path).parts)
    _reject_symlink_components(path, role)
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        _fail(f"{role}_file_missing", str(exc))
    if not stat.S_ISREG(info.st_mode):
        _fail(f"{role}_file_not_regular", binding.relative_path)
    return path


def _load_bound_json(
    path: Path,
    binding: MetadataFileBinding,
    role: str,
) -> dict[str, Any]:
    return _decode_json_object(_load_bound_bytes(path, binding, role), role)


def _load_bound_bytes(path: Path, binding: MetadataFileBinding, role: str) -> bytes:
    content = path.read_bytes()
    if sha256(content).hexdigest() != binding.sha256:
        _fail(f"{role}_file_sha256_mismatch", binding.relative_path)
    return content


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


def _decode_json_lines(content: bytes, label: str) -> list[dict[str, Any]]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeError as exc:
        _fail(f"{label}_utf8_invalid", str(exc))
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            _fail(f"{label}_blank_line", str(line_number))
        rows.append(_decode_json_object(line.encode("utf-8"), f"{label}_{line_number}"))
    return rows


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path.expanduser().absolute()
    for component in (absolute, *absolute.parents):
        if component.exists() and component.is_symlink():
            _fail(f"{label}_symlink_forbidden", str(component))


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail(f"{label}_invalid", repr(value))
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{label}_invalid", value)
    canonical = path.as_posix()
    if canonical != value:
        _fail(f"{label}_not_canonical", value)
    return canonical


def _exact_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        actual = set(value) if isinstance(value, Mapping) else set()
        _fail(f"{label}_fields_mismatch", ",".join(sorted(fields ^ actual)))
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


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        _fail(f"{label}_invalid", str(value))
    return value


def _commit(value: Any) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        _fail("source_git_commit_invalid", str(value))
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        _fail(f"{label}_invalid", str(value))
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        _fail(f"{label}_invalid", str(value))
    return value


def _finite_nonnegative(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        _fail(f"{label}_invalid", str(value))
    return float(value)


def _require_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        _fail(code, f"expected={expected!r};actual={actual!r}")


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


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


def _render_markdown(result: Mapping[str, Any]) -> str:
    passed = result.get("metadata_preflight_passed") is True
    lines = [
        "# D3/D4/D5 来源生成元数据预检",
        "",
        f"- 状态：`{result.get('status', 'failed_closed')}`",
        f"- 元数据预检：`{'通过' if passed else '未通过'}`",
        "- 正式来源载荷读取：`否`",
        "- 完整载荷审计：`未执行`",
        "- artifact inventory：`仅生产者元数据自洽；payload 内容未核验`",
        "- 训练、验证、测试、未来保留集、推理、影子、辅助、晋级、近端策略优化、",
        "  分配、降级、相机命令、运行、生产和控制权限：`全部关闭`",
        "",
        "## 模块结果",
        "",
        "| 模块 | 状态 | episode | seed | inventory 文件 | payload 打开数 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
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
                    str(item.get("progress_record_count", 0)),
                    str(item.get("unique_seed_count", 0)),
                    str(item.get("artifact_inventory_file_count", 0)),
                    str(item.get("payload_file_open_count", 0)),
                ]
            )
            + " |"
        )
    blockers = result.get("blocker_codes", [])
    lines.extend(["", "## 阻断项", ""])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- 无元数据阻断项。")
    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "本预检只确认显式绑定的生成元数据满足后续申请 D6 来源审计授权的条件。",
            "它不复算数据集文件摘要，不检查 episode/sample 内容，也不授予训练、验证、",
            "运行、分配、降级、相机或控制权限。",
            "",
        ]
    )
    return "\n".join(lines)


def _fail(code: str, detail: str = "") -> None:
    raise LearningSourceGenerationPreflightError(code, detail)


__all__ = [
    "EXPECTED_EPISODE_COUNTS",
    "GenerationSourceBinding",
    "LEARNING_SOURCE_GENERATION_PREFLIGHT_INPUT_SCHEMA_VERSION",
    "LEARNING_SOURCE_GENERATION_PREFLIGHT_SCHEMA_VERSION",
    "LearningSourceGenerationPreflightError",
    "LearningSourceGenerationPreflightInputs",
    "MetadataFileBinding",
    "evaluate_learning_source_generation_preflight",
    "load_learning_source_generation_preflight_inputs",
    "write_learning_source_generation_preflight_report",
]
