"""Build immutable causal snapshots and offline labels from one raw episode."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from dual_optical_40target.core import (
    AnonymousDetection,
    CameraSpec,
    CameraState,
    ray_observation_from_detection,
    sweep_index,
)

from .contracts import (
    BenchmarkProtocol,
    CandidateGatePolicy,
    CORRUPTION_LEVELS,
    RevolutionSnapshot,
    SHARED_CANDIDATE_GRAPH_VERSION,
    SnapshotTrack,
    SnapshotTrackSample,
    candidate_graph_fingerprint,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from .tracking import (
    SharedBearingTrack,
    SharedBearingTracker,
    SharedTrackerConfig,
    load_tracker_freeze,
)


DATASET_SCHEMA_VERSION = "dual-optical-online-dataset-v2"
LEGACY_DATASET_SCHEMA_VERSION = "dual-optical-online-dataset-v1"
CORRUPTION_POLICY: Mapping[str, Mapping[str, float | int]] = {
    "clean": {
        "miss_probability": 0.0,
        "transient_false_per_camera_second": 0.0,
        "persistent_false_per_camera": 0,
    },
    "light": {
        "miss_probability": 0.03,
        "transient_false_per_camera_second": 2.0,
        "persistent_false_per_camera": 0,
    },
    "medium": {
        "miss_probability": 0.07,
        "transient_false_per_camera_second": 4.0,
        "persistent_false_per_camera": 1,
    },
    "heavy": {
        "miss_probability": 0.12,
        "transient_false_per_camera_second": 8.0,
        "persistent_false_per_camera": 2,
    },
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_seed(*values: object) -> int:
    payload = "|".join(str(value) for value in values).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def split_for_seed(protocol: BenchmarkProtocol, seed: int) -> str:
    if seed in protocol.train_seeds:
        return "train"
    if seed in protocol.validation_seeds:
        return "validation"
    if seed in protocol.test_seeds:
        return "test"
    raise ValueError(f"seed {seed} is outside the frozen protocol")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_vector(value: str) -> tuple[float, ...]:
    parsed = json.loads(value)
    return tuple(float(item) for item in parsed)


@dataclass(frozen=True)
class _RawDetection:
    detection_uid: str
    camera_id: str
    frame_index: int
    measurement_timestamp: float
    arrival_timestamp: float
    bbox_xyxy: tuple[float, float, float, float]
    center_px: tuple[float, float]
    confidence: float


@dataclass(frozen=True)
class _FalseTrackSpec:
    false_id: str
    camera_id: str
    start_s: float
    end_s: float
    azimuth_offset_deg: float
    elevation_offset_deg: float
    azimuth_rate_deg_s: float
    elevation_rate_deg_s: float
    persistent: bool


def validate_raw_episode(
    episode_dir: str | Path,
    protocol: BenchmarkProtocol,
    *,
    expected_seed: int | None = None,
    expected_gimbal_pose_error: bool | None = True,
    split_override: str | None = None,
) -> dict[str, Any]:
    """Validate raw records and return hashes required for resumable reuse."""

    root = Path(episode_dir).resolve()
    required = {
        "scenario": root / "scenario.json",
        "manifest": root / "record_manifest.json",
        "metrics": root / "metrics.json",
        "detections": root / "online" / "anonymous_detections.csv",
        "scan": root / "online" / "camera_scan.csv",
        "detection_truth": root / "truth" / "detection_truth.csv",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ValueError(f"raw episode is incomplete: {missing}")
    scenario = json.loads(required["scenario"].read_text(encoding="utf-8"))
    values = scenario["scenario"]
    seed = int(values["seed"])
    if expected_seed is not None and seed != int(expected_seed):
        raise ValueError("episode seed does not match its batch entry")
    checks = {
        "target_count": int(values["target_count"]) == protocol.target_count,
        "target_speed_mps": math.isclose(
            float(values["target_speed_mps"]), protocol.target_speed_mps, abs_tol=1e-9
        ),
        "duration_s": math.isclose(
            float(values["duration_s"]), protocol.duration_s, abs_tol=1e-9
        ),
        "sample_rate_hz": math.isclose(
            float(values["sample_rate_hz"]), protocol.sample_rate_hz, abs_tol=1e-9
        ),
        "clock_speed": math.isclose(
            float(values["clock_speed"]), protocol.clock_speed, abs_tol=1e-9
        ),
        "scan_period_s": math.isclose(
            float(values["scan_period_s"]), protocol.scan_period_s, abs_tol=1e-9
        ),
        "scan_mode": str(values.get("scan_mode")) == protocol.scan_mode,
        "scan_half_span_deg": (
            protocol.scan_mode == "continuous_360"
            or math.isclose(
                float(values.get("scan_half_span_deg", -1.0)),
                protocol.scan_half_span_deg,
                abs_tol=1e-9,
            )
        ),
        "target_motion_profile": str(values.get("target_motion_profile"))
        == "split_0_minus30",
        "gimbal_pose_error_enabled": (
            expected_gimbal_pose_error is None
            or bool(values.get("gimbal_pose_error_enabled"))
            is bool(expected_gimbal_pose_error)
        ),
        "gimbal_fixed_bias_mrad": math.isclose(
            float(values.get("gimbal_fixed_bias_mrad", -1.0)),
            protocol.gimbal_fixed_bias_rms_mrad,
            abs_tol=1e-9,
        ),
        "gimbal_jitter_rms_mrad": math.isclose(
            float(values.get("gimbal_jitter_rms_mrad", -1.0)),
            protocol.gimbal_jitter_rms_mrad,
            abs_tol=1e-9,
        ),
        "camera_b_scan_phase_offset_s": math.isclose(
            float(values.get("camera_b_scan_phase_offset_s", 0.0)),
            protocol.camera_b_scan_phase_offset_s,
            abs_tol=1e-9,
        ),
        "deterministic_step_mode": str(
            values.get("deterministic_step_mode", "legacy_wall_yield")
        ) == protocol.deterministic_step_mode,
    }
    if not all(checks.values()):
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise ValueError(f"raw episode violates frozen protocol: {failed}")
    manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", {})
    for name in ("anonymous_detections", "camera_scan", "detection_truth", "metrics"):
        relative = artifacts.get(name)
        if not relative or not (root / relative).is_file():
            raise ValueError(f"record manifest is missing artifact {name}")
    headings = [
        float(item.get("heading_offset_deg") or 0.0)
        for item in scenario.get("target_specs_offline_truth_only", [])
    ]
    if len(headings) != protocol.target_count:
        raise ValueError("scenario does not contain the frozen target truth count")
    zero_count = sum(math.isclose(value, 0.0, abs_tol=1e-9) for value in headings)
    minus_count = sum(math.isclose(value, -30.0, abs_tol=1e-9) for value in headings)
    if (zero_count, minus_count) != (
        protocol.zero_heading_count,
        protocol.minus_thirty_heading_count,
    ):
        raise ValueError("scenario heading groups are not the frozen 50/50 split")
    metrics = json.loads(required["metrics"].read_text(encoding="utf-8"))
    if int(metrics.get("spawned_target_count", -1)) != protocol.target_count:
        raise ValueError("raw episode did not spawn all frozen-protocol targets")
    if int(metrics.get("target_count", -1)) != protocol.target_count:
        raise ValueError("raw episode metrics target count is inconsistent")
    if int(metrics.get("online_truth_leakage_count", -1)) != 0:
        raise ValueError("raw episode reports online truth leakage")
    expected_frames = int(round(protocol.duration_s * protocol.sample_rate_hz))
    scan_rows = _read_csv(required["scan"])
    scan_keys = {
        (row["camera_id"], int(row["frame_index"])) for row in scan_rows
    }
    expected_camera_ids = {
        str(values["camera_a_name"]), str(values["camera_b_name"])
    }
    actual_camera_ids = {camera_id for camera_id, _ in scan_keys}
    if actual_camera_ids != expected_camera_ids:
        raise ValueError("raw episode scan records do not cover both cameras")
    expected_scan_keys = {
        (camera_id, frame_index)
        for camera_id in expected_camera_ids
        for frame_index in range(expected_frames)
    }
    if not expected_scan_keys <= scan_keys:
        raise ValueError("raw episode scan records are incomplete")
    return {
        "seed": seed,
        "split": (
            str(split_override)
            if split_override is not None
            else split_for_seed(protocol, seed)
        ),
        "protocol_fingerprint": protocol.fingerprint,
        "files": {name: sha256_file(path) for name, path in required.items()},
    }


def _load_raw_episode(root: Path) -> tuple[dict[str, Any], list[_RawDetection], list[dict[str, str]], dict[str, str]]:
    scenario = json.loads((root / "scenario.json").read_text(encoding="utf-8"))
    detections = [
        _RawDetection(
            detection_uid=row["detection_uid"],
            camera_id=row["camera_id"],
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
    truth = {
        row["detection_uid"]: row["truth_id"]
        for row in _read_csv(root / "truth" / "detection_truth.csv")
        if row.get("truth_id")
    }
    return scenario, detections, scan_rows, truth


def _camera_states(scan_rows: Sequence[Mapping[str, str]]) -> dict[tuple[str, int], CameraState]:
    states: dict[tuple[str, int], CameraState] = {}
    for row in scan_rows:
        key = (str(row["camera_id"]), int(row["frame_index"]))
        states[key] = CameraState(
            camera_id=key[0],
            frame_index=key[1],
            timestamp=float(row["measurement_timestamp"]),
            position_ned=(0.0, 0.0, 0.0),
            yaw_deg=float(row["yaw_deg"]),
            pitch_deg=float(row["pitch_deg"]),
        )
    return states


def _false_track_specs(
    protocol: BenchmarkProtocol,
    seed: int,
    corruption_level: str,
    camera_ids: Sequence[str],
    states: Mapping[tuple[str, int], CameraState],
) -> tuple[_FalseTrackSpec, ...]:
    policy = CORRUPTION_POLICY[corruption_level]
    specs: list[_FalseTrackSpec] = []
    for camera_id in camera_ids:
        rng = np.random.default_rng(_stable_seed(seed, corruption_level, camera_id, "false"))
        transient_count = int(
            round(float(policy["transient_false_per_camera_second"]) * protocol.duration_s)
        )
        for index in range(transient_count):
            frame_index = int(rng.integers(0, int(protocol.duration_s * protocol.sample_rate_hz)))
            start_s = frame_index / protocol.sample_rate_hz
            state = states[(camera_id, frame_index)]
            specs.append(
                _FalseTrackSpec(
                    false_id=f"FA-{camera_id}-T{index:04d}",
                    camera_id=camera_id,
                    start_s=start_s,
                    end_s=min(protocol.duration_s, start_s + float(rng.uniform(0.01, 0.04))),
                    azimuth_offset_deg=state.yaw_deg + float(
                        rng.uniform(-0.4, 0.4) * CameraSpec().horizontal_fov_deg
                    ),
                    elevation_offset_deg=float(rng.uniform(-1.0, 1.0)),
                    azimuth_rate_deg_s=float(rng.uniform(-0.08, 0.08)),
                    elevation_rate_deg_s=float(rng.uniform(-0.03, 0.03)),
                    persistent=False,
                )
            )
        for index in range(int(policy["persistent_false_per_camera"])):
            specs.append(
                _FalseTrackSpec(
                    false_id=f"FA-{camera_id}-P{index:02d}",
                    camera_id=camera_id,
                    start_s=0.0,
                    end_s=protocol.duration_s,
                    azimuth_offset_deg=float(rng.uniform(-180.0, 180.0)),
                    elevation_offset_deg=float(rng.uniform(-0.8, 0.8)),
                    azimuth_rate_deg_s=float(rng.uniform(-0.05, 0.05)),
                    elevation_rate_deg_s=float(rng.uniform(-0.02, 0.02)),
                    persistent=True,
                )
            )
    return tuple(specs)


def _false_detections(
    specs: Sequence[_FalseTrackSpec],
    states: Mapping[tuple[str, int], CameraState],
    camera: CameraSpec,
    *,
    sample_rate_hz: float,
) -> Iterable[tuple[AnonymousDetection, str]]:
    focal = camera.focal_length_px
    for spec in specs:
        first = int(math.ceil(spec.start_s * sample_rate_hz - 1e-9))
        last = int(math.floor(spec.end_s * sample_rate_hz + 1e-9))
        for frame_index in range(first, last + 1):
            state = states.get((spec.camera_id, frame_index))
            if state is None:
                continue
            timestamp = frame_index / sample_rate_hz
            elapsed = timestamp - spec.start_s
            world_azimuth = spec.azimuth_offset_deg + spec.azimuth_rate_deg_s * elapsed
            world_elevation = -state.pitch_deg + spec.elevation_offset_deg + spec.elevation_rate_deg_s * elapsed
            local_yaw_deg = (world_azimuth - state.yaw_deg + 180.0) % 360.0 - 180.0
            local_yaw = math.radians(local_yaw_deg)
            local_elevation = math.radians(world_elevation + state.pitch_deg)
            if abs(local_yaw) > math.radians(camera.horizontal_fov_deg * 0.48):
                continue
            if abs(local_elevation) > math.radians(camera.vertical_fov_deg * 0.48):
                continue
            center_x = camera.width * 0.5 + focal * math.tan(local_yaw)
            center_y = camera.height * 0.5 + focal * math.tan(local_elevation)
            size = 5.0 if spec.persistent else 3.0
            uid = f"{spec.false_id}-F{frame_index:05d}"
            yield (
                AnonymousDetection(
                    detection_uid=uid,
                    camera_id=spec.camera_id,
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp,
                    bbox_xyxy=(center_x - size, center_y - size, center_x + size, center_y + size),
                    center_px=(center_x, center_y),
                    confidence=0.35 if spec.persistent else 0.25,
                ),
                spec.false_id,
            )


def _should_drop(seed: int, level: str, detection_uid: str, probability: float) -> bool:
    rng = np.random.default_rng(_stable_seed(seed, level, "miss", detection_uid))
    return bool(rng.random() < probability)


def _snapshot_tracks(
    tracker: SharedBearingTracker,
    cutoff: float,
    current_sweep: int,
) -> tuple[SnapshotTrack, ...]:
    result: list[SnapshotTrack] = []
    for track in tracker.tracks:
        samples = tuple(
            SnapshotTrackSample(
                sweep_index=int(sample.sweep_index),
                timestamp=float(sample.timestamp),
                direction_ned=tuple(float(value) for value in sample.direction_ned),
                detection_count=len(sample.detection_uids),
                bbox_area_px2=float(sample.bbox_area_px2),
                confidence=float(sample.confidence),
                measurement_covariance_deg2=tuple(
                    float(value) for value in sample.measurement_covariance_deg2
                ),
                state_vector=tuple(float(value) for value in sample.state_vector),
                state_covariance=tuple(
                    float(value) for value in sample.state_covariance
                ),
                innovation_mahalanobis2=float(sample.innovation_mahalanobis2),
            )
            for sample in track.samples
            if sample.timestamp <= cutoff + 1e-9
        )
        if samples:
            track_state = track.status(tracker.config, current_sweep)
            # Dormant tracks remain internal reconnection candidates.  They do
            # not represent a currently available online bearing and therefore
            # must not enter either station's cross-view candidate graph.
            if track_state == "dormant":
                continue
            # Online consumers cannot know whether a local track came from a
            # real detection or an injected false alarm.
            hit_set = set(track.hit_sweeps)
            result.append(
                SnapshotTrack(
                    track_id=track.track_id,
                    camera_id=tracker.camera_id,
                    samples=samples,
                    source_kind="anonymous",
                    track_state=track_state,
                    recent_sweep_hits=tuple(
                        sweep in hit_set
                        for sweep in range(current_sweep - 2, current_sweep + 1)
                    ),
                    missed_sweep_count=int(track.missed_sweeps),
                    ambiguity_count=int(track.ambiguity_count),
                )
            )
    return tuple(result)


def _track_prediction(
    track: SnapshotTrack,
    timestamp: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a causal bearing prediction and 2x2 angular covariance in radians."""

    sample = track.samples[-1]
    state = np.asarray(sample.state_vector, dtype=float)
    covariance = np.asarray(sample.state_covariance, dtype=float).reshape(4, 4)
    dt = max(0.0, float(timestamp) - float(sample.timestamp))
    transition = np.asarray(
        ((1.0, 0.0, dt, 0.0), (0.0, 1.0, 0.0, dt)),
        dtype=float,
    )
    angles_deg = transition @ state
    covariance_deg2 = transition @ covariance @ transition.T
    covariance_deg2 += np.asarray(
        sample.measurement_covariance_deg2, dtype=float
    ).reshape(2, 2)
    azimuth, elevation = np.radians(angles_deg)
    direction = np.asarray(
        (
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            -math.sin(elevation),
        ),
        dtype=float,
    )
    return direction, covariance_deg2 * (math.pi / 180.0) ** 2


def _signed_epipolar_residual(
    baseline_unit: np.ndarray,
    direction_a: np.ndarray,
    direction_b: np.ndarray,
) -> float | None:
    normal = np.cross(direction_a, baseline_unit)
    norm = float(np.linalg.norm(normal))
    if norm <= 1.0e-9:
        return None
    return math.asin(
        float(np.clip(np.dot(direction_b, normal / norm), -1.0, 1.0))
    )


def _epipolar_sigma_rad(
    baseline_unit: np.ndarray,
    state_a: tuple[np.ndarray, np.ndarray],
    state_b: tuple[np.ndarray, np.ndarray],
) -> float:
    """Propagate both track covariances into one signed epipolar residual."""

    direction_a, covariance_a = state_a
    direction_b, covariance_b = state_b
    def angles(direction: np.ndarray) -> tuple[float, float]:
        return (
            math.atan2(float(direction[1]), float(direction[0])),
            -math.atan2(float(direction[2]), math.hypot(float(direction[0]), float(direction[1]))),
        )
    def ray(azimuth: float, elevation: float) -> np.ndarray:
        return np.asarray(
            (
                math.cos(elevation) * math.cos(azimuth),
                math.cos(elevation) * math.sin(azimuth),
                -math.sin(elevation),
            ),
            dtype=float,
        )
    parameters = np.asarray((*angles(direction_a), *angles(direction_b)), dtype=float)
    jacobian = np.zeros(4, dtype=float)
    step = 1.0e-6
    for index in range(4):
        positive = parameters.copy()
        negative = parameters.copy()
        positive[index] += step
        negative[index] -= step
        positive_value = _signed_epipolar_residual(
            baseline_unit,
            ray(positive[0], positive[1]),
            ray(positive[2], positive[3]),
        )
        negative_value = _signed_epipolar_residual(
            baseline_unit,
            ray(negative[0], negative[1]),
            ray(negative[2], negative[3]),
        )
        if positive_value is None or negative_value is None:
            return math.inf
        jacobian[index] = (positive_value - negative_value) / (2.0 * step)
    covariance = np.zeros((4, 4), dtype=float)
    covariance[:2, :2] = covariance_a
    covariance[2:, 2:] = covariance_b
    return math.sqrt(max(float(jacobian @ covariance @ jacobian.T), 1.0e-12))


def build_shared_candidate_graph(
    *,
    tracks: Mapping[str, tuple[SnapshotTrack, ...]],
    camera_ids: tuple[str, str],
    camera_positions_ned: Mapping[str, tuple[float, float, float]],
    cutoff_timestamp: float,
    target_count: int,
    candidate_gate_policy: CandidateGatePolicy | None = None,
) -> tuple[tuple[tuple[str, str], ...], dict[str, int | float | str], str]:
    """Build one anonymous top-K epipolar whitelist shared by all routes."""

    started = time.perf_counter()
    left_id, right_id = camera_ids
    left_tracks = tuple(
        track for track in tracks[left_id]
        if track.samples and track.track_state not in {"dormant", "terminated"}
    )
    right_tracks = tuple(
        track for track in tracks[right_id]
        if track.samples and track.track_state not in {"dormant", "terminated"}
    )
    if candidate_gate_policy is None:
        top_k = min(16, max(8, int(math.ceil(1.5 * math.sqrt(target_count)))))
        gate_sigma = 8.0
    else:
        top_k = candidate_gate_policy.top_k(target_count)
        gate_sigma = candidate_gate_policy.normalized_gate_sigma
    baseline = (
        np.asarray(camera_positions_ned[right_id], dtype=float)
        - np.asarray(camera_positions_ned[left_id], dtype=float)
    )
    baseline /= max(float(np.linalg.norm(baseline)), 1.0e-12)
    left_states = [
        _track_prediction(track, cutoff_timestamp) for track in left_tracks
    ]
    right_states = [
        _track_prediction(track, cutoff_timestamp) for track in right_tracks
    ]
    scored: dict[tuple[str, str], float] = {}
    evaluated = len(left_tracks) * len(right_tracks)
    normalized = np.empty((len(left_tracks), len(right_tracks)), dtype=float)
    normalized.fill(np.inf)
    if left_tracks and right_tracks:
        left_directions = np.asarray([state[0] for state in left_states])
        right_directions = np.asarray([state[0] for state in right_states])
        plane_normals = np.cross(left_directions, baseline)
        plane_norms = np.linalg.norm(plane_normals, axis=1)
        valid_left = plane_norms > 1.0e-9
        plane_normals[valid_left] /= plane_norms[valid_left, None]
        sine_residual = np.abs(plane_normals @ right_directions.T)
        residual_rad = np.arcsin(np.clip(sine_residual, 0.0, 1.0))
        # The maximum angular variance is a conservative first-order bound
        # for the normal-to-epipolar-plane component. It includes the frozen
        # bearing measurement variance carried by each local track.
        left_sigma2 = np.asarray(
            [max(float(np.linalg.eigvalsh(state[1])[-1]), 1.0e-12) for state in left_states]
        )
        right_sigma2 = np.asarray(
            [max(float(np.linalg.eigvalsh(state[1])[-1]), 1.0e-12) for state in right_states]
        )
        sigma = np.sqrt(left_sigma2[:, None] + right_sigma2[None, :])
        normalized = residual_rad / np.maximum(sigma, 1.0e-6)
        normalized[~valid_left, :] = np.inf
    eligible = np.isfinite(normalized) & (normalized <= gate_sigma)
    def maturity_rank(track: SnapshotTrack) -> int:
        # Confirmed and briefly coasting tracks have repeated scan evidence.
        # Tentative one-sweep tracks remain eligible for early acquisition but
        # must not displace mature tracks when transient false alarms are dense.
        return 0 if track.track_state in {"confirmed", "coasting"} else 1

    # The union of row-wise and column-wise top-K keeps both station views
    # symmetric when one camera has more track fragments than the other.  Each
    # side spends its bounded budget on mature tracks first, then orders them
    # by the covariance-normalized epipolar residual.
    row_selected_indices: set[tuple[int, int]] = set()
    for left_index in range(len(left_tracks)):
        right_indices = np.flatnonzero(eligible[left_index]).tolist()
        order = sorted(
            right_indices,
            key=lambda right_index: (
                maturity_rank(right_tracks[right_index]),
                float(normalized[left_index, right_index]),
                right_tracks[right_index].track_id,
            ),
        )
        row_selected_indices.update(
            (left_index, int(right_index)) for right_index in order[:top_k]
        )
    column_selected_indices: set[tuple[int, int]] = set()
    for right_index in range(len(right_tracks)):
        left_indices = np.flatnonzero(eligible[:, right_index]).tolist()
        order = sorted(
            left_indices,
            key=lambda left_index: (
                maturity_rank(left_tracks[left_index]),
                float(normalized[left_index, right_index]),
                left_tracks[left_index].track_id,
            ),
        )
        column_selected_indices.update(
            (int(left_index), right_index) for left_index in order[:top_k]
        )
    selected_indices = row_selected_indices | column_selected_indices
    for left_index, right_index in selected_indices:
        scored[
            (left_tracks[left_index].track_id, right_tracks[right_index].track_id)
        ] = float(normalized[left_index, right_index])
    rejected = int(evaluated - np.count_nonzero(eligible))
    pairs = tuple(sorted(scored))
    summary: dict[str, int | float | str] = {
        "builder_version": SHARED_CANDIDATE_GRAPH_VERSION,
        "left_track_count": len(left_tracks),
        "right_track_count": len(right_tracks),
        "full_pair_count": len(left_tracks) * len(right_tracks),
        "evaluated_pair_count": evaluated,
        "normalized_gate_rejected_count": rejected,
        "retained_pair_count": len(pairs),
        "top_k_per_track": top_k,
        "normalized_gate_sigma": gate_sigma,
        "ranking_policy": "mature_track_then_normalized_epipolar_residual",
    }
    if candidate_gate_policy is not None:
        left_with_candidates = {left_index for left_index, _ in selected_indices}
        right_with_candidates = {right_index for _, right_index in selected_indices}
        summary.update(
            {
                "candidate_gate_strategy": candidate_gate_policy.strategy_name,
                "candidate_gate_config_version": candidate_gate_policy.config_version,
                "candidate_gate_config_fingerprint": candidate_gate_policy.fingerprint,
                "candidate_gate_top_k_policy": candidate_gate_policy.top_k_policy_text,
                "eligible_pair_count": int(np.count_nonzero(eligible)),
                "row_selected_pair_count": len(row_selected_indices),
                "column_selected_pair_count": len(column_selected_indices),
                "left_tracks_with_candidate_count": len(left_with_candidates),
                "right_tracks_with_candidate_count": len(right_with_candidates),
                "isolated_left_track_count": len(left_tracks) - len(left_with_candidates),
                "isolated_right_track_count": len(right_tracks) - len(right_with_candidates),
            }
        )
    fingerprint = candidate_graph_fingerprint(pairs, summary)
    summary["candidate_build_ms"] = (
        time.perf_counter() - started
    ) * 1000.0
    return pairs, summary, fingerprint


def materialize_episode(
    episode_dir: str | Path,
    dataset_root: str | Path,
    protocol: BenchmarkProtocol | None = None,
    *,
    tracker_config: SharedTrackerConfig | None = None,
) -> list[dict[str, Any]]:
    """Materialize all corruption levels and cumulative revolution snapshots."""

    protocol = protocol or BenchmarkProtocol()
    tracker_config = tracker_config or SharedTrackerConfig(
        nominal_sweep_period_s=protocol.association_round_period_s
    )
    episode_dir = Path(episode_dir).resolve()
    dataset_root = Path(dataset_root).resolve()
    validation = validate_raw_episode(episode_dir, protocol)
    seed = int(validation["seed"])
    split = str(validation["split"])
    scenario, raw, scan_rows, raw_truth = _load_raw_episode(episode_dir)
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
    camera_positions = {
        camera_ids[0]: tuple(float(value) for value in config["camera_a_position_ned"]),
        camera_ids[1]: tuple(float(value) for value in config["camera_b_position_ned"]),
    }
    states = _camera_states(scan_rows)
    for key, state in list(states.items()):
        states[key] = CameraState(
            camera_id=state.camera_id,
            frame_index=state.frame_index,
            timestamp=state.timestamp,
            position_ned=camera_positions[state.camera_id],
            yaw_deg=state.yaw_deg,
            pitch_deg=state.pitch_deg,
        )
    entries: list[dict[str, Any]] = []
    for level in protocol.corruption_levels:
        policy = CORRUPTION_POLICY[level]
        kept: list[AnonymousDetection] = []
        uid_truth: dict[str, str] = {}
        dropped_timestamps: list[float] = []
        for item in raw:
            if _should_drop(seed, level, item.detection_uid, float(policy["miss_probability"])):
                dropped_timestamps.append(item.measurement_timestamp)
                continue
            detection = AnonymousDetection(**asdict(item))
            kept.append(detection)
            if item.detection_uid in raw_truth:
                uid_truth[item.detection_uid] = raw_truth[item.detection_uid]
        specs = _false_track_specs(protocol, seed, level, camera_ids, states)
        false_detections: list[AnonymousDetection] = []
        for detection, false_id in _false_detections(
            specs, states, camera, sample_rate_hz=protocol.sample_rate_hz
        ):
            kept.append(detection)
            false_detections.append(detection)
            uid_truth[detection.detection_uid] = false_id
        by_frame: dict[tuple[int, str], list[AnonymousDetection]] = defaultdict(list)
        confidence_by_uid = {
            detection.detection_uid: detection.confidence for detection in kept
        }
        for detection in kept:
            by_frame[(detection.frame_index, detection.camera_id)].append(detection)
        trackers = {
            camera_id: SharedBearingTracker(camera_id, tracker_config)
            for camera_id in camera_ids
        }
        observations_by_sweep: dict[
            tuple[str, int], list[Any]
        ] = defaultdict(list)
        written_revolutions: set[int] = set()
        frame_count = int(round(protocol.duration_s * protocol.sample_rate_hz))
        frames_per_revolution = int(
            round(protocol.association_round_period_s * protocol.sample_rate_hz)
        )
        for frame_index in range(frame_count):
            timestamp = frame_index / protocol.sample_rate_hz
            for camera_id in camera_ids:
                state = states.get((camera_id, frame_index))
                if state is None:
                    continue
                observations = [
                    ray_observation_from_detection(
                        detection,
                        state,
                        camera,
                        scan_period_s=protocol.scan_period_s,
                        scan_mode=protocol.scan_mode,
                    )
                    for detection in by_frame.get((frame_index, camera_id), ())
                ]
                global_sweep = min(
                    sweep_index(
                        timestamp,
                        period_s=protocol.scan_period_s,
                        mode=protocol.scan_mode,
                    ),
                    protocol.revolution_count - 1,
                )
                observations_by_sweep[(camera_id, global_sweep)].extend(observations)
            if (frame_index + 1) % frames_per_revolution == 0:
                revolution = (frame_index + 1) // frames_per_revolution
                completed_sweep = revolution - 1
                for camera_id, tracker in trackers.items():
                    tracker.update_sweep(
                        completed_sweep,
                        observations_by_sweep.get((camera_id, completed_sweep), ()),
                        confidence_by_uid,
                    )
                cutoff = float(
                    revolution * protocol.association_round_period_s
                )
                prefix_detections = [
                    {
                        "detection_uid": item.detection_uid,
                        "camera_id": item.camera_id,
                        "frame_index": item.frame_index,
                        "measurement_timestamp": item.measurement_timestamp,
                        "arrival_timestamp": item.arrival_timestamp,
                        "bbox_xyxy": item.bbox_xyxy,
                        "center_px": item.center_px,
                        "confidence": item.confidence,
                    }
                    for item in kept
                    if item.measurement_timestamp < cutoff - 1e-9
                ]
                prefix_scan = [
                    dict(row)
                    for row in scan_rows
                    if float(row["measurement_timestamp"]) < cutoff - 1e-9
                ]
                dropped_prefix = sum(
                    timestamp < cutoff - 1e-9 for timestamp in dropped_timestamps
                )
                retained_real_prefix = sum(
                    item.measurement_timestamp < cutoff - 1e-9 for item in raw
                ) - dropped_prefix
                false_prefix = sum(
                    item.measurement_timestamp < cutoff - 1e-9
                    for item in false_detections
                )
                snapshot_tracks = {
                    camera_id: _snapshot_tracks(
                        trackers[camera_id], cutoff, completed_sweep
                    )
                    for camera_id in camera_ids
                }
                candidate_pairs, candidate_summary, candidate_fingerprint = (
                    build_shared_candidate_graph(
                        tracks=snapshot_tracks,
                        camera_ids=camera_ids,
                        camera_positions_ned=camera_positions,
                        cutoff_timestamp=cutoff,
                        target_count=protocol.target_count,
                    )
                )
                snapshot = RevolutionSnapshot(
                    protocol_fingerprint=protocol.fingerprint,
                    seed=seed,
                    split=split,
                    corruption_level=level,
                    revolution_index=revolution,
                    cutoff_timestamp=cutoff,
                    camera_ids=camera_ids,
                    camera_positions_ned=camera_positions,
                    focal_length_px=camera.focal_length_px,
                    tracks=snapshot_tracks,
                    target_count=protocol.target_count,
                    tracker_fingerprint=tracker_config.fingerprint,
                    geometry_candidate_pairs=candidate_pairs,
                    candidate_graph_fingerprint=candidate_fingerprint,
                    candidate_graph_summary=candidate_summary,
                    corruption_summary={
                        "miss_probability": float(policy["miss_probability"]),
                        "dropped_detection_count": dropped_prefix,
                        "retained_real_detection_count": retained_real_prefix,
                        "false_detection_count": false_prefix,
                        "transient_false_track_count": sum(
                            not spec.persistent and spec.start_s < cutoff - 1e-9
                            for spec in specs
                        ),
                        "persistent_false_track_count": sum(
                            spec.persistent and spec.start_s < cutoff - 1e-9
                            for spec in specs
                        ),
                    },
                    source_hashes={
                        "anonymous_detection_prefix_sha256": _payload_sha256(
                            prefix_detections
                        ),
                        "camera_scan_prefix_sha256": _payload_sha256(prefix_scan),
                    },
                    association_round_period_s=protocol.association_round_period_s,
                    association_round_count=protocol.association_round_count,
                )
                relative = Path("snapshots") / split / str(seed) / level / f"revolution_{revolution:02d}.json"
                snapshot_path = dataset_root / relative
                write_snapshot(snapshot_path, snapshot)
                labels: dict[str, dict[str, int]] = {}
                for camera_id in camera_ids:
                    for track in snapshot.tracks[camera_id]:
                        counts: dict[str, int] = defaultdict(int)
                        for source_track in trackers[camera_id].tracks:
                            if source_track.track_id != track.track_id:
                                continue
                            for sample in source_track.samples:
                                for uid in sample.detection_uids:
                                    if uid in uid_truth:
                                        counts[uid_truth[uid]] += 1
                        labels[track.track_id] = dict(sorted(counts.items()))
                heading_groups = {
                    str(target["truth_id"]): (
                        "heading_0_deg"
                        if math.isclose(float(target.get("heading_offset_deg") or 0.0), 0.0, abs_tol=1e-9)
                        else "heading_minus_30_deg"
                    )
                    for target in scenario["target_specs_offline_truth_only"]
                }
                label_relative = Path("labels") / split / str(seed) / level / f"revolution_{revolution:02d}.json"
                label_path = dataset_root / label_relative
                write_json(label_path, {
                    "schema_version": DATASET_SCHEMA_VERSION,
                    "offline_truth_only": True,
                    "seed": seed,
                    "corruption_level": level,
                    "revolution_index": revolution,
                    "track_truth_counts": labels,
                    "truth_heading_groups": heading_groups,
                })
                entries.append({
                    "split": split,
                    "seed": seed,
                    "corruption_level": level,
                    "revolution_index": revolution,
                    "snapshot_path": relative.as_posix(),
                    "snapshot_sha256": sha256_file(snapshot_path),
                    "input_fingerprint": snapshot_fingerprint(snapshot),
                    "label_path": label_relative.as_posix(),
                    "label_sha256": sha256_file(label_path),
                    "tracker_fingerprint": tracker_config.fingerprint,
                })
                written_revolutions.add(revolution)
        if written_revolutions != set(range(1, protocol.revolution_count + 1)):
            raise RuntimeError("episode did not materialize all revolution boundaries")
    return entries


def write_dataset_manifest(
    dataset_root: str | Path,
    entries: Sequence[Mapping[str, Any]],
    protocol: BenchmarkProtocol | None = None,
    *,
    phase: str,
    tracker_freeze: str | Path | None = None,
) -> Path:
    protocol = protocol or BenchmarkProtocol()
    if phase not in {"calibration", "test"}:
        raise ValueError("dataset phase must be calibration or test")
    normalized = sorted(
        (dict(entry) for entry in entries),
        key=lambda item: (
            ("train", "validation", "test").index(item["split"]),
            item["seed"], item["corruption_level"], item["revolution_index"],
        ),
    )
    allowed = {"train", "validation"} if phase == "calibration" else {"test"}
    if any(item["split"] not in allowed for item in normalized):
        raise ValueError("manifest phase contains a forbidden split")
    keys = {
        (
            str(item["split"]),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in normalized
    }
    if len(keys) != len(normalized):
        raise ValueError("dataset manifest contains duplicate entries")
    expected_seeds = (
        protocol.train_seeds + protocol.validation_seeds
        if phase == "calibration"
        else protocol.test_seeds
    )
    expected_keys = {
        (split_for_seed(protocol, seed), seed, level, revolution)
        for seed in expected_seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }
    if keys != expected_keys:
        missing = len(expected_keys - keys)
        unexpected = len(keys - expected_keys)
        raise ValueError(
            "dataset manifest is incomplete or out of protocol: "
            f"missing={missing}, unexpected={unexpected}"
        )
    tracker_freeze_path = (
        None if tracker_freeze is None else Path(tracker_freeze).resolve()
    )
    tracker_payload: dict[str, Any] = {}
    diagnostic_only = False
    if tracker_freeze_path is not None:
        tracker_payload, _ = load_tracker_freeze(tracker_freeze_path)
        diagnostic_only = tracker_payload.get("diagnostic_only") is True
        if diagnostic_only and (
            tracker_payload.get("formal_use_allowed") is not False
            or tracker_payload.get("promotion_allowed") is not False
            or tracker_payload.get("validation_metrics", {})
            .get("acceptance", {})
            .get("accepted")
            is not False
        ):
            raise ValueError("diagnostic tracker freeze grants formal capability")
    tracker_fingerprints = {
        str(item.get("tracker_fingerprint", "")) for item in normalized
    }
    if len(tracker_fingerprints) != 1 or "" in tracker_fingerprints:
        raise ValueError("dataset entries do not share one frozen tracker")
    payload = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "phase": phase,
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "test_access_allowed": phase == "test",
        "tracker_fingerprint": next(iter(tracker_fingerprints)),
        "tracker_freeze": None
        if tracker_freeze_path is None
        else str(tracker_freeze_path),
        "tracker_freeze_sha256": None
        if tracker_freeze_path is None
        else sha256_file(tracker_freeze_path),
        "diagnostic_only": diagnostic_only,
        "formal_use_allowed": not diagnostic_only,
        "promotion_allowed": not diagnostic_only,
        "tracker_acceptance_passed": not diagnostic_only,
        "entries": normalized,
    }
    manifest_path = Path(dataset_root) / f"{phase}_manifest.json"
    write_json(manifest_path, payload)
    return manifest_path


def load_dataset_manifest(
    path: str | Path, *, validate_offline_labels: bool = True
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") not in {
        DATASET_SCHEMA_VERSION,
        LEGACY_DATASET_SCHEMA_VERSION,
    }:
        raise ValueError("unsupported benchmark dataset manifest")
    from .contracts import benchmark_protocol_from_mapping

    protocol = benchmark_protocol_from_mapping(payload["protocol"])
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("dataset protocol fingerprint mismatch")
    if payload.get("schema_version") == DATASET_SCHEMA_VERSION:
        tracker_freeze = payload.get("tracker_freeze")
        if tracker_freeze:
            freeze_path = Path(str(tracker_freeze)).resolve()
            if sha256_file(freeze_path) != payload.get("tracker_freeze_sha256"):
                raise ValueError("shared tracker freeze hash mismatch")
            _, config = load_tracker_freeze(freeze_path)
            if config.fingerprint != payload.get("tracker_fingerprint"):
                raise ValueError("dataset and shared tracker fingerprints disagree")
            tracker_payload, _ = load_tracker_freeze(freeze_path)
            diagnostic_only = payload.get("diagnostic_only") is True
            if diagnostic_only:
                if (
                    payload.get("formal_use_allowed") is not False
                    or payload.get("promotion_allowed") is not False
                    or payload.get("tracker_acceptance_passed") is not False
                    or tracker_payload.get("diagnostic_only") is not True
                    or tracker_payload.get("formal_use_allowed") is not False
                    or tracker_payload.get("promotion_allowed") is not False
                    or tracker_payload.get("validation_metrics", {})
                    .get("acceptance", {})
                    .get("accepted")
                    is not False
                ):
                    raise ValueError("diagnostic dataset capability contract is invalid")
    root = path.parent
    for entry in payload["entries"]:
        snapshot_path = root / entry["snapshot_path"]
        if sha256_file(snapshot_path) != entry["snapshot_sha256"]:
            raise ValueError("snapshot hash mismatch")
        if payload.get("schema_version") == DATASET_SCHEMA_VERSION:
            snapshot = RevolutionSnapshot.from_online_payload(
                json.loads(snapshot_path.read_text(encoding="utf-8"))
            )
            if snapshot.tracker_fingerprint != payload.get("tracker_fingerprint"):
                raise ValueError("snapshot was built by a foreign shared tracker")
        if validate_offline_labels:
            label_path = root / entry["label_path"]
            if sha256_file(label_path) != entry["label_sha256"]:
                raise ValueError("offline label hash mismatch")
    return payload
