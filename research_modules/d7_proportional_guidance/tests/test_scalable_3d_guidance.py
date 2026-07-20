from __future__ import annotations

import numpy as np
import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    AssignmentPairGuidanceInput3D,
    D4GuidancePermission,
    GuidanceMode3D,
    ScalableGuidanceConfig3D,
    ScalableGuidanceController3D,
    TerminalVisualObservation3D,
)
from research_modules.scalable_3d_simulation.dynamics import integrate_point_masses
from research_modules.scalable_3d_simulation.models import KinematicLimits
from research_modules.d2_data_association.d2_data_association.scalable_3d_models import (
    GlobalTrack3D,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.models import (
    AssignmentGuidanceBinding as D3AssignmentGuidanceBinding,
)


PLAN_ID = "plan-scalable-3d"
CAMERA_TO_NED = np.array(
    [
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=float,
)
CAMERA_K = np.array(
    [
        [320.0, 0.0, 320.0],
        [0.0, 320.0, 240.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=float,
)


def _binding(resource_id: str, target_id: str, version: int = 1) -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id=PLAN_ID,
        plan_version=version,
        resource_id=resource_id,
        vehicle_name=resource_id,
        assigned_global_track_id=target_id,
        track_version=version,
        authorization_state="recorded",
        owner_node_id="center",
        assignment_id=f"{PLAN_ID}:{resource_id}:{target_id}",
    )


def _track(target_id: str, state: np.ndarray, timestamp_s: float) -> dict[str, object]:
    return {
        "global_track_id": target_id,
        "state": np.asarray(state, dtype=float),
        "covariance": np.eye(6, dtype=float),
        "timestamp": timestamp_s,
        "lifecycle_state": "confirmed",
    }


def _association(
    resource_id: str,
    target_id: str,
    *,
    version: int = 1,
    decision_state: str = "locked",
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "assigned_global_track_id": target_id,
        "local_track_id": f"{resource_id}:camera-track",
        "association_confidence": 0.95,
        "friend_conflict_state": "none",
        "decision_state": decision_state,
        "assignment_version": version,
        "plan_id": PLAN_ID,
        "plan_version": version,
        "resource_id": resource_id,
        "metadata": dict(metadata or {}),
    }


def _visual(
    target_id: str,
    resource_id: str,
    timestamp_s: float,
    half_size_px: float,
    *,
    center_px: tuple[float, float] = (320.0, 240.0),
) -> TerminalVisualObservation3D:
    center_x, center_y = center_px
    return TerminalVisualObservation3D(
        timestamp_s=timestamp_s,
        bbox_xyxy=(
            center_x - half_size_px,
            center_y - half_size_px,
            center_x + half_size_px,
            center_y + half_size_px,
        ),
        image_width_px=640,
        image_height_px=480,
        camera_intrinsics=CAMERA_K,
        camera_to_ned_rotation=CAMERA_TO_NED,
        detection_confidence=0.95,
        local_track_id=f"{resource_id}:camera-track",
        assigned_global_track_id=target_id,
        camera_id=f"{resource_id}:front_center",
    )


def _pair_input(
    *,
    resource_index: int,
    resource_id: str,
    target_id: str,
    resource_state: np.ndarray,
    target_state: np.ndarray,
    timestamp_s: float,
    version: int = 1,
    active_plan_version: int | None = None,
    association: dict[str, object] | None = None,
    visual: TerminalVisualObservation3D | None = None,
    permission: D4GuidancePermission | None = None,
    camera_recognition_ready: bool | None = None,
    available_accel_mps2: float | None = None,
) -> AssignmentPairGuidanceInput3D:
    return AssignmentPairGuidanceInput3D(
        resource_index=resource_index,
        resource_state=np.asarray(resource_state, dtype=float),
        global_track=_track(target_id, target_state, timestamp_s),
        binding=_binding(resource_id, target_id, version),
        d4_permission=permission or D4GuidancePermission(action="continue_center"),
        terminal_association=association,
        active_plan_id=PLAN_ID,
        active_plan_version=(version if active_plan_version is None else active_plan_version),
        timestamp_s=timestamp_s,
        visual_observation=visual,
        camera_recognition_ready=camera_recognition_ready,
        available_accel_mps2=available_accel_mps2,
    )


def _warm_terminal_visual(
    controller: ScalableGuidanceController3D,
    *,
    association_metadata: dict[str, object] | None = None,
    camera_recognition_ready: bool | None = True,
    available_accel_mps2: float | None = None,
) -> tuple[object, np.ndarray, np.ndarray]:
    resource_id = "INT-0001"
    target_id = "GT-0001"
    resource_state = np.array([0.0, 0.0, -40.0, 4.0, 0.0, 0.0])
    target_state = np.array([50.0, 0.0, -40.0, 0.0, 0.0, 0.0])
    output = None
    for frame_index, half_size in enumerate((10.0, 13.0, 17.0)):
        timestamp_s = 0.1 * frame_index
        association = _association(
            resource_id,
            target_id,
            metadata=association_metadata,
        )
        output = controller.command_pair(
            _pair_input(
                resource_index=0,
                resource_id=resource_id,
                target_id=target_id,
                resource_state=resource_state,
                target_state=target_state,
                timestamp_s=timestamp_s,
                association=association,
                visual=_visual(target_id, resource_id, timestamp_s, half_size),
                camera_recognition_ready=camera_recognition_ready,
                available_accel_mps2=available_accel_mps2,
            )
        )
    assert output is not None
    return output, resource_state, target_state


def test_single_pair_is_deterministic_and_emits_bounded_3d_midcourse_command() -> None:
    pair_input = _pair_input(
        resource_index=0,
        resource_id="INT-0001",
        target_id="GT-0001",
        resource_state=np.array([0.0, 0.0, -20.0, 3.0, 0.0, 0.0]),
        target_state=np.array([350.0, 80.0, -100.0, -2.0, 0.5, 0.0]),
        timestamp_s=0.0,
    )
    first = ScalableGuidanceController3D().command_pair(pair_input)
    second = ScalableGuidanceController3D().command_pair(pair_input)

    assert first.mode is GuidanceMode3D.MIDCOURSE_PN
    assert first.acceleration_ned_mps2 == pytest.approx(second.acceleration_ned_mps2)
    assert np.all(np.isfinite(first.acceleration_ned_mps2))
    assert 0.0 < first.command_norm_mps2 <= 16.0
    assert first.assigned_global_track_id == "GT-0001"
    assert first.metadata["global_track_id_rebound"] is False
    assert first.metadata["end_to_end_rl_used"] is False


def test_accepts_concrete_d2_six_state_track_and_d3_versioned_binding() -> None:
    d2_track = GlobalTrack3D(
        global_track_id="GT-D2-0001",
        state=np.array([320.0, 20.0, -90.0, -1.0, 0.0, 0.0]),
        covariance=np.eye(6, dtype=float),
        timestamp=0.0,
    )
    d3_binding = D3AssignmentGuidanceBinding(
        binding_id="binding-d3-0001",
        plan_id=PLAN_ID,
        plan_version=1,
        resource_id="INT-0001",
        assigned_global_track_id="GT-D2-0001",
        target_id="GT-D2-0001",
        authorization_state="recorded",
        vehicle_name="INT-0001",
        source_node_id="center",
    )
    output = ScalableGuidanceController3D().command_pair(
        AssignmentPairGuidanceInput3D(
            resource_index=0,
            resource_state=np.array([0.0, 0.0, -30.0, 3.0, 0.0, 0.0]),
            global_track=d2_track,
            binding=d3_binding,
            d4_permission=D4GuidancePermission(action="continue_center"),
            terminal_association=None,
            active_plan_id=PLAN_ID,
            active_plan_version=1,
            timestamp_s=0.0,
        )
    )

    assert output.mode is GuidanceMode3D.MIDCOURSE_PN
    assert output.assigned_global_track_id == d2_track.global_track_id
    assert output.plan_version == d3_binding.plan_version
    assert np.all(np.isfinite(output.acceleration_ned_mps2))


def test_n_pairs_keep_independent_track_filter_and_mode_state() -> None:
    controller = ScalableGuidanceController3D()
    pair_inputs = []
    for index in range(7):
        resource_id = f"INT-{index + 1:04d}"
        target_id = f"GT-{index + 1:04d}"
        pair_inputs.append(
            _pair_input(
                resource_index=index,
                resource_id=resource_id,
                target_id=target_id,
                resource_state=np.array([0.0, 20.0 * index, -30.0, 2.0, 0.0, 0.0]),
                target_state=np.array(
                    [300.0 + 10.0 * index, 20.0 * index, -40.0 - index, -1.0, 0.0, 0.0]
                ),
                timestamp_s=0.01 * index,
            )
        )

    batch = controller.command_batch(pair_inputs, resource_count=9)

    assert batch.acceleration_ned_mps2.shape == (9, 3)
    assert np.allclose(batch.acceleration_ned_mps2[7:], 0.0)
    assert len(batch.pair_commands) == 7
    for index in range(7):
        snapshot = controller.pair_state(f"INT-{index + 1:04d}", f"GT-{index + 1:04d}")
        assert snapshot is not None
        assert snapshot.track_filter_timestamp_s == pytest.approx(0.01 * index)
        assert snapshot.mode is GuidanceMode3D.MIDCOURSE_PN


def test_two_hundred_pairs_produce_finite_resource_indexed_commands() -> None:
    controller = ScalableGuidanceController3D()
    pair_inputs = []
    for index in range(200):
        angle = 2.0 * np.pi * index / 200.0
        resource_position = np.array(
            [100.0 * np.cos(angle), 100.0 * np.sin(angle), -50.0 - (index % 5)]
        )
        target_position = resource_position + np.array(
            [500.0, 25.0 * np.sin(3.0 * angle), -40.0 + (index % 11)]
        )
        pair_inputs.append(
            _pair_input(
                resource_index=index,
                resource_id=f"INT-{index + 1:04d}",
                target_id=f"GT-{index + 1:04d}",
                resource_state=np.concatenate((resource_position, np.array([3.0, 0.0, 0.0]))),
                target_state=np.concatenate((target_position, np.array([-1.0, 0.2, 0.0]))),
                timestamp_s=0.0,
            )
        )

    batch = controller.command_batch(reversed(pair_inputs), resource_count=200)
    norms = np.linalg.norm(batch.acceleration_ned_mps2, axis=1)

    assert batch.acceleration_ned_mps2.shape == (200, 3)
    assert np.all(np.isfinite(batch.acceleration_ned_mps2))
    assert np.max(norms) <= controller.config.max_accel_mps2 + 1.0e-9
    assert tuple(command.resource_index for command in batch.pair_commands) == tuple(range(200))


def test_three_dimensional_height_error_drives_ned_vertical_acceleration() -> None:
    output = ScalableGuidanceController3D().command_pair(
        _pair_input(
            resource_index=0,
            resource_id="INT-0001",
            target_id="GT-0001",
            resource_state=np.array([0.0, 0.0, -30.0, 0.0, 0.0, 0.0]),
            target_state=np.array([250.0, 0.0, -130.0, 0.0, 0.0, 0.0]),
            timestamp_s=0.0,
        )
    )

    assert output.mode is GuidanceMode3D.MIDCOURSE_PN
    assert output.acceleration_ned_mps2[2] < 0.0
    assert output.los_unit_ned[2] < 0.0
    assert output.range_m == pytest.approx(np.hypot(250.0, 100.0))


def test_locked_visual_ttc_switch_and_bounded_reacquire_coast() -> None:
    controller = ScalableGuidanceController3D()
    visual_output, resource_state, target_state = _warm_terminal_visual(controller)

    assert visual_output.mode is GuidanceMode3D.TERMINAL_VISUAL_PNG
    assert visual_output.visual_switch_allowed is True
    assert visual_output.terminal_contract_allowed is True
    assert visual_output.ttc_s is not None

    coast = controller.command_pair(
        _pair_input(
            resource_index=0,
            resource_id="INT-0001",
            target_id="GT-0001",
            resource_state=resource_state,
            target_state=target_state,
            timestamp_s=0.3,
            association=_association(
                "INT-0001",
                "GT-0001",
                decision_state="reacquire",
            ),
        )
    )
    assert coast.mode is GuidanceMode3D.TERMINAL_VISUAL_COAST
    assert coast.using_visual_coast is True
    assert coast.visual_switch_allowed is False
    assert 0.0 < coast.command_norm_mps2 < visual_output.command_norm_mps2

    controller.command_pair(
        _pair_input(
            resource_index=0,
            resource_id="INT-0001",
            target_id="GT-0001",
            resource_state=resource_state,
            target_state=target_state,
            timestamp_s=0.4,
            association=_association(
                "INT-0001",
                "GT-0001",
                decision_state="reacquire",
            ),
        )
    )
    expired = controller.command_pair(
        _pair_input(
            resource_index=0,
            resource_id="INT-0001",
            target_id="GT-0001",
            resource_state=resource_state,
            target_state=target_state,
            timestamp_s=0.5,
            association=_association(
                "INT-0001",
                "GT-0001",
                decision_state="reacquire",
            ),
        )
    )
    assert expired.mode is GuidanceMode3D.MIDCOURSE_PN
    assert expired.gate_reason == "terminal_visual_coast_expired"
    assert expired.using_visual_coast is False


def test_visual_observation_can_be_consumed_from_d5_association_metadata() -> None:
    controller = ScalableGuidanceController3D()
    output = None
    for frame_index, half_size in enumerate((10.0, 13.0, 17.0)):
        timestamp_s = 0.1 * frame_index
        visual = _visual("GT-0001", "INT-0001", timestamp_s, half_size)
        association = _association(
            "INT-0001",
            "GT-0001",
            metadata={
                "camera_recognition_ready": True,
                "visual_observation": {
                    "timestamp_s": timestamp_s,
                    "bbox_xyxy": visual.bbox_xyxy,
                    "image_width_px": visual.image_width_px,
                    "image_height_px": visual.image_height_px,
                    "camera_intrinsics": CAMERA_K,
                    "camera_to_ned_rotation": CAMERA_TO_NED,
                    "detection_confidence": visual.detection_confidence,
                    "local_track_id": visual.local_track_id,
                    "assigned_global_track_id": visual.assigned_global_track_id,
                },
            },
        )
        output = controller.command_pair(
            _pair_input(
                resource_index=0,
                resource_id="INT-0001",
                target_id="GT-0001",
                resource_state=np.array([0.0, 0.0, -40.0, 4.0, 0.0, 0.0]),
                target_state=np.array([50.0, 0.0, -40.0, 0.0, 0.0, 0.0]),
                timestamp_s=timestamp_s,
                association=association,
                visual=None,
            )
        )

    assert output is not None
    assert output.mode is GuidanceMode3D.TERMINAL_VISUAL_PNG
    assert output.visual_switch_allowed is True


@pytest.mark.parametrize(
    ("permission", "active_plan_version", "expected_reason"),
    [
        (D4GuidancePermission(action="request_center_replan"), 1, "d4_action_not_executable"),
        (D4GuidancePermission(action="degrade_to_secondary"), 1, "d4_action_not_executable"),
        (D4GuidancePermission(action="degrade_to_distributed"), 1, "d4_action_not_executable"),
        (D4GuidancePermission(action="continue_center"), 2, "stale_plan_version"),
    ],
)
def test_d4_pending_actions_and_stale_plan_fail_closed(
    permission: D4GuidancePermission,
    active_plan_version: int,
    expected_reason: str,
) -> None:
    output = ScalableGuidanceController3D().command_pair(
        _pair_input(
            resource_index=0,
            resource_id="INT-0001",
            target_id="GT-0001",
            resource_state=np.array([0.0, 0.0, -40.0, 4.0, 0.0, 0.0]),
            target_state=np.array([50.0, 0.0, -40.0, 0.0, 0.0, 0.0]),
            timestamp_s=0.0,
            association=_association("INT-0001", "GT-0001"),
            visual=_visual("GT-0001", "INT-0001", 0.0, 12.0),
            permission=permission,
            active_plan_version=active_plan_version,
        )
    )

    assert output.mode is GuidanceMode3D.HOLD
    assert output.acceleration_ned_mps2 == (0.0, 0.0, 0.0)
    assert output.visual_switch_allowed is False
    assert output.gate_reason == expected_reason


def test_nonlocked_camera_and_maneuver_gates_cannot_switch_visual_mode() -> None:
    nonlocked_controller = ScalableGuidanceController3D()
    for frame_index, half_size in enumerate((10.0, 13.0, 17.0)):
        timestamp_s = 0.1 * frame_index
        nonlocked = nonlocked_controller.command_pair(
            _pair_input(
                resource_index=0,
                resource_id="INT-0001",
                target_id="GT-0001",
                resource_state=np.array([0.0, 0.0, -40.0, 4.0, 0.0, 0.0]),
                target_state=np.array([50.0, 0.0, -40.0, 0.0, 0.0, 0.0]),
                timestamp_s=timestamp_s,
                association=_association(
                    "INT-0001",
                    "GT-0001",
                    decision_state="ambiguous",
                ),
                visual=_visual("GT-0001", "INT-0001", timestamp_s, half_size),
            )
        )
    assert nonlocked.mode is GuidanceMode3D.MIDCOURSE_PN
    assert nonlocked.gate_reason == "d5_not_locked"

    camera_output, _, _ = _warm_terminal_visual(
        ScalableGuidanceController3D(),
        camera_recognition_ready=False,
    )
    assert camera_output.mode is GuidanceMode3D.MIDCOURSE_PN
    assert camera_output.gate_reason == "camera_recognition_capability_unavailable"
    assert camera_output.visual_switch_allowed is False

    maneuver_output, _, _ = _warm_terminal_visual(
        ScalableGuidanceController3D(),
        association_metadata={"maneuver_capable": False},
    )
    assert maneuver_output.mode is GuidanceMode3D.MIDCOURSE_PN
    assert maneuver_output.gate_reason == "maneuver_capability_unavailable"
    assert maneuver_output.visual_switch_allowed is False


def test_d5_plan_version_mismatch_blocks_visual_switch_without_rebinding_identity() -> None:
    association = _association("INT-0001", "GT-0001")
    association["plan_version"] = 2
    output = ScalableGuidanceController3D().command_pair(
        _pair_input(
            resource_index=0,
            resource_id="INT-0001",
            target_id="GT-0001",
            resource_state=np.array([0.0, 0.0, -40.0, 4.0, 0.0, 0.0]),
            target_state=np.array([50.0, 0.0, -40.0, 0.0, 0.0, 0.0]),
            timestamp_s=0.0,
            association=association,
            visual=_visual("GT-0001", "INT-0001", 0.0, 12.0),
        )
    )

    assert output.mode is GuidanceMode3D.MIDCOURSE_PN
    assert output.gate_reason == "d5_plan_version_mismatch"
    assert output.assigned_global_track_id == "GT-0001"
    assert output.visual_switch_allowed is False


def test_point_mass_fixture_closes_five_meter_any_arrival_criterion() -> None:
    config = ScalableGuidanceConfig3D(
        terminal_switch_range_m=1.0,
        desired_closing_speed_mps=10.0,
        max_longitudinal_accel_mps2=8.0,
    )
    controller = ScalableGuidanceController3D(config)
    resource_state = np.array(
        [
            [-80.0, 0.0, 30.0, 0.0, 0.0, 0.0],
            [-150.0, 40.0, 60.0, 0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    target_state = np.array([0.0, 0.0, -20.0, 0.0, 0.0, 0.0], dtype=float)
    limits = KinematicLimits(
        max_speed_mps=24.0,
        max_accel_mps2=20.0,
        max_turn_rate_radps=1.5,
        max_climb_rate_mps=12.0,
    )
    dt_s = 0.05
    first_arrival_distances = None

    for step_index in range(500):
        timestamp_s = step_index * dt_s
        pair_inputs = [
            _pair_input(
                resource_index=index,
                resource_id=f"INT-{index + 1:04d}",
                target_id="GT-0001",
                resource_state=resource_state[index],
                target_state=target_state,
                timestamp_s=timestamp_s,
            )
            for index in range(2)
        ]
        batch = controller.command_batch(pair_inputs, resource_count=2)
        resource_state, _ = integrate_point_masses(
            resource_state,
            batch.to_world_acceleration(),
            dt_s=dt_s,
            limits=limits,
        )
        distances = np.linalg.norm(resource_state[:, :3] - target_state[:3], axis=1)
        if float(np.min(distances)) <= config.intercept_radius_m:
            first_arrival_distances = distances
            break

    assert first_arrival_distances is not None
    assert float(np.min(first_arrival_distances)) <= 5.0
    assert float(np.max(first_arrival_distances)) > 5.0
