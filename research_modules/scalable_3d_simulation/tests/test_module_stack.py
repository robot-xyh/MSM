from __future__ import annotations

from collections import Counter

from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.scenarios import make_curriculum_scenario


def test_5v5_online_stack_connects_d1_to_d7_without_truth_identity() -> None:
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

    result = run_episode(config, module_stack=stack)

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
        "modules.d7.guidance_commands",
    }.issubset(topics)
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


def test_secondary_failure_keeps_distributed_path_fail_closed_without_d3_plan() -> None:
    config = make_curriculum_scenario(
        "secondary_failure",
        scale=5,
        seed=4,
        duration_s=2.4,
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["distributed"] == 8
    assert d4_payloads[-1]["summary"]["execution_allowed_region_count"] == 0
    assert d4_payloads[-1]["summary"]["fail_closed_region_count"] == 8
    assert stack.latest_plan.metadata["active_plan_owner"] == "secondary"
    assert Counter(
        command.mode.value for command in stack.latest_guidance_batch.pair_commands
    ) == {"hold": 5}
    assert {
        command.gate_reason for command in stack.latest_guidance_batch.pair_commands
    } == {"d4_hold_for_review"}
