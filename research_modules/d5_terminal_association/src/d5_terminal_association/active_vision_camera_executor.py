"""Deterministic, fail-closed execution of D5 active-vision camera intents.

The executor has no command authority of its own.  It applies one already
selected :class:`ActiveVisionActionV1` to explicit camera feedback after the
existing D5 safety validator accepts the action.  Missing acknowledgement is
kept distinct from successful application and leaves the supplied feedback
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Any

from .active_vision_contracts import (
    ActiveVisionActionV1,
    ActiveVisionCameraState,
    ActiveVisionIntent,
    ActiveVisionSafetyConfigV1,
    ActiveVisionSnapshotV1,
    assert_truth_free_active_vision_payload,
    validate_active_vision_action_v1,
)
from .active_vision_episode_dataset import (
    ActiveVisionCameraFeedbackV1,
    ActiveVisionRuntimeAckV1,
)


ACTIVE_VISION_CAMERA_EXECUTION_SCHEMA_VERSION = "d5.active-vision-camera-execution.v1"


class ActiveVisionCameraExecutionOutcome(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"
    MISSING = "missing"


class ActiveVisionCameraFault(str, Enum):
    """Explicit test/runtime fault inputs; none can make an unsafe action valid."""

    NONE = "none"
    CAMERA_BUSY = "camera_busy"
    CAMERA_UNAVAILABLE = "camera_unavailable"
    ACK_MISSING = "ack_missing"


@dataclass(frozen=True)
class ActiveVisionCameraExecutionResult:
    outcome: ActiveVisionCameraExecutionOutcome
    reason: str
    command_version: int
    camera_feedback: ActiveVisionCameraFeedbackV1
    runtime_ack: ActiveVisionRuntimeAckV1 | None
    schema_version: str = ACTIVE_VISION_CAMERA_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_CAMERA_EXECUTION_SCHEMA_VERSION:
            raise ValueError("active-vision camera execution schema mismatch")
        outcome = ActiveVisionCameraExecutionOutcome(self.outcome)
        command_version = _non_negative_integer(self.command_version, "command_version")
        reason = str(self.reason).strip()
        if not reason:
            raise ValueError("camera execution reason must be non-empty")
        if not isinstance(self.camera_feedback, ActiveVisionCameraFeedbackV1):
            raise TypeError("camera_feedback must be ActiveVisionCameraFeedbackV1")
        ack = self.runtime_ack
        if outcome is ActiveVisionCameraExecutionOutcome.APPLIED:
            if ack is None or not ack.accepted or ack.status_code != "applied":
                raise ValueError("applied execution requires an accepted applied ACK")
            if self.camera_feedback.last_accepted_command_version != command_version:
                raise ValueError("applied feedback must expose the accepted command version")
        elif outcome is ActiveVisionCameraExecutionOutcome.REJECTED:
            if ack is None or ack.accepted or not ack.status_code.startswith("rejected_"):
                raise ValueError("rejected execution requires an explicit rejected ACK")
        elif ack is not None:
            raise ValueError("missing execution must not contain a runtime ACK")
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "command_version", command_version)

    @property
    def applied(self) -> bool:
        return self.outcome is ActiveVisionCameraExecutionOutcome.APPLIED


class DeterministicCameraCommandExecutor:
    """Apply one bounded camera action without retaining hidden runtime state."""

    def __init__(self, config: ActiveVisionSafetyConfigV1 | None = None) -> None:
        self.config = config or ActiveVisionSafetyConfigV1()

    def execute(
        self,
        snapshot: ActiveVisionSnapshotV1,
        action: ActiveVisionActionV1,
        camera_feedback: ActiveVisionCameraFeedbackV1,
        *,
        sample_key: str,
        command_version: int,
        execution_timestamp: float,
        expected_plan_version: int,
        expected_coalition_version: int,
        expected_communication_version: int,
        fault: ActiveVisionCameraFault | str = ActiveVisionCameraFault.NONE,
    ) -> ActiveVisionCameraExecutionResult:
        """Validate, then apply or reject one camera command deterministically."""

        if not isinstance(snapshot, ActiveVisionSnapshotV1):
            raise TypeError("snapshot must be ActiveVisionSnapshotV1")
        if not isinstance(action, ActiveVisionActionV1):
            raise TypeError("action must be ActiveVisionActionV1")
        if not isinstance(camera_feedback, ActiveVisionCameraFeedbackV1):
            raise TypeError("camera_feedback must be ActiveVisionCameraFeedbackV1")
        assert_truth_free_active_vision_payload(
            {
                "snapshot": snapshot,
                "action": action,
                "camera_feedback": camera_feedback,
            }
        )
        now = _finite(execution_timestamp, "execution_timestamp")
        version = _non_negative_integer(command_version, "command_version")
        selected_fault = ActiveVisionCameraFault(fault)

        # This validator is the authoritative D5 safety envelope.  Runtime
        # feedback checks below can only reject additional cases.
        reason = validate_active_vision_action_v1(
            action,
            snapshot,
            camera_id=action.camera_id,
            current_timestamp=now,
            expected_plan_version=expected_plan_version,
            expected_coalition_version=expected_coalition_version,
            expected_communication_version=expected_communication_version,
            config=self.config,
        )
        if reason is not None:
            return self._rejected(
                action,
                camera_feedback,
                sample_key=sample_key,
                command_version=version,
                execution_timestamp=now,
                reason=reason,
            )

        reason = _feedback_failure(snapshot, action, camera_feedback, now)
        if reason is None:
            runtime_snapshot = _snapshot_with_runtime_camera(snapshot, camera_feedback.camera_state)
            reason = validate_active_vision_action_v1(
                action,
                runtime_snapshot,
                camera_id=action.camera_id,
                current_timestamp=now,
                expected_plan_version=expected_plan_version,
                expected_coalition_version=expected_coalition_version,
                expected_communication_version=expected_communication_version,
                config=self.config,
            )
        if reason is None:
            accepted_version = camera_feedback.last_accepted_command_version
            if accepted_version is not None and version <= accepted_version:
                reason = "stale_command_version"
        if reason is None and selected_fault is ActiveVisionCameraFault.CAMERA_BUSY:
            reason = "gimbal_busy"
        if reason is None and selected_fault is ActiveVisionCameraFault.CAMERA_UNAVAILABLE:
            reason = "camera_unavailable"
        if reason is not None:
            return self._rejected(
                action,
                camera_feedback,
                sample_key=sample_key,
                command_version=version,
                execution_timestamp=now,
                reason=reason,
            )
        if selected_fault is ActiveVisionCameraFault.ACK_MISSING:
            return ActiveVisionCameraExecutionResult(
                outcome=ActiveVisionCameraExecutionOutcome.MISSING,
                reason="runtime_ack_missing",
                command_version=version,
                camera_feedback=camera_feedback,
                runtime_ack=None,
            )

        updated_feedback = _apply_action(
            action,
            camera_feedback,
            execution_timestamp=now,
            command_version=version,
        )
        ack = _ack(
            action,
            sample_key=sample_key,
            command_version=version,
            execution_timestamp=now,
            accepted=True,
            status_code="applied",
        )
        return ActiveVisionCameraExecutionResult(
            outcome=ActiveVisionCameraExecutionOutcome.APPLIED,
            reason="applied",
            command_version=version,
            camera_feedback=updated_feedback,
            runtime_ack=ack,
        )

    @staticmethod
    def _rejected(
        action: ActiveVisionActionV1,
        camera_feedback: ActiveVisionCameraFeedbackV1,
        *,
        sample_key: str,
        command_version: int,
        execution_timestamp: float,
        reason: str,
    ) -> ActiveVisionCameraExecutionResult:
        stable_reason = _status_token(reason)
        ack = _ack(
            action,
            sample_key=sample_key,
            command_version=command_version,
            execution_timestamp=execution_timestamp,
            accepted=False,
            status_code=f"rejected_{stable_reason}",
        )
        return ActiveVisionCameraExecutionResult(
            outcome=ActiveVisionCameraExecutionOutcome.REJECTED,
            reason=stable_reason,
            command_version=command_version,
            camera_feedback=camera_feedback,
            runtime_ack=ack,
        )


def _feedback_failure(
    snapshot: ActiveVisionSnapshotV1,
    action: ActiveVisionActionV1,
    feedback: ActiveVisionCameraFeedbackV1,
    now: float,
) -> str | None:
    snapshot_camera = snapshot.camera(action.camera_id)
    runtime_camera = feedback.camera_state
    if (
        runtime_camera.camera_id != snapshot_camera.camera_id
        or runtime_camera.resource_id != snapshot_camera.resource_id
    ):
        return "camera_feedback_membership_mismatch"
    if runtime_camera.state_timestamp + 1.0e-9 < snapshot_camera.state_timestamp:
        return "camera_feedback_stale"
    if runtime_camera.state_timestamp > now + 1.0e-9:
        return "camera_feedback_from_future"
    return None


def _snapshot_with_runtime_camera(
    snapshot: ActiveVisionSnapshotV1,
    runtime_camera: ActiveVisionCameraState,
) -> ActiveVisionSnapshotV1:
    cameras = tuple(
        runtime_camera if item.camera_id == runtime_camera.camera_id else item
        for item in snapshot.cameras
    )
    return replace(snapshot, cameras=cameras)


def _apply_action(
    action: ActiveVisionActionV1,
    feedback: ActiveVisionCameraFeedbackV1,
    *,
    execution_timestamp: float,
    command_version: int,
) -> ActiveVisionCameraFeedbackV1:
    state = feedback.camera_state
    busy_until = (
        state.action_in_progress_until
        if action.intent is ActiveVisionIntent.HOLD
        else None
    )
    updated_state = replace(
        state,
        state_timestamp=execution_timestamp,
        yaw_deg=state.yaw_deg + action.yaw_delta_deg,
        pitch_deg=state.pitch_deg + action.pitch_delta_deg,
        yaw_rate_deg_s=0.0,
        pitch_rate_deg_s=0.0,
        current_fov_mode=action.fov_mode,
        action_in_progress_until=busy_until,
    )
    return ActiveVisionCameraFeedbackV1(
        camera_state=updated_state,
        last_accepted_command_version=command_version,
    )


def _ack(
    action: ActiveVisionActionV1,
    *,
    sample_key: str,
    command_version: int,
    execution_timestamp: float,
    accepted: bool,
    status_code: str,
) -> ActiveVisionRuntimeAckV1:
    return ActiveVisionRuntimeAckV1(
        sample_key=sample_key,
        camera_id=action.camera_id,
        command_version=command_version,
        ack_timestamp=execution_timestamp,
        accepted=accepted,
        status_code=status_code,
        plan_version=action.plan_version,
        coalition_version=action.coalition_version,
        communication_version=action.communication_version,
    )


def _status_token(value: Any) -> str:
    token = str(value).strip().lower().replace(":", "_").replace("-", "_")
    if not token or any(not (character.isalnum() or character in "._+@_") for character in token):
        raise ValueError("camera execution rejection reason is not a portable status token")
    return token


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _non_negative_integer(value: Any, name: str) -> int:
    result = int(value)
    if isinstance(value, bool) or result != value or result < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return result


__all__ = [
    "ACTIVE_VISION_CAMERA_EXECUTION_SCHEMA_VERSION",
    "ActiveVisionCameraExecutionOutcome",
    "ActiveVisionCameraExecutionResult",
    "ActiveVisionCameraFault",
    "DeterministicCameraCommandExecutor",
]
