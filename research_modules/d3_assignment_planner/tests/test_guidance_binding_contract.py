from dataclasses import replace

from d3_assignment_planner import (
    Assignment,
    AssignmentPlan,
    SECONDARY_PLAN_SCHEMA_V2,
    assignment_validity_summary_from_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)


def _assignment(
    target_id: str = "T01",
    resource_id: str = "R01",
    *,
    terminal_feedback_state: str | None = None,
    duplicate_terminal_lock_risk: bool = False,
    feasibility_state: str = "feasible",
) -> Assignment:
    return Assignment(
        target_id=target_id,
        resource_id=resource_id,
        cost=1.25,
        cost_breakdown={"total": 1.25},
        feasibility_state=feasibility_state,
        source_node_id="center-c2",
        target_node_id=resource_id,
        link_type="c2_direct",
        plan_version=3,
        stale_after_s=2.0,
        terminal_feedback_state=terminal_feedback_state,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
        metadata={"resource_actor_name": f"CV_{resource_id}"},
    )


def _plan(
    *assignments: Assignment,
    plan_id: str = "PLAN-003",
    version: int = 3,
    created_at: float = 10.0,
    authorization_state: str = "approved",
    stale_after_s: float | None = 5.0,
    terminal_feedback_state: str | None = None,
    duplicate_terminal_lock_risk: bool = False,
) -> AssignmentPlan:
    return AssignmentPlan(
        plan_id=plan_id,
        version=version,
        window_id=1,
        assignments=assignments,
        unassigned_target_ids=(),
        total_cost=sum(item.cost for item in assignments),
        created_at=created_at,
        last_changed_at=created_at,
        human_authorization_state=authorization_state,
        source_node_id="center-c2",
        target_node_id="interceptor-group",
        link_type="c2_direct",
        stale_after_s=stale_after_s,
        terminal_feedback_state=terminal_feedback_state,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
    )


def test_guidance_binding_exposes_d7_assignment_like_aliases() -> None:
    plan = _plan(_assignment())

    (binding,) = guidance_bindings_from_assignment_plan(
        plan,
        guidance_phase="vision_terminal",
        target_alias_map={
            "T01": {
                "target_actor_name": "TargetActor_01",
                "target_object_id": "TargetMesh_01",
                "mesh_aliases": ("TargetDrone_01",),
            }
        },
    )

    assert binding.binding_state == "active"
    assert binding.is_active is True
    assert binding.plan_id == "PLAN-003"
    assert binding.plan_version == 3
    assert binding.version == 3
    assert binding.resource_id == "R01"
    assert binding.owner == "R01"
    assert binding.assigned_resource_id == "R01"
    assert binding.vehicle_name == "CV_R01"
    assert binding.resource_actor_name == "CV_R01"
    assert binding.assigned_global_track_id == "T01"
    assert binding.target_id == "T01"
    assert binding.global_track_id == "T01"
    assert binding.authorization_state == "approved"
    assert binding.human_authorization_state == "approved"
    assert binding.guidance_phase == "vision_terminal"
    assert binding.source == "center-c2"
    assert binding.target == "R01"
    assert binding.link == "c2_direct"
    assert binding.target_actor_name == "TargetActor_01"
    assert binding.target_object_id == "TargetMesh_01"
    assert binding.target_mesh_aliases == (
        "TargetDrone_01",
        "TargetActor_01",
        "TargetMesh_01",
    )
    assert binding.actor_aliases["resource_actor_name"] == "CV_R01"
    assert binding.actor_aliases["target_actor_name"] == "TargetActor_01"
    assert binding.metadata["allow_local_rebind"] is False

    metadata = binding.to_assignment_metadata()
    assert metadata["assignment_id"] == binding.binding_id
    assert metadata["id"] == binding.binding_id
    assert metadata["plan_version"] == 3
    assert metadata["version"] == 3
    assert metadata["resource_id"] == "R01"
    assert metadata["owner"] == "R01"
    assert metadata["assigned_resource_id"] == "R01"
    assert metadata["target_id"] == "T01"
    assert metadata["assigned_global_track_id"] == "T01"
    assert metadata["global_track_id"] == "T01"
    assert metadata["authorization_state"] == "approved"
    assert metadata["human_authorization_state"] == "approved"
    assert metadata["source"] == "center-c2"
    assert metadata["target"] == "R01"
    assert metadata["link"] == "c2_direct"


def test_guidance_binding_state_stale_revoked_and_hold() -> None:
    base_plan = _plan(_assignment(), stale_after_s=1.0)

    (stale_binding,) = guidance_bindings_from_assignment_plan(base_plan, now_s=12.1)
    (revoked_binding,) = guidance_bindings_from_assignment_plan(
        base_plan,
        now_s=10.5,
        revoked_plan_versions=frozenset({3}),
    )
    (feedback_hold,) = guidance_bindings_from_assignment_plan(
        _plan(_assignment(terminal_feedback_state="mismatch"))
    )
    (duplicate_hold,) = guidance_bindings_from_assignment_plan(
        _plan(_assignment(duplicate_terminal_lock_risk=True))
    )
    (explicit_hold,) = guidance_bindings_from_assignment_plan(
        base_plan,
        hold_resource_ids=frozenset({"R01"}),
    )

    assert stale_binding.binding_state == "stale"
    assert stale_binding.revoke_reason == "plan_stale"
    assert revoked_binding.binding_state == "revoked"
    assert revoked_binding.revoke_reason == "plan_version_revoked"
    assert feedback_hold.binding_state == "hold"
    assert feedback_hold.revoke_reason == "terminal_feedback_mismatch"
    assert duplicate_hold.binding_state == "hold"
    assert duplicate_hold.revoke_reason == "duplicate_terminal_lock_risk"
    assert explicit_hold.binding_state == "hold"
    assert explicit_hold.revoke_reason == "resource_hold_requested"


def test_guidance_binding_marks_reassignment_from_previous_plan() -> None:
    previous = _plan(
        _assignment(target_id="T00", resource_id="R01"),
        plan_id="PLAN-002",
        version=2,
        created_at=8.0,
    )
    current = _plan(
        _assignment(target_id="T01", resource_id="R01"),
        plan_id="PLAN-003",
        version=3,
        created_at=10.0,
    )

    (binding,) = guidance_bindings_from_assignment_plan(current, previous_plan=previous)

    assert binding.binding_state == "active"
    assert binding.revoke_reason is None
    assert binding.assigned_global_track_id == "T01"
    assert binding.metadata["previous_target_for_resource"] == "T00"
    assert binding.metadata["resource_reassigned"] is True


def test_secondary_plan_v2_binding_after_center_plan_invalidates() -> None:
    center_plan = _plan(
        _assignment(target_id="T00", resource_id="R01"),
        plan_id="CENTER-PLAN-001",
        version=1,
        created_at=0.0,
        stale_after_s=1.0,
    )
    secondary_plan = _plan(
        Assignment(
            target_id="T01",
            resource_id="R01",
            cost=1.25,
            cost_breakdown={"total": 1.25},
            feasibility_state="feasible",
            plan_version=2,
            stale_after_s=2.0,
            metadata={"resource_actor_name": "CV_R01"},
        ),
        plan_id="SECONDARY-PLAN-002",
        version=2,
        created_at=2.0,
        stale_after_s=2.0,
    )
    secondary_plan = prepare_secondary_takeover_plan(
        secondary_plan,
        supersedes_plan=center_plan,
        secondary_node_id="secondary-node-2",
        target_node_id="interceptor-group",
        takeover_reason="d4_degrade_to_secondary",
        lease_expires_at_s=4.0,
        leader_epoch=12,
    )

    center_summary = assignment_validity_summary_from_plan(
        center_plan,
        evaluated_at=2.1,
        latest_plan_id=secondary_plan.plan_id,
        latest_version=secondary_plan.version,
    )
    (binding,) = guidance_bindings_from_assignment_plan(
        secondary_plan,
        previous_plan=center_plan,
        now_s=2.1,
    )

    assert center_summary.stale_plan_version is True
    assert center_summary.plan_age_s == 2.1
    assert binding.plan_id == "SECONDARY-PLAN-002"
    assert binding.plan_version == 2
    assert binding.plan_schema == SECONDARY_PLAN_SCHEMA_V2
    assert binding.to_assignment_metadata()["plan_schema"] == SECONDARY_PLAN_SCHEMA_V2
    assert binding.source_node_id == "secondary-node-2"
    assert binding.target_node_id == "R01"
    assert binding.link_type == "d4_secondary_relay"
    assert binding.metadata["previous_plan_id"] == center_plan.plan_id
    assert binding.metadata["previous_target_for_resource"] == "T00"
    assert binding.metadata["resource_reassigned"] is True
    assert binding.metadata["allow_local_rebind"] is False
    assert secondary_plan.metadata["plan_schema"] == SECONDARY_PLAN_SCHEMA_V2
    assert secondary_plan.metadata["active_plan_owner"] == "secondary"
    assert secondary_plan.metadata["owner_node_id"] == "secondary-node-2"
    assert secondary_plan.metadata["selected_secondary_node_id"] == "secondary-node-2"
    assert secondary_plan.metadata["supersedes_plan_id"] == center_plan.plan_id
    assert secondary_plan.metadata["supersedes_plan_version"] == center_plan.version
    assert secondary_plan.metadata["secondary_lease_expires_at_s"] == 4.0
    assert secondary_plan.metadata["secondary_leader_epoch"] == 12


def test_secondary_takeover_rejects_stale_or_tied_version() -> None:
    center_plan = _plan(
        _assignment(target_id="T00", resource_id="R01"),
        plan_id="CENTER-PLAN-001",
        version=3,
        created_at=0.0,
    )
    stale_candidate = replace(
        center_plan,
        plan_id="SECONDARY-PLAN-003",
        previous_plan_id=center_plan.plan_id,
        source_node_id="secondary-node-2",
    )

    try:
        prepare_secondary_takeover_plan(
            stale_candidate,
            supersedes_plan=center_plan,
            secondary_node_id="secondary-node-2",
        )
    except ValueError as exc:
        assert "newer" in str(exc)
    else:
        raise AssertionError("expected stale secondary takeover plan rejection")
