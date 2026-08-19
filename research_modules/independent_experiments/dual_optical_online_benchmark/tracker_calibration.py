"""Offline-only calibration and fail-closed freeze for the shared tracker."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Mapping, Sequence

import numpy as np

from dual_optical_40target.core import (
    AnonymousDetection,
    CameraSpec,
    CameraState,
    RayObservation,
    ray_observation_from_detection,
    sweep_index,
)

from .contracts import BenchmarkProtocol, CORRUPTION_LEVELS, write_json
from .dataset import (
    CORRUPTION_POLICY,
    _camera_states,
    _false_detections,
    _false_track_specs,
    _parse_vector,
    _read_csv,
    _should_drop,
    sha256_file,
    split_for_seed,
)
from .tracking import (
    BearingScanlet,
    CHI2_GATE_BY_CONFIDENCE,
    SharedBearingTracker,
    SharedTrackerConfig,
    _scanlets_for_sweep,
    tracker_freeze_payload,
)


TRACKER_CALIBRATION_SCHEMA = "dual-optical-shared-tracker-calibration-v4"
LEGACY_TRACKER_CALIBRATION_SCHEMA = "dual-optical-shared-tracker-calibration-v1"
PREVIOUS_TRACKER_CALIBRATION_SCHEMA = "dual-optical-shared-tracker-calibration-v2"
CONTENDED_TRACKER_CALIBRATION_SCHEMA = "dual-optical-shared-tracker-calibration-v3"
PREPARED_TRACKER_CACHE_SCHEMA = "dual-optical-prepared-tracker-cache-v2"
PREPARATION_POLICY_VERSION = "dual-optical-anonymous-scanlet-policy-v2"
VALIDATION_RUNTIME_MEASUREMENT_POLICY = "isolated-serial-wall-clock-v1"
PARALLEL_QUALITY_REPLAY_POLICY = "parallel-quality-replay-not-for-latency-v1"
TRACKER_ACCEPTANCE = {
    "median_track_purity": 0.85,
    "light_common_confirmed_rate": 0.70,
    "medium_common_confirmed_rate": 0.70,
    "heavy_common_confirmed_rate": 0.50,
    "maximum_false_reactivation_rate": 0.005,
    "maximum_sweep_runtime_p95_ms": 250.0,
}
TRACKER_DIAGNOSTIC_LEVELS = ("none", *CORRUPTION_LEVELS)


def tracker_config_for_protocol(
    protocol: BenchmarkProtocol,
    config: SharedTrackerConfig | None = None,
) -> SharedTrackerConfig:
    """Apply only the protocol revisit time to an otherwise frozen tracker."""

    base = config or SharedTrackerConfig()
    return replace(
        base,
        nominal_sweep_period_s=protocol.association_round_period_s,
    )


def tracker_candidate_configs(
    protocol: BenchmarkProtocol | None = None,
) -> tuple[SharedTrackerConfig, ...]:
    """Return the bounded tracker grid used before opening reserved test data."""

    if protocol is not None and not protocol.is_legacy_continuous_profile:
        # S180 is a scan-timing comparison.  Keep every tracker parameter at
        # its established value and change only the nominal revisit period.
        return (tracker_config_for_protocol(protocol),)

    configs: list[SharedTrackerConfig] = []
    for confidence in CHI2_GATE_BY_CONFIDENCE:
        for process_noise in (0.05, 0.10, 0.20):
            for dormant_retention, local_k, decision_window in (
                (3, 3, 2),
                (4, 5, 3),
            ):
                configs.append(
                    SharedTrackerConfig(
                        chi2_confidence=confidence,
                        process_noise_deg_s2=process_noise,
                        motion_initialization_residual_gate_m=3.0,
                        maximum_global_hypotheses=1,
                        dormant_retention_sweeps=dormant_retention,
                        local_k_best=local_k,
                        local_hypothesis_window_sweeps=decision_window,
                    )
                )
    baseline = SharedTrackerConfig()
    if all(item.fingerprint != baseline.fingerprint for item in configs):
        configs.append(baseline)
    return tuple(configs)


@dataclass(frozen=True)
class PreparedTrackerEpisode:
    """Anonymous observations prepared once for repeated tracker candidates."""

    seed: int
    split: str
    corruption_level: str
    camera_ids: tuple[str, str]
    observations: Mapping[tuple[str, int], tuple[RayObservation, ...]]
    confidence_by_uid: Mapping[str, float]
    scanlets: Mapping[tuple[str, int], tuple[BearingScanlet, ...]] | None = None
    scanlet_preparation_fingerprint: str = ""
    cache_key: str = ""
    cache_status: str = "disabled"
    episode_dir: str = ""


@dataclass(frozen=True)
class _OfflineScoringLabels:
    uid_to_identity: Mapping[str, str]
    observed_real: Mapping[str, frozenset[str]]


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_anonymous_episode(
    episode_dir: str | Path,
    protocol: BenchmarkProtocol,
    *,
    expected_gimbal_pose_error: bool = True,
    split_override: str | None = None,
) -> dict[str, Any]:
    """Validate only files permitted before the anonymous tracking run."""

    root = Path(episode_dir).resolve()
    paths = {
        "scenario": root / "scenario.json",
        "detections": root / "online" / "anonymous_detections.csv",
        "scan": root / "online" / "camera_scan.csv",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"anonymous tracker episode is incomplete: {missing}")
    scenario = json.loads(paths["scenario"].read_text(encoding="utf-8"))
    values = scenario["scenario"]
    seed = int(values["seed"])
    checks = {
        "target_count": int(values["target_count"]) == protocol.target_count,
        "target_speed_mps": math.isclose(
            float(values["target_speed_mps"]),
            protocol.target_speed_mps,
            abs_tol=1.0e-9,
        ),
        "duration_s": math.isclose(
            float(values["duration_s"]), protocol.duration_s, abs_tol=1.0e-9
        ),
        "sample_rate_hz": math.isclose(
            float(values["sample_rate_hz"]),
            protocol.sample_rate_hz,
            abs_tol=1.0e-9,
        ),
        "clock_speed": math.isclose(
            float(values["clock_speed"]), protocol.clock_speed, abs_tol=1.0e-9
        ),
        "scan_period_s": math.isclose(
            float(values["scan_period_s"]),
            protocol.scan_period_s,
            abs_tol=1.0e-9,
        ),
        "scan_mode": str(values.get("scan_mode")) == protocol.scan_mode,
        "scan_half_span_deg": (
            protocol.scan_mode == "continuous_360"
            or math.isclose(
                float(values.get("scan_half_span_deg", -1.0)),
                protocol.scan_half_span_deg,
                abs_tol=1.0e-9,
            )
        ),
        "target_motion_profile": str(values.get("target_motion_profile"))
        == "split_0_minus30",
        "gimbal_pose_error_enabled": bool(
            values.get("gimbal_pose_error_enabled")
        ) is bool(expected_gimbal_pose_error),
        "gimbal_fixed_bias_mrad": math.isclose(
            float(values.get("gimbal_fixed_bias_mrad", -1.0)),
            protocol.gimbal_fixed_bias_rms_mrad,
            abs_tol=1.0e-9,
        ),
        "gimbal_jitter_rms_mrad": math.isclose(
            float(values.get("gimbal_jitter_rms_mrad", -1.0)),
            protocol.gimbal_jitter_rms_mrad,
            abs_tol=1.0e-9,
        ),
        "camera_b_scan_phase_offset_s": math.isclose(
            float(values.get("camera_b_scan_phase_offset_s", 0.0)),
            protocol.camera_b_scan_phase_offset_s,
            abs_tol=1.0e-9,
        ),
        "deterministic_step_mode": str(
            values.get("deterministic_step_mode", "legacy_wall_yield")
        ) == protocol.deterministic_step_mode,
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ValueError(f"anonymous tracker episode violates protocol: {failed}")
    scan_rows = _read_csv(paths["scan"])
    camera_ids = {
        str(values["camera_a_name"]), str(values["camera_b_name"])
    }
    scan_keys = {
        (str(row["camera_id"]), int(row["frame_index"])) for row in scan_rows
    }
    if {camera_id for camera_id, _ in scan_keys} != camera_ids:
        raise ValueError("anonymous camera scan does not cover both cameras")
    expected_frames = int(round(protocol.duration_s * protocol.sample_rate_hz))
    expected_scan_keys = {
        (camera_id, frame_index)
        for camera_id in camera_ids
        for frame_index in range(expected_frames)
    }
    if not expected_scan_keys <= scan_keys:
        raise ValueError("anonymous camera scan is incomplete")
    return {
        "seed": seed,
        "split": (
            str(split_override)
            if split_override is not None
            else split_for_seed(protocol, seed)
        ),
        "protocol_fingerprint": protocol.fingerprint,
        "files": {name: sha256_file(path) for name, path in paths.items()},
    }


def _load_anonymous_episode(
    root: Path,
) -> tuple[dict[str, Any], list[AnonymousDetection], list[dict[str, str]]]:
    source = json.loads((root / "scenario.json").read_text(encoding="utf-8"))
    scenario = {
        "scenario": dict(source["scenario"]),
        "camera": dict(source["camera"]),
    }
    detections = [
        AnonymousDetection(
            detection_uid=str(row["detection_uid"]),
            camera_id=str(row["camera_id"]),
            frame_index=int(row["frame_index"]),
            measurement_timestamp=float(row["measurement_timestamp"]),
            arrival_timestamp=float(row["arrival_timestamp"]),
            bbox_xyxy=_parse_vector(row["bbox_xyxy"]),
            center_px=_parse_vector(row["center_px"]),
            confidence=float(row["confidence"]),
        )
        for row in _read_csv(root / "online" / "anonymous_detections.csv")
    ]
    scan_rows = _read_csv(root / "online" / "camera_scan.csv")
    return scenario, detections, scan_rows


def _load_offline_scoring_labels(
    prepared: PreparedTrackerEpisode,
    protocol: BenchmarkProtocol,
) -> _OfflineScoringLabels:
    """Open identity labels only after the caller completes tracking."""

    if not prepared.episode_dir:
        raise ValueError("offline scoring requires the source episode directory")
    root = Path(prepared.episode_dir).resolve()
    observed_uids = {
        observation.detection_uid
        for observations in prepared.observations.values()
        for observation in observations
    }
    uid_to_identity: dict[str, str] = {}
    for row in _read_csv(root / "truth" / "detection_truth.csv"):
        uid = str(row.get("detection_uid", ""))
        identity = str(row.get("truth_id", ""))
        if not uid or not identity or uid not in observed_uids:
            continue
        previous = uid_to_identity.setdefault(uid, identity)
        if previous != identity:
            raise ValueError("offline labels assign one detection to two identities")

    if prepared.corruption_level != "none":
        scenario = json.loads(
            (root / "scenario.json").read_text(encoding="utf-8")
        )
        scan_rows = _read_csv(root / "online" / "camera_scan.csv")
        camera, camera_ids, _, states = _camera_specs_and_states(
            scenario, scan_rows
        )
        false_specs = _false_track_specs(
            protocol,
            prepared.seed,
            prepared.corruption_level,
            camera_ids,
            states,
        )
        for detection, false_id in _false_detections(
            false_specs,
            states,
            camera,
            sample_rate_hz=protocol.sample_rate_hz,
        ):
            if detection.detection_uid in observed_uids:
                uid_to_identity[detection.detection_uid] = false_id

    observed_real: dict[str, set[str]] = {
        camera_id: set() for camera_id in prepared.camera_ids
    }
    for (camera_id, _), observations in prepared.observations.items():
        for observation in observations:
            identity = uid_to_identity.get(observation.detection_uid, "")
            if identity and not identity.startswith("FA-"):
                observed_real[camera_id].add(identity)
    return _OfflineScoringLabels(
        uid_to_identity=dict(uid_to_identity),
        observed_real={
            camera_id: frozenset(values)
            for camera_id, values in observed_real.items()
        },
    )


def _prepared_cache_metadata(
    validation: Mapping[str, Any],
    protocol: BenchmarkProtocol,
    corruption_level: str,
    expected_gimbal_pose_error: bool,
    split_override: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": PREPARED_TRACKER_CACHE_SCHEMA,
        "preparation_policy_version": PREPARATION_POLICY_VERSION,
        "protocol_fingerprint": protocol.fingerprint,
        "raw_source_sha256": dict(validation["files"]),
        "seed": int(validation["seed"]),
        "split": str(validation["split"]),
        "split_override": split_override,
        "corruption_level": corruption_level,
        "expected_gimbal_pose_error": bool(expected_gimbal_pose_error),
        "scanlet_preparation_fingerprint": (
            tracker_config_for_protocol(protocol).scanlet_preparation_fingerprint
        ),
    }


def _prepared_cache_path(cache_dir: Path, metadata: Mapping[str, Any]) -> Path:
    key = _canonical_sha256(metadata)
    return cache_dir / (
        f"seed_{int(metadata['seed'])}_{metadata['corruption_level']}_{key}.json"
    )


def _prepared_episode_payload(prepared: PreparedTrackerEpisode) -> dict[str, Any]:
    observation_rows = [
        {
            "camera_id": camera_id,
            "sweep_index": int(sweep),
            "items": [asdict(item) for item in items],
        }
        for (camera_id, sweep), items in sorted(prepared.observations.items())
    ]
    scanlet_rows = [
        {
            "camera_id": camera_id,
            "sweep_index": int(sweep),
            "items": [asdict(item) for item in items],
        }
        for (camera_id, sweep), items in sorted((prepared.scanlets or {}).items())
    ]
    return {
        "online_anonymous": {
            "seed": prepared.seed,
            "split": prepared.split,
            "corruption_level": prepared.corruption_level,
            "camera_ids": list(prepared.camera_ids),
            "observations": observation_rows,
            "scanlets": scanlet_rows,
            "confidence_by_uid": dict(prepared.confidence_by_uid),
            "scanlet_preparation_fingerprint": (
                prepared.scanlet_preparation_fingerprint
            ),
        },
    }


def _ray_observation_from_mapping(values: Mapping[str, Any]) -> RayObservation:
    normalized = dict(values)
    for name in ("origin_ned", "direction_ned", "bbox_xyxy"):
        normalized[name] = tuple(float(value) for value in normalized[name])
    return RayObservation(**normalized)


def _bearing_scanlet_from_mapping(values: Mapping[str, Any]) -> BearingScanlet:
    normalized = dict(values)
    for name in (
        "origin_ned",
        "direction_ned",
        "measurement_covariance_deg2",
    ):
        normalized[name] = tuple(float(value) for value in normalized[name])
    normalized["detection_uids"] = tuple(
        str(value) for value in normalized["detection_uids"]
    )
    return BearingScanlet(**normalized)


def _prepared_episode_from_payload(
    payload: Mapping[str, Any],
    *,
    cache_key: str,
) -> PreparedTrackerEpisode:
    if set(payload) != {"online_anonymous"}:
        raise ValueError("prepared tracker cache contains non-anonymous sections")
    online = payload["online_anonymous"]
    camera_ids = tuple(str(value) for value in online["camera_ids"])
    if len(camera_ids) != 2:
        raise ValueError("prepared tracker cache must contain two cameras")
    observations: dict[tuple[str, int], tuple[RayObservation, ...]] = {}
    for row in online["observations"]:
        key = (str(row["camera_id"]), int(row["sweep_index"]))
        if key in observations:
            raise ValueError("prepared tracker cache repeats an observation sweep")
        items = tuple(_ray_observation_from_mapping(item) for item in row["items"])
        if any(item.camera_id != key[0] or item.sweep_index != key[1] for item in items):
            raise ValueError("prepared tracker observation key mismatch")
        observations[key] = items
    scanlets: dict[tuple[str, int], tuple[BearingScanlet, ...]] = {}
    for row in online["scanlets"]:
        key = (str(row["camera_id"]), int(row["sweep_index"]))
        if key in scanlets:
            raise ValueError("prepared tracker cache repeats a scanlet sweep")
        items = tuple(_bearing_scanlet_from_mapping(item) for item in row["items"])
        if any(item.camera_id != key[0] or item.sweep_index != key[1] for item in items):
            raise ValueError("prepared tracker scanlet key mismatch")
        used: set[str] = set()
        for item in items:
            if used.intersection(item.detection_uids):
                raise ValueError("prepared tracker cache reuses an anonymous detection")
            used.update(item.detection_uids)
        scanlets[key] = items
    confidence = {
        str(uid): float(value)
        for uid, value in online["confidence_by_uid"].items()
    }
    for items in scanlets.values():
        if any(uid not in confidence for item in items for uid in item.detection_uids):
            raise ValueError("prepared scanlet has no anonymous confidence record")
    return PreparedTrackerEpisode(
        seed=int(online["seed"]),
        split=str(online["split"]),
        corruption_level=str(online["corruption_level"]),
        camera_ids=(camera_ids[0], camera_ids[1]),
        observations=observations,
        confidence_by_uid=confidence,
        scanlets=scanlets,
        scanlet_preparation_fingerprint=str(
            online["scanlet_preparation_fingerprint"]
        ),
        cache_key=cache_key,
        cache_status="hit",
    )


def _write_prepared_cache(
    path: Path,
    metadata: Mapping[str, Any],
    prepared: PreparedTrackerEpisode,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _prepared_episode_payload(prepared)
    envelope = {
        "metadata": dict(metadata),
        "cache_key": _canonical_sha256(metadata),
        "content_sha256": _canonical_sha256(content),
        "content": content,
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                envelope,
                handle,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _load_prepared_cache(
    path: Path,
    expected_metadata: Mapping[str, Any],
) -> PreparedTrackerEpisode:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    metadata = envelope["metadata"]
    expected_key = _canonical_sha256(expected_metadata)
    if metadata != dict(expected_metadata):
        raise ValueError("prepared tracker cache metadata mismatch")
    if envelope.get("cache_key") != expected_key:
        raise ValueError("prepared tracker cache key mismatch")
    content = envelope["content"]
    if envelope.get("content_sha256") != _canonical_sha256(content):
        raise ValueError("prepared tracker cache content hash mismatch")
    prepared = _prepared_episode_from_payload(content, cache_key=expected_key)
    if prepared.seed != int(expected_metadata["seed"]):
        raise ValueError("prepared tracker cache seed mismatch")
    if prepared.split != str(expected_metadata["split"]):
        raise ValueError("prepared tracker cache split mismatch")
    if prepared.corruption_level != str(expected_metadata["corruption_level"]):
        raise ValueError("prepared tracker cache corruption mismatch")
    if prepared.scanlet_preparation_fingerprint != expected_metadata[
        "scanlet_preparation_fingerprint"
    ]:
        raise ValueError("prepared tracker scanlet policy mismatch")
    return prepared


def _dominant_real_identity(counts: Mapping[str, int]) -> tuple[str | None, float]:
    real = {
        str(identity): int(count)
        for identity, count in counts.items()
        if not str(identity).startswith("FA-") and int(count) > 0
    }
    total = sum(int(count) for count in counts.values())
    if not real or total <= 0:
        return None, 0.0
    maximum = max(real.values())
    winners = sorted(identity for identity, count in real.items() if count == maximum)
    if len(winners) != 1:
        return None, maximum / total
    return winners[0], maximum / total


def _camera_specs_and_states(
    scenario: Mapping[str, Any], scan_rows: Sequence[Mapping[str, str]]
) -> tuple[CameraSpec, tuple[str, str], dict[str, tuple[float, float, float]], dict[tuple[str, int], CameraState]]:
    config = scenario["scenario"]
    camera_values = scenario["camera"]
    camera = CameraSpec(
        width=int(camera_values["width"]),
        height=int(camera_values["height"]),
        horizontal_fov_deg=float(camera_values["horizontal_fov_deg"]),
        equivalent_focal_length_mm=float(camera_values["equivalent_focal_length_mm"]),
        stated_ifov_mrad=float(camera_values["stated_ifov_mrad"]),
    )
    camera_ids = (str(config["camera_a_name"]), str(config["camera_b_name"]))
    positions = {
        camera_ids[0]: tuple(float(value) for value in config["camera_a_position_ned"]),
        camera_ids[1]: tuple(float(value) for value in config["camera_b_position_ned"]),
    }
    states = _camera_states(scan_rows)
    for key, state in tuple(states.items()):
        states[key] = replace(state, position_ned=positions[state.camera_id])
    return camera, camera_ids, positions, states


def prepare_tracker_episode(
    episode_dir: str | Path,
    protocol: BenchmarkProtocol,
    corruption_level: str,
    *,
    expected_gimbal_pose_error: bool = True,
    split_override: str | None = None,
    cache_dir: str | Path | None = None,
) -> PreparedTrackerEpisode:
    """Load and corrupt one raw episode without choosing tracker parameters."""

    if corruption_level not in TRACKER_DIAGNOSTIC_LEVELS:
        raise ValueError("invalid tracker calibration corruption level")
    root = Path(episode_dir).resolve()
    validation = _validate_anonymous_episode(
        root,
        protocol,
        expected_gimbal_pose_error=expected_gimbal_pose_error,
        split_override=split_override,
    )
    cache_metadata = _prepared_cache_metadata(
        validation,
        protocol,
        corruption_level,
        expected_gimbal_pose_error,
        split_override,
    )
    cache_path: Path | None = None
    cache_was_invalid = False
    if cache_dir is not None:
        cache_path = _prepared_cache_path(Path(cache_dir).resolve(), cache_metadata)
        if cache_path.is_file():
            try:
                cached = _load_prepared_cache(cache_path, cache_metadata)
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                cache_was_invalid = True
            else:
                return replace(cached, episode_dir=str(root))
    scenario, raw, scan_rows = _load_anonymous_episode(root)
    camera, camera_ids, _, states = _camera_specs_and_states(scenario, scan_rows)
    seed = int(validation["seed"])
    policy = (
        {
            "miss_probability": 0.0,
            "transient_false_per_camera_second": 0.0,
            "persistent_false_per_camera": 0,
        }
        if corruption_level == "none"
        else CORRUPTION_POLICY[corruption_level]
    )
    kept: list[AnonymousDetection] = []
    for item in raw:
        if _should_drop(
            seed,
            corruption_level,
            item.detection_uid,
            float(policy["miss_probability"]),
        ):
            continue
        detection = AnonymousDetection(**asdict(item))
        kept.append(detection)
    if corruption_level != "none":
        false_specs = _false_track_specs(
            protocol, seed, corruption_level, camera_ids, states
        )
        for detection, _ in _false_detections(
            false_specs, states, camera, sample_rate_hz=protocol.sample_rate_hz
        ):
            kept.append(detection)

    confidence = {item.detection_uid: item.confidence for item in kept}
    observations: dict[tuple[str, int], list[RayObservation]] = defaultdict(list)
    for detection in kept:
        state = states.get((detection.camera_id, detection.frame_index))
        if state is None:
            continue
        sweep = min(
            sweep_index(
                detection.measurement_timestamp,
                period_s=protocol.scan_period_s,
                mode=protocol.scan_mode,
            ),
            protocol.association_round_count - 1,
        )
        observations[(detection.camera_id, sweep)].append(
            ray_observation_from_detection(
                detection,
                state,
                camera,
                scan_period_s=protocol.scan_period_s,
                scan_mode=protocol.scan_mode,
            )
        )

    frozen_observations = {
        key: tuple(values) for key, values in observations.items()
    }
    scanlet_config = tracker_config_for_protocol(protocol)
    prepared_scanlets = {
        key: _scanlets_for_sweep(
            key[0],
            key[1],
            values,
            confidence,
            scanlet_config,
        )
        for key, values in frozen_observations.items()
    }
    prepared = PreparedTrackerEpisode(
        seed=seed,
        split=str(validation["split"]),
        corruption_level=corruption_level,
        camera_ids=camera_ids,
        observations=frozen_observations,
        confidence_by_uid=dict(confidence),
        scanlets=prepared_scanlets,
        scanlet_preparation_fingerprint=(
            scanlet_config.scanlet_preparation_fingerprint
        ),
        cache_key=_canonical_sha256(cache_metadata) if cache_path is not None else "",
        cache_status=(
            "rebuilt" if cache_was_invalid else "miss"
        ) if cache_path is not None else "disabled",
        episode_dir=str(root),
    )
    if cache_path is not None:
        _write_prepared_cache(cache_path, cache_metadata, prepared)
    return prepared


def evaluate_prepared_tracker_episode(
    prepared: PreparedTrackerEpisode,
    protocol: BenchmarkProtocol,
    config: SharedTrackerConfig,
) -> dict[str, Any]:
    """Run one tracker candidate, then open prepared labels for scoring."""

    camera_ids = prepared.camera_ids
    trackers = {
        camera_id: SharedBearingTracker(camera_id, config)
        for camera_id in camera_ids
    }
    sweep_runtime_ms: list[float] = []
    maximum_hypothesis_count = 1
    use_cached_scanlets = (
        prepared.scanlets is not None
        and prepared.scanlet_preparation_fingerprint
        == config.scanlet_preparation_fingerprint
    )
    for sweep in range(protocol.revolution_count):
        started = time.perf_counter()
        for camera_id in camera_ids:
            if use_cached_scanlets:
                trackers[camera_id].update_scanlets(
                    sweep,
                    prepared.scanlets.get((camera_id, sweep), ()),
                )
            else:
                trackers[camera_id].update_sweep(
                    sweep,
                    prepared.observations.get((camera_id, sweep), ()),
                    prepared.confidence_by_uid,
                )
            maximum_hypothesis_count = max(
                maximum_hypothesis_count,
                trackers[camera_id].hypothesis_count,
            )
        sweep_runtime_ms.append((time.perf_counter() - started) * 1000.0)

    # This is the first identity-label access. Both trackers have completed all
    # sweeps before the offline file is opened.
    offline_labels = _load_offline_scoring_labels(prepared, protocol)
    uid_truth = offline_labels.uid_to_identity
    identities_by_camera: dict[str, set[str]] = {
        camera_id: set() for camera_id in camera_ids
    }
    purities: list[float] = []
    fragment_counts: dict[str, int] = defaultdict(int)
    confirmed_track_counts: dict[str, int] = {}
    false_reactivation_count = 0
    reactivation_count = 0
    for camera_id, tracker in trackers.items():
        confirmed_count = 0
        for track in tracker.all_tracks:
            status = track.status(config, protocol.revolution_count - 1)
            counts: dict[str, int] = defaultdict(int)
            for sample in track.samples:
                for uid in sample.detection_uids:
                    identity = uid_truth.get(uid)
                    if identity:
                        counts[identity] += 1
            identity, purity = _dominant_real_identity(counts)
            if identity is not None:
                purities.append(purity)
                fragment_counts[f"{camera_id}:{identity}"] += 1
                if status in {"confirmed", "coasting"}:
                    identities_by_camera[camera_id].add(identity)
            if status in {"confirmed", "coasting"}:
                confirmed_count += 1
            for boundary in track.reconnection_boundaries:
                reactivation_count += 1
                before: dict[str, int] = defaultdict(int)
                after: dict[str, int] = defaultdict(int)
                for sample in track.samples[:boundary]:
                    for uid in sample.detection_uids:
                        identity = uid_truth.get(uid)
                        if identity:
                            before[identity] += 1
                for sample in track.samples[boundary:]:
                    for uid in sample.detection_uids:
                        identity = uid_truth.get(uid)
                        if identity:
                            after[identity] += 1
                before_identity = (
                    max(before, key=before.get) if before else None
                )
                after_identity = max(after, key=after.get) if after else None
                if (
                    before_identity is None
                    or after_identity is None
                    or before_identity != after_identity
                ):
                    false_reactivation_count += 1
        confirmed_track_counts[camera_id] = confirmed_count

    common_observed = (
        offline_labels.observed_real[camera_ids[0]]
        & offline_labels.observed_real[camera_ids[1]]
    )
    common_confirmed = (
        identities_by_camera[camera_ids[0]] & identities_by_camera[camera_ids[1]]
    )
    common_rate = len(common_confirmed) / max(len(common_observed), 1)
    return {
        "seed": prepared.seed,
        "split": prepared.split,
        "corruption_level": prepared.corruption_level,
        "median_track_purity": float(np.median(purities)) if purities else 0.0,
        "common_observed_identity_count": len(common_observed),
        "common_confirmed_identity_count": len(common_confirmed),
        "common_confirmed_rate": common_rate,
        "confirmed_track_counts": confirmed_track_counts,
        "track_count_by_camera": {
            camera_id: len(trackers[camera_id].all_tracks) for camera_id in camera_ids
        },
        "online_track_count_by_camera": {
            camera_id: len(trackers[camera_id].tracks) for camera_id in camera_ids
        },
        "mean_fragments_per_real_identity": float(np.mean(list(fragment_counts.values())))
        if fragment_counts
        else 0.0,
        "maximum_hypothesis_count": maximum_hypothesis_count,
        "reactivation_count": reactivation_count,
        "false_reactivation_count": false_reactivation_count,
        "false_reactivation_rate": (
            false_reactivation_count / max(reactivation_count, 1)
        ),
        "sweep_runtime_p95_ms": float(np.percentile(sweep_runtime_ms, 95.0))
        if sweep_runtime_ms
        else 0.0,
        "tracker_event_count": sum(len(tracker.events) for tracker in trackers.values()),
        "prepared_cache_status": prepared.cache_status,
        "online_truth_used": False,
        "truth_opened_after_tracking": True,
    }


def evaluate_tracker_episode(
    episode_dir: str | Path,
    protocol: BenchmarkProtocol,
    config: SharedTrackerConfig,
    corruption_level: str,
    *,
    expected_gimbal_pose_error: bool = True,
    split_override: str | None = None,
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Score one anonymous tracking run with labels opened only afterwards."""

    prepared = prepare_tracker_episode(
        episode_dir,
        protocol,
        corruption_level,
        expected_gimbal_pose_error=expected_gimbal_pose_error,
        split_override=split_override,
        cache_dir=cache_dir,
    )
    return evaluate_prepared_tracker_episode(prepared, protocol, config)


def _aggregate(
    rows: Sequence[Mapping[str, Any]],
    split: str,
    levels: Sequence[str] | None = None,
) -> dict[str, Any]:
    selected = [row for row in rows if row["split"] == split]
    by_level: dict[str, Any] = {}
    for level in levels or CORRUPTION_LEVELS:
        level_rows = [row for row in selected if row["corruption_level"] == level]
        by_level[level] = {
            "episode_count": len(level_rows),
            "median_track_purity": float(
                np.median([row["median_track_purity"] for row in level_rows])
            ) if level_rows else 0.0,
            "mean_common_confirmed_rate": float(
                np.mean([row["common_confirmed_rate"] for row in level_rows])
            ) if level_rows else 0.0,
            "median_common_confirmed_rate": float(
                np.median([row["common_confirmed_rate"] for row in level_rows])
            ) if level_rows else 0.0,
            "mean_fragments_per_real_identity": float(
                np.mean([row["mean_fragments_per_real_identity"] for row in level_rows])
            ) if level_rows else 0.0,
            "false_reactivation_rate": (
                sum(int(row.get("false_reactivation_count", 0)) for row in level_rows)
                / max(
                    sum(int(row.get("reactivation_count", 0)) for row in level_rows),
                    1,
                )
            ),
            "sweep_runtime_p95_ms": float(np.percentile(
                [float(row.get("sweep_runtime_p95_ms", 0.0)) for row in level_rows],
                95.0,
            )) if level_rows else 0.0,
        }
    all_purity = [float(row["median_track_purity"]) for row in selected]
    reactivation_count = sum(
        int(row.get("reactivation_count", 0)) for row in selected
    )
    false_reactivation_count = sum(
        int(row.get("false_reactivation_count", 0)) for row in selected
    )
    return {
        "episode_level_count": len(selected),
        "median_track_purity": float(np.median(all_purity)) if all_purity else 0.0,
        "mean_fragments_per_real_identity": float(np.mean([
            float(row["mean_fragments_per_real_identity"]) for row in selected
        ])) if selected else 0.0,
        "reactivation_count": reactivation_count,
        "false_reactivation_count": false_reactivation_count,
        "false_reactivation_rate": (
            false_reactivation_count / max(reactivation_count, 1)
        ),
        "sweep_runtime_p95_ms": float(np.percentile([
            float(row.get("sweep_runtime_p95_ms", 0.0)) for row in selected
        ], 95.0)) if selected else 0.0,
        "by_corruption_level": by_level,
    }


def _selection_key(candidate: Mapping[str, Any]) -> tuple[float, ...]:
    validation = candidate["validation"]
    levels = validation["by_corruption_level"]
    active = [
        values
        for values in levels.values()
        if "episode_count" not in values
        or int(values.get("episode_count", 0)) > 0
    ]
    return (
        min(
            (float(values["mean_common_confirmed_rate"]) for values in active),
            default=0.0,
        ),
        float(validation["median_track_purity"]),
        -max(
            (
                float(values["mean_fragments_per_real_identity"])
                for values in active
            ),
            default=0.0,
        ),
        -float(validation.get("false_reactivation_rate", 0.0)),
        -float(validation.get("sweep_runtime_p95_ms", 0.0)),
        float(candidate["config"]["chi2_confidence"]),
    )


def _acceptance(validation: Mapping[str, Any]) -> dict[str, Any]:
    levels = validation["by_corruption_level"]
    false_reactivation_rate = float(validation.get("false_reactivation_rate", 0.0))
    baseline_false_reactivation_rate = float(
        validation.get("baseline_false_reactivation_rate", false_reactivation_rate)
    )
    fragmentation = float(
        validation.get("mean_fragments_per_real_identity", 0.0)
    )
    baseline_fragmentation = float(
        validation.get("baseline_mean_fragments_per_real_identity", fragmentation)
    )
    sweep_runtime_p95_ms = float(validation.get("sweep_runtime_p95_ms", 0.0))
    checks: dict[str, bool] = {
        "median_track_purity": float(validation["median_track_purity"])
        >= TRACKER_ACCEPTANCE["median_track_purity"],
        "false_reactivation_rate_absolute": false_reactivation_rate
        <= TRACKER_ACCEPTANCE["maximum_false_reactivation_rate"],
        "false_reactivation_rate_not_above_baseline": false_reactivation_rate
        <= baseline_false_reactivation_rate + 1.0e-12,
        "fragmentation_not_above_baseline": fragmentation
        <= baseline_fragmentation + 1.0e-12,
        "sweep_runtime_p95_ms": sweep_runtime_p95_ms
        <= TRACKER_ACCEPTANCE["maximum_sweep_runtime_p95_ms"],
    }
    for level, values in levels.items():
        if "episode_count" in values and int(values.get("episode_count", 0)) <= 0:
            continue
        threshold_key = f"{level}_common_confirmed_rate"
        threshold = float(
            TRACKER_ACCEPTANCE.get(
                threshold_key,
                TRACKER_ACCEPTANCE["light_common_confirmed_rate"],
            )
        )
        checks[threshold_key] = (
            float(values["mean_common_confirmed_rate"]) >= threshold
        )
    return {
        "accepted": all(checks.values()),
        "thresholds": dict(TRACKER_ACCEPTANCE),
        "checks": checks,
        "failure_reasons": [name for name, passed in checks.items() if not passed],
    }


def _select_candidate(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], int]:
    """Select within the passing set before applying performance ranking."""

    if not candidates:
        raise ValueError("shared tracker calibration produced no candidates")
    accepted = [
        candidate
        for candidate in candidates
        if _acceptance(candidate["validation"])["accepted"]
    ]
    ranked = accepted or list(candidates)
    return max(ranked, key=_selection_key), len(accepted)


def _tracker_config_from_mapping(values: Mapping[str, Any]) -> SharedTrackerConfig:
    normalized = dict(values)
    normalized["allowed_heading_offsets_deg"] = tuple(
        float(value) for value in normalized["allowed_heading_offsets_deg"]
    )
    normalized["corridor_x_bounds_m"] = tuple(
        float(value) for value in normalized["corridor_x_bounds_m"]
    )
    return SharedTrackerConfig(**normalized)


def _validated_reusable_candidates(
    evidence_path: Path,
    protocol: BenchmarkProtocol,
) -> list[dict[str, Any]]:
    """Validate a complete train/validation grid before reusing its scores."""

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") not in {
        LEGACY_TRACKER_CALIBRATION_SCHEMA,
        PREVIOUS_TRACKER_CALIBRATION_SCHEMA,
        CONTENDED_TRACKER_CALIBRATION_SCHEMA,
        TRACKER_CALIBRATION_SCHEMA,
    }:
        raise ValueError("unsupported shared tracker calibration evidence schema")
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("shared tracker calibration protocol fingerprint mismatch")
    if payload.get("test_data_accessed") is not False:
        raise ValueError("shared tracker calibration evidence accessed test data")

    expected_configs = {
        config.fingerprint: config for config in tracker_candidate_configs(protocol)
    }
    candidates = list(payload.get("candidates", []))
    if (
        int(payload.get("candidate_count", -1)) != len(expected_configs)
        or len(candidates) != len(expected_configs)
    ):
        raise ValueError("shared tracker calibration candidate grid is incomplete")

    expected_rows = {
        (int(seed), level)
        for seed in protocol.train_seeds + protocol.validation_seeds
        for level in protocol.corruption_levels
    }
    seen_fingerprints: set[str] = set()
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        config = _tracker_config_from_mapping(candidate["config"])
        fingerprint = str(candidate.get("tracker_fingerprint", ""))
        if fingerprint != config.fingerprint or fingerprint not in expected_configs:
            raise ValueError("shared tracker candidate fingerprint mismatch")
        if fingerprint in seen_fingerprints:
            raise ValueError("shared tracker calibration repeats a candidate")
        seen_fingerprints.add(fingerprint)

        rows = list(candidate.get("rows", []))
        actual_rows = {
            (int(row.get("seed", -1)), str(row.get("corruption_level", "")))
            for row in rows
        }
        if actual_rows != expected_rows or len(rows) != len(expected_rows):
            raise ValueError("shared tracker candidate row matrix is incomplete")
        for row in rows:
            if row.get("split") != split_for_seed(protocol, int(row["seed"])):
                raise ValueError("shared tracker candidate split mismatch")
            if row.get("online_truth_used") is not False:
                raise ValueError("shared tracker candidate used truth online")
            if row.get("truth_opened_after_tracking") is not True:
                raise ValueError("shared tracker candidate lacks offline scoring proof")
        if candidate.get("train") != _aggregate(
            rows, "train", protocol.corruption_levels
        ):
            raise ValueError("shared tracker train aggregate does not match rows")
        candidate_validation = dict(candidate.get("validation", {}))
        candidate_validation.pop("baseline_false_reactivation_rate", None)
        candidate_validation.pop(
            "baseline_mean_fragments_per_real_identity", None
        )
        if candidate_validation != _aggregate(
            rows, "validation", protocol.corruption_levels
        ):
            raise ValueError("shared tracker validation aggregate does not match rows")
        validated.append(dict(candidate))
    if payload.get("schema_version") == TRACKER_CALIBRATION_SCHEMA:
        if (
            payload.get("validation_runtime_measurement_policy")
            != VALIDATION_RUNTIME_MEASUREMENT_POLICY
        ):
            raise ValueError("shared tracker evidence lacks isolated runtime proof")
        for candidate in validated:
            if (
                candidate.get("validation_runtime_measurement_policy")
                != VALIDATION_RUNTIME_MEASUREMENT_POLICY
            ):
                raise ValueError("shared tracker candidate lacks isolated runtime proof")
            if any(
                row.get("runtime_measurement_policy")
                != VALIDATION_RUNTIME_MEASUREMENT_POLICY
                for row in candidate["rows"]
                if row["split"] == "validation"
            ):
                raise ValueError("shared tracker validation row lacks isolated runtime proof")
    baseline = next(
        (
            candidate
            for candidate in validated
            if candidate["tracker_fingerprint"]
            == tracker_config_for_protocol(protocol).fingerprint
        ),
        None,
    )
    if baseline is None:
        raise ValueError("shared tracker calibration omits the baseline candidate")
    expected_false_rate = float(
        baseline["validation"]["false_reactivation_rate"]
    )
    expected_fragmentation = float(
        baseline["validation"]["mean_fragments_per_real_identity"]
    )
    for candidate in validated:
        validation = candidate["validation"]
        if not math.isclose(
            float(validation.get("baseline_false_reactivation_rate", math.nan)),
            expected_false_rate,
            abs_tol=1.0e-12,
        ):
            raise ValueError("shared tracker baseline reactivation metric mismatch")
        if not math.isclose(
            float(validation.get(
                "baseline_mean_fragments_per_real_identity", math.nan
            )),
            expected_fragmentation,
            abs_tol=1.0e-12,
        ):
            raise ValueError("shared tracker baseline fragmentation metric mismatch")
    return validated


def _attach_baseline_metrics(
    candidates: Sequence[Mapping[str, Any]],
    protocol: BenchmarkProtocol | None = None,
) -> list[dict[str, Any]]:
    normalized = [dict(candidate) for candidate in candidates]
    baseline_fingerprint = (
        SharedTrackerConfig().fingerprint
        if protocol is None
        else tracker_config_for_protocol(protocol).fingerprint
    )
    baseline = next(
        (
            candidate
            for candidate in normalized
            if candidate["tracker_fingerprint"] == baseline_fingerprint
        ),
        normalized[0] if normalized else None,
    )
    if baseline is None:
        raise RuntimeError("tracker candidate replay produced no baseline")
    baseline_validation = baseline["validation"]
    for candidate in normalized:
        validation = dict(candidate["validation"])
        validation["baseline_false_reactivation_rate"] = float(
            baseline_validation["false_reactivation_rate"]
        )
        validation["baseline_mean_fragments_per_real_identity"] = float(
            baseline_validation["mean_fragments_per_real_identity"]
        )
        candidate["validation"] = validation
    return normalized


def _refresh_validation_rows_serially(
    candidates: Sequence[Mapping[str, Any]],
    prepared: Sequence[PreparedTrackerEpisode],
    protocol: BenchmarkProtocol,
) -> list[dict[str, Any]]:
    """Measure validation wall time without concurrent candidate contention."""

    validation_inputs = [
        episode for episode in prepared if episode.split == "validation"
    ]
    validation_episodes = {
        (episode.seed, episode.corruption_level): episode
        for episode in validation_inputs
    }
    if not validation_episodes or len(validation_episodes) != len(validation_inputs):
        raise ValueError("isolated runtime pass requires unique validation episodes")

    refreshed: list[dict[str, Any]] = []
    for raw_candidate in candidates:
        candidate = dict(raw_candidate)
        config = _tracker_config_from_mapping(candidate["config"])
        rows: list[dict[str, Any]] = []
        for raw_row in candidate["rows"]:
            row = dict(raw_row)
            if row["split"] == "validation":
                key = (int(row["seed"]), str(row["corruption_level"]))
                row = evaluate_prepared_tracker_episode(
                    validation_episodes[key], protocol, config
                )
                row["runtime_measurement_policy"] = (
                    VALIDATION_RUNTIME_MEASUREMENT_POLICY
                )
            else:
                row["runtime_measurement_policy"] = PARALLEL_QUALITY_REPLAY_POLICY
            rows.append(row)
        candidate["rows"] = rows
        candidate["train"] = _aggregate(
            rows, "train", protocol.corruption_levels
        )
        candidate["validation"] = _aggregate(
            rows, "validation", protocol.corruption_levels
        )
        candidate["validation_runtime_measurement_policy"] = (
            VALIDATION_RUNTIME_MEASUREMENT_POLICY
        )
        refreshed.append(candidate)
    return _attach_baseline_metrics(refreshed, protocol)


def _evaluate_candidate_grid(
    prepared: Sequence[PreparedTrackerEpisode],
    protocol: BenchmarkProtocol,
    configs: Sequence[SharedTrackerConfig] | None = None,
    *,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """Replay candidates concurrently while preserving serial grid order."""

    if not 1 <= int(max_workers) <= 4:
        raise ValueError("tracker candidate replay supports one to four workers")
    selected_configs = tuple(configs or tracker_candidate_configs(protocol))
    if not selected_configs:
        raise ValueError("tracker candidate grid cannot be empty")
    tasks = [
        (config_index, episode_index, config, episode)
        for config_index, config in enumerate(selected_configs)
        for episode_index, episode in enumerate(prepared)
    ]
    ordered_rows: list[list[dict[str, Any] | None]] = [
        [None] * len(prepared) for _ in selected_configs
    ]
    worker_count = min(int(max_workers), max(1, len(tasks)))
    executor = ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="tracker-candidate",
    )
    futures: list[tuple[int, int, Future[dict[str, Any]]]] = []
    try:
        for config_index, episode_index, config, episode in tasks:
            futures.append((
                config_index,
                episode_index,
                executor.submit(
                    evaluate_prepared_tracker_episode,
                    episode,
                    protocol,
                    config,
                ),
            ))
        for config_index, episode_index, future in futures:
            ordered_rows[config_index][episode_index] = future.result()
    except BaseException:
        for _, _, future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    candidates: list[dict[str, Any]] = []
    for config, maybe_rows in zip(selected_configs, ordered_rows):
        if any(row is None for row in maybe_rows):
            raise RuntimeError("tracker candidate replay returned an incomplete grid")
        rows = [dict(row) for row in maybe_rows if row is not None]
        candidates.append({
            "config": asdict(config),
            "tracker_fingerprint": config.fingerprint,
            "train": _aggregate(rows, "train", protocol.corruption_levels),
            "validation": _aggregate(
                rows, "validation", protocol.corruption_levels
            ),
            "rows": rows,
        })

    return _refresh_validation_rows_serially(candidates, prepared, protocol)


def calibrate_and_freeze_tracker(
    episode_dirs: Sequence[str | Path],
    calibration_manifest_hint: str | Path,
    output_path: str | Path,
    protocol: BenchmarkProtocol | None = None,
    *,
    max_workers: int = 4,
    prepared_cache_dir: str | Path | None = None,
) -> Path:
    """Select only on train/validation episodes and write a fail-closed freeze."""

    protocol = protocol or BenchmarkProtocol()
    roots = [Path(path).resolve() for path in episode_dirs]
    expected = set(protocol.train_seeds + protocol.validation_seeds)
    actual = {
        int(_validate_anonymous_episode(path, protocol)["seed"])
        for path in roots
    }
    if actual != expected or len(actual) != len(roots):
        raise ValueError("shared tracker calibration requires complete unique train/validation episodes")

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path = output_path.with_name("shared_tracker_calibration.json")
    source_evidence_sha256: str | None = None
    reused_complete_candidate_evidence = False
    reused_quality_candidate_evidence = False
    runtime_refresh_required = False
    if evidence_path.is_file():
        try:
            candidates = _validated_reusable_candidates(evidence_path, protocol)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            candidates = []
        else:
            source_evidence_sha256 = sha256_file(evidence_path)
            evidence_payload = json.loads(
                evidence_path.read_text(encoding="utf-8")
            )
            reused_complete_candidate_evidence = (
                evidence_payload.get("schema_version")
                == TRACKER_CALIBRATION_SCHEMA
                and evidence_payload.get("validation_runtime_measurement_policy")
                == VALIDATION_RUNTIME_MEASUREMENT_POLICY
            )
            reused_quality_candidate_evidence = not reused_complete_candidate_evidence
            runtime_refresh_required = reused_quality_candidate_evidence
            archive = evidence_path.with_name(
                "shared_tracker_calibration.initial_selection.json"
            )
            if not archive.exists():
                shutil.copy2(evidence_path, archive)
    else:
        candidates = []

    if not candidates or runtime_refresh_required:
        cache_dir = (
            Path(prepared_cache_dir).resolve()
            if prepared_cache_dir is not None
            else output_path.parent / "prepared_tracker_cache"
        )
        prepared = [
            prepare_tracker_episode(
                root,
                protocol,
                level,
                cache_dir=cache_dir,
            )
            for root in roots
            for level in protocol.corruption_levels
        ]
        if runtime_refresh_required:
            candidates = _refresh_validation_rows_serially(
                candidates, prepared, protocol
            )
        else:
            candidates = _evaluate_candidate_grid(
                prepared,
                protocol,
                max_workers=max_workers,
            )

    selected, accepted_candidate_count = _select_candidate(candidates)
    selected_config = _tracker_config_from_mapping(selected["config"])
    acceptance = _acceptance(selected["validation"])
    calibration_hint = Path(calibration_manifest_hint).resolve()
    hint_hash = sha256_file(calibration_hint) if calibration_hint.is_file() else "pending"
    write_json(evidence_path, {
        "schema_version": TRACKER_CALIBRATION_SCHEMA,
        "protocol_fingerprint": protocol.fingerprint,
        "candidate_count": len(candidates),
        "accepted_candidate_count": accepted_candidate_count,
        "selection_basis": [
            "validation_acceptance_required",
            "validation_worst_corruption_common_confirmed_rate_desc",
            "validation_median_track_purity_desc",
            "validation_fragmentation_asc",
            "chi2_confidence_desc_on_exact_tie",
        ],
        "reused_complete_candidate_evidence": reused_complete_candidate_evidence,
        "reused_quality_candidate_evidence": reused_quality_candidate_evidence,
        "source_evidence_sha256": source_evidence_sha256,
        "validation_runtime_measurement_policy": (
            VALIDATION_RUNTIME_MEASUREMENT_POLICY
        ),
        "calibration_manifest": str(calibration_hint),
        "calibration_manifest_sha256": hint_hash,
        "selected_tracker_fingerprint": selected_config.fingerprint,
        "selected_config": asdict(selected_config),
        "selected_train_metrics": selected["train"],
        "selected_validation_metrics": selected["validation"],
        "acceptance": acceptance,
        "candidates": candidates,
        "test_data_accessed": False,
    })
    if not acceptance["accepted"]:
        if protocol.scan_profile != "s180_triangle_1s_v1":
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                "shared tracker validation acceptance failed; "
                f"see {evidence_path}"
            )
        payload = tracker_freeze_payload(
            selected_config,
            calibration_manifest=str(calibration_hint),
            calibration_manifest_sha256=hint_hash,
            validation_metrics={
                **selected["validation"],
                "acceptance": acceptance,
                "calibration_evidence": str(evidence_path),
                "calibration_evidence_sha256": sha256_file(evidence_path),
            },
        )
        payload.update(
            {
                "diagnostic_only": True,
                "formal_use_allowed": False,
                "promotion_allowed": False,
                "diagnostic_reason": "shared_tracker_validation_failed",
            }
        )
        write_json(output_path, payload)
        return output_path
    payload = tracker_freeze_payload(
        selected_config,
        calibration_manifest=str(calibration_hint),
        calibration_manifest_sha256=hint_hash,
        validation_metrics={
            **selected["validation"],
            "acceptance": acceptance,
            "calibration_evidence": str(evidence_path),
            "calibration_evidence_sha256": sha256_file(evidence_path),
        },
    )
    write_json(output_path, payload)
    return output_path


__all__ = [
    "PREPARATION_POLICY_VERSION",
    "PREPARED_TRACKER_CACHE_SCHEMA",
    "PreparedTrackerEpisode",
    "TRACKER_ACCEPTANCE",
    "TRACKER_CALIBRATION_SCHEMA",
    "TRACKER_DIAGNOSTIC_LEVELS",
    "VALIDATION_RUNTIME_MEASUREMENT_POLICY",
    "_acceptance",
    "_evaluate_candidate_grid",
    "_select_candidate",
    "_validated_reusable_candidates",
    "calibrate_and_freeze_tracker",
    "evaluate_prepared_tracker_episode",
    "evaluate_tracker_episode",
    "prepare_tracker_episode",
    "tracker_candidate_configs",
    "tracker_config_for_protocol",
]
