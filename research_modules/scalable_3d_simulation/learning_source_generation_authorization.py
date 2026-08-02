"""Fail-closed main authorization for scalable learning-source generation.

Module readiness only states that a frozen request can be generated.  This
contract is the separate main-owned decision that permits writing source data
from one exact clean commit.  It never grants training or runtime authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .learning_source_preflight import (
    LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION,
    evaluate_learning_source_preflight,
)


SOURCE_GENERATION_AUTHORIZATION_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-authorization-v1"
)
SOURCE_GENERATION_CONFIRMATION = (
    "AUTHORIZE D3 D4 D5 SOURCE GENERATION ONLY"
)
SOURCE_GENERATION_MODULES = ("D3", "D4", "D5")
SOURCE_GENERATION_PERMISSION_FIELDS = (
    "dataset_generation",
    "training",
    "validation_consumption",
    "test_consumption",
    "future_held_out_consumption",
    "optimizer",
    "checkpoint_selection",
    "threshold_adjustment",
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

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


class LearningSourceGenerationAuthorizationError(RuntimeError):
    """A source-generation authorization is missing, stale, or overbroad."""


@dataclass(frozen=True)
class LearningSourceGenerationAuthorization:
    """Validated generation-only permission for one immutable source tree."""

    authorization_id: str
    authorization_file_sha256: str
    source_git_commit: str
    preflight_sha256: str
    registry_file_sha256: str
    module_request_sha256: Mapping[str, str]
    planned_episode_count: Mapping[str, int]
    permissions: Mapping[str, bool]
    approver_id: str
    approval_reason: str
    approved_at_utc: str

    def __post_init__(self) -> None:
        _identifier(self.authorization_id, "authorization_id")
        _sha256(self.authorization_file_sha256, "authorization_file_sha256")
        _commit(self.source_git_commit)
        _sha256(self.preflight_sha256, "preflight_sha256")
        _sha256(self.registry_file_sha256, "registry_file_sha256")
        request_hashes = _module_hashes(self.module_request_sha256)
        episode_counts = _episode_counts(self.planned_episode_count)
        permissions = _permissions(self.permissions)
        if not isinstance(self.approver_id, str) or not self.approver_id.strip():
            raise LearningSourceGenerationAuthorizationError("approver_id_missing")
        if not isinstance(self.approval_reason, str) or not self.approval_reason.strip():
            raise LearningSourceGenerationAuthorizationError(
                "approval_reason_missing"
            )
        _timestamp(self.approved_at_utc, "approved_at_utc")
        object.__setattr__(
            self, "module_request_sha256", MappingProxyType(request_hashes)
        )
        object.__setattr__(
            self, "planned_episode_count", MappingProxyType(episode_counts)
        )
        object.__setattr__(self, "permissions", MappingProxyType(permissions))

    def assert_module(self, module: str) -> None:
        selected = str(module).strip().upper()
        if selected not in SOURCE_GENERATION_MODULES:
            raise LearningSourceGenerationAuthorizationError(
                "generation_module_not_authorized"
            )
        if not self.permissions["dataset_generation"]:
            raise LearningSourceGenerationAuthorizationError(
                "dataset_generation_not_granted"
            )


def generation_only_permissions() -> dict[str, bool]:
    """Return the only permission map accepted by this contract."""

    return {
        name: name == "dataset_generation"
        for name in SOURCE_GENERATION_PERMISSION_FIELDS
    }


def build_learning_source_generation_authorization(
    preflight: Mapping[str, Any],
    *,
    authorization_id: str,
    approver_id: str,
    approval_reason: str,
    confirmation: str,
    approved_at_utc: datetime | str | None = None,
) -> dict[str, Any]:
    """Build one self-contained approval from a ready, clean preflight."""

    if confirmation != SOURCE_GENERATION_CONFIRMATION:
        raise LearningSourceGenerationAuthorizationError(
            "source_generation_confirmation_mismatch"
        )
    auth_id = _identifier(authorization_id, "authorization_id")
    source_commit, registry_sha, request_hashes, counts = _preflight_binding(
        preflight
    )
    approver = str(approver_id).strip()
    reason = str(approval_reason).strip()
    if not approver:
        raise LearningSourceGenerationAuthorizationError("approver_id_missing")
    if not reason:
        raise LearningSourceGenerationAuthorizationError(
            "approval_reason_missing"
        )
    approved = _format_timestamp(approved_at_utc)
    payload = {
        "schema_version": SOURCE_GENERATION_AUTHORIZATION_SCHEMA_VERSION,
        "authorization_id": auth_id,
        "source_git_commit": source_commit,
        "preflight_sha256": canonical_json_sha256(preflight),
        "registry_file_sha256": registry_sha,
        "module_request_sha256": request_hashes,
        "planned_episode_count": counts,
        "total_planned_episode_count": sum(counts.values()),
        "permissions": generation_only_permissions(),
        "approver_id": approver,
        "approval_reason": reason,
        "approved_at_utc": approved,
        "formal_seed_payload_read": False,
        "formal_shards_10_19_run": False,
        "training_started": False,
        "runtime_authority_granted": False,
    }
    return payload


def write_learning_source_generation_authorization(
    path: str | Path,
    payload: Mapping[str, Any],
) -> tuple[Path, str]:
    """Validate and atomically write a new authorization without overwrite."""

    _authorization_from_payload(payload, authorization_file_sha256="0" * 64)
    destination = Path(path).expanduser().resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"authorization already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(payload)
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"authorization temporary exists: {temporary}")
    temporary.write_bytes(content)
    temporary.replace(destination)
    return destination, sha256(content).hexdigest()


def load_learning_source_generation_authorization(
    path: str | Path,
    *,
    repository_root: str | Path,
    expected_authorization_sha256: str,
) -> LearningSourceGenerationAuthorization:
    """Load an approval and bind it to the current clean preflight."""

    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise LearningSourceGenerationAuthorizationError(
            "authorization_file_symlink_forbidden"
        )
    source = candidate.resolve()
    try:
        content = source.read_bytes()
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_unique_pairs
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearningSourceGenerationAuthorizationError(
            "authorization_file_invalid"
        ) from exc
    actual_sha = sha256(content).hexdigest()
    if actual_sha != _sha256(
        expected_authorization_sha256, "expected_authorization_sha256"
    ):
        raise LearningSourceGenerationAuthorizationError(
            "authorization_file_sha256_mismatch"
        )
    authorization = _authorization_from_payload(
        payload, authorization_file_sha256=actual_sha
    )
    root = Path(repository_root).expanduser().resolve()
    commit, dirty = _repository_state(root)
    if dirty:
        raise LearningSourceGenerationAuthorizationError(
            "generation_repository_dirty"
        )
    if commit != authorization.source_git_commit:
        raise LearningSourceGenerationAuthorizationError(
            "generation_source_commit_mismatch"
        )
    preflight = evaluate_learning_source_preflight(repository_root=root)
    source_commit, registry_sha, request_hashes, counts = _preflight_binding(
        preflight
    )
    if source_commit != authorization.source_git_commit:
        raise LearningSourceGenerationAuthorizationError(
            "authorization_preflight_source_mismatch"
        )
    if canonical_json_sha256(preflight) != authorization.preflight_sha256:
        raise LearningSourceGenerationAuthorizationError(
            "authorization_preflight_sha256_mismatch"
        )
    if registry_sha != authorization.registry_file_sha256:
        raise LearningSourceGenerationAuthorizationError(
            "authorization_registry_sha256_mismatch"
        )
    if request_hashes != dict(authorization.module_request_sha256):
        raise LearningSourceGenerationAuthorizationError(
            "authorization_module_request_sha256_mismatch"
        )
    if counts != dict(authorization.planned_episode_count):
        raise LearningSourceGenerationAuthorizationError(
            "authorization_episode_inventory_mismatch"
        )
    return authorization


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


def _preflight_binding(
    preflight: Mapping[str, Any],
) -> tuple[str, str, dict[str, str], dict[str, int]]:
    if preflight.get("schema_version") != LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION:
        raise LearningSourceGenerationAuthorizationError(
            "preflight_schema_mismatch"
        )
    required_true = (
        "all_module_plans_ready",
        "all_producer_adapters_complete",
        "all_generation_requests_ready",
        "source_worktree_clean",
        "execution_plan_ready",
    )
    if any(preflight.get(name) is not True for name in required_true):
        raise LearningSourceGenerationAuthorizationError(
            "preflight_not_ready_for_authorization"
        )
    if (
        preflight.get("execution_authorized") is not False
        or preflight.get("generation_started") is not False
        or preflight.get("training_started") is not False
        or preflight.get("formal_seed_payload_read") is not False
        or preflight.get("formal_shards_10_19_run") is not False
    ):
        raise LearningSourceGenerationAuthorizationError(
            "preflight_authority_boundary_invalid"
        )
    if preflight.get("generation_commands") not in (None, []):
        raise LearningSourceGenerationAuthorizationError(
            "preflight_generation_commands_not_empty"
        )
    preflight_permissions = preflight.get("permissions")
    if not isinstance(preflight_permissions, Mapping) or any(
        value is not False for value in preflight_permissions.values()
    ):
        raise LearningSourceGenerationAuthorizationError(
            "preflight_permissions_not_false"
        )
    if preflight.get("status") != "ready_for_explicit_main_execution_authorization":
        raise LearningSourceGenerationAuthorizationError(
            "preflight_status_not_authorizable"
        )
    source = preflight.get("source_state")
    registry = preflight.get("registry")
    modules = preflight.get("modules")
    if not isinstance(source, Mapping) or not isinstance(registry, Mapping):
        raise LearningSourceGenerationAuthorizationError(
            "preflight_binding_missing"
        )
    if not isinstance(modules, Mapping) or set(modules) != set(
        SOURCE_GENERATION_MODULES
    ):
        raise LearningSourceGenerationAuthorizationError(
            "preflight_module_inventory_invalid"
        )
    source_commit = _commit(str(source.get("git_commit", "")))
    registry_sha = _sha256(
        str(registry.get("file_sha256", "")), "registry.file_sha256"
    )
    request_hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for module in SOURCE_GENERATION_MODULES:
        item = modules[module]
        if not isinstance(item, Mapping):
            raise LearningSourceGenerationAuthorizationError(
                "preflight_module_record_invalid"
            )
        producer = item.get("producer")
        if not isinstance(producer, Mapping):
            raise LearningSourceGenerationAuthorizationError(
                "preflight_producer_record_invalid"
            )
        request_hashes[module] = _sha256(
            str(producer.get("source_generation_request_sha256", "")),
            f"{module}.source_generation_request_sha256",
        )
        count = producer.get("planned_episode_count")
        if type(count) is not int or count <= 0:
            raise LearningSourceGenerationAuthorizationError(
                "preflight_episode_count_invalid"
            )
        counts[module] = count
    return source_commit, registry_sha, request_hashes, counts


def _authorization_from_payload(
    payload: Mapping[str, Any],
    *,
    authorization_file_sha256: str,
) -> LearningSourceGenerationAuthorization:
    if not isinstance(payload, Mapping):
        raise LearningSourceGenerationAuthorizationError(
            "authorization_payload_not_object"
        )
    required = {
        "schema_version",
        "authorization_id",
        "source_git_commit",
        "preflight_sha256",
        "registry_file_sha256",
        "module_request_sha256",
        "planned_episode_count",
        "total_planned_episode_count",
        "permissions",
        "approver_id",
        "approval_reason",
        "approved_at_utc",
        "formal_seed_payload_read",
        "formal_shards_10_19_run",
        "training_started",
        "runtime_authority_granted",
    }
    if set(payload) != required:
        raise LearningSourceGenerationAuthorizationError(
            "authorization_fields_mismatch"
        )
    if payload.get("schema_version") != SOURCE_GENERATION_AUTHORIZATION_SCHEMA_VERSION:
        raise LearningSourceGenerationAuthorizationError(
            "authorization_schema_mismatch"
        )
    counts = _episode_counts(payload["planned_episode_count"])
    if payload.get("total_planned_episode_count") != sum(counts.values()):
        raise LearningSourceGenerationAuthorizationError(
            "authorization_total_episode_count_mismatch"
        )
    for name in (
        "formal_seed_payload_read",
        "formal_shards_10_19_run",
        "training_started",
        "runtime_authority_granted",
    ):
        if payload.get(name) is not False:
            raise LearningSourceGenerationAuthorizationError(
                "authorization_forbidden_state_true"
            )
    return LearningSourceGenerationAuthorization(
        authorization_id=str(payload["authorization_id"]),
        authorization_file_sha256=authorization_file_sha256,
        source_git_commit=str(payload["source_git_commit"]),
        preflight_sha256=str(payload["preflight_sha256"]),
        registry_file_sha256=str(payload["registry_file_sha256"]),
        module_request_sha256=payload["module_request_sha256"],
        planned_episode_count=counts,
        permissions=payload["permissions"],
        approver_id=str(payload["approver_id"]),
        approval_reason=str(payload["approval_reason"]),
        approved_at_utc=str(payload["approved_at_utc"]),
    )


def _module_hashes(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(
        SOURCE_GENERATION_MODULES
    ):
        raise LearningSourceGenerationAuthorizationError(
            "module_request_hash_inventory_invalid"
        )
    return {
        module: _sha256(str(value[module]), f"{module}.request_sha256")
        for module in SOURCE_GENERATION_MODULES
    }


def _episode_counts(value: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(
        SOURCE_GENERATION_MODULES
    ):
        raise LearningSourceGenerationAuthorizationError(
            "episode_count_inventory_invalid"
        )
    counts: dict[str, int] = {}
    for module in SOURCE_GENERATION_MODULES:
        count = value[module]
        if type(count) is not int or count <= 0:
            raise LearningSourceGenerationAuthorizationError(
                "episode_count_invalid"
            )
        counts[module] = count
    return counts


def _permissions(value: Mapping[str, Any]) -> dict[str, bool]:
    if not isinstance(value, Mapping) or set(value) != set(
        SOURCE_GENERATION_PERMISSION_FIELDS
    ):
        raise LearningSourceGenerationAuthorizationError(
            "authorization_permission_inventory_invalid"
        )
    permissions = dict(value)
    if permissions != generation_only_permissions():
        raise LearningSourceGenerationAuthorizationError(
            "authorization_permission_escalation"
        )
    return permissions


def _repository_state(root: Path) -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LearningSourceGenerationAuthorizationError(
            "generation_repository_state_unavailable"
        ) from exc
    return _commit(commit), bool(status.strip())


def _sha256(value: str, name: str) -> str:
    if not _HEX64.fullmatch(value):
        raise LearningSourceGenerationAuthorizationError(f"{name}_invalid")
    return value


def _commit(value: str) -> str:
    if not _GIT_COMMIT.fullmatch(value):
        raise LearningSourceGenerationAuthorizationError(
            "source_git_commit_invalid"
        )
    return value


def _identifier(value: str, name: str) -> str:
    text = str(value).strip()
    if not _IDENTIFIER.fullmatch(text):
        raise LearningSourceGenerationAuthorizationError(f"{name}_invalid")
    return text


def _format_timestamp(value: datetime | str | None) -> str:
    if value is None:
        selected = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        selected = value
    else:
        return _timestamp(str(value), "approved_at_utc")
    if selected.tzinfo is None:
        raise LearningSourceGenerationAuthorizationError(
            "approved_at_utc_timezone_missing"
        )
    return selected.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: str, name: str) -> str:
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LearningSourceGenerationAuthorizationError(
            f"{name}_invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise LearningSourceGenerationAuthorizationError(
            f"{name}_timezone_missing"
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise LearningSourceGenerationAuthorizationError(
                "authorization_duplicate_json_key"
            )
        payload[key] = value
    return payload


__all__ = [
    "LearningSourceGenerationAuthorization",
    "LearningSourceGenerationAuthorizationError",
    "SOURCE_GENERATION_AUTHORIZATION_SCHEMA_VERSION",
    "SOURCE_GENERATION_CONFIRMATION",
    "SOURCE_GENERATION_MODULES",
    "build_learning_source_generation_authorization",
    "canonical_json_sha256",
    "generation_only_permissions",
    "load_learning_source_generation_authorization",
    "write_learning_source_generation_authorization",
]
