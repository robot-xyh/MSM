from __future__ import annotations

from dataclasses import replace

import pytest

from d5_terminal_association.active_vision_camera_executor import (
    ActiveVisionCameraExecutionOutcome,
    ActiveVisionCameraFault,
    DeterministicCameraCommandExecutor,
)
from d5_terminal_association.active_vision_contracts import (
    ActiveVisionActionV1,
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionDecisionV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    enumerate_safe_action_candidates,
)
from d5_terminal_association.active_vision_episode_dataset import (
    ActiveVisionCameraFeedbackV1,
    active_vision_sample_from_decision,
)


NOW = 20.0


def _snapshot() -> ActiveVisionSnapshotV1:
    camera = ActiveVisionCameraState(
        camera_id="CAM-0",
        resource_id="INT-0",
        state_timestamp=NOW,
        yaw_deg=1.0,
        pitch_deg=-1.0,
        yaw_rate_deg_s=0.0,
        pitch_rate_deg_s=0.0,
        yaw_limits_deg=(-30.0, 30.0),
        pitch_limits_deg=(-20.0, 20.0),
        max_yaw_rate_deg_s=40.0,
        max_pitch_rate_deg_s=40.0,
        max_slew_deg_s=50.0,
        current_fov_mode=ActiveVisionFovMode.WIDE,
    )
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=NOW,
        plan=ActiveVisionPlanReference(
            plan_version=4,
            coalition_version=7,
            assignments=(
                ActiveVisionAssignmentReference(
                    resource_id="INT-0",
                    camera_id="CAM-0",
                    global_track_id="GT-001",
                ),
            ),
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=9,
            plan_version=4,
            coalition_version=7,
            update_timestamp=NOW - 0.05,
            healthy=True,
        ),
        tracks=(
            ActiveVisionTrackReference(
                global_track_id="GT-001",
                track_version=3,
                measurement_timestamp=NOW - 0.05,
            ),
        ),
        cameras=(camera,),
        projections=(
            ActiveVisionProjectionEvidence(
                camera_id="CAM-0",
                global_track_id="GT-001",
                measurement_timestamp=NOW - 0.05,
                arrival_timestamp=NOW - 0.02,
                yaw_error_deg=4.0,
                pitch_error_deg=-2.0,
                projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
                visibility_probability=0.9,
                occlusion_fraction=0.1,
                association_confidence=0.95,
                in_fov=True,
            ),
        ),
    )


def _action(
    snapshot: ActiveVisionSnapshotV1,
    intent: ActiveVisionIntent,
    fov_mode: ActiveVisionFovMode,
) -> ActiveVisionActionV1:
    return next(
        item
        for item in enumerate_safe_action_candidates(
            snapshot,
            camera_id="CAM-0",
            current_timestamp=NOW,
        )
        if item.intent is intent and item.fov_mode is fov_mode
    )


def _feedback(
    snapshot: ActiveVisionSnapshotV1,
    *,
    last_version: int | None = None,
    camera_state: ActiveVisionCameraState | None = None,
) -> ActiveVisionCameraFeedbackV1:
    return ActiveVisionCameraFeedbackV1(
        camera_state=camera_state or snapshot.camera("CAM-0"),
        last_accepted_command_version=last_version,
    )


def _execute(
    snapshot: ActiveVisionSnapshotV1,
    action: ActiveVisionActionV1,
    feedback: ActiveVisionCameraFeedbackV1,
    **overrides: object,
):
    arguments = {
        "sample_key": "sample-000",
        "command_version": 11,
        "execution_timestamp": NOW + 0.1,
        "expected_plan_version": snapshot.plan.plan_version,
        "expected_coalition_version": snapshot.plan.coalition_version,
        "expected_communication_version": snapshot.communication.communication_version,
    }
    arguments.update(overrides)
    return DeterministicCameraCommandExecutor().execute(
        snapshot,
        action,
        feedback,
        **arguments,
    )


@pytest.mark.parametrize(
    ("intent", "fov_mode"),
    [
        (ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE),
        (ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.ZOOM),
        (ActiveVisionIntent.HOLD, ActiveVisionFovMode.WIDE),
    ],
)
def test_executor_applies_wide_zoom_and_hold_with_compatible_ack(
    intent: ActiveVisionIntent,
    fov_mode: ActiveVisionFovMode,
) -> None:
    snapshot = _snapshot()
    action = _action(snapshot, intent, fov_mode)
    feedback = _feedback(snapshot)

    result = _execute(snapshot, action, feedback)

    assert result.outcome is ActiveVisionCameraExecutionOutcome.APPLIED
    assert result.applied is True
    assert result.runtime_ack is not None
    assert result.runtime_ack.accepted is True
    assert result.runtime_ack.status_code == "applied"
    assert result.runtime_ack.command_version == 11
    assert result.runtime_ack.communication_version == action.communication_version
    assert result.camera_feedback.last_accepted_command_version == 11
    assert result.camera_feedback.camera_state.current_fov_mode is fov_mode
    assert result.camera_feedback.camera_state.state_timestamp == NOW + 0.1
    assert result.camera_feedback.camera_state.yaw_deg == pytest.approx(
        feedback.camera_state.yaw_deg + action.yaw_delta_deg
    )
    assert result.camera_feedback.camera_state.pitch_deg == pytest.approx(
        feedback.camera_state.pitch_deg + action.pitch_delta_deg
    )

    decision = ActiveVisionDecisionV1(
        requested_mode=ActiveVisionRuntimeMode.DISABLED,
        effective_mode=ActiveVisionRuntimeMode.DISABLED,
        rule_action=action,
        requested_action=None,
        effective_action=action,
        fallback_reason="learning_disabled",
        inference_latency_ms=0.0,
        model_fingerprint=None,
        plan_version=snapshot.plan.plan_version,
        coalition_version=snapshot.plan.coalition_version,
        communication_version=snapshot.communication.communication_version,
    )
    sample = active_vision_sample_from_decision(
        sample_key="sample-000",
        observation_key="observation-000",
        sequence_index=0,
        camera_id="CAM-0",
        snapshot=snapshot,
        decision=decision,
        camera_feedback=result.camera_feedback,
        runtime_ack=result.runtime_ack,
    )
    assert sample.runtime_ack == result.runtime_ack


def test_executor_rejects_expired_action_without_updating_feedback() -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE)
    feedback = _feedback(snapshot, last_version=5)

    result = _execute(
        snapshot,
        action,
        feedback,
        execution_timestamp=action.expires_timestamp + 0.01,
    )

    _assert_rejected(result, feedback, "action_timeout")


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"expected_plan_version": 5}, "stale_plan_version"),
        ({"expected_coalition_version": 8}, "stale_coalition_version"),
        ({"expected_communication_version": 10}, "stale_communication_version"),
    ],
)
def test_executor_rejects_expected_version_mismatch(
    override: dict[str, int],
    reason: str,
) -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE)
    feedback = _feedback(snapshot)

    result = _execute(snapshot, action, feedback, **override)

    _assert_rejected(result, feedback, reason)
    assert result.runtime_ack is not None
    assert result.runtime_ack.plan_version == snapshot.plan.plan_version
    assert result.runtime_ack.coalition_version == snapshot.plan.coalition_version
    assert result.runtime_ack.communication_version == snapshot.communication.communication_version


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        (ActiveVisionCameraFault.CAMERA_BUSY, "gimbal_busy"),
        (ActiveVisionCameraFault.CAMERA_UNAVAILABLE, "camera_unavailable"),
    ],
)
def test_executor_fault_injection_only_rejects(
    fault: ActiveVisionCameraFault,
    reason: str,
) -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE)
    feedback = _feedback(snapshot)

    result = _execute(snapshot, action, feedback, fault=fault)

    _assert_rejected(result, feedback, reason)


def test_executor_rejects_runtime_busy_feedback() -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE)
    busy = replace(snapshot.camera("CAM-0"), action_in_progress_until=NOW + 1.0)
    feedback = _feedback(snapshot, camera_state=busy)

    result = _execute(snapshot, action, feedback)

    _assert_rejected(result, feedback, "gimbal_busy")


def test_executor_rejects_runtime_unsupported_fov() -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.ZOOM)
    wide_only = replace(
        snapshot.camera("CAM-0"),
        supported_fov_modes=(ActiveVisionFovMode.WIDE,),
        current_fov_mode=ActiveVisionFovMode.WIDE,
    )
    feedback = _feedback(snapshot, camera_state=wide_only)

    result = _execute(snapshot, action, feedback)

    _assert_rejected(result, feedback, "unsupported_fov_mode")


def test_executor_rejects_action_rejected_by_existing_validator() -> None:
    snapshot = _snapshot()
    base = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE)
    invalid = replace(base, yaw_delta_deg=9.0)
    feedback = _feedback(snapshot)

    result = _execute(snapshot, invalid, feedback)

    _assert_rejected(result, feedback, "gimbal_increment_limit")


def test_executor_rejects_non_monotonic_command_version() -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.HOLD, ActiveVisionFovMode.WIDE)
    feedback = _feedback(snapshot, last_version=11)

    result = _execute(snapshot, action, feedback, command_version=11)

    _assert_rejected(result, feedback, "stale_command_version")


def test_missing_ack_is_not_applied_and_preserves_feedback() -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.ZOOM)
    feedback = _feedback(snapshot, last_version=4)

    result = _execute(snapshot, action, feedback, fault=ActiveVisionCameraFault.ACK_MISSING)

    assert result.outcome is ActiveVisionCameraExecutionOutcome.MISSING
    assert result.applied is False
    assert result.reason == "runtime_ack_missing"
    assert result.runtime_ack is None
    assert result.camera_feedback is feedback
    assert result.camera_feedback.last_accepted_command_version == 4


@pytest.mark.parametrize(
    "fault",
    [ActiveVisionCameraFault.CAMERA_BUSY, ActiveVisionCameraFault.ACK_MISSING],
)
def test_rejected_and_missing_results_fit_existing_episode_sample_contract(
    fault: ActiveVisionCameraFault,
) -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.WIDE)
    result = _execute(snapshot, action, _feedback(snapshot), fault=fault)
    decision = ActiveVisionDecisionV1(
        requested_mode=ActiveVisionRuntimeMode.DISABLED,
        effective_mode=ActiveVisionRuntimeMode.DISABLED,
        rule_action=action,
        requested_action=None,
        effective_action=action,
        fallback_reason="learning_disabled",
        inference_latency_ms=0.0,
        model_fingerprint=None,
        plan_version=snapshot.plan.plan_version,
        coalition_version=snapshot.plan.coalition_version,
        communication_version=snapshot.communication.communication_version,
    )

    sample = active_vision_sample_from_decision(
        sample_key="sample-000",
        observation_key="observation-000",
        sequence_index=0,
        camera_id="CAM-0",
        snapshot=snapshot,
        decision=decision,
        camera_feedback=result.camera_feedback,
        runtime_ack=result.runtime_ack,
    )

    assert sample.runtime_ack == result.runtime_ack
    assert sample.camera_feedback == result.camera_feedback


def test_truth_like_action_payload_fails_before_execution() -> None:
    snapshot = _snapshot()
    action = replace(
        _action(snapshot, ActiveVisionIntent.HOLD, ActiveVisionFovMode.WIDE),
        reason="actor-001",
    )

    with pytest.raises(ValueError, match="forbidden truth/actor/object identity"):
        _execute(snapshot, action, _feedback(snapshot))


def test_executor_is_deterministic_and_does_not_mutate_inputs() -> None:
    snapshot = _snapshot()
    action = _action(snapshot, ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionFovMode.ZOOM)
    feedback = _feedback(snapshot, last_version=3)
    original_camera = feedback.camera_state

    first = _execute(snapshot, action, feedback)
    second = _execute(snapshot, action, feedback)

    assert first == second
    assert snapshot.camera("CAM-0") == original_camera
    assert feedback.camera_state == original_camera
    assert feedback.last_accepted_command_version == 3
    assert first.camera_feedback is not feedback


def _assert_rejected(result, original_feedback, reason: str) -> None:
    assert result.outcome is ActiveVisionCameraExecutionOutcome.REJECTED
    assert result.applied is False
    assert result.reason == reason
    assert result.runtime_ack is not None
    assert result.runtime_ack.accepted is False
    assert result.runtime_ack.status_code == f"rejected_{reason}"
    assert result.camera_feedback is original_feedback
