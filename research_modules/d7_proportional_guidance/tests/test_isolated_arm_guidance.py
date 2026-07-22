from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    AssignmentPairGuidanceInput3D,
    D4GuidancePermission,
    IsolatedArmGuidanceExecutor3D,
    IsolatedGuidanceContractError,
    IsolatedGuidanceExecutionContextV1,
    TerminalVisualObservation3D,
    build_isolated_guidance_lineage_record_v1,
    summarize_isolated_guidance_commands,
    validate_isolated_guidance_command,
)


PLAN_ID = "isolated-plan"
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


def _plan(version: int = 1, *, pair_count: int = 1) -> dict[str, object]:
    return {
        "plan_id": PLAN_ID,
        "plan_version": version,
        "assignments": [
            {
                "resource_id": f"INT-{index:04d}",
                "global_track_id": f"GT-{index:06d}",
            }
            for index in range(pair_count)
        ],
        "metadata": {"owner_node_id": "center"},
    }


def _context(
    *,
    arm: str,
    timestamp_s: float,
    plan: dict[str, object] | None = None,
) -> IsolatedGuidanceExecutionContextV1:
    source_plan = plan or _plan()
    return IsolatedGuidanceExecutionContextV1.from_plan_payload(
        experiment_id="paired-rollout",
        seed=1000,
        arm_id=f"seed-1000-{arm}",
        arm_kind=arm,
        episode_id=f"episode-1000-{arm}",
        isolation_id=f"world-1000-{arm}",
        source_plan_id=str(source_plan["plan_id"]),
        source_plan_version=int(source_plan["plan_version"]),
        source_plan_payload=source_plan,
        generated_at_s=timestamp_s,
    )


def _binding(
    *,
    resource_id: str = "INT-0000",
    target_id: str = "GT-000000",
    version: int = 1,
) -> AssignmentGuidanceBinding:
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


def _track(
    target_id: str,
    timestamp_s: float,
    *,
    target_position: tuple[float, float, float] = (300.0, 20.0, -50.0),
) -> dict[str, object]:
    return {
        "global_track_id": target_id,
        "state": np.array([*target_position, -1.0, 0.0, 0.0], dtype=float),
        "covariance": np.eye(6, dtype=float),
        "timestamp": timestamp_s,
        "lifecycle_state": "confirmed",
    }


def _association(
    resource_id: str,
    target_id: str,
    *,
    version: int = 1,
) -> dict[str, object]:
    return {
        "assigned_global_track_id": target_id,
        "local_track_id": f"{resource_id}:local-1",
        "association_confidence": 0.95,
        "friend_conflict_state": "none",
        "decision_state": "locked",
        "assignment_version": version,
        "plan_id": PLAN_ID,
        "plan_version": version,
        "resource_id": resource_id,
        "metadata": {},
    }


def _visual(
    resource_id: str,
    target_id: str,
    timestamp_s: float,
    half_size_px: float,
) -> TerminalVisualObservation3D:
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
        local_track_id=f"{resource_id}:local-1",
        assigned_global_track_id=target_id,
        camera_id=f"{resource_id}:front",
    )


def _pair_input(
    *,
    timestamp_s: float,
    resource_index: int = 0,
    resource_id: str = "INT-0000",
    target_id: str = "GT-000000",
    track_target_id: str | None = None,
    version: int = 1,
    permission: D4GuidancePermission | None = None,
    terminal: bool = False,
    half_size_px: float = 12.0,
) -> AssignmentPairGuidanceInput3D:
    target_position = (50.0, 0.0, -40.0) if terminal else (300.0, 20.0, -50.0)
    return AssignmentPairGuidanceInput3D(
        resource_index=resource_index,
        resource_state=np.array([0.0, 0.0, -40.0, 4.0, 0.0, 0.0], dtype=float),
        global_track=_track(
            track_target_id or target_id,
            timestamp_s,
            target_position=target_position,
        ),
        binding=_binding(resource_id=resource_id, target_id=target_id, version=version),
        d4_permission=permission or D4GuidancePermission(action="continue_center"),
        terminal_association=(
            _association(resource_id, target_id, version=version) if terminal else None
        ),
        active_plan_id=PLAN_ID,
        active_plan_version=version,
        timestamp_s=timestamp_s,
        visual_observation=(
            _visual(resource_id, target_id, timestamp_s, half_size_px)
            if terminal
            else None
        ),
        camera_recognition_ready=True if terminal else None,
    )


def test_control_and_treatment_keep_independent_pair_filter_state() -> None:
    plan = _plan()
    control_initial = _context(arm="control", timestamp_s=0.0, plan=plan)
    treatment_initial = _context(arm="treatment", timestamp_s=0.0, plan=plan)
    control = IsolatedArmGuidanceExecutor3D(control_initial)
    treatment = IsolatedArmGuidanceExecutor3D(treatment_initial)

    last_control = None
    for frame_index, half_size in enumerate((10.0, 13.0, 17.0)):
        timestamp_s = 0.1 * frame_index
        context = _context(arm="control", timestamp_s=timestamp_s, plan=plan)
        last_control = control.command_batch(
            [_pair_input(timestamp_s=timestamp_s, terminal=True, half_size_px=half_size)],
            resource_count=1,
            context=context,
            source_plan_payload=plan,
            d5_gate_required_bindings=(("INT-0000", "GT-000000"),),
        ).command_records[0]

    treatment_context = _context(arm="treatment", timestamp_s=0.2, plan=plan)
    first_treatment = treatment.command_batch(
        [_pair_input(timestamp_s=0.2, terminal=True, half_size_px=17.0)],
        resource_count=1,
        context=treatment_context,
        source_plan_payload=plan,
        d5_gate_required_bindings=(("INT-0000", "GT-000000"),),
    ).command_records[0]

    assert last_control is not None
    assert last_control.held is False
    assert last_control.control_mode == "terminal_visual_png_3d"
    assert first_treatment.held is True
    assert first_treatment.d5_gate_passed is False
    assert control.pair_state("INT-0000", "GT-000000").visual_stable_frame_count == 3
    assert treatment.pair_state("INT-0000", "GT-000000").visual_stable_frame_count == 1


def test_isolated_wrapper_emits_two_hundred_lineage_bound_commands() -> None:
    plan = _plan(pair_count=200)
    context = _context(arm="control", timestamp_s=0.0, plan=plan)
    executor = IsolatedArmGuidanceExecutor3D(context)
    inputs = [
        _pair_input(
            timestamp_s=0.0,
            resource_index=index,
            resource_id=f"INT-{index:04d}",
            target_id=f"GT-{index:06d}",
        )
        for index in range(200)
    ]

    batch = executor.command_batch(
        reversed(inputs),
        resource_count=200,
        context=context,
        source_plan_payload=plan,
    )

    assert batch.acceleration_ned_mps2.shape == (200, 3)
    assert np.all(np.isfinite(batch.acceleration_ned_mps2))
    assert len(batch.command_records) == 200
    assert len(
        {
            record.assignment_binding.binding_payload_sha256
            for record in batch.command_records
        }
    ) == 200
    assert all(record.arm_id == "seed-1000-control" for record in batch.command_records)
    snapshots = [
        executor.pair_state(f"INT-{index:04d}", f"GT-{index:06d}")
        for index in range(200)
    ]
    assert all(snapshot is not None for snapshot in snapshots)
    assert {
        (snapshot.resource_id, snapshot.assigned_global_track_id)
        for snapshot in snapshots
        if snapshot is not None
    } == {
        (f"INT-{index:04d}", f"GT-{index:06d}")
        for index in range(200)
    }


def test_command_lineage_and_isolated_world_confirmation_are_distinct_states() -> None:
    plan = _plan()
    context = _context(arm="control", timestamp_s=0.0, plan=plan)
    executor = IsolatedArmGuidanceExecutor3D(context)
    batch = executor.command_batch(
        [_pair_input(timestamp_s=0.0)],
        resource_count=1,
        context=context,
        source_plan_payload=plan,
    )
    record = batch.command_records[0]

    generated = validate_isolated_guidance_command(record, expected_context=context)
    assert generated.valid is True
    assert generated.state == "command_generated"
    assert generated.control_applied_to_world is False
    assert record.experiment_id == "paired-rollout"
    assert record.seed == 1000
    assert record.arm_id == "seed-1000-control"
    assert record.episode_id == "episode-1000-control"
    assert record.source_plan_id == PLAN_ID
    assert len(record.source_plan_payload_sha256) == 64
    assert len(record.assignment_binding.binding_payload_sha256) == 64

    receipt = executor.confirm_world_application(
        record,
        context=context,
        world_id="world-1000-control",
        applied_at_s=0.0,
        applied_acceleration_ned_mps2=batch.acceleration_ned_mps2[0],
    )
    applied = validate_isolated_guidance_command(
        record,
        expected_context=context,
        application=receipt,
    )
    assert applied.valid is True
    assert applied.state == "control_applied_to_world"
    assert applied.control_applied_to_world is True
    assert receipt.isolated_simulation_only is True
    assert receipt.production_runtime_ack is False

    lineage = build_isolated_guidance_lineage_record_v1(
        record,
        command_id="cmd-control-0001",
        cycle_index=0,
        consumption_id="consume-control-0001",
        application=receipt,
        world_application_id="apply-control-0001",
    )
    assert set(lineage) == {
        "schema_version",
        "command_id",
        "cycle_index",
        "issued_at_s",
        "consumption_id",
        "plan_id",
        "plan_version",
        "plan_payload_sha256",
        "resource_id",
        "global_track_id",
        "command_payload_sha256",
        "command_payload",
        "control_applied_to_world",
        "world_application_id",
    }
    assert lineage["schema_version"] == "d7.isolated-command-lineage.v1"
    assert lineage["control_applied_to_world"] is True
    assert lineage["command_payload"]["context"]["arm_kind"] == "control"
    assert lineage["command_payload"]["production_runtime_ack"] is False


def test_wrong_arm_and_cross_arm_validation_fail_closed() -> None:
    plan = _plan()
    control_context = _context(arm="control", timestamp_s=0.0, plan=plan)
    treatment_context = _context(arm="treatment", timestamp_s=0.0, plan=plan)
    executor = IsolatedArmGuidanceExecutor3D(control_context)
    record = executor.command_batch(
        [_pair_input(timestamp_s=0.0)],
        resource_count=1,
        context=control_context,
        source_plan_payload=plan,
    ).command_records[0]

    with pytest.raises(IsolatedGuidanceContractError, match="wrong_arm"):
        executor.command_batch(
            [_pair_input(timestamp_s=0.0)],
            resource_count=1,
            context=treatment_context,
            source_plan_payload=plan,
        )

    verdict = validate_isolated_guidance_command(
        record,
        expected_context=treatment_context,
    )
    assert verdict.valid is False
    assert verdict.code == "wrong_arm"


def test_stale_plan_and_source_plan_hash_tamper_fail_before_command_generation() -> None:
    plan_v2 = _plan(version=2)
    context_v2 = _context(arm="control", timestamp_s=0.0, plan=plan_v2)
    executor = IsolatedArmGuidanceExecutor3D(context_v2)
    executor.command_batch(
        [_pair_input(timestamp_s=0.0, version=2)],
        resource_count=1,
        context=context_v2,
        source_plan_payload=plan_v2,
    )

    plan_v1 = _plan(version=1)
    context_v1 = _context(arm="control", timestamp_s=0.1, plan=plan_v1)
    with pytest.raises(IsolatedGuidanceContractError, match="stale_plan_version"):
        executor.command_batch(
            [_pair_input(timestamp_s=0.1, version=1)],
            resource_count=1,
            context=context_v1,
            source_plan_payload=plan_v1,
        )

    tampered_plan = {**plan_v2, "metadata": {"owner_node_id": "secondary"}}
    context_v2_later = replace(context_v2, generated_at_s=0.2)
    with pytest.raises(IsolatedGuidanceContractError, match="source_plan_hash_mismatch"):
        executor.command_batch(
            [_pair_input(timestamp_s=0.2, version=2)],
            resource_count=1,
            context=context_v2_later,
            source_plan_payload=tampered_plan,
        )

    conflicting_context = _context(
        arm="control",
        timestamp_s=0.25,
        plan=tampered_plan,
    )
    with pytest.raises(IsolatedGuidanceContractError, match="source_plan_hash_conflict"):
        executor.command_batch(
            [_pair_input(timestamp_s=0.25, version=2)],
            resource_count=1,
            context=conflicting_context,
            source_plan_payload=tampered_plan,
        )

    missing_binding_context = _context(
        arm="control",
        timestamp_s=0.3,
        plan=plan_v2,
    )
    with pytest.raises(
        IsolatedGuidanceContractError,
        match="assignment_binding_not_in_source_plan",
    ):
        executor.command_batch(
            [
                _pair_input(
                    timestamp_s=0.3,
                    resource_id="INT-0001",
                    target_id="GT-000001",
                    version=2,
                )
            ],
            resource_count=2,
            context=missing_binding_context,
            source_plan_payload=plan_v2,
        )


def test_d4_d5_and_resource_track_mismatch_are_held_with_zero_commands() -> None:
    plan = _plan(pair_count=3)
    context = _context(arm="control", timestamp_s=0.0, plan=plan)
    executor = IsolatedArmGuidanceExecutor3D(context)
    inputs = (
        _pair_input(
            timestamp_s=0.0,
            resource_index=0,
            resource_id="INT-0000",
            target_id="GT-000000",
            permission=D4GuidancePermission(action="request_center_replan"),
        ),
        _pair_input(
            timestamp_s=0.0,
            resource_index=1,
            resource_id="INT-0001",
            target_id="GT-000001",
            terminal=False,
        ),
        _pair_input(
            timestamp_s=0.0,
            resource_index=2,
            resource_id="INT-0002",
            target_id="GT-000002",
            track_target_id="GT-DIFFERENT",
        ),
    )
    batch = executor.command_batch(
        inputs,
        resource_count=3,
        context=context,
        source_plan_payload=plan,
        d5_gate_required_bindings=(("INT-0001", "GT-000001"),),
    )

    assert np.allclose(batch.acceleration_ned_mps2, 0.0)
    d4_blocked, d5_blocked, binding_blocked = batch.command_records
    assert d4_blocked.held is True
    assert d4_blocked.d4_gate_passed is False
    assert d4_blocked.hold_reason == "d4_action_not_executable"
    assert d5_blocked.held is True
    assert d5_blocked.d5_gate_required is True
    assert d5_blocked.d5_gate_passed is False
    assert binding_blocked.held is True
    assert binding_blocked.binding_gate_passed is False
    assert binding_blocked.hold_reason == "global_track_id_mismatch"

    with pytest.raises(IsolatedGuidanceContractError, match="d5_gate_binding_not_present"):
        executor.command_batch(
            [_pair_input(timestamp_s=0.0)],
            resource_count=3,
            context=context,
            source_plan_payload=plan,
            d5_gate_required_bindings=(("INT-0099", "GT-009999"),),
        )


def test_lineage_and_application_tampering_are_detected() -> None:
    plan = _plan()
    context = _context(arm="control", timestamp_s=0.0, plan=plan)
    executor = IsolatedArmGuidanceExecutor3D(context)
    batch = executor.command_batch(
        [_pair_input(timestamp_s=0.0)],
        resource_count=1,
        context=context,
        source_plan_payload=plan,
    )
    record = batch.command_records[0]
    tampered = replace(record, control_mode="terminal_visual_png_3d")

    verdict = validate_isolated_guidance_command(tampered, expected_context=context)
    assert verdict.valid is False
    assert verdict.code == "command_record_hash_mismatch"

    receipt = executor.confirm_world_application(
        record,
        context=context,
        world_id="world-1000-control",
        applied_at_s=0.0,
        applied_acceleration_ned_mps2=batch.acceleration_ned_mps2[0],
    )
    tampered_receipt = replace(receipt, arm_id="seed-1000-treatment")
    receipt_verdict = validate_isolated_guidance_command(
        record,
        expected_context=context,
        application=tampered_receipt,
    )
    assert receipt_verdict.valid is False
    assert receipt_verdict.code == "application_lineage_mismatch"

    with pytest.raises(IsolatedGuidanceContractError, match="wrong_isolated_world"):
        executor.confirm_world_application(
            record,
            context=context,
            world_id="world-1000-treatment",
            applied_at_s=0.0,
            applied_acceleration_ned_mps2=batch.acceleration_ned_mps2[0],
        )


def test_summary_separates_generated_held_and_applied_counts() -> None:
    plan = _plan(pair_count=2)
    context = _context(arm="control", timestamp_s=0.0, plan=plan)
    executor = IsolatedArmGuidanceExecutor3D(context)
    batch = executor.command_batch(
        [
            _pair_input(timestamp_s=0.0),
            _pair_input(
                timestamp_s=0.0,
                resource_index=1,
                resource_id="INT-0001",
                target_id="GT-000001",
                permission=D4GuidancePermission(action="hold_for_review"),
            ),
        ],
        resource_count=2,
        context=context,
        source_plan_payload=plan,
    )
    applied_record, held_record = batch.command_records
    receipt = executor.confirm_world_application(
        applied_record,
        context=context,
        world_id="world-1000-control",
        applied_at_s=0.0,
        applied_acceleration_ned_mps2=batch.acceleration_ned_mps2[0],
    )
    with pytest.raises(IsolatedGuidanceContractError, match="held_command_cannot_be_applied"):
        executor.confirm_world_application(
            held_record,
            context=context,
            world_id="world-1000-control",
            applied_at_s=0.0,
            applied_acceleration_ned_mps2=(0.0, 0.0, 0.0),
        )

    summary = summarize_isolated_guidance_commands(
        batch.command_records,
        applications=(receipt,),
        expected_context=context,
    )
    assert summary.command_count == 2
    assert summary.command_generated_count == 2
    assert summary.held_count == 1
    assert summary.control_applied_to_world_count == 1
    assert summary.generated_not_applied_count == 0
    assert summary.invalid_count == 0
    assert summary.production_runtime_ack is False


def test_online_truth_identity_fields_are_rejected() -> None:
    plan = {
        **_plan(),
        "metadata": {"truth_id": "TARGET-001"},
    }
    with pytest.raises(IsolatedGuidanceContractError, match="forbidden field"):
        _context(arm="control", timestamp_s=0.0, plan=plan)
