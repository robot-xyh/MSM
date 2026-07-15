from __future__ import annotations

from dataclasses import replace

import numpy as np

from d5_terminal_association import (
    Assignment,
    CameraModel,
    GlobalTrack,
    LocalVisualTrack,
    TerminalAssociator,
    annotate_visual_png_handoff,
)


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [[120.0, 0.0, 320.0], [0.0, 120.0, 240.0], [0.0, 0.0, 1.0]],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
    )


def _global_track() -> GlobalTrack:
    return GlobalTrack(
        global_track_id="G1",
        position=np.array([0.0, 0.0, 10.0]),
        covariance=np.eye(3) * 0.01,
        timestamp=0.0,
        track_version=1,
    )


def _local(frame_index: int, *, local_track_id: str = "L1") -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_track_id,
        center_px=np.array([320.0, 240.0]),
        bbox=(300.0, 220.0, 340.0, 260.0),
        category="uav",
        quality=0.95,
        mot_history_length=frame_index + 1,
        timestamp=0.1 * frame_index,
        arrival_timestamp=0.1 * frame_index,
        exposure_timestamp=0.1 * frame_index,
        local_track_state="measured",
        detection_source="airsim_builtin_detection",
        track_transition_state="continued",
        image_size=(640, 480),
        metadata={
            "resource_id": "R2",
            "camera_id": "R2/front",
            "stream_id": "episode:R2/front",
            "detector_backend": "airsim_detect",
            "tracker_backend": "airsim_builtin_tracklet",
        },
    )


def _assignment(*, arrival_window_end_s: float | None = None) -> Assignment:
    return Assignment(
        assigned_global_track_id="G1",
        assignment_version=1,
        plan_id="P1",
        plan_version=1,
        resource_id="R2",
        coalition_id="C1",
        coalition_version=1,
        member_role="primary",
        required_resource_count=2,
        coordination_mode="hybrid",
        activation_state="active",
        authorization_state="authorized",
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
        arrival_window_start_s=0.0,
        arrival_window_end_s=arrival_window_end_s,
    )


def _decide(
    associator: TerminalAssociator,
    frame_index: int,
    *,
    assignment: Assignment | None = None,
):
    local = _local(frame_index)
    decision = associator.decide(
        assignment=assignment or _assignment(),
        global_tracks=[_global_track()],
        local_tracks=[local],
        camera=_camera(),
        current_time=local.timestamp,
        arrival_timestamp=local.arrival_timestamp,
        camera_id="R2/front",
        stream_id="episode:R2/front",
        detector_backend="airsim_detect",
        tracker_backend="airsim_builtin_tracklet",
        committed_coalition_member_ids=("R1", "R2"),
    )
    return decision, local


def test_live_funnel_separates_measured_lock_stability_from_bbox_handoff() -> None:
    associator = TerminalAssociator()
    decisions = []
    locals_history = []
    for frame_index in range(1, 5):
        decision, local = _decide(associator, frame_index)
        decisions.append(decision)
        locals_history.append(local)

    first = decisions[0].metadata["d5_live_visual_funnel"]
    second = decisions[1].metadata["d5_live_visual_funnel"]
    fourth = decisions[-1].metadata["d5_live_visual_funnel"]

    assert first["measured_detection_available"] is True
    assert first["measured_bbox_available"] is True
    assert first["own_camera_measured_bbox_available"] is True
    assert first["visual_match_locked"] is True
    assert first["execution_lock_allowed"] is False
    assert first["association_lock_only"] is True
    assert first["measured_lock_streak_count"] == 1
    assert first["measured_stable_lock"] is False
    assert first["first_failure_stage"] == "measured_stable_lock"

    assert second["measured_lock_streak_count"] == 2
    assert second["measured_stable_lock"] is True
    assert second["execution_lock_allowed"] is False
    assert second["first_failure_stage"] == "bbox_stability"

    assert fourth["measured_lock_streak_count"] == 4
    assert fourth["measured_stable_lock"] is True
    assert fourth["bbox_stable"] is True
    assert fourth["execution_lock_allowed"] is True
    assert fourth["first_failure_stage"] == "handoff_evaluation"

    handoff = annotate_visual_png_handoff(
        decisions[-1],
        local_track_history=locals_history,
        image_size=(640, 480),
        range_to_assigned_track_m=20.0,
        closing_speed_mps=5.0,
        detection_latency_s=0.0,
        measurement_age_s=0.0,
        los_rate_px_s=(0.0, 0.0),
    )
    diagnostic = handoff.metadata["d5_live_visual_funnel"]
    assert diagnostic["handoff_evaluated"] is True
    assert diagnostic["handoff_recommended"] is True
    assert diagnostic["d7_handoff_input_ready"] is True
    assert diagnostic["first_failure_stage"] == "complete"
    assert diagnostic["d7_handoff_input"]["assigned_global_track_id"] == "G1"
    assert diagnostic["d7_handoff_input"]["resource_id"] == "R2"
    assert diagnostic["d7_handoff_input"]["camera_id"] == "R2/front"
    assert diagnostic["d7_handoff_input"]["stream_id"] == "episode:R2/front"
    assert diagnostic["d7_handoff_input"]["detector_backend"] == "airsim_detect"
    assert diagnostic["d7_handoff_input"]["tracker_backend"] == (
        "airsim_builtin_tracklet"
    )
    assert diagnostic["d7_handoff_input"]["center_px"] == [320.0, 240.0]
    assert diagnostic["d7_handoff_input"]["bbox_xyxy"] == [
        300.0,
        220.0,
        340.0,
        260.0,
    ]
    assert diagnostic["d7_handoff_input"]["local_track_state"] == "measured"
    assert diagnostic["d7_handoff_input"]["measured_detection_available"] is True
    assert diagnostic["d7_handoff_input"]["measured_bbox_available"] is True
    assert diagnostic["d7_handoff_input"]["measured_stable_lock"] is True
    assert diagnostic["d7_handoff_input"]["bbox_stable"] is True
    assert diagnostic["d7_handoff_input"]["execution_lock_allowed"] is True

    runtime_record = handoff.to_runtime_record()
    assert runtime_record["measured_lock_streak_count"] == 4
    assert runtime_record["measured_stable_lock"] is True
    assert runtime_record["bbox_stable"] is True
    assert runtime_record["handoff_recommended"] is True
    assert runtime_record["execution_lock_allowed"] is True
    assert runtime_record["own_camera_measured_bbox_available"] is True
    assert runtime_record["d7_handoff_input_ready"] is True
    assert runtime_record["d7_handoff_input"]["bbox_xyxy"] == [
        300.0,
        220.0,
        340.0,
        260.0,
    ]
    assert runtime_record["d5_first_failure_stage"] == "complete"


def test_live_funnel_exposes_raw_lock_blocked_by_expired_arrival_contract() -> None:
    associator = TerminalAssociator()
    decision, _ = _decide(
        associator,
        2,
        assignment=_assignment(arrival_window_end_s=0.15),
    )
    diagnostic = decision.metadata["d5_live_visual_funnel"]

    assert decision.decision_state == "hold"
    assert decision.reason == "arrival_window_expired"
    assert diagnostic["measured_detection_available"] is True
    assert diagnostic["visual_match_locked"] is True
    assert diagnostic["execution_gate_pass"] is False
    assert diagnostic["execution_gate_reason"] == "arrival_window_expired"
    assert diagnostic["execution_lock_allowed"] is False
    assert diagnostic["measured_lock_streak_count"] == 0
    assert diagnostic["measured_stable_lock"] is False
    assert diagnostic["first_failure_stage"] == "execution_contract"
    assert diagnostic["first_failure_reason"] == "arrival_window_expired"
    assert diagnostic["failure_domain"] == "upstream_assignment_contract"


def test_live_funnel_fails_closed_when_committed_membership_is_not_delivered() -> None:
    associator = TerminalAssociator()
    local = _local(1)
    decision = associator.decide(
        assignment=_assignment(),
        global_tracks=[_global_track()],
        local_tracks=[local],
        camera=_camera(),
        current_time=local.timestamp,
        camera_id="R2/front",
        stream_id="episode:R2/front",
        detector_backend="airsim_detect",
        tracker_backend="airsim_builtin_tracklet",
        committed_coalition_member_ids=None,
    )
    diagnostic = decision.metadata["d5_live_visual_funnel"]

    assert decision.decision_state == "locked"
    assert diagnostic["history_contract_complete"] is False
    assert diagnostic["history_contract_missing_fields"] == [
        "committed_coalition_member_ids"
    ]
    assert diagnostic["measured_stable_lock"] is False
    assert diagnostic["first_failure_stage"] == "evidence_contract"
    assert diagnostic["first_failure_reason"] == (
        "committed_current_membership_missing"
    )
    assert diagnostic["failure_domain"] == (
        "upstream_membership_or_runtime_contract"
    )


def test_live_funnel_keeps_bboxless_geometric_lock_non_executable() -> None:
    associator = TerminalAssociator()
    local = replace(_local(2), bbox=None)
    decision = associator.decide(
        assignment=_assignment(),
        global_tracks=[_global_track()],
        local_tracks=[local],
        camera=_camera(),
        current_time=local.timestamp,
        camera_id="R2/front",
        stream_id="episode:R2/front",
        detector_backend="airsim_detect",
        tracker_backend="airsim_builtin_tracklet",
        committed_coalition_member_ids=("R1", "R2"),
    )
    diagnostic = decision.metadata["d5_live_visual_funnel"]

    assert decision.decision_state == "locked"
    assert diagnostic["visual_match_locked"] is True
    assert diagnostic["measured_detection_available"] is True
    assert diagnostic["measured_bbox_available"] is False
    assert diagnostic["own_camera_measured_bbox_available"] is False
    assert diagnostic["execution_lock_allowed"] is False
    assert diagnostic["association_lock_only"] is True
    assert diagnostic["first_failure_stage"] == "measured_bbox"
    assert diagnostic["first_failure_reason"] == "measured_local_track_bbox_unavailable"


def test_live_funnel_rejects_local_track_from_another_camera_scope() -> None:
    associator = TerminalAssociator()
    local = replace(
        _local(2),
        metadata={
            **_local(2).metadata,
            "camera_id": "R3/front",
            "resource_id": "R3",
        },
    )
    decision = associator.decide(
        assignment=_assignment(),
        global_tracks=[_global_track()],
        local_tracks=[local],
        camera=_camera(),
        current_time=local.timestamp,
        camera_id="R2/front",
        stream_id="episode:R2/front",
        detector_backend="airsim_detect",
        tracker_backend="airsim_builtin_tracklet",
        committed_coalition_member_ids=("R1", "R2"),
    )
    diagnostic = decision.metadata["d5_live_visual_funnel"]

    assert decision.decision_state == "hold"
    assert decision.reason == "local_visual_scope_mismatch"
    assert diagnostic["visual_match_locked"] is True
    assert diagnostic["local_visual_scope_consistent"] is False
    assert diagnostic["own_camera_measured_bbox_available"] is False
    assert diagnostic["execution_lock_allowed"] is False
    assert diagnostic["first_failure_stage"] == "camera_scope"


def test_small_stable_bbox_never_becomes_executable_or_handoff_ready() -> None:
    associator = TerminalAssociator()
    decisions = []
    history = []
    for frame_index in range(1, 5):
        local = replace(
            _local(frame_index),
            bbox=(318.0, 238.0, 322.0, 242.0),
        )
        decision = associator.decide(
            assignment=_assignment(),
            global_tracks=[_global_track()],
            local_tracks=[local],
            camera=_camera(),
            current_time=local.timestamp,
            camera_id="R2/front",
            stream_id="episode:R2/front",
            detector_backend="airsim_detect",
            tracker_backend="airsim_builtin_tracklet",
            committed_coalition_member_ids=("R1", "R2"),
        )
        decisions.append(decision)
        history.append(local)

    diagnostic = decisions[-1].metadata["d5_live_visual_funnel"]
    assert diagnostic["measured_stable_lock"] is True
    assert diagnostic["bbox_stable"] is False
    assert diagnostic["execution_lock_allowed"] is False
    assert diagnostic["first_failure_stage"] == "bbox_stability"

    handoff = annotate_visual_png_handoff(
        decisions[-1],
        local_track_history=history,
        image_size=(640, 480),
        range_to_assigned_track_m=20.0,
        closing_speed_mps=5.0,
        detection_latency_s=0.0,
        measurement_age_s=0.0,
        los_rate_px_s=(0.0, 0.0),
    )
    handoff_diagnostic = handoff.metadata["d5_live_visual_funnel"]
    assert handoff_diagnostic["handoff_recommended"] is False
    assert handoff_diagnostic["d7_handoff_input_ready"] is False
    assert handoff_diagnostic["d7_handoff_input"]["bbox_xyxy"] == [
        318.0,
        238.0,
        322.0,
        242.0,
    ]
    assert handoff_diagnostic["d7_handoff_input"]["measured_stable_lock"] is True
    assert handoff_diagnostic["d7_handoff_input"]["bbox_stable"] is False
    assert handoff_diagnostic["d7_handoff_input"]["association_lock_only"] is True
    assert handoff_diagnostic["d7_handoff_input"]["execution_lock_allowed"] is False
