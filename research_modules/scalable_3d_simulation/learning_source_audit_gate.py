"""Main-owned contracts between source generation and a future D6 audit.

The request builder reads only explicitly named generation metadata.  It does
not walk a dataset directory or open episode/sample payloads.  The separate
authorization contract can permit a read-only integrity audit, but never
training, model inference, runtime decisions, or control.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping


SOURCE_PREFLIGHT_INPUT_SCHEMA = "d6.learning-source-generation-preflight-input.v1"
SOURCE_PREFLIGHT_RESULT_SCHEMA = "d6.learning-source-generation-preflight.v1"
SOURCE_AUDIT_AUTHORIZATION_SCHEMA = "scalable3d-d6-source-audit-authorization-v1"
SOURCE_AUDIT_CONFIRMATION = "AUTHORIZE D6 SOURCE AUDIT OF D3 D4 D5 ONLY"

EXPECTED_EPISODE_COUNTS = {"D3": 300, "D4": 324, "D5": 104}
DEFAULT_MANIFEST_PATHS = {
    "D3": "dataset/dataset_manifest.json",
    "D4": "dataset/manifest.json",
    "D5": "source_manifest.json",
}
_FIXED_METADATA_PATHS = {
    "session": "generation_session.json",
    "checkpoint": "generation_checkpoint.json",
    "result": "generation_result.json",
    "progress": "episode_progress.jsonl",
}
_ALLOWED_MANIFEST_NAMES = frozenset(
    {"dataset_manifest.json", "manifest.json", "source_manifest.json"}
)
_MANIFEST_SCHEMA_FIELD_BY_MODULE = {
    "D3": "schema_version",
    "D4": "schema",
    "D5": "schema_version",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")

_AUDIT_PERMISSION_FIELDS = (
    "source_metadata_read",
    "source_payload_integrity_read",
    "source_integrity_audit",
    "training",
    "optimizer",
    "checkpoint_selection",
    "threshold_adjustment",
    "model_inference",
    "validation_model_consumption",
    "test_model_consumption",
    "future_held_out_model_consumption",
    "shadow",
    "assist",
    "assignment",
    "degradation",
    "coalition",
    "camera_command",
    "runtime",
    "physical",
    "production",
    "control",
    "global_track_id_create",
    "global_track_id_write",
)


class LearningSourceAuditGateError(RuntimeError):
    """Stable failure for an unsafe or stale preflight/audit contract."""


def audit_only_permissions() -> dict[str, bool]:
    """Return the only permissions accepted by the D6 source-audit gate."""

    enabled = {
        "source_metadata_read",
        "source_payload_integrity_read",
        "source_integrity_audit",
    }
    return {name: name in enabled for name in _AUDIT_PERMISSION_FIELDS}


def build_learning_source_preflight_input(
    *,
    contract_id: str,
    source_roots: Mapping[str, str | Path],
    manifest_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Bind D3/D4/D5 metadata without inspecting a dataset payload."""

    identifier = _identifier(contract_id, "contract_id")
    if set(source_roots) != set(EXPECTED_EPISODE_COUNTS):
        raise LearningSourceAuditGateError("source_roots_must_be_exactly_d3_d4_d5")
    selected_manifests = dict(DEFAULT_MANIFEST_PATHS)
    if manifest_paths is not None:
        if set(manifest_paths) != set(EXPECTED_EPISODE_COUNTS):
            raise LearningSourceAuditGateError(
                "manifest_paths_must_be_exactly_d3_d4_d5"
            )
        selected_manifests.update(manifest_paths)

    sources = [
        _build_source_binding(
            module,
            source_roots[module],
            selected_manifests[module],
        )
        for module in sorted(EXPECTED_EPISODE_COUNTS)
    ]
    return {
        "schema_version": SOURCE_PREFLIGHT_INPUT_SCHEMA,
        "contract_id": identifier,
        "sources": sources,
    }


def write_learning_source_preflight_input(
    path: str | Path,
    payload: Mapping[str, Any],
) -> tuple[Path, str]:
    """Atomically write a new SHA-bound preflight input without overwrite."""

    _validate_preflight_input_shape(payload)
    destination = Path(path).expanduser().absolute()
    _reject_symlink_components(destination, "preflight_input_output")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"preflight input already exists: {destination}")
    for source in payload["sources"]:
        root = Path(source["source_root"]).absolute()
        if _is_relative_to(destination, root):
            raise LearningSourceAuditGateError("preflight_input_inside_source_root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(payload)
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"preflight input temporary exists: {temporary}")
    temporary.write_bytes(content)
    temporary.replace(destination)
    return destination, sha256(content).hexdigest()


def build_learning_source_audit_authorization(
    preflight_result: Mapping[str, Any],
    *,
    authorization_id: str,
    approver_id: str,
    approval_reason: str,
    confirmation: str,
    preflight_report_file_sha256: str,
    approved_at_utc: datetime | str | None = None,
) -> dict[str, Any]:
    """Build an audit-only approval; this function performs no audit."""

    if confirmation != SOURCE_AUDIT_CONFIRMATION:
        raise LearningSourceAuditGateError("source_audit_confirmation_mismatch")
    _validate_ready_preflight(preflight_result)
    approver = str(approver_id).strip()
    reason = str(approval_reason).strip()
    if not approver:
        raise LearningSourceAuditGateError("approver_id_missing")
    if not reason:
        raise LearningSourceAuditGateError("approval_reason_missing")
    source_summaries = []
    for module in sorted(EXPECTED_EPISODE_COUNTS):
        item = preflight_result["sources"][module]
        source_summaries.append(
            {
                "module": module,
                "source_root": str(item["source_root"]),
                "source_git_commit": _commit(item["source_git_commit"]),
                "generation_authorization_sha256": _sha256_value(
                    item["generation_authorization_sha256"],
                    "generation_authorization_sha256",
                ),
                "module_request_sha256": _sha256_value(
                    item["module_request_sha256"], "module_request_sha256"
                ),
                "artifact_inventory_tree_sha256": _sha256_value(
                    item["artifact_inventory_tree_sha256"],
                    "artifact_inventory_tree_sha256",
                ),
                "manifest_schema_field": str(item["manifest_schema_field"]),
                "manifest_schema_version": str(item["manifest_schema_version"]),
            }
        )
    return {
        "schema_version": SOURCE_AUDIT_AUTHORIZATION_SCHEMA,
        "authorization_id": _identifier(authorization_id, "authorization_id"),
        "status": "approved_for_source_integrity_audit_only",
        "confirmation": SOURCE_AUDIT_CONFIRMATION,
        "preflight_input_contract_sha256": _sha256_value(
            preflight_result["input_contract_sha256"],
            "preflight_input_contract_sha256",
        ),
        "preflight_result_sha256": canonical_json_sha256(preflight_result),
        "preflight_report_file_sha256": _sha256_value(
            preflight_report_file_sha256, "preflight_report_file_sha256"
        ),
        "sources": source_summaries,
        "permissions": audit_only_permissions(),
        "approver_id": approver,
        "approval_reason": reason,
        "approved_at_utc": _format_timestamp(approved_at_utc),
    }


def write_learning_source_audit_authorization(
    path: str | Path,
    payload: Mapping[str, Any],
) -> tuple[Path, str]:
    """Validate and atomically write a non-overwritable audit authorization."""

    _validate_audit_authorization(payload)
    destination = Path(path).expanduser().absolute()
    _reject_symlink_components(destination, "audit_authorization_output")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"audit authorization already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(payload)
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"audit authorization temporary exists: {temporary}")
    temporary.write_bytes(content)
    temporary.replace(destination)
    return destination, sha256(content).hexdigest()


def load_learning_source_audit_authorization(
    path: str | Path,
    *,
    expected_authorization_sha256: str,
    expected_input_contract_sha256: str,
    expected_preflight_result_sha256: str,
) -> dict[str, Any]:
    """Load an audit-only grant and recheck all immutable bindings."""

    candidate = Path(path).expanduser().absolute()
    _reject_symlink_components(candidate, "audit_authorization")
    if not candidate.is_file():
        raise LearningSourceAuditGateError("audit_authorization_missing")
    content = _read_bound_bytes(candidate)
    if sha256(content).hexdigest() != _sha256_value(
        expected_authorization_sha256, "expected_authorization_sha256"
    ):
        raise LearningSourceAuditGateError("audit_authorization_sha256_mismatch")
    payload = _decode_json_object(content, "audit_authorization")
    _validate_audit_authorization(payload)
    if payload["preflight_input_contract_sha256"] != _sha256_value(
        expected_input_contract_sha256, "expected_input_contract_sha256"
    ):
        raise LearningSourceAuditGateError("audit_input_contract_binding_mismatch")
    if payload["preflight_result_sha256"] != _sha256_value(
        expected_preflight_result_sha256, "expected_preflight_result_sha256"
    ):
        raise LearningSourceAuditGateError("audit_preflight_binding_mismatch")
    return payload


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
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


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def _build_source_binding(
    module: str,
    source_root: str | Path,
    manifest_relative_path: str,
) -> dict[str, Any]:
    root = Path(source_root).expanduser().absolute()
    _reject_symlink_components(root, f"{module}_source_root")
    if not root.is_dir():
        raise LearningSourceAuditGateError(f"{module.lower()}_source_root_invalid")
    manifest = _safe_relative(manifest_relative_path, f"{module}_manifest_path")
    if PurePosixPath(manifest).name not in _ALLOWED_MANIFEST_NAMES:
        raise LearningSourceAuditGateError(f"{module.lower()}_manifest_name_invalid")
    relative_paths = {**_FIXED_METADATA_PATHS, "manifest": manifest}
    bound_files: dict[str, dict[str, str]] = {}
    file_bytes: dict[str, bytes] = {}
    for role, relative in relative_paths.items():
        path = root.joinpath(*PurePosixPath(relative).parts)
        _reject_symlink_components(path, f"{module}_{role}")
        try:
            info = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise LearningSourceAuditGateError(
                f"{module.lower()}_{role}_missing"
            ) from exc
        if not stat.S_ISREG(info.st_mode):
            raise LearningSourceAuditGateError(
                f"{module.lower()}_{role}_not_regular"
            )
        content = _read_bound_bytes(path)
        file_bytes[role] = content
        bound_files[role] = {
            "relative_path": relative,
            "sha256": sha256(content).hexdigest(),
        }

    result = _decode_json_object(file_bytes["result"], f"{module}_result")
    if result.get("module") != module:
        raise LearningSourceAuditGateError(f"{module.lower()}_result_module_mismatch")
    expected_count = EXPECTED_EPISODE_COUNTS[module]
    if result.get("planned_episode_count") != expected_count:
        raise LearningSourceAuditGateError(f"{module.lower()}_episode_count_mismatch")
    inventory = result.get("artifact_inventory")
    if not isinstance(inventory, Mapping):
        raise LearningSourceAuditGateError(
            f"{module.lower()}_artifact_inventory_missing"
        )
    return {
        "module": module,
        "source_root": root.as_posix(),
        "expected_episode_count": expected_count,
        "source_git_commit": _commit(result.get("source_git_commit")),
        "generation_authorization_sha256": _sha256_value(
            result.get("authorization_sha256"), "generation_authorization_sha256"
        ),
        "module_request_sha256": _sha256_value(
            result.get("module_request_sha256"), "module_request_sha256"
        ),
        "files": bound_files,
        "artifact_inventory_sha256": canonical_json_sha256(inventory),
    }


def _validate_preflight_input_shape(payload: Mapping[str, Any]) -> None:
    if set(payload) != {"schema_version", "contract_id", "sources"}:
        raise LearningSourceAuditGateError("preflight_input_fields_invalid")
    if payload["schema_version"] != SOURCE_PREFLIGHT_INPUT_SCHEMA:
        raise LearningSourceAuditGateError("preflight_input_schema_invalid")
    _identifier(payload["contract_id"], "contract_id")
    sources = payload["sources"]
    if not isinstance(sources, list) or [item.get("module") for item in sources] != [
        "D3",
        "D4",
        "D5",
    ]:
        raise LearningSourceAuditGateError("preflight_input_sources_invalid")


def _validate_ready_preflight(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version": SOURCE_PREFLIGHT_RESULT_SCHEMA,
        "status": "ready_for_explicit_d6_source_audit_authorization",
        "metadata_preflight_passed": True,
        "full_payload_audit_performed": False,
        "formal_source_data_read": False,
        "d6_control_participation": False,
    }
    for name, expected in required.items():
        if payload.get(name) != expected:
            raise LearningSourceAuditGateError(f"preflight_{name}_invalid")
    permissions = payload.get("permissions")
    if not isinstance(permissions, Mapping) or any(
        value is not False for value in permissions.values()
    ):
        raise LearningSourceAuditGateError("preflight_permissions_not_false")
    sources = payload.get("sources")
    if not isinstance(sources, Mapping) or set(sources) != set(EXPECTED_EPISODE_COUNTS):
        raise LearningSourceAuditGateError("preflight_source_inventory_invalid")
    for module, count in EXPECTED_EPISODE_COUNTS.items():
        item = sources[module]
        if not isinstance(item, Mapping):
            raise LearningSourceAuditGateError(f"{module.lower()}_preflight_invalid")
        expected = {
            "status": "metadata_ready",
            "expected_episode_count": count,
            "progress_record_count": count,
            "unique_seed_count": count,
            "payload_file_open_count": 0,
            "full_payload_audit_performed": False,
            "artifact_inventory_verification_scope": (
                "producer_metadata_self_consistency_only"
            ),
            "artifact_inventory_producer_metadata_self_consistent": True,
            "artifact_inventory_payload_content_verified": False,
        }
        for name, value in expected.items():
            if item.get(name) != value:
                raise LearningSourceAuditGateError(
                    f"{module.lower()}_preflight_{name}_invalid"
                )
        if item.get("manifest_schema_field") != _MANIFEST_SCHEMA_FIELD_BY_MODULE[module]:
            raise LearningSourceAuditGateError(
                f"{module.lower()}_preflight_manifest_schema_field_invalid"
            )
        schema_value = item.get("manifest_schema_version")
        if (
            not isinstance(schema_value, str)
            or not schema_value
            or schema_value != schema_value.strip()
        ):
            raise LearningSourceAuditGateError(
                f"{module.lower()}_preflight_manifest_schema_version_invalid"
            )


def _validate_audit_authorization(payload: Mapping[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "authorization_id",
        "status",
        "confirmation",
        "preflight_input_contract_sha256",
        "preflight_result_sha256",
        "preflight_report_file_sha256",
        "sources",
        "permissions",
        "approver_id",
        "approval_reason",
        "approved_at_utc",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected_fields:
        raise LearningSourceAuditGateError("audit_authorization_fields_invalid")
    if payload["schema_version"] != SOURCE_AUDIT_AUTHORIZATION_SCHEMA:
        raise LearningSourceAuditGateError("audit_authorization_schema_invalid")
    if payload["status"] != "approved_for_source_integrity_audit_only":
        raise LearningSourceAuditGateError("audit_authorization_status_invalid")
    if payload["confirmation"] != SOURCE_AUDIT_CONFIRMATION:
        raise LearningSourceAuditGateError("audit_authorization_confirmation_invalid")
    _identifier(payload["authorization_id"], "authorization_id")
    for name in (
        "preflight_input_contract_sha256",
        "preflight_result_sha256",
        "preflight_report_file_sha256",
    ):
        _sha256_value(payload[name], name)
    if payload["permissions"] != audit_only_permissions():
        raise LearningSourceAuditGateError("audit_authorization_permission_escalation")
    sources = payload["sources"]
    if not isinstance(sources, list) or [item.get("module") for item in sources] != [
        "D3",
        "D4",
        "D5",
    ]:
        raise LearningSourceAuditGateError("audit_authorization_sources_invalid")
    source_fields = {
        "module",
        "source_root",
        "source_git_commit",
        "generation_authorization_sha256",
        "module_request_sha256",
        "artifact_inventory_tree_sha256",
        "manifest_schema_field",
        "manifest_schema_version",
    }
    for item in sources:
        if not isinstance(item, Mapping) or set(item) != source_fields:
            raise LearningSourceAuditGateError(
                "audit_authorization_source_fields_invalid"
            )
        root = item["source_root"]
        if not isinstance(root, str) or not Path(root).is_absolute():
            raise LearningSourceAuditGateError(
                "audit_authorization_source_root_invalid"
            )
        _commit(item["source_git_commit"])
        for name in (
            "generation_authorization_sha256",
            "module_request_sha256",
            "artifact_inventory_tree_sha256",
        ):
            _sha256_value(item[name], name)
        module = item["module"]
        if item["manifest_schema_field"] != _MANIFEST_SCHEMA_FIELD_BY_MODULE[module]:
            raise LearningSourceAuditGateError(
                "audit_authorization_manifest_schema_field_invalid"
            )
        schema_value = item["manifest_schema_version"]
        if (
            not isinstance(schema_value, str)
            or not schema_value
            or schema_value != schema_value.strip()
        ):
            raise LearningSourceAuditGateError(
                "audit_authorization_manifest_schema_version_invalid"
            )
    if not str(payload["approver_id"]).strip():
        raise LearningSourceAuditGateError("approver_id_missing")
    if not str(payload["approval_reason"]).strip():
        raise LearningSourceAuditGateError("approval_reason_missing")
    _format_timestamp(payload["approved_at_utc"])


def _read_bound_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _decode_json_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise LearningSourceAuditGateError(f"{label}_json_invalid") from exc
    if not isinstance(value, dict):
        raise LearningSourceAuditGateError(f"{label}_json_object_required")
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LearningSourceAuditGateError(f"{label}_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise LearningSourceAuditGateError(f"{label}_invalid")
    if path.as_posix() != value:
        raise LearningSourceAuditGateError(f"{label}_not_canonical")
    return value


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path.expanduser().absolute()
    for component in (absolute, *absolute.parents):
        if component.exists() and component.is_symlink():
            raise LearningSourceAuditGateError(f"{label}_symlink_forbidden")


def _identifier(value: Any, label: str) -> str:
    text = str(value)
    if _IDENTIFIER.fullmatch(text) is None:
        raise LearningSourceAuditGateError(f"{label}_invalid")
    return text


def _sha256_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise LearningSourceAuditGateError(f"{label}_invalid")
    return value


def _commit(value: Any) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise LearningSourceAuditGateError("source_git_commit_invalid")
    return value


def _format_timestamp(value: datetime | str | None) -> str:
    if value is None:
        stamp = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LearningSourceAuditGateError("approved_at_utc_invalid") from exc
    else:
        raise LearningSourceAuditGateError("approved_at_utc_invalid")
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise LearningSourceAuditGateError("approved_at_utc_timezone_missing")
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "DEFAULT_MANIFEST_PATHS",
    "EXPECTED_EPISODE_COUNTS",
    "LearningSourceAuditGateError",
    "SOURCE_AUDIT_AUTHORIZATION_SCHEMA",
    "SOURCE_AUDIT_CONFIRMATION",
    "SOURCE_PREFLIGHT_INPUT_SCHEMA",
    "audit_only_permissions",
    "build_learning_source_audit_authorization",
    "build_learning_source_preflight_input",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "load_learning_source_audit_authorization",
    "write_learning_source_audit_authorization",
    "write_learning_source_preflight_input",
]
