from __future__ import annotations

from dataclasses import asdict
import math

import numpy as np

from dual_optical_40target.core import (
    AnonymousDetection,
    CameraSpec,
    CameraState,
    ScanRevisitTracker,
    ScenarioConfig,
    associate_tracks,
    generate_target_specs,
    look_angles_deg,
    minimum_target_separation,
    online_truth_leakage_keys,
    pixel_to_world_ray,
    project_world_point,
    ray_observation_from_detection,
    scan_yaw_deg,
    sweep_index,
)


def test_camera_projection_round_trip_and_spec_difference() -> None:
    camera = CameraSpec()
    state = CameraState(
        camera_id="A",
        frame_index=0,
        timestamp=0.0,
        position_ned=(0.0, -1000.0, -100.0),
        yaw_deg=26.565051,
        pitch_deg=0.0,
    )
    point = (2000.0, 0.0, -90.0)
    pixel = project_world_point(point, state, camera)
    assert pixel is not None
    ray = np.asarray(pixel_to_world_ray(pixel, state, camera))
    expected = np.asarray(point) - np.asarray(state.position_ned)
    expected /= np.linalg.norm(expected)
    assert np.allclose(ray, expected, atol=1e-10)
    assert math.isclose(camera.vertical_fov_deg, 2.344, abs_tol=0.01)
    assert not math.isclose(camera.effective_ifov_mrad, camera.stated_ifov_mrad)


def test_scan_is_yaw_only_with_one_second_round_trip() -> None:
    base = 20.0
    assert math.isclose(scan_yaw_deg(0.0, base), -25.0)
    assert math.isclose(scan_yaw_deg(0.25, base), 20.0)
    assert math.isclose(scan_yaw_deg(0.5, base), 65.0)
    assert math.isclose(scan_yaw_deg(0.75, base), 20.0)
    assert math.isclose(scan_yaw_deg(1.0, base), -25.0)
    assert [sweep_index(value) for value in (0.0, 0.49, 0.5, 0.99, 1.0)] == [0, 0, 1, 1, 2]


def test_target_generator_is_irregular_fast_and_separated() -> None:
    config = ScenarioConfig()
    targets = generate_target_specs(config)
    assert len(targets) == 40
    assert all(math.isclose(target.speed_mps, 50.0, abs_tol=1e-9) for target in targets)
    assert minimum_target_separation(targets, config.duration_s) >= 25.0
    assert len({round(target.start_ned[0], 3) for target in targets}) == 40
    assert any(target.velocity_ned[1] > 0.0 for target in targets)
    assert any(target.velocity_ned[1] < 0.0 for target in targets)


def test_online_schema_rejects_truth_fields() -> None:
    clean = {
        "detection_uid": "A-F00001-D000",
        "camera_id": "A",
        "bbox_xyxy": [1.0, 2.0, 3.0, 4.0],
        "camera_position_ned": [0.0, 0.0, -100.0],
    }
    assert online_truth_leakage_keys([clean]) == ()
    leaked = clean | {"actor_name": "target", "nested": {"box3d": {}}}
    assert len(online_truth_leakage_keys([leaked])) == 2


def test_ideal_projection_forms_correct_one_to_one_matches() -> None:
    config = ScenarioConfig()
    camera = CameraSpec()
    targets = generate_target_specs(config)
    trackers = {
        camera_id: ScanRevisitTracker(camera_id, max_coast_s=config.track_coast_s)
        for camera_id in config.camera_positions
    }
    uid_truth: dict[str, str] = {}
    for frame_index in range(config.frame_count):
        timestamp = frame_index * config.dt_s
        current_sweep = sweep_index(timestamp, period_s=config.scan_period_s)
        for camera_id, position in config.camera_positions.items():
            base_yaw, fixed_pitch = look_angles_deg(position, config.corridor_center_ned)
            state = CameraState(
                camera_id=camera_id,
                frame_index=frame_index,
                timestamp=timestamp,
                position_ned=position,
                yaw_deg=scan_yaw_deg(timestamp, base_yaw),
                pitch_deg=fixed_pitch,
            )
            observations = []
            for target in targets:
                point = target.position_at(timestamp)
                pixel = project_world_point(point, state, camera)
                if pixel is None or not (
                    0.0 <= pixel[0] < camera.width
                    and 0.0 <= pixel[1] < camera.height
                ):
                    continue
                distance = math.dist(position, point)
                extent = max(4.0, camera.focal_length_px * 3.0 / distance)
                uid = f"{camera_id}-F{frame_index:05d}-D{len(observations):03d}"
                detection = AnonymousDetection(
                    detection_uid=uid,
                    camera_id=camera_id,
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp,
                    bbox_xyxy=(
                        pixel[0] - extent * 0.5,
                        pixel[1] - extent * 0.5,
                        pixel[0] + extent * 0.5,
                        pixel[1] + extent * 0.5,
                    ),
                    center_px=pixel,
                    confidence=1.0,
                )
                observations.append(
                    ray_observation_from_detection(
                        detection, state, camera, scan_period_s=config.scan_period_s
                    )
                )
                uid_truth[uid] = target.truth_id
            trackers[camera_id].update(
                sweep_index=current_sweep,
                timestamp=timestamp,
                observations=observations,
            )
    for tracker in trackers.values():
        tracker.flush()
    tracks_a = trackers[config.camera_a_name].stable_tracks(config.stable_sweep_count)
    tracks_b = trackers[config.camera_b_name].stable_tracks(config.stable_sweep_count)
    result = associate_tracks(tracks_a, tracks_b)

    def majority(track) -> str:
        values = [uid_truth[uid] for uid in track.detection_uids]
        return max(set(values), key=values.count)

    truth_a = {track.track_id: majority(track) for track in tracks_a}
    truth_b = {track.track_id: majority(track) for track in tracks_b}
    correct = sum(
        truth_a[match.track_a_id] == truth_b[match.track_b_id]
        for match in result.matches
    )
    assert correct == 40
    assert len(result.matches) == 40
    assert len({match.track_a_id for match in result.matches}) == 40
    assert len({match.track_b_id for match in result.matches}) == 40
    assert online_truth_leakage_keys(
        [asdict(match) for match in result.matches]
    ) == ()
