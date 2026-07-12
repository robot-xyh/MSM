from __future__ import annotations

import pytest

from d7_proportional_guidance import (
    GuidanceState,
    MidcourseReacquisitionConfig,
    MidcourseReacquisitionSelector,
    compute_midcourse_reacquisition_command,
)


def test_not_closing_enters_bounded_pursuit_and_positive_closing_recovers_pn() -> None:
    selector = MidcourseReacquisitionSelector(
        MidcourseReacquisitionConfig(
            enter_closing_speed_mps=0.0,
            exit_closing_speed_mps=1.0,
            enter_consecutive_frames=2,
            exit_consecutive_frames=3,
            max_reacquisition_turn_rate_radps=0.4,
        )
    )
    target = _target(position_x=100.0)

    nominal = _compute(selector, _pursuer(0.0, 10.0), target)
    first_bad = _compute(selector, _pursuer(1.0, -5.0), target)
    entered = _compute(selector, _pursuer(2.0, -5.0), target)

    assert nominal.metadata["midcourse_guidance_selection"] == "radar_pn"
    assert nominal.metadata["midcourse_selection_reason"] == "pn_nominal_positive_closing"
    assert first_bad.metadata["midcourse_guidance_selection"] == "radar_pn"
    assert first_bad.metadata["midcourse_selection_reason"] == "reacquisition_entry_hysteresis:not_closing"
    assert entered.metadata["midcourse_guidance_selection"] == "pure_pursuit_reacquisition"
    assert entered.metadata["midcourse_selection_reason"] == "not_closing"
    assert entered.metadata["guidance_law"] == "pure_pursuit"
    assert abs(entered.limited_turn_rate_radps) <= 0.4

    recovering_1 = _compute(selector, _pursuer(3.0, 5.0), target)
    interrupted = _compute(selector, _pursuer(4.0, -1.0), target)
    recovering_2 = _compute(selector, _pursuer(5.0, 5.0), target)
    recovering_3 = _compute(selector, _pursuer(6.0, 5.0), target)
    recovered = _compute(selector, _pursuer(7.0, 5.0), target)

    assert recovering_1.metadata["midcourse_selection_reason"] == "positive_closing_recovery_hysteresis"
    assert interrupted.metadata["midcourse_reacquisition_recovery_streak"] == 0
    assert recovering_2.metadata["midcourse_guidance_selection"] == "pure_pursuit_reacquisition"
    assert recovering_3.metadata["midcourse_guidance_selection"] == "pure_pursuit_reacquisition"
    assert recovered.metadata["midcourse_guidance_selection"] == "radar_pn"
    assert recovered.metadata["midcourse_selection_reason"] == "positive_closing_recovered"
    assert recovered.metadata["guidance_law"] == "radar_pn"
    assert selector.reacquisition_active is False


def test_range_growth_after_closest_approach_records_overshoot_reason() -> None:
    selector = MidcourseReacquisitionSelector(
        MidcourseReacquisitionConfig(
            enter_consecutive_frames=1,
            overshoot_range_increase_m=2.0,
            range_increase_epsilon_m=0.05,
        )
    )
    target = _target(position_x=0.0)

    _compute(selector, _pursuer(-5.0, 1.0), target)
    _compute(selector, _pursuer(-3.0, 1.0), target)
    overshot = _compute(selector, _pursuer(6.0, 1.0), target)

    assert overshot.metadata["midcourse_guidance_selection"] == "pure_pursuit_reacquisition"
    assert overshot.metadata["midcourse_selection_reason"] == "range_increasing_after_closest_approach"
    assert overshot.metadata["midcourse_overshoot_detected"] is True
    assert overshot.metadata["midcourse_minimum_range_m"] == pytest.approx(3.0)


def test_reset_clears_pair_reacquisition_history() -> None:
    selector = MidcourseReacquisitionSelector(
        MidcourseReacquisitionConfig(enter_consecutive_frames=1)
    )
    target = _target(position_x=100.0)
    active = _compute(selector, _pursuer(0.0, -2.0), target)
    assert active.metadata["midcourse_reacquisition_active"] is True

    selector.reset()
    reset_command = _compute(selector, _pursuer(0.0, 5.0), target)

    assert reset_command.metadata["midcourse_reacquisition_active"] is False
    assert reset_command.metadata["midcourse_minimum_range_m"] == pytest.approx(100.0)
    assert reset_command.metadata["midcourse_selection_count"] == 1


def test_assignment_pairs_keep_independent_reacquisition_state() -> None:
    config = MidcourseReacquisitionConfig(enter_consecutive_frames=1)
    selector_1 = MidcourseReacquisitionSelector(config)
    selector_2 = MidcourseReacquisitionSelector(config)
    target = _target(position_x=100.0)

    pair_1 = _compute(selector_1, _pursuer(0.0, -2.0), target)
    pair_2 = _compute(selector_2, _pursuer(0.0, 5.0), target)

    assert pair_1.metadata["midcourse_guidance_selection"] == "pure_pursuit_reacquisition"
    assert pair_2.metadata["midcourse_guidance_selection"] == "radar_pn"
    assert selector_1.reacquisition_active is True
    assert selector_2.reacquisition_active is False


def test_config_rejects_invalid_hysteresis() -> None:
    with pytest.raises(ValueError, match="exit_closing_speed_mps"):
        MidcourseReacquisitionConfig(
            enter_closing_speed_mps=1.0,
            exit_closing_speed_mps=1.0,
        )
    with pytest.raises(ValueError, match="consecutive frame"):
        MidcourseReacquisitionConfig(enter_consecutive_frames=0)


def _compute(
    selector: MidcourseReacquisitionSelector,
    pursuer: GuidanceState,
    target: GuidanceState,
):
    return compute_midcourse_reacquisition_command(
        selector,
        pursuer=pursuer,
        target=target,
        dt_s=0.1,
        navigation_constant=3.0,
        max_lateral_accel_mps2=20.0,
        max_turn_rate_radps=0.9,
    )


def _pursuer(position_x: float, velocity_x: float) -> GuidanceState:
    return GuidanceState(
        entity_id="INT-01",
        timestamp_s=0.0,
        position_m=(position_x, 0.0),
        velocity_mps=(velocity_x, 0.0),
        source="airsim_state",
    )


def _target(position_x: float) -> GuidanceState:
    return GuidanceState(
        entity_id="TGT-001",
        timestamp_s=0.0,
        position_m=(position_x, 0.0),
        velocity_mps=(0.0, 0.0),
        source="global_track",
    )
