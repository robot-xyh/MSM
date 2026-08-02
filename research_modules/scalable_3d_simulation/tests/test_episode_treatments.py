from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.episode_bus import jsonable
from research_modules.scalable_3d_simulation.episode_treatments import (
    build_d4_supply_demand_treatment,
)
from research_modules.scalable_3d_simulation.learning_source_recipes import (
    load_d4_a2_v8_episode_recipes,
)
from research_modules.scalable_3d_simulation.models import OnlineSensorBatch, ScenarioConfig
from research_modules.scalable_3d_simulation.orchestrator import run_episode


ROOT = Path(__file__).resolve().parents[3]
D4_REGISTRY = (
    ROOT
    / "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
    "v8_development_seed_registry.json"
)


def _dynamic_roster_config() -> ScenarioConfig:
    return ScenarioConfig(
        scenario_name="dynamic_roster_test",
        scenario_version="dynamic-roster-test-v1",
        seed=31,
        target_count=20,
        resource_count=12,
        recon_count=2,
        region_count=2,
        duration_s=8.0,
        physics_dt_s=0.125,
        radar_period_s=0.25,
        acoustic_period_s=0.25,
        visual_period_s=0.25,
        association_period_s=0.25,
        assignment_period_s=0.25,
        region_policy_period_s=1.0,
        radar_enabled=True,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
        radar_detection_probability=1.0,
        metadata={
            "learning_source_recipe": {
                "module": "D3",
                "treatment_id": "anonymous_external_event_schedule_v1",
                "roster_events": [
                    {
                        "fraction_of_duration": 0.0,
                        "entity_kind": "intruder",
                        "action": "deactivate",
                        "ordinal_count": 10,
                        "selection_key": "target-a",
                        "selection_method": "episode_seeded_permutation_v1",
                    },
                    {
                        "fraction_of_duration": 0.25,
                        "entity_kind": "intruder",
                        "action": "activate",
                        "ordinal_count": 10,
                        "selection_key": "target-a",
                        "selection_method": "episode_seeded_permutation_v1",
                    },
                    {
                        "fraction_of_duration": 0.5,
                        "entity_kind": "intruder",
                        "action": "deactivate",
                        "ordinal_count": 10,
                        "selection_key": "target-b",
                        "selection_method": "episode_seeded_permutation_v1",
                    },
                    {
                        "fraction_of_duration": 0.625,
                        "entity_kind": "interceptor",
                        "action": "deactivate",
                        "ordinal_count": 8,
                        "selection_key": "resource-a",
                        "selection_method": "episode_seeded_permutation_v1",
                    },
                    {
                        "fraction_of_duration": 0.75,
                        "entity_kind": "interceptor",
                        "action": "activate",
                        "ordinal_count": 8,
                        "selection_key": "resource-a",
                        "selection_method": "episode_seeded_permutation_v1",
                    },
                ],
                "stable_observation_windows": [],
            }
        },
    )


def _at(result, timestamp_s: float) -> int:
    matches = np.flatnonzero(np.isclose(result.timestamps, timestamp_s))
    assert matches.size == 1
    return int(matches[0])


def test_dynamic_roster_treatment_applies_before_same_timestamp_snapshot() -> None:
    result = run_episode(_dynamic_roster_config())

    assert np.count_nonzero(result.intruder_active_history[_at(result, 0.0)]) == 10
    assert np.count_nonzero(result.intruder_active_history[_at(result, 2.0)]) == 20
    assert np.count_nonzero(result.intruder_active_history[_at(result, 4.0)]) == 10
    assert np.count_nonzero(result.interceptor_active_history[_at(result, 5.0)]) == 4
    assert np.count_nonzero(result.interceptor_active_history[_at(result, 6.0)]) == 12
    assert np.all(result.recon_active_history)

    records = result.episode_treatment_audit_records
    assert [record.applied_timestamp_s for record in records] == [
        0.0,
        2.0,
        4.0,
        5.0,
        6.0,
    ]
    assert [(record.active_count_before, record.active_count_after) for record in records] == [
        (20, 10),
        (10, 20),
        (20, 10),
        (12, 4),
        (4, 12),
    ]
    assert result.summary["episode_treatment_event_count"] == 5
    assert result.summary["episode_treatment_applied_count"] == 5
    assert result.summary["episode_treatment_complete"] is True


def test_treatment_metadata_and_entity_identity_do_not_enter_online_messages(
    tmp_path,
) -> None:
    result = run_episode(_dynamic_roster_config(), output_dir=tmp_path)
    serialized = json.dumps(
        [jsonable(message) for message in result.online_messages],
        sort_keys=True,
    )

    assert result.online_messages
    assert "learning_source_recipe" not in serialized
    assert "roster_event" not in serialized
    assert "ordinal_start" not in serialized
    assert "selected_ordinals" not in serialized
    assert "selection_digest" not in serialized
    assert "episode_treatment" not in serialized
    assert "TGT-" not in serialized
    assert all(
        record.to_dict()["online_truth_use_count"] == 0
        and record.to_dict()["identity_values_present"] is False
        for record in result.episode_treatment_audit_records
    )
    assert result.output_paths is not None
    audit_path = result.output_paths["episode_treatment_audit"]
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_payload["schema_version"] == (
        "scalable3d-episode-treatment-audit-v2"
    )
    assert len(audit_payload["records"]) == 5
    assert all("ordinal_start" not in item for item in audit_payload["records"])
    assert all("selected_ordinals" not in item for item in audit_payload["records"])
    assert len(audit_payload["content_sha256"]) == 64
    with np.load(result.output_paths["offline_truth_state"]) as truth_state:
        assert np.array_equal(
            truth_state["interceptor_active"],
            result.interceptor_active_history,
        )
        assert np.array_equal(truth_state["recon_active"], result.recon_active_history)


def test_non_treatment_episode_retains_fully_active_rosters() -> None:
    config = ScenarioConfig(
        target_count=5,
        resource_count=4,
        recon_count=1,
        region_count=1,
        duration_s=0.2,
        physics_dt_s=0.1,
        radar_period_s=0.1,
        acoustic_period_s=0.1,
        visual_period_s=0.1,
        association_period_s=0.1,
        assignment_period_s=0.1,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )

    result = run_episode(config)

    assert np.all(result.intruder_active_history)
    assert np.all(result.interceptor_active_history)
    assert np.all(result.recon_active_history)
    assert result.episode_treatment_audit_records == ()
    assert result.summary["episode_treatment_event_count"] == 0
    assert result.summary["episode_treatment_applied_count"] == 0
    assert result.summary["episode_treatment_complete"] is True


def test_stable_window_holds_world_and_regenerates_identity_free_observations() -> None:
    config = ScenarioConfig(
        target_count=5,
        resource_count=5,
        recon_count=1,
        duration_s=4.0,
        physics_dt_s=0.1,
        radar_period_s=0.2,
        acoustic_period_s=0.5,
        visual_period_s=0.2,
        association_period_s=0.2,
        assignment_period_s=0.5,
        radar_enabled=True,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
        metadata={
            "learning_source_recipe": {
                "module": "D3",
                "treatment_id": "anonymous_external_event_schedule_v1",
                "roster_events": [],
                "stable_observation_windows": [
                    {
                        "start_fraction_of_duration": 0.25,
                        "end_fraction_of_duration": 0.75,
                        "minimum_assignment_ticks": 3,
                        "window_key": "stable-a",
                        "kinematic_mode": "hold_state_v1",
                        "observation_mode": "noiseless_regeneration_v1",
                        "frame_copying_allowed": False,
                    }
                ],
            }
        },
    )

    result = run_episode(config)
    start = _at(result, 1.0)
    end = _at(result, 3.0)
    held = result.intruder_state_history[start : end + 1]
    assert np.allclose(held, held[0][None, :, :])
    assert not np.allclose(
        result.intruder_state_history[end + 1],
        result.intruder_state_history[end],
    )
    records = result.episode_treatment_audit_records
    assert [(item.treatment_kind, item.action) for item in records] == [
        ("stable_observation_window", "start"),
        ("stable_observation_window", "end"),
    ]
    assert result.summary["episode_treatment_event_count"] == 2
    assert result.summary["episode_treatment_complete"] is True
    stable_batches = [
        message.payload
        for message in result.online_messages
        if isinstance(message.payload, OnlineSensorBatch)
        and 1.0 <= message.payload.measurement_timestamp < 3.0
    ]
    assert len(stable_batches) >= 3
    assert len({item.batch_id for item in stable_batches}) == len(stable_batches)
    assert len({item.measurement_timestamp for item in stable_batches}) == len(
        stable_batches
    )
    reference = [item.measurement for item in stable_batches[0].measurements]
    for batch in stable_batches[1:]:
        assert all(
            np.array_equal(actual.measurement, expected)
            for actual, expected in zip(batch.measurements, reference, strict=True)
        )


def test_radar_only_stable_window_suppresses_other_sources_without_catchup() -> None:
    config = ScenarioConfig(
        target_count=3,
        resource_count=3,
        recon_count=1,
        duration_s=2.0,
        physics_dt_s=0.05,
        radar_period_s=0.1,
        acoustic_period_s=0.2,
        visual_period_s=0.1,
        association_period_s=0.1,
        assignment_period_s=0.25,
        radar_enabled=True,
        acoustic_enabled=True,
        visual_enabled=True,
        communication_enabled=False,
        radar_detection_probability=1.0,
        acoustic_range_limit_m=10_000.0,
        acoustic_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
        metadata={
            "learning_source_recipe": {
                "module": "D3",
                "treatment_id": "anonymous_external_event_schedule_v1",
                "roster_events": [],
                "stable_observation_windows": [
                    {
                        "start_fraction_of_duration": 0.0,
                        "end_fraction_of_duration": 0.5,
                        "minimum_assignment_ticks": 3,
                        "window_key": "radar-only-a",
                        "kinematic_mode": "hold_state_v1",
                        "observation_mode": (
                            "radar_only_noiseless_regeneration_v1"
                        ),
                        "frame_copying_allowed": False,
                    }
                ],
            }
        },
    )

    result = run_episode(config)
    sensor_batches = [
        message.payload
        for message in result.online_messages
        if isinstance(message.payload, OnlineSensorBatch)
    ]
    before_end = [
        batch for batch in sensor_batches if batch.measurement_timestamp < 1.0
    ]
    after_end = [
        batch for batch in sensor_batches if batch.measurement_timestamp >= 1.0
    ]
    assert before_end
    assert {
        measurement.modality
        for batch in before_end
        for measurement in batch.measurements
    } == {"radar_spherical"}
    assert {measurement.modality for batch in after_end for measurement in batch.measurements} >= {
        "radar_spherical",
        "acoustic_bearing",
    }
    assert 0 < result.summary["camera_frame_event_generated_count"] <= 48
    assert result.summary["episode_treatment_complete"] is True


def test_anonymous_roster_selection_is_seeded_and_never_serializes_ordinals() -> None:
    first = run_episode(_dynamic_roster_config())
    second = run_episode(_dynamic_roster_config())
    different_seed = run_episode(replace(_dynamic_roster_config(), seed=32))
    first_records = [item.to_dict() for item in first.episode_treatment_audit_records]
    second_records = [item.to_dict() for item in second.episode_treatment_audit_records]

    assert first_records == second_records
    assert first_records[0]["selection_digest"] == first_records[1]["selection_digest"]
    assert first_records[0]["selection_digest"] != (
        different_seed.episode_treatment_audit_records[0].selection_digest
    )
    assert all("selected_ordinals" not in item for item in first_records)
    assert all("ordinal_start" not in item for item in first_records)


def test_anonymous_treatment_rejects_identity_or_label_inputs() -> None:
    config = _dynamic_roster_config()
    metadata = dict(config.metadata)
    recipe = dict(metadata["learning_source_recipe"])
    events = [dict(item) for item in recipe["roster_events"]]
    events[0]["global_track_id"] = "forbidden"
    recipe["roster_events"] = events
    metadata["learning_source_recipe"] = recipe

    with pytest.raises(ValueError, match="forbidden identity or label field"):
        run_episode(replace(config, metadata=metadata))


def test_d4_supply_demand_treatments_materialize_all_frozen_boundaries() -> None:
    recipes = load_d4_a2_v8_episode_recipes(D4_REGISTRY)
    representatives = {
        (
            item.supply_demand_condition,
            item.requested_target_class,
            item.requested_transfer_resource_count,
            item.hard_negative_candidate_resource_count,
        ): item
        for item in recipes
        if item.topology_id == "directed_ring_8"
        and item.communication_condition == "nominal"
    }
    assert len(representatives) == 27

    for recipe in representatives.values():
        config = recipe.build_config(ScenarioConfig())
        treatment = build_d4_supply_demand_treatment(config)
        assert treatment is not None
        region_ids = tuple(f"region-{index:03d}" for index in range(8))
        base = {
            region_id: {
                "target_demand": 2.0,
                "high_threat_backlog": 0.0,
                "available_resources": 3,
                "reserve_resources": 1,
                "committed_resources": 0,
            }
            for region_id in region_ids
        }
        treated = treatment.apply(region_ids, base)
        gaps = []
        for region_id in region_ids:
            signal = treated[region_id]
            reserve_floor = max(
                1,
                int(np.ceil(0.10 * signal["available_resources"])),
                int(signal["reserve_resources"]),
            )
            gaps.append(
                int(signal["available_resources"])
                - int(signal["committed_resources"])
                - reserve_floor
                - int(np.ceil(signal["target_demand"]))
            )

        condition = recipe.supply_demand_condition
        if condition == "source_surplus_target_deficit":
            assert any(value > 0 for value in gaps)
            assert any(value < 0 for value in gaps)
        elif condition == "balanced_boundary":
            assert all(abs(value) <= 1 for value in gaps)
        else:
            assert sum(gaps) < 0
            assert any(value > 0 for value in gaps)

        source_index, _ = treatment.candidate_index_pair()
        source = treated[region_ids[source_index]]
        transferable = max(
            0,
            int(source["available_resources"])
            - int(source["committed_resources"])
            - max(
                1,
                int(np.ceil(0.10 * source["available_resources"])),
                int(source["reserve_resources"]),
            ),
        )
        if recipe.requested_target_class == "hard_no_transfer_negative":
            assert transferable == 0
        else:
            assert transferable >= recipe.requested_transfer_resource_count
        assert not any(treatment.to_dict()["permissions"].values())
