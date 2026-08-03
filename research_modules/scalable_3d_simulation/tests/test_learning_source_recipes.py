from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.learning_source_recipes import (
    D3_A1_V3_RECIPE_SCHEMA_VERSION,
    D4_A2_V8_RECIPE_SCHEMA_VERSION,
    D5_A3_V3_RECIPE_SCHEMA_VERSION,
    LearningSourceRecipeError,
    load_d3_a1_v3_episode_recipes,
    load_d4_a2_v8_episode_recipes,
    load_d5_a3_v3_episode_recipes,
)
from research_modules.scalable_3d_simulation.episode_treatments import (
    build_d4_region_graph_treatment,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    _region_ids,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


ROOT = Path(__file__).resolve().parents[3]
D3_SCHEDULE = (
    ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_generation_schedule_v1.json"
)
D4_REGISTRY = (
    ROOT
    / "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
    "v8_development_seed_registry.json"
)
D5_SCHEDULE = (
    ROOT
    / "research_modules/d5_terminal_association/configs/"
    "a3_v3_source_collection_schedule_20260801.json"
)


def test_d3_recipes_preserve_frozen_order_split_and_unequal_counts() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)

    assert len(recipes) == 300
    assert [item.entry_index for item in recipes] == list(range(300))
    assert {item.seed for item in recipes} == set(range(23000, 23300))
    assert Counter(item.split for item in recipes) == {
        "train": 180,
        "validation": 60,
        "test": 60,
    }
    assert {item.schema_version for item in recipes} == {
        D3_A1_V3_RECIPE_SCHEMA_VERSION
    }
    unequal = [item for item in recipes if item.target_count != item.resource_count]
    assert len(unequal) == 60
    assert {
        (item.scenario_family, item.target_count, item.resource_count)
        for item in unequal
    } == {
        ("resource_shortage", 30, 20),
        ("resource_surplus", 20, 30),
        ("dynamic_add_drop", 100, 80),
    }


def test_d3_dynamic_and_near_tie_treatments_are_explicit() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
    dynamic = next(item for item in recipes if item.scenario_family == "dynamic_add_drop")
    near_tie = next(
        item for item in recipes if item.scenario_family == "near_tie_hard_negative"
    )

    assert dynamic.runtime_scenario == "nominal"
    assert dynamic.duration_s == 14.0
    assert dynamic.treatment_id == "anonymous_external_event_schedule_v1"
    dynamic_events = [
        (
            item.fraction_of_duration,
            item.entity_kind,
            item.action,
            item.ordinal_count,
            item.selection_key,
        )
        for item in dynamic.roster_events
    ]
    assert not any("-quota-target-" in item[4] for item in dynamic_events)
    assert [
        item
        for item in dynamic_events
        if item[4].startswith("dynamic-") and "-quota-" not in item[4]
    ] == [
        (0.0, "intruder", "deactivate", 10, "dynamic-target-a"),
        (0.1, "intruder", "deactivate", 10, "dynamic-target-b"),
        (0.2, "intruder", "activate", 10, "dynamic-target-a"),
        (0.3, "interceptor", "deactivate", 8, "dynamic-resource-a"),
        (0.9, "interceptor", "activate", 8, "dynamic-resource-a"),
    ]
    assert [
        (
            item.start_fraction_of_duration,
            item.end_fraction_of_duration,
            item.minimum_assignment_ticks,
        )
        for item in dynamic.stable_observation_windows
    ] == [(0.45, 1.0, 4)]
    assert near_tie.runtime_scenario == "dense_crossing"
    assert near_tie.treatment_id == "near_tie_cost_boundary_v1"
    assert len(near_tie.roster_events) == 2
    assert [
        (
            item.start_fraction_of_duration,
            item.end_fraction_of_duration,
            item.minimum_assignment_ticks,
        )
        for item in near_tie.stable_observation_windows
    ] == [(0.0, 1.0, 4)]


def test_d3_problem_cells_receive_preregistered_anonymous_events() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
    by_cell = {item.cell_id: item for item in recipes}

    formation = by_cell["formation-split-50t50r"]
    assert formation.treatment_id == "anonymous_external_event_schedule_v1"
    assert formation.duration_s == 10.0
    formation_specific = [
        item
        for item in formation.roster_events
        if item.selection_key == "formation-target-a"
    ]
    assert [(item.entity_kind, item.action) for item in formation_specific] == [
        ("intruder", "deactivate"),
        ("intruder", "activate"),
    ]
    assert [item.fraction_of_duration for item in formation_specific] == [0.2, 0.55]

    for cell_id in ("resource-surplus-20t30r", "resource-shortage-30t20r"):
        recipe = by_cell[cell_id]
        specific = [
            item
            for item in recipe.roster_events
            if item.selection_key in {"surplus-resource-a", "shortage-resource-a"}
        ]
        assert [(item.entity_kind, item.action) for item in specific] == [
            ("interceptor", "deactivate"),
            ("interceptor", "activate"),
        ]
        config = recipe.build_config(ScenarioConfig())
        serialized = json.dumps(config.metadata["learning_source_recipe"])
        assert "ordinal_start" not in serialized
        assert '"global_track_id":' not in serialized
        assert "truth_id" not in serialized


def test_d3_fault_cells_delay_faults_until_after_quota_events() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
    by_cell = {item.cell_id: item for item in recipes}

    for cell_id in ("center-failure-20t20r", "secondary-failure-50t50r"):
        recipe = by_cell[cell_id]
        config = recipe.build_config(ScenarioConfig())
        raw = config.metadata["learning_source_recipe"]["fault_schedule_profile"]
        assert raw["profile_id"].startswith("d3_late_")
        assert raw["events"] == config.metadata["fault_schedule"]
        assert all(event["time_s"] >= 0.65 * recipe.duration_s for event in raw["events"])
        assert all(event["time_s"] < recipe.duration_s for event in raw["events"])


def test_d3_unstable_cells_receive_noncopying_stable_windows() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
    by_cell = {item.cell_id: item for item in recipes}

    for cell_id in (
        "delayed-noisy-200t200r",
        "communication-degraded-5t5r",
        "dynamic-add-drop-100t80r",
        "evasive-multilevel-100t100r",
        "formation-split-50t50r",
        "high-threat-m-to-n-100t100r",
        "high-threat-m-to-n-200t200r",
        "near-tie-hard-negative-50t50r",
    ):
        recipe = by_cell[cell_id]
        expected_treatment = (
            "near_tie_cost_boundary_v1"
            if cell_id == "near-tie-hard-negative-50t50r"
            else "anonymous_external_event_schedule_v1"
        )
        assert recipe.treatment_id == expected_treatment
        assert len(recipe.roster_events) >= 2
        assert len(recipe.stable_observation_windows) == 1
        window = recipe.stable_observation_windows[0]
        assert window.minimum_assignment_ticks >= 3
        config = recipe.build_config(ScenarioConfig())
        raw = config.metadata["learning_source_recipe"][
            "stable_observation_windows"
        ][0]
        assert raw["frame_copying_allowed"] is False
        expected_mode = (
            "radar_only_noiseless_regeneration_v1"
            if cell_id == "delayed-noisy-200t200r"
            else "noiseless_regeneration_v1"
        )
        assert raw["observation_mode"] == expected_mode


def test_d3_late_stable_windows_preserve_early_scenario_motion() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
    by_cell = {item.cell_id: item for item in recipes}
    expected = {
        "dynamic-add-drop-100t80r": (0.45, 1.0, 4),
        "evasive-multilevel-100t100r": (0.4125, 1.0, 4),
        "formation-split-50t50r": (0.0, 1.0, 4),
        "near-tie-hard-negative-50t50r": (0.0, 1.0, 4),
        "high-threat-m-to-n-100t100r": (0.0, 1.0, 4),
        "high-threat-m-to-n-200t200r": (0.0, 1.0, 4),
    }

    for cell_id, values in expected.items():
        windows = by_cell[cell_id].stable_observation_windows
        assert len(windows) == 1
        window = windows[0]
        assert (
            window.start_fraction_of_duration,
            window.end_fraction_of_duration,
            window.minimum_assignment_ticks,
        ) == values
        assert window.observation_mode == "noiseless_regeneration_v1"

    assert by_cell["evasive-multilevel-100t100r"].duration_s == 12.0


def test_d3_dense_50_recipes_use_the_exact_noncopying_stable_window() -> None:
    recipes = [
        item
        for item in load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
        if item.cell_id == "dense-crossing-50t50r"
    ]

    assert len(recipes) == 20
    for recipe in recipes:
        assert len(recipe.stable_observation_windows) == 1
        window = recipe.stable_observation_windows[0]
        assert window.start_fraction_of_duration == 0.55
        assert window.end_fraction_of_duration == 1.0
        assert window.minimum_assignment_ticks == 4
        assert window.observation_mode == "noiseless_regeneration_v1"

        config = recipe.build_config(ScenarioConfig())
        raw = config.metadata["learning_source_recipe"]
        assert raw["stable_observation_windows"] == [
            {
                "start_fraction_of_duration": 0.55,
                "end_fraction_of_duration": 1.0,
                "minimum_assignment_ticks": 4,
                "window_key": "dense-crossing-50t50r-stable-a",
                "kinematic_mode": "hold_state_v1",
                "observation_mode": "noiseless_regeneration_v1",
                "frame_copying_allowed": False,
            }
        ]


def test_d3_center_failure_recipe_does_not_retake_the_active_regional_owner() -> None:
    recipe = next(
        item
        for item in load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
        if item.entry_index == 140
    )
    stack = IntegratedScalableModuleStack()

    result = run_episode(recipe.build_config(ScenarioConfig()), module_stack=stack)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_plan is not None
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["owner_node_id"] == "RECON-001"


def test_d3_recipes_use_universal_or_specialized_preregistered_roster_cadence() -> None:
    recipes = load_d3_a1_v3_episode_recipes(D3_SCHEDULE)

    for recipe in recipes:
        quota_events = [
            item for item in recipe.roster_events if "-quota-" in item.selection_key
        ]
        actual = [
            (item.fraction_of_duration, item.entity_kind, item.action, item.ordinal_count)
            for item in quota_events
        ]
        if recipe.cell_id in {
            "dynamic-add-drop-100t80r",
            "formation-split-50t50r",
        }:
            assert actual == []
            continue
        if recipe.cell_id == "evasive-multilevel-100t100r":
            assert actual == [
                (0.18333333333333332, "intruder", "deactivate", 1),
                (0.4125, "intruder", "activate", 1),
            ]
            assert quota_events[0].selection_key == quota_events[1].selection_key
            continue
        assert actual == [
            (0.20, "intruder", "deactivate", 1),
            (0.45, "intruder", "activate", 1),
        ]
        assert quota_events[0].selection_key == quota_events[1].selection_key


def test_d3_recipe_builds_non_authoritative_runtime_config() -> None:
    recipe = next(
        item
        for item in load_d3_a1_v3_episode_recipes(D3_SCHEDULE)
        if item.scenario_family == "resource_shortage"
    )
    config = recipe.build_config(ScenarioConfig())

    assert (config.target_count, config.resource_count) == (30, 20)
    assert config.duration_s == 10.0
    metadata = config.metadata["learning_source_recipe"]
    assert metadata["episode_id"] == recipe.episode_id
    assert metadata["split"] == recipe.split
    assert metadata["scenario_family"] == "resource_shortage"
    assert not any(metadata["permissions"].values())


def test_d4_recipes_cover_full_frozen_matrix_without_seed_reuse() -> None:
    recipes = load_d4_a2_v8_episode_recipes(D4_REGISTRY)

    assert len(recipes) == 324
    assert [item.entry_index for item in recipes] == list(range(324))
    assert {item.seed for item in recipes} == set(range(28100, 28424))
    assert {item.schema_version for item in recipes} == {
        D4_A2_V8_RECIPE_SCHEMA_VERSION
    }
    assert {item.region_count for item in recipes} == {8, 9, 12, 16}
    assert {item.topology_id for item in recipes} == {
        "directed_ring_8",
        "directed_grid_3x3",
        "directed_ring_12",
        "directed_mesh_16",
    }
    assert {item.communication_condition for item in recipes} == {
        "nominal",
        "bounded_delay_and_loss",
        "partition_then_recovery",
    }
    assert {item.requested_target_class for item in recipes} == {
        "safe_forward_transfer",
        "safe_reverse_transfer",
        "hard_no_transfer_negative",
    }
    assert all(item.split == "train" for item in recipes)


def test_d4_recipe_config_carries_topology_and_runtime_period() -> None:
    recipe = next(
        item
        for item in load_d4_a2_v8_episode_recipes(D4_REGISTRY)
        if item.topology_id == "directed_grid_3x3"
        and item.communication_condition == "partition_then_recovery"
    )
    config = recipe.build_config(ScenarioConfig())

    assert config.region_count == 9
    assert config.region_policy_period_s == 1.0
    assert (config.target_count, config.resource_count, config.recon_count) == (18, 27, 3)
    metadata = config.metadata["learning_source_recipe"]
    assert metadata["topology_id"] == "directed_grid_3x3"
    assert metadata["communication_condition"] == "partition_then_recovery"
    assert config.metadata["communication_partition_schedule"] == [
        {"time_s": 1.0, "generation": 1},
        {"time_s": 2.0, "generation": 2},
    ]
    assert not any(metadata["permissions"].values())


def test_d4_region_graph_treatments_materialize_all_frozen_topologies() -> None:
    recipes = load_d4_a2_v8_episode_recipes(D4_REGISTRY)
    expected_edge_counts = {
        "directed_ring_8": 16,
        "directed_grid_3x3": 24,
        "directed_ring_12": 24,
        "directed_mesh_16": 240,
    }

    for topology_id, expected_count in expected_edge_counts.items():
        recipe = next(
            item
            for item in recipes
            if item.topology_id == topology_id
            and item.communication_condition == "partition_then_recovery"
        )
        config = recipe.build_config(ScenarioConfig())
        treatment = build_d4_region_graph_treatment(config)
        assert treatment is not None
        region_ids = tuple(f"region-{index:03d}" for index in range(recipe.region_count))
        pairs = treatment.directed_pairs(region_ids)

        assert len(pairs) == expected_count
        assert len(set(pairs)) == expected_count
        assert treatment.partitioned_pairs(region_ids, timestamp_s=0.5) == frozenset()
        assert treatment.partitioned_pairs(region_ids, timestamp_s=1.5)
        assert treatment.partitioned_pairs(region_ids, timestamp_s=2.0) == frozenset()
        assert all(source != target for source, target in pairs)


def test_d4_partition_window_changes_runtime_edges_and_recovers() -> None:
    recipe = next(
        item
        for item in load_d4_a2_v8_episode_recipes(D4_REGISTRY)
        if item.topology_id == "directed_grid_3x3"
        and item.communication_condition == "partition_then_recovery"
    )
    config = recipe.build_config(ScenarioConfig())
    stack = IntegratedScalableModuleStack()
    stack.reset(config)
    region_ids = _region_ids(config.region_count)
    signals = {
        region_id: {
            "available_resources": 3,
            "reserve_resources": 0,
            "committed_resources": 1,
        }
        for region_id in region_ids
    }

    before = stack._d4_region_resource_edges(
        region_ids,
        signals,
        timestamp_s=0.5,
    )
    during = stack._d4_region_resource_edges(
        region_ids,
        signals,
        timestamp_s=1.5,
    )
    recovered = stack._d4_region_resource_edges(
        region_ids,
        signals,
        timestamp_s=2.0,
    )

    assert len(before) == len(during) == len(recovered) == 24
    assert sum(edge.partitioned for edge in before) == 0
    assert sum(edge.partitioned for edge in during) == 8
    assert sum(edge.communication_available for edge in during) == 16
    assert sum(edge.partitioned for edge in recovered) == 0


def test_d5_recipes_preserve_frozen_episode_entries_and_quota() -> None:
    recipes = load_d5_a3_v3_episode_recipes(D5_SCHEDULE)

    assert len(recipes) == 104
    assert [item.entry_index for item in recipes] == list(range(104))
    assert {item.seed for item in recipes} == set(range(24000, 24104))
    assert Counter(item.split for item in recipes) == {
        "train": 48,
        "validation": 24,
        "future_held_out": 32,
    }
    assert {item.schema_version for item in recipes} == {
        D5_A3_V3_RECIPE_SCHEMA_VERSION
    }
    assert all(len(item.intent_windows) == 4 for item in recipes)
    assert all(len(item.hard_confusion_assignments) == 2 for item in recipes)
    assert sum(
        sum(window.minimum_unique_samples for window in item.intent_windows)
        for item in recipes
    ) == 9984
    assert {
        hard.family
        for item in recipes
        for hard in item.hard_confusion_assignments
    } == {
        "observe_vs_reacquire_projection_boundary",
        "search_vs_reacquire_cue_loss_boundary",
        "hold_vs_observe_gimbal_busy_boundary",
        "role_matched_interceptor_recon_geometry",
        "multiple_legal_targets_near_tie",
    }


def test_d5_recipe_builds_exact_m_n_recon_and_window_metadata() -> None:
    recipe = next(
        item
        for item in load_d5_a3_v3_episode_recipes(D5_SCHEDULE)
        if item.scale == 200
    )
    config = recipe.build_config(ScenarioConfig())

    assert (config.target_count, config.resource_count, config.recon_count) == (
        recipe.target_count,
        recipe.resource_count,
        recipe.recon_count,
    )
    assert config.duration_s == 8.0
    metadata = config.metadata["learning_source_recipe"]
    assert metadata["episode_id"] == recipe.episode_id
    assert len(metadata["intent_windows"]) == 4
    assert metadata["minimum_unique_sample_quota"]["total"] == 96
    assert not any(metadata["permissions"].values())


@pytest.mark.parametrize(
    ("source", "loader", "mutation", "code"),
    (
        (
            D3_SCHEDULE,
            load_d3_a1_v3_episode_recipes,
            lambda payload: payload["episodes"][0].pop("cell_id"),
            "schedule_entry_fields_mismatch",
        ),
        (
            D4_REGISTRY,
            load_d4_a2_v8_episode_recipes,
            lambda payload: payload["schedule"][0].__setitem__("split", "validation"),
            "unsupported_value",
        ),
        (
            D5_SCHEDULE,
            load_d5_a3_v3_episode_recipes,
            lambda payload: payload["episode_entries"][0]["generation_controls"].__setitem__(
                "sample_copying_allowed", True
            ),
            "d5_generation_control_not_false",
        ),
    ),
)
def test_recipe_loaders_fail_closed_on_schedule_drift(
    tmp_path: Path,
    source: Path,
    loader,
    mutation,
    code: str,
) -> None:
    payload = deepcopy(json.loads(source.read_text(encoding="utf-8")))
    mutation(payload)
    path = tmp_path / source.name
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LearningSourceRecipeError, match=code):
        loader(path)
