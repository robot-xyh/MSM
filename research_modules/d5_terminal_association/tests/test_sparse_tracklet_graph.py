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
    SparseTrackletGraph,
    SparseTrackletGraphConfig,
    TrackletCameraGeometry,
    TrackletCluster,
    assert_anonymous_online_payload,
    bind_clusters_to_center_tracks,
    build_sparse_tracklet_graph,
    constrained_tracklet_clusters,
    is_truth_like_local_track_id,
)
from d5_terminal_association.tracklet_gnn import (
    NativeTrackletEdgeClassifier,
    OfflineTrackletTruthLabel,
    build_offline_edge_training_batch,
    train_small_sample,
)
import d5_terminal_association.tracklet_gnn as tracklet_gnn_module
import d5_terminal_association.sparse_tracklet_graph as graph_module
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


def test_truth_like_id_cache_preserves_legacy_rule_and_reuses_strings() -> None:
    values: tuple[object, ...] = (
        None,
        7,
        "",
        "trk-000001",
        "RESOURCE-17",
        "target-17",
        "camera_actor_3",
        "intruder.42",
    )
    graph_module._is_truth_like_local_track_id_text.cache_clear()

    def legacy(value: object) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        return bool(
            text
            and (
                graph_module._IDENTITY_TOKEN.search(text)
                or graph_module._TRUTH_LIKE_LOCAL_ID.search(text)
            )
        )

    first = tuple(is_truth_like_local_track_id(value) for value in values)
    second = tuple(is_truth_like_local_track_id(value) for value in values)

    assert first == tuple(legacy(value) for value in values)
    assert second == first
    cache_info = graph_module._is_truth_like_local_track_id_text.cache_info()
    assert cache_info.hits == sum(isinstance(value, str) for value in values)
    assert cache_info.currsize == sum(isinstance(value, str) for value in values)


def test_anonymous_payload_leaf_fast_path_still_audits_builtin_subclasses() -> None:
    class StringWithMetadata(str):
        pass

    value = StringWithMetadata("anonymous")
    value.truth_entity_id = "offline-only"

    assert_anonymous_online_payload(
        {"safe": ["trk-000001", 1, 2.0, True, None, b"bytes"]}
    )
    with pytest.raises(ValueError, match="truth_entity_id"):
        assert_anonymous_online_payload({"nested": value})


def test_singleton_binding_rows_match_legacy_cost_materialization_exactly() -> None:
    clusters = (
        TrackletCluster(
            cluster_key="cluster:a",
            node_indices=(0,),
            tracklet_keys=("camera:a",),
            camera_keys=("camera",),
        ),
        TrackletCluster(
            cluster_key="cluster:b|c",
            node_indices=(1, 2),
            tracklet_keys=("camera:b", "other:c"),
            camera_keys=("camera", "other"),
        ),
        TrackletCluster(
            cluster_key="cluster:d",
            node_indices=(3,),
            tracklet_keys=("third:d",),
            camera_keys=("third",),
        ),
    )
    distances = np.asarray(
        [
            [-0.0, np.inf, 4.0, 7.0],
            [2.0, 3.0, np.inf, 8.0],
            [4.0, 5.0, np.inf, 6.0],
            [np.inf, 1.5, 2.5, 9.0],
        ],
        dtype=float,
    )
    legacy = np.full((len(clusters), distances.shape[1]), np.inf, dtype=float)
    for row, cluster in enumerate(clusters):
        cluster_distances = distances[np.asarray(cluster.node_indices, dtype=int)]
        finite_count = np.sum(np.isfinite(cluster_distances), axis=0)
        finite_sum = np.sum(
            np.where(np.isfinite(cluster_distances), cluster_distances, 0.0),
            axis=0,
        )
        valid = finite_count == len(cluster.node_indices)
        legacy[row, valid] = finite_sum[valid] / finite_count[valid]

    candidate = graph_module._cluster_binding_cost_matrix(
        clusters,
        distances,
        center_track_count=distances.shape[1],
    )

    assert np.array_equal(candidate, legacy)
    assert np.array_equal(np.signbit(candidate), np.signbit(legacy))


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
    ("field_name", "truth_like_id"),
    [
        ("resource_id", "MSM_TargetActor_1"),
        ("camera_id", "object-camera-1"),
    ],
)
def test_truth_like_resource_and_camera_names_are_rejected(
    field_name: str,
    truth_like_id: str,
) -> None:
    values = {
        "resource_id": "RESOURCE",
        "camera_id": "CAM-0",
        "local_track_id": "local-001",
        "measurement_timestamp": 1.0,
        "arrival_timestamp": 1.1,
        "center_px": np.array([20.0, 30.0]),
        "covariance_px": np.eye(2),
    }
    values[field_name] = truth_like_id

    with pytest.raises(ValueError, match=f"{field_name} must be anonymous"):
        CameraLocalTracklet(**values)


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


def test_small_final_degree_cap_is_deterministic_bounded_and_geometry_safe() -> None:
    points = np.array(
        [
            [1000.0, -45.0, -65.0],
            [990.0, -15.0, -45.0],
            [1010.0, 15.0, -35.0],
            [1020.0, 45.0, -55.0],
        ],
        dtype=float,
    )
    tracklets, cameras, center_tracks = _projected_inputs(points, camera_count=4)
    default_graph = build_sparse_tracklet_graph(
        tracklets,
        cameras,
        center_tracks=center_tracks,
    )
    config = SparseTrackletGraphConfig(max_neighbors_per_node=2)
    forward = build_sparse_tracklet_graph(
        tracklets,
        cameras,
        center_tracks=center_tracks,
        config=config,
    )
    reverse = build_sparse_tracklet_graph(
        reversed(tracklets),
        reversed(cameras),
        center_tracks=reversed(center_tracks),
        config=config,
    )

    def edge_keys(graph: SparseTrackletGraph) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                tuple(sorted((edge.source_tracklet_key, edge.target_tracklet_key)))
                for edge in graph.edges
            )
        )

    degrees = np.bincount(forward.edge_index.reshape(-1), minlength=forward.node_count)
    geometry_counts = (
        "time_gate_pass",
        "fov_gate_pass",
        "epipolar_gate_pass",
        "ray_gate_pass",
        "reprojection_gate_pass",
        "covariance_gate_pass",
        "global_projection_gate_pass",
        "rejected_geometry_gate_total",
    )

    assert edge_keys(forward) == edge_keys(reverse)
    assert int(degrees.max()) <= config.max_neighbors_per_node
    assert forward.edge_count <= forward.node_count * config.max_neighbors_per_node // 2
    assert forward.candidate_counts["effective_degree_upper_bound"] == 2
    assert forward.candidate_counts["retained_edge_count_upper_bound"] == forward.node_count
    assert forward.candidate_counts["retained_max_degree"] == int(degrees.max())
    assert forward.candidate_counts["rejected_final_degree_cap"] > 0
    assert forward.candidate_counts["pre_cap_edges"] == (
        forward.candidate_counts["retained_edges"]
        + forward.candidate_counts["rejected_final_degree_cap"]
    )
    assert forward.candidate_counts["geometry_gate_input_edges"] == (
        forward.candidate_counts["pre_cap_edges"]
        + forward.candidate_counts["rejected_geometry_gate_total"]
    )
    assert all(
        forward.candidate_counts[name] == default_graph.candidate_counts[name]
        for name in geometry_counts
    )
    assert all(
        forward.nodes[edge.source_index].camera_key
        != forward.nodes[edge.target_index].camera_key
        for edge in forward.edges
    )
