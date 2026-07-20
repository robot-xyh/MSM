from __future__ import annotations

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.dynamics import integrate_point_masses
from research_modules.scalable_3d_simulation.models import KinematicLimits, ScenarioConfig
from research_modules.scalable_3d_simulation.world import VectorizedPointMassWorld
from research_modules.scalable_3d_simulation.scenarios import make_curriculum_scenario


def test_ned_altitude_and_seeded_reset_are_consistent() -> None:
    config = ScenarioConfig(target_count=20, resource_count=20, recon_count=2, duration_s=0.1)
    world = VectorizedPointMassWorld(config)
    first = world.snapshot()
    world.step()
    reset = world.reset()
    assert np.all(-first.intruders.position_ned[:, 2] >= config.minimum_altitude_m)
    assert np.all(-first.intruders.position_ned[:, 2] <= config.maximum_altitude_m)
    assert np.array_equal(first.intruders.state, reset.intruders.state)
    assert np.array_equal(first.interceptors.state, reset.interceptors.state)


def test_dynamics_enforce_speed_acceleration_turn_and_inactive_state() -> None:
    state = np.array(
        [
            [0.0, 0.0, -100.0, 10.0, 0.0, 0.0],
            [1.0, 2.0, -80.0, 2.0, 1.0, 0.0],
        ]
    )
    command = np.array([[100.0, 100.0, 100.0], [5.0, 5.0, 5.0]])
    limits = KinematicLimits(
        max_speed_mps=12.0,
        max_accel_mps2=4.0,
        max_turn_rate_radps=0.5,
        max_climb_rate_mps=1.0,
    )
    result, realized = integrate_point_masses(
        state,
        command,
        dt_s=0.1,
        limits=limits,
        active=np.array([True, False]),
    )
    assert np.linalg.norm(result[0, 3:]) <= limits.max_speed_mps + 1.0e-9
    assert abs(result[0, 5]) <= limits.max_climb_rate_mps + 1.0e-9
    assert np.linalg.norm(realized[0]) <= limits.max_accel_mps2 + 1.0e-6
    assert np.array_equal(result[1], state[1])
    assert np.array_equal(realized[1], np.zeros(3))


@pytest.mark.parametrize("scale", [5, 20, 50, 100, 200])
def test_world_supports_curriculum_scales_without_shape_assumptions(scale: int) -> None:
    config = ScenarioConfig(
        target_count=scale,
        resource_count=scale,
        recon_count=max(1, scale // 25),
        duration_s=0.1,
    )
    world = VectorizedPointMassWorld(config)
    for _ in range(2):
        diagnostics = world.step()
        assert diagnostics.finite_state
    snapshot = world.snapshot()
    assert snapshot.intruders.state.shape == (scale, 6)
    assert snapshot.interceptors.state.shape == (scale, 6)
    assert np.all(np.isfinite(snapshot.intruders.state))
    assert np.all(np.isfinite(snapshot.interceptors.state))


def test_intercept_registration_uses_three_dimensional_five_meter_radius() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.1,
        intercept_radius_m=5.0,
    )
    world = VectorizedPointMassWorld(config)
    world.interceptor_state[0, :3] = np.array([0.0, 0.0, -100.0])
    world.intruder_state[0, :3] = np.array([3.0, 0.0, -96.0])
    assert world.register_intercepts(np.array([[0, 0]], dtype=int)) == (0,)
    assert not world.intruder_active[0]


def test_proximity_intercepts_are_unique_and_truth_bearing_only_offline() -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=0,
        duration_s=0.1,
        intercept_radius_m=5.0,
    )
    world = VectorizedPointMassWorld(config)
    world.interceptor_state[:, :3] = np.array(
        [[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]], dtype=float
    )
    world.intruder_state[:, :3] = np.array(
        [[3.0, 0.0, -96.0], [104.0, 0.0, -100.0]], dtype=float
    )
    events = world.register_proximity_intercepts()
    assert len(events) == 2
    assert {event.resource_id for event in events} == {"INT-0001", "INT-0002"}
    assert {event.truth_target_id for event in events} == {"TGT-0001", "TGT-0002"}
    assert not np.any(world.intruder_active)


@pytest.mark.parametrize(
    ("name", "profile"),
    [
        ("nominal", "constant_velocity"),
        ("dense_crossing", "crossing"),
        ("formation_split", "formation_split"),
        ("evasive_multilevel", "evasive"),
    ],
)
def test_scenario_catalog_freezes_scale_seed_and_motion(name: str, profile: str) -> None:
    config = make_curriculum_scenario(name, scale=50, seed=19, duration_s=3.0)
    assert config.target_count == 50
    assert config.resource_count == 50
    assert config.seed == 19
    assert config.motion_profile.value == profile
    assert config.metadata["catalog_version"] == "scalable3d-catalog-v1"


def test_fault_scenario_is_explicitly_marked_as_runtime_pending() -> None:
    config = make_curriculum_scenario("secondary_failure", scale=20, seed=7, duration_s=9.0)
    assert len(config.metadata["fault_schedule"]) == 2
    assert config.metadata["fault_schedule_runtime_required"] is True
