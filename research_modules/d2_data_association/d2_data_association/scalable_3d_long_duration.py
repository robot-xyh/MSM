"""Reproducible long-duration metadata scaling benchmark for scalable D2."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import floor
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import numpy as np

from .models import govern_covariance
from .scalable_3d_models import (
    Detection3D,
    STATE_ORDER_3D,
    _finite_timestamp,
    _finite_vector,
    _mapping_or_empty,
    _optional_identifier,
    _read,
    detections3d_from_d1_global_tracks,
)
from .sparse_3d import Scalable3DTracker


SCALABLE_3D_D2_LONG_DURATION_BENCHMARK_SCHEMA_VERSION = (
    "d2-scalable3d-long-duration-metadata-benchmark-v1"
)
_TIMING_ONLY_KEYS = frozenset(
    {
        "association_runtime_seconds",
        "assignment_seconds",
        "candidate_generation_seconds",
        "index_build_seconds",
        "mean_frame_runtime_seconds",
        "p95_frame_runtime_seconds",
        "runtime_seconds",
        "tracker_runtime_seconds",
    }
)


@dataclass(frozen=True, slots=True)
class Scalable3DLongDurationBenchmarkReport:
    """Timing and exact online-semantics evidence for one synthetic replay."""

    track_count: int
    cycle_count: int
    sensor_count_start: int
    sensor_count_end: int
    baseline_total_seconds: float
    candidate_total_seconds: float
    cycle_semantic_hashes_equal: bool
    final_track_hash_equal: bool
    final_claim_hash_equal: bool
    all_online_truth_free: bool
    cycle_records: tuple[dict[str, Any], ...]

    @property
    def speedup(self) -> float | None:
        if self.candidate_total_seconds <= 0.0:
            return None
        return self.baseline_total_seconds / self.candidate_total_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                SCALABLE_3D_D2_LONG_DURATION_BENCHMARK_SCHEMA_VERSION
            ),
            "track_count": self.track_count,
            "cycle_count": self.cycle_count,
            "sensor_count_start": self.sensor_count_start,
            "sensor_count_end": self.sensor_count_end,
            "baseline_path": "unprojected_d1_diagnostics_reference",
            "candidate_path": "batch_audit_then_d2_contract_projection",
            "baseline_total_seconds": self.baseline_total_seconds,
            "candidate_total_seconds": self.candidate_total_seconds,
            "speedup": self.speedup,
            "cycle_semantic_hashes_equal": self.cycle_semantic_hashes_equal,
            "final_track_hash_equal": self.final_track_hash_equal,
            "final_claim_hash_equal": self.final_claim_hash_equal,
            "all_online_truth_free": self.all_online_truth_free,
            "cycle_records": list(self.cycle_records),
        }


def run_scalable_3d_long_duration_metadata_benchmark(
    *,
    track_count: int = 200,
    cycle_count: int = 48,
    sensor_count_start: int = 20,
    sensor_count_end: int = 181,
) -> Scalable3DLongDurationBenchmarkReport:
    """Compare the old unprojected metadata shape with the optimized adapter.

    Both trackers receive identical six-state posteriors and observation
    lineage.  The reference path retains all audited D1 diagnostics on each
    ``Detection3D``.  The candidate path performs the production batch audit
    and then carries only D2 contract fields.  Runtime values are excluded from
    semantic hashes; all decisions, claims, lifecycle and track states remain.
    """

    for name, value in (
        ("track_count", track_count),
        ("cycle_count", cycle_count),
        ("sensor_count_start", sensor_count_start),
        ("sensor_count_end", sensor_count_end),
    ):
        if int(value) <= 0:
            raise ValueError(f"{name} must be positive")
    if sensor_count_end < sensor_count_start:
        raise ValueError("sensor_count_end cannot be below sensor_count_start")

    baseline = Scalable3DTracker()
    candidate = Scalable3DTracker()
    baseline_total = 0.0
    candidate_total = 0.0
    records: list[dict[str, Any]] = []

    for cycle_index in range(cycle_count):
        timestamp = cycle_index * 0.2
        sensor_count = _interpolated_sensor_count(
            cycle_index,
            cycle_count,
            sensor_count_start,
            sensor_count_end,
        )
        source_tracks = _synthetic_d1_tracks(
            track_count,
            cycle_index,
            timestamp,
            sensor_count,
        )

        started = perf_counter()
        baseline_timestamp, baseline_detections = (
            _unprojected_reference_detections(source_tracks)
        )
        baseline_result = baseline.step(
            baseline_detections,
            baseline_timestamp,
        )
        baseline_seconds = perf_counter() - started
        baseline_total += baseline_seconds

        started = perf_counter()
        candidate_timestamp, candidate_detections = (
            detections3d_from_d1_global_tracks(source_tracks)
        )
        candidate_result = candidate.step(
            candidate_detections,
            candidate_timestamp,
        )
        candidate_seconds = perf_counter() - started
        candidate_total += candidate_seconds

        baseline_hash = _cycle_semantic_hash(baseline_result, baseline)
        candidate_hash = _cycle_semantic_hash(candidate_result, candidate)
        records.append(
            {
                "cycle_index": cycle_index,
                "timestamp": timestamp,
                "sensor_count": sensor_count,
                "baseline_seconds": baseline_seconds,
                "candidate_seconds": candidate_seconds,
                "speedup": (
                    baseline_seconds / candidate_seconds
                    if candidate_seconds > 0.0
                    else None
                ),
                "baseline_semantic_sha256": baseline_hash,
                "candidate_semantic_sha256": candidate_hash,
                "semantics_equal": baseline_hash == candidate_hash,
                "track_count": len(candidate.active_tracks()),
                "claim_count": int(
                    candidate.summary()["observation_claim_count"]
                ),
            }
        )

    baseline_summary = baseline.summary()
    candidate_summary = candidate.summary()
    return Scalable3DLongDurationBenchmarkReport(
        track_count=track_count,
        cycle_count=cycle_count,
        sensor_count_start=sensor_count_start,
        sensor_count_end=sensor_count_end,
        baseline_total_seconds=baseline_total,
        candidate_total_seconds=candidate_total,
        cycle_semantic_hashes_equal=all(
            bool(item["semantics_equal"]) for item in records
        ),
        final_track_hash_equal=(
            _canonical_sha256([item.to_dict() for item in baseline.active_tracks()])
            == _canonical_sha256([item.to_dict() for item in candidate.active_tracks()])
        ),
        final_claim_hash_equal=(
            _canonical_sha256(baseline_summary["observation_claim_ledger"])
            == _canonical_sha256(candidate_summary["observation_claim_ledger"])
        ),
        all_online_truth_free=True,
        cycle_records=tuple(records),
    )


def write_scalable_3d_long_duration_metadata_benchmark(
    output_path: str,
    report: Scalable3DLongDurationBenchmarkReport,
) -> str:
    """Write canonical JSON and return its SHA-256 digest."""

    content = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    from pathlib import Path

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return sha256(content.encode("utf-8")).hexdigest()


def _unprojected_reference_detections(
    tracks: list[SimpleNamespace],
) -> tuple[float, list[Detection3D]]:
    """Reproduce the pre-optimization D1 adapter metadata shape."""

    detections: list[Detection3D] = []
    frame_timestamp = 0.0
    for index, item in enumerate(tracks):
        metadata = dict(_mapping_or_empty(_read(item, "metadata", {})))
        frame_id = str(metadata.get("frame_id", _read(item, "frame_id", "NED")))
        state = _finite_vector(_read(item, "state"), 6, "D1 track state")
        covariance, _ = govern_covariance(
            _read(item, "covariance"),
            (6, 6),
            "D1 track covariance",
        )
        state_timestamp = _finite_timestamp(_read(item, "timestamp"), "timestamp")
        source_measurement_timestamp = _finite_timestamp(
            metadata.get("latest_measurement_timestamp", state_timestamp),
            "source measurement_timestamp",
        )
        source_arrival_timestamp = _finite_timestamp(
            metadata.get("latest_arrival_timestamp", state_timestamp),
            "source arrival_timestamp",
        )
        published_at = _finite_timestamp(
            metadata.get("published_at", state_timestamp),
            "published_at",
        )
        frame_timestamp = max(frame_timestamp, state_timestamp)
        safe_metadata = dict(metadata)
        safe_metadata.update(
            {
                "source_format": "d1_six_state_track",
                "upstream_identity_ignored": True,
                "state_valid_timestamp": state_timestamp,
                "source_measurement_timestamp": source_measurement_timestamp,
                "source_arrival_timestamp": source_arrival_timestamp,
                "state_order": list(STATE_ORDER_3D),
            }
        )
        detections.append(
            Detection3D(
                detection_id=(
                    f"d1-3d-{state_timestamp:.9f}-{index:04d}"
                ),
                measurement_timestamp=state_timestamp,
                arrival_timestamp=max(
                    state_timestamp,
                    source_arrival_timestamp,
                    published_at,
                ),
                position_ned=state[:3],
                covariance=covariance[:3, :3],
                confidence=float(metadata.get("confidence", 1.0)),
                velocity_ned=state[3:],
                velocity_covariance=covariance[3:, 3:],
                state_estimate_covariance=covariance,
                source_node_id=_optional_identifier(
                    metadata.get("source_node_id")
                ),
                source_track_id=_optional_identifier(
                    metadata.get("source_track_id")
                ),
                frame_id=frame_id,
                metadata=safe_metadata,
            )
        )
    return frame_timestamp, detections


def _synthetic_d1_tracks(
    track_count: int,
    cycle_index: int,
    timestamp: float,
    sensor_count: int,
) -> list[SimpleNamespace]:
    indices = np.arange(track_count, dtype=float)
    positions = np.column_stack(
        (
            (indices % 20.0) * 100.0 + timestamp * 2.0,
            np.floor(indices / 20.0) * 100.0 - timestamp * 0.5,
            -100.0 - (indices % 4.0) * 25.0,
        )
    )
    velocities = np.column_stack(
        (
            np.full(track_count, 2.0),
            np.full(track_count, -0.5),
            np.zeros(track_count),
        )
    )
    covariance = np.diag([4.0, 4.0, 4.0, 1.0, 1.0, 1.0])
    health_template = {
        f"CAM-{sensor_index:04d}": {
            "accepted_count": cycle_index + sensor_index + 1,
            "arrival_latency_mean_s": 0.08,
            "covariance_scale": 1.0,
            "detection_probability": 0.92,
            "measurement_count": cycle_index + 1,
            "modality": "eo",
            "quality_flags": ("nominal",),
            "rejected_count": 0,
        }
        for sensor_index in range(sensor_count)
    }
    common = {
        "association_audit": {
            "candidate_count": track_count,
            "gate": 11.344866730144373,
            "reasons": (),
        },
        "latency_audit": {
            "mean_s": 0.08,
            "p95_s": 0.12,
            "sample_count": cycle_index + 1,
        },
    }
    tracks: list[SimpleNamespace] = []
    for index in range(track_count):
        metadata = {
            **common,
            "frame_id": "NED",
            "latest_arrival_timestamp": timestamp + 0.05,
            "latest_measurement_timestamp": timestamp,
            "latest_modality": "radar",
            "latest_observation_id": f"obs-{cycle_index:04d}-{index:04d}",
            "latest_sensor_id": "RADAR-CENTER-001",
            "measurement_order": tuple(STATE_ORDER_3D),
            "published_at": timestamp + 0.05,
            "sensor_health": {
                key: dict(value) for key, value in health_template.items()
            },
            "source_node_id": "D1-CENTER",
            "source_track_id": f"d1-local-{index:04d}",
        }
        tracks.append(
            SimpleNamespace(
                global_track_id=f"D1-UPSTREAM-{index:04d}",
                state=np.concatenate((positions[index], velocities[index])),
                covariance=covariance.copy(),
                timestamp=timestamp,
                metadata=metadata,
            )
        )
    return tracks


def _interpolated_sensor_count(
    cycle_index: int,
    cycle_count: int,
    start: int,
    end: int,
) -> int:
    if cycle_count == 1:
        return end
    fraction = cycle_index / (cycle_count - 1)
    return int(floor(start + fraction * (end - start) + 0.5))


def _cycle_semantic_hash(result: Any, tracker: Scalable3DTracker) -> str:
    payload = {
        "association": result.to_dict(),
        "tracks": [item.to_dict() for item in tracker.active_tracks()],
        "tracker": tracker.summary(),
    }
    return _canonical_sha256(_without_runtime(payload))


def _without_runtime(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _without_runtime(item)
            for key, item in value.items()
            if str(key) not in _TIMING_ONLY_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_without_runtime(item) for item in value]
    return value


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
