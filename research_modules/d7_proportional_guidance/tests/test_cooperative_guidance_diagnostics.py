from __future__ import annotations

from dataclasses import replace

import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    CooperativeGuidanceCandidateMetadata,
    CooperativeGuidanceDiagnosticSample,
    D4GuidancePermission,
    D7RuntimeBus,
    D7RuntimePairInput,
    PngGuidanceConfig,
    VisionGuidanceObservation,
    build_assignment_pair_guidance_diagnostics,
    coerce_cooperative_guidance_candidate,
    prescreen_cooperative_guidance_candidates,
    summarize_cooperative_guidance_diagnostics,
)


def test_dynamic_primary_diagnostics_identify_second_primary_failure() -> None:
    candidate = _candidate("C-A")
    samples = [
        _sample(candidate, "R1", 5.0, physical=True, separation=12.0),
        _sample(
            candidate,
            "R2",
            5.5,
            control=False,
            mode=False,
            physical=False,
            control_reason="bbox_area_jump",
            disturbance="bbox_area_jump",
            separation=9.0,
        ),
        _sample(candidate, "R3", 6.5, physical=True, separation=10.0),
        _sample(
            candidate,
            "R4",
            5.0,
            role="reserve",
            activation="standby",
            contract=False,
            control=False,
            mode=False,
            physical=False,
            contract_reason="coalition_not_activated",
        ),
    ]

    summary = summarize_cooperative_guidance_diagnostics(samples)
    pairs = {row["resource_id"]: row for row in summary["pair_diagnostics"]}
    coalition = summary["coalition_diagnostics"][0]

    assert summary["pair_count"] == 4
    assert pairs["R1"]["radar_midcourse_reached"] is True
    assert pairs["R1"]["physical_intercept_reached"] is True
    assert pairs["R1"]["arrival_window_error_s"] == pytest.approx(0.0)
    assert pairs["R2"]["first_failure_stage"] == "terminal_control"
    assert pairs["R2"]["first_failure_reason"] == "bbox_area_jump"
    assert pairs["R3"]["arrival_window_error_s"] == pytest.approx(0.5)
    assert pairs["R4"]["first_failure_reason"] == "coalition_not_activated"
    assert coalition["primary_count"] == 3
    assert coalition["arrived_primary_count"] == 2
    assert coalition["coalition_complete"] is False
    assert coalition["coalition_arrival_spread_s"] == pytest.approx(1.5)
    assert coalition["coalition_arrival_spread_complete"] is False
    assert coalition["second_primary_failure_stage"] == "terminal_control"
    assert summary["second_primary_failure_stage_counts"] == {"terminal_control": 1}
    assert coalition["second_primary_canonical_first_failure_stage"] == (
        "terminal_control"
    )
    assert coalition["second_primary_funnel"]["assigned"]["reached"] is True
    assert coalition["second_primary_funnel"]["d5_locked"]["reached"] is True
    assert coalition["second_primary_funnel"]["terminal_contract"]["reached"] is True
    assert coalition["second_primary_funnel"]["terminal_control"]["reached"] is False
    assert coalition["second_primary_first_reached_timestamp_s"][
        "terminal_contract"
    ] == pytest.approx(5.5)
    assert summary["primary_failure_stage_counts_by_ordinal"] == {
        "2": {"terminal_control": 1}
    }
    assert summary["second_primary_canonical_first_failure_stage_counts"] == {
        "terminal_control": 1
    }


def test_candidate_prescreen_uses_fixed_safety_completion_success_spread_order() -> None:
    samples = []
    for candidate_id, arrival_times, safety in (
        ("SAFE", (5.0, 5.4), False),
        ("UNSAFE", (5.0, 5.1), True),
        ("INCOMPLETE", (5.0, None), False),
    ):
        candidate = _candidate(candidate_id)
        for index, arrival_time in enumerate(arrival_times, start=1):
            samples.append(
                _sample(
                    candidate,
                    f"R{index}",
                    arrival_time or 5.8,
                    physical=arrival_time is not None,
                    control=arrival_time is not None,
                    mode=arrival_time is not None,
                    safety=safety and index == 1,
                    coalition_id=f"coalition-{candidate_id}",
                )
            )

    result = prescreen_cooperative_guidance_candidates(samples, top_k=2)

    assert result["selected_candidate_ids"] == ["SAFE", "INCOMPLETE"]
    assert [row["candidate_id"] for row in result["ranked_candidates"]] == [
        "SAFE",
        "INCOMPLETE",
        "UNSAFE",
    ]
    assert result["default_runtime_candidate_changed"] is False
    assert result["png_core_formula_changed"] is False
    assert result["d3_d4_d5_gate_bypassed"] is False
    assert "complete_arrival_spread_asc" not in result["ranking_order"]


def test_ten_seed_pair_identity_isolated_by_episode_and_seed() -> None:
    candidate = _candidate("BASELINE")
    samples = [
        replace(
            _sample(candidate, "R1", 4.0, physical=True),
            episode_id=f"m5n2-seed-{seed:03d}",
            seed=seed,
        )
        for seed in range(1, 11)
    ]

    summary = summarize_cooperative_guidance_diagnostics(samples)

    assert summary["pair_count"] == 10
    assert summary["coalition_count"] == 10
    assert len(summary["rows"]) == 10
    assert {row["seed"] for row in summary["rows"]} == set(range(1, 11))
    assert summary["candidate_summaries"][0]["coalition_completion_rate"] == 1.0
    assert summary["simultaneous_arrival_required"] is False
    assert summary["physical_success_radius_m_values"] == [5.0]


def test_pair_funnel_exposes_d5_stages_reserve_and_identity_mismatches() -> None:
    candidate = _candidate("PAIR-FUNNEL")
    successful = replace(
        _sample(candidate, "R1", 5.0, physical=True),
        episode_id="m5n2-seed-007",
        seed=7,
    )
    second_primary = replace(
        _sample(
            candidate,
            "R2",
            6.0,
            contract=False,
            control=False,
            mode=False,
            physical=False,
            contract_reason="d5_not_locked",
        ),
        episode_id="m5n2-seed-007",
        seed=7,
        d5_visible=True,
        d5_associated=False,
        d5_locked=False,
        owner_mismatch=True,
        version_mismatch=True,
    )
    unauthorized_reserve = replace(
        _sample(
            candidate,
            "R3",
            5.5,
            role="reserve",
            activation="standby",
            physical=False,
        ),
        episode_id="m5n2-seed-007",
        seed=7,
    )

    summary = summarize_cooperative_guidance_diagnostics(
        [successful, second_primary, unauthorized_reserve]
    )
    rows = {row["resource_id"]: row for row in summary["rows"]}

    assert rows["R1"]["assigned"] is True
    assert rows["R1"]["active_primary"] is True
    assert rows["R1"]["closest_range_m"] == pytest.approx(5.0)
    assert rows["R2"]["visible"] is True
    assert rows["R2"]["associated"] is False
    assert rows["R2"]["locked"] is False
    assert rows["R2"]["first_failure_stage"] == "d5_associated"
    assert rows["R2"]["owner_version_mismatch_count"] == 2
    assert rows["R3"]["reserve_unauthorized"] is True
    assert summary["reserve_unauthorized_count"] == 1
    assert summary["owner_mismatch_count"] == 1
    assert summary["version_mismatch_count"] == 1
    assert summary["coalition_diagnostics"][0]["second_primary_failure_stage"] == (
        "d5_associated"
    )


def test_runtime_output_adapter_preserves_explicit_d5_funnel_evidence() -> None:
    output = D7RuntimeBus(_png_config()).evaluate_pair(
        _runtime_input(_binding(), 1.0)
    )

    sample = CooperativeGuidanceDiagnosticSample.from_runtime_output(
        output,
        candidate=_candidate("RUNTIME"),
        episode_id="m5n2-seed-003",
        seed=3,
        metadata={"detection_seen": True, "associated": True},
    )

    assert sample.episode_id == "m5n2-seed-003"
    assert sample.seed == 3
    assert sample.assigned is True
    assert sample.active is True
    assert sample.d5_visible is True
    assert sample.d5_associated is True
    assert sample.d5_locked is True
    assert sample.owner_mismatch is False
    assert sample.version_mismatch is False


def test_m5n2_no_switch_funnel_separates_range_and_d5_lock_failures() -> None:
    candidate = _candidate("M5N2-SEMANTICS-V2")
    bus = D7RuntimeBus(_png_config())
    cases = (
        ("INT-01", "G1", 35.6, "ambiguous"),
        ("INT-02", "G1", 26.3, "reacquire"),
        ("INT-04", "G2", 38.9, "ambiguous"),
    )
    samples = []
    outputs = []
    for index, (resource_id, target_id, range_m, decision_state) in enumerate(cases):
        binding = replace(
            _binding(),
            assignment_id=f"assign-{resource_id}-{target_id}",
            resource_id=resource_id,
            vehicle_name=f"Interceptor-{resource_id}",
            assigned_global_track_id=target_id,
        )
        terminal = _terminal_association(binding)
        terminal["decision_state"] = decision_state
        pair_input = replace(
            _runtime_input(binding, index * 0.1, terminal=terminal),
            terminal_locked=False,
            relative_position_ned=(range_m, 0.0, 0.0),
        )
        output = bus.evaluate_pair(pair_input)
        outputs.append(output)
        samples.append(
            CooperativeGuidanceDiagnosticSample.from_runtime_output(
                output,
                candidate=candidate,
                episode_id="p1-m5n2-seed-001",
                seed=1,
                d5_visible=True,
                d5_associated=True,
            )
        )

    summary = summarize_cooperative_guidance_diagnostics(samples)
    rows = {row["resource_id"]: row for row in summary["rows"]}

    assert all(output.raw_terminal_gate_allowed is False for output in outputs)
    assert all(output.latched_visual_mode_active is False for output in outputs)
    assert all(output.effective_terminal_contract_allowed is False for output in outputs)
    assert all(output.effective_control_authorized is False for output in outputs)
    assert rows["INT-01"]["first_failure_stage"] == "terminal_handoff_range"
    assert rows["INT-01"]["first_failure_reason"] == "terminal_handoff_range_not_reached"
    assert rows["INT-02"]["first_failure_stage"] == "d5_locked"
    assert rows["INT-02"]["first_failure_reason"] == "d5_not_locked"
    assert rows["INT-02"]["funnel"]["raw_terminal_gate"] == {
        "available": True,
        "reached": False,
    }
    assert rows["INT-02"]["funnel"]["d5_measured_lock"] == {
        "available": True,
        "reached": False,
    }
    assert rows["INT-04"]["first_failure_stage"] == "terminal_handoff_range"
    assert summary["pair_first_failure_stage_counts"] == {
        "terminal_handoff_range": 2,
        "d5_locked": 1,
    }
    assert summary["diagnostic_reason_missing_count"] == 0


def test_detailed_funnel_reports_measured_lock_camera_closing_and_maneuver() -> None:
    candidate = _candidate("DETAILED-GATES")
    binding = _binding()

    no_measurement_output = D7RuntimeBus(_png_config()).evaluate_pair(
        replace(
            _runtime_input(binding, 0.0),
            observation=None,
            relative_position_ned=(20.0, 0.0, 0.0),
        )
    )
    no_measurement = CooperativeGuidanceDiagnosticSample.from_runtime_output(
        no_measurement_output,
        candidate=candidate,
        d5_visible=True,
        d5_associated=True,
        d5_locked=True,
    )

    camera_bus = D7RuntimeBus(replace(_png_config(), min_stable_frames=2))
    camera_output = camera_bus.evaluate_pair(
        replace(
            _runtime_input(binding, 0.0),
            relative_position_ned=(20.0, 0.0, 0.0),
        )
    )
    camera_sample = CooperativeGuidanceDiagnosticSample.from_runtime_output(
        camera_output,
        candidate=candidate,
    )

    closing_bus = D7RuntimeBus(_png_config())
    closing_outputs = [
        closing_bus.evaluate_pair(
            replace(
                _runtime_input(binding, timestamp_s),
                relative_position_ned=(20.0, 0.0, 0.0),
                relative_velocity_ned=(5.0, 0.0, 0.0),
            )
        )
        for timestamp_s in (0.0, 0.1, 0.2)
    ]
    closing_samples = [
        CooperativeGuidanceDiagnosticSample.from_runtime_output(
            output,
            candidate=candidate,
        )
        for output in closing_outputs
    ]

    maneuver_sample = replace(
        closing_samples[-1],
        assignment_id="maneuver-R1-G1",
        camera_quality_gate_passed=True,
        los_quality_gate_passed=True,
        closing_speed_gate_passed=True,
        maneuver_margin_gate_passed=False,
        terminal_control_reject_reason="maneuver_margin_low",
    )
    diagnostics = build_assignment_pair_guidance_diagnostics(
        [
            replace(no_measurement, assignment_id="measured-R1-G1"),
            replace(camera_sample, assignment_id="camera-R1-G1"),
            *[
                replace(sample, assignment_id="closing-R1-G1")
                for sample in closing_samples
            ],
            maneuver_sample,
        ]
    )
    by_assignment = {row.assignment_id: row for row in diagnostics}

    assert by_assignment["measured-R1-G1"].first_failure_stage == "d5_measured_lock"
    assert by_assignment["measured-R1-G1"].first_failure_reason == (
        "terminal_visual_acquiring"
    )
    assert by_assignment["camera-R1-G1"].first_failure_stage == "camera_quality"
    assert by_assignment["camera-R1-G1"].first_failure_reason == "stable_frame_count_low"
    assert by_assignment["closing-R1-G1"].first_failure_stage == "closing_speed"
    assert by_assignment["closing-R1-G1"].first_failure_reason == "not_closing"
    assert closing_outputs[-1].closing_speed_gate_passed is False
    assert closing_outputs[-1].closing_speed_gate_threshold_mps == pytest.approx(0.2)
    assert closing_outputs[-1].as_log_record()["closing_speed_gate_passed"] is False
    assert closing_outputs[-1].as_log_record()[
        "closing_speed_gate_threshold_mps"
    ] == pytest.approx(0.2)
    assert by_assignment["maneuver-R1-G1"].first_failure_stage == "maneuver_margin"
    assert by_assignment["maneuver-R1-G1"].first_failure_reason == "maneuver_margin_low"


def test_raw_gate_false_without_reason_is_explicitly_flagged() -> None:
    candidate = _candidate("MISSING-REASON")
    output = D7RuntimeBus(_png_config()).evaluate_pair(
        _runtime_input(_binding(), 0.0)
    )
    sample = CooperativeGuidanceDiagnosticSample.from_runtime_output(
        output,
        candidate=candidate,
    )
    malformed = replace(
        sample,
        raw_terminal_gate_allowed=False,
        raw_terminal_gate_reject_reason="",
        terminal_contract_reject_reason="",
        effective_terminal_contract_allowed=False,
        effective_control_authorized=False,
        terminal_contract_allowed=False,
        terminal_control_allowed=False,
        d5_measured_lock_observed=False,
        camera_quality_gate_passed=None,
        los_quality_gate_passed=None,
        closing_speed_gate_passed=None,
        maneuver_margin_gate_passed=None,
        latched_visual_mode_active=False,
    )

    summary = summarize_cooperative_guidance_diagnostics([malformed])
    row = summary["rows"][0]

    assert row["first_failure_stage"] == "raw_terminal_gate"
    assert row["first_failure_reason"] == "raw_terminal_gate_reject_reason_missing"
    assert row["diagnostic_reason_missing_count"] == 1
    assert summary["diagnostic_reason_missing_count"] == 1


@pytest.mark.parametrize(
    ("permission", "terminal_override", "binding_override", "expected_reason"),
    [
        (
            D4GuidancePermission(action="degrade_to_secondary"),
            {},
            {},
            "d4_reassign_pending",
        ),
        (None, {"decision_state": "ambiguous"}, {}, "d5_not_locked"),
        (None, {"assignment_version": 8}, {}, "assignment_version_mismatch"),
        (
            None,
            {},
            {
                "coalition_id": "coalition-G1",
                "coalition_version": 1,
                "member_role": "reserve",
                "wave_id": 1,
                "coordination_mode": "hybrid",
                "arrival_window_start_s": 0.0,
                "arrival_window_end_s": 5.0,
                "activation_state": "standby",
            },
            "coalition_not_activated",
        ),
    ],
)
def test_contract_failures_and_standby_reserve_fall_back_to_radar_pn(
    permission: D4GuidancePermission | None,
    terminal_override: dict[str, object],
    binding_override: dict[str, object],
    expected_reason: str,
) -> None:
    binding = replace(_binding(), **binding_override)
    terminal = _terminal_association(binding)
    terminal.update(terminal_override)
    output = D7RuntimeBus(_png_config()).evaluate_pair(
        _runtime_input(binding, 1.0, permission=permission, terminal=terminal)
    )

    assert output.visual_png_enabled is False
    assert output.guidance_law == "radar_pn"
    assert output.terminal_contract_reject_reason == expected_reason
    assert output.assigned_global_track_id == "G1"


def test_controlled_area_jump_and_clipping_are_preserved_in_pair_diagnostics() -> None:
    candidate = _candidate("DISTURBANCE")
    jump_bus = D7RuntimeBus(_png_config(law="png_ttc"))
    jump_bus.evaluate_pair(_runtime_input(_binding(), 0.0, size_px=40.0))
    jump_bus.evaluate_pair(_runtime_input(_binding(), 0.1, size_px=44.0))
    jump_output = jump_bus.evaluate_pair(_runtime_input(_binding(), 0.2, size_px=120.0))
    jump_sample = CooperativeGuidanceDiagnosticSample.from_runtime_output(
        jump_output,
        candidate=candidate,
        disturbance_type="bbox_area_jump",
    )

    clip_bus = D7RuntimeBus(_png_config(law="png_ttc"))
    clipped = replace(
        _observation(0.0, size_px=44.0),
        bbox_xyxy=(0.0, 218.0, 44.0, 262.0),
    )
    clip_output = clip_bus.evaluate_pair(
        replace(_runtime_input(_binding(), 0.0), observation=clipped)
    )
    clip_sample = CooperativeGuidanceDiagnosticSample.from_runtime_output(
        clip_output,
        candidate=candidate,
        disturbance_type="bbox_clipping",
    )

    diagnostics = build_assignment_pair_guidance_diagnostics(
        [
            replace(jump_sample, assignment_id="jump-R1-G1"),
            replace(clip_sample, assignment_id="clip-R1-G1"),
        ]
    )
    by_assignment = {row.assignment_id: row for row in diagnostics}

    assert jump_output.ttc_reject_reason == "bbox_area_jump"
    assert by_assignment["jump-R1-G1"].first_failure_reason == "bbox_area_jump"
    assert "bbox_area_jump" in by_assignment["jump-R1-G1"].disturbance_reject_reasons
    assert clip_output.ttc_reject_reason == "bbox_left_clipped"
    assert by_assignment["clip-R1-G1"].first_failure_reason == "bbox_left_clipped"
    assert "bbox_left_clipped" in by_assignment["clip-R1-G1"].disturbance_reject_reasons


def test_dropout_seed_boundary_reports_two_predictions_then_hard_expiry() -> None:
    bus = D7RuntimeBus(_png_config(law="png_vm"))
    binding = _binding()
    for index in range(3):
        bus.evaluate_pair(_runtime_input(binding, index * 0.1))
    reacquire = _terminal_association(binding)
    reacquire["decision_state"] = "reacquire"

    outputs = [
        bus.evaluate_pair(
            replace(
                _runtime_input(binding, timestamp_s, terminal=reacquire),
                observation=None,
            )
        )
        for timestamp_s in (0.3, 0.4, 0.5)
    ]
    samples = [
        CooperativeGuidanceDiagnosticSample.from_runtime_output(
            output,
            candidate=_candidate("DROP-SEED-2"),
            disturbance_type="detection_dropout_seed_2",
            metadata={"seed": 2, "dropout_frame_index": index},
        )
        for index, output in enumerate(outputs, start=1)
    ]

    assert [sample.terminal_delivery_state for sample in samples] == [
        "image_kf_predict",
        "image_kf_predict",
        "expired",
    ]
    assert [sample.terminal_prediction_age_s for sample in samples] == pytest.approx(
        [0.1, 0.2, 0.3]
    )
    assert samples[-1].terminal_delivery_reason == "terminal_visual_prediction_window_expired"
    assert samples[-1].terminal_control_allowed is False


def test_single_frame_dropout_seed2_explains_measured_lock_and_reacquisition() -> None:
    bus = D7RuntimeBus(_png_config(law="png_vm"))
    binding = _binding()
    measured_outputs = [
        bus.evaluate_pair(_runtime_input(binding, index * 0.1))
        for index in range(3)
    ]
    reacquire = _terminal_association(binding)
    reacquire["decision_state"] = "reacquire"
    dropout = bus.evaluate_pair(
        replace(
            _runtime_input(binding, 0.3, terminal=reacquire),
            observation=None,
        )
    )
    reacquired = bus.evaluate_pair(_runtime_input(binding, 0.4))
    outputs = [*measured_outputs, dropout, reacquired]
    samples = [
        CooperativeGuidanceDiagnosticSample.from_runtime_output(
            output,
            candidate=_candidate("DROP-SEED-2-SINGLE"),
            episode_id="2v2-dropout-seed-002",
            seed=2,
            disturbance_type=(
                "single_frame_detection_dropout" if index == 3 else ""
            ),
            metadata={"dropout_frame_index": 1 if index == 3 else 0},
        )
        for index, output in enumerate(outputs)
    ]

    diagnostic = build_assignment_pair_guidance_diagnostics(samples)[0]
    timing = diagnostic.measured_lock_timing

    assert dropout.terminal_delivery_state == "image_kf_predict"
    assert dropout.terminal_visual_lock_measured is False
    assert dropout.terminal_measured_lock_history_available is True
    assert reacquired.terminal_delivery_state == "reacquired"
    assert reacquired.terminal_visual_lock_measured is True
    assert timing["first_measured_lock_timestamp_s"] == pytest.approx(0.0)
    assert timing["first_dropout_timestamp_s"] == pytest.approx(0.3)
    assert timing["first_reacquired_timestamp_s"] == pytest.approx(0.4)
    assert timing["measured_lock_before_first_dropout"] is True
    assert timing["dropout_run_lengths"] == [1]
    assert timing["max_consecutive_dropout_frames"] == 1
    assert timing["single_frame_dropout_reacquired"] is True
    assert diagnostic.funnel_first_reached_timestamp_s["d5_measured_lock"] == (
        pytest.approx(0.0)
    )
    assert len(diagnostic.measured_lock_timeline) == 5
    assert diagnostic.measured_lock_timeline[3][
        "terminal_dropout_reason_scope"
    ] == "bounded_prediction"


def test_candidate_metadata_validation_is_fail_fast() -> None:
    with pytest.raises(ValueError, match="terminal_handoff_range_m"):
        CooperativeGuidanceCandidateMetadata(
            candidate_id="bad",
            terminal_handoff_range_m=0.0,
            primary_arrival_window_width_s=3.0,
            approach_sector_separation_deg=40.0,
        )


def test_candidate_metadata_accepts_frozen_d3_schema() -> None:
    candidate = coerce_cooperative_guidance_candidate(
        {
            "candidate_id": "d3-p1-h030.0-w05.0-s040.0",
            "terminal_handoff_range_m": 30.0,
            "primary_arrival_window_width_s": 5.0,
            "approach_sector_separation_deg": 40.0,
            "schema": "d3_cooperative_prescreen_v1",
        }
    )

    assert candidate.terminal_handoff_range_m == pytest.approx(30.0)
    assert candidate.primary_arrival_window_width_s == pytest.approx(5.0)
    assert candidate.approach_sector_separation_deg == pytest.approx(40.0)
    assert candidate.schema == "d3_cooperative_prescreen_v1"


def _candidate(candidate_id: str) -> CooperativeGuidanceCandidateMetadata:
    return CooperativeGuidanceCandidateMetadata(
        candidate_id=candidate_id,
        terminal_handoff_range_m=30.0,
        primary_arrival_window_width_s=3.0,
        approach_sector_separation_deg=40.0,
        minimum_member_separation_m=5.0,
    )


def _sample(
    candidate: CooperativeGuidanceCandidateMetadata,
    resource_id: str,
    timestamp_s: float,
    *,
    role: str = "primary",
    activation: str = "active",
    contract: bool = True,
    control: bool = True,
    mode: bool = True,
    physical: bool = False,
    contract_reason: str = "",
    control_reason: str = "",
    disturbance: str = "",
    separation: float | None = None,
    safety: bool = False,
    coalition_id: str = "coalition-G1",
) -> CooperativeGuidanceDiagnosticSample:
    return CooperativeGuidanceDiagnosticSample(
        timestamp_s=timestamp_s,
        assignment_id=f"{candidate.candidate_id}-{resource_id}-G1",
        resource_id=resource_id,
        target_id="G1",
        candidate=candidate,
        plan_id=f"plan-{candidate.candidate_id}",
        plan_version=1,
        coalition_id=coalition_id,
        coalition_version=1,
        member_role=role,
        activation_state=activation,
        radar_midcourse_active=True,
        terminal_contract_allowed=contract,
        terminal_control_allowed=control,
        terminal_mode_entered=mode,
        physical_intercept=physical,
        range_m=5.0 if physical else 12.0,
        closing_speed_mps=4.0,
        member_separation_m=separation,
        arrival_window_start_s=4.0,
        arrival_window_end_s=6.0,
        terminal_contract_reject_reason=contract_reason,
        terminal_control_reject_reason=control_reason,
        disturbance_type=disturbance,
        ttc_reject_reason=control_reason if control_reason.startswith("bbox_") else "",
        safety_violation=safety,
    )


def _png_config(*, law: str = "png_vm") -> PngGuidanceConfig:
    return PngGuidanceConfig(
        dt_s=0.1,
        min_bbox_area_ratio=0.0001,
        min_stable_frames=1,
        edge_margin_ratio=0.01,
        max_los_rate_variance_radps2=10.0,
        los_rate_window=2,
        max_visual_latency_s=1.0,
        min_maneuver_margin=0.0,
        law=law,
    )


def _binding() -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-1",
        plan_version=1,
        owner_node_id="center",
        assignment_id="assign-R1-G1",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=9,
        authorization_state="approved",
    )


def _terminal_association(binding: AssignmentGuidanceBinding) -> dict[str, object]:
    return {
        "resource_id": binding.resource_id,
        "assigned_global_track_id": binding.assigned_global_track_id,
        "local_track_id": "BT-1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": binding.track_version,
        "plan_version": binding.plan_version,
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "coalition_visual_complete": True,
        "coalition_support_count": 2,
        "required_resource_count": 2,
        "coalition_conflict_state": "none",
        "metadata": {"execution_gate_pass": True},
    }


def _observation(timestamp_s: float, *, size_px: float = 40.0) -> VisionGuidanceObservation:
    half = size_px / 2.0
    return VisionGuidanceObservation(
        timestamp_s=timestamp_s,
        frame_timestamp_s=timestamp_s,
        bbox_xyxy=(320.0 - half, 240.0 - half, 320.0 + half, 240.0 + half),
        detection_confidence=0.95,
        local_track_id="BT-1",
        assigned_global_track_id="G1",
    )


def _runtime_input(
    binding: AssignmentGuidanceBinding,
    timestamp_s: float,
    *,
    permission: D4GuidancePermission | None = None,
    terminal: dict[str, object] | None = None,
    size_px: float = 40.0,
) -> D7RuntimePairInput:
    return D7RuntimePairInput(
        binding=binding,
        d4_permission=permission
        or D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id=binding.plan_id,
            new_plan_version=binding.plan_version,
        ),
        terminal_association=terminal or _terminal_association(binding),
        observation=_observation(timestamp_s, size_px=size_px),
        timestamp_s=timestamp_s,
        terminal_locked=True,
        current_heading_rad=0.0,
        current_speed_mps=8.0,
        intercept_speed_mps=8.0,
        relative_position_ned=(30.0, 0.0, 0.0),
        relative_velocity_ned=(-5.0, 0.0, 0.0),
    )
