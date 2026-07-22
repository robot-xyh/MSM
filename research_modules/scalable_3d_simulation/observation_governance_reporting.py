"""Main-owned persistence for D1/D2 long-episode governance evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


def write_episode_observation_governance_outputs(
    result: Any,
    output_dir: str | Path,
    *,
    source_bus_path: str | Path,
) -> dict[str, Path]:
    """Write one hash-bound D6 bundle from public runtime summaries.

    Truth-dependent evaluator metrics remain unavailable here. A separate
    offline calibration runner may add a hash-bound sidecar after it evaluates
    truth labels that were never visible to D1 or D2.
    """

    from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
        D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
        D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
        OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
        OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
        OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
        ObservationGovernanceCalibrationReportGenerator,
        load_observation_governance_calibration_inputs,
    )

    audit = result.observation_governance_audit
    if not isinstance(audit, Mapping):
        return {}
    if int(audit.get("online_truth_use_count", -1)) != 0:
        raise ValueError("observation governance audit reports online truth use")

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_bus = Path(source_bus_path).expanduser().resolve()
    if not source_bus.is_file():
        raise FileNotFoundError(f"online episode bus is missing: {source_bus}")

    episode = _episode_identity(result)
    evidence_tier = (
        "development" if bool(result.manifest.repository_dirty) else "formal"
    )
    manifest_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
        "episode": episode,
        "provenance": {
            "producer": "main-scalable3d-runtime",
            "git_commit": str(result.manifest.git_commit),
            "repository_dirty": bool(result.manifest.repository_dirty),
            "evidence_tier": evidence_tier,
            "config_sha256": _normalise_sha256(result.manifest.config_sha256),
            "world_schema": str(result.manifest.world_schema),
            "bus_schema": str(result.manifest.bus_schema),
            "scenario_schema": str(result.manifest.scenario_schema),
            "online_observation_schema": str(
                result.manifest.online_observation_schema
            ),
            "d1_scan_oosm_audit_schema": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
            "d2_claim_ledger_audit_schema": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
        },
        "online_truth_use_count": 0,
    }
    manifest_path = _write_json(
        root / "observation_governance_manifest.json",
        manifest_payload,
    )
    manifest_sha = _sha256_file(manifest_path)

    online_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
        "episode": episode,
        "provenance": {
            "producer": "main-scalable3d-runtime",
            "git_commit": str(result.manifest.git_commit),
            "config_sha256": _normalise_sha256(result.manifest.config_sha256),
            "episode_manifest_sha256": manifest_sha,
            "source_bus_sha256": _sha256_file(source_bus),
            "source_bus_schema": str(result.manifest.bus_schema),
        },
        "online_truth_use_count": 0,
        "d1_scan_oosm_audit": {
            "schema_version": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
            "metrics": _d1_metrics(audit),
        },
        "d2_claim_ledger_audit": {
            "schema_version": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
            "metrics": _d2_metrics(audit),
        },
    }
    online_path = _write_json(
        root / "observation_governance_online_audit.json",
        online_payload,
    )
    online_sha = _sha256_file(online_path)

    descriptor = {
        "episode": episode,
        "manifest_artifact": {
            "path": manifest_path.name,
            "sha256": manifest_sha,
        },
        "online_audit_artifact": {
            "path": online_path.name,
            "sha256": online_sha,
        },
        "evaluator_sidecar": {
            "availability": "unavailable",
            "artifact": None,
            "reason": "episode_truth_governance_sidecar_not_produced",
        },
    }
    descriptor_path = _write_json(
        root / "observation_governance_episode_descriptor.json",
        descriptor,
    )
    input_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
        "created_at_utc": _utc_timestamp(),
        "producer": "main-scalable3d-orchestrator",
        "admission_policy": (
            "allow_development" if evidence_tier == "development" else "formal_only"
        ),
        "expected_scales": [episode["scale"]],
        "episodes": [descriptor],
    }
    input_path = _write_json(
        root / "observation_governance_calibration_input.json",
        input_payload,
    )
    inputs = load_observation_governance_calibration_inputs(
        input_path,
        expected_sha256=_sha256_file(input_path),
    )
    report_paths = ObservationGovernanceCalibrationReportGenerator().write_report_bundle(
        root / "d6_report",
        inputs=inputs,
    )
    return {
        "observation_governance_manifest": manifest_path,
        "observation_governance_online_audit": online_path,
        "observation_governance_episode_descriptor": descriptor_path,
        "observation_governance_calibration_input": input_path,
        **{
            f"observation_governance_d6_{name}": path
            for name, path in report_paths.items()
        },
    }


def _episode_identity(result: Any) -> dict[str, Any]:
    return {
        "episode_id": str(result.manifest.episode_id),
        "scale": int(result.config.target_count),
        "target_count": int(result.config.target_count),
        "resource_count": int(result.config.resource_count),
        "seed": int(result.config.seed),
        "duration_s": float(result.config.duration_s),
    }


def _d1_metrics(audit: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(audit.get("d1_scan_input"), "D1 scan audit")
    values = {
        "scan_count": _count(raw, "received_scan_count"),
        "current_oosm_buffer_count": _count(
            raw, "current_buffered_scan_count"
        ),
        "peak_oosm_buffer_count": _count(
            raw, "maximum_buffered_scan_count"
        ),
        "oosm_buffered_count": _count(raw, "buffered_event_count"),
        "oosm_reordered_count": _count(raw, "reordered_scan_count"),
        "oosm_rejected_count": _count(raw, "rejected_scan_count"),
        "oosm_too_old_count": _count(raw, "too_late_scan_count"),
        "oosm_overflow_count": (
            _count(raw, "buffer_overflow_scan_count")
            + _count(raw, "capacity_overflow_scan_count")
        ),
        "oosm_eviction_count": _count(raw, "buffer_expired_scan_count"),
    }
    metrics = {name: _available(value) for name, value in values.items()}
    metrics["estimated_current_memory_bytes"] = _unavailable(
        "runtime_object_size_not_instrumented"
    )
    metrics["estimated_peak_memory_bytes"] = _unavailable(
        "runtime_object_size_not_instrumented"
    )
    return metrics


def _d2_metrics(audit: Mapping[str, Any]) -> dict[str, Any]:
    ledger = _mapping(audit.get("d2_claim_ledger"), "D2 claim ledger")
    values = {
        "current_claim_count": _count(ledger, "current_count"),
        "peak_claim_count": _count(ledger, "peak_count"),
        "claim_eviction_count": _count(ledger, "evicted_count"),
        "claim_too_old_count": _count(ledger, "too_old_rejection_count"),
        "claim_overflow_count": _count(ledger, "overflow_rejection_count"),
        "replay_quarantine_count": int(
            audit.get("d2_replay_quarantine_count", 0)
        ),
        "timestamp_conflict_count": int(
            audit.get("d2_timestamp_conflict_count", 0)
        ),
        "duplicate_coalescence_count": int(
            audit.get("d2_duplicate_coalescence_count", 0)
        ),
    }
    if any(value < 0 for value in values.values()):
        raise ValueError("D2 governance counters must be non-negative")
    metrics = {name: _available(value) for name, value in values.items()}
    metrics["estimated_current_memory_bytes"] = _unavailable(
        "runtime_object_size_not_instrumented"
    )
    metrics["estimated_peak_memory_bytes"] = _unavailable(
        "runtime_object_size_not_instrumented"
    )
    return metrics


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _count(payload: Mapping[str, Any], name: str) -> int:
    value = int(payload.get(name, 0))
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _available(value: int) -> dict[str, Any]:
    return {"availability": "available", "value": int(value), "reason": None}


def _unavailable(reason: str) -> dict[str, Any]:
    return {"availability": "unavailable", "value": None, "reason": reason}


def _normalise_sha256(value: Any) -> str:
    text = str(value).strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("SHA-256 value must contain 64 lowercase hexadecimal digits")
    return f"sha256:{text}"


def _sha256_file(path: str | Path) -> str:
    return f"sha256:{sha256(Path(path).read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
