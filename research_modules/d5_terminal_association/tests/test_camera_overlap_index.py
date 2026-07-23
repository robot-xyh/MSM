from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from d5_terminal_association.models import CameraModel, GlobalTrack
from d5_terminal_association.scalable_3d_adapter import (
    run_scalable_3d_online_association,
)
from d5_terminal_association.sparse_tracklet_graph import (
    CameraLocalTracklet,
    SparseTrackletGraphConfig,
    TrackletCameraGeometry,
    _occupied_bucket_pairs,
    bind_clusters_to_center_tracks,
    build_camera_overlap_index,
    build_sparse_tracklet_graph,
    constrained_tracklet_clusters,
)


IMAGE_SIZE = (1280, 720)
K = np.array(
    [
        [540.0, 0.0, 640.0],
        [0.0, 540.0, 360.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=float,
)
# Camera x/y/z axes align with NED east/down/north respectively.
R_CAMERA_FROM_NED = np.array(
    [
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
    ],
    dtype=float,
)
TARGET_POINT = np.array([1000.0, 0.0, 0.0], dtype=float)


def _camera(
    index: int,
    *,
    east_offset_m: float | None = None,
    timestamp: float = 10.0,
) -> TrackletCameraGeometry:
    east = float(index) * 0.25 if east_offset_m is None else float(east_offset_m)
    center = np.array([0.0, east, -20.0], dtype=float)
    model = CameraModel(
        K=K,
        R=R_CAMERA_FROM_NED,
        t=-R_CAMERA_FROM_NED @ center,
        image_size=IMAGE_SIZE,
        measurement_cov=np.eye(2, dtype=float),
    )
    return TrackletCameraGeometry(
        resource_id=f"RESOURCE-{index:04d}",
        camera_id=f"CAM-{index:04d}",
        camera=model,
        measurement_timestamp=timestamp,
        position_covariance_ned=np.eye(3, dtype=float) * 0.04,
        attitude_covariance_rad2=np.eye(3, dtype=float) * np.deg2rad(0.05) ** 2,
    )


def _project(point_ned: np.ndarray, geometry: TrackletCameraGeometry) -> np.ndarray:
    camera_point = geometry.camera.R @ point_ned + geometry.camera.t
    assert camera_point[2] > 0.0
    return np.array(
        [
            geometry.camera.K[0, 0] * camera_point[0] / camera_point[2]
            + geometry.camera.K[0, 2],
            geometry.camera.K[1, 1] * camera_point[1] / camera_point[2]
            + geometry.camera.K[1, 2],
        ],
        dtype=float,
    )


def _tracklet(
    geometry: TrackletCameraGeometry,
    local_index: int = 0,
    *,
    point_ned: np.ndarray = TARGET_POINT,
) -> CameraLocalTracklet:
    center = _project(point_ned, geometry)
    half_width = 10.0 + 0.1 * local_index
    half_height = 7.0 + 0.1 * local_index
    return CameraLocalTracklet(
        resource_id=geometry.resource_id,
        camera_id=geometry.camera_id,
        local_track_id=f"local-{local_index:04d}",
        measurement_timestamp=geometry.measurement_timestamp,
        arrival_timestamp=geometry.measurement_timestamp + 0.05,
        center_px=center,
        covariance_px=np.eye(2, dtype=float),
        bbox_xyxy=(
            center[0] - half_width,
            center[1] - half_height,
            center[0] + half_width,
            center[1] + half_height,
        ),
        confidence=0.95,
        metadata={"source": "anonymous_structural_fixture"},
    )


@pytest.mark.parametrize("camera_count", [5, 20, 50, 100, 200])
def test_camera_overlap_index_scales_by_budget_not_complete_pair_list(
    camera_count: int,
) -> None:
    cameras = tuple(_camera(index) for index in range(camera_count))
    tracklets = tuple(_tracklet(camera) for camera in cameras)
    center_tracks = (
        GlobalTrack(
            global_track_id="GT-CENTER-0001",
            position=TARGET_POINT,
            covariance=np.eye(3, dtype=float) * 4.0,
            timestamp=10.0,
        ),
    )
    budget = 2 * camera_count
    config = SparseTrackletGraphConfig(
        camera_pair_budget=budget,
        max_tracklet_candidate_edges_per_node=4,
        max_neighbors_per_node=4,
    )

    index = build_camera_overlap_index(cameras, config=config)
    graph = build_sparse_tracklet_graph(
        tracklets,
        cameras,
        center_tracks=center_tracks,
        config=config,
    )

    all_possible = camera_count * (camera_count - 1) // 2
    assert index.candidate_counts["all_possible_camera_pairs"] == all_possible
    assert index.candidate_counts["camera_pairs_inspected"] <= budget
    assert index.candidate_counts["indexed_camera_pairs"] <= budget
    assert len(index.camera_pairs) <= budget
    assert {key for pair in index.camera_pairs for key in pair} == {
        camera.camera_key for camera in cameras
    }
    assert graph.candidate_counts["candidate_tracklet_edges"] <= camera_count * 2
    assert graph.candidate_counts["camera_pairs_inspected"] <= budget
    if all_possible > budget:
        assert index.candidate_counts["camera_pair_budget_exhausted"] == 1
        assert index.candidate_counts["camera_pair_budget_dropped"] == all_possible - budget


def test_nonoverlapping_camera_frusta_do_not_create_candidate_pair() -> None:
    cameras = (_camera(0), _camera(1, east_offset_m=50_000.0))

    index = build_camera_overlap_index(cameras)

    assert index.candidate_counts["all_possible_camera_pairs"] == 1
    assert index.candidate_counts["indexed_camera_pairs"] == 0
    assert index.camera_pairs == ()


def test_overlapping_camera_frusta_create_time_aligned_pair() -> None:
    cameras = (_camera(0), _camera(1, east_offset_m=15.0))

    index = build_camera_overlap_index(cameras)

    assert index.camera_pairs == ((cameras[0].camera_key, cameras[1].camera_key),)
    assert index.candidate_counts["indexed_camera_pairs"] == 1
    assert index.candidate_counts["camera_time_rejected_pairs"] == 0
    assert index.candidate_counts["camera_overlap_rejected_pairs"] == 0


def test_camera_pair_budget_clipping_order_is_input_order_independent() -> None:
    cameras = tuple(_camera(index) for index in range(20))
    config = SparseTrackletGraphConfig(camera_pair_budget=7)

    forward = build_camera_overlap_index(cameras, config=config)
    reverse = build_camera_overlap_index(reversed(cameras), config=config)

    assert forward.camera_pairs == reverse.camera_pairs
    assert forward.candidate_counts == reverse.candidate_counts
    assert forward.candidate_counts["camera_pair_budget_dropped"] == 183


def test_occupied_bucket_pairs_match_legacy_lattice_probe_exactly() -> None:
    occupied = tuple(
        sorted(
            {
                (-7, 2, 4),
                (-3, -1, 0),
                (0, 0, 0),
                (1, 2, -1),
                (5, -4, 3),
                (8, 2, 4),
            }
        )
    )
    radius = {bucket: 1 + index % 4 for index, bucket in enumerate(occupied)}
    max_radius = max(radius.values())
    maximum_search_radius = 7

    legacy: set[tuple[tuple[int, int, int], tuple[int, int, int]]] = set()
    occupied_set = frozenset(occupied)
    for left_bucket in occupied:
        search_radius = min(
            maximum_search_radius,
            radius[left_bucket] + max_radius,
        )
        for north_offset in range(-search_radius, search_radius + 1):
            for east_offset in range(-search_radius, search_radius + 1):
                for down_offset in range(-search_radius, search_radius + 1):
                    right_bucket = (
                        left_bucket[0] + north_offset,
                        left_bucket[1] + east_offset,
                        left_bucket[2] + down_offset,
                    )
                    if right_bucket in occupied_set and right_bucket >= left_bucket:
                        legacy.add((left_bucket, right_bucket))

    current = _occupied_bucket_pairs(
        occupied,
        radius,
        max_radius=max_radius,
        max_search_radius=maximum_search_radius,
    )

    assert set(current) == legacy
    assert len(current) == len(set(current))


def test_tracklet_candidate_degree_is_bounded_before_geometry_and_deterministic() -> None:
    cameras = tuple(_camera(index) for index in range(3))
    tracklets = tuple(
        _tracklet(
            camera,
            local_index,
            point_ned=TARGET_POINT + np.array([0.0, 0.2 * local_index, 0.0]),
        )
        for camera in cameras
        for local_index in range(12)
    )
    config = SparseTrackletGraphConfig(
        camera_pair_budget=3,
        max_tracklet_candidate_edges_per_node=3,
        max_neighbors_per_node=3,
        max_epipolar_error_px=1_000.0,
        max_ray_closest_distance_m=1_000.0,
        min_triangulation_angle_deg=0.001,
        max_reprojection_error_px=1_000.0,
        max_pixel_mahalanobis=1_000.0,
    )

    forward = build_sparse_tracklet_graph(tracklets, cameras, config=config)
    reverse = build_sparse_tracklet_graph(reversed(tracklets), reversed(cameras), config=config)

    candidate_limit = forward.node_count * config.max_tracklet_candidate_edges_per_node // 2
    assert forward.candidate_counts["candidate_tracklet_edges"] <= candidate_limit
    assert forward.candidate_counts["selected_camera_tracklet_pair_space"] == 432
    assert forward.candidate_counts["possible_cross_camera_pairs"] == 432
    assert tuple(
        (edge.source_tracklet_key, edge.target_tracklet_key) for edge in forward.edges
    ) == tuple(
        (edge.source_tracklet_key, edge.target_tracklet_key) for edge in reverse.edges
    )
    degree = np.bincount(forward.edge_index.reshape(-1), minlength=forward.node_count)
    assert int(degree.max(initial=0)) <= config.max_neighbors_per_node


def test_budget_exhaustion_leaves_unexamined_tracklets_unbound_and_preserves_center_id() -> None:
    cameras = tuple(_camera(index) for index in range(10))
    tracklets = tuple(_tracklet(camera) for camera in cameras)
    center_tracks = (
        GlobalTrack(
            global_track_id="GT-CENTER-0001",
            position=TARGET_POINT,
            covariance=np.eye(3, dtype=float) * 4.0,
            timestamp=10.0,
        ),
    )
    center_id_before = center_tracks[0].global_track_id
    config = SparseTrackletGraphConfig(
        camera_pair_budget=1,
        max_tracklet_candidate_edges_per_node=2,
        max_neighbors_per_node=2,
    )

    graph = build_sparse_tracklet_graph(
        tracklets,
        cameras,
        center_tracks=center_tracks,
        config=config,
    )
    clusters = constrained_tracklet_clusters(
        graph,
        np.full(graph.edge_count, 0.99, dtype=float),
    )
    decisions = bind_clusters_to_center_tracks(
        graph,
        clusters,
        cameras,
        center_tracks,
        config=config,
    )

    assert graph.candidate_counts["camera_pair_budget_exhausted"] == 1
    assert graph.candidate_counts["camera_pairs_inspected"] == 1
    assert sum(item.decision_state == "unbound" for item in decisions) >= 8
    assert {
        item.global_track_id for item in decisions if item.global_track_id is not None
    }.issubset({center_id_before})
    assert center_tracks[0].global_track_id == center_id_before
    assert "global_track_id" not in {item.name for item in fields(CameraLocalTracklet)}


def test_geometry_rejections_and_rule_path_are_explicit_in_scalable_diagnostics() -> None:
    cameras = (_camera(0), _camera(1, east_offset_m=15.0))
    tracklets = tuple(_tracklet(camera) for camera in cameras)
    center_tracks = (
        GlobalTrack(
            global_track_id="GT-CENTER-0001",
            position=TARGET_POINT,
            covariance=np.eye(3, dtype=float) * 4.0,
            timestamp=10.0,
        ),
    )
    graph = build_sparse_tracklet_graph(tracklets, cameras, center_tracks=center_tracks)
    association = run_scalable_3d_online_association(
        tracklets,
        cameras,
        center_tracks,
    )

    required_counts = {
        "all_possible_camera_pairs",
        "indexed_camera_pairs",
        "camera_pair_budget_dropped",
        "candidate_tracklet_edges",
        "rejected_epipolar",
        "rejected_ray_geometry",
        "rejected_ray_gate",
        "rejected_reprojection_gate",
        "rejected_covariance",
        "rejected_pixel_mahalanobis",
        "rejected_global_projection",
    }
    assert required_counts.issubset(graph.candidate_counts)
    assert association.diagnostics["probability_source"] == "deterministic_geometry_rule"
    assert association.diagnostics["scoring_status"] == "rule_fallback_model_missing"
    assert association.diagnostics["fallback_reason"] == "model_missing"
