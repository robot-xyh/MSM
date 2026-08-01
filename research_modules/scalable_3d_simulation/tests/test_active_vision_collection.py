from __future__ import annotations

from collections import Counter

from research_modules.scalable_3d_simulation.active_vision_collection import (
    ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1,
    ACTIVE_VISION_OPERATIONAL_PROFILE_V1,
    resolve_active_vision_collection_treatment,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
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
