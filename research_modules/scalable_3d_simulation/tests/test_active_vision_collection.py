from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from research_modules.scalable_3d_simulation.active_vision_collection import (
    ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1,
    ACTIVE_VISION_OPERATIONAL_PROFILE_V1,
    bind_active_vision_recipe_treatment,
    resolve_active_vision_collection_treatment,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.learning_source_recipes import (
    load_d5_a3_v3_episode_recipes,
)
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


def test_collection_treatments_preserve_operational_default_and_bound_busy_time() -> None:
    operational = resolve_active_vision_collection_treatment(
        ACTIVE_VISION_OPERATIONAL_PROFILE_V1
    )
    balanced = resolve_active_vision_collection_treatment(
        ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1
    )

    assert operational.recon_cue_suppressed(1.1) is False
    assert operational.camera_settle_seconds(
        intent="reacquire",
        yaw_delta_deg=90.0,
        pitch_delta_deg=0.0,
        fov_changed=False,
    ) == 0.0
    assert balanced.recon_cue_suppressed(1.1) is True
    assert balanced.recon_cue_suppressed(1.6) is False
    assert balanced.camera_settle_seconds(
        intent="reacquire",
        yaw_delta_deg=90.0,
        pitch_delta_deg=0.0,
        fov_changed=False,
    ) == balanced.camera_maximum_settle_s
    assert balanced.camera_settle_seconds(
        intent="hold",
        yaw_delta_deg=90.0,
        pitch_delta_deg=0.0,
        fov_changed=True,
    ) == 0.0


def test_frozen_collection_retains_truth_free_recon_cues_across_geometry_change() -> None:
    schedule = (
        Path(__file__).resolve().parents[2]
        / "d5_terminal_association"
        / "configs"
        / "a3_v3_source_collection_schedule_20260801.json"
    )
    recipe = load_d5_a3_v3_episode_recipes(schedule)[0]
    config = recipe.build_config(
        ScenarioConfig(
            target_count=4,
            resource_count=4,
            recon_count=2,
            duration_s=recipe.duration_s,
            seed=recipe.seed,
        )
    )
    collection = bind_active_vision_recipe_treatment(
        resolve_active_vision_collection_treatment(
            ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1
        ),
        config,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d5_recon_track_cues_enabled=True)
    )
    stack.latest_plan = SimpleNamespace(
        assignments=tuple(
            SimpleNamespace(resource_id=f"INT-{index:04d}", target_id=target_id)
            for index, target_id in enumerate(
                ("GT-001", "GT-002", "GT-003", "GT-004"),
                start=1,
            )
        )
    )
    tracks = {
        target_id: SimpleNamespace(
            state=np.array([*position, 0.0, 0.0, 0.0]),
            covariance=np.eye(6),
            timestamp=0.0,
        )
        for target_id, position in {
            "GT-001": (100.0, 0.0, 0.0),
            "GT-002": (0.0, 100.0, 0.0),
            "GT-003": (-100.0, 0.0, 0.0),
            "GT-004": (0.0, -100.0, 0.0),
        }.items()
    }

    def cameras(yaw_deg: float) -> tuple[SimpleNamespace, ...]:
        return tuple(
            SimpleNamespace(
                camera_id=f"CAM-RECON-{index:03d}",
                resource_id=f"RECON-{index:03d}",
                platform_kind="recon",
                yaw_deg=yaw_deg,
                pitch_deg=0.0,
            )
            for index in (1, 2)
        )

    navigation = SimpleNamespace(
        platform_ids=("RECON-001", "RECON-002"),
        active=(True, True),
        state_ned=np.zeros((2, 6), dtype=float),
    )
    first_cameras = cameras(0.0)
    step_input = SimpleNamespace(
        timestamp=0.0,
        recon=navigation,
        cameras=first_cameras,
    )
    first = stack._active_vision_recon_track_cues(
        step_input,
        track_by_id=tracks,
        camera_by_resource={item.resource_id: item for item in first_cameras},
        treatment=collection,
    )
    reversed_cameras = cameras(180.0)
    step_input.cameras = reversed_cameras
    retained = stack._active_vision_recon_track_cues(
        step_input,
        track_by_id=tracks,
        camera_by_resource={item.resource_id: item for item in reversed_cameras},
        treatment=collection,
    )

    assert {
        item.camera_id: item.global_track_id for item in retained
    } == {
        item.camera_id: item.global_track_id for item in first
    }
    assert set(stack._d5_collection_recon_target_by_camera.values()).issubset(
        tracks
    )

    removed_target_id = first[0].global_track_id
    remaining_tracks = {
        target_id: track
        for target_id, track in tracks.items()
        if target_id != removed_target_id
    }
    stack.latest_plan = SimpleNamespace(
        assignments=tuple(
            assignment
            for assignment in stack.latest_plan.assignments
            if assignment.target_id != removed_target_id
        )
    )
    rebound = stack._active_vision_recon_track_cues(
        step_input,
        track_by_id=remaining_tracks,
        camera_by_resource={item.resource_id: item for item in reversed_cameras},
        treatment=collection,
    )
    assert removed_target_id not in {
        item.global_track_id for item in rebound
    }
    assert set(stack._d5_collection_recon_target_by_camera.values()).issubset(
        remaining_tracks
    )

    operational = stack._active_vision_recon_track_cues(
        step_input,
        track_by_id=remaining_tracks,
        camera_by_resource={item.resource_id: item for item in reversed_cameras},
        treatment=resolve_active_vision_collection_treatment(
            ACTIVE_VISION_OPERATIONAL_PROFILE_V1
        ),
    )
    assert {
        item.camera_id: item.global_track_id for item in operational
    } != {
        item.camera_id: item.global_track_id for item in first
    }
    assert stack._d5_collection_recon_target_by_camera == {}


def test_balanced_runtime_reaches_missing_action_role_cells_without_truth() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            capture_learning_artifacts=True,
            d5_recon_track_cues_enabled=True,
            d5_active_vision_collection_profile=(
                ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1
            ),
        )
    )
    config = ScenarioConfig(
        scenario_name="a3_action_role_reachability",
        scenario_version="a3-action-role-reachability-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=1.4,
        seed=21_100,
        radar_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
    )

    result = run_episode(config, module_stack=stack)
    counts: Counter[tuple[str, str]] = Counter()
    recon_search_preserved_assignment_count = 0
    for frame in stack.learning_artifacts().d5_active_vision_frames:
        camera_by_id = {
            camera.camera_id: camera for camera in frame.snapshot.cameras
        }
        for decision in frame.decisions:
            action = decision.effective_action
            camera = camera_by_id[action.camera_id]
            role = (
                "recon"
                if camera.resource_id.startswith("RECON-")
                else "interceptor"
            )
            counts[(action.intent.value, role)] += 1
            if action.intent.value == "search_sector" and role == "recon":
                assigned_target_ids = frame.snapshot.assigned_target_ids(
                    action.camera_id
                )
                assert assigned_target_ids
                assert all(
                    frame.snapshot.projection(action.camera_id, target_id) is None
                    for target_id in assigned_target_ids
                )
                recon_search_preserved_assignment_count += 1

    assert result.summary["online_truth_use_count"] == 0
    assert result.summary["finite_state"] is True
    assert counts[("hold", "interceptor")] > 0
    assert counts[("hold", "recon")] > 0
    assert counts[("search_sector", "recon")] > 0
    assert recon_search_preserved_assignment_count > 0
    runtime_profile = result.manifest.runtime_profile
    assert runtime_profile["configuration"][
        "d5_active_vision_collection_profile"
    ] == ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1
    assert runtime_profile["d5_active_vision_collection_treatment"][
        "recon_cue_loss_duration_s"
    ] == 0.45


def test_frozen_recipe_windows_drive_rule_actions_from_bound_inputs() -> None:
    schedule = (
        Path(__file__).resolve().parents[2]
        / "d5_terminal_association"
        / "configs"
        / "a3_v3_source_collection_schedule_20260801.json"
    )
    recipe = load_d5_a3_v3_episode_recipes(schedule)[0]
    base = ScenarioConfig(
        scenario_name="d5_recipe_base",
        scenario_version="d5-recipe-base-v1",
        target_count=1,
        resource_count=1,
        region_count=1,
        duration_s=recipe.duration_s,
        seed=recipe.seed,
    )
    config = recipe.build_config(base)
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            capture_learning_artifacts=True,
            d5_recon_track_cues_enabled=True,
            d5_active_vision_collection_profile=(
                ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1
            ),
        )
    )

    result = run_episode(config, module_stack=stack)
    expected_action_count: Counter[tuple[str, str]] = Counter()
    observed_input_condition: Counter[tuple[str, str]] = Counter()
    forbidden_markers = (
        "intent-window",
        "treatment_recipe",
        "learning_source_recipe",
        "TGT-",
    )
    for frame in stack.learning_artifacts().d5_active_vision_frames:
        for decision in frame.decisions:
            camera = frame.snapshot.camera(decision.effective_action.camera_id)
            role = (
                "recon"
                if camera.resource_id.startswith("RECON-")
                else "interceptor"
            )
            window = next(
                (
                    item
                    for item in recipe.intent_windows
                    if item.camera_role == role
                    and item.start_s <= frame.timestamp_s < item.end_s
                ),
                None,
            )
            if window is None:
                continue
            assigned = frame.snapshot.assigned_target_ids(camera.camera_id)
            evidence = tuple(
                frame.snapshot.projection(camera.camera_id, target_id)
                for target_id in assigned
            )
            if decision.effective_action.intent.value == window.intent:
                expected_action_count[(window.intent, role)] += 1
            if window.intent == "observe_target" and (
                len(assigned) == 1
                and evidence[0] is not None
                and evidence[0].in_fov
                and evidence[0].measurement_timestamp == frame.timestamp_s
            ):
                observed_input_condition[(window.intent, role)] += 1
            elif window.intent == "search_sector" and assigned and all(
                item is None for item in evidence
            ):
                observed_input_condition[(window.intent, role)] += 1
            elif window.intent == "hold" and (
                camera.action_in_progress_until is not None
                and camera.action_in_progress_until > frame.timestamp_s
            ):
                observed_input_condition[(window.intent, role)] += 1
            elif window.intent == "reacquire" and (
                len(assigned) == 1
                and evidence[0] is not None
                and not evidence[0].in_fov
                and evidence[0].measurement_timestamp == frame.timestamp_s
            ):
                observed_input_condition[(window.intent, role)] += 1

            online_payload = repr((frame.snapshot, decision.effective_action))
            assert all(marker not in online_payload for marker in forbidden_markers)

    expected_cells = {
        (window.intent, window.camera_role) for window in recipe.intent_windows
    }
    assert result.summary["online_truth_use_count"] == 0
    assert all(expected_action_count[cell] > 0 for cell in expected_cells)
    assert all(observed_input_condition[cell] > 0 for cell in expected_cells)
    assert len(
        result.manifest.runtime_profile[
            "d5_active_vision_collection_treatment"
        ]["intent_windows"]
    ) == 4


def test_frozen_recipe_roles_alternate_without_changing_track_ownership() -> None:
    schedule = (
        Path(__file__).resolve().parents[2]
        / "d5_terminal_association"
        / "configs"
        / "a3_v3_source_collection_schedule_20260801.json"
    )
    first, second = load_d5_a3_v3_episode_recipes(schedule)[:2]

    assert tuple(item.intent for item in first.intent_windows) == tuple(
        item.intent for item in second.intent_windows
    )
    assert tuple(item.camera_role for item in first.intent_windows) == (
        "interceptor",
        "recon",
        "interceptor",
        "recon",
    )
    assert tuple(item.camera_role for item in second.intent_windows) == (
        "recon",
        "interceptor",
        "recon",
        "interceptor",
    )
