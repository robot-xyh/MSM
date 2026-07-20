from __future__ import annotations

from dataclasses import dataclass

import pytest

from d5_terminal_association.active_vision import (
    ActiveVisionAction,
    ActiveVisionActionType,
    ActiveVisionObservation,
    SafeRuleScanPolicy,
    run_active_vision_step,
)


def _observation(
    *,
    confidence: float = 0.9,
    last_detection_timestamp: float | None = 9.8,
    center_id: str | None = "GT-0001",
) -> ActiveVisionObservation:
    return ActiveVisionObservation(
        camera_id="CAM-0",
        measurement_timestamp=9.8,
        arrival_timestamp=9.9,
        association_confidence=confidence,
        last_detection_timestamp=last_detection_timestamp,
        center_owned_global_track_id=center_id,
    )


def test_safe_policy_observes_only_a_fresh_center_owned_target() -> None:
    policy = SafeRuleScanPolicy()
    action = policy.select_action(
        _observation(),
        current_timestamp=10.0,
        center_owned_global_track_ids=("GT-0001", "GT-0002"),
    )
    assert action.action_type is ActiveVisionActionType.OBSERVE_TARGET
    assert action.target_global_track_id == "GT-0001"
    assert action.search_sector_deg is None


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (_observation(confidence=0.2), "low_association_confidence"),
        (_observation(last_detection_timestamp=8.0), "observation_timeout"),
        (_observation(center_id="GT-STALE"), "center_binding_unavailable"),
    ],
)
def test_timeout_low_confidence_or_invalid_binding_falls_back_to_rule_scan(
    observation: ActiveVisionObservation,
    reason: str,
) -> None:
    policy = SafeRuleScanPolicy()
    action = policy.select_action(
        observation,
        current_timestamp=10.0,
        center_owned_global_track_ids=("GT-0001",),
    )
    assert action.action_type is ActiveVisionActionType.SEARCH_SECTOR
    assert action.target_global_track_id is None
    assert action.search_sector_deg is not None
    assert reason in action.reason


def test_camera_action_envelope_clips_gimbal_fov_and_zoom() -> None:
    policy = SafeRuleScanPolicy()
    gimbal = policy.bounded_gimbal_increment(
        camera_id="CAM-0",
        current_timestamp=10.0,
        yaw_delta_deg=100.0,
        pitch_delta_deg=-100.0,
    )
    assert gimbal.action_type is ActiveVisionActionType.GIMBAL_INCREMENT
    assert gimbal.gimbal_increment_deg == (8.0, -8.0)

    optics = policy.bounded_fov_zoom(
        camera_id="CAM-0",
        current_timestamp=10.0,
        horizontal_fov_deg=200.0,
        zoom_ratio=30.0,
    )
    assert optics.action_type is ActiveVisionActionType.SET_FOV_ZOOM
    assert optics.horizontal_fov_deg == 120.0
    assert optics.zoom_ratio == 12.0
    assert {item.value for item in ActiveVisionActionType} == {
        "observe_target",
        "search_sector",
        "gimbal_increment",
        "set_fov_zoom",
    }

    with pytest.raises(ValueError, match="outside its action type"):
        ActiveVisionAction(
            action_type=ActiveVisionActionType.OBSERVE_TARGET,
            camera_id="CAM-0",
            issued_timestamp=10.0,
            target_global_track_id="GT-0001",
            gimbal_increment_deg=(1.0, 1.0),
        )


@dataclass
class _FakeEnvironment:
    observation: ActiveVisionObservation
    last_action: ActiveVisionAction | None = None

    def observe(self, camera_id: str) -> ActiveVisionObservation:
        assert camera_id == self.observation.camera_id
        return self.observation

    def apply_camera_action(self, action: ActiveVisionAction) -> ActiveVisionObservation:
        self.last_action = action
        return self.observation


def test_environment_policy_step_exposes_only_camera_action() -> None:
    environment = _FakeEnvironment(_observation(confidence=0.1))
    action, next_observation = run_active_vision_step(
        environment,
        SafeRuleScanPolicy(),
        camera_id="CAM-0",
        current_timestamp=10.0,
        center_owned_global_track_ids=("GT-0001",),
    )
    assert action is environment.last_action
    assert action.action_type is ActiveVisionActionType.SEARCH_SECTOR
    assert next_observation is environment.observation


class _UnsafePolicy:
    def select_action(
        self,
        observation: ActiveVisionObservation,
        *,
        current_timestamp: float,
        center_owned_global_track_ids: tuple[str, ...],
    ) -> ActiveVisionAction:
        return ActiveVisionAction(
            action_type=ActiveVisionActionType.OBSERVE_TARGET,
            camera_id=observation.camera_id,
            issued_timestamp=current_timestamp,
            target_global_track_id="GT-NOT-CENTER-OWNED",
        )


def test_environment_rejects_custom_policy_identity_outside_center_set() -> None:
    environment = _FakeEnvironment(_observation())
    with pytest.raises(ValueError, match="center-owned"):
        run_active_vision_step(
            environment,
            _UnsafePolicy(),
            camera_id="CAM-0",
            current_timestamp=10.0,
            center_owned_global_track_ids=("GT-0001",),
        )
    assert environment.last_action is None
