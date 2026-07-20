from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import numpy as np
import pytest

from d2_data_association import (
    Detection3D,
    GlobalTrack3D,
    OfflineTruthLabel3D,
    Scalable3DTracker,
    Sparse3DGNNHungarianAssociator,
    Sparse3DOfflineEvaluator,
    detection3d_from_position_measurement,
    detections3d_from_d1_global_tracks,
    mahalanobis_squared_3d,
)


def _grid_state(count: int) -> tuple[np.ndarray, np.ndarray]:
    indices = np.arange(count, dtype=float)
    positions = np.column_stack(
        (
            (indices % 20.0) * 100.0,
            np.floor(indices / 20.0) * 100.0,
            -100.0 - (indices % 4.0) * 25.0,
        )
    )
    velocities = np.column_stack(
        (
            2.0 + (indices % 3.0) * 0.1,
            -0.5 + (indices % 5.0) * 0.05,
            (indices % 2.0) * 0.04,
        )
    )
    return positions, velocities


def _detections(
    timestamp: float,
    positions: np.ndarray,
    velocities: np.ndarray,
    *,
    prefix: str = "anonymous",
) -> list[Detection3D]:
    return [
        Detection3D(
            detection_id=f"{prefix}-{timestamp:.1f}-{index:04d}",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.05,
            position_ned=position,
            covariance=np.eye(3, dtype=float),
            velocity_ned=velocity,
            velocity_covariance=np.eye(3, dtype=float) * 0.25,
            source_node_id="d1-center",
            source_track_id=f"local-{index:04d}",
            metadata={"frame_index": int(round(timestamp * 10.0))},
        )
        for index, (position, velocity) in enumerate(
            zip(positions, velocities, strict=True)
        )
    ]


def _labels(
    detections: list[Detection3D],
    truth_indices: list[int] | None = None,
) -> list[OfflineTruthLabel3D]:
    indices = list(range(len(detections))) if truth_indices is None else truth_indices
    return [
        OfflineTruthLabel3D(
            detection_id=detection.detection_id,
            truth_id=f"target-{truth_index:04d}",
            measurement_timestamp=detection.measurement_timestamp,
        )
        for detection, truth_index in zip(detections, indices, strict=True)
    ]


@pytest.mark.parametrize("target_count", [5, 20, 50, 100, 200])
def test_sparse_3d_curriculum_scales_without_dense_candidate_expansion(
    target_count: int,
) -> None:
    positions, velocities = _grid_state(target_count)
    tracker = Scalable3DTracker()
    tracker.step(_detections(0.0, positions, velocities))

    next_positions = positions + velocities
    result = tracker.step(_detections(1.0, next_positions, velocities))

    assert len(result.matched_pairs) == target_count
    assert len(tracker.active_tracks()) == target_count
    assert all(track.state.shape == (6,) for track in tracker.active_tracks())
    assert all(track.covariance.shape == (6, 6) for track in tracker.active_tracks())
    assert result.metadata["state_order"] == ["pN", "pE", "pD", "vN", "vE", "vD"]
    assert result.metadata["innovation_dimension"] == 3
    assert result.metadata["candidate_edge_count"] == target_count
    assert result.metadata["component_matrix_pair_count"] == target_count
    assert result.metadata["dense_pair_count"] == target_count**2
    assert result.metadata["unconditional_dense_matrix_allocated"] is False
    assert result.cost_matrix is None
    assert result.distance_matrix is None
    assert result.metadata["association_runtime_seconds"] >= 0.0
    assert result.metadata["candidate_pruning_ratio"] == pytest.approx(
        1.0 - 1.0 / target_count
    )


def test_three_dimensional_mahalanobis_gate_uses_down_axis() -> None:
    track = GlobalTrack3D(
        global_track_id="GT3D-test",
        state=np.zeros(6, dtype=float),
        covariance=np.diag([1.0, 100.0, 1.0, 1.0, 1.0, 1.0]),
        timestamp=0.0,
    )
    near = Detection3D(
        "near",
        0.0,
        0.0,
        np.array([0.0, 0.0, 1.0]),
        np.eye(3, dtype=float),
    )
    far_down = Detection3D(
        "far-down",
        0.0,
        0.0,
        np.array([0.0, 0.0, 10.0]),
        np.eye(3, dtype=float),
    )
    associator = Sparse3DGNNHungarianAssociator()

    result = associator.associate([track], [far_down], 0.0)

    assert mahalanobis_squared_3d(track, near) == pytest.approx(0.5)
    assert mahalanobis_squared_3d(track, far_down) == pytest.approx(50.0)
    assert not result.matched_pairs
    assert result.rejected_pairs[0].reason == "mahalanobis_gate_3d"


def test_crossing_uses_velocity_tie_break_without_changing_3d_gate() -> None:
    tracker = Scalable3DTracker()
    evaluator = Sparse3DOfflineEvaluator()
    first = [
        Detection3D(
            "scan0-a",
            0.0,
            0.05,
            np.array([-10.0, 0.0, -100.0]),
            np.eye(3),
            velocity_ned=np.array([10.0, 0.0, 0.0]),
            velocity_covariance=np.eye(3) * 0.1,
        ),
        Detection3D(
            "scan0-b",
            0.0,
            0.05,
            np.array([10.0, 0.0, -100.0]),
            np.eye(3),
            velocity_ned=np.array([-10.0, 0.0, 0.0]),
            velocity_covariance=np.eye(3) * 0.1,
        ),
    ]
    first_result = tracker.step(first)
    evaluator.record_frame(
        first_result,
        [
            OfflineTruthLabel3D("scan0-a", "eastbound", 0.0),
            OfflineTruthLabel3D("scan0-b", "westbound", 0.0),
        ],
    )
    crossing = [
        Detection3D(
            "scan1-east",
            1.0,
            1.05,
            np.array([0.0, 0.0, -100.0]),
            np.eye(3),
            velocity_ned=np.array([10.0, 0.0, 0.0]),
            velocity_covariance=np.eye(3) * 0.1,
        ),
        Detection3D(
            "scan1-west",
            1.0,
            1.05,
            np.array([0.0, 0.0, -100.0]),
            np.eye(3),
            velocity_ned=np.array([-10.0, 0.0, 0.0]),
            velocity_covariance=np.eye(3) * 0.1,
        ),
    ]
    crossing_result = tracker.step(crossing)
    evaluator.record_frame(
        crossing_result,
        [
            OfflineTruthLabel3D("scan1-east", "eastbound", 1.0),
            OfflineTruthLabel3D("scan1-west", "westbound", 1.0),
        ],
    )
    final = [
        Detection3D(
            "scan2-east",
            2.0,
            2.05,
            np.array([10.0, 0.0, -100.0]),
            np.eye(3),
            velocity_ned=np.array([10.0, 0.0, 0.0]),
            velocity_covariance=np.eye(3) * 0.1,
        ),
        Detection3D(
            "scan2-west",
            2.0,
            2.05,
            np.array([-10.0, 0.0, -100.0]),
            np.eye(3),
            velocity_ned=np.array([-10.0, 0.0, 0.0]),
            velocity_covariance=np.eye(3) * 0.1,
        ),
    ]
    final_result = tracker.step(final)
    evaluator.record_frame(
        final_result,
        [
            OfflineTruthLabel3D("scan2-east", "eastbound", 2.0),
            OfflineTruthLabel3D("scan2-west", "westbound", 2.0),
        ],
    )

    summary = evaluator.summary()
    assert crossing_result.metadata["candidate_edge_count"] == 4
    assert crossing_result.metadata["gate_metric"] == "3d_position_mahalanobis_squared"
    assert summary["id_switch_count"] == 0
    assert summary["track_continuity"] == pytest.approx(1.0)


def test_missed_detections_preserve_identity_until_reacquisition() -> None:
    target_count = 20
    positions, velocities = _grid_state(target_count)
    tracker = Scalable3DTracker(drop_miss_threshold=5)
    evaluator = Sparse3DOfflineEvaluator()
    truth_ids = [f"target-{index:04d}" for index in range(target_count)]

    for timestamp in range(5):
        frame_positions = positions + velocities * timestamp
        detections = _detections(float(timestamp), frame_positions, velocities)
        truth_indices = list(range(target_count))
        if timestamp in {2, 3}:
            detections.pop(7)
            truth_indices.pop(7)
        result = tracker.step(detections, float(timestamp))
        evaluator.record_frame(
            result,
            _labels(detections, truth_indices),
            truth_ids_present=truth_ids,
        )

    summary = evaluator.summary()
    assert summary["id_switch_count"] == 0
    assert summary["track_continuity"] == pytest.approx(0.98)
    assert summary["coverage_continuity"] == pytest.approx(0.98)
    assert len(tracker.active_tracks()) == target_count
    assert tracker.summary()["lost_count"] == 1


def test_false_alarms_remain_unlabeled_and_do_not_switch_true_tracks() -> None:
    target_count = 50
    positions, velocities = _grid_state(target_count)
    tracker = Scalable3DTracker()
    evaluator = Sparse3DOfflineEvaluator()
    initial = _detections(0.0, positions, velocities)
    initial_result = tracker.step(initial)
    evaluator.record_frame(initial_result, _labels(initial))

    true_detections = _detections(1.0, positions + velocities, velocities)
    false_positions = np.column_stack(
        (
            np.arange(15, dtype=float) * 80.0 + 5_000.0,
            np.full(15, 5_000.0),
            np.full(15, -800.0),
        )
    )
    false_velocities = np.zeros((15, 3), dtype=float)
    false_alarms = _detections(
        1.0,
        false_positions,
        false_velocities,
        prefix="false-alarm",
    )
    result = tracker.step([*true_detections, *false_alarms])
    evaluator.record_frame(result, _labels(true_detections))

    summary = evaluator.summary()
    assert result.metadata["candidate_edge_count"] == target_count
    assert result.metadata["dense_pair_count"] == target_count * (target_count + 15)
    assert len(result.metadata["created_track_ids_by_detection"]) == 15
    assert summary["false_alarm_assignment_count"] == 15
    assert summary["id_switch_count"] == 0
    assert summary["track_continuity"] == pytest.approx(1.0)


def test_online_contract_rejects_truth_and_upstream_global_id_is_not_authority() -> None:
    assert "truth_id" not in {item.name for item in fields(Detection3D)}
    assert "truth_id" not in {item.name for item in fields(GlobalTrack3D)}
    with pytest.raises(ValueError, match="evaluator or external identity"):
        Detection3D(
            "bad",
            0.0,
            0.0,
            np.zeros(3),
            np.eye(3),
            metadata={"nested": {"truth_id": "forbidden"}},
        )
    mutated = Detection3D(
        "mutated-after-construction",
        0.0,
        0.0,
        np.zeros(3),
        np.eye(3),
    )
    mutated.metadata["truthId"] = "forbidden-after-construction"
    with pytest.raises(ValueError, match="evaluator or external identity"):
        Scalable3DTracker().step([mutated])

    d1_track = SimpleNamespace(
        global_track_id="UPSTREAM-MUST-NOT-BECOME-CANONICAL",
        state=np.array([1.0, 2.0, -3.0, 4.0, 5.0, 6.0]),
        covariance=np.eye(6),
        timestamp=1.25,
        metadata={
            "frame_id": "NED",
            "measurement_timestamp": 1.0,
            "arrival_timestamp": 1.2,
            "published_at": 1.25,
        },
    )
    timestamp, detections = detections3d_from_d1_global_tracks([d1_track])
    tracker = Scalable3DTracker()
    result = tracker.step(detections, timestamp)

    assert timestamp == pytest.approx(1.25)
    assert detections[0].measurement_timestamp == pytest.approx(1.25)
    assert detections[0].arrival_timestamp == pytest.approx(1.25)
    assert detections[0].metadata["source_measurement_timestamp"] == pytest.approx(
        1.0
    )
    assert detections[0].metadata["source_arrival_timestamp"] == pytest.approx(1.2)
    assert detections[0].detection_id.startswith("d1-3d-")
    assert "UPSTREAM" not in str(detections[0].to_dict())
    assert result.metadata["detection_to_track"][detections[0].detection_id].startswith(
        "GT3D-"
    )
    assert result.metadata["global_track_id_owner"] == "D2_center"
    assert result.metadata["id_switch_count"] is None
    assert result.metadata["track_continuity"] is None
    assert result.metadata["identity_continuity"] is None
    assert result.metadata["coverage_continuity"] is None
    assert result.metadata["continuity_available"] is False
    assert result.risk_summary is not None
    assert result.risk_summary.truth_metrics_available is False


def test_scalable_measurement_adapter_accepts_only_cartesian_ned() -> None:
    cartesian = SimpleNamespace(
        observation_id="obs-1",
        sensor_id="d1",
        modality="fused_position",
        measurement_timestamp=1.0,
        arrival_timestamp=1.1,
        frame_id="NED",
        measurement=np.array([10.0, 20.0, -30.0]),
        covariance=np.eye(3),
        confidence=0.9,
        metadata={"measurement_order": ["pN", "pE", "pD"]},
    )
    detection = detection3d_from_position_measurement(cartesian)
    assert detection.position_ned.tolist() == [10.0, 20.0, -30.0]

    raw_radar = SimpleNamespace(
        **{
            **vars(cartesian),
            "observation_id": "radar-1",
            "modality": "radar",
            "measurement_order": None,
            "metadata": {
                "measurement_order": ["range_m", "azimuth_rad", "elevation_rad"]
            },
        }
    )
    with pytest.raises(ValueError, match="not Cartesian NED"):
        detection3d_from_position_measurement(raw_radar)

    raw_radar_without_order = SimpleNamespace(
        **{
            **vars(cartesian),
            "observation_id": "radar-2",
            "modality": "radar_spherical",
            "metadata": {},
        }
    )
    with pytest.raises(ValueError, match="Cartesian 3D position"):
        detection3d_from_position_measurement(raw_radar_without_order)


def test_history_and_frame_audit_are_bounded() -> None:
    positions, velocities = _grid_state(5)
    tracker = Scalable3DTracker(track_history_limit=6, frame_log_limit=7)
    for timestamp in range(30):
        tracker.step(
            _detections(
                float(timestamp),
                positions + velocities * timestamp,
                velocities,
            )
        )

    assert all(len(track.history) <= 6 for track in tracker.active_tracks())
    summary = tracker.summary()
    assert len(summary["frame_logs"]) == 7
    assert summary["frame_log_limit"] == 7
    assert summary["truth_metrics_available"] is False
    assert summary["id_switch_count"] is None
    assert summary["track_continuity"] is None


def test_gnn_name_means_global_nearest_neighbor_not_graph_network() -> None:
    positions, velocities = _grid_state(5)
    tracker = Scalable3DTracker()
    tracker.step(_detections(0.0, positions, velocities))
    result = tracker.step(_detections(1.0, positions + velocities, velocities))

    assert result.metadata["gnn_meaning"] == "global_nearest_neighbor"
    assert result.metadata["graph_neural_network_used"] is False
    assert "Global nearest-neighbor" in (
        Sparse3DGNNHungarianAssociator.__doc__ or ""
    )
