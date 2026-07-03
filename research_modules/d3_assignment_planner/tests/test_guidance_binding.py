from d3_assignment_planner import (
    Assignment,
    AssignmentPlan,
    guidance_bindings_from_assignment_plan,
)


def _plan(
    *,
    version: int = 1,
    created_at: float = 0.0,
    stale_after_s: float | None = None,
    authorization: str = "authorized",
    assignments: tuple[Assignment, ...] | None = None,
) -> AssignmentPlan:
    return AssignmentPlan(
        plan_id="plan-alpha",
        version=version,
        window_id=1,
        assignments=assignments
        or (
            Assignment(
                target_id="G-TGT-001",
                resource_id="INT-01",
                cost=1.0,
                cost_breakdown={"window": 1.0},
                plan_version=version,
            ),
        ),
        unassigned_target_ids=(),
        total_cost=1.0,
        created_at=created_at,
        last_changed_at=created_at,
        human_authorization_state=authorization,
        stale_after_s=stale_after_s,
        source_node_id="MAIN-C2",
        link_type="c2_direct",
    )


def test_guidance_binding_exports_d7_assignment_like_fields() -> None:
    bindings = guidance_bindings_from_assignment_plan(
        _plan(),
        resource_vehicle_map={"INT-01": "Interceptor1"},
        target_alias_map={
            "G-TGT-001": {
                "actor_name": "MSM_TargetActor_1",
                "object_id": "TGT-001",
                "mesh_aliases": ("MSM_TargetActor_1", "TGT-001"),
            }
        },
        guidance_phase="radar_midcourse",
        now_s=0.5,
    )

    assert len(bindings) == 1
    binding = bindings[0]
    assert binding.binding_state == "active"
    assert binding.assignment_id == binding.binding_id
    assert binding.plan_id == "plan-alpha"
    assert binding.plan_version == 1
    assert binding.track_version == 1
    assert binding.assignment_validity_state == "current"
    assert binding.resource_id == "INT-01"
    assert binding.vehicle_name == "Interceptor1"
    assert binding.target_id == "G-TGT-001"
    assert binding.assigned_global_track_id == "G-TGT-001"
    assert binding.target_actor_name == "MSM_TargetActor_1"
    assert binding.target_object_id == "TGT-001"
    assert "MSM_TargetActor_1" in binding.target_mesh_aliases
    assert binding.to_assignment_metadata()["target_id"] == "G-TGT-001"


def test_guidance_binding_marks_stale_and_revoked_versions() -> None:
    stale = guidance_bindings_from_assignment_plan(
        _plan(created_at=10.0, stale_after_s=2.0),
        now_s=13.1,
    )[0]
    revoked = guidance_bindings_from_assignment_plan(
        _plan(version=7),
        revoked_plan_versions={7},
    )[0]

    assert stale.binding_state == "stale"
    assert stale.revoke_reason == "plan_stale"
    assert revoked.binding_state == "revoked"
    assert revoked.revoke_reason == "plan_version_revoked"


def test_guidance_binding_holds_unauthorized_or_terminal_feedback() -> None:
    unauthorized = guidance_bindings_from_assignment_plan(
        _plan(authorization="required"),
    )[0]
    feedback_hold = guidance_bindings_from_assignment_plan(
        _plan(
            authorization="authorized",
            assignments=(
                Assignment(
                    target_id="G-TGT-002",
                    resource_id="INT-02",
                    cost=1.0,
                    cost_breakdown={},
                    terminal_feedback_state="ambiguous",
                ),
            ),
        )
    )[0]

    assert unauthorized.binding_state == "hold"
    assert unauthorized.revoke_reason == "authorization_not_effective"
    assert feedback_hold.binding_state == "hold"
    assert feedback_hold.revoke_reason == "terminal_feedback_ambiguous"


def test_guidance_binding_records_resource_reassignment() -> None:
    previous = _plan(
        version=1,
        assignments=(
            Assignment(target_id="G-TGT-001", resource_id="INT-01", cost=1.0, cost_breakdown={}),
        ),
    )
    current = _plan(
        version=2,
        assignments=(
            Assignment(target_id="G-TGT-002", resource_id="INT-01", cost=1.0, cost_breakdown={}),
        ),
    )

    binding = guidance_bindings_from_assignment_plan(current, previous_plan=previous)[0]

    assert binding.binding_state == "active"
    assert binding.metadata["previous_target_for_resource"] == "G-TGT-001"
    assert binding.metadata["resource_reassigned"] is True
