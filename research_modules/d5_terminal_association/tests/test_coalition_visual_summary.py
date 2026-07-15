from __future__ import annotations

from types import SimpleNamespace

from d5_terminal_association import (
    TerminalAssociation,
    TerminalObservationBus,
    summarize_coalition_visual_completion,
)


def _binding(
    resource_id: str,
    role: str,
    *,
    plan_version: int = 9,
    plan_id: str = "plan-v2",
    coalition_id: str = "C-G1",
    coalition_version: int = 4,
    coalition_epoch: int | None = None,
    global_track_id: str = "G1",
    target_id: str = "T001",
    plan_owner: str = "center",
    owner_node_id: str = "C2",
) -> dict[str, object]:
    binding: dict[str, object] = {
        "resource_id": resource_id,
        "assigned_global_track_id": global_track_id,
        "target_id": target_id,
        "plan_id": plan_id,
        "plan_version": plan_version,
        "active_plan_owner": plan_owner,
        "owner_node_id": owner_node_id,
        "coalition_id": coalition_id,
        "coalition_version": coalition_version,
        "member_role": role,
        "coordination_mode": "hybrid",
        "primary_resource_count": 2,
        "required_resource_count": 3,
        "authorization_state": "authorized",
        "binding_state": "standby" if role == "reserve" else "active",
    }
    if coalition_epoch is not None:
        binding["coalition_epoch"] = coalition_epoch
    return binding


def _association(
    resource_id: str,
    role: str,
    frame_index: int,
    *,
    decision_state: str = "locked",
    visual_match_state: str | None = None,
    plan_version: int = 9,
    plan_id: str = "plan-v2",
    coalition_id: str = "C-G1",
    coalition_version: int = 4,
    global_track_id: str = "G1",
    local_track_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> TerminalAssociation:
    association_metadata = {
        "frame_index": frame_index,
        "projection_timestamp": float(frame_index),
        "execution_gate_pass": decision_state == "locked",
        "visual_match_decision_state": visual_match_state or decision_state,
        "measurement_resource_id": resource_id,
        "measurement_camera_id": f"{resource_id}/front_rgb",
        "projection_camera_id": f"{resource_id}/front_rgb",
        **(metadata or {}),
    }
    return TerminalAssociation(
        assigned_global_track_id=global_track_id,
        local_track_id=local_track_id or f"mot-{resource_id}",
        association_confidence=0.95,
        ambiguity_score=0.05,
        friend_conflict_state="none",
        decision_state=decision_state,
        assignment_version=2,
        resource_id=resource_id,
        plan_id=plan_id,
        plan_version=plan_version,
        coalition_id=coalition_id,
        coalition_version=coalition_version,
        member_role=role,
        wave_id=1 if role == "reserve" else 0,
        required_resource_count=3,
        coordination_mode="hybrid",
        activation_state="standby" if role == "reserve" else "active",
        metadata=association_metadata,
    )


def _bindings(
    *,
    plan_version: int = 9,
    plan_id: str = "plan-v2",
    coalition_id: str = "C-G1",
    coalition_version: int = 4,
    primary_resource_ids: tuple[str, str] = ("R1", "R2"),
    reserve_resource_id: str = "R3",
    coalition_epoch: int | None = None,
    global_track_id: str = "G1",
    target_id: str = "T001",
    plan_owner: str = "center",
    owner_node_id: str = "C2",
) -> tuple[dict[str, object], ...]:
    common = {
        "plan_version": plan_version,
        "plan_id": plan_id,
        "coalition_id": coalition_id,
        "coalition_version": coalition_version,
        "coalition_epoch": coalition_epoch,
        "global_track_id": global_track_id,
        "target_id": target_id,
        "plan_owner": plan_owner,
        "owner_node_id": owner_node_id,
    }
    return (
        _binding(primary_resource_ids[0], "primary", **common),
        _binding(primary_resource_ids[1], "primary", **common),
        _binding(reserve_resource_id, "reserve", **common),
    )


def _stable_primary_history() -> tuple[TerminalAssociation, ...]:
    return (
        _association("R1", "primary", 1),
        _association("R2", "primary", 1),
    )


def _commit(
    *,
    state: str = "committed",
    epoch: int = 7,
    lease_expires_at_s: float = 10.0,
    plan_version: int = 9,
    coalition_version: int = 4,
    required_members: tuple[str, ...] = ("R1", "R2", "R3"),
    acked_members: tuple[str, ...] = ("R1", "R2", "R3"),
) -> SimpleNamespace:
    return SimpleNamespace(
        state=state,
        epoch=epoch,
        lease={"expires_at_s": lease_expires_at_s},
        coalition_id="C-G1",
        coalition_version=coalition_version,
        plan_id="plan-v2",
        plan_version=plan_version,
        required_members=required_members,
        acked_members=tuple(
            {"resource_id": resource_id, "ack_state": "acked"}
            for resource_id in acked_members
        ),
        fallback_active=True,
    )


def test_hybrid_two_primary_one_reserve_reports_visual_completion() -> None:
    bus = TerminalObservationBus()
    for association in (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    ):
        bus.publish_terminal_association(
            resource_id=association.resource_id or "",
            source_node_id="d3_central",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=association,
            camera_id=f"{association.resource_id}/front_rgb",
            frame_id=f"frame-{association.resource_id}-2",
        )

    summary = bus.coalition_visual_summary(
        _bindings(),
        historical_associations=_stable_primary_history(),
    )

    assert summary.primary_required_count == 2
    assert summary.primary_locked_resource_ids == ("R1", "R2")
    assert summary.primary_lock_complete is True
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is True
    assert summary.planned_cooperative_lock is True
    assert summary.duplicate_terminal_lock_risk is False
    assert summary.visual_png_authorized_resource_ids == ("R1", "R2")
    assert summary.metadata["reserve_visual_png_authorized"] is False


def test_d3_style_bindings_infer_total_demand_from_coalition_members() -> None:
    bindings = tuple(
        {key: value for key, value in binding.items() if key != "required_resource_count"}
        for binding in _bindings()
    )
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(
        bindings,
        current,
        _stable_primary_history(),
    )

    assert summary.primary_required_count == 2
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is True


def test_accumulated_bus_uses_latest_frame_and_earlier_frames_for_stability() -> None:
    bus = TerminalObservationBus()
    for frame_index in (1, 2):
        for resource_id in ("R1", "R2"):
            association = _association(resource_id, "primary", frame_index)
            bus.publish_terminal_association(
                resource_id=resource_id,
                source_node_id="d3_central",
                link_type="c2_direct",
                timestamp=float(frame_index),
                terminal_association=association,
                frame_id=f"frame-{frame_index}",
            )

    summary = bus.coalition_visual_summary(_bindings())

    assert summary.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 2}
    assert summary.primary_lock_complete is True


def test_missing_one_primary_never_completes_with_ready_reserve() -> None:
    current = (
        _association("R1", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert summary.primary_locked_resource_ids == ("R1",)
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.primary_lock_complete is False
    assert summary.coalition_visual_consensus is False
    assert summary.visual_png_authorized_resource_ids == ()


def test_reserve_only_visual_match_is_readiness_not_consensus() -> None:
    current = (
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(_bindings(), current)

    assert summary.primary_locked_resource_ids == ()
    assert summary.primary_lock_complete is False
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is False
    assert summary.planned_cooperative_lock is False


def test_primary_lock_requires_two_consecutive_frames_for_each_resource() -> None:
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
    )
    unstable_history = (
        _association("R1", "primary", 1),
        _association("R2", "primary", 1, decision_state="hold"),
    )

    unstable = summarize_coalition_visual_completion(
        _bindings(),
        current,
        unstable_history,
    )
    stable = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert unstable.primary_locked_resource_ids == ("R1", "R2")
    assert unstable.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 1}
    assert unstable.primary_lock_complete is False
    assert unstable.reason == "primary_lock_stability_incomplete"
    assert stable.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 2}
    assert stable.primary_lock_complete is True


def test_current_plan_version_conflict_blocks_consensus_and_cooperative_lock() -> None:
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2, plan_version=8),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert summary.primary_lock_complete is False
    assert summary.coalition_visual_consensus is False
    assert summary.planned_cooperative_lock is False
    assert summary.duplicate_terminal_lock_risk is True
    assert summary.coalition_conflict_state == "coalition_or_plan_version_mismatch"
    assert summary.metadata["version_conflict_resource_ids"] == ("R2",)


def test_borrowed_secondary_bbox_cannot_make_reserve_ready() -> None:
    borrowed = _association(
        "R3",
        "reserve",
        2,
        decision_state="hold",
        visual_match_state="locked",
        metadata={
            "measurement_resource_id": "Secondary1",
            "measurement_camera_id": "Secondary1/down_rgb",
            "projection_camera_id": "R3/front_rgb",
            "recon_cue_used": True,
        },
    )

    summary = summarize_coalition_visual_completion(_bindings(), (borrowed,))

    assert summary.reserve_ready_resource_ids == ()
    assert summary.metadata["secondary_cue_policy"] == "search_or_registration_only"


def test_unbound_execution_lock_preserves_over_demand_safety() -> None:
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
        _association("R3", "reserve", 2),
        _association("R4", "primary", 2),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert summary.primary_lock_complete is False
    assert summary.coalition_visual_consensus is False
    assert summary.duplicate_terminal_lock_risk is True
    assert summary.coalition_conflict_state == "member_count_exceeds_demand"
    assert summary.excess_lock_resource_ids == ("R4",)


def test_t001_two_primary_same_snapshot_two_frames_requires_valid_commit() -> None:
    bus = TerminalObservationBus()
    for frame_index in (1, 2):
        for resource_id in ("R1", "R2"):
            association = _association(resource_id, "primary", frame_index)
            bus.publish_terminal_association(
                resource_id=resource_id,
                source_node_id="distributed-coordinator",
                link_type="peer_mesh",
                timestamp=float(frame_index),
                terminal_association=association,
                frame_id=f"snapshot-{frame_index}",
            )

    summary = bus.coalition_visual_summary(
        _bindings(),
        coalition_commit=_commit(),
        current_time_s=2.0,
        center_failed=True,
    )

    assert summary.primary_locked_resource_ids == ("R1", "R2")
    assert summary.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 2}
    assert summary.coalition_commit_required is True
    assert summary.coalition_commit_valid is True
    assert summary.coalition_visual_consensus is True
    assert summary.coalition_execution_state == "authorized"
    assert summary.visual_png_authorized_resource_ids == ("R1", "R2")


def test_valid_commit_does_not_allow_single_primary_or_reserve_substitution() -> None:
    current = (
        _association("R1", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
        coalition_commit=_commit(),
        current_time_s=2.0,
        fallback_active=True,
    )

    assert summary.coalition_commit_valid is True
    assert summary.primary_locked_resource_ids == ("R1",)
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is False
    assert summary.coalition_execution_state == "cue_only"
    assert summary.visual_png_authorized_resource_ids == ()


def test_reserve_only_stays_readiness_with_valid_commit() -> None:
    reserve = _association(
        "R3",
        "reserve",
        2,
        decision_state="hold",
        visual_match_state="locked",
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        (reserve,),
        coalition_commit=_commit(),
        current_time_s=2.0,
        center_failed=True,
    )

    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.primary_locked_resource_ids == ()
    assert summary.coalition_visual_consensus is False
    assert summary.visual_png_authorized_resource_ids == ()


def test_old_commit_epoch_blocks_consensus_and_png_authority() -> None:
    bindings = (
        _binding("R1", "primary", coalition_epoch=8),
        _binding("R2", "primary", coalition_epoch=8),
        _binding("R3", "reserve", coalition_epoch=8),
    )
    current = (_association("R1", "primary", 2), _association("R2", "primary", 2))

    summary = summarize_coalition_visual_completion(
        bindings,
        current,
        _stable_primary_history(),
        coalition_commit=_commit(epoch=7),
        current_time_s=2.0,
    )

    assert summary.coalition_commit_valid is False
    assert summary.coalition_conflict_state == "coalition_commit_epoch_mismatch"
    assert summary.coalition_visual_consensus is False
    assert summary.visual_png_authorized_resource_ids == ()


def test_expired_commit_lease_blocks_consensus() -> None:
    summary = summarize_coalition_visual_completion(
        _bindings(),
        (_association("R1", "primary", 2), _association("R2", "primary", 2)),
        _stable_primary_history(),
        coalition_commit=_commit(lease_expires_at_s=1.5),
        current_time_s=2.0,
    )

    assert summary.coalition_commit_valid is False
    assert summary.reason == "coalition_commit_lease_expired"
    assert summary.coalition_execution_state == "hold"
    assert summary.visual_png_authorized_resource_ids == ()


def test_missing_member_ack_blocks_consensus() -> None:
    summary = summarize_coalition_visual_completion(
        _bindings(),
        (_association("R1", "primary", 2), _association("R2", "primary", 2)),
        _stable_primary_history(),
        coalition_commit=_commit(acked_members=("R1", "R2")),
        current_time_s=2.0,
    )

    assert summary.coalition_commit_valid is False
    assert summary.coalition_conflict_state == "coalition_commit_member_ack_incomplete"
    assert summary.coalition_commit_acked_member_ids == ("R1", "R2")
    assert summary.coalition_visual_consensus is False
    assert summary.primary_locked_resource_ids == ()
    assert summary.stable_lock_frame_count_by_resource == {"R1": 0, "R2": 0}
    assert summary.metadata["committed_current_primary_resource_ids"] == ()
    assert summary.metadata["uncommitted_current_primary_resource_ids"] == (
        "R1",
        "R2",
    )


def test_commit_plan_version_conflict_blocks_consensus() -> None:
    summary = summarize_coalition_visual_completion(
        _bindings(),
        (_association("R1", "primary", 2), _association("R2", "primary", 2)),
        _stable_primary_history(),
        coalition_commit=vars(_commit(plan_version=8)),
        current_time_s=2.0,
    )

    assert summary.coalition_commit_valid is False
    assert summary.coalition_conflict_state == "coalition_commit_plan_version_mismatch"
    assert summary.visual_png_authorized_resource_ids == ()


def test_uncommitted_fallback_state_blocks_consensus() -> None:
    summary = summarize_coalition_visual_completion(
        _bindings(),
        (_association("R1", "primary", 2), _association("R2", "primary", 2)),
        _stable_primary_history(),
        coalition_commit=_commit(state="collecting_acks"),
        current_time_s=2.0,
    )

    assert summary.coalition_commit_state == "collecting_acks"
    assert summary.coalition_conflict_state == "coalition_commit_not_committed"
    assert summary.coalition_visual_consensus is False
    assert summary.visual_png_authorized_resource_ids == ()


def test_center_failure_without_commit_fails_closed_for_multi_resource_target() -> None:
    summary = summarize_coalition_visual_completion(
        _bindings(),
        (_association("R1", "primary", 2), _association("R2", "primary", 2)),
        _stable_primary_history(),
        current_time_s=2.0,
        center_failed=True,
    )

    assert summary.coalition_commit_required is True
    assert summary.coalition_commit_valid is False
    assert summary.reason == "coalition_commit_missing"
    assert summary.coalition_visual_consensus is False


def test_center_contract_remains_compatible_without_fallback_commit() -> None:
    summary = summarize_coalition_visual_completion(
        _bindings(),
        (_association("R1", "primary", 2), _association("R2", "primary", 2)),
        _stable_primary_history(),
    )

    assert summary.coalition_commit_required is False
    assert summary.coalition_commit_valid is True
    assert summary.coalition_visual_consensus is True
    assert summary.visual_png_authorized_resource_ids == ("R1", "R2")


def test_online_truth_metadata_cannot_rebind_commit_summary_global_id() -> None:
    current = (
        _association(
            "R1",
            "primary",
            2,
            metadata={
                "truth_id": "TRUTH-TARGET-OTHER",
                "actor_name": "MSM_TargetActor_Other",
                "offline_truth_global_id": "G-OTHER",
            },
        ),
        _association("R2", "primary", 2),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
        coalition_commit=_commit(),
        current_time_s=2.0,
    )

    assert summary.global_track_id == "G1"
    assert summary.metadata["global_id_policy"] == "existing_assigned_global_track_id_only"
    assert summary.coalition_visual_consensus is True


def test_reserve_only_replan_preserves_primary_stability_into_new_version() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        first = _association(
            resource_id,
            "primary",
            1,
            plan_version=1,
            plan_id="plan-reserve-v1",
            coalition_version=1,
        )
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=first,
            frame_id="snapshot-1",
        )
    first_summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=1,
            plan_id="plan-reserve-v1",
            coalition_version=1,
            reserve_resource_id="R3",
        )
    )
    assert first_summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}

    for resource_id in ("R1", "R2"):
        second = _association(
            resource_id,
            "primary",
            2,
            plan_version=2,
            plan_id="plan-reserve-v2",
            coalition_version=2,
        )
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=second,
            frame_id="snapshot-2",
        )
    reserve = _association(
        "R4",
        "reserve",
        2,
        plan_version=2,
        plan_id="plan-reserve-v2",
        coalition_version=2,
        decision_state="hold",
        visual_match_state="locked",
    )
    bus.publish_terminal_association(
        resource_id="R4",
        source_node_id="C2",
        link_type="c2_direct",
        timestamp=2.0,
        terminal_association=reserve,
        frame_id="snapshot-2",
    )

    summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=2,
            plan_id="plan-reserve-v2",
            coalition_version=2,
            reserve_resource_id="R4",
        )
    )

    assert summary.plan_version == 2
    assert summary.coalition_version == 2
    assert summary.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 2}
    assert summary.coalition_visual_consensus is True
    assert summary.visual_png_authorized_resource_ids == ("R1", "R2")
    assert summary.reserve_ready_resource_ids == ("R4",)
    assert summary.metadata[
        "stability_continued_across_plan_version_resource_ids"
    ] == ("R1", "R2")
    assert summary.metadata["stability_source_plan_versions_by_resource"] == {
        "R1": [2, 1],
        "R2": [2, 1],
    }


def test_non_increasing_coalition_version_blocks_new_plan_continuity() -> None:
    for next_coalition_version in (4, 3):
        bus = TerminalObservationBus()
        for resource_id in ("R1", "R2"):
            bus.publish_terminal_association(
                resource_id=resource_id,
                source_node_id="C2",
                link_type="c2_direct",
                timestamp=1.0,
                terminal_association=_association(
                    resource_id,
                    "primary",
                    1,
                    plan_version=9,
                    coalition_version=4,
                ),
                frame_id="snapshot-1",
            )
        bus.coalition_visual_summary(_bindings(plan_version=9, coalition_version=4))

        for resource_id in ("R1", "R2"):
            bus.publish_terminal_association(
                resource_id=resource_id,
                source_node_id="C2",
                link_type="c2_direct",
                timestamp=2.0,
                terminal_association=_association(
                    resource_id,
                    "primary",
                    2,
                    plan_version=10,
                    coalition_version=next_coalition_version,
                ),
                frame_id="snapshot-2",
            )
        summary = bus.coalition_visual_summary(
            _bindings(plan_version=10, coalition_version=next_coalition_version)
        )

        assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
        assert summary.coalition_visual_consensus is False
        assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
            "coalition_version_not_strictly_monotonic"
        }


def test_coalition_id_change_blocks_new_plan_continuity() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=_association(
                resource_id,
                "primary",
                1,
                plan_version=9,
                coalition_id="coalition-old",
                coalition_version=1,
            ),
            frame_id="snapshot-1",
        )
    bus.coalition_visual_summary(
        _bindings(
            plan_version=9,
            coalition_id="coalition-old",
            coalition_version=1,
        )
    )

    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=_association(
                resource_id,
                "primary",
                2,
                plan_version=10,
                coalition_id="coalition-new",
                coalition_version=2,
            ),
            frame_id="snapshot-2",
        )
    summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=10,
            coalition_id="coalition-new",
            coalition_version=2,
        )
    )

    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
        "coalition_id_changed"
    }


def test_primary_membership_change_resets_new_primary_stability() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=_association(
                resource_id, "primary", 1, plan_version=9, coalition_version=4
            ),
            frame_id="snapshot-1",
        )
    bus.coalition_visual_summary(_bindings(plan_version=9, coalition_version=4))

    for resource_id in ("R1", "R4"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=_association(
                resource_id, "primary", 2, plan_version=10, coalition_version=5
            ),
            frame_id="snapshot-2",
        )

    summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=10,
            coalition_version=5,
            primary_resource_ids=("R1", "R4"),
            reserve_resource_id="R2",
        )
    )

    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R4": 1}
    assert summary.coalition_visual_consensus is False
    assert summary.visual_png_authorized_resource_ids == ()
    assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
        "primary_membership_changed",
    }


def test_stale_plan_version_replay_clears_stability_and_fails_closed() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=_association(
                resource_id, "primary", 1, plan_version=10, coalition_version=5
            ),
            frame_id="snapshot-1",
        )
    bus.coalition_visual_summary(_bindings(plan_version=10, coalition_version=5))

    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=_association(
                resource_id, "primary", 2, plan_version=9, coalition_version=4
            ),
            frame_id="snapshot-2",
        )

    summary = bus.coalition_visual_summary(_bindings(plan_version=9, coalition_version=4))

    assert summary.plan_version == 9
    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert summary.coalition_conflict_state == "plan_version_not_strictly_monotonic"
    assert summary.metadata["stale_plan_replay_resource_ids"] == ("R1", "R2")


def test_owner_or_epoch_change_does_not_bridge_plan_versions() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=_association(
                resource_id, "primary", 1, plan_version=9, coalition_version=4
            ),
            frame_id="snapshot-1",
        )
    bus.coalition_visual_summary(
        _bindings(plan_version=9, coalition_version=4, coalition_epoch=4)
    )

    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="SEC-1",
            link_type="secondary_mesh",
            timestamp=2.0,
            terminal_association=_association(
                resource_id, "primary", 2, plan_version=10, coalition_version=5
            ),
            frame_id="snapshot-2",
        )
    summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=10,
            coalition_version=5,
            coalition_epoch=5,
            plan_owner="secondary",
            owner_node_id="SEC-1",
        )
    )

    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
        "plan_owner_changed"
    }


def test_epoch_change_with_same_owner_does_not_bridge_plan_versions() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="SEC-1",
            link_type="secondary_mesh",
            timestamp=1.0,
            terminal_association=_association(
                resource_id, "primary", 1, plan_version=9, coalition_version=4
            ),
            frame_id="snapshot-1",
        )
    bus.coalition_visual_summary(
        _bindings(
            plan_version=9,
            coalition_version=4,
            coalition_epoch=4,
            plan_owner="secondary",
            owner_node_id="SEC-1",
        )
    )

    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="SEC-1",
            link_type="secondary_mesh",
            timestamp=2.0,
            terminal_association=_association(
                resource_id, "primary", 2, plan_version=10, coalition_version=5
            ),
            frame_id="snapshot-2",
        )
    summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=10,
            coalition_version=5,
            coalition_epoch=5,
            plan_owner="secondary",
            owner_node_id="SEC-1",
        )
    )

    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
        "coalition_epoch_changed"
    }


def test_commit_conflicted_version_cannot_seed_later_stability() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=_association(
                resource_id, "primary", 1, plan_version=9, coalition_version=4
            ),
            frame_id="snapshot-1",
        )
    conflicted = bus.coalition_visual_summary(
        _bindings(plan_version=9, coalition_version=4),
        coalition_commit=_commit(state="collecting_acks", coalition_version=4),
        current_time_s=1.0,
    )
    assert conflicted.coalition_commit_valid is False

    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=_association(
                resource_id, "primary", 2, plan_version=10, coalition_version=5
            ),
            frame_id="snapshot-2",
        )
    summary = bus.coalition_visual_summary(_bindings(plan_version=10, coalition_version=5))

    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
        "historical_plan_version_safety_conflict"
    }


def test_target_rebind_does_not_reuse_previous_target_stability() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=1.0,
            terminal_association=_association(
                resource_id, "primary", 1, plan_version=9, coalition_version=4
            ),
            frame_id="snapshot-1",
        )
    bus.coalition_visual_summary(_bindings(plan_version=9, coalition_version=4))

    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="C2",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=_association(
                resource_id,
                "primary",
                2,
                plan_version=10,
                coalition_version=5,
                global_track_id="G2",
            ),
            frame_id="snapshot-2",
        )
    summary = bus.coalition_visual_summary(
        _bindings(
            plan_version=10,
            coalition_version=5,
            global_track_id="G2",
            target_id="T002",
        )
    )

    assert summary.global_track_id == "G2"
    assert summary.stable_lock_frame_count_by_resource == {"R1": 1, "R2": 1}
    assert summary.coalition_visual_consensus is False
    assert set(summary.metadata["stability_reset_reason_by_resource"].values()) == {
        "resource_target_binding_changed"
    }
