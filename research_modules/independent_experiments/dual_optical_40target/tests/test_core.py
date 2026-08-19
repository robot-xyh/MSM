from __future__ import annotations

from dataclasses import asdict
import math

import numpy as np

from dual_optical_40target.core import (
    AssociationConfig,
    AnonymousDetection,
    BearingSample,
    BearingTrack,
    CameraSpec,
    CameraState,
    CrossCameraCandidate,
    ScanRevisitTracker,
    ScenarioConfig,
    associate_tracks,
    associate_tracks_temporally,
    build_epipolar_evidence,
    _ambiguity_resolution,
    generate_target_specs,
    k_best_global_assignments,
    look_angles_deg,
    minimum_target_separation,
    online_truth_leakage_keys,
    normalized_symmetric_coplanarity_mrad,
    pixel_to_world_ray,
    project_world_point,
    ray_observation_from_detection,
    scan_yaw_deg,
    sweep_index,
)


def _bearing_sample(
    camera_id: str,
    origin: tuple[float, float, float],
    point: tuple[float, float, float],
    timestamp: float,
) -> BearingSample:
    direction = np.asarray(point, dtype=float) - np.asarray(origin, dtype=float)
    direction /= np.linalg.norm(direction)
    return BearingSample(
        camera_id=camera_id,
        sweep_index=int(round(timestamp * 2.0)),
        timestamp=timestamp,
        origin_ned=origin,
        direction_ned=tuple(float(value) for value in direction),
        detection_uids=(f"{camera_id}-{timestamp:.2f}",),
        focal_length_px=25_000.0,
        bbox_area_px2=4.0,
    )


def _moving_track(
    track_id: str,
    camera_id: str,
    origin: tuple[float, float, float],
    start: tuple[float, float, float],
    velocity: tuple[float, float, float],
    timestamps: list[float],
) -> BearingTrack:
    return BearingTrack(
        track_id=track_id,
        camera_id=camera_id,
        samples=[
            _bearing_sample(
                camera_id,
                origin,
                tuple(
                    float(value)
                    for value in np.asarray(start) + np.asarray(velocity) * timestamp
                ),
                timestamp,
            )
            for timestamp in timestamps
        ],
    )


def _candidate(track_a_id: str, track_b_id: str, cost: float) -> CrossCameraCandidate:
    return CrossCameraCandidate(
        track_a_id=track_a_id,
        track_b_id=track_b_id,
        valid=True,
        rejection_reason="",
        cost=cost,
        reprojection_rms_px=1.0,
        reprojection_max_px=1.0,
        ray_residual_rms_m=0.1,
        fitted_speed_mps=50.0,
        median_nearest_time_delta_s=0.0,
        condition_number=10.0,
        observation_count=8,
        inlier_count=8,
        outlier_count=0,
        reference_timestamp=1.0,
        position_ned=(2000.0, 0.0, -100.0),
        velocity_ned=(-50.0, 0.0, 0.0),
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


def test_ray_observation_uses_global_clock_at_two_second_boundaries() -> None:
    camera = CameraSpec()
    for frame_index, (timestamp, expected_sweep) in enumerate(
        ((0.0, 0), (1.0, 0), (2.0, 1))
    ):
        state = CameraState(
            camera_id="Optical_B",
            frame_index=frame_index,
            timestamp=timestamp,
            position_ned=(0.0, 1000.0, -100.0),
            yaw_deg=180.0,
            pitch_deg=0.0,
        )
        detection = AnonymousDetection(
            detection_uid=f"B-{frame_index}",
            camera_id="Optical_B",
            frame_index=frame_index,
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.001,
            bbox_xyxy=(630.0, 502.0, 650.0, 522.0),
            center_px=(640.0, 512.0),
            confidence=1.0,
        )

        observation = ray_observation_from_detection(
            detection,
            state,
            camera,
            scan_period_s=2.0,
            scan_mode="continuous_360",
        )

        assert observation.timestamp == timestamp
        assert observation.sweep_index == expected_sweep


def test_target_generator_is_irregular_fast_and_separated() -> None:
    config = ScenarioConfig()
    targets = generate_target_specs(config)
    assert len(targets) == 40
    assert all(math.isclose(target.speed_mps, 50.0, abs_tol=1e-9) for target in targets)
    assert minimum_target_separation(targets, config.duration_s) >= 25.0
    assert len({round(target.start_ned[0], 3) for target in targets}) == 40
    assert any(target.velocity_ned[1] > 0.0 for target in targets)
    assert any(target.velocity_ned[1] < 0.0 for target in targets)


def test_target_generator_supports_dynamic_n_and_100_target_scene() -> None:
    for target_count in (1, 41, 100):
        config = ScenarioConfig(target_count=target_count, seed=20260813)
        targets = generate_target_specs(config)

        assert len(targets) == target_count
        assert len({target.truth_id for target in targets}) == target_count
        assert len({target.actor_name for target in targets}) == target_count
        assert all(
            target.actor_name.startswith("MSM_DualOptical_S20260813_Target_")
            for target in targets
        )
        assert targets[-1].truth_id == f"TRUTH-{target_count:03d}"
        assert all(
            math.isclose(target.speed_mps, config.target_speed_mps, abs_tol=1e-9)
            for target in targets
        )


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


def test_symmetric_coplanarity_is_order_independent_and_rejects_zero_baseline() -> None:
    origin_a = (0.0, -1000.0, -100.0)
    origin_b = (0.0, 1000.0, -100.0)
    point = np.asarray((2000.0, 30.0, -95.0))
    ray_a = point - np.asarray(origin_a)
    ray_b = point - np.asarray(origin_b)
    residual_ab, angle_ab = normalized_symmetric_coplanarity_mrad(
        origin_a, ray_a, origin_b, ray_b
    )
    residual_ba, angle_ba = normalized_symmetric_coplanarity_mrad(
        origin_b, ray_b, origin_a, ray_a
    )
    assert residual_ab < 1e-9
    assert math.isclose(residual_ab, residual_ba, abs_tol=1e-12)
    assert math.isclose(angle_ab, angle_ba, abs_tol=1e-12)
    with np.testing.assert_raises(ValueError):
        normalized_symmetric_coplanarity_mrad(origin_a, ray_a, origin_a, ray_b)


def test_epipolar_sequence_interpolates_asynchronous_tracks() -> None:
    start = (2000.0, 20.0, -100.0)
    velocity = (-50.0, 0.0, 0.0)
    track_a = _moving_track(
        "A-T1",
        "A",
        (0.0, -1000.0, -100.0),
        start,
        velocity,
        [0.0, 0.5, 1.0, 1.5, 2.0],
    )
    track_b = _moving_track(
        "B-T1",
        "B",
        (0.0, 1000.0, -100.0),
        start,
        velocity,
        [0.1, 0.6, 1.1, 1.6, 2.1],
    )
    evidence = build_epipolar_evidence(track_a, track_b)
    assert evidence.gate_passed is True
    assert evidence.aligned_sample_count >= 4
    assert evidence.residual_median_mrad < 0.01
    assert evidence.timestamps_s == tuple(sorted(evidence.timestamps_s))


def test_k_best_assignments_are_unique_and_one_to_one() -> None:
    tracks_a = (BearingTrack("A1", "A"), BearingTrack("A2", "A"))
    tracks_b = (BearingTrack("B1", "B"), BearingTrack("B2", "B"))
    candidates = (
        _candidate("A1", "B1", 0.10),
        _candidate("A1", "B2", 0.20),
        _candidate("A2", "B1", 0.20),
        _candidate("A2", "B2", 0.10),
    )
    hypotheses = k_best_global_assignments(
        tracks_a,
        tracks_b,
        candidates,
        config=AssociationConfig(top_k=5),
    )
    signatures = {hypothesis.matches for hypothesis in hypotheses}
    assert len(signatures) == len(hypotheses) == 5
    assert hypotheses[0].matches == (("A1", "B1"), ("A2", "B2"))
    assert math.isclose(
        sum(item.normalized_support for item in hypotheses), 1.0, abs_tol=1e-12
    )
    for hypothesis in hypotheses:
        assert len({pair[0] for pair in hypothesis.matches}) == len(hypothesis.matches)
        assert len({pair[1] for pair in hypothesis.matches}) == len(hypothesis.matches)


def test_crossing_relations_wait_then_confirm_after_separation() -> None:
    timestamps = [0.5 * index for index in range(13)]
    camera_a = (0.0, -1000.0, -100.0)
    camera_b = (0.0, 1000.0, -100.0)
    starts = ((2200.0, -20.0, -100.0), (2200.0, 20.0, -100.0))
    velocities = ((-49.36, 8.0, 0.0), (-49.36, -8.0, 0.0))
    tracks_a = tuple(
        _moving_track(f"A-T{index}", "A", camera_a, start, velocity, timestamps)
        for index, (start, velocity) in enumerate(zip(starts, velocities), start=1)
    )
    tracks_b = tuple(
        _moving_track(f"B-T{index}", "B", camera_b, start, velocity, timestamps)
        for index, (start, velocity) in enumerate(zip(starts, velocities), start=1)
    )
    result = associate_tracks_temporally(tracks_a, tracks_b)
    assert len(result.selected_matches) == 2
    assert len(result.confirmed_matches) == 2
    assert result.candidate_screening_elapsed_ms >= 0.0
    assert result.candidate_fitting_elapsed_ms >= 0.0
    assert result.processing_elapsed_ms >= (
        result.candidate_screening_elapsed_ms
        + result.candidate_fitting_elapsed_ms
    )
    assert any(item.state == "pending" and item.crossing_alert for item in result.state_history)
    final_epoch = result.decisions[-1].epoch_index
    assert all(
        item.state == "confirmed"
        for item in result.state_history
        if item.epoch_index == final_epoch and (item.track_a_id, item.track_b_id) in result.hypotheses[0].matches
    )


def test_permanently_ambiguous_tracks_remain_pending_and_order_is_stable() -> None:
    timestamps = [0.5 * index for index in range(10)]
    camera_a = (0.0, -1000.0, -100.0)
    camera_b = (0.0, 1000.0, -100.0)
    start = (2200.0, 0.0, -100.0)
    velocity = (-50.0, 0.0, 0.0)
    tracks_a = tuple(
        _moving_track(f"A-T{index}", "A", camera_a, start, velocity, timestamps)
        for index in (1, 2)
    )
    tracks_b = tuple(
        _moving_track(f"B-T{index}", "B", camera_b, start, velocity, timestamps)
        for index in (1, 2)
    )
    first = associate_tracks_temporally(tracks_a, tracks_b)
    permuted = associate_tracks_temporally(tuple(reversed(tracks_a)), tuple(reversed(tracks_b)))
    assert first.hypotheses[0].matches == permuted.hypotheses[0].matches
    assert len(first.selected_matches) == 1
    assert len(first.fragment_suppressions) == 1
    assert first.confirmed_matches == ()
    final_epoch = first.decisions[-1].epoch_index
    selected = set(first.hypotheses[0].matches)
    assert all(
        item.state == "pending"
        for item in first.state_history
        if item.epoch_index == final_epoch
        and (item.track_a_id, item.track_b_id) in selected
    )
    assert online_truth_leakage_keys(
        [asdict(item) for item in first.selected_matches]
        + [asdict(item) for item in first.state_history]
    ) == ()


def test_ambiguity_resolution_waits_two_revolutions_and_requires_real_margin() -> None:
    config = AssociationConfig(
        ambiguity_resolution_revolutions=2,
        ambiguity_support_margin=0.10,
        ambiguity_cost_margin=0.05,
    )
    pair = ("A1", "B1")
    competitor = ("A1", "B2")
    common = {
        "pair": pair,
        "selected_pairs": {pair},
        "pair_supports": {pair: 0.8, competitor: 0.2},
        "smoothed_supports": {pair: 0.8, competitor: 0.2},
        "candidate_costs": {pair: 0.10, competitor: 0.30},
        "ambiguous": True,
        "config": config,
    }
    age, resolved, retained = _ambiguity_resolution(previous_age=0, **common)
    assert (age, resolved, retained) == (1, False, 2)
    age, resolved, retained = _ambiguity_resolution(previous_age=age, **common)
    assert (age, resolved, retained) == (2, True, 2)

    tied = dict(common)
    tied["smoothed_supports"] = {pair: 0.5, competitor: 0.5}
    tied["candidate_costs"] = {pair: 0.10, competitor: 0.10}
    assert _ambiguity_resolution(previous_age=4, **tied)[1] is False
