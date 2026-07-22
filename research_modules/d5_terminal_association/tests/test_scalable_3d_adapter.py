from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pytest

import d5_terminal_association.scalable_3d_adapter as adapter_module
import d5_terminal_association.sparse_tracklet_graph as graph_module
from d5_terminal_association.scalable_3d_adapter import (
    Scalable3DTerminalAdapter,
    global_track3d_to_projection_track,
    global_tracks3d_to_projection_tracks,
    run_scalable_3d_online_association,
)
from d5_terminal_association.tracklet_dataset import join_offline_observation_labels
from research_modules.scalable_3d_simulation.camera_projection import (
    CameraIntrinsics,
    CameraPose,
    look_at_rotation_ned_to_camera,
    project_points,
)
from research_modules.scalable_3d_simulation.models import OnlineSensorBatch, SensorMeasurement
from research_modules.d2_data_association.d2_data_association.scalable_3d_models import GlobalTrack3D


CAMERA_POSITIONS = (
    np.array([0.0, -180.0, -20.0]),
    np.array([0.0, 180.0, -20.0]),
    np.array([-100.0, 0.0, -160.0]),
    np.array([80.0, 0.0, 80.0]),
)
POINTS = np.array(
    [
        [1000.0, -120.0, -80.0],
        [980.0, 0.0, -30.0],
        [1040.0, 130.0, 20.0],
    ],
    dtype=float,
)
PARTIAL_VISIBILITY = ((0, 1), (1, 2), (0, 2), (0, 1, 2))


def _intrinsics() -> CameraIntrinsics:
    return CameraIntrinsics.from_horizontal_fov(
        width_px=1280,
        height_px=720,
        horizontal_fov_deg=100.0,
    )


def _camera_metadata(camera_index: int) -> dict[str, object]:
    intrinsics = _intrinsics()
    position = CAMERA_POSITIONS[camera_index]
    rotation = look_at_rotation_ned_to_camera(position, np.array([1000.0, 0.0, -50.0]))
    return {
        "measurement_order": ["u", "v", "xmin", "ymin", "xmax", "ymax"],
        "camera_position_ned": position.tolist(),
        "rotation_camera_from_ned": rotation.tolist(),
        "camera_intrinsics": {
            "width_px": intrinsics.width_px,
            "height_px": intrinsics.height_px,
            "fx": intrinsics.fx,
            "fy": intrinsics.fy,
            "cx": intrinsics.cx,
            "cy": intrinsics.cy,
        },
        "position_covariance_ned": (np.eye(3) * 0.04).tolist(),
        "attitude_covariance_rad2": (
            np.eye(3) * np.deg2rad(0.05) ** 2
        ).tolist(),
    }


def _projected_boxes(camera_index: int, point_indices: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    intrinsics = _intrinsics()
    position = CAMERA_POSITIONS[camera_index]
    rotation = look_at_rotation_ned_to_camera(position, np.array([1000.0, 0.0, -50.0]))
    projection = project_points(
        POINTS[np.asarray(point_indices, dtype=int)],
        camera_pose=CameraPose(
            position_ned=position,
            rotation_camera_from_ned=rotation,
            position_covariance_ned=np.eye(3) * 0.04,
            attitude_covariance_rad2=np.eye(3) * np.deg2rad(0.05) ** 2,
        ),
        intrinsics=intrinsics,
        point_covariance_ned=np.broadcast_to(
            np.eye(3) * 4.0,
            (len(point_indices), 3, 3),
        ).copy(),
        object_size_m=(4.0, 3.0),
        pixel_noise_std=0.8,
    )
    assert np.all(projection.visible)
    return projection.pixel_centers, projection.bbox_xyxy


def _measurement(
    *,
    camera_index: int,
    center: np.ndarray,
    bbox: np.ndarray | tuple[float, float, float, float],
    timestamp: float,
    frame_index: int,
    detection_index: int,
    observation_id: str | None = None,
    metadata_updates: dict[str, object] | None = None,
    confidence: float = 0.95,
    arrival_timestamp: float | None = None,
) -> SimpleNamespace:
    metadata = _camera_metadata(camera_index)
    metadata.update(metadata_updates or {})
    covariance = np.zeros((6, 6), dtype=float)
    covariance[:2, :2] = np.eye(2) * 0.64
    covariance[2:, 2:] = np.eye(4) * 4.0
    sensor_id = f"SENSOR-{camera_index}"
    return SimpleNamespace(
        observation_id=(
            observation_id
            or f"obs-c{camera_index:02d}-f{frame_index:04d}-d{detection_index:04d}"
        ),
        sensor_id=sensor_id,
        modality="vision_bbox",
        measurement_timestamp=timestamp,
        arrival_timestamp=(
            timestamp + 0.05 if arrival_timestamp is None else arrival_timestamp
        ),
        frame_id=f"camera_{camera_index}_optical",
        measurement=np.concatenate((np.asarray(center, dtype=float), np.asarray(bbox, dtype=float))),
        covariance=covariance,
        confidence=confidence,
        classification_hint="unmanned_aircraft",
        metadata=metadata,
    )


def _batch(
    camera_index: int,
    measurements: tuple[SimpleNamespace, ...],
    *,
    timestamp: float,
    frame_index: int,
    batch_id: str | None = None,
    include_camera_metadata: bool = False,
    arrival_timestamp: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        batch_id=batch_id or f"batch-c{camera_index:02d}-f{frame_index:04d}",
        sensor_id=f"SENSOR-{camera_index}",
        resource_id=f"RESOURCE-{camera_index}",
        camera_id=f"CAM-{camera_index}",
        measurement_timestamp=timestamp,
        arrival_timestamp=(
            timestamp + 0.05 if arrival_timestamp is None else arrival_timestamp
        ),
        measurements=measurements,
        camera_metadata=(_camera_metadata(camera_index) if include_camera_metadata else None),
    )


def _projected_batch(
    camera_index: int,
    point_indices: tuple[int, ...],
    *,
    timestamp: float = 10.0,
    frame_index: int = 1,
) -> SimpleNamespace:
    centers, boxes = _projected_boxes(camera_index, point_indices)
    measurements = tuple(
        _measurement(
            camera_index=camera_index,
            center=centers[index],
            bbox=boxes[index],
            timestamp=timestamp,
            frame_index=frame_index,
            detection_index=index,
        )
        for index in range(len(point_indices))
    )
    return _batch(
        camera_index,
        measurements,
        timestamp=timestamp,
        frame_index=frame_index,
    )


def _timed_projected_batch(
    camera_index: int,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    frame_index: int,
    center_offset_px: tuple[float, float] = (0.0, 0.0),
    point_index: int = 1,
) -> SimpleNamespace:
    centers, boxes = _projected_boxes(camera_index, (point_index,))
    offset = np.asarray(center_offset_px, dtype=float)
    bbox_offset = np.array([offset[0], offset[1], offset[0], offset[1]])
    measurement = _measurement(
        camera_index=camera_index,
        center=centers[0] + offset,
        bbox=boxes[0] + bbox_offset,
        timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_index=frame_index,
        detection_index=0,
    )
    return _batch(
        camera_index,
        (measurement,),
        timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_index=frame_index,
    )


def _center_tracks() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            global_track_id=f"GT-{index:04d}",
            state=np.concatenate((point, np.zeros(3))),
            covariance=np.eye(6) * 4.0,
            timestamp=10.0,
            track_version=7,
        )
        for index, point in enumerate(POINTS)
    ]


@pytest.mark.parametrize("camera_count", [2, 3, 4])
def test_two_to_four_camera_partial_visibility_binds_only_center_ids(camera_count: int) -> None:
    adapter = Scalable3DTerminalAdapter()
    batches = [
        _projected_batch(camera_index, PARTIAL_VISIBILITY[camera_index])
        for camera_index in range(camera_count)
    ]
    source_tracks = _center_tracks()
    center_ids_before = [track.global_track_id for track in source_tracks]

    result = adapter.process(batches, source_tracks)

    assert len(result.camera_batches) == camera_count
    assert all(batch.status == "ok" for batch in result.camera_batches)
    assert all(batch.tracklets[0].local_track_id == "trk-000001" for batch in result.camera_batches)
    assert len({tracklet.tracklet_key for tracklet in result.tracklets}) == len(result.tracklets)
    assert result.association.scoring_status == "rule_fallback_model_missing"
    assert result.association.probability_source == "deterministic_geometry_rule"
    assert all(
        len(cluster.camera_keys) == len(set(cluster.camera_keys))
        for cluster in result.association.clusters
    )
    bound_ids = {
        binding.global_track_id
        for binding in result.association.bindings
        if binding.global_track_id is not None
    }
    assert bound_ids == set(center_ids_before)
    assert [track.global_track_id for track in source_tracks] == center_ids_before


def test_cross_frame_local_id_is_tracker_owned_and_kinematics_are_computed() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))
    first = adapter.adapt_batch(
        _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=centers[0],
                    bbox=boxes[0],
                    timestamp=1.0,
                    frame_index=1,
                    detection_index=0,
                    observation_id="anonymous-observation-a",
                ),
            ),
            timestamp=1.0,
            frame_index=1,
        )
    )
    moved_center = centers[0] + np.array([10.0, 5.0])
    width = (boxes[0, 2] - boxes[0, 0]) * 1.2
    height = (boxes[0, 3] - boxes[0, 1]) * 1.2
    moved_bbox = np.array(
        [
            moved_center[0] - width / 2.0,
            moved_center[1] - height / 2.0,
            moved_center[0] + width / 2.0,
            moved_center[1] + height / 2.0,
        ]
    )
    second = adapter.adapt_batch(
        _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=moved_center,
                    bbox=moved_bbox,
                    timestamp=1.1,
                    frame_index=2,
                    detection_index=0,
                    observation_id="unrelated-observation-b",
                ),
            ),
            timestamp=1.1,
            frame_index=2,
        )
    )

    first_track = first.tracklets[0]
    second_track = second.tracklets[0]
    assert first_track.local_track_id == second_track.local_track_id == "trk-000001"
    assert first_track.local_track_id not in {
        "anonymous-observation-a",
        "unrelated-observation-b",
    }
    assert first_track.source_observation_id == "anonymous-observation-a"
    assert second_track.source_observation_id == "unrelated-observation-b"
    assert first_track.tracklet_key == second_track.tracklet_key
    intrinsics = _intrinsics()
    expected_velocity = np.array(
        [10.0 / intrinsics.fx / 0.1, 5.0 / intrinsics.fy / 0.1]
    )
    assert second_track.angular_velocity_rad_s == pytest.approx(expected_velocity)
    assert second_track.bbox_scale_rate_s > 0.0
    assert np.asarray(second_track.metadata["bbox_covariance_px"]).shape == (4, 4)
    assert second_track.metadata["mot_history_length"] == 2


def test_arrival_order_accepts_oosm_measurement_without_rewinding_tracker() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))

    def scan(
        measurement_timestamp: float,
        arrival_timestamp: float,
        offset: tuple[float, float],
        frame_index: int,
    ) -> SimpleNamespace:
        delta = np.asarray(offset, dtype=float)
        return _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=centers[0] + delta,
                    bbox=boxes[0] + np.array([delta[0], delta[1], delta[0], delta[1]]),
                    timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    frame_index=frame_index,
                    detection_index=0,
                ),
            ),
            timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_index=frame_index,
        )

    first = adapter.adapt_batch(scan(1.0, 1.10, (0.0, 0.0), 1))
    newest = adapter.adapt_batch(scan(1.2, 1.25, (4.0, 2.0), 2))
    late = adapter.adapt_batch(scan(1.1, 1.35, (2.0, 1.0), 3))
    resumed = adapter.adapt_batch(scan(1.3, 1.45, (6.0, 3.0), 4))

    assert first.tracklets[0].local_track_id == "trk-000001"
    assert newest.tracklets[0].local_track_id == "trk-000001"
    assert late.status == "oosm_ignored"
    assert late.measurement_timestamp == pytest.approx(1.1)
    assert late.arrival_timestamp == pytest.approx(1.35)
    assert late.tracklets == ()
    assert late.camera_geometry is not None
    assert late.camera_geometry.measurement_timestamp == pytest.approx(1.1)
    assert late.metadata["temporal_status"] == "oosm_measurement_ignored"
    assert late.metadata["tracker_state_updated"] is False
    assert late.metadata["oosm_measurement_ignored_count"] == 1
    assert late.metadata["latest_state_measurement_timestamp"] == pytest.approx(1.2)
    assert late.metadata["last_arrival_timestamp"] == pytest.approx(1.35)

    resumed_track = resumed.tracklets[0]
    assert resumed.status == "ok"
    assert resumed_track.local_track_id == "trk-000001"
    assert resumed_track.metadata["mot_history_length"] == 3
    assert resumed_track.tracklet_start_timestamp == pytest.approx(1.0)
    intrinsics = _intrinsics()
    assert resumed_track.angular_velocity_rad_s == pytest.approx(
        np.array([2.0 / intrinsics.fx / 0.1, 1.0 / intrinsics.fy / 0.1])
    )
    assert resumed.metadata["temporal_status"] == "in_order_state_update"
    assert resumed.metadata["oosm_measurement_ignored_count"] == 1
    assert resumed.metadata["latest_state_measurement_timestamp"] == pytest.approx(1.3)


def test_one_process_call_drains_two_normal_batches_from_the_same_camera() -> None:
    adapter = Scalable3DTerminalAdapter()
    first = _timed_projected_batch(
        0,
        measurement_timestamp=1.0,
        arrival_timestamp=1.10,
        frame_index=1,
    )
    second = _timed_projected_batch(
        0,
        measurement_timestamp=1.1,
        arrival_timestamp=1.20,
        frame_index=2,
        center_offset_px=(4.0, 2.0),
    )

    result = adapter.process((second, first), _center_tracks())

    assert [batch.arrival_timestamp for batch in result.camera_batches] == [1.10, 1.20]
    assert [batch.status for batch in result.camera_batches] == ["ok", "ok"]
    assert [
        batch.tracklets[0].metadata["mot_history_length"]
        for batch in result.camera_batches
    ] == [1, 2]
    assert len(result.tracklets) == result.association.graph.node_count == 1
    assert result.tracklets[0].source_observation_id == "obs-c00-f0002-d0000"
    assert result.tracklets[0].local_track_id == "trk-000001"
    assert len(result.camera_geometries) == 1
    assert result.camera_geometries[0].measurement_timestamp == pytest.approx(1.1)


def test_one_call_mixes_normal_and_oosm_batches_without_rewinding_state() -> None:
    adapter = Scalable3DTerminalAdapter()
    baseline = adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.0,
            arrival_timestamp=1.05,
            frame_index=1,
        )
    )
    normal = _timed_projected_batch(
        0,
        measurement_timestamp=1.2,
        arrival_timestamp=1.25,
        frame_index=2,
        center_offset_px=(4.0, 2.0),
    )
    oosm = _timed_projected_batch(
        0,
        measurement_timestamp=1.1,
        arrival_timestamp=1.35,
        frame_index=3,
        center_offset_px=(2.0, 1.0),
    )

    drained = adapter.adapt_batches((oosm, normal))
    resumed = adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.3,
            arrival_timestamp=1.45,
            frame_index=4,
            center_offset_px=(6.0, 3.0),
        )
    )

    assert baseline.tracklets[0].local_track_id == "trk-000001"
    assert [batch.status for batch in drained] == ["ok", "oosm_ignored"]
    assert [batch.measurement_timestamp for batch in drained] == [1.2, 1.1]
    assert drained[0].tracklets[0].metadata["mot_history_length"] == 2
    assert drained[1].tracklets == ()
    assert drained[1].metadata["tracker_state_updated"] is False
    assert drained[1].metadata["latest_state_measurement_timestamp"] == pytest.approx(1.2)
    assert drained[1].metadata["last_arrival_timestamp"] == pytest.approx(1.35)
    assert resumed.tracklets[0].metadata["mot_history_length"] == 3
    assert resumed.metadata["oosm_measurement_ignored_count"] == 1


def test_historical_normal_and_oosm_retransmissions_are_duplicate_measurements() -> None:
    adapter = Scalable3DTerminalAdapter()
    adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.0,
            arrival_timestamp=1.05,
            frame_index=1,
        )
    )
    adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.2,
            arrival_timestamp=1.25,
            frame_index=2,
            center_offset_px=(4.0, 2.0),
        )
    )

    with pytest.raises(ValueError, match="duplicate camera scan measurement timestamp"):
        adapter.adapt_batch(
            _timed_projected_batch(
                0,
                measurement_timestamp=1.0,
                arrival_timestamp=1.35,
                frame_index=3,
            )
        )

    oosm = adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.1,
            arrival_timestamp=1.45,
            frame_index=4,
            center_offset_px=(2.0, 1.0),
        )
    )
    with pytest.raises(ValueError, match="duplicate camera scan measurement timestamp"):
        adapter.adapt_batch(
            _timed_projected_batch(
                0,
                measurement_timestamp=1.1,
                arrival_timestamp=1.55,
                frame_index=5,
                center_offset_px=(2.0, 1.0),
            )
        )

    recovered = adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.3,
            arrival_timestamp=1.65,
            frame_index=6,
            center_offset_px=(6.0, 3.0),
        )
    )
    assert oosm.status == "oosm_ignored"
    assert oosm.metadata["oosm_measurement_ignored_count"] == 1
    assert recovered.tracklets[0].metadata["mot_history_length"] == 3
    assert recovered.metadata["oosm_measurement_ignored_count"] == 1


@pytest.mark.parametrize(
    ("invalid_batches", "message"),
    [
        (
            (
                (1.1, 1.20, 2),
                (1.2, 1.20, 3),
            ),
            "duplicate camera scan arrival timestamp",
        ),
        (
            (
                (0.9, 1.05, 2),
                (1.1, 1.20, 3),
            ),
            "arrival timestamps must not regress",
        ),
        (
            (
                (1.1, 1.20, 2),
                (1.1, 1.30, 3),
            ),
            "duplicate camera scan measurement timestamp",
        ),
    ],
)
def test_multibatch_timestamp_failure_is_atomic(
    invalid_batches: tuple[tuple[float, float, int], ...],
    message: str,
) -> None:
    adapter = Scalable3DTerminalAdapter()
    first = adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.0,
            arrival_timestamp=1.10,
            frame_index=1,
        )
    )
    batches = tuple(
        _timed_projected_batch(
            0,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_index=frame_index,
            center_offset_px=(2.0, 1.0),
        )
        for measurement_timestamp, arrival_timestamp, frame_index in invalid_batches
    )

    with pytest.raises(ValueError, match=message):
        adapter.adapt_batches(batches)

    recovered = adapter.adapt_batch(
        _timed_projected_batch(
            0,
            measurement_timestamp=1.1,
            arrival_timestamp=1.40,
            frame_index=4,
            center_offset_px=(4.0, 2.0),
        )
    )
    assert first.tracklets[0].local_track_id == recovered.tracklets[0].local_track_id
    assert recovered.tracklets[0].metadata["mot_history_length"] == 2
    assert recovered.metadata["oosm_measurement_ignored_count"] == 0


def test_multicamera_multibatch_processing_is_deterministic_and_stream_local() -> None:
    batches = (
        _timed_projected_batch(
            0,
            measurement_timestamp=2.1,
            arrival_timestamp=2.30,
            frame_index=2,
            center_offset_px=(5.0, 2.0),
        ),
        _timed_projected_batch(
            1,
            measurement_timestamp=2.0,
            arrival_timestamp=2.05,
            frame_index=1,
        ),
        _timed_projected_batch(
            1,
            measurement_timestamp=2.1,
            arrival_timestamp=2.20,
            frame_index=2,
            center_offset_px=(-3.0, 1.0),
        ),
        _timed_projected_batch(
            0,
            measurement_timestamp=2.0,
            arrival_timestamp=2.10,
            frame_index=1,
        ),
    )

    forward = Scalable3DTerminalAdapter().process(batches, _center_tracks())
    reverse = Scalable3DTerminalAdapter().process(tuple(reversed(batches)), _center_tracks())

    def signature(result: object) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                batch.resource_id,
                batch.camera_id,
                batch.measurement_timestamp,
                batch.arrival_timestamp,
                batch.tracklets[0].local_track_id,
                batch.tracklets[0].metadata["mot_history_length"],
            )
            for batch in result.camera_batches
        )

    assert signature(forward) == signature(reverse)
    assert [batch.arrival_timestamp for batch in forward.camera_batches] == [
        2.05,
        2.10,
        2.20,
        2.30,
    ]
    assert [
        batch.tracklets[0].metadata["mot_history_length"]
        for batch in forward.camera_batches
    ] == [1, 1, 2, 2]
    assert len(forward.tracklets) == forward.association.graph.node_count == 2
    assert {tracklet.camera_key for tracklet in forward.tracklets} == {
        "RESOURCE-0/CAM-0",
        "RESOURCE-1/CAM-1",
    }
    assert {tracklet.local_track_id for tracklet in forward.tracklets} == {"trk-000001"}
    assert len(forward.camera_geometries) == 2


def test_arrival_timestamp_regression_fails_before_tracker_state_update() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))

    def scan(
        measurement_timestamp: float,
        arrival_timestamp: float,
        frame_index: int,
    ) -> SimpleNamespace:
        return _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=centers[0],
                    bbox=boxes[0],
                    timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    frame_index=frame_index,
                    detection_index=0,
                ),
            ),
            timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_index=frame_index,
        )

    first = adapter.adapt_batch(scan(2.0, 2.20, 1))
    with pytest.raises(ValueError, match="arrival timestamps must not regress"):
        adapter.adapt_batch(scan(2.1, 2.15, 2))
    recovered = adapter.adapt_batch(scan(2.1, 2.30, 3))

    assert first.tracklets[0].local_track_id == recovered.tracklets[0].local_track_id
    assert recovered.tracklets[0].metadata["mot_history_length"] == 2
    assert recovered.metadata["oosm_measurement_ignored_count"] == 0


def test_duplicate_arrival_and_measurement_fail_closed_before_state_update() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))

    def scan(
        measurement_timestamp: float,
        arrival_timestamp: float,
        frame_index: int,
    ) -> SimpleNamespace:
        return _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=centers[0],
                    bbox=boxes[0],
                    timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    frame_index=frame_index,
                    detection_index=0,
                ),
            ),
            timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_index=frame_index,
        )

    original = scan(3.0, 3.10, 1)
    first = adapter.adapt_batch(original)
    with pytest.raises(ValueError, match="duplicate camera scan arrival timestamp"):
        adapter.adapt_batch(original)
    with pytest.raises(ValueError, match="duplicate camera scan measurement timestamp"):
        adapter.adapt_batch(scan(3.0, 3.20, 2))
    recovered = adapter.adapt_batch(scan(3.1, 3.30, 3))

    assert first.tracklets[0].local_track_id == recovered.tracklets[0].local_track_id
    assert recovered.tracklets[0].metadata["mot_history_length"] == 2
    assert recovered.metadata["oosm_measurement_ignored_count"] == 0


def test_false_alarm_miss_and_empty_scan_do_not_relabel_surviving_track() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))
    false_center = np.array([80.0, 80.0])
    false_bbox = np.array([70.0, 70.0, 90.0, 90.0])
    first = adapter.adapt_batch(
        _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=centers[0],
                    bbox=boxes[0],
                    timestamp=2.0,
                    frame_index=1,
                    detection_index=0,
                ),
                _measurement(
                    camera_index=0,
                    center=false_center,
                    bbox=false_bbox,
                    timestamp=2.0,
                    frame_index=1,
                    detection_index=1,
                    confidence=0.15,
                ),
            ),
            timestamp=2.0,
            frame_index=1,
        )
    )
    real_first = min(first.tracklets, key=lambda item: np.linalg.norm(item.center_px - centers[0]))
    second_center = centers[0] + np.array([2.0, 1.0])
    second_bbox = boxes[0] + np.array([2.0, 1.0, 2.0, 1.0])
    second = adapter.adapt_batch(
        _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=second_center,
                    bbox=second_bbox,
                    timestamp=2.1,
                    frame_index=2,
                    detection_index=0,
                ),
            ),
            timestamp=2.1,
            frame_index=2,
        )
    )
    empty = adapter.adapt_batch(
        _batch(0, (), timestamp=2.2, frame_index=3)
    )
    recovered = adapter.adapt_batch(
        _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=second_center + np.array([2.0, 1.0]),
                    bbox=second_bbox + np.array([2.0, 1.0, 2.0, 1.0]),
                    timestamp=2.3,
                    frame_index=4,
                    detection_index=0,
                ),
            ),
            timestamp=2.3,
            frame_index=4,
        )
    )
    association = run_scalable_3d_online_association(
        first.tracklets,
        (first.camera_geometry,),
        global_tracks3d_to_projection_tracks(_center_tracks()),
    )

    assert len(second.tracklets) == 1
    assert second.tracklets[0].local_track_id == real_first.local_track_id
    assert empty.status == "empty_geometry_unavailable"
    assert empty.tracklets == ()
    assert empty.camera_geometry is None
    assert recovered.tracklets[0].local_track_id == real_first.local_track_id
    assert any(binding.decision_state == "unbound" for binding in association.bindings)
    assert {
        binding.global_track_id
        for binding in association.bindings
        if binding.global_track_id is not None
    }.issubset({track.global_track_id for track in _center_tracks()})


@pytest.mark.parametrize(
    ("location", "value"),
    [
        ("metadata_truth_id", "safe-looking-value"),
        ("metadata_actor_id", "safe-looking-value"),
        ("metadata_object_name", "safe-looking-value"),
        ("metadata_target_id", "safe-looking-value"),
        ("metadata_alias", "TGT-0001"),
        ("observation_id", "TargetDrone_1"),
        ("batch_id", "intruder-003"),
    ],
)
def test_truth_fields_and_truth_like_identifiers_fail_before_tracker_update(
    location: str,
    value: str,
) -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))
    metadata_updates: dict[str, object] = {}
    observation_id = None
    batch_id = None
    if location.startswith("metadata_"):
        metadata_updates[location.removeprefix("metadata_")] = value
    elif location == "observation_id":
        observation_id = value
    else:
        batch_id = value
    contaminated_measurement = _measurement(
        camera_index=0,
        center=centers[0],
        bbox=boxes[0],
        timestamp=3.0,
        frame_index=1,
        detection_index=0,
        observation_id=observation_id,
        metadata_updates=metadata_updates,
    )
    contaminated_batch = _batch(
        0,
        (contaminated_measurement,),
        timestamp=3.0,
        frame_index=1,
        batch_id=batch_id,
    )

    with pytest.raises(ValueError, match="identity|truth-like"):
        adapter.adapt_batch(contaminated_batch)

    clean = adapter.adapt_batch(_projected_batch(0, (1,), timestamp=3.0, frame_index=1))
    assert clean.tracklets[0].local_track_id == "trk-000001"


def test_center_six_state_adapter_copies_state_and_preserves_global_id() -> None:
    source = GlobalTrack3D(
        global_track_id="GT-ACTUAL-0001",
        state=np.concatenate((POINTS[0], np.array([4.0, -1.0, 0.5]))),
        covariance=np.eye(6) * 4.0,
        timestamp=10.0,
    )
    source_id = source.global_track_id
    source_state = source.state.copy()
    source_covariance = source.covariance.copy()

    adapted = global_track3d_to_projection_track(source)

    assert adapted.global_track_id == source_id
    assert adapted.position == pytest.approx(source_state[:3])
    assert adapted.velocity == pytest.approx(source_state[3:])
    assert adapted.covariance == pytest.approx(source_covariance[:3, :3])
    assert adapted.track_version == 0
    adapted.position[0] += 100.0
    assert source.state == pytest.approx(source_state)
    assert source.global_track_id == source_id


def test_episode_reset_restarts_only_anonymous_local_namespace_and_clears_geometry() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (1,))
    first = adapter.adapt_batch(_projected_batch(0, (1,), timestamp=4.0, frame_index=1))
    far_center = centers[0] + np.array([300.0, 200.0])
    far_bbox = boxes[0] + np.array([300.0, 200.0, 300.0, 200.0])
    second = adapter.adapt_batch(
        _batch(
            0,
            (
                _measurement(
                    camera_index=0,
                    center=far_center,
                    bbox=far_bbox,
                    timestamp=4.1,
                    frame_index=2,
                    detection_index=0,
                ),
            ),
            timestamp=4.1,
            frame_index=2,
        )
    )
    assert first.tracklets[0].local_track_id == "trk-000001"
    assert second.tracklets[0].local_track_id == "trk-000002"

    adapter.reset_episode()
    empty = adapter.adapt_batch(_batch(0, (), timestamp=0.0, frame_index=0))
    empty_with_geometry = adapter.adapt_batch(
        _batch(
            0,
            (),
            timestamp=0.05,
            frame_index=0,
            include_camera_metadata=True,
        )
    )
    restarted = adapter.adapt_batch(_projected_batch(0, (1,), timestamp=0.1, frame_index=1))

    assert empty.status == "empty_geometry_unavailable"
    assert empty.camera_geometry is None
    assert empty_with_geometry.status == "empty"
    assert empty_with_geometry.camera_geometry is not None
    assert restarted.tracklets[0].local_track_id == "trk-000001"


def test_model_missing_and_low_confidence_use_explicit_rule_fallback() -> None:
    adapter = Scalable3DTerminalAdapter()
    step = adapter.process(
        [_projected_batch(0, (1,)), _projected_batch(1, (1,))],
        _center_tracks(),
    )
    assert step.association.graph.edge_count == 1
    assert step.association.scoring_status == "rule_fallback_model_missing"

    class LowConfidenceModel:
        def forward_graph(self, graph: object) -> np.ndarray:
            return np.full(getattr(graph, "edge_count"), 0.5)

    low = run_scalable_3d_online_association(
        step.tracklets,
        step.camera_geometries,
        step.center_projection_tracks,
        edge_model=LowConfidenceModel(),
    )
    assert low.scoring_status == "rule_fallback_low_confidence"
    assert low.probability_source == "deterministic_geometry_rule"

    class LoadedModel:
        def forward_graph(self, graph: object) -> np.ndarray:
            return np.full(getattr(graph, "edge_count"), 0.95)

    loaded = run_scalable_3d_online_association(
        step.tracklets,
        step.camera_geometries,
        step.center_projection_tracks,
        edge_model=LoadedModel(),
    )
    assert loaded.scoring_status == "model_scored"
    assert loaded.probability_source == "loaded_edge_model"


def test_real_online_sensor_batch_shape_uses_anonymous_id_and_covariance_fallback() -> None:
    centers, boxes = _projected_boxes(0, (1,))
    metadata = _camera_metadata(0)
    metadata.pop("position_covariance_ned")
    metadata.pop("attitude_covariance_rad2")
    covariance = np.zeros((6, 6), dtype=float)
    covariance[:2, :2] = np.eye(2) * 0.64
    covariance[2:, 2:] = np.eye(4) * 4.0
    measurement = SensorMeasurement(
        observation_id="vision-s000001-cam-int-0001-d0000",
        sensor_id="CAM-INT-0001",
        modality="vision_bbox",
        measurement_timestamp=5.0,
        arrival_timestamp=5.08,
        frame_id="cam-int-0001_optical_frame",
        measurement=np.concatenate((centers[0], boxes[0])),
        covariance=covariance,
        confidence=0.9,
        classification_hint="unmanned_aircraft",
        metadata=metadata,
    )
    batch = OnlineSensorBatch(
        batch_id="cam-int-0001-scan-5.0",
        sensor_id="CAM-INT-0001",
        measurement_timestamp=5.0,
        arrival_timestamp=5.08,
        measurements=(measurement,),
    )

    result = Scalable3DTerminalAdapter().adapt_batch(batch)

    assert result.resource_id == "INT-0001"
    assert result.camera_id == "CAM-INT-0001"
    assert result.tracklets[0].local_track_id == "trk-000001"
    assert result.metadata["position_covariance_source"] == "configured_fallback"
    assert result.metadata["attitude_covariance_source"] == "configured_fallback"


def test_adapter_module_has_no_main_d2_or_optional_graph_imports() -> None:
    source = inspect.getsource(adapter_module)
    assert "scalable_3d_simulation" not in source
    assert "d2_data_association" not in source
    assert "torch_geometric" not in source
    assert "OfflineTruthLabel" not in source
    assert "WorldSnapshot" not in source
    assert "local_track_id=detection.source_observation_id" not in source
    assert "global_track_id=detection.source_observation_id" not in source


def test_source_observation_link_is_one_to_one_and_does_not_drive_tracker_identity() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (0, 1))
    measurements = tuple(
        _measurement(
            camera_index=0,
            center=centers[index],
            bbox=boxes[index],
            timestamp=6.0,
            frame_index=1,
            detection_index=index,
            observation_id=f"source-measurement-{index}",
        )
        for index in range(2)
    )
    result = adapter.process(
        (_batch(0, measurements, timestamp=6.0, frame_index=1),),
        _center_tracks(),
    )

    links = result.source_observation_links
    assert {item.source_observation_id for item in links} == {
        "source-measurement-0",
        "source-measurement-1",
    }
    assert {item.tracklet_key for item in links} == {
        item.tracklet_key for item in result.tracklets
    }
    assert all(
        tracklet.local_track_id != tracklet.source_observation_id
        for tracklet in result.tracklets
    )
    assert result.association.graph.node_features.shape[0] == len(result.tracklets)


def test_duplicate_source_observation_is_rejected_before_tracker_state_changes() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (0, 1))
    duplicated = tuple(
        _measurement(
            camera_index=0,
            center=centers[index],
            bbox=boxes[index],
            timestamp=7.0,
            frame_index=1,
            detection_index=index,
            observation_id="same-source-observation",
        )
        for index in range(2)
    )

    with pytest.raises(ValueError, match="only one detection per frame"):
        adapter.adapt_batch(_batch(0, duplicated, timestamp=7.0, frame_index=1))
    clean = adapter.adapt_batch(
        _batch(0, (duplicated[0],), timestamp=7.0, frame_index=1)
    )
    assert clean.tracklets[0].local_track_id == "trk-000001"


def test_source_observation_cannot_map_to_two_cameras_in_the_same_frame() -> None:
    adapter = Scalable3DTerminalAdapter()
    batches = []
    for camera_index in (0, 1):
        centers, boxes = _projected_boxes(camera_index, (0,))
        measurement = _measurement(
            camera_index=camera_index,
            center=centers[0],
            bbox=boxes[0],
            timestamp=7.5,
            frame_index=1,
            detection_index=0,
            observation_id="cross-camera-duplicate-source",
        )
        batches.append(
            _batch(
                camera_index,
                (measurement,),
                timestamp=7.5,
                frame_index=1,
            )
        )

    with pytest.raises(ValueError, match="only one tracklet per frame"):
        adapter.adapt_batches(batches)
    clean = adapter.adapt_batch(batches[0])
    assert clean.tracklets[0].local_track_id == "trk-000001"


def test_offline_observation_join_marks_unlabeled_false_alarm_incomplete() -> None:
    adapter = Scalable3DTerminalAdapter()
    centers, boxes = _projected_boxes(0, (0,))
    real = _measurement(
        camera_index=0,
        center=centers[0],
        bbox=boxes[0],
        timestamp=8.0,
        frame_index=1,
        detection_index=0,
        observation_id="observation-with-label",
    )
    false_alarm = _measurement(
        camera_index=0,
        center=np.array([80.0, 80.0]),
        bbox=np.array([70.0, 70.0, 90.0, 90.0]),
        timestamp=8.0,
        frame_index=1,
        detection_index=1,
        observation_id="false-alarm-without-label",
        confidence=0.1,
    )
    result = adapter.process(
        (_batch(0, (real, false_alarm), timestamp=8.0, frame_index=1),),
        _center_tracks(),
    )
    joined = join_offline_observation_labels(
        result.association.graph,
        (
            SimpleNamespace(
                observation_id="observation-with-label",
                truth_entity_id="EVALUATOR-ENTITY-1",
                measurement_timestamp=8.0,
            ),
        ),
    )

    assert joined.labels_complete is False
    assert len(joined.tracklet_labels) == 1
    assert len(joined.missing_tracklet_keys) == 1
    assert joined.unmatched_observation_ids == ()
    labeled_tracklet = next(
        item
        for item in result.tracklets
        if item.source_observation_id == "observation-with-label"
    )
    assert joined.tracklet_labels[0].tracklet_key == labeled_tracklet.tracklet_key
    assert joined.tracklet_labels[0].truth_entity_id == "EVALUATOR-ENTITY-1"


def test_repeated_center_snapshot_reuses_only_content_equivalent_projection_tracks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Scalable3DTerminalAdapter()
    source_tracks = _center_tracks()
    original = adapter_module.global_tracks3d_to_projection_tracks
    conversion_count = 0

    def counted_conversion(tracks: object) -> object:
        nonlocal conversion_count
        conversion_count += 1
        return original(tracks)

    monkeypatch.setattr(
        adapter_module,
        "global_tracks3d_to_projection_tracks",
        counted_conversion,
    )
    first = adapter.process(
        (
            _timed_projected_batch(
                0,
                measurement_timestamp=10.0,
                arrival_timestamp=10.05,
                frame_index=1,
            ),
        ),
        source_tracks,
    )
    second = adapter.process(
        (
            _timed_projected_batch(
                0,
                measurement_timestamp=10.1,
                arrival_timestamp=10.15,
                frame_index=2,
            ),
        ),
        source_tracks,
    )

    assert conversion_count == 1
    assert second.center_projection_tracks is first.center_projection_tracks

    source_tracks[0].state[0] += 2.0
    third = adapter.process(
        (
            _timed_projected_batch(
                0,
                measurement_timestamp=10.2,
                arrival_timestamp=10.25,
                frame_index=3,
            ),
        ),
        source_tracks,
    )
    assert conversion_count == 2
    assert third.center_projection_tracks is not second.center_projection_tracks
    assert third.center_projection_tracks[0].position[0] == pytest.approx(
        second.center_projection_tracks[0].position[0] + 2.0
    )

    adapter.reset_episode()
    adapter.process(
        (
            _timed_projected_batch(
                0,
                measurement_timestamp=10.3,
                arrival_timestamp=10.35,
                frame_index=4,
            ),
        ),
        source_tracks,
    )
    assert conversion_count == 3


def test_online_association_reuses_build_projection_distances_for_center_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = graph_module._center_projection_distance_matrix
    projection_call_count = 0

    def counted_projection(*args: object, **kwargs: object) -> np.ndarray:
        nonlocal projection_call_count
        projection_call_count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        graph_module,
        "_center_projection_distance_matrix",
        counted_projection,
    )
    result = Scalable3DTerminalAdapter().process(
        (
            _projected_batch(0, PARTIAL_VISIBILITY[0]),
            _projected_batch(1, PARTIAL_VISIBILITY[1]),
        ),
        _center_tracks(),
    )

    assert projection_call_count == 1
    assert {
        item.global_track_id
        for item in result.association.bindings
        if item.global_track_id is not None
    } == {"GT-0000", "GT-0001", "GT-0002"}
