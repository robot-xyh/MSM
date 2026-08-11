from __future__ import annotations

import json

import numpy as np
import pytest

from d5_terminal_association import (
    AssociationConfig,
    CameraModel,
    GlobalTrack,
    LocalVisualTrack,
    TemporalGeometricAssociationConfig,
    TemporalGeometricAssociator,
)


def _camera(*, measurement_variance: float = 4.0) -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [100.0, 0.0, 320.0],
                [0.0, 100.0, 240.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([measurement_variance, measurement_variance]),
    )


def _global(global_track_id: str, projected_x_px: float) -> GlobalTrack:
    x_m = (projected_x_px - 320.0) * 20.0 / 100.0
    return GlobalTrack(
        global_track_id=global_track_id,
        position=np.array([x_m, 0.0, 20.0], dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        velocity=np.zeros(3),
        timestamp=0.0,
    )


def _local(
    local_track_id: str,
    center_x_px: float,
    timestamp: float,
    *,
    state: str = "measured",
    prediction_age_s: float | None = None,
    bearing_rate: tuple[float, float] = (0.0, 0.0),
    metadata: dict | None = None,
) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_track_id,
        center_px=np.array([center_x_px, 240.0], dtype=float),
        bbox=(center_x_px - 5.0, 235.0, center_x_px + 5.0, 245.0),
        bearing_rate=np.array(bearing_rate, dtype=float),
        quality=0.95,
        mot_history_length=5,
        timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        local_track_state=state,
        prediction_age_s=prediction_age_s,
        metadata=dict(metadata or {}),
    )


def _associate(
    associator: TemporalGeometricAssociator,
    globals_: list[GlobalTrack],
    locals_: list[LocalVisualTrack],
    timestamp: float,
    *,
    camera: CameraModel | None = None,
    resource_id: str = "R1",
    camera_id: str = "front",
    stream_id: str = "live",
    frame_id: str | None = None,
):
    return associator.associate(
        globals_,
        locals_,
        camera or _camera(),
        resource_id=resource_id,
        camera_id=camera_id,
        stream_id=stream_id,
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        frame_id=frame_id or f"frame-{timestamp:.3f}",
    )


@pytest.mark.parametrize("gap_s", [0.06, 0.10, 0.17])
def test_bounded_coast_predicts_center_bbox_and_covariance_then_recovers(gap_s: float) -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0)]
    initial = _associate(
        associator,
        globals_,
        [_local("anon-1", 320.0, 1.0, bearing_rate=(20.0, -10.0))],
        1.0,
    )
    coast = _associate(associator, globals_, [], 1.0 + gap_s)

    assert initial.measured_assignments == {"G1": "anon-1"}
    assert coast.measured_assignments == {}
    assert coast.active_bindings == {"anon-1": "G1"}
    assert len(coast.coasted_records) == 1
    record = coast.coasted_records[0]
    assert record.decision_state == "coast"
    assert record.local_track_state == "predicted"
    assert record.prediction_age_s == pytest.approx(gap_s)
    assert record.predicted_center_px == pytest.approx(
        np.array([320.0 + 20.0 * gap_s, 240.0 - 10.0 * gap_s])
    )
    assert record.predicted_bbox == pytest.approx(
        (
            315.0 + 20.0 * gap_s,
            235.0 - 10.0 * gap_s,
            325.0 + 20.0 * gap_s,
            245.0 - 10.0 * gap_s,
        )
    )
    expected_variance = 4.0 + (40.0 * gap_s) ** 2
    assert record.prediction_covariance_px == pytest.approx(np.diag([expected_variance] * 2))
    assert record.metadata["prediction_covariance_growth_px2"] == pytest.approx(
        (40.0 * gap_s) ** 2
    )
    assert record.to_log_record()["terminal_authorization_allowed"] is False

    recovery_timestamp = 1.0 + gap_s + 0.001
    recovered = _associate(
        associator,
        globals_,
        [_local("anon-1", 320.0, recovery_timestamp)],
        recovery_timestamp,
    )
    assert recovered.measured_assignments == {"G1": "anon-1"}
    assert recovered.binding_events[-1].event == "recovered"
    assert recovered.binding_events[-1].association_confirmed is True


def test_coast_expires_after_point_two_six_seconds() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0)]
    _associate(associator, globals_, [_local("anon-1", 320.0, 1.0)], 1.0)

    expired = _associate(associator, globals_, [], 1.26)

    assert expired.active_bindings == {}
    assert expired.coasted_records == ()
    assert [(event.event, event.reason) for event in expired.binding_events] == [
        ("expired", "coast_window_expired")
    ]
    assert expired.binding_events[0].prediction_age_s == pytest.approx(0.26)


@pytest.mark.parametrize(
    ("state", "expected_decision"),
    [("predicted", "coast"), ("lost", "reacquire")],
)
def test_predicted_and_lost_inputs_never_create_measured_assignment(
    state: str,
    expected_decision: str,
) -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0)]
    _associate(associator, globals_, [_local("anon-1", 320.0, 1.0)], 1.0)

    result = _associate(
        associator,
        globals_,
        [_local("anon-1", 321.0, 1.1, state=state, prediction_age_s=0.1)],
        1.1,
    )

    assert result.instantaneous_result.assignments == {}
    assert result.measured_assignments == {}
    assert result.active_bindings == {"anon-1": "G1"}
    assert result.coasted_records[0].decision_state == expected_decision
    assert result.binding_events[-1].event == "held"
    assert result.binding_events[-1].association_confirmed is False
    assert all(record["terminal_authorization_allowed"] is False for record in result.to_log_records())


def test_one_frame_challenger_is_pending_and_does_not_replace_binding() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0), _global("G2", 340.0)]
    _associate(associator, globals_, [_local("anon-1", 320.0, 1.0)], 1.0)

    challenged = _associate(
        associator,
        globals_,
        [_local("anon-1", 340.0, 1.1)],
        1.1,
    )

    assert challenged.instantaneous_result.assignments == {"G2": "anon-1"}
    assert challenged.measured_assignments == {}
    assert challenged.active_bindings == {"anon-1": "G1"}
    assert challenged.binding_events[-1].event == "pending"
    assert challenged.binding_events[-1].candidate_global_track_id == "G2"
    assert challenged.candidate_margins["anon-1"] == pytest.approx(float("inf"))


def test_two_distinct_measured_challenger_frames_confirm_binding_change() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0), _global("G2", 340.0)]
    _associate(associator, globals_, [_local("anon-1", 320.0, 1.0)], 1.0)
    first = _associate(
        associator,
        globals_,
        [_local("anon-1", 340.0, 1.1)],
        1.1,
        frame_id="challenger-1",
    )
    second = _associate(
        associator,
        globals_,
        [_local("anon-1", 340.0, 1.2)],
        1.2,
        frame_id="challenger-2",
    )

    assert first.binding_events[-1].event == "pending"
    assert second.binding_events[-1].event == "confirmed"
    assert second.binding_events[-1].incumbent_global_track_id == "G1"
    assert second.binding_events[-1].candidate_global_track_id == "G2"
    assert second.measured_assignments == {"G2": "anon-1"}
    assert second.active_bindings == {"anon-1": "G2"}


def test_near_tie_challenger_is_held_even_when_instantaneous_assignment_changes() -> None:
    association_config = AssociationConfig(min_lock_margin=3.0, rate_cost_weight=0.0)
    associator = TemporalGeometricAssociator(
        TemporalGeometricAssociationConfig(association_config=association_config)
    )
    camera = _camera(measurement_variance=100.0)
    globals_ = [_global("G1", 320.0), _global("G2", 324.0)]
    _associate(
        associator,
        globals_,
        [_local("anon-1", 320.0, 1.0)],
        1.0,
        camera=camera,
    )

    result = _associate(
        associator,
        globals_,
        [_local("anon-1", 323.0, 1.1)],
        1.1,
        camera=camera,
    )

    assert result.instantaneous_result.assignments == {"G2": "anon-1"}
    assert result.candidate_margins["anon-1"] < association_config.min_lock_margin
    assert result.binding_events[-1].event == "held"
    assert result.binding_events[-1].reason == "challenger_margin_below_min_lock_margin"
    assert result.active_bindings == {"anon-1": "G1"}


def test_pairwise_swap_remains_held_across_repeated_crossing_frames() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0), _global("G2", 340.0)]
    initial = _associate(
        associator,
        globals_,
        [_local("anon-1", 320.0, 1.0), _local("anon-2", 340.0, 1.0)],
        1.0,
    )
    assert initial.measured_assignments == {"G1": "anon-1", "G2": "anon-2"}

    for timestamp in (1.1, 1.2):
        result = _associate(
            associator,
            globals_,
            [_local("anon-1", 340.0, timestamp), _local("anon-2", 320.0, timestamp)],
            timestamp,
        )
        assert result.instantaneous_result.assignments == {
            "G1": "anon-2",
            "G2": "anon-1",
        }
        assert result.measured_assignments == {}
        assert result.active_bindings == {"anon-1": "G1", "anon-2": "G2"}
        assert {event.event for event in result.binding_events} == {"held"}
        assert {event.reason for event in result.binding_events} == {
            "pairwise_swap_or_crossing_ambiguity"
        }


def test_timestamp_rollback_clears_history_before_processing_new_frame() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0)]
    _associate(associator, globals_, [_local("anon-1", 320.0, 10.0)], 10.0)

    rollback = _associate(
        associator,
        globals_,
        [_local("anon-1", 320.0, 9.5)],
        9.5,
    )

    assert rollback.reset_reasons == ("measurement_timestamp_rollback",)
    assert [(event.event, event.reason) for event in rollback.binding_events] == [
        ("expired", "measurement_timestamp_rollback"),
        ("confirmed", "initial_measured_binding"),
    ]
    assert rollback.binding_events[-1].incumbent_global_track_id is None
    assert rollback.active_bindings == {"anon-1": "G1"}


def test_camera_and_stream_state_are_isolated_and_reset_is_scoped() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("G1", 320.0), _global("G2", 340.0)]
    _associate(
        associator,
        globals_,
        [_local("shared-local", 320.0, 1.0)],
        1.0,
        camera_id="cam-A",
        stream_id="live",
    )
    camera_b = _associate(
        associator,
        globals_,
        [_local("shared-local", 340.0, 1.0)],
        1.0,
        camera_id="cam-B",
        stream_id="live",
    )
    archive = _associate(
        associator,
        globals_,
        [_local("shared-local", 340.0, 1.0)],
        1.0,
        camera_id="cam-A",
        stream_id="archive",
    )

    assert camera_b.active_bindings == {"shared-local": "G2"}
    assert archive.active_bindings == {"shared-local": "G2"}
    reset_events = associator.reset(
        resource_id="R1",
        camera_id="cam-A",
        stream_id="live",
        reason="camera_stream_reset",
    )
    assert len(reset_events) == 1
    assert reset_events[0].reason == "camera_stream_reset"

    camera_b_continued = _associate(
        associator,
        globals_,
        [_local("shared-local", 340.0, 1.1)],
        1.1,
        camera_id="cam-B",
        stream_id="live",
    )
    archive_continued = _associate(
        associator,
        globals_,
        [_local("shared-local", 340.0, 1.1)],
        1.1,
        camera_id="cam-A",
        stream_id="archive",
    )
    camera_a_reinitialized = _associate(
        associator,
        globals_,
        [_local("shared-local", 320.0, 1.1)],
        1.1,
        camera_id="cam-A",
        stream_id="live",
    )

    assert camera_b_continued.binding_events[-1].event == "continued"
    assert archive_continued.binding_events[-1].event == "continued"
    assert camera_a_reinitialized.binding_events[-1].event == "confirmed"
    assert camera_a_reinitialized.binding_events[-1].reason == "initial_measured_binding"


def test_truth_metadata_is_not_consumed_or_emitted_and_global_ids_remain_unchanged() -> None:
    associator = TemporalGeometricAssociator()
    globals_ = [_global("CENTER-G1", 320.0), _global("CENTER-G2", 340.0)]
    original_ids = tuple(track.global_track_id for track in globals_)
    local = _local(
        "anonymous-local-7",
        320.0,
        1.0,
        metadata={
            "truth_global_track_id": "SECRET-TRUTH-ID",
            "actor_name": "SECRET-ACTOR",
            "object_id": 999,
        },
    )

    result = _associate(associator, globals_, [local], 1.0)
    serialized = json.dumps(result.to_log_records(), sort_keys=True)

    assert tuple(track.global_track_id for track in globals_) == original_ids
    assert result.measured_assignments == {"CENTER-G1": "anonymous-local-7"}
    assert result.truth_identity_used is False
    assert "SECRET-TRUTH-ID" not in serialized
    assert "SECRET-ACTOR" not in serialized
    assert '"object_id"' not in serialized
    assert all(record["truth_identity_used"] is False for record in result.to_log_records())
