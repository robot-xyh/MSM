"""Hash-bound strict offline D2 identity evidence for scalable 3D episodes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .truth_isolated_offline import (
    D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSIONS,
    D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION,
    TruthIsolatedEvaluationError,
    adapt_d2_scalable_3d_identity,
)


STRICT_OFFLINE_ID_SWITCH_SEMANTICS = (
    "strict_offline_truth_isolated_d2_identity"
)
STRICT_OFFLINE_ID_SWITCH_SOURCE = (
    "d6_truth_isolated/episode_record.json:"
    "d2_identity.metrics.id_switch_count"
)
D6_TRUTH_ISOLATED_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d6-truth-isolated-manifest-v1"
)

_IDENTITY_SOURCE_FILES = {
    "online_d1_records": "online_d1_records.jsonl",
    "online_d2_records": "online_d2_records.jsonl",
    "observation_truth_labels": "observation_truth_labels.jsonl",
    "identity_evidence": "identity_evidence.json",
    "identity_evaluation": "identity_evaluation.json",
}
_ADAPTER_SOURCE_NAMES = {
    "online_d1_records": "online_d1_records",
    "online_d2_records": "online_d2_records",
    "observation_truth_labels": "observation_truth_labels",
    "identity_evidence": "identity_evidence_bundle",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StrictOfflineIdSwitchEvidence:
    """One fail-closed strict ID-switch result and its verified provenance."""

    value: int | None
    available: bool
    unavailable_reason: str | None
    artifact_verified: bool
    truth_isolation_verified: bool | None
    strict_backfilled: bool | None
    source_artifact: str | None
    verification_mode: str | None
    truth_manifest_sha256: str | None
    episode_record_sha256: str | None
    identity_manifest_sha256: str | None
    identity_evaluation_sha256: str | None
    semantics: str = STRICT_OFFLINE_ID_SWITCH_SEMANTICS


class _StrictIdentityEvidenceError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_strict_offline_id_switch(
    episode_dir: str | Path,
    *,
    expected_context: Mapping[str, Any],
) -> StrictOfflineIdSwitchEvidence:
    """Load the strict metric only after validating every identity binding."""

    directory = Path(episode_dir)
    try:
        return _load_verified_strict_offline_id_switch(
            directory,
            expected_context=expected_context,
        )
    except _StrictIdentityEvidenceError as exc:
        return _unavailable(exc.reason)
    except TruthIsolatedEvaluationError as exc:
        return _unavailable(
            "strict_offline_d2_contract_invalid:" + _reason_slug(str(exc))
        )
    except OSError as exc:
        return _unavailable(
            "strict_offline_artifact_io_error:" + _reason_slug(str(exc))
        )


def strict_id_switch_provenance_is_verified(
    evidence: Mapping[str, Any],
) -> bool:
    """Return true only for the hash-bound, non-backfilled strict source."""

    return bool(
        evidence.get("d2_id_switch_count_semantics")
        == STRICT_OFFLINE_ID_SWITCH_SEMANTICS
        and evidence.get("d2_id_switch_count_source_artifact")
        == STRICT_OFFLINE_ID_SWITCH_SOURCE
        and evidence.get("d2_strict_identity_artifact_verified") is True
        and evidence.get("d2_strict_identity_truth_isolation_verified") is True
        and evidence.get("d2_strict_identity_id_switch_backfilled") is False
        and evidence.get("d2_strict_identity_verification_mode")
        == "sha256_verified_artifact"
    )


def _load_verified_strict_offline_id_switch(
    directory: Path,
    *,
    expected_context: Mapping[str, Any],
) -> StrictOfflineIdSwitchEvidence:
    truth_dir = directory / "d6_truth_isolated"
    identity_dir = directory / "offline_identity"
    truth_manifest_path = truth_dir / "manifest.json"
    episode_record_path = truth_dir / "episode_record.json"
    identity_manifest_path = identity_dir / "manifest.json"
    identity_evaluation_path = identity_dir / "identity_evaluation.json"

    truth_manifest = _load_json_object(
        truth_manifest_path,
        "d6_truth_isolated/manifest.json",
    )
    _require_equal(
        truth_manifest.get("schema_version"),
        D6_TRUTH_ISOLATED_MANIFEST_SCHEMA_VERSION,
        "strict_offline_contract_unsupported:d6_truth_isolated/manifest.json",
    )
    _validate_truth_manifest_context(truth_manifest, expected_context)

    output_hashes = _require_mapping(
        truth_manifest.get("output_hashes"),
        "strict_offline_manifest_output_hashes_missing",
    )
    episode_record_sha = _verify_file_hash(
        episode_record_path,
        output_hashes.get("episode_record"),
        "d6_truth_isolated/episode_record.json",
    )
    episode_record = _load_json_object(
        episode_record_path,
        "d6_truth_isolated/episode_record.json",
    )
    _require_equal(
        episode_record.get("schema_version"),
        D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION,
        "strict_offline_contract_unsupported:"
        "d6_truth_isolated/episode_record.json",
    )
    _validate_episode_record_context(episode_record, expected_context)

    truth_source_hashes = _require_mapping(
        truth_manifest.get("source_hashes"),
        "strict_offline_manifest_source_hashes_missing",
    )
    identity_manifest_sha = _verify_file_hash(
        identity_manifest_path,
        truth_source_hashes.get("offline_identity_manifest"),
        "offline_identity/manifest.json",
    )
    identity_evaluation_sha = _verify_file_hash(
        identity_evaluation_path,
        truth_source_hashes.get("offline_identity_evaluation"),
        "offline_identity/identity_evaluation.json",
    )
    _load_json_object(
        identity_evaluation_path,
        "offline_identity/identity_evaluation.json",
    )

    identity_manifest = _load_json_object(
        identity_manifest_path,
        "offline_identity/manifest.json",
    )
    if identity_manifest.get("schema_version") not in (
        D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSIONS
    ):
        _fail("strict_offline_contract_unsupported:offline_identity/manifest.json")
    _require_equal(
        identity_manifest.get("episode_id"),
        expected_context.get("episode_id"),
        "strict_offline_episode_id_mismatch:offline_identity/manifest.json",
    )
    if identity_manifest.get("available") is not True:
        _fail("strict_offline_identity_manifest_declared_unavailable")
    if identity_manifest.get("reason") is not None:
        _fail("strict_offline_identity_manifest_reason_not_null")
    if identity_manifest.get("online_truth_isolation_verified") is not True:
        _fail("strict_offline_truth_isolation_not_verified")
    declared_metric_availability = identity_manifest.get(
        "identity_metrics_available"
    )
    if not isinstance(declared_metric_availability, bool):
        _fail("strict_offline_identity_metric_availability_invalid")

    identity_source_hashes = _require_mapping(
        identity_manifest.get("source_hashes"),
        "strict_offline_identity_manifest_source_hashes_missing",
    )
    verified_source_hashes: dict[str, str] = {}
    for source_name, filename in _IDENTITY_SOURCE_FILES.items():
        verified_source_hashes[source_name] = _verify_file_hash(
            identity_dir / filename,
            identity_source_hashes.get(source_name),
            f"offline_identity/{filename}",
        )
    _require_equal(
        verified_source_hashes["identity_evaluation"],
        identity_evaluation_sha,
        "strict_offline_identity_evaluation_hash_binding_mismatch",
    )

    adapter_source_hashes = {
        adapter_name: verified_source_hashes[manifest_name]
        for manifest_name, adapter_name in _ADAPTER_SOURCE_NAMES.items()
    }
    adapted = adapt_d2_scalable_3d_identity(
        identity_evaluation_path,
        expected_sha256=identity_evaluation_sha,
        expected_source_hashes=adapter_source_hashes,
        identity_manifest=identity_manifest_path,
        expected_identity_manifest_sha256=identity_manifest_sha,
        d2_online_d2_records=identity_dir / "online_d2_records.jsonl",
        d2_expected_online_d2_records_sha256=(
            verified_source_hashes["online_d2_records"]
        ),
    )

    persisted_d2 = _require_mapping(
        episode_record.get("d2_identity"),
        "strict_offline_episode_record_d2_identity_missing",
    )
    if persisted_d2 != adapted.to_dict():
        _fail("strict_offline_episode_record_d2_identity_mismatch")
    if adapted.episode_id != expected_context.get("episode_id"):
        _fail("strict_offline_episode_id_mismatch:d2_identity")
    if adapted.verification_mode != "sha256_verified_artifact":
        _fail("strict_offline_d2_verification_mode_not_hash_bound")
    if adapted.truth_isolation_verified is not True:
        _fail("strict_offline_truth_isolation_not_verified")

    disposition = adapted.audit.get("d6_observation_truth_disposition_acceptance")
    disposition = _require_mapping(
        disposition,
        "strict_offline_truth_disposition_contract_missing",
    )
    _require_equal(
        disposition.get("strict_id_switch_source"),
        "d2_identity_evaluation_only",
        "strict_offline_id_switch_source_mismatch",
    )
    if disposition.get("strict_id_switch_backfilled") is not False:
        _fail("strict_offline_id_switch_backfill_forbidden")

    metric = adapted.metrics.get("id_switch_count")
    if metric is None:
        _fail("strict_offline_id_switch_metric_missing")
    if metric.available:
        value = metric.value
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _fail("strict_offline_id_switch_metric_invalid")
        unavailable_reason = None
    else:
        if metric.value is not None:
            _fail("strict_offline_unavailable_id_switch_has_value")
        value = None
        unavailable_reason = str(
            metric.unavailable_reason or "strict_offline_id_switch_metric_unavailable"
        )
    if declared_metric_availability is not metric.available:
        _fail("strict_offline_identity_metric_availability_mismatch")

    return StrictOfflineIdSwitchEvidence(
        value=value,
        available=bool(metric.available),
        unavailable_reason=unavailable_reason,
        artifact_verified=True,
        truth_isolation_verified=True,
        strict_backfilled=False,
        source_artifact=STRICT_OFFLINE_ID_SWITCH_SOURCE,
        verification_mode=adapted.verification_mode,
        truth_manifest_sha256=_sha256_file(truth_manifest_path),
        episode_record_sha256=episode_record_sha,
        identity_manifest_sha256=identity_manifest_sha,
        identity_evaluation_sha256=identity_evaluation_sha,
    )


def _validate_truth_manifest_context(
    manifest: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    for field in (
        "episode_id",
        "scenario_version",
        "seed",
        "target_count",
        "resource_count",
    ):
        _require_expected_context(expected, field)
        _require_equal(
            manifest.get(field),
            expected.get(field),
            f"strict_offline_context_mismatch:d6_truth_isolated/manifest.json:{field}",
        )


def _validate_episode_record_context(
    record: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    context = _require_mapping(
        record.get("context"),
        "strict_offline_episode_record_context_missing",
    )
    aliases = {
        "episode_id": "episode_id",
        "scenario_name": "scenario_id",
        "scenario_version": "scenario_version",
        "seed": "seed",
        "target_count": "target_count",
        "resource_count": "resource_count",
        "recon_count": "recon_count",
        "camera_count": "camera_count",
    }
    for expected_field, record_field in aliases.items():
        _require_expected_context(expected, expected_field)
        _require_equal(
            context.get(record_field),
            expected.get(expected_field),
            "strict_offline_context_mismatch:"
            f"d6_truth_isolated/episode_record.json:{record_field}",
        )
    _require_equal(
        context.get("run_id"),
        expected.get("episode_id"),
        "strict_offline_context_mismatch:"
        "d6_truth_isolated/episode_record.json:run_id",
    )


def _require_expected_context(expected: Mapping[str, Any], field: str) -> None:
    if expected.get(field) is None:
        _fail(f"strict_offline_expected_context_unavailable:{field}")


def _load_json_object(path: Path, relative_name: str) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"strict_offline_artifact_missing:{relative_name}")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=lambda pairs: _unique_json_object(
                pairs,
                relative_name,
            ),
            parse_constant=lambda token: _reject_nonfinite_json(
                token,
                relative_name,
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _StrictIdentityEvidenceError(
            f"strict_offline_artifact_invalid_json:{relative_name}"
        ) from exc
    if not isinstance(payload, Mapping):
        _fail(f"strict_offline_artifact_not_object:{relative_name}")
    return dict(payload)


def _unique_json_object(
    pairs: list[tuple[str, Any]], relative_name: str
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"strict_offline_artifact_duplicate_key:{relative_name}:{key}")
        result[key] = value
    return result


def _reject_nonfinite_json(token: str, relative_name: str) -> None:
    _fail(f"strict_offline_artifact_nonfinite_json:{relative_name}:{token}")


def _verify_file_hash(path: Path, expected: Any, relative_name: str) -> str:
    if not path.is_file():
        _fail(f"strict_offline_artifact_missing:{relative_name}")
    expected_hash = _normalize_sha256(
        expected,
        f"strict_offline_manifest_hash_invalid:{relative_name}",
    )
    observed = _sha256_file(path)
    if observed != expected_hash:
        _fail(f"strict_offline_artifact_sha256_mismatch:{relative_name}")
    return observed


def _normalize_sha256(value: Any, reason: str) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if not _HEX64.fullmatch(text):
        _fail(reason)
    return f"sha256:{text}"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _require_mapping(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(reason)
    return dict(value)


def _require_equal(observed: Any, expected: Any, reason: str) -> None:
    if observed != expected:
        _fail(reason)


def _reason_slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value.strip())
    return normalized.strip("_") or "unspecified"


def _fail(reason: str) -> None:
    raise _StrictIdentityEvidenceError(reason)


def _unavailable(reason: str) -> StrictOfflineIdSwitchEvidence:
    return StrictOfflineIdSwitchEvidence(
        value=None,
        available=False,
        unavailable_reason=str(reason),
        artifact_verified=False,
        truth_isolation_verified=None,
        strict_backfilled=None,
        source_artifact=None,
        verification_mode=None,
        truth_manifest_sha256=None,
        episode_record_sha256=None,
        identity_manifest_sha256=None,
        identity_evaluation_sha256=None,
    )


__all__ = [
    "D6_TRUTH_ISOLATED_MANIFEST_SCHEMA_VERSION",
    "STRICT_OFFLINE_ID_SWITCH_SEMANTICS",
    "STRICT_OFFLINE_ID_SWITCH_SOURCE",
    "StrictOfflineIdSwitchEvidence",
    "load_strict_offline_id_switch",
    "strict_id_switch_provenance_is_verified",
]
