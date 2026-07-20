from __future__ import annotations

from dataclasses import fields, replace
import inspect
import time

import numpy as np
import pytest
import torch

from d5_terminal_association.models import CameraModel, GlobalTrack
from d5_terminal_association.sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    CameraLocalTracklet,
    SparseTrackletGraphConfig,
    TrackletCameraGeometry,
    assert_anonymous_online_payload,
    bind_clusters_to_center_tracks,
    build_sparse_tracklet_graph,
    constrained_tracklet_clusters,
)
from d5_terminal_association.tracklet_gnn import (
    NativeTrackletEdgeClassifier,
    OfflineTrackletTruthLabel,
    build_offline_edge_training_batch,
    train_small_sample,
)
import d5_terminal_association.tracklet_gnn as tracklet_gnn_module
from research_modules.scalable_3d_simulation.camera_projection import (
    CameraIntrinsics,
    CameraPose,
    look_at_rotation_ned_to_camera,
    project_points,
)


CAMERA_POSITIONS = (
    np.array([0.0, -180.0, -20.0]),
    np.array([0.0, 180.0, -20.0]),
    np.array([-100.0, 0.0, -160.0]),
    np.array([80.0, 0.0, 80.0]),
)


def _projected_inputs(
    points: np.ndarray,
    *,
    camera_count: int,
    timestamp: float = 10.0,
    target_covariance_m2: float = 4.0,
) -> tuple[list[CameraLocalTracklet], list[TrackletCameraGeometry], list[GlobalTrack]]:
    intrinsics = CameraIntrinsics.from_horizontal_fov(
        width_px=1280,
        height_px=720,
        horizontal_fov_deg=100.0,
    )
    tracklets: list[CameraLocalTracklet] = []
    camera_geometries: list[TrackletCameraGeometry] = []
    point_covariance = np.broadcast_to(
        np.eye(3, dtype=float) * target_covariance_m2,
        (len(points), 3, 3),
    ).copy()
    for camera_index, position in enumerate(CAMERA_POSITIONS[:camera_count]):
        rotation = look_at_rotation_ned_to_camera(position, np.array([1000.0, 0.0, -50.0]))
        pose = CameraPose(
            position_ned=position,
            rotation_camera_from_ned=rotation,
            position_covariance_ned=np.eye(3, dtype=float) * 0.04,
            attitude_covariance_rad2=np.eye(3, dtype=float) * np.deg2rad(0.05) ** 2,
        )
        projection = project_points(
            points,
            camera_pose=pose,
            intrinsics=intrinsics,
            point_covariance_ned=point_covariance,
            object_size_m=(4.0, 3.0),
            pixel_noise_std=0.8,
        )
        assert np.all(projection.visible)
        camera = CameraModel(
            K=intrinsics.matrix(),
            R=rotation,
            t=-rotation @ position,
            image_size=(intrinsics.width_px, intrinsics.height_px),
            measurement_cov=np.eye(2, dtype=float) * 0.64,
        )
        camera_geometries.append(
            TrackletCameraGeometry(
                resource_id="RESOURCE",
                camera_id=f"CAM-{camera_index}",
                camera=camera,
                measurement_timestamp=timestamp,
                position_covariance_ned=pose.position_covariance_ned,
                attitude_covariance_rad2=pose.attitude_covariance_rad2,
            )
        )
        for target_index in range(len(points)):
            tracklets.append(
                CameraLocalTracklet(
                    resource_id="RESOURCE",
                    camera_id=f"CAM-{camera_index}",
                    local_track_id=f"local-{target_index:04d}",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + 0.05,
                    center_px=projection.pixel_centers[target_index],
                    covariance_px=projection.covariance_pixels[target_index],
                    bbox_xyxy=tuple(projection.bbox_xyxy[target_index]),
                    angular_velocity_rad_s=np.zeros(2, dtype=float),
                    bbox_scale_rate_s=0.0,
                    confidence=0.95,
                    tracklet_start_timestamp=timestamp - 0.4,
                    metadata={"source": "anonymous_bbox", "scan_index": 1},
                )
            )
    center_tracks = [
        GlobalTrack(
            global_track_id=f"GT-{target_index:04d}",
            position=point,
            covariance=np.eye(3, dtype=float) * target_covariance_m2,
            timestamp=timestamp,
        )
        for target_index, point in enumerate(points)
    ]
    return tracklets, camera_geometries, center_tracks


def test_geometry_features_constrained_clusters_and_center_binding() -> None:
    points = np.array(
        [
            [1000.0, -120.0, -80.0],
            [980.0, 0.0, -30.0],
            [1040.0, 130.0, 20.0],
        ],
        dtype=float,
    )
    tracklets, cameras, center_tracks = _projected_inputs(points, camera_count=3)
    graph = build_sparse_tracklet_graph(tracklets, cameras, center_tracks=center_tracks)

    assert graph.node_count == 9
    assert graph.edge_count == 9
    assert all(
        graph.nodes[edge.source_index].local_track_id
        == graph.nodes[edge.target_index].local_track_id
        for edge in graph.edges
    )
    required_features = {
        "time_delta_s",
        "pixel_mahalanobis",
        "reprojection_error_px",
        "ray_closest_distance_m",
        "bbox_log_scale_delta",
        "bbox_scale_rate_delta_s",
        "angular_velocity_delta_rad_s",
        "baseline_m",
        "extrinsics_covariance_trace",
    }
    assert required_features.issubset(EDGE_FEATURE_NAMES)
    assert np.all(np.isfinite(graph.edge_features))
    assert graph.candidate_counts["time_gate_pass"] >= graph.candidate_counts["fov_gate_pass"]
    assert graph.candidate_counts["fov_gate_pass"] >= graph.candidate_counts["epipolar_gate_pass"]
    assert graph.candidate_counts["epipolar_gate_pass"] >= graph.candidate_counts["ray_gate_pass"]
    assert graph.candidate_counts["ray_gate_pass"] >= graph.candidate_counts["reprojection_gate_pass"]
    assert graph.candidate_counts["reprojection_gate_pass"] >= graph.candidate_counts["covariance_gate_pass"]
    assert graph.candidate_counts["covariance_gate_pass"] >= graph.candidate_counts["global_projection_gate_pass"]

    clusters = constrained_tracklet_clusters(graph, np.full(graph.edge_count, 0.99))
    assert sorted(len(cluster.node_indices) for cluster in clusters) == [3, 3, 3]
    assert all(len(cluster.camera_keys) == len(set(cluster.camera_keys)) for cluster in clusters)
    original_center_ids = tuple(track.global_track_id for track in center_tracks)
    decisions = bind_clusters_to_center_tracks(graph, clusters, cameras, center_tracks)
    assert {decision.global_track_id for decision in decisions} == set(original_center_ids)
    assert all(decision.decision_state == "bound" for decision in decisions)
    assert tuple(track.global_track_id for track in center_tracks) == original_center_ids


def test_truth_and_actor_identity_are_rejected_from_online_tracklets() -> None:
    base = {
        "resource_id": "RESOURCE",
        "camera_id": "CAM-0",
        "local_track_id": "local-001",
        "measurement_timestamp": 1.0,
        "arrival_timestamp": 1.1,
        "center_px": np.array([20.0, 30.0]),
        "covariance_px": np.eye(2),
    }
    with pytest.raises(ValueError, match="identity fields"):
        CameraLocalTracklet(**base, metadata={"nested": {"actor_id": "TargetActor_1"}})
    with pytest.raises(ValueError, match="anonymous"):
        CameraLocalTracklet(**{**base, "local_track_id": "TargetActor_1"})
    with pytest.raises(ValueError, match="anonymous measurement key"):
        CameraLocalTracklet(**base, source_observation_id="TargetDrone_1")
    with pytest.raises(ValueError, match="identity fields"):
        assert_anonymous_online_payload({"track": {"global_track_id": "GT-0001"}})

    field_names = {item.name for item in fields(CameraLocalTracklet)}
    assert "truth_entity_id" not in field_names
    assert "global_track_id" not in field_names
    assert "assigned_global_track_id" not in field_names
    assert "source_observation_id" in field_names


@pytest.mark.parametrize(
    "truth_like_id",
    [
        "TGT-0001",
        "camera-0:TGT-002",
        "TargetDrone_1",
        "Target_UAV_7",
        "intruder-003",
    ],
)
def test_truth_like_local_ids_are_rejected_by_tracklet_constructor(truth_like_id: str) -> None:
    with pytest.raises(ValueError, match="anonymous"):
        CameraLocalTracklet(
            resource_id="RESOURCE",
            camera_id="CAM-0",
            local_track_id=truth_like_id,
            measurement_timestamp=1.0,
            arrival_timestamp=1.1,
            center_px=np.array([20.0, 30.0]),
            covariance_px=np.eye(2),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"nodes": [{"local_track_id": "TGT-0001"}]},
        {"graph": {"tracklet": {"tracklet_id": "TargetDrone_1"}}},
        {"batches": [{"detections": [{"detection_id": "intruder-003"}]}]},
    ],
)
def test_truth_like_local_ids_are_rejected_recursively(payload: object) -> None:
    with pytest.raises(ValueError, match="identity fields"):
        assert_anonymous_online_payload(payload)


@pytest.mark.parametrize(
    "local_track_id",
    [
        "cam01-track-0001",
        "local-001",
        "front_det_0",
        "Secondary_Recon_1:0:det:0001",
    ],
)
def test_normal_camera_local_ids_are_not_rejected(local_track_id: str) -> None:
    tracklet = CameraLocalTracklet(
        resource_id="RESOURCE",
        camera_id="CAM-0",
        local_track_id=local_track_id,
        measurement_timestamp=1.0,
        arrival_timestamp=1.1,
        center_px=np.array([20.0, 30.0]),
        covariance_px=np.eye(2),
    )
    assert tracklet.local_track_id == local_track_id
    assert_anonymous_online_payload({"nodes": [{"local_track_id": local_track_id}]})


def test_stale_camera_pose_arrival_skew_and_large_extrinsic_covariance_reject_edges() -> None:
    points = np.array([[1000.0, 0.0, -40.0]], dtype=float)
    tracklets, cameras, center_tracks = _projected_inputs(points, camera_count=2)
    assert build_sparse_tracklet_graph(tracklets, cameras, center_tracks=center_tracks).edge_count == 1

    stale_cameras = [replace(cameras[0], measurement_timestamp=8.0), cameras[1]]
    assert build_sparse_tracklet_graph(tracklets, stale_cameras, center_tracks=center_tracks).edge_count == 0

    delayed_tracklets = [tracklets[0], replace(tracklets[1], arrival_timestamp=12.0)]
    assert build_sparse_tracklet_graph(delayed_tracklets, cameras, center_tracks=center_tracks).edge_count == 0

    uncertain_cameras = [
        replace(cameras[0], position_covariance_ned=np.eye(3) * 1000.0),
        cameras[1],
    ]
    assert build_sparse_tracklet_graph(
        tracklets,
        uncertain_cameras,
        center_tracks=center_tracks,
        config=SparseTrackletGraphConfig(max_extrinsics_covariance_trace=100.0),
    ).edge_count == 0


def test_native_pytorch_forward_hard_negatives_and_small_sample_fit() -> None:
    rng = np.random.default_rng(4)
    points = np.column_stack(
        (
            rng.uniform(950.0, 1050.0, 8),
            rng.uniform(-40.0, 40.0, 8),
            rng.uniform(-70.0, -30.0, 8),
        )
    )
    tracklets, cameras, center_tracks = _projected_inputs(
        points,
        camera_count=3,
        timestamp=1.0,
        target_covariance_m2=25.0,
    )
    graph = build_sparse_tracklet_graph(
        tracklets,
        cameras,
        center_tracks=center_tracks,
        config=SparseTrackletGraphConfig(
            max_epipolar_error_px=1000.0,
            max_ray_closest_distance_m=1000.0,
            min_triangulation_angle_deg=0.001,
            max_reprojection_error_px=1000.0,
            max_pixel_mahalanobis=1000.0,
            max_global_projection_mahalanobis=1000.0,
            max_neighbors_per_node=20,
        ),
    )
    offline_labels = [
        OfflineTrackletTruthLabel(
            tracklet_key=node.tracklet_key,
            truth_entity_id=f"TRUTH-{node.local_track_id}",
            measurement_timestamp=node.measurement_timestamp,
        )
        for node in graph.nodes
    ]
    batch = build_offline_edge_training_batch(graph, offline_labels, hard_negative_ratio=3.0)
    assert batch.positive_count > 0
    assert batch.negative_count >= batch.positive_count
    assert batch.hard_negative_count == batch.negative_count
    assert float(batch.positive_weight) >= 1.0
    with pytest.raises(ValueError, match="timestamp does not align"):
        build_offline_edge_training_batch(
            graph,
            [replace(offline_labels[0], measurement_timestamp=99.0), *offline_labels[1:]],
        )

    torch.manual_seed(4)
    model = NativeTrackletEdgeClassifier(hidden_dim=24, message_passing_steps=2)
    probabilities = model.forward_graph(graph)
    assert probabilities.shape == (graph.edge_count,)
    assert torch.all((probabilities >= 0.0) & (probabilities <= 1.0))
    assert model.uses_native_index_add is True
    assert "torch_geometric" not in inspect.getsource(tracklet_gnn_module)

    previous_thread_count = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        evidence = train_small_sample(model, batch, epochs=60, learning_rate=0.01)
    finally:
        torch.set_num_threads(previous_thread_count)
    assert evidence.final_loss < evidence.initial_loss * 0.5
    assert evidence.final_training_accuracy >= 0.9
    assert evidence.hard_negative_count > 0


def test_200_target_four_camera_graph_is_sparse_and_bounded() -> None:
    rng = np.random.default_rng(200)
    target_count = 200
    points = np.column_stack(
        (
            rng.uniform(800.0, 1200.0, target_count),
            rng.uniform(-500.0, 500.0, target_count),
            rng.uniform(-250.0, 150.0, target_count),
        )
    )
    tracklets, cameras, center_tracks = _projected_inputs(points, camera_count=4)
    config = SparseTrackletGraphConfig(max_neighbors_per_node=6)

    started = time.perf_counter()
    graph = build_sparse_tracklet_graph(
        tracklets,
        cameras,
        center_tracks=center_tracks,
        config=config,
    )
    elapsed_s = time.perf_counter() - started

    assert graph.node_count == target_count * 4
    assert graph.candidate_counts["possible_cross_camera_pairs"] == 240_000
    assert graph.edge_count <= graph.node_count * config.max_neighbors_per_node // 2
    assert graph.density < 0.01
    degree = np.bincount(graph.edge_index.reshape(-1), minlength=graph.node_count)
    assert int(degree.max()) <= config.max_neighbors_per_node
    assert graph.candidate_counts["global_projection_gate_pass"] < 0.02 * 240_000
    assert elapsed_s < 15.0
