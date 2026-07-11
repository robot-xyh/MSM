from __future__ import annotations

from d5_terminal_association import TerminalAssociation, TerminalObservationBus


def _locked(
    resource_id: str,
    local_track_id: str,
    *,
    plan_id: str,
    plan_version: int,
    coalition_id: str | None = None,
    coalition_version: int | None = None,
    required_resource_count: int = 1,
    coordination_mode: str = "independent",
) -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id="G1",
        local_track_id=local_track_id,
        association_confidence=0.95,
        ambiguity_score=0.05,
        friend_conflict_state="none",
        decision_state="locked",
        assignment_version=plan_version,
        resource_id=resource_id,
        plan_id=plan_id,
        plan_version=plan_version,
        coalition_id=coalition_id,
        coalition_version=coalition_version,
        member_role="primary",
        required_resource_count=required_resource_count,
        coordination_mode=coordination_mode,
        authorization_state="authorized",
        activation_state="active",
        metadata={"execution_gate_pass": True},
    )


def _publish(
    bus: TerminalObservationBus,
    resource_id: str,
    timestamp: float,
    association: TerminalAssociation,
) -> None:
    bus.publish_terminal_association(
        resource_id=resource_id,
        source_node_id="d3_central",
        link_type="c2_direct",
        timestamp=timestamp,
        terminal_association=association,
        camera_id="front_rgb",
        frame_id=f"frame-{timestamp:g}",
    )


def test_snapshot_uses_latest_frame_per_resource_without_cross_frame_duplicate() -> None:
    bus = TerminalObservationBus()
    _publish(bus, "R1", 1.0, _locked("R1", "mot-old", plan_id="P1", plan_version=1))
    _publish(bus, "R1", 2.0, _locked("R1", "mot-new", plan_id="P1", plan_version=1))

    legacy = bus.cross_view_associations()[0]
    snapshot = bus.cross_view_associations(
        as_of_timestamp=2.0,
        max_age_s=1.5,
        plan_id="P1",
        plan_version=1,
    )[0]

    assert legacy.duplicate_terminal_lock_risk is True
    assert snapshot.duplicate_terminal_lock_risk is False
    assert snapshot.local_track_ids == ("R1/front_rgb:mot-new",)
    assert snapshot.metadata["snapshot_scope_enabled"] is True
    assert snapshot.metadata["snapshot_candidate_observation_count"] == 2
    assert snapshot.metadata["snapshot_selected_observation_count"] == 1


def test_old_plan_multi_resource_locks_do_not_pollute_current_plan() -> None:
    bus = TerminalObservationBus()
    _publish(bus, "R1", 1.0, _locked("R1", "old-r1", plan_id="P1", plan_version=1))
    _publish(bus, "R2", 1.0, _locked("R2", "old-r2", plan_id="P1", plan_version=1))
    _publish(bus, "R1", 2.0, _locked("R1", "new-r1", plan_id="P2", plan_version=2))

    snapshot = bus.cross_view_associations(
        as_of_timestamp=2.0,
        max_age_s=2.0,
        plan_id="P2",
        plan_version=2,
    )

    assert len(snapshot) == 1
    assert snapshot[0].supporting_resource_ids == ("R1",)
    assert snapshot[0].duplicate_terminal_lock_risk is False
    assert snapshot[0].metadata["snapshot_plan_id"] == "P2"
    assert snapshot[0].metadata["snapshot_plan_version"] == 2


def test_same_frame_current_plan_unauthorized_multi_lock_remains_duplicate() -> None:
    bus = TerminalObservationBus()
    _publish(bus, "R1", 3.0, _locked("R1", "r1", plan_id="P3", plan_version=3))
    _publish(bus, "R2", 3.0, _locked("R2", "r2", plan_id="P3", plan_version=3))

    snapshot = bus.cross_view_associations(
        as_of_timestamp=3.0,
        max_age_s=0.75,
        plan_id="P3",
        plan_version=3,
    )[0]

    assert snapshot.supporting_resource_ids == ("R1", "R2")
    assert snapshot.duplicate_terminal_lock_risk is True
    assert snapshot.planned_cooperative_lock is False
    assert snapshot.coalition_conflict_state == "missing_coalition_contract"


def test_same_frame_authorized_coalition_remains_legal_in_snapshot() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        _publish(
            bus,
            resource_id,
            4.0,
            _locked(
                resource_id,
                f"mot-{resource_id}",
                plan_id="P4",
                plan_version=4,
                coalition_id="C-G1",
                coalition_version=2,
                required_resource_count=2,
                coordination_mode="simultaneous",
            ),
        )

    snapshot = bus.cross_view_associations(
        as_of_timestamp=4.0,
        max_age_s=0.75,
        plan_id="P4",
        plan_version=4,
    )[0]

    assert snapshot.supporting_resource_ids == ("R1", "R2")
    assert snapshot.duplicate_terminal_lock_risk is False
    assert snapshot.planned_cooperative_lock is True
    assert snapshot.reason == "planned_cooperative_lock"
