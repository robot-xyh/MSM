from __future__ import annotations

import pytest

from research_modules.scalable_3d_simulation.learning_runtime import (
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.module_stack import IntegratedStackConfig
from research_modules.scalable_3d_simulation.orchestrator import (
    Scalable3DEpisodeRunner,
)
from research_modules.scalable_3d_simulation.isolated_degraded_adoption import (
    evaluate_d4_isolated_physical_adoption,
)
from research_modules.scalable_3d_simulation.isolated_physical_rollout import (
    _d6_plan_payload,
    _guidance_bindings,
    _guidance_inputs,
    _track_templates,
)
from research_modules.d7_proportional_guidance.d7_proportional_guidance import (
    IsolatedArmGuidanceExecutor3D,
    IsolatedGuidanceExecutionContextV1,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    ReservedSeedSourceEvidence,
    ReservedSeedInterventionOptions,
    _canonical_sha256,
    _communication_schedule_sha256,
    _d3_input_snapshot_sha256,
    _fault_schedule_sha256,
    _frame_selection_policy,
    _initial_state_sha256,
    _make_intervention_scenario,
    _offline_identity_mapping_at_timestamp,
    _planning_identity_bridge_at_timestamp,
    _resolved_intervention_kind,
    _select_common_intervention_frames,
    _world_checkpoint_at_timestamp,
)
from research_modules.scalable_3d_simulation.episode_bus import jsonable


@pytest.mark.parametrize(
    ("scenario", "requested_kind", "expected_kind", "expected_action", "expected_layer"),
    (
        ("nominal", "auto", "nominal", "continue_center", "center"),
        (
            "center_failure",
            "auto",
            "center_failed",
            "degrade_to_secondary",
            "secondary",
        ),
        (
            "secondary_failure",
            "auto",
            "center_and_secondary_failed",
            "degrade_to_distributed",
            "distributed",
        ),
        (
            "nominal",
            "active_risk",
            "active_risk",
            "request_secondary_assist",
            "center",
        ),
    ),
)
def test_selector_never_relabels_a_precondition_frame(
    scenario: str,
    requested_kind: str,
    expected_kind: str,
    expected_action: str,
    expected_layer: str,
) -> None:
    options = ReservedSeedInterventionOptions(
        scenario=scenario,
        scale=5,
        duration_s=3.2,
        intervention_kind=requested_kind,
    )
    config = _make_intervention_scenario(options, seed=1000)
    runtime = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    Scalable3DEpisodeRunner(
        runtime.config,
        module_stack=runtime.stack,
    ).run()
    artifacts = runtime.stack.learning_artifacts()

    resolved_kind = _resolved_intervention_kind(options)
    d3_frame, d4_frame = _select_common_intervention_frames(
        artifacts.d3_planning_frames,
        artifacts.d4_region_frames,
        intervention_kind=resolved_kind,
    )

    assert resolved_kind == expected_kind
    assert d3_frame.timestamp_s == pytest.approx(d4_frame.timestamp_s)
    active_regions = tuple(
        item
        for item in d4_frame.formal_decision.region_decisions
        if item.task_ids
    )
    assert active_regions
    assert all(item.action.value == expected_action for item in active_regions)
    assert all(item.selected_layer.value == expected_layer for item in active_regions)
    assert all(item.execution_allowed for item in active_regions)


def test_intervention_kind_rejects_unknown_contract() -> None:
    with pytest.raises(ValueError, match="intervention_kind"):
        ReservedSeedInterventionOptions(intervention_kind="invented")


def test_active_risk_seed_1005_publishes_five_tracks_and_replay_audit() -> None:
    options = ReservedSeedInterventionOptions(
        scenario="nominal",
        scale=5,
        duration_s=1.1,
        intervention_kind="active_risk",
    )
    config = _make_intervention_scenario(options, seed=1005)
    runtime = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    result = Scalable3DEpisodeRunner(
        runtime.config,
        module_stack=runtime.stack,
    ).run()
    publications = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
    )

    assert [item.payload["track_count"] for item in publications] == [
        5,
        6,
        6,
        5,
        5,
    ]
    final_ids = tuple(
        item["global_track_id"] for item in publications[-1].payload["tracks"]
    )
    assert final_ids == tuple(f"GT3D-{index:06d}" for index in range(1, 6))
    governance = publications[-1].payload["association"][
        "observation_evidence_governance"
    ]
    assert governance["schema_version"] == (
        "d2-observation-evidence-governance-v1"
    )
    assert governance["cumulative"]["replay_quarantine_count"] >= 2
    assert governance["cumulative"]["tentative_stale_drop_count"] == 1
    assert governance["global_track_id_owner"] == "D2_center"
    assert governance["online_truth_used"] is False
    assert result.summary["online_truth_use_count"] == 0


@pytest.mark.parametrize(
    ("scenario", "requested_kind"),
    (
        ("center_failure", "auto"),
        ("secondary_failure", "auto"),
        ("nominal", "active_risk"),
    ),
)
def test_d4_post_application_evidence_is_region_scoped(
    scenario: str,
    requested_kind: str,
) -> None:
    options = ReservedSeedInterventionOptions(
        scenario=scenario,
        scale=5,
        duration_s=3.2,
        intervention_kind=requested_kind,
    )
    config = _make_intervention_scenario(options, seed=1000)
    runtime = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    result = Scalable3DEpisodeRunner(
        runtime.config,
        module_stack=runtime.stack,
    ).run()
    artifacts = runtime.stack.learning_artifacts()
    kind = _resolved_intervention_kind(options)
    d3_frame, d4_frame = _select_common_intervention_frames(
        artifacts.d3_planning_frames,
        artifacts.d4_region_frames,
        intervention_kind=kind,
    )
    timestamp = float(d3_frame.timestamp_s)
    checkpoint = _world_checkpoint_at_timestamp(result, timestamp)
    tracks, target_bridge, resource_bridge = _planning_identity_bridge_at_timestamp(
        result,
        timestamp_s=timestamp,
        d3_frame=d3_frame,
        checkpoint=checkpoint,
    )
    source = ReservedSeedSourceEvidence(
        seed=1000,
        scenario_config=runtime.config,
        source_episode_id=result.manifest.episode_id,
        source_git_commit=result.manifest.git_commit,
        source_repository_dirty=bool(result.manifest.repository_dirty),
        source_episode_manifest_sha256=_canonical_sha256(jsonable(result.manifest)),
        source_summary_sha256=_canonical_sha256(result.summary),
        scenario_config_sha256=_canonical_sha256(runtime.config.to_dict()),
        initial_state_sha256=_initial_state_sha256(result),
        communication_schedule_sha256=_communication_schedule_sha256(runtime.config),
        fault_schedule_sha256=_fault_schedule_sha256(runtime.config),
        d3_planning_frame=d3_frame,
        d4_region_snapshot=d4_frame.snapshot,
        d4_formal_snapshot=d4_frame.formal_snapshot,
        d4_formal_decision=d4_frame.formal_decision,
        d3_input_snapshot_sha256=_d3_input_snapshot_sha256(d3_frame),
        d4_region_snapshot_lineage_sha256=_canonical_sha256(
            d4_frame.snapshot.to_dict()
        ),
        intervention_kind=kind,
        frame_selection_policy=_frame_selection_policy(kind),
        intervention_timestamp_s=timestamp,
        intervention_world_checkpoint=checkpoint,
        intervention_global_tracks=tracks,
        planning_target_identity_bridge=target_bridge,
        planning_resource_identity_bridge=resource_bridge,
        offline_track_truth_mapping=_offline_identity_mapping_at_timestamp(
            result,
            timestamp_s=timestamp,
            global_track_ids=tuple(item.global_track_id for item in tracks),
        ),
        finite_state=True,
        online_truth_use_count=0,
    )
    applied = _d6_plan_payload(
        d3_frame.plan,
        source=source,
        d3_plan_sha256="a" * 64,
    )
    applications = tuple(
        {
            "resource_id": item["resource_id"],
            "global_track_id": item["global_track_id"],
            "control_applied_to_world": True,
        }
        for item in applied["assignments"]
    )
    bindings = _guidance_bindings(
        d3_frame.plan,
        source=source,
        duration_s=0.5,
    )
    pair_inputs = _guidance_inputs(
        plan=d3_frame.plan,
        source=source,
        bindings=bindings,
        track_templates=_track_templates(source),
        resource_index={
            resource_id: index
            for index, resource_id in enumerate(checkpoint.interceptor_ids)
        },
        interceptor_state=checkpoint.interceptor_state,
        timestamp_s=0.0,
    )
    context = IsolatedGuidanceExecutionContextV1.from_plan_payload(
        experiment_id="d4-selection-test",
        seed=1000,
        arm_id="seed-1000-control",
        arm_kind="control",
        episode_id="d4-selection-test-control",
        isolation_id="d4-selection-world-control",
        source_plan_id=d3_frame.plan.plan_id,
        source_plan_version=d3_frame.plan.version,
        source_plan_payload=applied,
        generated_at_s=0.0,
    )
    command_batch = IsolatedArmGuidanceExecutor3D(context).command_batch(
        pair_inputs,
        resource_count=config.resource_count,
        context=context,
        source_plan_payload=applied,
    )
    assert command_batch.command_records
    assert all(not item.held for item in command_batch.command_records)

    records = evaluate_d4_isolated_physical_adoption(
        source=source,
        arm_kind="control",
        applied_plan_payload=applied,
        world_application_records=applications,
        physical_duration_s=0.5,
    )

    assert records
    assert all(item.available for item in records)
    assert all(
        item.adoption_evidence["evaluation_refresh_applied"] is True
        for item in records
    )
    assert all(
        item.adoption_evidence["production_runtime_ack"] is False
        for item in records
    )

    missing_application = evaluate_d4_isolated_physical_adoption(
        source=source,
        arm_kind="treatment",
        applied_plan_payload=applied,
        world_application_records=applications[:-1],
        physical_duration_s=0.5,
    )
    assert sum(item.available for item in missing_application) == len(records) - 1
    assert any(
        item.reason == "isolated_plan_consumption_ack_invalid"
        for item in missing_application
    )


@pytest.mark.parametrize("seed", (1011, 1019))
def test_distributed_selection_keeps_zero_binding_targets_fail_closed(
    seed: int,
) -> None:
    options = ReservedSeedInterventionOptions(
        scenario="secondary_failure",
        scale=5,
        duration_s=4.2,
        intervention_kind="auto",
    )
    config = _make_intervention_scenario(options, seed=seed)
    runtime = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    Scalable3DEpisodeRunner(
        runtime.config,
        module_stack=runtime.stack,
    ).run()
    artifacts = runtime.stack.learning_artifacts()

    d3_frame, d4_frame = _select_common_intervention_frames(
        artifacts.d3_planning_frames,
        artifacts.d4_region_frames,
        intervention_kind="center_and_secondary_failed",
    )

    assert d3_frame.timestamp_s >= 3.0
    assert d3_frame.plan.metadata["active_plan_owner"] == "regional"
    assert d3_frame.plan.target_count == 5
    assert len(d3_frame.plan.assignments) == 4
    assert d3_frame.plan.unassigned_target_ids == ("target_0004",)
    assert d3_frame.plan.incomplete_target_ids == ("target_0004",)
    active_regions = tuple(
        decision
        for decision in d4_frame.formal_decision.region_decisions
        if decision.task_ids
    )
    assert active_regions
    assert all(
        decision.selected_layer.value == "distributed"
        and decision.action.value == "degrade_to_distributed"
        and decision.execution_allowed
        and not decision.fail_closed
        for decision in active_regions
    )
