from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import numpy as np

from .fusion import FusionAdapter
from .replay import REPLAY_MANIFEST_SCHEMA_VERSION, sensor_observation_from_jsonl_record


P2_BENCHMARK_SCHEMA_VERSION = "d1.p2_isolated_filter_benchmark.v1"
OFFLINE_TRUTH_SCHEMA_VERSION = "d1.offline_truth_state.v1"


@dataclass(frozen=True)
class P2FilterMetrics:
    position_rmse_m: float | None
    mean_nis: float | None
    mean_normalized_nis: float | None
    mean_nees: float | None
    mean_normalized_nees: float | None
    elapsed_ms: float | None
    estimate_count: int
    nis_sample_count: int
    nees_sample_count: int


@dataclass(frozen=True)
class P2BackendResult:
    backend_id: str
    status: str
    dependency_available: bool
    adapter_available: bool
    implementation: str
    metrics: P2FilterMetrics
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_frozen_governed_replay(path: str | Path) -> dict[str, Any]:
    """Load and validate an immutable offline benchmark fixture."""

    with Path(path).open("r", encoding="utf-8") as handle:
        bundle = json.load(handle)
    _validate_bundle(bundle)
    return bundle


def run_p2_isolated_benchmark(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Benchmark the current D1 path without exposing truth to online filtering."""

    _validate_bundle(bundle)
    manifest = dict(bundle["manifest"])
    records = list(bundle["records"])
    truth = _truth_arrays(bundle["offline_truth"])

    current = _run_current_backend(records, truth)
    optional = [
        _unavailable_optional_backend(
            backend_id="filterpy_optional_adapter",
            module_name="filterpy",
            implementation="D1 FilterPy adapter placeholder",
        ),
        _unavailable_optional_backend(
            backend_id="stonesoup_optional_adapter",
            module_name="stonesoup",
            implementation="D1 Stone Soup adapter placeholder",
        ),
    ]
    return {
        "schema_version": P2_BENCHMARK_SCHEMA_VERSION,
        "isolation": {
            "frozen_replay": True,
            "working_frame": "ned",
            "truth_usage": "offline_metrics_only",
            "default_online_path_changed": False,
        },
        "replay": {
            "scenario_id": manifest["provenance"]["scenario_id"],
            "config_id": manifest["provenance"]["config_id"],
            "config_digest": manifest["provenance"]["config_digest"],
            "seed": manifest["provenance"]["seed"],
            "observation_count": len(records),
        },
        "backends": [current.to_dict(), *(item.to_dict() for item in optional)],
    }


def _run_current_backend(
    records: list[Mapping[str, Any]],
    truth: tuple[np.ndarray, np.ndarray],
) -> P2BackendResult:
    adapter = FusionAdapter(use_truth_hints_for_association=False)
    position_squared_errors: list[float] = []
    nises: list[float] = []
    normalized_nises: list[float] = []
    neeses: list[float] = []
    estimate_count = 0

    started_at = perf_counter()
    for record in sorted(
        records,
        key=lambda item: (float(item["arrival_timestamp"]), str(item["observation_id"])),
    ):
        observation = sensor_observation_from_jsonl_record(record)
        tracks = adapter.process(observation)
        if len(tracks) != 1:
            raise ValueError(
                "D1 P2 frozen replay must produce exactly one track per observation; "
                f"got {len(tracks)} after {observation.observation_id}"
            )
        track = tracks[0]
        target = _truth_state_at(truth, track.timestamp)
        error = track.state - target
        position_squared_errors.append(float(error[:3] @ error[:3]))
        neeses.append(float(error @ np.linalg.pinv(track.covariance) @ error))
        if track.last_nis is not None:
            nises.append(float(track.last_nis))
            normalized_nises.append(float(track.last_nis) / observation.measurement.size)
        estimate_count += 1
    elapsed_ms = (perf_counter() - started_at) * 1000.0

    metrics = P2FilterMetrics(
        position_rmse_m=float(np.sqrt(np.mean(position_squared_errors))),
        mean_nis=float(np.mean(nises)) if nises else None,
        mean_normalized_nis=(
            float(np.mean(normalized_nises)) if normalized_nises else None
        ),
        mean_nees=float(np.mean(neeses)),
        mean_normalized_nees=float(np.mean(neeses) / 6.0),
        elapsed_ms=float(elapsed_ms),
        estimate_count=estimate_count,
        nis_sample_count=len(nises),
        nees_sample_count=len(neeses),
    )
    return P2BackendResult(
        backend_id="numpy_ekf_fixed_lag_current",
        status="completed",
        dependency_available=True,
        adapter_available=True,
        implementation="existing D1 FusionAdapter NumPy EKF/fixed-lag path",
        metrics=metrics,
    )


def _unavailable_optional_backend(
    *,
    backend_id: str,
    module_name: str,
    implementation: str,
) -> P2BackendResult:
    dependency_available = importlib.util.find_spec(module_name) is not None
    if dependency_available:
        reason = (
            f"optional dependency '{module_name}' is installed, but D1 exposes only a "
            "non-executable adapter placeholder; no third-party filter was run"
        )
    else:
        reason = (
            f"optional dependency '{module_name}' is not installed; no third-party "
            "filter was run"
        )
    return P2BackendResult(
        backend_id=backend_id,
        status="unavailable",
        dependency_available=dependency_available,
        adapter_available=False,
        implementation=implementation,
        metrics=P2FilterMetrics(
            position_rmse_m=None,
            mean_nis=None,
            mean_normalized_nis=None,
            mean_nees=None,
            mean_normalized_nees=None,
            elapsed_ms=None,
            estimate_count=0,
            nis_sample_count=0,
            nees_sample_count=0,
        ),
        unavailable_reason=reason,
    )


def _validate_bundle(bundle: Mapping[str, Any]) -> None:
    manifest = bundle.get("manifest")
    records = bundle.get("records")
    offline_truth = bundle.get("offline_truth")
    if not isinstance(manifest, Mapping):
        raise ValueError("D1 P2 benchmark requires a governed replay manifest")
    if manifest.get("schema_version") != REPLAY_MANIFEST_SCHEMA_VERSION:
        raise ValueError("D1 P2 benchmark requires governed replay manifest v1")
    if manifest.get("working_frame") != "ned":
        raise ValueError("D1 P2 benchmark working frame must be NED")
    if manifest.get("truth_policy", {}).get("online") != "stripped":
        raise ValueError("D1 P2 benchmark requires online truth stripping")
    if not isinstance(records, list) or not records:
        raise ValueError("D1 P2 benchmark requires non-empty replay records")
    if manifest.get("observation_count") != len(records):
        raise ValueError("D1 P2 benchmark observation_count does not match records")
    if not isinstance(offline_truth, Mapping):
        raise ValueError("D1 P2 benchmark requires a separate offline_truth sidecar")
    _truth_arrays(offline_truth)

    required = tuple(manifest.get("required_record_fields", ()))
    manifest_lineage = {
        str(item["observation_id"]): item["lineage"]
        for item in manifest.get("source_lineage", ())
    }
    seen_ids: set[str] = set()
    for record in records:
        missing = [field for field in required if field not in record]
        if missing:
            raise ValueError(
                "D1 P2 governed record missing required field(s): " + ", ".join(missing)
            )
        observation_id = str(record["observation_id"])
        if observation_id in seen_ids:
            raise ValueError("D1 P2 governed replay observation_id values must be unique")
        seen_ids.add(observation_id)
        if record.get("working_frame") != "ned" or record.get("frame_id") != "ned":
            raise ValueError("D1 P2 benchmark observations must use the NED working frame")
        if float(record["arrival_timestamp"]) < float(record["measurement_timestamp"]):
            raise ValueError("D1 P2 replay arrival timestamp precedes measurement timestamp")
        if _contains_online_truth(record):
            raise ValueError("D1 P2 online replay record contains forbidden truth metadata")
        if manifest_lineage.get(observation_id) != record.get("source_lineage"):
            raise ValueError("D1 P2 replay source lineage does not match manifest")
        sensor_observation_from_jsonl_record(record)


def _truth_arrays(offline_truth: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    if offline_truth.get("schema_version") != OFFLINE_TRUTH_SCHEMA_VERSION:
        raise ValueError("D1 P2 benchmark offline truth schema is unsupported")
    if offline_truth.get("frame_id") != "ned":
        raise ValueError("D1 P2 benchmark offline truth frame must be NED")
    samples = offline_truth.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        raise ValueError("D1 P2 benchmark requires at least two offline truth samples")
    times = np.asarray([sample["timestamp"] for sample in samples], dtype=float)
    states = np.asarray([sample["state_ned"] for sample in samples], dtype=float)
    if states.shape != (len(samples), 6) or not np.isfinite(states).all():
        raise ValueError("D1 P2 offline truth states must be finite six-state NED vectors")
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0.0):
        raise ValueError("D1 P2 offline truth timestamps must be finite and strictly increasing")
    return times, states


def _truth_state_at(truth: tuple[np.ndarray, np.ndarray], timestamp: float) -> np.ndarray:
    times, states = truth
    timestamp = float(timestamp)
    if timestamp <= times[0]:
        left, right = 0, 1
    elif timestamp >= times[-1]:
        left, right = len(times) - 2, len(times) - 1
    else:
        right = int(np.searchsorted(times, timestamp, side="right"))
        left = right - 1
    fraction = (timestamp - times[left]) / (times[right] - times[left])
    return states[left] + fraction * (states[right] - states[left])


def _contains_online_truth(value: Any) -> bool:
    if not isinstance(value, Mapping):
        if isinstance(value, list):
            return any(_contains_online_truth(item) for item in value)
        return False
    for key, item in value.items():
        normalized = str(key).strip().lower()
        if normalized == "offline_truth" or normalized.endswith(
            ("_truth_id", "_actor_id", "_actor_name", "_object_id", "_object_name")
        ):
            return True
        if normalized in {"truth_id", "actor_id", "actor_name", "object_id", "object_name"}:
            return True
        if _contains_online_truth(item):
            return True
    return False
