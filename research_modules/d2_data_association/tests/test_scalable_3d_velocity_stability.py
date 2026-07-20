from __future__ import annotations

import numpy as np
import pytest

from d2_data_association import (
    Detection3D,
    OfflineTruthLabel3D,
    Scalable3DTracker,
    Sparse3DOfflineEvaluator,
)


def _source_posterior_detection(
    *,
    frame_index: int,
    target_index: int,
    timestamp: float,
    state: np.ndarray,
    covariance: np.ndarray,
) -> Detection3D:
    return Detection3D(
        detection_id=f"scan-{frame_index:03d}-{target_index:04d}",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        position_ned=state[:3],
        covariance=covariance[:3, :3],
        velocity_ned=state[3:],
        velocity_covariance=covariance[3:, 3:],
        state_estimate_covariance=covariance,
        metadata={"frame_index": frame_index},
    )


def _percentiles(values: list[float] | np.ndarray) -> np.ndarray:
    return np.percentile(np.asarray(values, dtype=float), [50.0, 90.0, 100.0])


def test_multiframe_noisy_six_state_posteriors_do_not_amplify_velocity() -> None:
    rng = np.random.default_rng(17)
    target_count = 50
    frame_count = 12
    frame_period = 0.2
    indices = np.arange(target_count, dtype=float)
    initial_positions = np.column_stack(
        (
            (indices % 10.0) * 500.0,
            np.floor(indices / 10.0) * 500.0,
            np.full(target_count, -200.0),
        )
    )
    true_velocities = np.column_stack(
        (
            np.full(target_count, 4.7),
            np.zeros((target_count, 2), dtype=float),
        )
    )
    source_covariance = np.block(
        [
            [np.eye(3) * 300.0, np.eye(3) * 20.0],
            [np.eye(3) * 20.0, np.eye(3) * 34.0],
        ]
    )
    position_perturbation = np.zeros((target_count, 3), dtype=float)
    tracker = Scalable3DTracker()
    evaluator = Sparse3DOfflineEvaluator()
    all_input_speeds: list[float] = []
    final_detection_positions = np.empty((target_count, 3), dtype=float)
    final_result = None

    for frame_index in range(frame_count):
        timestamp = frame_index * frame_period
        position_perturbation += rng.normal(0.0, 8.0, (target_count, 3))
        positions = (
            initial_positions
            + true_velocities * timestamp
            + position_perturbation
        )
        velocities = true_velocities + rng.normal(
            0.0,
            2.0,
            (target_count, 3),
        )
        states = np.hstack((positions, velocities))
        detections = [
            _source_posterior_detection(
                frame_index=frame_index,
                target_index=target_index,
                timestamp=timestamp,
                state=state,
                covariance=source_covariance,
            )
            for target_index, state in enumerate(states)
        ]
        final_result = tracker.step(detections, timestamp)
        evaluator.record_frame(
            final_result,
            [
                OfflineTruthLabel3D(
                    detection.detection_id,
                    f"offline-target-{target_index:04d}",
                    timestamp,
                )
                for target_index, detection in enumerate(detections)
            ],
        )
        all_input_speeds.extend(np.linalg.norm(velocities, axis=1).tolist())
        final_detection_positions = positions

    assert final_result is not None
    tracks_by_id = {
        track.global_track_id: track for track in tracker.active_tracks()
    }
    ordered_tracks = [
        tracks_by_id[
            final_result.metadata["detection_to_track"][
                f"scan-{frame_count - 1:03d}-{target_index:04d}"
            ]
        ]
        for target_index in range(target_count)
    ]
    output_speeds = [
        float(np.linalg.norm(track.velocity_ned)) for track in ordered_tracks
    ]
    input_speed_percentiles = _percentiles(all_input_speeds)
    output_speed_percentiles = _percentiles(output_speeds)
    velocity_covariance_traces = [
        float(np.trace(track.covariance[3:, 3:])) for track in ordered_tracks
    ]
    final_truth_positions = initial_positions + true_velocities * (
        (frame_count - 1) * frame_period
    )
    input_position_rmse = float(
        np.sqrt(
            np.mean(
                np.sum(
                    (final_detection_positions - final_truth_positions) ** 2,
                    axis=1,
                )
            )
        )
    )
    output_position_rmse = float(
        np.sqrt(
            np.mean(
                np.sum(
                    (
                        np.asarray([track.position_ned for track in ordered_tracks])
                        - final_truth_positions
                    )
                    ** 2,
                    axis=1,
                )
            )
        )
    )
    summary = evaluator.summary()

    assert len(ordered_tracks) == target_count
    assert output_speed_percentiles[0] <= input_speed_percentiles[0] * 1.05
    assert output_speed_percentiles[1] <= input_speed_percentiles[1] * 1.05
    assert output_speed_percentiles[2] <= input_speed_percentiles[2]
    assert np.median(velocity_covariance_traces) >= (
        0.9 * np.trace(source_covariance[3:, 3:])
    )
    assert output_position_rmse <= input_position_rmse
    assert summary["id_switch_count"] == 0
    assert summary["track_continuity"] == pytest.approx(1.0)
    assert tracker.summary()["state_update_mode_counts"] == {
        "correlated_6d_covariance_intersection": target_count * (frame_count - 1)
    }


def test_crossing_with_velocity_outlier_keeps_identity_and_position_gate() -> None:
    rng = np.random.default_rng(29)
    tracker = Scalable3DTracker()
    evaluator = Sparse3DOfflineEvaluator()
    source_covariance = np.diag([0.5, 0.5, 0.5, 9.0, 9.0, 9.0])
    velocity_update_gate_count = 0
    velocity_cost_gate_count = 0
    crossing_candidate_edges = None

    for frame_index in range(21):
        timestamp = frame_index * 0.2
        source_states = (
            np.array([-12.0 + 6.0 * timestamp, 0.0, -100.0, 6.0, 0.0, 0.0]),
            np.array([12.0 - 6.0 * timestamp, 0.0, -100.0, -6.0, 0.0, 0.0]),
        )
        detections: list[Detection3D] = []
        labels: list[OfflineTruthLabel3D] = []
        for target_index, source_state in enumerate(source_states):
            state = source_state.copy()
            state[:3] += rng.normal(0.0, 1.0, 3)
            state[3:] += rng.normal(0.0, 2.0, 3)
            if frame_index == 10 and target_index == 0:
                state[3:] = np.array([-50.0, 50.0, 0.0])
            detection = _source_posterior_detection(
                frame_index=frame_index,
                target_index=target_index,
                timestamp=timestamp,
                state=state,
                covariance=source_covariance,
            )
            detections.append(detection)
            labels.append(
                OfflineTruthLabel3D(
                    detection.detection_id,
                    ("offline-eastbound", "offline-westbound")[target_index],
                    timestamp,
                )
            )
        result = tracker.step(detections, timestamp)
        evaluator.record_frame(result, labels)
        velocity_update_gate_count += result.metadata[
            "velocity_innovation_gate_count"
        ]
        velocity_cost_gate_count += result.metadata[
            "velocity_cost_gated_edge_count"
        ]
        if frame_index == 10:
            crossing_candidate_edges = result.metadata["candidate_edge_count"]
            assert result.metadata["gate_metric"] == (
                "3d_position_mahalanobis_squared"
            )

    summary = evaluator.summary()
    assert crossing_candidate_edges == 4
    assert velocity_update_gate_count >= 1
    assert velocity_cost_gate_count >= 1
    assert len(tracker.active_tracks()) == 2
    assert summary["id_switch_count"] == 0
    assert summary["track_continuity"] == pytest.approx(1.0)


def test_two_hundred_correlated_posteriors_remain_sparse_and_speed_stable() -> None:
    rng = np.random.default_rng(41)
    target_count = 200
    frame_count = 10
    indices = np.arange(target_count, dtype=float)
    initial_positions = np.column_stack(
        (
            (indices % 20.0) * 120.0,
            np.floor(indices / 20.0) * 120.0,
            -150.0 - (indices % 4.0) * 30.0,
        )
    )
    velocities = np.column_stack(
        (
            3.5 + (indices % 5.0) * 0.2,
            -0.4 + (indices % 7.0) * 0.1,
            (indices % 3.0) * 0.05,
        )
    )
    source_covariance = np.diag([25.0] * 6)
    position_perturbation = np.zeros((target_count, 3), dtype=float)
    tracker = Scalable3DTracker()
    evaluator = Sparse3DOfflineEvaluator()
    input_speeds: list[float] = []
    measured_candidate_edges: list[int] = []
    final_result = None

    for frame_index in range(frame_count):
        timestamp = frame_index * 0.2
        position_perturbation += rng.normal(0.0, 2.0, (target_count, 3))
        positions = initial_positions + velocities * timestamp + position_perturbation
        measured_velocities = velocities + rng.normal(
            0.0,
            2.5,
            (target_count, 3),
        )
        states = np.hstack((positions, measured_velocities))
        detections = [
            _source_posterior_detection(
                frame_index=frame_index,
                target_index=target_index,
                timestamp=timestamp,
                state=state,
                covariance=source_covariance,
            )
            for target_index, state in enumerate(states)
        ]
        final_result = tracker.step(detections, timestamp)
        evaluator.record_frame(
            final_result,
            [
                OfflineTruthLabel3D(
                    detection.detection_id,
                    f"offline-target-{target_index:04d}",
                    timestamp,
                )
                for target_index, detection in enumerate(detections)
            ],
        )
        if frame_index > 0:
            measured_candidate_edges.append(
                final_result.metadata["candidate_edge_count"]
            )
        input_speeds.extend(np.linalg.norm(measured_velocities, axis=1).tolist())

    assert final_result is not None
    output_speeds = [
        float(np.linalg.norm(track.velocity_ned))
        for track in tracker.active_tracks()
    ]
    output_velocity_covariance_traces = [
        float(np.trace(track.covariance[3:, 3:]))
        for track in tracker.active_tracks()
    ]
    summary = evaluator.summary()

    assert len(tracker.active_tracks()) == target_count
    assert measured_candidate_edges == [target_count] * (frame_count - 1)
    assert final_result.metadata["dense_pair_count"] == target_count**2
    assert final_result.metadata["component_matrix_pair_count"] == target_count
    assert final_result.metadata["unconditional_dense_matrix_allocated"] is False
    assert _percentiles(output_speeds)[1] <= _percentiles(input_speeds)[1]
    assert np.median(output_velocity_covariance_traces) >= (
        0.9 * np.trace(source_covariance[3:, 3:])
    )
    assert summary["id_switch_count"] == 0
    assert summary["track_continuity"] == pytest.approx(1.0)
