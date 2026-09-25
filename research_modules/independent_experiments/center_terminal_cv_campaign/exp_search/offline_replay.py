"""Deterministic offline search replay over saved AirSim actor trajectories.

The scheduler sees anonymous center cues and camera geometry only. Saved actor
identities are consumed by the observation simulator and the offline scorer,
never by resource assignment or cue closure decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from collections import Counter
import hashlib
import heapq
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from center_terminal_cv_campaign.common.contracts import SourceCueRecord


Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class OfflineSearchConfig:
    target_count: int
    resource_count: int
    position_sigma_m: float
    seed: int
    duration_s: float = 18.0
    frame_interval_s: float = 0.1
    frames_per_observation: int = 3
    platform_max_speed_mps: float = 97.0
    gimbal_max_rate_dps: float = 200.0
    image_width: int = 1920
    image_height: int = 1080
    horizontal_fov_deg: float = 19.0
    observation_standoff_m: float = 700.0
    cell_overlap_fraction: float = 0.2
    recognition_extent_px: float = 10.0
    confirmation_frames: int = 2
    local_track_gate_px: float = 180.0
    staging_north_m: float = 2100.0
    staging_east_bounds_m: tuple[float, float] = (-650.0, 650.0)
    staging_down_layers_m: tuple[float, ...] = (-90.0, -140.0, -200.0)

    def __post_init__(self) -> None:
        if self.target_count <= 0 or self.resource_count <= 0:
            raise ValueError("target_count and resource_count must be positive")
        if self.position_sigma_m <= 0.0:
            raise ValueError("position_sigma_m must be positive")
        if self.duration_s <= 0.0 or self.frame_interval_s <= 0.0:
            raise ValueError("duration and frame interval must be positive")
        if self.frames_per_observation < self.confirmation_frames:
            raise ValueError("observation frames cannot be below confirmation frames")
        if self.platform_max_speed_mps <= 0.0 or self.gimbal_max_rate_dps <= 0.0:
            raise ValueError("platform and gimbal limits must be positive")
        if not 0.0 <= self.cell_overlap_fraction < 1.0:
            raise ValueError("cell_overlap_fraction must be within [0, 1)")

    @property
    def vertical_fov_deg(self) -> float:
        half_horizontal = math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        half_vertical = half_horizontal * self.image_height / self.image_width
        return math.degrees(2.0 * math.atan(half_vertical))

    @property
    def focal_length_px(self) -> float:
        return self.image_width / (
            2.0 * math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        )

    @property
    def observation_dwell_s(self) -> float:
        return self.frames_per_observation * self.frame_interval_s


@dataclass(frozen=True)
class SavedTargetTrajectory:
    truth_target_id: str
    timestamps_s: tuple[float, ...]
    positions_ned_m: tuple[Vector3, ...]
    velocity_ned_mps: Vector3
    longest_dimension_m: float = 3.0

    def position_at(self, timestamp: float) -> Vector3:
        timestamp = float(timestamp)
        times = np.asarray(self.timestamps_s, dtype=float)
        positions = np.asarray(self.positions_ned_m, dtype=float)
        if timestamp <= times[0]:
            value = positions[0] + np.asarray(self.velocity_ned_mps) * (timestamp - times[0])
        elif timestamp >= times[-1]:
            value = positions[-1] + np.asarray(self.velocity_ned_mps) * (timestamp - times[-1])
        else:
            value = np.asarray(
                [np.interp(timestamp, times, positions[:, axis]) for axis in range(3)],
                dtype=float,
            )
        return tuple(float(component) for component in value)


@dataclass(frozen=True)
class TrajectoryEvidence:
    source_path: str
    sha256: str
    row_count: int
    recorded_start_s: float
    recorded_end_s: float
    extrapolated_after_s: float
    trajectories: tuple[SavedTargetTrajectory, ...] = field(repr=False)


@dataclass(frozen=True)
class OfflineCueLabel:
    source_track_id: str
    truth_target_id: str
    injected_error_ned_m: Vector3


@dataclass(frozen=True)
class SearchSubcell:
    search_cell_id: str
    source_track_id: str
    probability_mass: float
    lateral_offset_m: float
    vertical_offset_m: float
    forward_ned: Vector3
    right_ned: Vector3
    nominal_width_m: float
    nominal_height_m: float
    depth_half_extent_m: float


@dataclass
class ResourceState:
    camera_id: str
    position_ned_m: Vector3
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    available_time_s: float = 0.0


@dataclass(frozen=True)
class CandidateMotion:
    observation_start_s: float
    completion_time_s: float
    observation_position_ned_m: Vector3
    yaw_deg: float
    pitch_deg: float
    travel_distance_m: float
    travel_time_s: float
    slew_time_s: float


@dataclass(frozen=True)
class AssignmentEvent:
    assignment_id: str
    plan_version: int
    assignment_timestamp_s: float
    camera_id: str
    search_cell_id: str
    source_track_id: str
    probability_mass: float
    utility: float
    motion: CandidateMotion

    def to_online_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnonymousDetection:
    detection_uid: str
    camera_id: str
    search_cell_id: str
    frame_index: int
    measurement_timestamp: float
    bbox_xyxy: tuple[float, float, float, float]
    center_px: tuple[float, float]
    recognition_extent_px: float


@dataclass(frozen=True)
class DetectionTruthLabel:
    detection_uid: str
    truth_target_id: str


@dataclass(frozen=True)
class ObservationOutcome:
    assignment_id: str
    camera_id: str
    search_cell_id: str
    source_track_id: str
    observation_start_s: float
    completion_time_s: float
    covered_cell_ids: tuple[str, ...]
    anonymous_detection_count: int
    confirmed_local_track_ids: tuple[str, ...]
    cue_closed: bool


@dataclass(frozen=True)
class OfflineSearchResult:
    config: OfflineSearchConfig
    trajectory_evidence: TrajectoryEvidence
    source_cues: tuple[SourceCueRecord, ...]
    cue_labels: tuple[OfflineCueLabel, ...]
    cells: tuple[SearchSubcell, ...]
    assignments: tuple[AssignmentEvent, ...]
    observations: tuple[ObservationOutcome, ...]
    online_detections: tuple[AnonymousDetection, ...]
    detection_truth_labels: tuple[DetectionTruthLabel, ...]
    cell_status: Mapping[str, str]
    metrics: Mapping[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_saved_actor_trajectories(
    path: Path,
    *,
    expected_target_count: int,
    extrapolate_until_s: float,
) -> TrajectoryEvidence:
    path = Path(path)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not row.get("offline_truth_only", False):
            raise ValueError(f"actor motion row is not marked offline truth: {path}")
        grouped.setdefault(str(row["truth_target_id"]), []).append(row)
    if len(grouped) != expected_target_count:
        raise ValueError(
            f"expected {expected_target_count} saved targets, found {len(grouped)} in {path}"
        )
    trajectories: list[SavedTargetTrajectory] = []
    for target_id, target_rows in sorted(grouped.items()):
        ordered = sorted(target_rows, key=lambda value: float(value["measurement_timestamp"]))
        timestamps = tuple(float(value["measurement_timestamp"]) for value in ordered)
        if len(set(timestamps)) != len(timestamps):
            raise ValueError(f"duplicate actor timestamps for {target_id}")
        trajectories.append(
            SavedTargetTrajectory(
                truth_target_id=target_id,
                timestamps_s=timestamps,
                positions_ned_m=tuple(
                    tuple(float(component) for component in value["position_ned_m"])
                    for value in ordered
                ),
                velocity_ned_mps=tuple(
                    float(component) for component in ordered[-1]["velocity_ned_mps"]
                ),
            )
        )
    start = min(item.timestamps_s[0] for item in trajectories)
    end = max(item.timestamps_s[-1] for item in trajectories)
    return TrajectoryEvidence(
        source_path=str(path.resolve()),
        sha256=_sha256(path),
        row_count=len(rows),
        recorded_start_s=float(start),
        recorded_end_s=float(end),
        extrapolated_after_s=max(0.0, float(extrapolate_until_s) - float(end)),
        trajectories=tuple(trajectories),
    )


def _diagonal_covariance(position_sigma_m: float) -> tuple[tuple[float, ...], ...]:
    diagonal = (position_sigma_m**2,) * 3 + (0.2**2,) * 3
    return tuple(
        tuple(float(diagonal[row]) if row == column else 0.0 for column in range(6))
        for row in range(6)
    )


def _truncated_normal_3d(rng: np.random.Generator, sigma: float) -> Vector3:
    values: list[float] = []
    while len(values) < 3:
        candidate = float(rng.normal(0.0, sigma))
        if abs(candidate) <= 3.0 * sigma:
            values.append(candidate)
    return tuple(values)  # type: ignore[return-value]


def build_anonymous_perfect_cues(
    evidence: TrajectoryEvidence,
    config: OfflineSearchConfig,
) -> tuple[tuple[SourceCueRecord, ...], tuple[OfflineCueLabel, ...]]:
    """Create one correct anonymous cue per target with seeded position error."""

    rng = np.random.default_rng(config.seed)
    order = rng.permutation(len(evidence.trajectories))
    covariance = _diagonal_covariance(config.position_sigma_m)
    cues: list[SourceCueRecord] = []
    labels: list[OfflineCueLabel] = []
    for sequence, trajectory_index in enumerate(order, start=1):
        trajectory = evidence.trajectories[int(trajectory_index)]
        error = _truncated_normal_3d(rng, config.position_sigma_m)
        position = tuple(
            float(value + offset)
            for value, offset in zip(trajectory.position_at(0.0), error, strict=True)
        )
        source_track_id = f"SRC-{sequence:03d}"
        cues.append(
            SourceCueRecord(
                source_track_id=source_track_id,
                position_ned_m=position,
                velocity_ned_mps=trajectory.velocity_ned_mps,
                covariance_6x6=covariance,  # type: ignore[arg-type]
                measurement_timestamp=0.0,
                arrival_timestamp=0.1,
                valid_until=config.duration_s,
                existence_probability=1.0,
                source_kind="saved_airsim_trajectory_coarse_cue",
                metadata={
                    "position_sigma_m": config.position_sigma_m,
                    "error_truncation_sigma": 3.0,
                },
            )
        )
        labels.append(
            OfflineCueLabel(
                source_track_id=source_track_id,
                truth_target_id=trajectory.truth_target_id,
                injected_error_ned_m=error,
            )
        )
    return tuple(cues), tuple(labels)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _axis_bins(span_half: float, nominal_step: float) -> tuple[tuple[float, float, float], ...]:
    count = max(1, int(math.ceil((2.0 * span_half) / nominal_step)))
    edges = np.linspace(-span_half, span_half, count + 1)
    return tuple(
        (float(edges[index]), float(edges[index + 1]), float(0.5 * (edges[index] + edges[index + 1])))
        for index in range(count)
    )


def _horizontal_basis(position_ned_m: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    horizontal = np.asarray((position_ned_m[0], position_ned_m[1], 0.0), dtype=float)
    norm = float(np.linalg.norm(horizontal))
    forward = horizontal / norm if norm > 1.0e-9 else np.asarray((1.0, 0.0, 0.0))
    right = np.asarray((-forward[1], forward[0], 0.0), dtype=float)
    return forward, right


def build_probability_subcells(
    cues: Sequence[SourceCueRecord],
    config: OfflineSearchConfig,
) -> tuple[SearchSubcell, ...]:
    """Tile each 3-sigma cue region in camera cross-range coordinates."""

    horizontal_footprint = 2.0 * config.observation_standoff_m * math.tan(
        math.radians(config.horizontal_fov_deg) * 0.5
    )
    vertical_footprint = 2.0 * config.observation_standoff_m * math.tan(
        math.radians(config.vertical_fov_deg) * 0.5
    )
    horizontal_step = horizontal_footprint * (1.0 - config.cell_overlap_fraction)
    vertical_step = vertical_footprint * (1.0 - config.cell_overlap_fraction)
    half_span = 3.0 * config.position_sigma_m
    lateral_bins = _axis_bins(half_span, horizontal_step)
    vertical_bins = _axis_bins(half_span, vertical_step)
    cells: list[SearchSubcell] = []
    for cue in cues:
        forward, right = _horizontal_basis(cue.position_ned_m)
        masses: list[tuple[tuple[float, float, float], tuple[float, float, float], float]] = []
        for lateral in lateral_bins:
            lateral_mass = _normal_cdf(lateral[1] / config.position_sigma_m) - _normal_cdf(
                lateral[0] / config.position_sigma_m
            )
            for vertical in vertical_bins:
                vertical_mass = _normal_cdf(vertical[1] / config.position_sigma_m) - _normal_cdf(
                    vertical[0] / config.position_sigma_m
                )
                masses.append((lateral, vertical, lateral_mass * vertical_mass))
        normalization = sum(value[2] for value in masses)
        for index, (lateral, vertical, mass) in enumerate(masses, start=1):
            cells.append(
                SearchSubcell(
                    search_cell_id=f"CELL-{cue.source_track_id}-{index:03d}",
                    source_track_id=cue.source_track_id,
                    probability_mass=float(mass / normalization),
                    lateral_offset_m=lateral[2],
                    vertical_offset_m=vertical[2],
                    forward_ned=tuple(float(value) for value in forward),
                    right_ned=tuple(float(value) for value in right),
                    nominal_width_m=float(horizontal_footprint),
                    nominal_height_m=float(vertical_footprint),
                    depth_half_extent_m=half_span,
                )
            )
    return tuple(cells)


def initial_forward_staging_resources(config: OfflineSearchConfig) -> tuple[ResourceState, ...]:
    east_positions = np.linspace(
        config.staging_east_bounds_m[0],
        config.staging_east_bounds_m[1],
        config.resource_count,
    )
    return tuple(
        ResourceState(
            camera_id=f"Terminal_CV_{index + 1:02d}",
            position_ned_m=(
                config.staging_north_m,
                float(east_positions[index]),
                config.staging_down_layers_m[index % len(config.staging_down_layers_m)],
            ),
        )
        for index in range(config.resource_count)
    )


def _wrap_angle_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _look_angles_deg(origin: Sequence[float], target: Sequence[float]) -> tuple[float, float]:
    delta = np.asarray(target, dtype=float) - np.asarray(origin, dtype=float)
    horizontal = float(np.hypot(delta[0], delta[1]))
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    pitch = math.degrees(math.atan2(float(delta[2]), max(horizontal, 1.0e-9)))
    return float(yaw), float(pitch)


def _cue_position(cue: SourceCueRecord, timestamp: float) -> np.ndarray:
    elapsed = max(0.0, float(timestamp) - float(cue.measurement_timestamp))
    return np.asarray(cue.position_ned_m, dtype=float) + np.asarray(
        cue.velocity_ned_mps, dtype=float
    ) * elapsed


def cell_center_at(
    cell: SearchSubcell,
    cue: SourceCueRecord,
    timestamp: float,
) -> Vector3:
    center = (
        _cue_position(cue, timestamp)
        + np.asarray(cell.right_ned) * cell.lateral_offset_m
        + np.asarray((0.0, 0.0, 1.0)) * cell.vertical_offset_m
    )
    return tuple(float(value) for value in center)


def _candidate_motion(
    resource: ResourceState,
    cell: SearchSubcell,
    cue: SourceCueRecord,
    config: OfflineSearchConfig,
    timestamp: float,
) -> CandidateMotion:
    observation_start = float(timestamp)
    position = np.asarray(resource.position_ned_m, dtype=float)
    forward = np.asarray(cell.forward_ned, dtype=float)
    desired_position = position.copy()
    yaw = resource.yaw_deg
    pitch = resource.pitch_deg
    travel_distance = 0.0
    travel_time = 0.0
    slew_time = 0.0
    for _ in range(4):
        look_time = observation_start + 0.5 * config.observation_dwell_s
        look_at = np.asarray(cell_center_at(cell, cue, look_time), dtype=float)
        desired_position = look_at - forward * config.observation_standoff_m
        yaw, pitch = _look_angles_deg(desired_position, look_at)
        travel_distance = float(np.linalg.norm(desired_position - position))
        travel_time = travel_distance / config.platform_max_speed_mps
        slew_time = max(
            abs(_wrap_angle_deg(yaw - resource.yaw_deg)),
            abs(pitch - resource.pitch_deg),
        ) / config.gimbal_max_rate_dps
        observation_start = float(timestamp) + max(travel_time, slew_time)
    completion = observation_start + config.observation_dwell_s
    return CandidateMotion(
        observation_start_s=float(observation_start),
        completion_time_s=float(completion),
        observation_position_ned_m=tuple(float(value) for value in desired_position),
        yaw_deg=float(yaw),
        pitch_deg=float(pitch),
        travel_distance_m=float(travel_distance),
        travel_time_s=float(travel_time),
        slew_time_s=float(slew_time),
    )


def _camera_basis(yaw_deg: float, pitch_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    forward = np.asarray(
        (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)),
        dtype=float,
    )
    right = np.asarray((-math.sin(yaw), math.cos(yaw), 0.0), dtype=float)
    down = np.cross(forward, right)
    return forward, right, down


def _project_target(
    trajectory: SavedTargetTrajectory,
    *,
    timestamp: float,
    camera_position_ned_m: Vector3,
    yaw_deg: float,
    pitch_deg: float,
    config: OfflineSearchConfig,
) -> tuple[float, float, float, float] | None:
    point = np.asarray(trajectory.position_at(timestamp), dtype=float)
    origin = np.asarray(camera_position_ned_m, dtype=float)
    forward, right, down = _camera_basis(yaw_deg, pitch_deg)
    delta = point - origin
    depth = float(np.dot(delta, forward))
    if depth <= 1.0:
        return None
    horizontal = float(np.dot(delta, right))
    vertical = float(np.dot(delta, down))
    if abs(horizontal / depth) > math.tan(math.radians(config.horizontal_fov_deg) * 0.5):
        return None
    if abs(vertical / depth) > math.tan(math.radians(config.vertical_fov_deg) * 0.5):
        return None
    focal = config.focal_length_px
    center_x = config.image_width * 0.5 + focal * horizontal / depth
    center_y = config.image_height * 0.5 + focal * vertical / depth
    extent = focal * trajectory.longest_dimension_m / depth
    if extent < config.recognition_extent_px:
        return None
    return (
        max(0.0, center_x - 0.5 * extent),
        max(0.0, center_y - 0.35 * extent),
        min(float(config.image_width), center_x + 0.5 * extent),
        min(float(config.image_height), center_y + 0.35 * extent),
    )


def _point_in_camera(
    point_ned_m: Sequence[float],
    *,
    camera_position_ned_m: Vector3,
    yaw_deg: float,
    pitch_deg: float,
    config: OfflineSearchConfig,
) -> bool:
    forward, right, down = _camera_basis(yaw_deg, pitch_deg)
    delta = np.asarray(point_ned_m, dtype=float) - np.asarray(camera_position_ned_m, dtype=float)
    depth = float(np.dot(delta, forward))
    if depth <= 1.0:
        return False
    return (
        abs(float(np.dot(delta, right)) / depth)
        <= math.tan(math.radians(config.horizontal_fov_deg) * 0.5)
        and abs(float(np.dot(delta, down)) / depth)
        <= math.tan(math.radians(config.vertical_fov_deg) * 0.5)
    )


@dataclass
class _LocalTrack:
    local_track_id: str
    center_px: tuple[float, float]
    last_frame_index: int
    streak: int = 1
    confirmed: bool = False
    detection_uids: list[str] = field(default_factory=list)


def _track_observation_frames(
    frame_detections: Sequence[Sequence[AnonymousDetection]],
    config: OfflineSearchConfig,
    *,
    track_prefix: str,
) -> tuple[tuple[str, ...], Mapping[str, tuple[str, ...]]]:
    states: list[_LocalTrack] = []
    sequence = 0
    for frame_index, detections in enumerate(frame_detections):
        recent = [state for state in states if frame_index - state.last_frame_index <= 1]
        matches: dict[int, _LocalTrack] = {}
        if detections and recent:
            costs = np.full((len(detections), len(recent)), 1.0e9, dtype=float)
            for row, detection in enumerate(detections):
                for column, state in enumerate(recent):
                    distance = float(
                        np.linalg.norm(np.asarray(detection.center_px) - np.asarray(state.center_px))
                    )
                    if distance <= config.local_track_gate_px:
                        costs[row, column] = distance
            rows, columns = linear_sum_assignment(costs)
            for row, column in zip(rows, columns, strict=True):
                if costs[row, column] < 1.0e8:
                    matches[int(row)] = recent[int(column)]
        for index, detection in enumerate(detections):
            state = matches.get(index)
            if state is None:
                sequence += 1
                state = _LocalTrack(
                    local_track_id=f"{track_prefix}-{sequence:03d}",
                    center_px=detection.center_px,
                    last_frame_index=frame_index,
                )
                states.append(state)
            else:
                state.streak = state.streak + 1 if state.last_frame_index == frame_index - 1 else 1
                state.center_px = detection.center_px
                state.last_frame_index = frame_index
            state.detection_uids.append(detection.detection_uid)
            if state.streak >= config.confirmation_frames:
                state.confirmed = True
    confirmed = tuple(state.local_track_id for state in states if state.confirmed)
    memberships = {
        state.local_track_id: tuple(state.detection_uids)
        for state in states
        if state.confirmed
    }
    return confirmed, memberships


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: Iterable[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            value = asdict(row) if hasattr(row, "__dataclass_fields__") else row
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    return path


def run_offline_search(
    *,
    trajectory_path: Path,
    config: OfflineSearchConfig,
) -> OfflineSearchResult:
    evidence = load_saved_actor_trajectories(
        trajectory_path,
        expected_target_count=config.target_count,
        extrapolate_until_s=config.duration_s,
    )
    cues, cue_labels = build_anonymous_perfect_cues(evidence, config)
    cells = build_probability_subcells(cues, config)
    cue_by_id = {cue.source_track_id: cue for cue in cues}
    cue_label_by_id = {label.source_track_id: label for label in cue_labels}
    trajectories = {item.truth_target_id: item for item in evidence.trajectories}
    cells_by_cue: dict[str, list[SearchSubcell]] = {}
    for cell in cells:
        cells_by_cue.setdefault(cell.source_track_id, []).append(cell)

    resources = {item.camera_id: item for item in initial_forward_staging_resources(config)}
    reserved_cells: set[str] = set()
    observed_cells: set[str] = set()
    covered_probability_cells: set[str] = set()
    closed_cues: set[str] = set()
    event_queue: list[tuple[float, int, AssignmentEvent]] = []
    assignments: list[AssignmentEvent] = []
    outcomes: list[ObservationOutcome] = []
    online_detections: list[AnonymousDetection] = []
    detection_labels: list[DetectionTruthLabel] = []
    plan_compute_s: list[float] = []
    first_detection_by_truth: dict[str, float] = {}
    first_confirmation_by_truth: dict[str, float] = {}
    detected_truth: set[str] = set()
    confirmed_truth: set[str] = set()
    target_observation_events: list[str] = []
    cue_confirmation_truth: dict[str, set[str]] = {}
    plan_version = 0
    assignment_sequence = 0
    detection_sequence = 0
    deadline_candidate_rejections = 0
    current_time = 0.0

    while current_time <= config.duration_s + 1.0e-9:
        free_resources = [
            resource
            for resource in resources.values()
            if resource.available_time_s <= current_time + 1.0e-9
        ]
        active_cells = [
            cell
            for cell in cells
            if cell.search_cell_id not in observed_cells
            and cell.search_cell_id not in reserved_cells
            and cell.source_track_id not in closed_cues
        ]
        if free_resources and active_cells:
            started = time.perf_counter()
            utility = np.full(
                (len(free_resources), len(active_cells) + len(free_resources)),
                -1.0e9,
                dtype=float,
            )
            candidates: dict[tuple[int, int], CandidateMotion] = {}
            for row, resource in enumerate(free_resources):
                for column, cell in enumerate(active_cells):
                    motion = _candidate_motion(
                        resource,
                        cell,
                        cue_by_id[cell.source_track_id],
                        config,
                        current_time,
                    )
                    if motion.completion_time_s > config.duration_s + 1.0e-9:
                        deadline_candidate_rejections += 1
                        continue
                    duration = motion.completion_time_s - current_time
                    score = (
                        12.0 * cell.probability_mass
                        + 1.5 / (1.0 + duration)
                        - 0.018 * duration
                        - 0.00005 * motion.travel_distance_m
                    )
                    utility[row, column] = score
                    candidates[(row, column)] = motion
                utility[row, len(active_cells) :] = -0.75
            rows, columns = linear_sum_assignment(-utility)
            plan_version += 1
            planned_any = False
            for row, column in zip(rows, columns, strict=True):
                if int(column) >= len(active_cells) or utility[row, column] <= -0.75:
                    continue
                resource = free_resources[int(row)]
                cell = active_cells[int(column)]
                if cell.search_cell_id in reserved_cells:
                    continue
                assignment_sequence += 1
                motion = candidates[(int(row), int(column))]
                event = AssignmentEvent(
                    assignment_id=f"ASN-{assignment_sequence:06d}",
                    plan_version=plan_version,
                    assignment_timestamp_s=float(current_time),
                    camera_id=resource.camera_id,
                    search_cell_id=cell.search_cell_id,
                    source_track_id=cell.source_track_id,
                    probability_mass=cell.probability_mass,
                    utility=float(utility[row, column]),
                    motion=motion,
                )
                assignments.append(event)
                reserved_cells.add(cell.search_cell_id)
                resource.available_time_s = motion.completion_time_s
                heapq.heappush(
                    event_queue,
                    (motion.completion_time_s, assignment_sequence, event),
                )
                planned_any = True
            plan_compute_s.append(time.perf_counter() - started)
            if planned_any:
                pass

        if not event_queue:
            break
        next_time = event_queue[0][0]
        current_time = float(next_time)
        completed: list[AssignmentEvent] = []
        while event_queue and event_queue[0][0] <= current_time + 1.0e-9:
            _, _, event = heapq.heappop(event_queue)
            completed.append(event)

        for event in completed:
            resource = resources[event.camera_id]
            resource.position_ned_m = event.motion.observation_position_ned_m
            resource.yaw_deg = event.motion.yaw_deg
            resource.pitch_deg = event.motion.pitch_deg
            resource.available_time_s = event.motion.completion_time_s
            cell = next(item for item in cells if item.search_cell_id == event.search_cell_id)
            cue = cue_by_id[cell.source_track_id]
            frame_rows: list[tuple[AnonymousDetection, ...]] = []
            frame_truth: list[tuple[DetectionTruthLabel, ...]] = []
            for local_frame in range(config.frames_per_observation):
                timestamp = event.motion.observation_start_s + local_frame * config.frame_interval_s
                look_at = cell_center_at(cell, cue, timestamp)
                yaw, pitch = _look_angles_deg(event.motion.observation_position_ned_m, look_at)
                detections: list[AnonymousDetection] = []
                labels: list[DetectionTruthLabel] = []
                for trajectory in evidence.trajectories:
                    bbox = _project_target(
                        trajectory,
                        timestamp=timestamp,
                        camera_position_ned_m=event.motion.observation_position_ned_m,
                        yaw_deg=yaw,
                        pitch_deg=pitch,
                        config=config,
                    )
                    if bbox is None:
                        continue
                    detection_sequence += 1
                    detection_uid = f"OBS-{detection_sequence:08d}"
                    detections.append(
                        AnonymousDetection(
                            detection_uid=detection_uid,
                            camera_id=event.camera_id,
                            search_cell_id=event.search_cell_id,
                            frame_index=local_frame,
                            measurement_timestamp=float(timestamp),
                            bbox_xyxy=bbox,
                            center_px=(0.5 * (bbox[0] + bbox[2]), 0.5 * (bbox[1] + bbox[3])),
                            recognition_extent_px=max(bbox[2] - bbox[0], bbox[3] - bbox[1]),
                        )
                    )
                    labels.append(
                        DetectionTruthLabel(
                            detection_uid=detection_uid,
                            truth_target_id=trajectory.truth_target_id,
                        )
                    )
                    detected_truth.add(trajectory.truth_target_id)
                    first_detection_by_truth[trajectory.truth_target_id] = min(
                        first_detection_by_truth.get(trajectory.truth_target_id, math.inf),
                        timestamp,
                    )
                frame_rows.append(tuple(detections))
                frame_truth.append(tuple(labels))
                online_detections.extend(detections)
                detection_labels.extend(labels)

            confirmed_tracks, memberships = _track_observation_frames(
                frame_rows,
                config,
                track_prefix=f"LVT-{event.camera_id}-{event.assignment_id}",
            )
            truth_by_uid = {
                label.detection_uid: label.truth_target_id
                for labels in frame_truth
                for label in labels
            }
            event_confirmed_truth: set[str] = set()
            for track_id in confirmed_tracks:
                votes = Counter(
                    truth_by_uid[uid]
                    for uid in memberships[track_id]
                    if uid in truth_by_uid
                )
                if not votes:
                    continue
                truth_id = votes.most_common(1)[0][0]
                event_confirmed_truth.add(truth_id)
                confirmed_truth.add(truth_id)
                first_confirmation_by_truth[truth_id] = min(
                    first_confirmation_by_truth.get(truth_id, math.inf),
                    event.motion.completion_time_s,
                )
            target_observation_events.extend(sorted(event_confirmed_truth))
            if confirmed_tracks:
                closed_cues.add(event.source_track_id)
                cue_confirmation_truth.setdefault(event.source_track_id, set()).update(
                    event_confirmed_truth
                )

            midpoint = event.motion.observation_start_s + 0.5 * config.observation_dwell_s
            look_at = cell_center_at(cell, cue, midpoint)
            yaw, pitch = _look_angles_deg(event.motion.observation_position_ned_m, look_at)
            covered_ids: list[str] = []
            for candidate in cells_by_cue[event.source_track_id]:
                candidate_center = cell_center_at(candidate, cue, midpoint)
                if _point_in_camera(
                    candidate_center,
                    camera_position_ned_m=event.motion.observation_position_ned_m,
                    yaw_deg=yaw,
                    pitch_deg=pitch,
                    config=config,
                ):
                    observed_cells.add(candidate.search_cell_id)
                    covered_probability_cells.add(candidate.search_cell_id)
                    covered_ids.append(candidate.search_cell_id)
            reserved_cells.discard(event.search_cell_id)
            outcomes.append(
                ObservationOutcome(
                    assignment_id=event.assignment_id,
                    camera_id=event.camera_id,
                    search_cell_id=event.search_cell_id,
                    source_track_id=event.source_track_id,
                    observation_start_s=event.motion.observation_start_s,
                    completion_time_s=event.motion.completion_time_s,
                    covered_cell_ids=tuple(sorted(covered_ids)),
                    anonymous_detection_count=sum(len(value) for value in frame_rows),
                    confirmed_local_track_ids=confirmed_tracks,
                    cue_closed=bool(confirmed_tracks),
                )
            )

    cell_status = {
        cell.search_cell_id: (
            "observed_in_true_frustum"
            if cell.search_cell_id in observed_cells
            else (
                "closed_after_visual_confirmation"
                if cell.source_track_id in closed_cues
                else "unexecuted_within_18s_budget"
            )
        )
        for cell in cells
    }
    label_truth = {label.source_track_id: label.truth_target_id for label in cue_labels}
    correctly_closed_cues = sum(
        label_truth[cue_id] in cue_confirmation_truth.get(cue_id, set())
        for cue_id in closed_cues
    )
    identity_misclosed_cues = len(closed_cues) - correctly_closed_cues
    duplicate_target_events = len(target_observation_events) - len(set(target_observation_events))
    total_probability = sum(cell.probability_mass for cell in cells)
    covered_probability = sum(
        cell.probability_mass
        for cell in cells
        if cell.search_cell_id in covered_probability_cells
    )
    online_payload = {
        "cues": [cue.to_online_dict() for cue in cues],
        "cells": [asdict(cell) for cell in cells],
        "assignments": [event.to_online_dict() for event in assignments],
        "detections": [asdict(value) for value in online_detections],
    }
    online_text = json.dumps(online_payload, ensure_ascii=False)
    forbidden = [item.truth_target_id for item in evidence.trajectories]
    leakage_count = sum(value in online_text for value in forbidden)
    first_detection_values = tuple(first_detection_by_truth.values())
    first_confirmation_values = tuple(first_confirmation_by_truth.values())
    planner_ms = np.asarray(plan_compute_s, dtype=float) * 1000.0
    metrics: dict[str, Any] = {
        "schema_version": "center-terminal-offline-search-metrics-v2",
        "data_source": "saved_airsim_actor_trajectory_offline_replay",
        "target_count": config.target_count,
        "resource_count": config.resource_count,
        "position_sigma_m": config.position_sigma_m,
        "seed": config.seed,
        "source_cue_count": len(cues),
        "source_fixture_precision": 1.0,
        "source_fixture_recall": 1.0,
        "source_ghost_count": 0,
        "source_duplicate_count": 0,
        "source_missed_target_count": 0,
        "search_cell_count": len(cells),
        "executed_observation_task_count": len(outcomes),
        "true_frustum_covered_cell_count": len(observed_cells),
        "true_frustum_cell_coverage_rate": len(observed_cells) / len(cells) if cells else 0.0,
        "true_frustum_probability_mass_coverage_rate": (
            covered_probability / total_probability if total_probability else 0.0
        ),
        "unexecuted_task_count": sum(
            status == "unexecuted_within_18s_budget" for status in cell_status.values()
        ),
        "closed_after_confirmation_cell_count": sum(
            status == "closed_after_visual_confirmation" for status in cell_status.values()
        ),
        "detected_target_count": len(detected_truth),
        "target_discovery_rate": len(detected_truth) / config.target_count,
        "continuously_confirmed_target_count": len(confirmed_truth),
        "continuous_confirmation_rate": len(confirmed_truth) / config.target_count,
        "first_discovery_mean_s": (
            float(np.mean(first_detection_values)) if first_detection_values else None
        ),
        "first_discovery_p95_s": (
            float(np.percentile(first_detection_values, 95.0)) if first_detection_values else None
        ),
        "first_confirmation_mean_s": (
            float(np.mean(first_confirmation_values)) if first_confirmation_values else None
        ),
        "repeated_confirmed_observation_count": duplicate_target_events,
        "repeated_confirmed_observation_rate": (
            duplicate_target_events / len(target_observation_events)
            if target_observation_events
            else 0.0
        ),
        "closed_cue_count": len(closed_cues),
        "correctly_closed_cue_count": correctly_closed_cues,
        "identity_misclosed_cue_count": identity_misclosed_cues,
        "deadline_candidate_rejection_count": deadline_candidate_rejections,
        "planner_call_count": len(plan_compute_s),
        "planner_compute_mean_ms": float(np.mean(planner_ms)) if planner_ms.size else 0.0,
        "planner_compute_p95_ms": (
            float(np.percentile(planner_ms, 95.0)) if planner_ms.size else 0.0
        ),
        "planner_compute_max_ms": float(np.max(planner_ms)) if planner_ms.size else 0.0,
        "online_truth_leakage_count": leakage_count,
        "camera_vertical_fov_deg": config.vertical_fov_deg,
        "camera_horizontal_footprint_m": (
            2.0
            * config.observation_standoff_m
            * math.tan(math.radians(config.horizontal_fov_deg) * 0.5)
        ),
        "camera_vertical_footprint_m": (
            2.0
            * config.observation_standoff_m
            * math.tan(math.radians(config.vertical_fov_deg) * 0.5)
        ),
        "trajectory_recorded_end_s": evidence.recorded_end_s,
        "trajectory_extrapolated_after_s": evidence.extrapolated_after_s,
        "acceptance": {
            "source_precision_recall_one": len(cues) == config.target_count,
            "no_ghost_duplicate_or_missed_cue": True,
            "ten_pixel_gate_enabled": config.recognition_extent_px == 10.0,
            "two_consecutive_frames_enabled": config.confirmation_frames == 2,
            "online_truth_leakage_zero": leakage_count == 0,
            "deadline_enforced": all(
                item.motion.completion_time_s <= config.duration_s + 1.0e-9
                for item in assignments
            ),
        },
    }
    return OfflineSearchResult(
        config=config,
        trajectory_evidence=evidence,
        source_cues=cues,
        cue_labels=cue_labels,
        cells=cells,
        assignments=tuple(assignments),
        observations=tuple(outcomes),
        online_detections=tuple(online_detections),
        detection_truth_labels=tuple(detection_labels),
        cell_status=cell_status,
        metrics=metrics,
    )


def write_offline_search_result(result: OfflineSearchResult, output_dir: Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    paths = {
        "config": _write_json(output_dir / "config.json", asdict(result.config)),
        "metrics": _write_json(output_dir / "metrics.json", dict(result.metrics)),
        "source_cues": _write_jsonl(
            output_dir / "online" / "source_cues.jsonl",
            (cue.to_online_dict() for cue in result.source_cues),
        ),
        "cells": _write_jsonl(output_dir / "online" / "search_cells.jsonl", result.cells),
        "assignments": _write_jsonl(
            output_dir / "online" / "assignments.jsonl",
            (value.to_online_dict() for value in result.assignments),
        ),
        "observations": _write_jsonl(
            output_dir / "online" / "observation_outcomes.jsonl", result.observations
        ),
        "detections": _write_jsonl(
            output_dir / "online" / "anonymous_detections.jsonl", result.online_detections
        ),
        "cue_truth": _write_jsonl(
            output_dir / "truth" / "cue_labels.jsonl", result.cue_labels
        ),
        "detection_truth": _write_jsonl(
            output_dir / "truth" / "detection_labels.jsonl",
            result.detection_truth_labels,
        ),
        "cell_status": _write_json(output_dir / "cell_status.json", dict(result.cell_status)),
        "manifest": _write_json(
            output_dir / "evidence_manifest.json",
            {
                "schema_version": "center-terminal-offline-search-evidence-v2",
                "replay_kind": "deterministic_offline_search_over_saved_airsim_trajectory",
                "trajectory_source": {
                    key: value
                    for key, value in asdict(result.trajectory_evidence).items()
                    if key != "trajectories"
                },
                "online_truth_allowed": False,
                "truth_usage": "offline_observation_generation_and_scoring_only",
                "config": asdict(result.config),
            },
        ),
    }
    return paths

