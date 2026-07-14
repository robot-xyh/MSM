"""Deterministic truth-free P1 stress transforms for D1 governed replays."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from math import pi
from typing import Any

import numpy as np

from .d1_governed_adapter import (
    D1_GOVERNED_MANIFEST_SCHEMA,
    D1_OBSERVATION_SCHEMA,
    is_d1_governed_replay_payload,
)
from .p1_identity_calibration import (
    SCENARIO_DIFFICULTIES,
    TARGET_SPACING_BY_DIFFICULTY_M,
    TARGET_SPACING_TOLERANCE_M,
    scenario_difficulty_metadata,
)


P1_REPLAY_STRESS_SCHEMA_VERSION = "d2-p1-governed-replay-stress/v1"
_RADAR_MODALITY = "radar"
_TRUTH_KEYS = {
    "ground_truth",
    "offline_truth",
    "truth_id",
    "ground_truth_id",
    "offline_truth_id",
    "truth_label",
    "offline_truth_label",
    "truth_position",
    "ground_truth_position",
    "offline_truth_position",
    "truth_state",
    "offline_truth_state",
    "actor_name",
    "sim_truth_id",
}


@dataclass(frozen=True, slots=True)
class GovernedReplayStressResult:
    """One transformed online-safe D1 bundle and its audit metadata."""

    payload: dict[str, Any]
    profile_metadata: dict[str, Any]
    statistics: dict[str, Any]
    input_digest: str
    output_digest: str
    online_truth_leak_count: int
    schema_version: str = P1_REPLAY_STRESS_SCHEMA_VERSION

    def to_dict(self, *, include_payload: bool = True) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "profile_metadata": deepcopy(self.profile_metadata),
            "statistics": deepcopy(self.statistics),
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "online_truth_leak_count": self.online_truth_leak_count,
        }
        if include_payload:
            result["payload"] = deepcopy(self.payload)
        return result


def transform_d1_governed_replay(
    payload: Mapping[str, Any],
    *,
    scenario_difficulty: str,
    seed: int,
    declared_target_spacing_m: float,
) -> GovernedReplayStressResult:
    """Apply one deterministic observation-only stress profile.

    The transformer never accepts or reads an offline truth sidecar. Geometry
    is immutable: spacing is a required capture declaration, not an inferred
    or synthesized target state.
    """

    if not is_d1_governed_replay_payload(payload):
        raise ValueError("payload is not a supported D1 governed replay bundle")
    difficulty = _normalize_difficulty(scenario_difficulty)
    spacing = _validate_spacing_declaration(
        payload,
        difficulty=difficulty,
        declared_target_spacing_m=declared_target_spacing_m,
    )
    input_payload = deepcopy(dict(payload))
    input_leaks = _online_truth_leak_count(input_payload)
    if input_leaks:
        raise ValueError(
            f"D1 governed replay contains {input_leaks} online truth field(s)"
        )
    input_digest = _stable_digest(input_payload)
    records = [deepcopy(dict(record)) for record in input_payload["records"]]
    _validate_records(records)
    rng = np.random.default_rng(int(seed))
    statistics: dict[str, Any] = {
        "input_record_count": len(records),
        "input_radar_record_count": _radar_record_count(records),
        "dropped_radar_record_count": 0,
        "injected_clutter_record_count": 0,
        "delayed_radar_record_count": 0,
        "covariance_inflated_record_count": 0,
    }
    actual_parameters: dict[str, Any] = {}

    if difficulty in {"dropout", "combined"}:
        records, dropout_parameters, dropped = _apply_dropout(records, rng=rng)
        actual_parameters.update(dropout_parameters)
        statistics["dropped_radar_record_count"] = dropped

    if difficulty in {"clutter", "combined"}:
        injected, clutter_parameters = _build_clutter_records(
            input_payload["records"],
            rng=rng,
            seed=int(seed),
            difficulty=difficulty,
            input_digest=input_digest,
        )
        records.extend(injected)
        actual_parameters.update(clutter_parameters)
        statistics["injected_clutter_record_count"] = len(injected)

    if difficulty in {"delayed_noisy", "combined"}:
        records, delay_parameters, delayed_count = _apply_delay_and_noise(
            records,
            rng=rng,
            difficulty=difficulty,
            seed=int(seed),
        )
        actual_parameters.update(delay_parameters)
        statistics["delayed_radar_record_count"] = delayed_count
        statistics["covariance_inflated_record_count"] = delayed_count

    records.sort(
        key=lambda record: (
            float(record["arrival_timestamp"]),
            float(record["measurement_timestamp"]),
            str(record["observation_id"]),
        )
    )
    profile_metadata = {
        "schema_version": P1_REPLAY_STRESS_SCHEMA_VERSION,
        **scenario_difficulty_metadata(difficulty),
        "seed": int(seed),
        "declared_target_spacing_m": spacing,
        "expected_target_spacing_m": TARGET_SPACING_BY_DIFFICULTY_M[difficulty],
        "target_spacing_tolerance_m": TARGET_SPACING_TOLERANCE_M,
        "spacing_validation": "capture_declaration_only_no_truth_geometry",
        "geometry_modified": False,
        "truth_sidecar_consumed": False,
        "actual_parameters": actual_parameters,
        "input_digest": input_digest,
    }
    profile_digest = _stable_digest(profile_metadata)
    profile_metadata["profile_digest"] = profile_digest
    transformed = {
        "manifest": _rebuild_manifest(
            input_payload["manifest"],
            records,
            profile_metadata=profile_metadata,
        ),
        "records": records,
    }
    output_leaks = _online_truth_leak_count(transformed)
    if output_leaks:
        raise RuntimeError("stress transform introduced online truth fields")
    statistics.update(
        {
            "output_record_count": len(records),
            "output_radar_record_count": _radar_record_count(records),
            "retained_non_radar_record_count": sum(
                str(record.get("modality", "")).lower() != _RADAR_MODALITY
                for record in records
            ),
            "online_truth_leak_count": output_leaks,
        }
    )
    output_digest = _stable_digest(transformed)
    return GovernedReplayStressResult(
        payload=transformed,
        profile_metadata=profile_metadata,
        statistics=statistics,
        input_digest=input_digest,
        output_digest=output_digest,
        online_truth_leak_count=output_leaks,
    )


def _apply_dropout(
    records: Sequence[dict[str, Any]], *, rng: np.random.Generator
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    radar_timestamps = sorted(
        {
            float(record["measurement_timestamp"])
            for record in records
            if str(record.get("modality", "")).lower() == _RADAR_MODALITY
        }
    )
    if not radar_timestamps:
        raise ValueError("dropout profile requires radar records")
    duration = float(rng.uniform(0.6, 1.2))
    center = 0.5 * (radar_timestamps[0] + radar_timestamps[-1])
    start = center - 0.5 * duration
    end = center + 0.5 * duration
    retained: list[dict[str, Any]] = []
    dropped = 0
    for record in records:
        is_radar = str(record.get("modality", "")).lower() == _RADAR_MODALITY
        timestamp = float(record["measurement_timestamp"])
        if is_radar and start <= timestamp <= end:
            dropped += 1
            continue
        retained.append(record)
    if dropped == 0:
        raise ValueError("dropout interval did not overlap a radar measurement")
    if not any(
        str(record.get("modality", "")).lower() == _RADAR_MODALITY
        for record in retained
    ):
        raise ValueError("dropout profile would remove all radar observations")
    return (
        retained,
        {
            "dropout_center_measurement_timestamp": center,
            "dropout_start_measurement_timestamp": start,
            "dropout_end_measurement_timestamp": end,
            "dropout_duration_s": duration,
        },
        dropped,
    )


def _build_clutter_records(
    source_records: Sequence[Mapping[str, Any]],
    *,
    rng: np.random.Generator,
    seed: int,
    difficulty: str,
    input_digest: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[float, int | None], list[Mapping[str, Any]]] = defaultdict(list)
    for record in source_records:
        if str(record.get("modality", "")).lower() != _RADAR_MODALITY:
            continue
        metadata = record.get("metadata", {})
        frame_index = (
            int(metadata["airsim_frame_index"])
            if isinstance(metadata, Mapping)
            and metadata.get("airsim_frame_index") is not None
            else None
        )
        grouped[(float(record["measurement_timestamp"]), frame_index)].append(record)
    if not grouped:
        raise ValueError("clutter profile requires radar records")
    injected: list[dict[str, Any]] = []
    count_by_frame: dict[str, int] = {}
    lineage_digest = input_digest.removeprefix("sha256:")[:16]
    for frame_number, ((timestamp, frame_index), templates) in enumerate(
        sorted(grouped.items())
    ):
        count = int(rng.integers(1, 4))
        count_by_frame[str(frame_index if frame_index is not None else frame_number)] = count
        for clutter_index in range(count):
            template = templates[clutter_index % len(templates)]
            measurement = np.asarray(template["measurement"], dtype=float).reshape(-1)
            covariance = np.asarray(template["covariance"], dtype=float)
            if measurement.size < 3 or covariance.ndim != 2:
                raise ValueError("radar template has invalid measurement/covariance")
            generated = measurement.copy()
            generated[0] = max(1.0, float(measurement[0]) * rng.uniform(0.65, 1.35))
            generated[1] = float(rng.uniform(-pi, pi))
            generated[2] = float(np.clip(rng.normal(measurement[2], 0.08), -0.5, 0.5))
            if generated.size > 3:
                generated[3] = float(rng.normal(0.0, 2.0))
            original_delay = float(template["arrival_timestamp"]) - float(
                template["measurement_timestamp"]
            )
            arrival = timestamp + max(0.0, original_delay)
            opaque_id = (
                f"d2-injected-clutter-{lineage_digest}-{seed:08x}-"
                f"{frame_number:06d}-{clutter_index:02d}"
            )
            scenario_marker = {
                "schema_version": P1_REPLAY_STRESS_SCHEMA_VERSION,
                "scenario_difficulty": difficulty,
                "injection_type": "anonymous_radar_clutter",
                "anonymous": True,
                "seed": seed,
            }
            source_metadata = template.get("metadata", {})
            sensor_position = (
                deepcopy(source_metadata.get("sensor_position_ned"))
                if isinstance(source_metadata, Mapping)
                else None
            )
            metadata: dict[str, Any] = {
                "injected_evaluator_scenario": scenario_marker,
                "measurement_timestamp": timestamp,
                "arrival_timestamp": arrival,
                "source_record_digest": input_digest,
            }
            if frame_index is not None:
                metadata["airsim_frame_index"] = frame_index
            if sensor_position is not None:
                metadata["sensor_position_ned"] = sensor_position
            injected.append(
                {
                    "schema_version": D1_OBSERVATION_SCHEMA,
                    "observation_id": opaque_id,
                    "sensor_id": "D2-INJECTED-RADAR-CLUTTER",
                    "modality": _RADAR_MODALITY,
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": arrival,
                    "frame_id": str(template.get("frame_id", "ned")),
                    "working_frame": str(template.get("working_frame", "ned")),
                    "measurement": generated.tolist(),
                    "covariance": covariance.tolist(),
                    "confidence": float(rng.uniform(0.15, 0.55)),
                    "classification_hint": None,
                    "quality_flags": ["injected_anonymous_clutter"],
                    "coverage_cell": "cell-injected-clutter",
                    "metadata": metadata,
                    "source_lineage": [
                        "d2_p1_offline_stress",
                        input_digest,
                        difficulty,
                        seed,
                        frame_number,
                        clutter_index,
                        "anonymous_clutter",
                    ],
                }
            )
    return injected, {
        "clutter_count_range_per_frame": [1, 3],
        "clutter_count_by_frame": count_by_frame,
    }


def _apply_delay_and_noise(
    records: Sequence[dict[str, Any]],
    *,
    rng: np.random.Generator,
    difficulty: str,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    transformed: list[dict[str, Any]] = []
    delays: list[float] = []
    for record in records:
        if str(record.get("modality", "")).lower() != _RADAR_MODALITY:
            transformed.append(record)
            continue
        updated = deepcopy(record)
        extra_delay = float(rng.uniform(0.2, 0.5))
        delays.append(extra_delay)
        original_arrival = float(updated["arrival_timestamp"])
        new_arrival = original_arrival + extra_delay
        updated["arrival_timestamp"] = new_arrival
        covariance = np.asarray(updated["covariance"], dtype=float)
        updated["covariance"] = (covariance * 3.0).tolist()
        metadata = updated.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        metadata = deepcopy(dict(metadata))
        metadata["pre_transform_arrival_timestamp"] = original_arrival
        metadata["arrival_timestamp"] = new_arrival
        metadata["injected_evaluator_scenario"] = {
            "schema_version": P1_REPLAY_STRESS_SCHEMA_VERSION,
            "scenario_difficulty": difficulty,
            "injection_type": "radar_delay_and_covariance_inflation",
            "extra_delay_s": extra_delay,
            "covariance_scale": 3.0,
            "seed": seed,
        }
        if metadata.get("received_timestamp") is not None:
            metadata["received_timestamp"] = float(metadata["received_timestamp"]) + extra_delay
        updated["metadata"] = metadata
        communication = updated.get("communication")
        if isinstance(communication, Mapping):
            communication = deepcopy(dict(communication))
            if communication.get("received_timestamp") is not None:
                communication["received_timestamp"] = (
                    float(communication["received_timestamp"]) + extra_delay
                )
            updated["communication"] = communication
        quality_flags = list(updated.get("quality_flags") or [])
        quality_flags.extend(["injected_delay", "injected_covariance_inflation"])
        updated["quality_flags"] = list(dict.fromkeys(quality_flags))
        lineage = list(updated.get("source_lineage") or [])
        lineage.extend(
            [
                "d2_p1_offline_stress",
                difficulty,
                seed,
                "delay_and_covariance_inflation",
            ]
        )
        updated["source_lineage"] = lineage
        transformed.append(updated)
    if not delays:
        raise ValueError("delayed_noisy profile requires radar records")
    return transformed, {
        "extra_delay_range_s": [min(delays), max(delays)],
        "configured_extra_delay_range_s": [0.2, 0.5],
        "covariance_scale": 3.0,
    }, len(delays)


def _validate_spacing_declaration(
    payload: Mapping[str, Any],
    *,
    difficulty: str,
    declared_target_spacing_m: float,
) -> float:
    spacing = float(declared_target_spacing_m)
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("declared_target_spacing_m must be positive and finite")
    expected = TARGET_SPACING_BY_DIFFICULTY_M[difficulty]
    if abs(spacing - expected) > TARGET_SPACING_TOLERANCE_M:
        raise ValueError(
            f"{difficulty} requires captured target spacing approximately "
            f"{expected:.1f} m (+/- {TARGET_SPACING_TOLERANCE_M:.1f} m); got {spacing:.3f} m"
        )
    provenance = payload.get("manifest", {}).get("provenance", {})
    metadata = provenance.get("metadata", {}) if isinstance(provenance, Mapping) else {}
    manifest_spacing = metadata.get("target_spacing_m") if isinstance(metadata, Mapping) else None
    if manifest_spacing is not None and not np.isclose(
        float(manifest_spacing), spacing, atol=1e-6
    ):
        raise ValueError("declared target spacing conflicts with D1 manifest provenance")
    return spacing


def _validate_records(records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        raise ValueError("D1 governed replay contains no records")
    for record in records:
        if record.get("schema_version") != D1_OBSERVATION_SCHEMA:
            raise ValueError("unsupported D1 observation schema in governed replay")
        observation_id = str(record.get("observation_id", "")).strip()
        if not observation_id:
            raise ValueError("D1 governed replay observation_id must be non-empty")
        for key in ("measurement_timestamp", "arrival_timestamp"):
            value = float(record[key])
            if not np.isfinite(value):
                raise ValueError(f"{key} must be finite")
        covariance = np.asarray(record.get("covariance"), dtype=float)
        if covariance.ndim != 2 or not np.all(np.isfinite(covariance)):
            raise ValueError("record covariance must be a finite matrix")
        lineage = record.get("source_lineage")
        if (
            not isinstance(lineage, Sequence)
            or isinstance(lineage, (str, bytes))
            or not lineage
        ):
            raise ValueError("record source_lineage must be a non-empty sequence")


def _rebuild_manifest(
    source_manifest: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    profile_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = deepcopy(dict(source_manifest))
    if manifest.get("schema_version") != D1_GOVERNED_MANIFEST_SCHEMA:
        raise ValueError("unsupported D1 governed replay manifest schema")
    manifest["observation_count"] = len(records)
    measurement_times = [float(record["measurement_timestamp"]) for record in records]
    arrival_times = [float(record["arrival_timestamp"]) for record in records]
    manifest["measurement_timestamp_range"] = {
        "minimum": min(measurement_times),
        "maximum": max(measurement_times),
    }
    manifest["arrival_timestamp_range"] = {
        "minimum": min(arrival_times),
        "maximum": max(arrival_times),
    }
    manifest["observation_frames"] = sorted(
        {str(record.get("frame_id", "unknown")) for record in records}
    )
    manifest["coverage_cells"] = sorted(
        {str(record.get("coverage_cell", "cell-unknown")) for record in records}
    )
    manifest["source_lineage"] = [
        {
            "observation_id": str(record["observation_id"]),
            "lineage": deepcopy(record["source_lineage"]),
        }
        for record in records
    ]
    manifest["d2_offline_stress_profile"] = deepcopy(dict(profile_metadata))
    provenance = manifest.get("provenance")
    if isinstance(provenance, Mapping):
        provenance = deepcopy(dict(provenance))
        metadata = provenance.get("metadata")
        metadata = deepcopy(dict(metadata)) if isinstance(metadata, Mapping) else {}
        metadata["d2_offline_stress_profile"] = {
            "scenario_difficulty": profile_metadata["scenario_difficulty"],
            "profile_digest": profile_metadata["profile_digest"],
            "truth_sidecar_consumed": False,
        }
        provenance["metadata"] = metadata
        manifest["provenance"] = provenance
    return manifest


def _radar_record_count(records: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        str(record.get("modality", "")).lower() == _RADAR_MODALITY
        for record in records
    )


def _online_truth_leak_count(value: Any) -> int:
    if isinstance(value, Mapping):
        count = 0
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _TRUTH_KEYS:
                count += 1
            elif normalized == "online_truth_id_used" and bool(item):
                count += 1
            count += _online_truth_leak_count(item)
        return count
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return sum(_online_truth_leak_count(item) for item in value)
    return 0


def _normalize_difficulty(value: str) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized not in SCENARIO_DIFFICULTIES:
        raise ValueError(
            "scenario_difficulty must be one of " + ", ".join(SCENARIO_DIFFICULTIES)
        )
    return normalized


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
