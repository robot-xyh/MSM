from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    AssignmentPairGuidanceInput3D,
    D4GuidancePermission,
    GuidanceMode3D,
    ScalableGuidanceController3D,
    TerminalVisualObservation3D,
)
from d7_proportional_guidance.pair_lifecycle_benchmark import (
    PAIR_LIFECYCLE_BENCHMARK_SCHEMA,
    run_pair_lifecycle_frozen_benchmark,
)


PLAN_ID = "plan-lifecycle-test"
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


def test_batch_reconciles_plan_upgrade_rebind_lost_track_and_withdrawal() -> None:
    controller = ScalableGuidanceController3D()
    initial = [_pair_input(index=index, version=1) for index in range(3)]

    created = controller.command_batch(initial, resource_count=3)
    assert created.lifecycle_diagnostics is not None
    assert created.lifecycle_diagnostics.created_count == 3
    assert created.lifecycle_diagnostics.active_state_count == 3

    reused = controller.command_batch(
        [_pair_input(index=index, version=1, timestamp_s=0.1) for index in range(3)],
        resource_count=3,
    )
    assert reused.lifecycle_diagnostics is not None
    assert reused.lifecycle_diagnostics.reused_count == 3

    upgraded = controller.command_batch(
        [_pair_input(index=index, version=2, timestamp_s=0.2) for index in range(3)],
        resource_count=3,
    )
    assert upgraded.lifecycle_diagnostics is not None
    assert upgraded.lifecycle_diagnostics.reset_count == 3
    assert upgraded.lifecycle_diagnostics.reset_reasons == {
        "plan_version_changed": 3
    }

    lifecycle = controller.command_batch(
        [
            _pair_input(
                index=0,
                target_id="GT-REBOUND",
                version=3,
                timestamp_s=0.3,
            ),
            _pair_input(
                index=1,
                version=3,
                timestamp_s=0.3,
                lifecycle_state="lost",
            ),
        ],
        resource_count=3,
    )
    diagnostics = lifecycle.lifecycle_diagnostics
    assert diagnostics is not None
    assert diagnostics.active_pair_count == 1
    assert diagnostics.active_state_count == 1
    assert diagnostics.created_count == 1
    assert diagnostics.reclaimed_count == 3
    assert diagnostics.reclaim_reasons == {
        "resource_rebound": 1,
        "global_track_not_usable": 1,
        "assignment_withdrawn": 1,
    }
    assert controller.pair_state("INT-0001", "GT-0001") is None
    assert controller.pair_state("INT-0002", "GT-0002") is None
    assert controller.pair_state("INT-0003", "GT-0003") is None
    assert controller.pair_state("INT-0001", "GT-REBOUND") is not None
    assert diagnostics.global_track_id_rewrite_count == 0
    assert diagnostics.nonfinite_command_block_count == 0

    duplicate_resource = replace(
        _pair_input(index=1, target_id="GT-DUPLICATE", version=3, timestamp_s=0.4),
        binding=replace(
            _pair_input(index=1, version=3).binding,
            resource_id="INT-0001",
            assigned_global_track_id="GT-DUPLICATE",
        ),
    )
    with pytest.raises(
        ValueError,
        match="each resource_id may appear at most once per batch",
    ):
        controller.command_batch(
            [
                _pair_input(
                    index=0,
                    target_id="GT-REBOUND",
                    version=3,
                    timestamp_s=0.4,
                ),
                duplicate_resource,
            ],
            resource_count=3,
        )
    assert controller.active_pair_state_count == 1


@pytest.mark.parametrize(
    ("binding_changes", "permission", "expected_reason"),
    [
        (
            {"assignment_validity_state": "revoked"},
            D4GuidancePermission(action="continue_center"),
            "assignment_revoked",
        ),
        (
            {"expires_at_s": 0.05},
            D4GuidancePermission(action="continue_center"),
            "assignment_expired",
        ),
        (
            {},
            D4GuidancePermission(action="revoke"),
            "d4_assignment_revoked",
        ),
        (
            {},
            D4GuidancePermission(action="continue_center", reason="revoked"),
            "d4_assignment_revoked",
        ),
    ],
)
def test_explicit_assignment_revocation_expiry_and_d4_revoke_reclaim_state(
    binding_changes: dict[str, object],
    permission: D4GuidancePermission,
    expected_reason: str,
) -> None:
    controller = ScalableGuidanceController3D()
    initial_input = _pair_input(index=0)
    controller.command_batch([initial_input], resource_count=1)

    invalid_input = replace(
        _pair_input(index=0, timestamp_s=0.1),
        binding=replace(initial_input.binding, **binding_changes),
        d4_permission=permission,
    )
    batch = controller.command_batch([invalid_input], resource_count=1)
    diagnostics = batch.lifecycle_diagnostics

    assert diagnostics is not None
    assert diagnostics.active_pair_count == 0
    assert diagnostics.active_state_count == 0
    assert diagnostics.reclaimed_count == 1
    assert diagnostics.reclaim_reasons == {expected_reason: 1}
    assert controller.pair_state("INT-0001", "GT-0001") is None


def test_transient_d4_d5_and_visual_dropout_preserve_same_pair_filters() -> None:
    controller = ScalableGuidanceController3D()
    for frame_index, half_size_px in enumerate((10.0, 13.0, 17.0)):
        controller.command_batch(
            [
                _pair_input(
                    index=0,
                    timestamp_s=0.1 * frame_index,
                    association=_association(decision_state="locked"),
                    visual=_visual(0.1 * frame_index, half_size_px),
                )
            ],
            resource_count=1,
        )

    before = controller.pair_state("INT-0001", "GT-0001")
    assert before is not None
    assert before.los_filter_initialized is True
    assert before.last_visual_command_timestamp_s is not None

    pending = controller.command_batch(
        [
            _pair_input(
                index=0,
                timestamp_s=0.25,
                association=_association(decision_state="locked"),
                visual=_visual(0.25, 18.0),
                permission=D4GuidancePermission(action="request_center_replan"),
            )
        ],
        resource_count=1,
    )
    assert pending.pair_commands[0].mode is GuidanceMode3D.HOLD
    assert pending.lifecycle_diagnostics is not None
    assert pending.lifecycle_diagnostics.reused_count == 1
    _assert_visual_state_retained(before, controller)

    reacquire = controller.command_batch(
        [
            _pair_input(
                index=0,
                timestamp_s=0.3,
                association=_association(decision_state="reacquire"),
            )
        ],
        resource_count=1,
    )
    assert reacquire.pair_commands[0].mode in {
        GuidanceMode3D.TERMINAL_VISUAL_COAST,
        GuidanceMode3D.MIDCOURSE_PN,
    }
    _assert_visual_state_retained(before, controller)

    reacquire_with_detection = controller.command_batch(
        [
            _pair_input(
                index=0,
                timestamp_s=0.35,
                association=_association(decision_state="reacquire"),
                visual=_visual(0.35, 19.0),
            )
        ],
        resource_count=1,
    )
    assert reacquire_with_detection.pair_commands[0].gate_reason == "d5_not_locked"
    _assert_visual_state_retained(before, controller)

    locked_dropout = controller.command_batch(
        [
            _pair_input(
                index=0,
                timestamp_s=0.4,
                association=_association(decision_state="locked"),
            )
        ],
        resource_count=1,
    )
    assert (
        locked_dropout.pair_commands[0].gate_reason
        == "visual_observation_missing"
    )
    _assert_visual_state_retained(before, controller)

    recovered = controller.command_batch(
        [
            _pair_input(
                index=0,
                timestamp_s=0.45,
                association=_association(decision_state="locked"),
                visual=_visual(0.45, 21.0),
            )
        ],
        resource_count=1,
    )
    assert recovered.pair_commands[0].mode is GuidanceMode3D.TERMINAL_VISUAL_PNG
    assert controller.active_pair_state_count == 1

    expired_dropout = controller.command_batch(
        [
            _pair_input(
                index=0,
                timestamp_s=0.8,
                association=_association(decision_state="locked"),
            )
        ],
        resource_count=1,
    )
    assert expired_dropout.pair_commands[0].gate_reason == "visual_observation_missing"
    expired_state = controller.pair_state("INT-0001", "GT-0001")
    assert expired_state is not None
    assert expired_state.los_filter_initialized is False
    assert expired_state.ttc_sample_count == 0


def test_two_hundred_pair_frozen_lifecycle_benchmark() -> None:
    result = run_pair_lifecycle_frozen_benchmark(pair_count=200)

    assert result.schema == PAIR_LIFECYCLE_BENCHMARK_SCHEMA
    assert result.pair_count == 200
    assert result.batch_count == 9
    assert result.final_valid_pair_count == 170
    assert result.final_active_state_count == 170
    assert result.peak_active_state_count == 200
    assert result.state_bound_violation_count == 0
    assert result.transient_state_preserved is True
    assert result.old_state_reclaim_verified is True
    assert result.stale_plan_reject_count == 10
    assert result.stale_plan_accept_count == 0
    assert result.global_track_id_rewrite_count == 0
    assert result.nonfinite_command_block_count == 0
    assert result.created_count == 250
    assert result.reused_count == 1120
    assert result.reset_count == 330
    assert result.reclaimed_count == 80
    assert result.reset_reasons == {"plan_version_changed": 330}
    assert result.reclaim_reasons == {
        "resource_rebound": 40,
        "global_track_not_usable": 10,
        "assignment_withdrawn": 20,
        "stale_plan_version": 10,
    }
    assert result.mode_counts[GuidanceMode3D.MIDCOURSE_PN.value] > 0
    assert result.mode_counts[GuidanceMode3D.TERMINAL_VISUAL_PNG.value] > 0
    assert result.mode_counts[GuidanceMode3D.TERMINAL_VISUAL_COAST.value] > 0
    assert result.mode_counts[GuidanceMode3D.HOLD.value] > 0
    assert np.isfinite(result.pair_latency_p95_ms)
    assert result.pair_latency_p95_ms > 0.0
    assert np.isfinite(result.batch_latency_p95_ms)
    assert result.batch_latency_p95_ms > 0.0
    assert result.peak_traced_memory_bytes > 0


def _assert_visual_state_retained(
    before: object,
    controller: ScalableGuidanceController3D,
) -> None:
    after = controller.pair_state("INT-0001", "GT-0001")
    assert after is not None
    assert after.los_filter_initialized is True
    assert after.ttc_sample_count == before.ttc_sample_count
    assert (
        after.last_visual_command_timestamp_s
        == before.last_visual_command_timestamp_s
    )


def _pair_input(
    *,
    index: int,
    version: int = 1,
    target_id: str | None = None,
    timestamp_s: float = 0.0,
    lifecycle_state: str = "confirmed",
    association: dict[str, object] | None = None,
    visual: TerminalVisualObservation3D | None = None,
    permission: D4GuidancePermission | None = None,
) -> AssignmentPairGuidanceInput3D:
    resource_id = f"INT-{index + 1:04d}"
    target_id = target_id or f"GT-{index + 1:04d}"
    binding = AssignmentGuidanceBinding(
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
    if association is not None:
        association = {
            **association,
            "assigned_global_track_id": target_id,
            "local_track_id": f"{resource_id}:camera-track",
            "assignment_version": version,
            "plan_id": PLAN_ID,
            "plan_version": version,
            "resource_id": resource_id,
        }
    if visual is not None:
        visual = replace(
            visual,
            local_track_id=f"{resource_id}:camera-track",
            assigned_global_track_id=target_id,
            camera_id=f"{resource_id}:front_center",
        )
    return AssignmentPairGuidanceInput3D(
        resource_index=index,
        resource_state=np.array([0.0, float(index), -40.0, 4.0, 0.0, 0.0]),
        global_track={
            "global_track_id": target_id,
            "state": np.array(
                [50.0, float(index), -40.0, 0.0, 0.0, 0.0],
                dtype=float,
            ),
            "covariance": np.eye(6, dtype=float),
            "timestamp": timestamp_s,
            "lifecycle_state": lifecycle_state,
        },
        binding=binding,
        d4_permission=permission or D4GuidancePermission(action="continue_center"),
        terminal_association=association,
        active_plan_id=PLAN_ID,
        active_plan_version=version,
        timestamp_s=timestamp_s,
        visual_observation=visual,
        camera_recognition_ready=True,
    )


def _association(*, decision_state: str) -> dict[str, object]:
    return {
        "association_confidence": 0.95,
        "friend_conflict_state": "none",
        "decision_state": decision_state,
        "metadata": {"camera_recognition_ready": True, "maneuver_capable": True},
    }


def _visual(timestamp_s: float, half_size_px: float) -> TerminalVisualObservation3D:
    return TerminalVisualObservation3D(
        timestamp_s=timestamp_s,
        bbox_xyxy=(
            320.0 - half_size_px,
            240.0 - half_size_px,
            320.0 + half_size_px,
            240.0 + half_size_px,
        ),
        image_width_px=640,
        image_height_px=480,
        camera_intrinsics=CAMERA_K,
        camera_to_ned_rotation=CAMERA_TO_NED,
        detection_confidence=0.95,
    )
