from __future__ import annotations

import numpy as np
import pytest

from d5_terminal_association import (
    Assignment,
    CameraModel,
    GlobalTrack,
    IdentityClaim,
    LocalVisualTrack,
    TerminalAssociator,
    annotate_visual_png_handoff,
    summarize_coalition_visual_completion,
)


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array([[120.0, 0.0, 320.0], [0.0, 120.0, 240.0], [0.0, 0.0, 1.0]]),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
    )


def _global_track(global_track_id: str = "G1") -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_track_id,
        position=np.array([0.0, 0.0, 10.0]),
        covariance=np.eye(3) * 0.01,
        timestamp=0.0,
        track_version=1,
    )


def _assignment(
    *,
    global_track_id: str = "G1",
    plan_version: int = 1,
    required_resource_count: int = 1,
) -> Assignment:
    return Assignment(
        global_track_id,
        assignment_version=1,
        resource_id="R1",
        plan_id="plan-a",
        plan_version=plan_version,
        coalition_id="coalition-a" if required_resource_count > 1 else None,
        coalition_version=plan_version if required_resource_count > 1 else None,
        member_role="primary",
        required_resource_count=required_resource_count,
        coordination_mode="hybrid" if required_resource_count > 1 else "independent",
        activation_state="active",
    )


def _local_track(
    frame_index: int,
    *,
    local_track_id: str = "L1",
    camera_id: str = "front_rgb",
    stream_id: str = "R1/front_rgb/live",
    detector_backend: str = "airsim_builtin_detection",
    tracker_backend: str = "airsim_builtin_iou",
    detection_source: str = "airsim_builtin_detection",
) -> LocalVisualTrack:
    side = 20.0 + 0.1 * frame_index
    return LocalVisualTrack(
        local_track_id=local_track_id,
        center_px=np.array([320.0, 240.0]),
        bbox=(320.0 - side, 240.0 - side, 320.0 + side, 240.0 + side),
        category="uav",
        quality=0.95,
        mot_history_length=8,
        timestamp=0.1 * frame_index,
        detection_source=detection_source,
        track_transition_state="continued",
        image_size=(640, 480),
        metadata={
            "resource_id": "R1",
            "camera_id": camera_id,
            "stream_id": stream_id,
            "detector_backend": detector_backend,
            "tracker_backend": tracker_backend,
        },
    )


def _decide(
    associator: TerminalAssociator,
    frame_index: int,
    *,
    assignment: Assignment | None = None,
    local_track: LocalVisualTrack | None = None,
    camera_id: str = "front_rgb",
    stream_id: str = "R1/front_rgb/live",
    detector_backend: str = "airsim_builtin_detection",
    tracker_backend: str = "airsim_builtin_iou",
    committed_members: tuple[str, ...] | None = None,
    duplicate_risk: bool = False,
    identity_conflict: bool = False,
):
    assignment = assignment or _assignment(plan_version=frame_index)
    local_track = local_track or _local_track(frame_index)
    return associator.decide(
        assignment,
        [_global_track(assignment.assigned_global_track_id)],
        [local_track],
        camera=_camera(),
        current_time=0.1 * frame_index,
        frame_id=f"episode:{frame_index:04d}:R1",
        camera_id=camera_id,
        stream_id=stream_id,
        detector_backend=detector_backend,
        tracker_backend=tracker_backend,
        committed_coalition_member_ids=committed_members,
        duplicate_terminal_lock_risk=duplicate_risk,
        identity_conflict=identity_conflict,
    )


def test_plan_version_refresh_preserves_bbox_and_mot_history_signature() -> None:
    associator = TerminalAssociator()
    decisions = [_decide(associator, frame_index) for frame_index in range(1, 5)]
    handoff = annotate_visual_png_handoff(
        decisions[-1],
        local_track_history=[_local_track(4)],
        image_size=(640, 480),
        range_to_assigned_track_m=20.0,
        closing_speed_mps=5.0,
        measurement_age_s=0.0,
        los_rate_px_s=(0.0, 0.0),
    )

    assert handoff.metadata["bbox_stable"] is True
    assert handoff.metadata["bbox_history_length"] == 4
    assert handoff.metadata["bbox_area_cv"] < 0.30
    assert handoff.metadata["bbox_history_continued_across_plan_version"] is True
    assert handoff.metadata["bbox_history_source_plan_versions"] == [1, 2, 3, 4]
    assert handoff.metadata["bbox_history_plan_version_excluded_from_signature"] is True
    assert handoff.metadata["bbox_history_evidence_source"] == "measured"
    assert handoff.metadata["mot_history_effective_length"] == 8
    assert handoff.metadata["bbox_history_signature"]["local_track_id"] == "L1"
    assert "plan_version" not in handoff.metadata["bbox_history_signature"]


@pytest.mark.parametrize(
    ("change", "expected_reason"),
    (
        ("local_track", "local_track_id_changed"),
        ("camera", "camera_changed"),
        ("detector", "detector_backend_changed"),
        ("tracker", "tracker_backend_changed"),
        ("stream", "stream_changed"),
        ("duplicate", "duplicate_terminal_lock_risk"),
        ("identity", "identity_conflict"),
    ),
)
def test_visual_identity_or_safety_change_resets_history(
    change: str,
    expected_reason: str,
) -> None:
    associator = TerminalAssociator()
    for frame_index in range(1, 5):
        _decide(associator, frame_index)

    local = _local_track(
        5,
        local_track_id="L2" if change == "local_track" else "L1",
        camera_id="belly_rgb" if change == "camera" else "front_rgb",
        stream_id="R1/front_rgb/restarted" if change == "stream" else "R1/front_rgb/live",
        detector_backend="yolov8" if change == "detector" else "airsim_builtin_detection",
        tracker_backend="bytetrack" if change == "tracker" else "airsim_builtin_iou",
    )
    decision = _decide(
        associator,
        5,
        local_track=local,
        camera_id="belly_rgb" if change == "camera" else "front_rgb",
        stream_id="R1/front_rgb/restarted" if change == "stream" else "R1/front_rgb/live",
        detector_backend="yolov8" if change == "detector" else "airsim_builtin_detection",
        tracker_backend="bytetrack" if change == "tracker" else "airsim_builtin_iou",
        duplicate_risk=change == "duplicate",
        identity_conflict=change == "identity",
    )

    assert decision.metadata["bbox_stable"] is False
    assert decision.metadata["bbox_history_reset_reason"] == expected_reason
    assert decision.metadata["bbox_history_length"] in {0, 1}
    assert decision.metadata["mot_history_effective_length"] in {0, 1}


def test_resource_target_rebinding_drops_old_history_even_when_rebound_back() -> None:
    associator = TerminalAssociator()
    for frame_index in range(1, 5):
        _decide(associator, frame_index)

    rebound = _decide(
        associator,
        5,
        assignment=_assignment(global_track_id="G2", plan_version=5),
    )
    back = _decide(
        associator,
        6,
        assignment=_assignment(global_track_id="G1", plan_version=6),
    )

    assert rebound.metadata["bbox_history_reset_reason"] == "resource_target_binding_changed"
    assert rebound.metadata["bbox_history_length"] == 1
    assert back.metadata["bbox_history_reset_reason"] == "resource_target_binding_changed"
    assert back.metadata["bbox_history_length"] == 1


def test_verified_friend_conflict_clears_bbox_and_mot_history() -> None:
    associator = TerminalAssociator()
    for frame_index in range(1, 5):
        _decide(associator, frame_index)
    local = _local_track(5)
    decision = associator.decide(
        _assignment(plan_version=5),
        [_global_track()],
        [local],
        identity_claims=[
            IdentityClaim(
                platform_id="FRIEND-1",
                claim_type="remote_id",
                auth_state="verified",
                associated_local_track_id="L1",
                is_friend=True,
                timestamp=0.5,
            )
        ],
        camera=_camera(),
        current_time=0.5,
        camera_id="front_rgb",
        stream_id="R1/front_rgb/live",
        detector_backend="airsim_builtin_detection",
        tracker_backend="airsim_builtin_iou",
    )

    assert decision.friend_conflict_state == "verified_friend_overlap"
    assert decision.metadata["bbox_history_reset_reason"] == (
        "friend_conflict:verified_friend_overlap"
    )
    assert decision.metadata["bbox_history_length"] == 0
    assert decision.metadata["mot_history_effective_length"] == 0


def test_m_to_n_history_fails_closed_without_committed_current_membership() -> None:
    associator = TerminalAssociator()
    decision = _decide(
        associator,
        1,
        assignment=_assignment(plan_version=1, required_resource_count=3),
        committed_members=None,
    )

    assert decision.metadata["bbox_history_contract_complete"] is False
    assert decision.metadata["bbox_history_contract_missing_fields"] == [
        "committed_coalition_member_ids"
    ]
    assert decision.metadata["bbox_history_reset_reason"] == (
        "committed_current_membership_missing"
    )
    assert decision.metadata["bbox_history_length"] == 0
    assert decision.metadata["bbox_stable"] is False


def test_m_to_n_membership_change_resets_bbox_history() -> None:
    associator = TerminalAssociator()
    assignment = _assignment(plan_version=1, required_resource_count=3)
    for frame_index in range(1, 5):
        _decide(
            associator,
            frame_index,
            assignment=Assignment(
                **{
                    **assignment.__dict__,
                    "plan_version": frame_index,
                    "coalition_version": frame_index,
                }
            ),
            committed_members=("R1", "R2"),
        )

    changed = _decide(
        associator,
        5,
        assignment=Assignment(
            **{
                **assignment.__dict__,
                "plan_version": 5,
                "coalition_version": 5,
            }
        ),
        committed_members=("R1", "R3"),
    )

    assert changed.metadata["bbox_history_reset_reason"] == "coalition_membership_changed"
    assert changed.metadata["bbox_history_length"] == 1
    assert changed.metadata["mot_history_effective_length"] == 1


def test_yolo_history_contract_requires_backend_fields_from_producer() -> None:
    associator = TerminalAssociator()
    local = _local_track(
        1,
        detection_source="yolov8_mot",
        detector_backend="",
        tracker_backend="",
    )
    local = LocalVisualTrack(
        **{
            **local.__dict__,
            "metadata": {
                "resource_id": "R1",
                "camera_id": "front_rgb",
                "stream_id": "R1/front_rgb/live",
            },
        }
    )
    decision = associator.decide(
        _assignment(plan_version=1),
        [_global_track()],
        [local],
        camera=_camera(),
        current_time=0.1,
        camera_id="front_rgb",
        stream_id="R1/front_rgb/live",
    )

    assert decision.metadata["bbox_history_contract_complete"] is False
    assert decision.metadata["bbox_history_contract_missing_fields"] == [
        "detector_backend",
        "tracker_backend",
    ]
    assert decision.metadata["bbox_stable"] is False


def _binding(resource_id: str, *, plan_version: int, coalition_version: int) -> dict[str, object]:
    return {
        "resource_id": resource_id,
        "assigned_global_track_id": "G1",
        "target_id": "T001",
        "plan_id": "plan-a",
        "plan_version": plan_version,
        "active_plan_owner": "center",
        "owner_node_id": "C2",
        "coalition_id": "coalition-a",
        "coalition_version": coalition_version,
        "member_role": "primary",
        "coordination_mode": "hybrid",
        "primary_resource_count": 2,
        "required_resource_count": 2,
        "authorization_state": "authorized",
        "binding_state": "active",
    }


def _coalition_association(
    resource_id: str,
    *,
    frame_index: int,
    plan_version: int,
    coalition_version: int,
    local_track_id: str,
) -> object:
    from d5_terminal_association import TerminalAssociation

    return TerminalAssociation(
        assigned_global_track_id="G1",
        local_track_id=local_track_id,
        association_confidence=0.95,
        ambiguity_score=0.05,
        friend_conflict_state="none",
        decision_state="locked",
        assignment_version=1,
        resource_id=resource_id,
        plan_id="plan-a",
        plan_version=plan_version,
        coalition_id="coalition-a",
        coalition_version=coalition_version,
        member_role="primary",
        required_resource_count=2,
        coordination_mode="hybrid",
        activation_state="active",
        metadata={
            "frame_index": frame_index,
            "projection_timestamp": float(frame_index),
            "execution_gate_pass": True,
            "measurement_camera_id": f"{resource_id}/front_rgb",
            "projection_camera_id": f"{resource_id}/front_rgb",
            "detector_backend": "airsim_builtin_detection",
            "tracker_backend": "airsim_builtin_iou",
            "stream_id": f"{resource_id}/front_rgb/live",
        },
    )


def test_stable_lock_continues_across_plan_refresh_but_not_local_track_change() -> None:
    old_bindings = tuple(
        _binding(resource_id, plan_version=1, coalition_version=1)
        for resource_id in ("R1", "R2")
    )
    new_bindings = tuple(
        _binding(resource_id, plan_version=2, coalition_version=2)
        for resource_id in ("R1", "R2")
    )
    history = tuple(
        _coalition_association(
            resource_id,
            frame_index=1,
            plan_version=1,
            coalition_version=1,
            local_track_id=f"L-{resource_id}",
        )
        for resource_id in ("R1", "R2")
    )
    current = tuple(
        _coalition_association(
            resource_id,
            frame_index=2,
            plan_version=2,
            coalition_version=2,
            local_track_id=("L-new" if resource_id == "R2" else f"L-{resource_id}"),
        )
        for resource_id in ("R1", "R2")
    )

    summary = summarize_coalition_visual_completion(
        new_bindings,
        current,
        history,
        historical_bindings=old_bindings,
    )

    assert summary.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert summary.metadata["stability_reset_reason_by_resource"]["R2"] == (
        "local_track_id_changed"
    )
    assert summary.metadata["stability_evidence_source_by_resource"] == {
        "R1": "measured",
        "R2": "measured",
    }
    assert summary.metadata["stability_history_signature_by_resource"]["R1"][
        "local_track_id"
    ] == "L-R1"
