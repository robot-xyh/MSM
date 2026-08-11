"""Ideal two-stage visual registration for an anonymous multi-camera scene.

The online path intentionally receives no truth identity mapping.  Center-owned
global tracks are first registered to anonymous camera-A tracklets and are then
projected into camera B for a second anonymous registration.  Offline truth is
returned as a separate object and is consumed only by the evaluator.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, sqrt
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from research_modules.scalable_3d_simulation.camera_projection import (
    CameraIntrinsics,
    CameraPose,
    look_at_rotation_ned_to_camera,
    project_points,
)
from research_modules.scalable_3d_simulation.dynamics import integrate_point_masses
from research_modules.scalable_3d_simulation.models import KinematicLimits


IDEAL_REGISTRATION_SCHEMA_VERSION = "d5-ideal-two-stage-registration-v1"
FORBIDDEN_ONLINE_IDENTITY_TOKENS = (
    "actor_id",
    "actor_name",
    "object_id",
    "offline_truth",
    "true_global",
    "truth_id",
)


@dataclass(frozen=True)
class IdealRegistrationConfig:
    """Configuration for the deterministic point-mass registration demo."""

    target_count: int = 20
    seed: int = 20260810
    duration_s: float = 15.0
    physics_dt_s: float = 0.1
    image_period_s: float = 0.2
    target_speed_min_mps: float = 3.5
    target_speed_max_mps: float = 4.7
    formation_center_ned: tuple[float, float, float] = (1200.0, 0.0, -180.0)
    camera_a_position_ned: tuple[float, float, float] = (0.0, 0.0, -50.0)
    camera_b_position_ned: tuple[float, float, float] = (150.0, 300.0, -100.0)
    camera_b_speed_mps: float = 14.0
    camera_a_width_px: int = 3840
    camera_a_height_px: int = 2160
    camera_a_horizontal_fov_deg: float = 70.0
    camera_b_width_px: int = 1920
    camera_b_height_px: int = 1080
    camera_b_horizontal_fov_deg: float = 90.0
    temporal_window_frames: int = 5
    position_scale_px: float = 20.0
    displacement_scale_px: float = 10.0
    displacement_weight: float = 0.25
    covariance_regularization: float = 1.0e-6
    candidate_edge_count: int = 3

    def __post_init__(self) -> None:
        if self.target_count <= 0:
            raise ValueError("target_count must be positive")
        if self.duration_s <= 0.0 or self.physics_dt_s <= 0.0:
            raise ValueError("duration_s and physics_dt_s must be positive")
        if self.image_period_s < self.physics_dt_s:
            raise ValueError("image_period_s must be at least physics_dt_s")
        ratio = self.image_period_s / self.physics_dt_s
        if not np.isclose(ratio, round(ratio), atol=1.0e-10):
            raise ValueError("image_period_s must be an integer multiple of physics_dt_s")
        if self.target_speed_min_mps <= 0.0:
            raise ValueError("target_speed_min_mps must be positive")
        if self.target_speed_max_mps < self.target_speed_min_mps:
            raise ValueError("target speed range is invalid")
        if self.camera_b_speed_mps <= 0.0:
            raise ValueError("camera_b_speed_mps must be positive")
        if self.temporal_window_frames <= 0:
            raise ValueError("temporal_window_frames must be positive")
        if self.position_scale_px <= 0.0 or self.displacement_scale_px <= 0.0:
            raise ValueError("cost scales must be positive")
        if self.displacement_weight < 0.0:
            raise ValueError("displacement_weight must be non-negative")
        if self.covariance_regularization <= 0.0:
            raise ValueError("covariance_regularization must be positive")
        if self.candidate_edge_count <= 0:
            raise ValueError("candidate_edge_count must be positive")
        for width, height, fov in (
            (
                self.camera_a_width_px,
                self.camera_a_height_px,
                self.camera_a_horizontal_fov_deg,
            ),
            (
                self.camera_b_width_px,
                self.camera_b_height_px,
                self.camera_b_horizontal_fov_deg,
            ),
        ):
            if width <= 0 or height <= 0 or not 1.0 < fov < 179.0:
                raise ValueError("camera image dimensions or field of view are invalid")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = IDEAL_REGISTRATION_SCHEMA_VERSION
        payload["working_frame"] = "NED"
        payload["measurement_arrival_timestamp_policy"] = "equal_ideal_time"
        payload["online_truth_policy"] = "offline_sidecar_only"
        return payload


@dataclass(frozen=True)
class OnlineRegistrationFrame:
    """Truth-free online data available to the center-side registration path."""

    frame_index: int
    measurement_timestamp: float
    arrival_timestamp: float
    global_track_ids: tuple[str, ...]
    global_states_ned: np.ndarray
    global_covariances: np.ndarray
    camera_a_pose: CameraPose
    camera_b_pose: CameraPose
    camera_a_projected_pixels: np.ndarray
    camera_b_projected_pixels: np.ndarray
    camera_a_visible: np.ndarray
    camera_b_visible: np.ndarray
    camera_a_local_track_ids: tuple[str, ...]
    camera_b_local_track_ids: tuple[str, ...]
    camera_a_local_pixels: np.ndarray
    camera_b_local_pixels: np.ndarray
    camera_a_local_covariances: np.ndarray
    camera_b_local_covariances: np.ndarray

    def __post_init__(self) -> None:
        count = len(self.global_track_ids)
        expected_shapes = {
            "global_states_ned": (count, 6),
            "global_covariances": (count, 6, 6),
            "camera_a_projected_pixels": (count, 2),
            "camera_b_projected_pixels": (count, 2),
            "camera_a_visible": (count,),
            "camera_b_visible": (count,),
            "camera_a_local_pixels": (count, 2),
            "camera_b_local_pixels": (count, 2),
            "camera_a_local_covariances": (count, 2, 2),
            "camera_b_local_covariances": (count, 2, 2),
        }
        if len(self.camera_a_local_track_ids) != count:
            raise ValueError("camera A local track count must match global track count")
        if len(self.camera_b_local_track_ids) != count:
            raise ValueError("camera B local track count must match global track count")
        for field_name, shape in expected_shapes.items():
            if np.asarray(getattr(self, field_name)).shape != shape:
                raise ValueError(f"{field_name} must have shape {shape}")
        if not np.isclose(self.measurement_timestamp, self.arrival_timestamp):
            raise ValueError("ideal frames require equal measurement and arrival timestamps")


@dataclass(frozen=True)
class TemporalCostResult:
    """Auditable components of one complete rectangular assignment matrix."""

    position_cost: np.ndarray
    displacement_cost: np.ndarray
    total_cost: np.ndarray
    window_frame_count: int


@dataclass(frozen=True)
class FrameRegistrationResult:
    """Two-stage public association chain for one image timestamp."""

    frame_index: int
    measurement_timestamp: float
    arrival_timestamp: float
    stage_a_cost: TemporalCostResult
    stage_b_cost: TemporalCostResult
    global_to_camera_a: tuple[tuple[str, str], ...]
    global_camera_a_to_camera_b: tuple[tuple[str, str, str], ...]
    stage_a_selected_costs: tuple[float, ...]
    stage_b_selected_costs: tuple[float, ...]


@dataclass(frozen=True)
class OnlineRegistrationRun:
    """Online simulation and association results with no truth sidecar attached."""

    config: IdealRegistrationConfig
    frames: tuple[OnlineRegistrationFrame, ...]
    associations: tuple[FrameRegistrationResult, ...]
    camera_a_intrinsics: CameraIntrinsics
    camera_b_intrinsics: CameraIntrinsics
    center_global_track_ids_before: tuple[str, ...]
    center_global_track_ids_after: tuple[str, ...]
    online_truth_usage_count: int = 0

    def __post_init__(self) -> None:
        if len(self.frames) != len(self.associations):
            raise ValueError("every online frame requires one association result")
        if self.center_global_track_ids_before != self.center_global_track_ids_after:
            raise ValueError("D5 must not rewrite center-owned global_track_id values")
        if self.online_truth_usage_count != 0:
            raise ValueError("online truth use is forbidden")


@dataclass(frozen=True)
class OfflineIdentityTruth:
    """Evaluator-only mapping, deliberately separated from online frames."""

    seed: int
    global_to_camera_a: tuple[tuple[str, str], ...]
    global_to_camera_b: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SeedRegistrationMetrics:
    """Offline metrics for one seed."""

    seed: int
    target_count: int
    frame_count: int
    camera_a_accuracy: float
    camera_b_accuracy: float
    end_to_end_accuracy: float
    id_switch_count: int
    duplicate_assignment_count: int
    unmatched_count: int
    complete_chain_ratio: float
    camera_a_visibility_rate: float
    camera_b_visibility_rate: float
    full_visibility_rate: float
    online_truth_usage_count: int
    global_track_id_rewrite_count: int
    mean_stage_a_selected_cost: float
    mean_stage_b_selected_cost: float
    max_stage_a_selected_cost: float
    max_stage_b_selected_cost: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def acceptance_passed(self) -> bool:
        return bool(
            np.isclose(self.camera_a_accuracy, 1.0)
            and np.isclose(self.camera_b_accuracy, 1.0)
            and np.isclose(self.end_to_end_accuracy, 1.0)
            and self.id_switch_count == 0
            and self.duplicate_assignment_count == 0
            and self.unmatched_count == 0
            and np.isclose(self.complete_chain_ratio, 1.0)
            and self.online_truth_usage_count == 0
            and self.global_track_id_rewrite_count == 0
            and np.isclose(self.full_visibility_rate, 1.0)
        )


def build_temporal_cost_matrix(
    projected_pixel_history: Sequence[np.ndarray],
    anonymous_pixel_history: Sequence[np.ndarray],
    *,
    window_frames: int,
    position_scale_px: float,
    displacement_scale_px: float,
    displacement_weight: float,
) -> TemporalCostResult:
    """Build the requested recent-window position and displacement cost."""

    if len(projected_pixel_history) != len(anonymous_pixel_history):
        raise ValueError("projected and anonymous histories must have equal length")
    if not projected_pixel_history:
        raise ValueError("at least one frame is required")
    if window_frames <= 0:
        raise ValueError("window_frames must be positive")
    predicted = np.stack(projected_pixel_history[-window_frames:], axis=0).astype(float)
    observed = np.stack(anonymous_pixel_history[-window_frames:], axis=0).astype(float)
    if predicted.ndim != 3 or predicted.shape[2] != 2:
        raise ValueError("projected histories must contain (global_count, 2) arrays")
    if observed.ndim != 3 or observed.shape[2] != 2:
        raise ValueError("anonymous histories must contain (local_count, 2) arrays")
    pair_delta = predicted[:, :, None, :] - observed[:, None, :, :]
    position_cost = np.mean(np.sum(pair_delta**2, axis=-1), axis=0) / position_scale_px**2
    displacement_cost = np.zeros_like(position_cost)
    if predicted.shape[0] > 1:
        predicted_displacement = np.diff(predicted, axis=0)
        observed_displacement = np.diff(observed, axis=0)
        displacement_delta = (
            predicted_displacement[:, :, None, :]
            - observed_displacement[:, None, :, :]
        )
        displacement_cost = (
            np.mean(np.sum(displacement_delta**2, axis=-1), axis=0)
            / displacement_scale_px**2
        )
    total_cost = position_cost + displacement_weight * displacement_cost
    return TemporalCostResult(
        position_cost=position_cost,
        displacement_cost=displacement_cost,
        total_cost=total_cost,
        window_frame_count=int(predicted.shape[0]),
    )


def solve_complete_assignment(
    global_track_ids: Sequence[str],
    local_track_ids: Sequence[str],
    cost: TemporalCostResult,
) -> tuple[tuple[tuple[str, str], ...], tuple[float, ...]]:
    """Solve a complete assignment without creating or normalizing any IDs."""

    matrix = np.asarray(cost.total_cost, dtype=float)
    expected = (len(global_track_ids), len(local_track_ids))
    if matrix.shape != expected:
        raise ValueError(f"cost matrix must have shape {expected}")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("cost matrix must contain only finite values")
    row_indices, column_indices = linear_sum_assignment(matrix)
    pairs = tuple(
        (str(global_track_ids[row]), str(local_track_ids[column]))
        for row, column in zip(row_indices, column_indices, strict=True)
    )
    selected_costs = tuple(
        float(matrix[row, column])
        for row, column in zip(row_indices, column_indices, strict=True)
    )
    return pairs, selected_costs


def run_ideal_registration(
    config: IdealRegistrationConfig | None = None,
) -> tuple[OnlineRegistrationRun, OfflineIdentityTruth]:
    """Run one deterministic ideal episode and return online/offline partitions."""

    resolved = config or IdealRegistrationConfig()
    rng = np.random.default_rng(resolved.seed)
    global_ids = tuple(
        f"GT-{index + 1:03d}" for index in range(resolved.target_count)
    )
    camera_a_ids_by_global = _shuffled_local_ids("A", resolved.target_count, rng)
    camera_b_ids_by_global = _shuffled_local_ids("B", resolved.target_count, rng)
    camera_a_local_ids = tuple(sorted(camera_a_ids_by_global))
    camera_b_local_ids = tuple(sorted(camera_b_ids_by_global))
    camera_a_observation_order = np.array(
        [camera_a_ids_by_global.index(local_id) for local_id in camera_a_local_ids],
        dtype=int,
    )
    camera_b_observation_order = np.array(
        [camera_b_ids_by_global.index(local_id) for local_id in camera_b_local_ids],
        dtype=int,
    )

    target_state = _initial_target_states(resolved, rng)
    camera_b_state = _initial_camera_b_state(resolved)
    target_limits = KinematicLimits(
        max_speed_mps=max(6.0, resolved.target_speed_max_mps + 0.5),
        max_accel_mps2=1.0,
        max_turn_rate_radps=np.deg2rad(45.0),
        max_climb_rate_mps=2.0,
    )
    camera_b_limits = KinematicLimits(
        max_speed_mps=resolved.camera_b_speed_mps + 1.0,
        max_accel_mps2=2.0,
        max_turn_rate_radps=np.deg2rad(30.0),
        max_climb_rate_mps=4.0,
    )
    camera_a_intrinsics = CameraIntrinsics.from_horizontal_fov(
        width_px=resolved.camera_a_width_px,
        height_px=resolved.camera_a_height_px,
        horizontal_fov_deg=resolved.camera_a_horizontal_fov_deg,
    )
    camera_b_intrinsics = CameraIntrinsics.from_horizontal_fov(
        width_px=resolved.camera_b_width_px,
        height_px=resolved.camera_b_height_px,
        horizontal_fov_deg=resolved.camera_b_horizontal_fov_deg,
    )
    covariance_6d = np.eye(6, dtype=float) * resolved.covariance_regularization
    covariance_2d = np.eye(2, dtype=float) * resolved.covariance_regularization
    covariance_3d = np.eye(3, dtype=float) * resolved.covariance_regularization
    image_stride = int(round(resolved.image_period_s / resolved.physics_dt_s))
    physics_step_count = int(round(resolved.duration_s / resolved.physics_dt_s))

    frames: list[OnlineRegistrationFrame] = []
    associations: list[FrameRegistrationResult] = []
    projected_history_a: list[np.ndarray] = []
    projected_history_b: list[np.ndarray] = []
    anonymous_history_a: list[np.ndarray] = []
    anonymous_history_b: list[np.ndarray] = []

    for physics_step in range(physics_step_count + 1):
        if physics_step % image_stride == 0:
            timestamp = float(physics_step * resolved.physics_dt_s)
            target_positions = target_state[:, :3].copy()
            centroid = np.mean(target_positions, axis=0)
            camera_a_pose = CameraPose(
                position_ned=np.asarray(resolved.camera_a_position_ned, dtype=float),
                rotation_camera_from_ned=look_at_rotation_ned_to_camera(
                    np.asarray(resolved.camera_a_position_ned, dtype=float), centroid
                ),
                position_covariance_ned=np.eye(3) * resolved.covariance_regularization,
                attitude_covariance_rad2=np.eye(3) * resolved.covariance_regularization,
            )
            camera_b_pose = CameraPose(
                position_ned=camera_b_state[0, :3],
                rotation_camera_from_ned=look_at_rotation_ned_to_camera(
                    camera_b_state[0, :3], centroid
                ),
                position_covariance_ned=np.eye(3) * resolved.covariance_regularization,
                attitude_covariance_rad2=np.eye(3) * resolved.covariance_regularization,
            )
            projection_a = project_points(
                target_positions,
                camera_pose=camera_a_pose,
                intrinsics=camera_a_intrinsics,
                point_covariance_ned=covariance_3d,
                object_size_m=(2.0, 1.0),
                pixel_noise_std=0.0,
            )
            projection_b = project_points(
                target_positions,
                camera_pose=camera_b_pose,
                intrinsics=camera_b_intrinsics,
                point_covariance_ned=covariance_3d,
                object_size_m=(2.0, 1.0),
                pixel_noise_std=0.0,
            )
            if not np.all(projection_a.visible) or not np.all(projection_b.visible):
                raise RuntimeError(
                    f"all targets must remain visible in both cameras at t={timestamp:.3f}s"
                )
            anonymous_a = projection_a.pixel_centers[camera_a_observation_order].copy()
            anonymous_b = projection_b.pixel_centers[camera_b_observation_order].copy()
            projected_history_a.append(projection_a.pixel_centers.copy())
            projected_history_b.append(projection_b.pixel_centers.copy())
            anonymous_history_a.append(anonymous_a)
            anonymous_history_b.append(anonymous_b)

            stage_a_cost = build_temporal_cost_matrix(
                projected_history_a,
                anonymous_history_a,
                window_frames=resolved.temporal_window_frames,
                position_scale_px=resolved.position_scale_px,
                displacement_scale_px=resolved.displacement_scale_px,
                displacement_weight=resolved.displacement_weight,
            )
            stage_a_pairs, stage_a_selected_costs = solve_complete_assignment(
                global_ids, camera_a_local_ids, stage_a_cost
            )
            stage_a_lookup = dict(stage_a_pairs)

            # Stage B is authorized only for rows that already obtained an A-side
            # binding.  The projected rows retain center-owned global IDs.
            stage_b_cost = build_temporal_cost_matrix(
                projected_history_b,
                anonymous_history_b,
                window_frames=resolved.temporal_window_frames,
                position_scale_px=resolved.position_scale_px,
                displacement_scale_px=resolved.displacement_scale_px,
                displacement_weight=resolved.displacement_weight,
            )
            stage_b_pairs, stage_b_selected_costs = solve_complete_assignment(
                global_ids, camera_b_local_ids, stage_b_cost
            )
            stage_b_chain = tuple(
                (global_id, stage_a_lookup[global_id], camera_b_local_id)
                for global_id, camera_b_local_id in stage_b_pairs
            )
            frame_index = len(frames)
            frames.append(
                OnlineRegistrationFrame(
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp,
                    global_track_ids=global_ids,
                    global_states_ned=target_state.copy(),
                    global_covariances=np.broadcast_to(
                        covariance_6d,
                        (resolved.target_count, 6, 6),
                    ).copy(),
                    camera_a_pose=camera_a_pose,
                    camera_b_pose=camera_b_pose,
                    camera_a_projected_pixels=projection_a.pixel_centers.copy(),
                    camera_b_projected_pixels=projection_b.pixel_centers.copy(),
                    camera_a_visible=projection_a.visible.copy(),
                    camera_b_visible=projection_b.visible.copy(),
                    camera_a_local_track_ids=camera_a_local_ids,
                    camera_b_local_track_ids=camera_b_local_ids,
                    camera_a_local_pixels=anonymous_a,
                    camera_b_local_pixels=anonymous_b,
                    camera_a_local_covariances=np.broadcast_to(
                        covariance_2d,
                        (resolved.target_count, 2, 2),
                    ).copy(),
                    camera_b_local_covariances=np.broadcast_to(
                        covariance_2d,
                        (resolved.target_count, 2, 2),
                    ).copy(),
                )
            )
            associations.append(
                FrameRegistrationResult(
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp,
                    stage_a_cost=stage_a_cost,
                    stage_b_cost=stage_b_cost,
                    global_to_camera_a=stage_a_pairs,
                    global_camera_a_to_camera_b=stage_b_chain,
                    stage_a_selected_costs=stage_a_selected_costs,
                    stage_b_selected_costs=stage_b_selected_costs,
                )
            )

        if physics_step < physics_step_count:
            target_state, _ = integrate_point_masses(
                target_state,
                np.zeros((resolved.target_count, 3), dtype=float),
                dt_s=resolved.physics_dt_s,
                limits=target_limits,
            )
            camera_b_state, _ = integrate_point_masses(
                camera_b_state,
                np.zeros((1, 3), dtype=float),
                dt_s=resolved.physics_dt_s,
                limits=camera_b_limits,
            )

    online_run = OnlineRegistrationRun(
        config=resolved,
        frames=tuple(frames),
        associations=tuple(associations),
        camera_a_intrinsics=camera_a_intrinsics,
        camera_b_intrinsics=camera_b_intrinsics,
        center_global_track_ids_before=global_ids,
        center_global_track_ids_after=global_ids,
        online_truth_usage_count=0,
    )
    offline_truth = OfflineIdentityTruth(
        seed=resolved.seed,
        global_to_camera_a=tuple(zip(global_ids, camera_a_ids_by_global, strict=True)),
        global_to_camera_b=tuple(zip(global_ids, camera_b_ids_by_global, strict=True)),
    )
    assert_online_run_truth_free(online_run)
    return online_run, offline_truth


def evaluate_ideal_registration(
    online_run: OnlineRegistrationRun,
    offline_truth: OfflineIdentityTruth,
) -> SeedRegistrationMetrics:
    """Score an online run using the separately supplied evaluator sidecar."""

    if online_run.config.seed != offline_truth.seed:
        raise ValueError("online run and offline truth seed must match")
    expected_a = dict(offline_truth.global_to_camera_a)
    expected_b = dict(offline_truth.global_to_camera_b)
    target_count = online_run.config.target_count
    expected_assignment_count = len(online_run.associations) * target_count
    correct_a = 0
    correct_b = 0
    correct_chain = 0
    duplicate_count = 0
    unmatched_count = 0
    complete_count = 0
    id_switch_count = 0
    previous_a: dict[str, str] = {}
    previous_b: dict[str, str] = {}
    selected_a_costs: list[float] = []
    selected_b_costs: list[float] = []

    for frame_result in online_run.associations:
        pairs_a = dict(frame_result.global_to_camera_a)
        chain = {
            global_id: (camera_a_id, camera_b_id)
            for global_id, camera_a_id, camera_b_id in frame_result.global_camera_a_to_camera_b
        }
        duplicate_count += len(pairs_a) - len(set(pairs_a.values()))
        duplicate_count += len(chain) - len({value[1] for value in chain.values()})
        missing = set(expected_a) - set(pairs_a)
        missing.update(set(expected_b) - set(chain))
        unmatched_count += len(missing)
        for global_id in expected_a:
            camera_a_id = pairs_a.get(global_id)
            chain_value = chain.get(global_id)
            if camera_a_id == expected_a[global_id]:
                correct_a += 1
            if chain_value is not None and chain_value[1] == expected_b[global_id]:
                correct_b += 1
            if (
                chain_value is not None
                and chain_value[0] == expected_a[global_id]
                and chain_value[1] == expected_b[global_id]
            ):
                correct_chain += 1
            if camera_a_id is not None and chain_value is not None:
                complete_count += 1
            if global_id in previous_a and camera_a_id != previous_a[global_id]:
                id_switch_count += 1
            if (
                global_id in previous_b
                and chain_value is not None
                and chain_value[1] != previous_b[global_id]
            ):
                id_switch_count += 1
            if camera_a_id is not None:
                previous_a[global_id] = camera_a_id
            if chain_value is not None:
                previous_b[global_id] = chain_value[1]
        selected_a_costs.extend(frame_result.stage_a_selected_costs)
        selected_b_costs.extend(frame_result.stage_b_selected_costs)

    visible_a = sum(int(np.count_nonzero(frame.camera_a_visible)) for frame in online_run.frames)
    visible_b = sum(int(np.count_nonzero(frame.camera_b_visible)) for frame in online_run.frames)
    visibility_denominator = len(online_run.frames) * target_count
    full_visible_frames = sum(
        int(np.all(frame.camera_a_visible) and np.all(frame.camera_b_visible))
        for frame in online_run.frames
    )
    rewrite_count = sum(
        int(before != after)
        for before, after in zip(
            online_run.center_global_track_ids_before,
            online_run.center_global_track_ids_after,
            strict=True,
        )
    )
    return SeedRegistrationMetrics(
        seed=online_run.config.seed,
        target_count=target_count,
        frame_count=len(online_run.frames),
        camera_a_accuracy=_safe_ratio(correct_a, expected_assignment_count),
        camera_b_accuracy=_safe_ratio(correct_b, expected_assignment_count),
        end_to_end_accuracy=_safe_ratio(correct_chain, expected_assignment_count),
        id_switch_count=id_switch_count,
        duplicate_assignment_count=duplicate_count,
        unmatched_count=unmatched_count,
        complete_chain_ratio=_safe_ratio(complete_count, expected_assignment_count),
        camera_a_visibility_rate=_safe_ratio(visible_a, visibility_denominator),
        camera_b_visibility_rate=_safe_ratio(visible_b, visibility_denominator),
        full_visibility_rate=_safe_ratio(full_visible_frames, len(online_run.frames)),
        online_truth_usage_count=online_run.online_truth_usage_count,
        global_track_id_rewrite_count=rewrite_count,
        mean_stage_a_selected_cost=float(np.mean(selected_a_costs)),
        mean_stage_b_selected_cost=float(np.mean(selected_b_costs)),
        max_stage_a_selected_cost=float(np.max(selected_a_costs)),
        max_stage_b_selected_cost=float(np.max(selected_b_costs)),
    )


def run_seed_batch(
    seeds: Iterable[int],
    *,
    base_config: IdealRegistrationConfig | None = None,
) -> tuple[SeedRegistrationMetrics, ...]:
    """Run a bounded batch without writing artifacts."""

    template = base_config or IdealRegistrationConfig()
    results: list[SeedRegistrationMetrics] = []
    for seed in seeds:
        config_payload = asdict(template)
        config_payload["seed"] = int(seed)
        online_run, offline_truth = run_ideal_registration(
            IdealRegistrationConfig(**config_payload)
        )
        results.append(evaluate_ideal_registration(online_run, offline_truth))
    return tuple(results)


def assert_online_run_truth_free(online_run: OnlineRegistrationRun) -> None:
    """Fail if an online dataclass field name exposes evaluator identity data."""

    field_names: set[str] = set()
    for instance in (
        online_run,
        *online_run.frames,
        *online_run.associations,
    ):
        fields = getattr(instance, "__dataclass_fields__", {})
        field_names.update(str(name).lower() for name in fields)
    violations = sorted(
        name
        for name in field_names
        if any(token in name for token in FORBIDDEN_ONLINE_IDENTITY_TOKENS)
    )
    if violations:
        raise ValueError(f"online schema exposes truth identity fields: {violations}")


def candidate_columns(cost_matrix: np.ndarray, *, top_k: int) -> tuple[tuple[int, ...], ...]:
    """Return per-row sparse display candidates without changing the solver."""

    matrix = np.asarray(cost_matrix, dtype=float)
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise ValueError("cost_matrix must be a finite two-dimensional array")
    count = min(max(int(top_k), 1), matrix.shape[1])
    return tuple(
        tuple(int(value) for value in np.argsort(row, kind="stable")[:count])
        for row in matrix
    )


def _initial_target_states(
    config: IdealRegistrationConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    column_count = max(1, int(ceil(sqrt(config.target_count * 5.0 / 4.0))))
    row_count = int(ceil(config.target_count / column_count))
    center = np.asarray(config.formation_center_ned, dtype=float)
    states = np.zeros((config.target_count, 6), dtype=float)
    for index in range(config.target_count):
        row = index // column_count
        column = index % column_count
        east_offset = (column - 0.5 * (column_count - 1)) * 60.0
        east_offset += (row % 2) * 15.0
        down_offset = (row - 0.5 * (row_count - 1)) * 35.0
        north_offset = ((row + column) % 2) * 8.0 - 4.0
        states[index, :3] = center + np.array(
            [north_offset, east_offset, down_offset], dtype=float
        )
        speed = float(
            rng.uniform(config.target_speed_min_mps, config.target_speed_max_mps)
        )
        direction = np.array(
            [-1.0, rng.uniform(-0.20, 0.20), rng.uniform(-0.05, 0.05)],
            dtype=float,
        )
        states[index, 3:] = direction / np.linalg.norm(direction) * speed
    return states


def _initial_camera_b_state(config: IdealRegistrationConfig) -> np.ndarray:
    state = np.zeros((1, 6), dtype=float)
    state[0, :3] = np.asarray(config.camera_b_position_ned, dtype=float)
    direction = np.array([1.0, -0.22, -0.025], dtype=float)
    state[0, 3:] = direction / np.linalg.norm(direction) * config.camera_b_speed_mps
    return state


def _shuffled_local_ids(
    camera_prefix: str,
    count: int,
    rng: np.random.Generator,
) -> tuple[str, ...]:
    labels = np.array(
        [f"{camera_prefix}-L{index + 1:03d}" for index in range(count)],
        dtype=object,
    )
    rng.shuffle(labels)
    return tuple(str(value) for value in labels.tolist())


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0
