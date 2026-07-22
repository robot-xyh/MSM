"""Read-only calibration of long-episode observation governance evidence.

The evaluator consumes public, hash-bound artifacts written after an episode.
It never imports D1/D2 runtime code and never reconstructs truth mappings from
online records.  Truth-dependent metrics are admitted only from an explicit
evaluator-only sidecar that is bound to the online evidence by SHA-256.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np


OBSERVATION_GOVERNANCE_CALIBRATION_SCHEMA_VERSION = (
    "scalable3d-observation-governance-calibration-v1"
)
OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION = (
    "scalable3d-observation-governance-calibration-input-v1"
)
OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-observation-governance-episode-manifest-v1"
)
OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION = (
    "scalable3d-observation-governance-online-audit-v1"
)
OBSERVATION_GOVERNANCE_EVALUATOR_SIDECAR_SCHEMA_VERSION = (
    "scalable3d-observation-governance-evaluator-sidecar-v1"
)
D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION = "d1-scalable3d-scan-oosm-audit-v1"
D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION = "d2-scalable3d-claim-ledger-audit-v1"
OBSERVATION_GOVERNANCE_CALIBRATION_DATE = "2026-07-22"
DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RNG_SEED = 20260722


D1_ONLINE_METRICS = (
    "scan_count",
    "current_oosm_buffer_count",
    "peak_oosm_buffer_count",
    "oosm_buffered_count",
    "oosm_reordered_count",
    "oosm_rejected_count",
    "oosm_too_old_count",
    "oosm_overflow_count",
    "oosm_eviction_count",
    "estimated_current_memory_bytes",
    "estimated_peak_memory_bytes",
)
D2_ONLINE_METRICS = (
    "current_claim_count",
    "peak_claim_count",
    "claim_eviction_count",
    "claim_too_old_count",
    "claim_overflow_count",
    "replay_quarantine_count",
    "timestamp_conflict_count",
    "duplicate_coalescence_count",
    "estimated_current_memory_bytes",
    "estimated_peak_memory_bytes",
)
DERIVED_ONLINE_METRICS = (
    "estimated_total_current_memory_bytes",
    "estimated_total_peak_memory_bytes",
)
EVALUATOR_RATIO_METRICS = (
    "near_neighbor_recall",
    "false_suppression_rate",
    "erroneous_coalescence_rate",
)
EVALUATOR_LATENCY_METRIC = "confirmation_latency_s"


_SHA256_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_ONLINE_IDENTITY_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_target_id",
        "truth_target_ids",
        "target_truth_id",
        "ground_truth",
        "ground_truth_id",
        "truth_position",
        "truth_velocity",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
        "intercepted_target_indices",
    }
)
_ALLOWED_TRUTH_AUDIT_KEYS = frozenset(
    {
        "online_truth_use_count",
        "online_truth_used",
        "online_truth_isolation_verified",
    }
)


class ObservationGovernanceCalibrationError(ValueError):
    """Fail-closed input, provenance, availability, or truth-isolation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class ObservationGovernanceCalibrationInputs:
    """Hash-bound public input specification supplied by main."""

    input_spec_path: Path
    input_spec_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_spec_path",
            Path(self.input_spec_path).expanduser().resolve(),
        )
        object.__setattr__(
            self,
            "input_spec_sha256",
            _normalise_sha256(self.input_spec_sha256),
        )


@dataclass(frozen=True)
class ObservationGovernanceCalibrationResult:
    """Validated per-seed rows plus the versioned aggregate payload."""

    per_seed_records: tuple[dict[str, Any], ...]
    aggregate: dict[str, Any]


class ObservationGovernanceCalibrationReportGenerator:
    """Write per-seed CSV, aggregate JSON, and Chinese Markdown."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: ObservationGovernanceCalibrationInputs,
        bootstrap_resamples: int = (
            DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RESAMPLES
        ),
        bootstrap_rng_seed: int = (
            DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RNG_SEED
        ),
        title: str = "长 episode 观测治理标定报告",
    ) -> dict[str, Path]:
        result = evaluate_observation_governance_calibration(
            inputs,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
        )
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        csv_path = output_path / "observation_governance_per_seed.csv"
        _write_per_seed_csv(csv_path, result.per_seed_records)

        aggregate_path = output_path / "observation_governance_aggregate.json"
        aggregate_path.write_text(
            json.dumps(
                result.aggregate,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        markdown_path = (
            output_path / "OBSERVATION_GOVERNANCE_CALIBRATION_CN.md"
        )
        markdown_path.write_text(
            render_observation_governance_calibration_markdown(
                result.per_seed_records,
                result.aggregate,
                title=title,
            ),
            encoding="utf-8",
        )
        return {
            "per_seed_csv": csv_path,
            "aggregate_json": aggregate_path,
            "markdown": markdown_path,
        }


def load_observation_governance_calibration_inputs(
    input_spec_path: str | Path,
    *,
    expected_sha256: str,
) -> ObservationGovernanceCalibrationInputs:
    """Create a hash-bound input object without reading runtime state."""

    return ObservationGovernanceCalibrationInputs(
        input_spec_path=Path(input_spec_path),
        input_spec_sha256=expected_sha256,
    )


def evaluate_observation_governance_calibration(
    inputs: ObservationGovernanceCalibrationInputs,
    *,
    bootstrap_resamples: int = DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RNG_SEED,
) -> ObservationGovernanceCalibrationResult:
    """Validate a public batch and aggregate without touching D1/D2 control."""

    if int(bootstrap_resamples) <= 0:
        raise ValueError("bootstrap_resamples must be positive")
    path = inputs.input_spec_path
    actual_input_hash = _verify_file_hash(
        path,
        inputs.input_spec_sha256,
        artifact_name="input specification",
    )
    payload = _load_json_mapping(path, "input specification")
    _require_schema(
        payload,
        OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
        "input specification",
    )
    _require_fields(
        payload,
        {
            "schema_version",
            "created_at_utc",
            "producer",
            "admission_policy",
            "expected_scales",
            "episodes",
        },
        "input specification",
    )
    _identifier(payload.get("created_at_utc"), "created_at_utc")
    _identifier(payload.get("producer"), "input producer")
    admission_policy = str(payload.get("admission_policy", ""))
    if admission_policy not in {"formal_only", "allow_development"}:
        _fail(
            "unsupported_admission_policy",
            "admission_policy must be formal_only or allow_development",
        )

    expected_scales_raw = payload.get("expected_scales")
    if not _is_sequence(expected_scales_raw) or not expected_scales_raw:
        _fail("missing_expected_scales", "expected_scales must be non-empty")
    expected_scales = tuple(
        _positive_int(value, "expected scale") for value in expected_scales_raw
    )
    if len(set(expected_scales)) != len(expected_scales):
        _fail("duplicate_expected_scale", "expected_scales must be unique")

    descriptors = payload.get("episodes")
    if not _is_sequence(descriptors) or not descriptors:
        _fail("missing_episodes", "episodes must be a non-empty sequence")

    base_dir = path.parent
    rows: list[dict[str, Any]] = []
    episode_ids: set[str] = set()
    seeds: set[int] = set()
    for index, raw_descriptor in enumerate(descriptors):
        descriptor = _mapping(raw_descriptor, f"episodes[{index}]")
        row = _evaluate_episode_descriptor(
            descriptor,
            base_dir=base_dir,
            admission_policy=admission_policy,
        )
        episode_id = str(row["episode_id"])
        seed = int(row["seed"])
        if episode_id in episode_ids:
            _fail("duplicate_episode_id", f"duplicate episode_id {episode_id}")
        if seed in seeds:
            _fail("duplicate_seed", f"duplicate seed {seed}")
        episode_ids.add(episode_id)
        seeds.add(seed)
        rows.append(row)

    observed_scales = tuple(sorted({int(row["scale"]) for row in rows}))
    if set(observed_scales) != set(expected_scales):
        _fail(
            "inconsistent_scale_set",
            "observed scales do not exactly match expected_scales: "
            f"expected={sorted(expected_scales)}, observed={list(observed_scales)}",
        )

    rows.sort(key=lambda row: (int(row["scale"]), int(row["seed"])))
    aggregate = _aggregate_records(
        rows,
        input_spec_sha256=actual_input_hash,
        input_spec_created_at_utc=str(payload["created_at_utc"]),
        input_producer=str(payload["producer"]),
        admission_policy=admission_policy,
        expected_scales=expected_scales,
        bootstrap_resamples=int(bootstrap_resamples),
        bootstrap_rng_seed=int(bootstrap_rng_seed),
    )
    public_rows = tuple(_public_record(row) for row in rows)
    return ObservationGovernanceCalibrationResult(
        per_seed_records=public_rows,
        aggregate=aggregate,
    )


def _evaluate_episode_descriptor(
    descriptor: Mapping[str, Any],
    *,
    base_dir: Path,
    admission_policy: str,
) -> dict[str, Any]:
    _require_fields(
        descriptor,
        {
            "episode",
            "manifest_artifact",
            "online_audit_artifact",
            "evaluator_sidecar",
        },
        "episode descriptor",
    )
    descriptor_identity = _episode_identity(
        _mapping(descriptor.get("episode"), "descriptor episode")
    )
    manifest_path, manifest_hash = _artifact_reference(
        descriptor.get("manifest_artifact"),
        base_dir=base_dir,
        context="manifest_artifact",
    )
    online_path, online_hash = _artifact_reference(
        descriptor.get("online_audit_artifact"),
        base_dir=base_dir,
        context="online_audit_artifact",
    )
    manifest_payload = _load_json_mapping(manifest_path, "episode manifest")
    online_payload = _load_json_mapping(online_path, "online governance audit")
    manifest = _validate_manifest(
        manifest_payload,
        expected_hash=manifest_hash,
        actual_path=manifest_path,
        admission_policy=admission_policy,
    )
    _assert_same_episode(descriptor_identity, manifest["episode"], "manifest")
    online = _validate_online_audit(
        online_payload,
        expected_hash=online_hash,
        actual_path=online_path,
        manifest=manifest,
        manifest_hash=manifest_hash,
    )

    sidecar = _validate_evaluator_sidecar_descriptor(
        descriptor.get("evaluator_sidecar"),
        base_dir=base_dir,
        expected_episode=descriptor_identity,
        manifest=manifest,
        manifest_hash=manifest_hash,
        online_hash=online_hash,
    )

    row: dict[str, Any] = {
        **descriptor_identity,
        "git_commit": manifest["provenance"]["git_commit"],
        "repository_dirty": manifest["provenance"]["repository_dirty"],
        "evidence_tier": manifest["provenance"]["evidence_tier"],
        "config_sha256": manifest["provenance"]["config_sha256"],
        "world_schema": manifest["provenance"]["world_schema"],
        "bus_schema": manifest["provenance"]["bus_schema"],
        "scenario_schema": manifest["provenance"]["scenario_schema"],
        "online_observation_schema": manifest["provenance"][
            "online_observation_schema"
        ],
        "d1_scan_oosm_audit_schema": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
        "d2_claim_ledger_audit_schema": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
        "manifest_sha256": manifest_hash,
        "online_audit_sha256": online_hash,
        "source_bus_sha256": online["provenance"]["source_bus_sha256"],
        "online_truth_use_count": 0,
        "formal_source_admitted": manifest["provenance"]["evidence_tier"]
        == "formal",
        "evaluator_sidecar_sha256": sidecar["sidecar_sha256"],
        "evaluator_sidecar_availability": sidecar["availability"],
        "evaluator_sidecar_reason": sidecar["reason"],
        "evaluator_producer": sidecar["evaluator_producer"],
        "evaluator_git_commit": sidecar["evaluator_git_commit"],
        "truth_schema": sidecar["truth_schema"],
        "truth_artifact_sha256": sidecar["truth_artifact_sha256"],
    }
    row.update(online["metrics"])
    row.update(_derive_total_memory_metrics(row))
    row.update(sidecar["metrics"])
    return row


def _validate_manifest(
    payload: Mapping[str, Any],
    *,
    expected_hash: str,
    actual_path: Path,
    admission_policy: str,
) -> dict[str, Any]:
    actual_hash = _verify_file_hash(
        actual_path,
        expected_hash,
        artifact_name="episode manifest",
    )
    _require_schema(
        payload,
        OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
        "episode manifest",
    )
    _require_fields(
        payload,
        {"schema_version", "episode", "provenance", "online_truth_use_count"},
        "episode manifest",
    )
    episode = _episode_identity(_mapping(payload.get("episode"), "manifest episode"))
    provenance = _mapping(payload.get("provenance"), "manifest provenance")
    required = {
        "producer",
        "git_commit",
        "repository_dirty",
        "evidence_tier",
        "config_sha256",
        "world_schema",
        "bus_schema",
        "scenario_schema",
        "online_observation_schema",
        "d1_scan_oosm_audit_schema",
        "d2_claim_ledger_audit_schema",
    }
    _require_fields(provenance, required, "manifest provenance")
    _identifier(provenance.get("producer"), "manifest producer")
    git_commit = _git_commit(provenance.get("git_commit"), "manifest git_commit")
    dirty = _required_bool(
        provenance.get("repository_dirty"), "manifest repository_dirty"
    )
    evidence_tier = str(provenance.get("evidence_tier", ""))
    if evidence_tier not in {"formal", "development"}:
        _fail(
            "invalid_evidence_tier",
            "manifest evidence_tier must be formal or development",
        )
    if evidence_tier == "formal" and dirty:
        _fail("dirty_formal_source", "formal source has repository_dirty=true")
    if admission_policy == "formal_only" and evidence_tier != "formal":
        _fail("development_source_rejected", "formal_only rejects development source")
    config_sha256 = _normalise_sha256(provenance.get("config_sha256"))
    schemas = {
        name: _identifier(provenance.get(name), f"manifest {name}")
        for name in (
            "world_schema",
            "bus_schema",
            "scenario_schema",
            "online_observation_schema",
            "d1_scan_oosm_audit_schema",
            "d2_claim_ledger_audit_schema",
        )
    }
    if schemas["d1_scan_oosm_audit_schema"] != D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION:
        _fail("unsupported_d1_audit_schema", "manifest D1 audit schema is unsupported")
    if schemas["d2_claim_ledger_audit_schema"] != D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION:
        _fail("unsupported_d2_audit_schema", "manifest D2 audit schema is unsupported")
    truth_use_count = _nonnegative_int(
        payload.get("online_truth_use_count"), "manifest online_truth_use_count"
    )
    if truth_use_count != 0:
        _fail("online_truth_leakage", "manifest reports online truth use")
    return {
        "episode": episode,
        "sha256": actual_hash,
        "provenance": {
            "producer": str(provenance["producer"]),
            "git_commit": git_commit,
            "repository_dirty": dirty,
            "evidence_tier": evidence_tier,
            "config_sha256": config_sha256,
            **schemas,
        },
    }


def _validate_online_audit(
    payload: Mapping[str, Any],
    *,
    expected_hash: str,
    actual_path: Path,
    manifest: Mapping[str, Any],
    manifest_hash: str,
) -> dict[str, Any]:
    actual_hash = _verify_file_hash(
        actual_path,
        expected_hash,
        artifact_name="online governance audit",
    )
    _require_schema(
        payload,
        OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
        "online governance audit",
    )
    _require_fields(
        payload,
        {
            "schema_version",
            "episode",
            "provenance",
            "online_truth_use_count",
            "d1_scan_oosm_audit",
            "d2_claim_ledger_audit",
        },
        "online governance audit",
    )
    _scan_online_truth_leakage(payload)
    episode = _episode_identity(_mapping(payload.get("episode"), "online audit episode"))
    _assert_same_episode(manifest["episode"], episode, "online audit")
    provenance = _mapping(payload.get("provenance"), "online audit provenance")
    _require_fields(
        provenance,
        {
            "producer",
            "git_commit",
            "config_sha256",
            "episode_manifest_sha256",
            "source_bus_sha256",
            "source_bus_schema",
        },
        "online audit provenance",
    )
    _identifier(provenance.get("producer"), "online audit producer")
    git_commit = _git_commit(provenance.get("git_commit"), "online audit git_commit")
    config_hash = _normalise_sha256(provenance.get("config_sha256"))
    bound_manifest_hash = _normalise_sha256(
        provenance.get("episode_manifest_sha256")
    )
    source_bus_hash = _normalise_sha256(provenance.get("source_bus_sha256"))
    source_bus_schema = _identifier(
        provenance.get("source_bus_schema"), "online source_bus_schema"
    )
    if bound_manifest_hash != manifest_hash:
        _fail("manifest_hash_binding_mismatch", "online audit manifest hash mismatch")
    if git_commit != manifest["provenance"]["git_commit"]:
        _fail("git_provenance_mismatch", "online audit git commit differs from manifest")
    if config_hash != manifest["provenance"]["config_sha256"]:
        _fail("config_provenance_mismatch", "online audit config hash differs from manifest")
    if source_bus_schema != manifest["provenance"]["bus_schema"]:
        _fail("bus_schema_mismatch", "online source bus schema differs from manifest")
    truth_use_count = _nonnegative_int(
        payload.get("online_truth_use_count"), "online audit online_truth_use_count"
    )
    if truth_use_count != 0:
        _fail("online_truth_leakage", "online audit reports truth use")

    d1 = _mapping(payload.get("d1_scan_oosm_audit"), "D1 scan OOSM audit")
    d2 = _mapping(payload.get("d2_claim_ledger_audit"), "D2 claim ledger audit")
    _require_schema(d1, D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION, "D1 scan OOSM audit")
    _require_schema(d2, D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION, "D2 claim ledger audit")
    _require_fields(d1, {"schema_version", "metrics"}, "D1 scan OOSM audit")
    _require_fields(d2, {"schema_version", "metrics"}, "D2 claim ledger audit")
    d1_metrics = _parse_online_metrics(
        _mapping(d1.get("metrics"), "D1 scan OOSM metrics"),
        D1_ONLINE_METRICS,
        prefix="d1",
    )
    d2_metrics = _parse_online_metrics(
        _mapping(d2.get("metrics"), "D2 claim ledger metrics"),
        D2_ONLINE_METRICS,
        prefix="d2",
    )
    metrics = {**d1_metrics, **d2_metrics}
    _validate_online_metric_relations(metrics)
    return {
        "sha256": actual_hash,
        "provenance": {
            "git_commit": git_commit,
            "config_sha256": config_hash,
            "source_bus_sha256": source_bus_hash,
            "source_bus_schema": source_bus_schema,
        },
        "metrics": metrics,
    }


def _validate_evaluator_sidecar_descriptor(
    raw_descriptor: Any,
    *,
    base_dir: Path,
    expected_episode: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_hash: str,
    online_hash: str,
) -> dict[str, Any]:
    descriptor = _mapping(raw_descriptor, "evaluator_sidecar")
    _require_fields(descriptor, {"availability", "artifact", "reason"}, "evaluator_sidecar")
    availability = str(descriptor.get("availability", ""))
    if availability == "unavailable":
        if descriptor.get("artifact") is not None:
            _fail(
                "unavailable_sidecar_has_artifact",
                "unavailable evaluator_sidecar must use artifact=null",
            )
        reason = _identifier(descriptor.get("reason"), "evaluator sidecar reason")
        return {
            "availability": "unavailable",
            "reason": reason,
            "sidecar_sha256": None,
            "evaluator_producer": None,
            "evaluator_git_commit": None,
            "truth_schema": None,
            "truth_artifact_sha256": None,
            "metrics": _unavailable_evaluator_metrics(reason),
        }
    if availability != "available":
        _fail(
            "invalid_sidecar_availability",
            "evaluator_sidecar availability must be available or unavailable",
        )
    if descriptor.get("reason") is not None:
        _fail(
            "available_sidecar_has_reason",
            "available evaluator_sidecar must use reason=null",
        )
    path, expected_hash = _artifact_reference(
        descriptor.get("artifact"),
        base_dir=base_dir,
        context="evaluator_sidecar.artifact",
    )
    actual_hash = _verify_file_hash(
        path,
        expected_hash,
        artifact_name="evaluator-only sidecar",
    )
    payload = _load_json_mapping(path, "evaluator-only sidecar")
    _require_schema(
        payload,
        OBSERVATION_GOVERNANCE_EVALUATOR_SIDECAR_SCHEMA_VERSION,
        "evaluator-only sidecar",
    )
    _require_fields(
        payload,
        {
            "schema_version",
            "evaluator_only",
            "online_consumed",
            "episode",
            "provenance",
            "metrics",
        },
        "evaluator-only sidecar",
    )
    if payload.get("evaluator_only") is not True:
        _fail("sidecar_not_evaluator_only", "evaluator_only must be true")
    if payload.get("online_consumed") is not False:
        _fail("sidecar_online_consumed", "online_consumed must be false")
    episode = _episode_identity(_mapping(payload.get("episode"), "sidecar episode"))
    _assert_same_episode(expected_episode, episode, "evaluator-only sidecar")

    provenance = _mapping(payload.get("provenance"), "sidecar provenance")
    _require_fields(
        provenance,
        {
            "producer",
            "evaluator_git_commit",
            "config_sha256",
            "truth_schema",
            "truth_artifact_sha256",
            "episode_manifest_sha256",
            "online_audit_sha256",
        },
        "sidecar provenance",
    )
    producer = _identifier(provenance.get("producer"), "sidecar producer")
    evaluator_git = _git_commit(
        provenance.get("evaluator_git_commit"), "sidecar evaluator_git_commit"
    )
    config_hash = _normalise_sha256(provenance.get("config_sha256"))
    truth_schema = _identifier(provenance.get("truth_schema"), "sidecar truth_schema")
    truth_hash = _normalise_sha256(provenance.get("truth_artifact_sha256"))
    bound_manifest_hash = _normalise_sha256(
        provenance.get("episode_manifest_sha256")
    )
    bound_online_hash = _normalise_sha256(provenance.get("online_audit_sha256"))
    if config_hash != manifest["provenance"]["config_sha256"]:
        _fail("sidecar_config_mismatch", "sidecar config hash differs from manifest")
    if bound_manifest_hash != manifest_hash:
        _fail("sidecar_manifest_hash_mismatch", "sidecar manifest hash mismatch")
    if bound_online_hash != online_hash:
        _fail("sidecar_online_hash_mismatch", "sidecar online audit hash mismatch")

    metrics_payload = _mapping(payload.get("metrics"), "sidecar metrics")
    _require_fields(
        metrics_payload,
        {*EVALUATOR_RATIO_METRICS, EVALUATOR_LATENCY_METRIC},
        "sidecar metrics",
    )
    metrics: dict[str, Any] = {}
    for name in EVALUATOR_RATIO_METRICS:
        metrics.update(_parse_ratio_evidence(metrics_payload.get(name), name=name))
    metrics.update(
        _parse_latency_evidence(
            metrics_payload.get(EVALUATOR_LATENCY_METRIC),
            name=EVALUATOR_LATENCY_METRIC,
        )
    )
    return {
        "availability": "available",
        "reason": None,
        "sidecar_sha256": actual_hash,
        "evaluator_producer": producer,
        "evaluator_git_commit": evaluator_git,
        "truth_schema": truth_schema,
        "truth_artifact_sha256": truth_hash,
        "metrics": metrics,
    }


def _parse_online_metrics(
    payload: Mapping[str, Any],
    required_names: Sequence[str],
    *,
    prefix: str,
) -> dict[str, Any]:
    _require_fields(payload, set(required_names), f"{prefix} metrics")
    result: dict[str, Any] = {}
    for name in required_names:
        evidence = _metric_evidence(payload.get(name), context=f"{prefix}.{name}")
        output_name = f"{prefix}_{name}"
        result[output_name] = evidence["value"]
        result[f"{output_name}_availability"] = evidence["availability"]
        result[f"{output_name}_reason"] = evidence["reason"]
    return result


def _metric_evidence(raw: Any, *, context: str) -> dict[str, Any]:
    payload = _mapping(raw, context)
    _require_fields(payload, {"availability", "value", "reason"}, context)
    availability = str(payload.get("availability", ""))
    if availability == "available":
        if payload.get("reason") is not None:
            _fail("available_metric_has_reason", f"{context} must use reason=null")
        value = _nonnegative_int(payload.get("value"), f"{context}.value")
        return {"availability": "available", "value": value, "reason": None}
    if availability == "unavailable":
        if payload.get("value") is not None:
            _fail("unavailable_metric_has_value", f"{context} must use value=null")
        reason = _identifier(payload.get("reason"), f"{context}.reason")
        return {"availability": "unavailable", "value": None, "reason": reason}
    _fail(
        "invalid_metric_availability",
        f"{context}.availability must be available or unavailable",
    )


def _parse_ratio_evidence(raw: Any, *, name: str) -> dict[str, Any]:
    payload = _mapping(raw, name)
    _require_fields(
        payload,
        {"availability", "numerator", "denominator", "reason"},
        name,
    )
    availability = str(payload.get("availability", ""))
    if availability == "available":
        if payload.get("reason") is not None:
            _fail("available_metric_has_reason", f"{name} must use reason=null")
        numerator = _nonnegative_int(payload.get("numerator"), f"{name}.numerator")
        denominator = _positive_int(payload.get("denominator"), f"{name}.denominator")
        if numerator > denominator:
            _fail("invalid_ratio_counts", f"{name} numerator exceeds denominator")
        return {
            name: numerator / denominator,
            f"{name}_availability": "available",
            f"{name}_reason": None,
            f"{name}_numerator": numerator,
            f"{name}_denominator": denominator,
        }
    if availability == "unavailable":
        if payload.get("numerator") is not None or payload.get("denominator") is not None:
            _fail(
                "unavailable_metric_has_value",
                f"{name} unavailable counts must be null",
            )
        reason = _identifier(payload.get("reason"), f"{name}.reason")
        return {
            name: None,
            f"{name}_availability": "unavailable",
            f"{name}_reason": reason,
            f"{name}_numerator": None,
            f"{name}_denominator": None,
        }
    _fail(
        "invalid_metric_availability",
        f"{name}.availability must be available or unavailable",
    )


def _parse_latency_evidence(raw: Any, *, name: str) -> dict[str, Any]:
    payload = _mapping(raw, name)
    _require_fields(payload, {"availability", "samples_s", "reason"}, name)
    availability = str(payload.get("availability", ""))
    if availability == "available":
        if payload.get("reason") is not None:
            _fail("available_metric_has_reason", f"{name} must use reason=null")
        samples_raw = payload.get("samples_s")
        if not _is_sequence(samples_raw) or not samples_raw:
            _fail("missing_latency_samples", f"{name}.samples_s must be non-empty")
        samples = tuple(
            _nonnegative_float(value, f"{name}.samples_s") for value in samples_raw
        )
        array = np.asarray(samples, dtype=float)
        return {
            name: float(np.mean(array)),
            f"{name}_availability": "available",
            f"{name}_reason": None,
            f"{name}_sample_count": len(samples),
            f"{name}_mean": float(np.mean(array)),
            f"{name}_p95": float(np.percentile(array, 95)),
            f"{name}_max": float(np.max(array)),
            "_confirmation_latency_samples_s": samples,
        }
    if availability == "unavailable":
        if payload.get("samples_s") is not None:
            _fail("unavailable_metric_has_value", f"{name}.samples_s must be null")
        reason = _identifier(payload.get("reason"), f"{name}.reason")
        return {
            name: None,
            f"{name}_availability": "unavailable",
            f"{name}_reason": reason,
            f"{name}_sample_count": 0,
            f"{name}_mean": None,
            f"{name}_p95": None,
            f"{name}_max": None,
            "_confirmation_latency_samples_s": (),
        }
    _fail(
        "invalid_metric_availability",
        f"{name}.availability must be available or unavailable",
    )


def _unavailable_evaluator_metrics(reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in EVALUATOR_RATIO_METRICS:
        result.update(
            {
                name: None,
                f"{name}_availability": "unavailable",
                f"{name}_reason": reason,
                f"{name}_numerator": None,
                f"{name}_denominator": None,
            }
        )
    result.update(
        {
            EVALUATOR_LATENCY_METRIC: None,
            f"{EVALUATOR_LATENCY_METRIC}_availability": "unavailable",
            f"{EVALUATOR_LATENCY_METRIC}_reason": reason,
            f"{EVALUATOR_LATENCY_METRIC}_sample_count": 0,
            f"{EVALUATOR_LATENCY_METRIC}_mean": None,
            f"{EVALUATOR_LATENCY_METRIC}_p95": None,
            f"{EVALUATOR_LATENCY_METRIC}_max": None,
            "_confirmation_latency_samples_s": (),
        }
    )
    return result


def _validate_online_metric_relations(metrics: Mapping[str, Any]) -> None:
    _validate_current_peak(metrics, "d1_current_oosm_buffer_count", "d1_peak_oosm_buffer_count")
    _validate_current_peak(metrics, "d2_current_claim_count", "d2_peak_claim_count")
    _validate_current_peak(
        metrics,
        "d1_estimated_current_memory_bytes",
        "d1_estimated_peak_memory_bytes",
    )
    _validate_current_peak(
        metrics,
        "d2_estimated_current_memory_bytes",
        "d2_estimated_peak_memory_bytes",
    )
    rejected = metrics.get("d1_oosm_rejected_count")
    too_old = metrics.get("d1_oosm_too_old_count")
    overflow = metrics.get("d1_oosm_overflow_count")
    if rejected is not None and too_old is not None and overflow is not None:
        if int(too_old) + int(overflow) > int(rejected):
            _fail(
                "inconsistent_oosm_rejection_counts",
                "D1 too-old plus overflow exceeds total rejected count",
            )


def _validate_current_peak(
    metrics: Mapping[str, Any], current_name: str, peak_name: str
) -> None:
    current = metrics.get(current_name)
    peak = metrics.get(peak_name)
    if current is not None and peak is not None and int(current) > int(peak):
        _fail(
            "current_exceeds_peak",
            f"{current_name} exceeds {peak_name}",
        )


def _derive_total_memory_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for suffix in ("current", "peak"):
        output_name = f"estimated_total_{suffix}_memory_bytes"
        parts = (
            f"d1_estimated_{suffix}_memory_bytes",
            f"d2_estimated_{suffix}_memory_bytes",
        )
        missing = [
            name
            for name in parts
            if row.get(f"{name}_availability") != "available"
        ]
        if missing:
            result[output_name] = None
            result[f"{output_name}_availability"] = "unavailable"
            result[f"{output_name}_reason"] = (
                "component_unavailable:" + ",".join(missing)
            )
        else:
            result[output_name] = sum(int(row[name]) for name in parts)
            result[f"{output_name}_availability"] = "available"
            result[f"{output_name}_reason"] = None
    return result


def _aggregate_records(
    rows: Sequence[Mapping[str, Any]],
    *,
    input_spec_sha256: str,
    input_spec_created_at_utc: str,
    input_producer: str,
    admission_policy: str,
    expected_scales: Sequence[int],
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    by_scale: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_scale.setdefault(int(row["scale"]), []).append(row)

    scale_summaries: list[dict[str, Any]] = []
    numeric_metrics = tuple(
        [f"d1_{name}" for name in D1_ONLINE_METRICS]
        + [f"d2_{name}" for name in D2_ONLINE_METRICS]
        + list(DERIVED_ONLINE_METRICS)
    )
    for scale in sorted(by_scale):
        group = by_scale[scale]
        numeric_summary = {
            name: _aggregate_numeric_metric(group, name)
            for name in numeric_metrics
        }
        ratio_summary = {
            name: _aggregate_ratio_metric(
                group,
                name,
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=(
                    bootstrap_rng_seed + scale * 101 + index * 100_003
                ),
            )
            for index, name in enumerate(EVALUATOR_RATIO_METRICS)
        }
        latency_summary = _aggregate_latency_metric(group)
        durations = [float(row["duration_s"]) for row in group]
        scale_summaries.append(
            {
                "scale": scale,
                "episode_count": len(group),
                "seeds": sorted(int(row["seed"]) for row in group),
                "target_counts": sorted({int(row["target_count"]) for row in group}),
                "resource_counts": sorted({int(row["resource_count"]) for row in group}),
                "duration_s": _descriptive_stats(durations),
                "formal_episode_count": sum(
                    int(bool(row["formal_source_admitted"])) for row in group
                ),
                "online_truth_use_count": sum(
                    int(row["online_truth_use_count"]) for row in group
                ),
                "online_metrics": numeric_summary,
                "evaluator_ratio_metrics": ratio_summary,
                "confirmation_latency_s": latency_summary,
            }
        )

    provenance = [
        {
            "episode_id": row["episode_id"],
            "scale": row["scale"],
            "seed": row["seed"],
            "git_commit": row["git_commit"],
            "repository_dirty": row["repository_dirty"],
            "evidence_tier": row["evidence_tier"],
            "config_sha256": row["config_sha256"],
            "manifest_sha256": row["manifest_sha256"],
            "online_audit_sha256": row["online_audit_sha256"],
            "source_bus_sha256": row["source_bus_sha256"],
            "evaluator_sidecar_sha256": row["evaluator_sidecar_sha256"],
            "truth_artifact_sha256": row["truth_artifact_sha256"],
        }
        for row in rows
    ]
    return {
        "schema_version": OBSERVATION_GOVERNANCE_CALIBRATION_SCHEMA_VERSION,
        "evaluation_date": OBSERVATION_GOVERNANCE_CALIBRATION_DATE,
        "evaluation_mode": "offline_read_only_fail_closed",
        "input": {
            "schema_version": OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
            "sha256": input_spec_sha256,
            "created_at_utc": input_spec_created_at_utc,
            "producer": input_producer,
            "admission_policy": admission_policy,
            "expected_scales": sorted(int(value) for value in expected_scales),
        },
        "episode_count": len(rows),
        "seed_count": len({int(row["seed"]) for row in rows}),
        "scales": scale_summaries,
        "truth_isolation": {
            "online_truth_use_count": sum(
                int(row["online_truth_use_count"]) for row in rows
            ),
            "online_truth_isolation_passed": all(
                int(row["online_truth_use_count"]) == 0 for row in rows
            ),
            "truth_dependent_metrics_source": "evaluator_only_sidecar",
            "d6_reads_raw_truth": False,
        },
        "bootstrap": {
            "resamples": bootstrap_resamples,
            "rng_seed": bootstrap_rng_seed,
            "confidence_level": 0.95,
            "method": "episode_resampling_pooled_ratio_percentile",
        },
        "source_provenance_by_episode": provenance,
        "main_producer_required_json_paths": list(
            main_producer_required_json_paths()
        ),
        "control_effect": {
            "d1_control_mutated": False,
            "d2_control_mutated": False,
            "runtime_modules_imported": False,
        },
    }


def _aggregate_numeric_metric(
    rows: Sequence[Mapping[str, Any]], name: str
) -> dict[str, Any]:
    available = [row for row in rows if row.get(f"{name}_availability") == "available"]
    values = [float(row[name]) for row in available]
    reasons = _reason_counts(rows, f"{name}_reason")
    return {
        "availability": _aggregate_availability(len(available), len(rows)),
        "available_episode_count": len(available),
        "total_episode_count": len(rows),
        "mean": None if not values else float(np.mean(values)),
        "p95": None if not values else float(np.percentile(values, 95)),
        "max": None if not values else float(np.max(values)),
        "unavailability_reasons": reasons,
    }


def _aggregate_ratio_metric(
    rows: Sequence[Mapping[str, Any]],
    name: str,
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    available = [row for row in rows if row.get(f"{name}_availability") == "available"]
    reasons = _reason_counts(rows, f"{name}_reason")
    if not available:
        return {
            "availability": "unavailable",
            "available_episode_count": 0,
            "total_episode_count": len(rows),
            "numerator": None,
            "sample_count": 0,
            "rate": None,
            "bootstrap_ci95": None,
            "unavailability_reasons": reasons,
        }
    numerators = np.asarray(
        [int(row[f"{name}_numerator"]) for row in available], dtype=float
    )
    denominators = np.asarray(
        [int(row[f"{name}_denominator"]) for row in available], dtype=float
    )
    numerator = int(np.sum(numerators))
    denominator = int(np.sum(denominators))
    rate = numerator / denominator
    rng = np.random.default_rng(bootstrap_rng_seed)
    sampled_rates = np.empty(bootstrap_resamples, dtype=float)
    count = len(available)
    for index in range(bootstrap_resamples):
        selection = rng.integers(0, count, size=count)
        sampled_rates[index] = float(
            np.sum(numerators[selection]) / np.sum(denominators[selection])
        )
    return {
        "availability": _aggregate_availability(len(available), len(rows)),
        "available_episode_count": len(available),
        "total_episode_count": len(rows),
        "numerator": numerator,
        "sample_count": denominator,
        "rate": rate,
        "bootstrap_ci95": {
            "lower": float(np.percentile(sampled_rates, 2.5)),
            "upper": float(np.percentile(sampled_rates, 97.5)),
            "resamples": bootstrap_resamples,
            "rng_seed": bootstrap_rng_seed,
        },
        "unavailability_reasons": reasons,
    }


def _aggregate_latency_metric(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    available = [
        row
        for row in rows
        if row.get(f"{EVALUATOR_LATENCY_METRIC}_availability") == "available"
    ]
    samples = tuple(
        value
        for row in available
        for value in row.get("_confirmation_latency_samples_s", ())
    )
    reasons = _reason_counts(rows, f"{EVALUATOR_LATENCY_METRIC}_reason")
    return {
        "availability": _aggregate_availability(len(available), len(rows)),
        "available_episode_count": len(available),
        "total_episode_count": len(rows),
        "sample_count": len(samples),
        "mean": None if not samples else float(np.mean(samples)),
        "p95": None if not samples else float(np.percentile(samples, 95)),
        "max": None if not samples else float(np.max(samples)),
        "unavailability_reasons": reasons,
    }


def render_observation_governance_calibration_markdown(
    rows: Sequence[Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    *,
    title: str,
) -> str:
    """Render a Chinese report with explicit evidence boundaries and fields."""

    lines = [
        f"# {title}",
        "",
        "## 结论",
        "",
        (
            f"本批读取 {aggregate['episode_count']} 个 episode、"
            f"{aggregate['seed_count']} 个互异 seed。输入已通过 schema、SHA-256、"
            "episode 身份、规模、正式来源和在线真值隔离检查。"
        ),
        "D6 只读取 episode 结束后的公共制品，不导入或调用 D1/D2 控制代码。",
        "",
        "## Episode 来源",
        "",
        "| episode | 规模 | 目标 | 资源 | seed | 时长/s | 来源 | 在线真值 | 侧车 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {episode_id} | {scale} | {target_count} | {resource_count} | "
            "{seed} | {duration_s:.3f} | {tier}/{dirty} | {truth} | {sidecar} |".format(
                episode_id=row["episode_id"],
                scale=row["scale"],
                target_count=row["target_count"],
                resource_count=row["resource_count"],
                seed=row["seed"],
                duration_s=float(row["duration_s"]),
                tier=row["evidence_tier"],
                dirty="dirty" if row["repository_dirty"] else "clean",
                truth=row["online_truth_use_count"],
                sidecar=row["evaluator_sidecar_availability"],
            )
        )

    metric_labels = {
        "d1_scan_count": "D1 扫描数",
        "d1_current_oosm_buffer_count": "D1 当前乱序缓冲量",
        "d1_peak_oosm_buffer_count": "D1 峰值乱序缓冲量",
        "d1_oosm_buffered_count": "D1 进入乱序缓冲数",
        "d1_oosm_reordered_count": "D1 重排数",
        "d1_oosm_rejected_count": "D1 乱序拒绝数",
        "d1_oosm_too_old_count": "D1 过旧数",
        "d1_oosm_overflow_count": "D1 溢出数",
        "d1_oosm_eviction_count": "D1 淘汰数",
        "d1_estimated_current_memory_bytes": "D1 当前内存估算/B",
        "d1_estimated_peak_memory_bytes": "D1 峰值内存估算/B",
        "d2_current_claim_count": "D2 当前 claim 数",
        "d2_peak_claim_count": "D2 峰值 claim 数",
        "d2_claim_eviction_count": "D2 claim 淘汰数",
        "d2_claim_too_old_count": "D2 claim 过旧数",
        "d2_claim_overflow_count": "D2 claim 溢出数",
        "d2_replay_quarantine_count": "D2 重放隔离数",
        "d2_timestamp_conflict_count": "D2 时间戳冲突数",
        "d2_duplicate_coalescence_count": "D2 合并事件数",
        "d2_estimated_current_memory_bytes": "D2 当前内存估算/B",
        "d2_estimated_peak_memory_bytes": "D2 峰值内存估算/B",
        "estimated_total_current_memory_bytes": "合计当前内存估算/B",
        "estimated_total_peak_memory_bytes": "合计峰值内存估算/B",
    }
    lines.extend(["", "## 在线治理指标", ""])
    for scale_summary in aggregate["scales"]:
        lines.extend(
            [
                f"### 规模 {scale_summary['scale']}",
                "",
                "| 指标 | 可用性 | 可用 episode | 均值 | P95 | 最大值 |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, summary in scale_summary["online_metrics"].items():
            lines.append(
                f"| {metric_labels[name]} | {summary['availability']} | "
                f"{summary['available_episode_count']}/{summary['total_episode_count']} | "
                f"{_format_number(summary['mean'])} | "
                f"{_format_number(summary['p95'])} | "
                f"{_format_number(summary['max'])} |"
            )

        lines.extend(
            [
                "",
                "| evaluator-only 指标 | 可用性 | 样本数 | 比例/均值 | 95% 自助区间 | P95 | 最大值 |",
                "| --- | --- | ---: | ---: | --- | ---: | ---: |",
            ]
        )
        ratio_labels = {
            "near_neighbor_recall": "近邻目标召回率",
            "false_suppression_rate": "错误抑制率",
            "erroneous_coalescence_rate": "错误合并率",
        }
        for name, summary in scale_summary["evaluator_ratio_metrics"].items():
            ci = summary["bootstrap_ci95"]
            ci_text = (
                "unavailable"
                if ci is None
                else f"[{ci['lower']:.6f}, {ci['upper']:.6f}]"
            )
            lines.append(
                f"| {ratio_labels[name]} | {summary['availability']} | "
                f"{summary['sample_count']} | {_format_number(summary['rate'])} | "
                f"{ci_text} | - | - |"
            )
        latency = scale_summary["confirmation_latency_s"]
        lines.append(
            f"| 确认时延/s | {latency['availability']} | {latency['sample_count']} | "
            f"{_format_number(latency['mean'])} | - | "
            f"{_format_number(latency['p95'])} | {_format_number(latency['max'])} |"
        )

    lines.extend(
        [
            "",
            "## Main 写盘合同",
            "",
            "main 必须提供下列精确 JSON 路径。字段缺失、schema 不匹配或哈希链断开时，D6 拒绝整批输入。",
            "",
            "```text",
            *main_producer_required_json_paths(),
            "```",
            "",
            "## 证据边界",
            "",
            "- 在线审计只允许无真值的计数、可用性和来源字段。在线真值使用计数必须为零。",
            "- 近邻召回、错误抑制、错误合并和确认时延只读取 evaluator-only 侧车；侧车不可用时数值保持空值。",
            "- 显式零只有在 availability=available 且存在有效分母或样本时成立；unavailable 不写成零。",
            "- 本报告评估治理证据完整性和规模趋势，不证明 D1/D2 算法精度或控制效果。",
            "",
        ]
    )
    return "\n".join(lines)


def main_producer_required_json_paths() -> tuple[str, ...]:
    """Exact v1 producer fields rendered in every generated report."""

    paths = [
        "input.schema_version",
        "input.created_at_utc",
        "input.producer",
        "input.admission_policy",
        "input.expected_scales[]",
        "input.episodes[].episode.{episode_id,scale,target_count,resource_count,seed,duration_s}",
        "input.episodes[].manifest_artifact.{path,sha256}",
        "input.episodes[].online_audit_artifact.{path,sha256}",
        "input.episodes[].evaluator_sidecar.{availability,artifact,reason}",
        "manifest.schema_version",
        "manifest.episode.{episode_id,scale,target_count,resource_count,seed,duration_s}",
        "manifest.online_truth_use_count",
        "manifest.provenance.{producer,git_commit,repository_dirty,evidence_tier,config_sha256}",
        "manifest.provenance.{world_schema,bus_schema,scenario_schema,online_observation_schema}",
        "manifest.provenance.{d1_scan_oosm_audit_schema,d2_claim_ledger_audit_schema}",
        "online.schema_version",
        "online.episode.{episode_id,scale,target_count,resource_count,seed,duration_s}",
        "online.online_truth_use_count",
        "online.provenance.{producer,git_commit,config_sha256,episode_manifest_sha256}",
        "online.provenance.{source_bus_sha256,source_bus_schema}",
        "online.d1_scan_oosm_audit.schema_version",
    ]
    paths.extend(
        f"online.d1_scan_oosm_audit.metrics.{name}.{{availability,value,reason}}"
        for name in D1_ONLINE_METRICS
    )
    paths.append("online.d2_claim_ledger_audit.schema_version")
    paths.extend(
        f"online.d2_claim_ledger_audit.metrics.{name}.{{availability,value,reason}}"
        for name in D2_ONLINE_METRICS
    )
    paths.extend(
        [
            "sidecar.schema_version",
            "sidecar.evaluator_only=true",
            "sidecar.online_consumed=false",
            "sidecar.episode.{episode_id,scale,target_count,resource_count,seed,duration_s}",
            "sidecar.provenance.{producer,evaluator_git_commit,config_sha256}",
            "sidecar.provenance.{truth_schema,truth_artifact_sha256}",
            "sidecar.provenance.{episode_manifest_sha256,online_audit_sha256}",
        ]
    )
    paths.extend(
        f"sidecar.metrics.{name}.{{availability,numerator,denominator,reason}}"
        for name in EVALUATOR_RATIO_METRICS
    )
    paths.append(
        "sidecar.metrics.confirmation_latency_s.{availability,samples_s,reason}"
    )
    return tuple(paths)


def _write_per_seed_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = _per_seed_csv_fieldnames()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def _per_seed_csv_fieldnames() -> tuple[str, ...]:
    fields = [
        "episode_id",
        "scale",
        "target_count",
        "resource_count",
        "seed",
        "duration_s",
        "git_commit",
        "repository_dirty",
        "evidence_tier",
        "config_sha256",
        "world_schema",
        "bus_schema",
        "scenario_schema",
        "online_observation_schema",
        "d1_scan_oosm_audit_schema",
        "d2_claim_ledger_audit_schema",
        "manifest_sha256",
        "online_audit_sha256",
        "source_bus_sha256",
        "online_truth_use_count",
        "formal_source_admitted",
        "evaluator_sidecar_sha256",
        "evaluator_sidecar_availability",
        "evaluator_sidecar_reason",
        "evaluator_producer",
        "evaluator_git_commit",
        "truth_schema",
        "truth_artifact_sha256",
    ]
    for name in (
        [f"d1_{value}" for value in D1_ONLINE_METRICS]
        + [f"d2_{value}" for value in D2_ONLINE_METRICS]
        + list(DERIVED_ONLINE_METRICS)
    ):
        fields.extend((name, f"{name}_availability", f"{name}_reason"))
    for name in EVALUATOR_RATIO_METRICS:
        fields.extend(
            (
                name,
                f"{name}_availability",
                f"{name}_reason",
                f"{name}_numerator",
                f"{name}_denominator",
            )
        )
    fields.extend(
        (
            EVALUATOR_LATENCY_METRIC,
            f"{EVALUATOR_LATENCY_METRIC}_availability",
            f"{EVALUATOR_LATENCY_METRIC}_reason",
            f"{EVALUATOR_LATENCY_METRIC}_sample_count",
            f"{EVALUATOR_LATENCY_METRIC}_mean",
            f"{EVALUATOR_LATENCY_METRIC}_p95",
            f"{EVALUATOR_LATENCY_METRIC}_max",
        )
    )
    return tuple(fields)


def _public_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _episode_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(
        payload,
        {"episode_id", "scale", "target_count", "resource_count", "seed", "duration_s"},
        "episode identity",
    )
    scale = _positive_int(payload.get("scale"), "episode scale")
    target_count = _positive_int(payload.get("target_count"), "target_count")
    if scale != target_count:
        _fail(
            "inconsistent_scale",
            f"v1 defines scale as target_count: scale={scale}, target_count={target_count}",
        )
    return {
        "episode_id": _identifier(payload.get("episode_id"), "episode_id"),
        "scale": scale,
        "target_count": target_count,
        "resource_count": _positive_int(payload.get("resource_count"), "resource_count"),
        "seed": _nonnegative_int(payload.get("seed"), "seed"),
        "duration_s": _positive_float(payload.get("duration_s"), "duration_s"),
    }


def _assert_same_episode(
    expected: Mapping[str, Any], actual: Mapping[str, Any], context: str
) -> None:
    for field in (
        "episode_id",
        "scale",
        "target_count",
        "resource_count",
        "seed",
        "duration_s",
    ):
        if expected[field] != actual[field]:
            _fail(
                "episode_identity_mismatch",
                f"{context} {field} differs: {actual[field]!r} != {expected[field]!r}",
            )


def _artifact_reference(
    raw: Any, *, base_dir: Path, context: str
) -> tuple[Path, str]:
    payload = _mapping(raw, context)
    _require_fields(payload, {"path", "sha256"}, context)
    raw_path = _identifier(payload.get("path"), f"{context}.path")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve(), _normalise_sha256(payload.get("sha256"))


def _load_json_mapping(path: Path, context: str) -> Mapping[str, Any]:
    if not path.is_file():
        _fail("artifact_missing", f"{context} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("invalid_json", f"cannot read {context}: {exc}")
    return _mapping(payload, context)


def _verify_file_hash(path: Path, expected: str, *, artifact_name: str) -> str:
    if not path.is_file():
        _fail("artifact_missing", f"{artifact_name} does not exist: {path}")
    expected_hash = _normalise_sha256(expected)
    actual = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    if actual != expected_hash:
        _fail(
            "artifact_sha256_mismatch",
            f"{artifact_name} SHA-256 mismatch: expected={expected_hash}, actual={actual}",
        )
    return actual


def _normalise_sha256(value: Any) -> str:
    text = str(value or "").strip().lower()
    match = _SHA256_RE.fullmatch(text)
    if match is None:
        _fail("invalid_sha256", f"invalid SHA-256 value {value!r}")
    return f"sha256:{match.group(1)}"


def _git_commit(value: Any, context: str) -> str:
    text = str(value or "").strip().lower()
    if _GIT_COMMIT_RE.fullmatch(text) is None:
        _fail("invalid_git_commit", f"{context} must be a full 40-hex commit")
    return text


def _scan_online_truth_leakage(value: Any, path: str = "online") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().lower()
            if key not in _ALLOWED_TRUTH_AUDIT_KEYS:
                if key in _FORBIDDEN_ONLINE_IDENTITY_KEYS or (
                    "truth" in key and key not in _ALLOWED_TRUTH_AUDIT_KEYS
                ):
                    _fail("online_truth_leakage", f"forbidden online key {path}.{raw_key}")
            _scan_online_truth_leakage(nested, f"{path}.{raw_key}")
    elif _is_sequence(value):
        for index, nested in enumerate(value):
            _scan_online_truth_leakage(nested, f"{path}[{index}]")


def _require_schema(payload: Mapping[str, Any], expected: str, context: str) -> None:
    if payload.get("schema_version") != expected:
        _fail(
            "unsupported_schema",
            f"{context} schema must be {expected!r}, got {payload.get('schema_version')!r}",
        )


def _require_fields(
    payload: Mapping[str, Any], required: set[str], context: str
) -> None:
    missing = required - set(payload)
    if missing:
        _fail(
            "missing_required_field",
            f"{context} missing fields: {','.join(sorted(missing))}",
        )


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("invalid_mapping", f"{context} must be an object")
    return value


def _identifier(value: Any, context: str) -> str:
    text = str(value or "").strip()
    if not text:
        _fail("missing_identifier", f"{context} must be non-empty")
    return text


def _required_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        _fail("invalid_boolean", f"{context} must be boolean")
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("invalid_nonnegative_integer", f"{context} must be a non-negative integer")
    return int(value)


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    if result <= 0:
        _fail("invalid_positive_integer", f"{context} must be positive")
    return result


def _nonnegative_float(value: Any, context: str) -> float:
    if isinstance(value, bool):
        _fail("invalid_number", f"{context} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError):
        _fail("invalid_number", f"{context} must be numeric")
    if not math.isfinite(result) or result < 0.0:
        _fail("invalid_nonnegative_number", f"{context} must be finite and non-negative")
    return result


def _positive_float(value: Any, context: str) -> float:
    result = _nonnegative_float(value, context)
    if result <= 0.0:
        _fail("invalid_positive_number", f"{context} must be positive")
    return result


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _aggregate_availability(available_count: int, total_count: int) -> str:
    if available_count == 0:
        return "unavailable"
    if available_count == total_count:
        return "available"
    return "partial"


def _reason_counts(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = row.get(field)
        if reason:
            key = str(reason)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _descriptive_stats(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def _format_number(value: Any) -> str:
    if value is None:
        return "unavailable"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}"


def _fail(code: str, message: str) -> None:
    raise ObservationGovernanceCalibrationError(code, message)
