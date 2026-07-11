from __future__ import annotations

import numpy as np
import pytest

from d1_sensor_fusion.cooperative import (
    BearingLocalizationConfig,
    covariance_intersection,
    localize_bearing_observation_group,
)
from d1_sensor_fusion.types import (
    CooperativeBearingObservation,
    CooperativeObservationGroup,
    CooperativeTrackEstimate,
    ObserverLineage,
)


TARGET = np.array([120.0, 15.0, -20.0])
OBSERVER_POSITIONS = (
    np.array([0.0, -45.0, 0.0]),
    np.array([5.0, 50.0, -5.0]),
    np.array([35.0, 0.0, 15.0]),
    np.array([-30.0, 25.0, 5.0]),
    np.array([20.0, -60.0, -10.0]),
    np.array([10.0, 65.0, 12.0]),
)


def _bearing_observation(
    index: int,
    observer_position: np.ndarray,
    target_position: np.ndarray,
    *,
    measurement_timestamp: float = 1.0,
    arrival_timestamp: float | None = None,
    message_uuid: str | None = None,
    source_lineage: tuple[str, ...] | None = None,
    bearing_covariance: np.ndarray | None = None,
    platform_pose_covariance: np.ndarray | None = None,
    sensor_extrinsics_covariance: np.ndarray | None = None,
) -> CooperativeBearingObservation:
    direction = target_position - observer_position
    if arrival_timestamp is None:
        arrival_timestamp = measurement_timestamp + 0.1
    if bearing_covariance is None:
        bearing_covariance = np.eye(2) * np.deg2rad(0.15) ** 2
    if platform_pose_covariance is None:
        platform_pose_covariance = np.diag(
            [0.2**2] * 3 + [np.deg2rad(0.1) ** 2] * 3
        )
    if sensor_extrinsics_covariance is None:
        sensor_extrinsics_covariance = np.diag(
            [0.05**2] * 3 + [np.deg2rad(0.05) ** 2] * 3
        )
    return CooperativeBearingObservation(
        global_track_id="GT-CANONICAL-7",
        lineage=ObserverLineage(
            observer_id=f"observer-{index}",
            sensor_id=f"camera-{index}",
            observation_id=f"observation-{index}",
            message_uuid=message_uuid or f"message-{index}",
            source_lineage=source_lineage or (f"source-payload-{index}",),
        ),
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        platform_position_ned=observer_position,
        platform_rotation_body_to_ned=np.eye(3),
        sensor_translation_body=np.zeros(3),
        sensor_rotation_sensor_to_body=np.eye(3),
        bearing_unit_sensor=direction,
        bearing_covariance=bearing_covariance,
        platform_pose_covariance=platform_pose_covariance,
        sensor_extrinsics_covariance=sensor_extrinsics_covariance,
        timestamp_uncertainty_s=0.002,
    )


def _group(
    observations: tuple[CooperativeBearingObservation, ...],
    *,
    estimate_timestamp: float = 1.0,
    target_velocity_ned: np.ndarray | None = None,
) -> CooperativeObservationGroup:
    return CooperativeObservationGroup(
        global_track_id="GT-CANONICAL-7",
        estimate_timestamp=estimate_timestamp,
        observations=observations,
        target_velocity_ned=target_velocity_ned,
    )


@pytest.mark.parametrize("observer_count", [1, 2, 3, 6])
def test_bearing_localization_supports_one_two_three_and_n_observers(
    observer_count: int,
) -> None:
    observations = tuple(
        _bearing_observation(index, OBSERVER_POSITIONS[index], TARGET)
        for index in range(observer_count)
    )

    summary = localize_bearing_observation_group(_group(observations))

    assert summary.unique_observer_count == observer_count
    if observer_count == 1:
        assert not summary.accepted
        assert summary.geometry_reason == "insufficient_unique_observers"
    else:
        assert summary.accepted
        assert summary.information_rank == 3
        assert np.linalg.norm(summary.position_ned - TARGET) < 1e-6
        assert summary.to_dict()["global_track_id"] == "GT-CANONICAL-7"
        observation_payload = observations[0].to_dict()
        assert observation_payload["platform_pose_covariance"] is not None
        assert observation_payload["sensor_extrinsics_covariance"] is not None
        assert "truth_id" not in observation_payload


def test_good_three_view_geometry_is_not_worse_than_best_pair() -> None:
    observations = tuple(
        _bearing_observation(index, OBSERVER_POSITIONS[index], TARGET)
        for index in range(3)
    )
    pair_summaries = tuple(
        localize_bearing_observation_group(_group((observations[first], observations[second])))
        for first, second in ((0, 1), (0, 2), (1, 2))
    )
    triple = localize_bearing_observation_group(_group(observations))

    assert triple.accepted
    assert all(summary.accepted for summary in pair_summaries)
    assert np.linalg.norm(triple.position_ned - TARGET) <= min(
        np.linalg.norm(summary.position_ned - TARGET) for summary in pair_summaries
    ) + 1e-8
    assert np.trace(triple.position_covariance_ned) <= min(
        np.trace(summary.position_covariance_ned) for summary in pair_summaries
    ) + 1e-12


def test_near_collinear_geometry_is_rejected() -> None:
    first = _bearing_observation(0, np.array([0.0, 0.0, 0.0]), np.array([100.0, 0.0, 0.0]))
    second = _bearing_observation(1, np.array([0.0, 20.0, 0.0]), np.array([100.0, 20.0, 0.0]))

    summary = localize_bearing_observation_group(_group((first, second)))

    assert not summary.accepted
    assert summary.geometry_reason == "los_geometry_near_collinear"
    assert summary.los_intersection_angles[0].angle_deg == pytest.approx(0.0)


def test_async_bearings_propagate_to_common_estimate_time_and_inflate_covariance() -> None:
    estimate_timestamp = 1.0
    velocity = np.array([12.0, -3.0, 1.5])
    timestamps = (0.5, 0.7, 0.9)
    async_observations = tuple(
        _bearing_observation(
            index,
            OBSERVER_POSITIONS[index],
            TARGET - velocity * (estimate_timestamp - timestamp),
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.2,
        )
        for index, timestamp in enumerate(timestamps)
    )
    synchronous_observations = tuple(
        _bearing_observation(
            index,
            OBSERVER_POSITIONS[index],
            TARGET,
            measurement_timestamp=estimate_timestamp,
        )
        for index in range(3)
    )

    asynchronous = localize_bearing_observation_group(
        _group(
            async_observations,
            estimate_timestamp=estimate_timestamp,
            target_velocity_ned=velocity,
        )
    )
    synchronous = localize_bearing_observation_group(_group(synchronous_observations))

    assert asynchronous.accepted
    assert np.linalg.norm(asynchronous.position_ned - TARGET) < 1e-6
    assert asynchronous.measurement_timestamps == timestamps
    assert asynchronous.arrival_timestamps == pytest.approx((0.7, 0.9, 1.1))
    assert asynchronous.measurement_skew_s == pytest.approx(0.4)
    assert asynchronous.max_propagation_horizon_s == pytest.approx(0.5)
    assert asynchronous.covariance_inflation_trace > 0.0
    assert "time_process_covariance_inflated" in asynchronous.quality_flags
    assert np.trace(asynchronous.position_covariance_ned) > np.trace(
        synchronous.position_covariance_ned
    )


def test_time_skew_and_missing_covariance_are_conservatively_gated() -> None:
    first = _bearing_observation(0, OBSERVER_POSITIONS[0], TARGET, measurement_timestamp=0.0)
    late = _bearing_observation(1, OBSERVER_POSITIONS[1], TARGET, measurement_timestamp=1.0)
    skewed = localize_bearing_observation_group(
        _group((first, late), estimate_timestamp=1.0, target_velocity_ned=np.zeros(3))
    )
    complete = _bearing_observation(0, OBSERVER_POSITIONS[0], TARGET)
    missing = _bearing_observation(2, OBSERVER_POSITIONS[2], TARGET)
    object.__setattr__(missing, "platform_pose_covariance", None)
    rejected_missing = localize_bearing_observation_group(_group((complete, missing)))
    inflated_missing = localize_bearing_observation_group(
        _group((complete, missing)),
        BearingLocalizationConfig(incomplete_covariance_policy="inflate"),
    )

    assert skewed.geometry_reason == "measurement_skew_exceeds_limit"
    assert rejected_missing.geometry_reason == "covariance_incomplete"
    assert inflated_missing.accepted
    assert "incomplete_covariance_inflated" in inflated_missing.quality_flags


def _track_estimate(
    index: int,
    *,
    covariance: np.ndarray | None = None,
    estimate_timestamp: float = 2.0,
    measurement_timestamp: float | None = None,
    arrival_timestamp: float | None = None,
    message_uuid: str | None = None,
    source_lineage: tuple[str, ...] | None = None,
    global_track_id: str = "GT-CANONICAL-7",
) -> CooperativeTrackEstimate:
    if covariance is None:
        covariance = np.diag([4.0, 6.0, 8.0, 1.0, 1.5, 2.0])
    if measurement_timestamp is None:
        measurement_timestamp = estimate_timestamp - 0.1
    if arrival_timestamp is None:
        arrival_timestamp = estimate_timestamp + 0.1
    return CooperativeTrackEstimate(
        global_track_id=global_track_id,
        state=np.array([100.0 + index, 20.0, -10.0, 5.0, -1.0, 0.5]),
        covariance=covariance,
        estimate_timestamp=estimate_timestamp,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        message_uuid=message_uuid or f"track-message-{index}",
        source_lineage=source_lineage or (f"track-source-{index}",),
        timestamp_uncertainty_s=0.01,
    )


@pytest.mark.parametrize("source_count", [1, 2, 3, 7])
def test_covariance_intersection_supports_one_two_three_and_n_sources(
    source_count: int,
) -> None:
    result = covariance_intersection(_track_estimate(index) for index in range(source_count))

    assert result.accepted
    assert result.unique_source_count == source_count
    assert result.fused_estimate.global_track_id == "GT-CANONICAL-7"
    assert sum(item.weight for item in result.source_weights) == pytest.approx(1.0)


def test_duplicate_message_or_lineage_does_not_repeat_ci_convergence() -> None:
    original = _track_estimate(0)
    duplicate_message = _track_estimate(
        1,
        message_uuid=original.message_uuid,
        source_lineage=("relay-copy",),
    )
    duplicate_lineage = _track_estimate(
        2,
        message_uuid="different-relay-message",
        source_lineage=original.source_lineage,
    )

    result = covariance_intersection((original, duplicate_message, duplicate_lineage))

    assert result.accepted
    assert result.unique_source_count == 1
    assert result.duplicate_source_count == 2
    assert np.allclose(result.fused_estimate.state, original.state)
    expected = covariance_intersection((original,)).fused_estimate.covariance
    assert np.allclose(result.fused_estimate.covariance, expected)


def test_ci_is_no_more_confident_than_false_independent_fusion() -> None:
    first_covariance = np.diag([4.0, 9.0, 16.0, 1.0, 2.0, 3.0])
    second_covariance = np.diag([9.0, 4.0, 12.0, 2.0, 1.0, 4.0])
    first = _track_estimate(0, covariance=first_covariance)
    second = _track_estimate(1, covariance=second_covariance)

    result = covariance_intersection((first, second))
    independent_covariance = np.linalg.inv(
        np.linalg.inv(first_covariance) + np.linalg.inv(second_covariance)
    )

    assert result.accepted
    difference = result.fused_estimate.covariance - independent_covariance
    assert np.min(np.linalg.eigvalsh(0.5 * (difference + difference.T))) >= -1e-10


def test_ci_propagates_async_states_and_preserves_source_timestamps() -> None:
    first = _track_estimate(
        0,
        estimate_timestamp=1.0,
        measurement_timestamp=0.8,
        arrival_timestamp=1.2,
    )
    second = _track_estimate(
        1,
        estimate_timestamp=1.5,
        measurement_timestamp=1.4,
        arrival_timestamp=1.7,
    )

    result = covariance_intersection((first, second), estimate_timestamp=2.0)

    assert result.accepted
    assert result.fused_estimate.estimate_timestamp == 2.0
    assert result.fused_estimate.measurement_timestamp == 1.4
    assert result.fused_estimate.arrival_timestamp == 1.7
    assert result.source_measurement_timestamps == (0.8, 1.4)
    assert result.source_arrival_timestamps == (1.2, 1.7)
    assert result.fused_estimate.state[0] > first.state[0]


def test_ci_rejects_mixed_canonical_ids_without_rebinding() -> None:
    result = covariance_intersection(
        (_track_estimate(0), _track_estimate(1, global_track_id="GT-OTHER"))
    )

    assert not result.accepted
    assert result.reason == "global_track_id_mismatch"
    assert result.fused_estimate is None
