"""Main-owned, truth-isolated offline evaluation artifact wiring."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .episode_bus import VersionedEnvelope
from .models import OfflineTruthLabel


OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-offline-identity-evaluation-manifest-v1"
)
OFFLINE_CONSISTENCY_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-offline-consistency-evaluation-manifest-v1"
)


@dataclass(frozen=True)
class PrewrittenIdentityRecordPaths:
    """Identity record views serialized with the authoritative online bus."""

    d1_path: Path
    d2_path: Path
    d1_record_count: int
    d2_record_count: int


def write_offline_identity_evaluation(
    output_dir: str | Path,
    *,
    episode_id: str,
    messages: Iterable[VersionedEnvelope],
    offline_truth_labels: Iterable[OfflineTruthLabel],
    lineage_time_window_s: float = 1.0,
    truth_presence_window_s: float = 1.0,
    prewritten_records: PrewrittenIdentityRecordPaths | None = None,
) -> dict[str, Path]:
    """Persist D2 identity evidence and evaluator truth as separate artifacts."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    message_items = tuple(messages)
    d1_messages = tuple(
        item for item in message_items if item.topic == "modules.d1.fused_tracks"
    )
    d2_messages = tuple(
        item for item in message_items if item.topic == "modules.d2.associated_tracks"
    )
    manifest_path = root / "manifest.json"
    if not d1_messages or not d2_messages:
        _write_json(
            manifest_path,
            {
                "schema_version": OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION,
                "available": False,
                "reason": "d1_or_d2_online_records_unavailable",
                "episode_id": str(episode_id),
                "d1_record_count": len(d1_messages),
                "d2_record_count": len(d2_messages),
                "evidence_record_count": 0,
                "source_hashes": {},
            },
        )
        return {"offline_identity_manifest": manifest_path}

    from research_modules.d2_data_association.d2_data_association import (
        GlobalTrackLineageEvidence,
        ObservationLineageRef,
        Scalable3DObservationTruthLabel,
        create_scalable_3d_identity_evidence_bundle,
        evaluate_scalable_3d_identity_files,
        sha256_file,
        write_scalable_3d_identity_evaluation,
        write_scalable_3d_identity_evidence,
        write_scalable_3d_observation_truth_labels,
    )

    if prewritten_records is None:
        d1_path = _write_message_jsonl(root / "online_d1_records.jsonl", d1_messages)
        d2_path = _write_message_jsonl(root / "online_d2_records.jsonl", d2_messages)
    else:
        if prewritten_records.d1_record_count != len(d1_messages):
            raise ValueError("prewritten D1 record count does not match online messages")
        if prewritten_records.d2_record_count != len(d2_messages):
            raise ValueError("prewritten D2 record count does not match online messages")
        d1_path = Path(prewritten_records.d1_path)
        d2_path = Path(prewritten_records.d2_path)
        if not d1_path.is_file() or not d2_path.is_file():
            raise FileNotFoundError("prewritten identity record view is missing")
        if d1_path.resolve() == d2_path.resolve():
            raise ValueError("prewritten D1 and D2 record views must be separate files")
    truth_records = tuple(
        Scalable3DObservationTruthLabel(
            observation_id=item.observation_id,
            truth_target_id=item.truth_entity_id,
            measurement_timestamp=item.measurement_timestamp,
            disposition=item.disposition,
        )
        for item in offline_truth_labels
    )
    truth_path = root / "observation_truth_labels.jsonl"
    truth_sha = write_scalable_3d_observation_truth_labels(
        truth_path,
        truth_records,
    )
    d1_sha = sha256_file(d1_path)
    d2_sha = sha256_file(d2_path)
    d1_sequences_by_observation = _d1_sequences_by_observation(d1_messages)
    evidence_records, incomplete_count = _identity_evidence_records(
        episode_id=str(episode_id),
        d2_messages=d2_messages,
        d1_sequences_by_observation=d1_sequences_by_observation,
        evidence_type=GlobalTrackLineageEvidence,
        observation_type=ObservationLineageRef,
    )
    if not evidence_records:
        _write_json(
            manifest_path,
            {
                "schema_version": OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION,
                "available": False,
                "reason": "d2_track_frame_evidence_unavailable",
                "episode_id": str(episode_id),
                "d1_record_count": len(d1_messages),
                "d2_record_count": len(d2_messages),
                "evidence_record_count": 0,
                "lineage_incomplete_record_count": incomplete_count,
                "truth_label_count": len(truth_records),
                "source_hashes": {
                    "online_d1_records": d1_sha,
                    "online_d2_records": d2_sha,
                    "observation_truth_labels": truth_sha,
                },
                "online_truth_isolation_verified": False,
                "identity_metrics_available": False,
            },
        )
        return {
            "offline_identity_manifest": manifest_path,
            "offline_identity_d1_records": d1_path,
            "offline_identity_d2_records": d2_path,
            "offline_identity_truth_labels": truth_path,
        }
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id=str(episode_id),
        records=evidence_records,
        online_d1_records_sha256=d1_sha,
        online_d2_records_sha256=d2_sha,
        observation_truth_labels_sha256=truth_sha,
    )
    evidence_path = root / "identity_evidence.json"
    evidence_sha = write_scalable_3d_identity_evidence(evidence_path, bundle)
    evaluation = evaluate_scalable_3d_identity_files(
        evidence_path=evidence_path,
        expected_evidence_sha256=evidence_sha,
        online_d1_records_path=d1_path,
        online_d2_records_path=d2_path,
        observation_truth_labels_path=truth_path,
        lineage_time_window_s=float(lineage_time_window_s),
        truth_presence_window_s=float(truth_presence_window_s),
    )
    evaluation_path = root / "identity_evaluation.json"
    evaluation_sha = write_scalable_3d_identity_evaluation(
        evaluation_path,
        evaluation,
    )
    source_hashes = {
        "online_d1_records": d1_sha,
        "online_d2_records": d2_sha,
        "observation_truth_labels": truth_sha,
        "identity_evidence": evidence_sha,
        "identity_evaluation": evaluation_sha,
    }
    _write_json(
        manifest_path,
        {
            "schema_version": OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION,
            "available": True,
            "reason": None,
            "episode_id": str(episode_id),
            "d1_record_count": len(d1_messages),
            "d2_record_count": len(d2_messages),
            "evidence_record_count": len(evidence_records),
            "lineage_incomplete_record_count": incomplete_count,
            "truth_label_count": len(truth_records),
            "source_hashes": source_hashes,
            "online_truth_isolation_verified": bool(
                evaluation.audit.get("online_truth_isolation_verified", False)
            ),
            "identity_metrics_available": bool(evaluation.metrics.available),
        },
    )
    return {
        "offline_identity_manifest": manifest_path,
        "offline_identity_d1_records": d1_path,
        "offline_identity_d2_records": d2_path,
        "offline_identity_truth_labels": truth_path,
        "offline_identity_evidence": evidence_path,
        "offline_identity_evaluation": evaluation_path,
    }


def write_offline_consistency_evaluation(
    output_dir: str | Path,
    *,
    manifest: Any,
    consistency_records: Iterable[Any],
    identity_evaluation_path: str | Path | None,
    online_source_path: str | Path,
    truth_state_source_path: str | Path,
    intruder_ids: Sequence[str],
    timestamps: Sequence[float] | np.ndarray,
    intruder_state_history: np.ndarray,
    timestamp_tolerance_s: float = 1.0e-8,
) -> dict[str, Path]:
    """Persist D1 consistency evidence and score it through D2-only identity mapping."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    records = tuple(consistency_records)
    if not records:
        _write_json(
            manifest_path,
            {
                "schema_version": OFFLINE_CONSISTENCY_MANIFEST_SCHEMA_VERSION,
                "available": False,
                "status": "unavailable",
                "reason": "d1_consistency_evidence_unavailable",
                "episode_id": str(manifest.episode_id),
                "online_evidence_record_count": 0,
                "source_hashes": {},
            },
        )
        return {"offline_consistency_manifest": manifest_path}

    from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
        ConsistencySourceProvenance,
        D2LineageTruthMapping,
        build_d2_lineage_mapping_sidecar,
        build_offline_truth_state_sidecar,
        evaluate_offline_consistency,
        export_online_consistency_evidence,
    )
    from research_modules.d2_data_association.d2_data_association import (
        load_scalable_3d_identity_evaluation,
    )

    tolerance = float(timestamp_tolerance_s)
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("timestamp_tolerance_s must be finite and non-negative")
    config_digest = _prefixed_sha256(manifest.config_sha256)
    online_source_sha = _sha256_file(online_source_path)
    truth_state_source_sha = _sha256_file(truth_state_source_path)

    evidence_provenance = ConsistencySourceProvenance(
        scenario_id=str(manifest.scenario_name),
        scenario_version=str(manifest.scenario_version),
        run_id=str(manifest.episode_id),
        seed=int(manifest.seed),
        producer_id="d1_sensor_fusion.scalable_3d",
        producer_version=str(manifest.d1_model_version),
        source_schema_version=str(manifest.bus_schema),
        source_digest=online_source_sha,
        config_digest=config_digest,
    )
    evidence = export_online_consistency_evidence(records, evidence_provenance)
    evidence_path = _write_json(root / "online_evidence.json", evidence.to_dict())
    online_rows_path = _write_jsonl(
        root / "online_aggregation.jsonl",
        evidence.aggregation_records(),
    )

    truth_provenance = ConsistencySourceProvenance(
        scenario_id=str(manifest.scenario_name),
        scenario_version=str(manifest.scenario_version),
        run_id=str(manifest.episode_id),
        seed=int(manifest.seed),
        producer_id="main.scalable_3d_truth_state",
        producer_version=str(manifest.world_schema),
        source_schema_version=str(manifest.offline_truth_schema),
        source_digest=truth_state_source_sha,
        config_digest=config_digest,
    )
    truth_samples = _truth_samples_for_consistency_records(
        records=records,
        timestamps=timestamps,
        intruder_ids=intruder_ids,
        intruder_state_history=intruder_state_history,
        timestamp_tolerance_s=tolerance,
    )
    truth_sidecar = build_offline_truth_state_sidecar(
        truth_provenance,
        truth_samples,
    )
    truth_path = _write_json(root / "truth_state_sidecar.json", truth_sidecar.to_dict())

    identity_evaluation = None
    identity_sha = None
    mapping_records: tuple[Any, ...] = ()
    mapping_audit: dict[str, Any] = {
        "available": False,
        "reason": "d2_identity_evaluation_unavailable",
    }
    identity_path = None if identity_evaluation_path is None else Path(identity_evaluation_path)
    if identity_path is not None and identity_path.is_file():
        identity_sha = _sha256_file(identity_path)
        identity_evaluation = load_scalable_3d_identity_evaluation(
            identity_path,
            expected_sha256=identity_sha,
        )
        mapping_records, mapping_audit = _canonical_mappings_from_d2_identity(
            records=records,
            identity_evaluation=identity_evaluation,
            mapping_type=D2LineageTruthMapping,
        )

    d2_lineage_mapping = None
    mapping_path: Path | None = None
    if mapping_records and identity_evaluation is not None and identity_sha is not None:
        mapping_provenance = ConsistencySourceProvenance(
            scenario_id=str(manifest.scenario_name),
            scenario_version=str(manifest.scenario_version),
            run_id=str(manifest.episode_id),
            seed=int(manifest.seed),
            producer_id="d2_data_association.scalable_3d_identity",
            producer_version=str(identity_evaluation.policy_version),
            source_schema_version=str(identity_evaluation.schema_version),
            source_digest=identity_sha,
            config_digest=config_digest,
        )
        d2_lineage_mapping = build_d2_lineage_mapping_sidecar(
            mapping_provenance,
            mapping_records,
            online_evidence_digest=evidence.content_digest,
            truth_sidecar_digest=truth_sidecar.content_digest,
        )
        mapping_path = _write_json(
            root / "d2_lineage_mapping.json",
            d2_lineage_mapping.to_dict(),
        )

    result = evaluate_offline_consistency(
        evidence,
        truth_sidecar,
        d2_lineage_mapping,
        timestamp_tolerance_s=tolerance,
    )
    result_path = _write_json(root / "offline_result.json", result.to_dict())
    offline_rows_path = _write_jsonl(
        root / "offline_aggregation.jsonl",
        result.aggregation_records(),
    )
    source_hashes = {
        "online_source": online_source_sha,
        "truth_state_source": truth_state_source_sha,
        "online_evidence": _sha256_file(evidence_path),
        "online_aggregation": _sha256_file(online_rows_path),
        "truth_state_sidecar": _sha256_file(truth_path),
        "offline_result": _sha256_file(result_path),
        "offline_aggregation": _sha256_file(offline_rows_path),
    }
    if identity_sha is not None:
        source_hashes["identity_evaluation"] = identity_sha
    if mapping_path is not None:
        source_hashes["d2_lineage_mapping"] = _sha256_file(mapping_path)

    truth_metric_names = (
        "position_rmse_m",
        "velocity_rmse_mps",
        "mean_nees",
        "mean_normalized_nees",
    )
    nis_metric_names = (
        "mean_nis",
        "mean_normalized_nis",
        "nis_gate_coverage",
    )
    _write_json(
        manifest_path,
        {
            "schema_version": OFFLINE_CONSISTENCY_MANIFEST_SCHEMA_VERSION,
            "available": result.status == "available",
            "status": result.status,
            "reason": None if result.status == "available" else "consistency_metrics_partial",
            "episode_id": str(manifest.episode_id),
            "timestamp_tolerance_s": tolerance,
            "online_evidence_record_count": len(evidence.records),
            "truth_state_sample_count": len(truth_sidecar.samples),
            "d2_lineage_mapping_count": len(mapping_records),
            "mapping_audit": mapping_audit,
            "truth_metrics_available": all(
                result.metrics[name].available for name in truth_metric_names
            ),
            "nis_metrics_available": all(
                result.metrics[name].available for name in nis_metric_names
            ),
            "failure_reasons": list(result.failure_reasons),
            "input_digests": {
                "online_evidence": result.online_evidence_digest,
                "truth_sidecar": result.truth_sidecar_digest,
                "d2_lineage_mapping": result.d2_lineage_mapping_digest,
            },
            "source_hashes": dict(sorted(source_hashes.items())),
        },
    )
    paths = {
        "offline_consistency_manifest": manifest_path,
        "offline_consistency_online_evidence": evidence_path,
        "offline_consistency_online_aggregation": online_rows_path,
        "offline_consistency_truth_state": truth_path,
        "offline_consistency_result": result_path,
        "offline_consistency_aggregation": offline_rows_path,
    }
    if mapping_path is not None:
        paths["offline_consistency_d2_lineage_mapping"] = mapping_path
    return paths


def _d1_sequences_by_observation(
    messages: Sequence[VersionedEnvelope],
) -> dict[str, tuple[int, ...]]:
    sequences: dict[str, set[int]] = {}
    for message in messages:
        payload = _mapping(message.payload, "D1 publication payload")
        for raw in payload.get("observation_lineage", ()):
            item = _mapping(raw, "D1 observation lineage")
            observation_id = str(item["observation_id"])
            sequences.setdefault(observation_id, set()).add(int(message.sequence))
    return {
        observation_id: tuple(sorted(values))
        for observation_id, values in sequences.items()
    }


def _identity_evidence_records(
    *,
    episode_id: str,
    d2_messages: Sequence[VersionedEnvelope],
    d1_sequences_by_observation: Mapping[str, tuple[int, ...]],
    evidence_type: Any,
    observation_type: Any,
) -> tuple[tuple[Any, ...], int]:
    records = []
    incomplete_count = 0
    for frame_index, message in enumerate(d2_messages):
        payload = _mapping(message.payload, "D2 publication payload")
        association = _mapping(payload.get("association"), "D2 association payload")
        frame_timestamp = float(association["timestamp"])
        for raw in payload.get("identity_lineage", ()):
            item = _mapping(raw, "D2 identity lineage")
            observations = tuple(
                observation_type.from_mapping(
                    _mapping(value, "D2 source observation lineage")
                )
                for value in item.get("source_observations", ())
            )
            d1_sequences = tuple(
                sorted(
                    {
                        sequence
                        for observation in observations
                        for sequence in d1_sequences_by_observation.get(
                            observation.observation_id,
                            (),
                        )
                    }
                )
            )
            association_state = str(item["association_state"]).strip().lower()
            if association_state in {"created", "matched"} and (
                not observations or not d1_sequences
            ):
                incomplete_count += 1
            records.append(
                evidence_type(
                    episode_id=episode_id,
                    frame_index=frame_index,
                    frame_timestamp=frame_timestamp,
                    global_track_id=str(item["global_track_id"]),
                    lifecycle_state=str(item["lifecycle_state"]),
                    association_state=association_state,
                    source_observations=observations,
                    d1_record_sequences=d1_sequences,
                    d2_record_sequence=int(message.sequence),
                )
            )
    return tuple(records), incomplete_count


def _truth_samples_for_consistency_records(
    *,
    records: Sequence[Any],
    timestamps: Sequence[float] | np.ndarray,
    intruder_ids: Sequence[str],
    intruder_state_history: np.ndarray,
    timestamp_tolerance_s: float,
) -> tuple[dict[str, Any], ...]:
    timeline = np.asarray(timestamps, dtype=float).reshape(-1)
    states = np.asarray(intruder_state_history, dtype=float)
    truth_ids = tuple(str(item) for item in intruder_ids)
    if states.shape != (timeline.size, len(truth_ids), 6):
        raise ValueError("intruder truth history shape does not match timeline and IDs")
    if not np.all(np.isfinite(timeline)) or not np.all(np.isfinite(states)):
        raise ValueError("intruder truth history must contain only finite values")
    estimate_times = sorted(
        {
            float(record.estimate_timestamp)
            for record in records
            if record.availability.estimate.available
            and record.estimate_timestamp is not None
        }
    )
    if not estimate_times:
        raise ValueError("D1 consistency evidence contains no available estimates")
    samples: list[dict[str, Any]] = []
    for estimate_time in estimate_times:
        indices = np.flatnonzero(
            np.abs(timeline - estimate_time) <= timestamp_tolerance_s
        )
        if indices.size != 1:
            raise ValueError(
                "D1 estimate timestamp is missing or ambiguous in offline truth history"
            )
        state_row = states[int(indices[0])]
        for truth_id, state in zip(truth_ids, state_row):
            samples.append(
                {
                    "truth_id": truth_id,
                    "timestamp": estimate_time,
                    "state_ned": state.tolist(),
                }
            )
    return tuple(samples)


def _canonical_mappings_from_d2_identity(
    *,
    records: Sequence[Any],
    identity_evaluation: Any,
    mapping_type: Any,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Join D1 estimates to evaluator-only D2 identity by exact observation lineage."""

    estimate_records = tuple(
        record
        for record in records
        if record.availability.estimate.available
        and record.source_global_track_id is not None
        and record.estimate_timestamp is not None
    )
    records_by_observation: dict[str, Any] = {}
    duplicate_observations: set[str] = set()
    for record in estimate_records:
        observation_id = str(record.observation_id)
        if observation_id in records_by_observation:
            duplicate_observations.add(observation_id)
        records_by_observation[observation_id] = record

    audit: dict[str, Any] = {
        "available": False,
        "reason": None,
        "policy": "d2_source_observation_exact_join_v1",
        "identity_metrics_available": bool(identity_evaluation.metrics.available),
        "online_truth_isolation_verified": bool(
            identity_evaluation.audit.get(
                "online_truth_isolation_verified",
                False,
            )
        ),
        "d1_estimate_observation_count": len(estimate_records),
        "direct_claim_count": 0,
        "missing_observation_ids": [],
        "conflicting_observation_ids": sorted(duplicate_observations),
    }
    if not audit["online_truth_isolation_verified"]:
        audit["reason"] = "d2_online_truth_isolation_not_verified"
        return (), audit
    if not audit["identity_metrics_available"]:
        audit["reason"] = "d2_identity_metrics_unavailable"
        return (), audit

    claims: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for frame in identity_evaluation.frames:
        for item in frame.mappings:
            if item.status != "available" or item.truth_target_id is None:
                continue
            truth_id = str(item.truth_target_id)
            for observation_id in item.source_observation_ids:
                record = records_by_observation.get(str(observation_id))
                if record is None:
                    continue
                claims[str(observation_id)].add(
                    (str(item.global_track_id), truth_id)
                )
                audit["direct_claim_count"] += 1

    mappings: list[Any] = []
    missing: list[str] = []
    conflicting = set(duplicate_observations)
    for observation_id, record in sorted(records_by_observation.items()):
        observation_claims = claims.get(observation_id, set())
        if not observation_claims:
            missing.append(observation_id)
            continue
        if len(observation_claims) != 1:
            conflicting.add(observation_id)
            continue
        global_track_id, truth_id = next(iter(observation_claims))
        mappings.append(
            mapping_type(
                observation_id=observation_id,
                measurement_timestamp=float(record.measurement_timestamp),
                global_track_id=global_track_id,
                truth_id=truth_id,
            )
        )

    audit["missing_observation_ids"] = missing
    audit["conflicting_observation_ids"] = sorted(conflicting)
    audit["d2_lineage_mapping_count"] = len(mappings)
    audit["mapped_observation_count"] = len(
        {item.observation_id for item in mappings}
    )
    audit["available"] = not missing and not conflicting and bool(mappings)
    if missing:
        audit["reason"] = "d1_observations_missing_d2_lineage_mapping"
    elif conflicting:
        audit["reason"] = "d2_observation_lineage_mapping_conflict"
    elif not mappings:
        audit["reason"] = "d2_lineage_mapping_empty"
    return tuple(mappings), audit


def _write_message_jsonl(
    path: Path,
    messages: Sequence[VersionedEnvelope],
) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for message in messages:
            stream.write(
                json.dumps(
                    message.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return path


def _write_jsonl(path: Path, payloads: Iterable[Mapping[str, Any]]) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for payload in payloads:
            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _prefixed_sha256(value: Any) -> str:
    text = str(value).strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("config digest must be a SHA-256 hexadecimal value")
    return f"sha256:{text}"


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


__all__ = [
    "OFFLINE_CONSISTENCY_MANIFEST_SCHEMA_VERSION",
    "OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION",
    "PrewrittenIdentityRecordPaths",
    "write_offline_consistency_evaluation",
    "write_offline_identity_evaluation",
]
