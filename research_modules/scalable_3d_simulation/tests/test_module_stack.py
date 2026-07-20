from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    RegionalPlanAuthorityError,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.scenarios import make_curriculum_scenario


def test_5v5_online_stack_connects_d1_to_d7_without_truth_identity(tmp_path) -> None:
    config = ScenarioConfig(
        scenario_name="integrated_5v5",
        scenario_version="integrated-5v5-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack, output_dir=tmp_path)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert len(stack.latest_d1_tracks) == 5
    assert len(stack.latest_d2_tracks) == 5
    assert len(stack.latest_plan.assignments) == 5
    assert stack.latest_plan.unassigned_target_ids == ()
    assert len(stack.latest_guidance_batch.pair_commands) == 5
    assert all(
        command.mode.value == "midcourse_pn_3d"
        for command in stack.latest_guidance_batch.pair_commands
    )
    topics = {message.topic for message in result.online_messages}
    assert {
        "modules.d1.fused_tracks",
        "modules.d2.associated_tracks",
        "modules.d3.assignment_plan",
        "modules.d4.regional_failover",
        "modules.d5.terminal_association",
        "modules.d5.active_vision",
        "modules.d7.guidance_commands",
    }.issubset(topics)
    d5_payload = next(
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.terminal_association"
    )
    assert "all_possible_camera_pairs" in d5_payload["diagnostics"]
    assert "candidate_tracklet_edges" in d5_payload["diagnostics"]
    assert stack.latest_d5_result is not None
    assert all(
        tracklet.local_track_id.startswith("trk-")
        for tracklet in stack.latest_d5_result.tracklets
    )
    center_ids = {track.global_track_id for track in stack.latest_d2_tracks}
    assert {
        binding.global_track_id
        for binding in stack.latest_d5_result.association.bindings
        if binding.global_track_id is not None
    }.issubset(center_ids)
    active_vision_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.active_vision"
    ]
    assert active_vision_payloads
    assert result.summary["camera_command_issued_count"] > 0
    assert result.summary["camera_command_applied_count"] == result.summary[
        "camera_command_issued_count"
    ]
    assert result.summary["camera_command_rejected_count"] == 0
    assert all(
        command["target_global_track_id"] is None
        or command["target_global_track_id"] in center_ids
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    assert all(
        not str(command["target_global_track_id"]).startswith("TGT-")
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    camera_acks = [
        message.payload
        for message in result.online_messages
        if message.topic == "runtime.camera_command_ack"
    ]
    assert len(camera_acks) == result.summary["camera_command_ack_count"]
    assert {ack["status"] for ack in camera_acks} == {"applied"}
    timings = {item.stage: item for item in result.stage_timings}
    assert timings["module.d1_fusion"].call_count > 0
    assert timings["module.d3_assignment"].wall_time_s > 0.0
    assert timings["module.main_d4_adapter"].mean_wall_time_ms > 0.0
    report = (tmp_path / "SCALABLE_3D_EPISODE_REPORT_CN.md").read_text(
        encoding="utf-8"
    )
    assert "本次启用 D1-D7 规则集成栈" in report
    assert "D1/D2 航迹数分别为 5/5" in report


def test_200v200_stack_uses_sparse_candidates_and_commands_every_assignment() -> None:
    config = ScenarioConfig(
        scenario_name="integrated_200v200_smoke",
        scenario_version="integrated-200v200-smoke-v1",
        target_count=200,
        resource_count=200,
        recon_count=8,
        region_count=8,
        duration_s=0.25,
        seed=17,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert len(stack.latest_d1_tracks) == 200
    assert len(stack.latest_d2_tracks) == 200
    assert len(stack.latest_plan.assignments) == 200
    assert stack.latest_plan.unassigned_target_ids == ()
    assert stack.latest_plan.metadata["candidate_full_edge_count"] == 40_000
    assert stack.latest_plan.metadata["candidate_edge_count"] == 6_400
    assert len(stack.latest_guidance_batch.pair_commands) == 200
    assert stack.latest_guidance_batch.acceleration_ned_mps2.shape == (200, 3)


def test_center_failure_reissues_a_secondary_owned_plan_before_guidance_continues() -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[0]["summary"]["selected_layer_counts"]["center"] == 8
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["secondary"] == 8
    assert d4_payloads[-1]["summary"]["execution_allowed_region_count"] == 8
    assert stack.latest_plan.version == 2
    assert stack.latest_plan.metadata["active_plan_owner"] == "secondary"
    assert stack.latest_plan.metadata["owner_node_id"] == "RECON-001"
    assert all(
        command.mode.value == "midcourse_pn_3d"
        for command in stack.latest_guidance_batch.pair_commands
    )


def test_secondary_failure_reissues_a_distributed_regional_plan() -> None:
    config = make_curriculum_scenario(
        "secondary_failure",
        scale=5,
        seed=4,
        duration_s=4.4,
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["distributed"] == 8
    active_regions = [
        item for item in d4_payloads[-1]["regions"] if item["task_ids"]
    ]
    assert len(active_regions) == 5
    assert all(item["execution_allowed"] for item in active_regions)
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["regional_owner_layers"] == ("distributed",)
    assert stack.latest_plan.metadata["regional_single_member_authority_count"] == 5
    assert stack.latest_plan.metadata["regional_atomic_coalition_commit_count"] == 0
    assert all(
        assignment.metadata["regional_owner_layer"] == "distributed"
        for assignment in stack.latest_plan.assignments
    )
    assert Counter(
        command.mode.value for command in stack.latest_guidance_batch.pair_commands
    ) == {"midcourse_pn_3d": 5}
    assert stack._regional_plan_rejection_reason is None
    target_id = stack.latest_plan.assignments[0].target_id
    permission = stack._d4_permission(target_id)
    assert permission.action == "continue"
    assert permission.mode == "distributed"
    assert permission.atomic_coalition_formed is None
    assert permission.coalition_commit_state == "single_member_authorized"
    assert permission.metadata["commit_required"] is False


def test_two_secondary_nodes_publish_one_multi_owner_regional_plan() -> None:
    config = ScenarioConfig(
        scenario_name="multi_secondary_50v50",
        scenario_version="multi-secondary-50v50-v1",
        target_count=50,
        resource_count=50,
        recon_count=2,
        region_count=8,
        duration_s=2.4,
        seed=13,
        interceptor_speed_mps=30.0,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        metadata={
            "fault_schedule": [
                {"time_s": 0.4, "component": "center", "action": "failed"}
            ]
        },
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["regional_owner_layers"] == ("secondary",)
    assert stack.latest_plan.metadata["regional_owner_node_ids"] == (
        "RECON-001",
        "RECON-002",
    )
    assert stack.latest_plan.metadata["regional_single_member_authority_count"] == 50
    assert stack.latest_plan.metadata["regional_atomic_coalition_commit_count"] == 0
    assert {
        assignment.target_id for assignment in stack.latest_plan.assignments
    } == {track.global_track_id for track in stack.latest_d2_tracks}
    assert Counter(
        command.mode.value for command in stack.latest_guidance_batch.pair_commands
    ) == {"midcourse_pn_3d": 50}
    assert stack._regional_plan_rejection_reason is None


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("expired", "regional_d4_authority_lease_expired"),
        ("missing_commit", "regional_d4_commit_evidence_missing"),
        ("stale_source", "regional_d4_stale_source_plan"),
    ),
)
def test_regional_authority_adapter_rejects_incomplete_d4_evidence(
    mutation: str,
    expected_reason: str,
) -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    stack = IntegratedScalableModuleStack()
    run_episode(config, module_stack=stack)

    target_ids = {track.global_track_id for track in stack.latest_d2_tracks}
    now = 1.1
    if mutation == "expired":
        now = 10.0
    else:
        decisions = list(stack.latest_d4_decision.region_decisions)
        index = next(
            index for index, item in enumerate(decisions) if item.task_ids
        )
        selected = decisions[index]
        if mutation == "missing_commit":
            selected = replace(selected, coalition_commits=())
        else:
            selected = replace(
                selected,
                ownership=replace(
                    selected.ownership,
                    plan_version=selected.ownership.plan_version - 1,
                ),
            )
        decisions[index] = selected
        stack.latest_d4_decision = replace(
            stack.latest_d4_decision,
            region_decisions=tuple(decisions),
        )

    with pytest.raises(RegionalPlanAuthorityError) as error:
        stack._regional_authority_from_d4(
            stack.latest_plan,
            target_ids=target_ids,
            now=now,
        )
    assert error.value.reason == expected_reason
