"""Adapters from existing strict evidence schemas to readiness gate facts.

The adapters do not accept caller-provided gate facts.  A small reference
sidecar may name original producer artifacts, but every named file is resolved
below one explicit root, hashed, and then consumed by an existing D6 auditor.
Unsupported gates remain unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .canonical_seed_split_readiness import (
    CANONICAL_SEED_SPLIT_READINESS_SCHEMA_VERSION,
    CanonicalSeedSplitAuditError,
    audit_canonical_seed_split_readiness,
)


CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION = (
    "d6.learning-run-canonical-seed-source-reference.v1"
)
LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS = {
    "model_source": frozenset(),
    "frozen_unseen_seeds": frozenset(
        {CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION}
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
    if schema == CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION:
        return _load_canonical_seed_source(
            data,
            artifact_root=Path(artifact_root),
            expected_variant=expected_variant,
        )
    _fail("gate_source_schema_unsupported", schema)


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

    root = artifact_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        _fail("gate_source_artifact_root_not_directory")
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


def _resolve_and_verify(
    root: Path,
    reference: Mapping[str, str],
    *,
    label: str,
) -> Path:
    relative = Path(reference["path"])
    if relative.is_absolute() or ".." in relative.parts:
        _fail("gate_source_original_path_escape_rejected", label)
    unresolved = root / relative
    if unresolved.is_symlink():
        _fail("gate_source_original_symlink_rejected", label)
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
    "LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS",
    "LearningRunSourceAdapterError",
    "load_learning_run_source_evidence_bytes",
]
