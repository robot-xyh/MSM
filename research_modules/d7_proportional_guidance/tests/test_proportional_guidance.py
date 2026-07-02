from __future__ import annotations

import math

from d7_proportional_guidance import (
    GuidanceConfig,
    GuidanceMode,
    GuidanceState,
    compute_proportional_navigation_command,
    simulate_guidance_episode,
)


def test_pure_pn_reduces_range() -> None:
    config = GuidanceConfig(
        dt_s=0.05,
        max_duration_s=4.0,
        terminal_switch_range_m=1.0,
        navigation_constant=3.0,
        max_lateral_accel_mps2=80.0,
        max_turn_rate_radps=1.0,
        stop_at_intercept_radius=False,
    )
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (140.0, 0.0))
    target = GuidanceState("T0", 0.0, (1000.0, 160.0), (-20.0, 0.0))

    records, summary = simulate_guidance_episode(pursuer, target, config)

    assert records
    assert all(record.mode == GuidanceMode.RADAR_MIDCOURSE for record in records)
    assert summary["final_range_m"] < summary["initial_range_m"]
    assert records[-1].range_m < records[0].range_m * 0.6


def test_terminal_vision_pn_switches_mode() -> None:
    config = GuidanceConfig(
        dt_s=0.1,
        max_duration_s=6.0,
        terminal_switch_range_m=650.0,
        navigation_constant=3.0,
        max_lateral_accel_mps2=70.0,
        max_turn_rate_radps=1.0,
        stop_at_intercept_radius=False,
    )
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (160.0, 0.0))
    target = GuidanceState("T0", 0.0, (900.0, 100.0), (-10.0, 0.0))

    records, summary = simulate_guidance_episode(pursuer, target, config)
    modes = [record.mode for record in records]

    assert GuidanceMode.RADAR_MIDCOURSE in modes
    assert GuidanceMode.VISION_TERMINAL in modes
    assert summary["terminal_mode_entered"] is True
    assert any(record.mode_switch for record in records)
    assert records[-1].mode == GuidanceMode.VISION_TERMINAL


def test_acceleration_and_turn_rate_limits_apply() -> None:
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (100.0, 0.0))
    target = GuidanceState("T0", 0.0, (200.0, 800.0), (-300.0, 0.0))

    command = compute_proportional_navigation_command(
        pursuer=pursuer,
        target=target,
        dt_s=0.1,
        navigation_constant=5.0,
        mode=GuidanceMode.RADAR_MIDCOURSE,
        max_lateral_accel_mps2=8.0,
        max_turn_rate_radps=0.03,
    )

    assert abs(command.commanded_lateral_accel_mps2) > 8.0
    assert abs(command.limited_turn_rate_radps) <= 0.03 + 1e-12
    assert abs(command.limited_lateral_accel_mps2) <= 3.0 + 1e-12
    assert command.is_saturated


def test_records_include_guidance_geometry_fields() -> None:
    config = GuidanceConfig(
        dt_s=0.1,
        max_duration_s=1.0,
        terminal_switch_range_m=500.0,
        stop_at_intercept_radius=False,
    )
    records, _summary = simulate_guidance_episode(config=config)

    assert records
    for record in records:
        assert isinstance(record.mode, GuidanceMode)
        assert record.range_m >= 0.0
        assert math.isfinite(record.los_angle_rad)
        assert math.isfinite(record.los_rate_radps)
        assert math.isfinite(record.closing_speed_mps)
        data = record.as_dict()
        assert {"mode", "range_m", "los_angle_rad", "closing_speed_mps"} <= set(data)
