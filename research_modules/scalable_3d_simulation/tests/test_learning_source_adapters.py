from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path

import pytest

from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_data_contract import (
    A1V3EdgeResidualRank,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
    A1V3AdapterFrameEvidence,
    A1V3DatasetWriter,
    build_a1_v3_online_frame,
    load_a1_v3_writer_contract,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_dataset_writer import (
    V8CleanSourceMetadata,
    V8TrainDatasetWriter,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_development_contract import (
    V8TransferClass,
    load_v8_frozen_request,
)
from research_modules.d5_terminal_association.src.d5_terminal_association.active_vision_a3_v3_episode_evidence import (
    A3V3OfflineEpisodeAuditV1,
    A3V3OnlineEpisodeEvidenceV1,
    A3V3EpisodeRecipeV1,
    load_frozen_a3_v3_episode_recipes,
    stage_a3_v3_episode_evidence,
)
from research_modules.scalable_3d_simulation.learning_source_adapters import (
    adapt_d3_a1_runtime_frame,
    build_d4_v8_runtime_episode,
    build_d5_a3_runtime_episode,
)
from research_modules.scalable_3d_simulation.learning_source_recipes import (
    load_d5_a3_v3_episode_recipes,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


ROOT = Path(__file__).resolve().parents[3]
D4_REQUEST_ROOT = (
    ROOT
    / "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)
D4_REQUEST_PATH = D4_REQUEST_ROOT / "v8_development_data_request.json"
D4_REGISTRY_PATH = D4_REQUEST_ROOT / "v8_development_seed_registry.json"
D5_SCHEDULE_PATH = (
    ROOT
    / "research_modules/d5_terminal_association/configs/"
    "a3_v3_source_collection_schedule_20260801.json"
)


def _stack(*, d5_collection: bool = False) -> IntegratedScalableModuleStack:
    return IntegratedScalableModuleStack(
        IntegratedStackConfig(
            capture_learning_artifacts=True,
            d5_recon_track_cues_enabled=d5_collection,
            d5_active_vision_collection_profile=(
                "balanced_action_role_v1" if d5_collection else "operational_v1"
            ),
        )
    )


def test_actual_d3_planning_frame_adapts_with_dual_time_and_demand_slots() -> None:
    config = ScenarioConfig(
        scenario_name="d3-adapter-smoke",
        scenario_version="d3-adapter-smoke-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=1,
        duration_s=2.0,
        seed=31_001,
        radar_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
    )
    stack = _stack()

    result = run_episode(config, module_stack=stack)
    runtime_frame = stack.learning_artifacts().d3_a1_source_frames[0]
    adapted = adapt_d3_a1_runtime_frame(runtime_frame)

    assert result.summary["online_truth_use_count"] == 0
    assert adapted.arrival_timestamp_s > adapted.measurement_timestamp_s
    assert adapted.observed_target_count == len(adapted.target_demand_slots)
    assert all(value >= 1 for value in adapted.target_demand_slots)
    assert set(adapted.teacher_edges).issubset(
        set(adapted.candidate_mask_true_edges)
    )
    assert "TGT-" not in repr(adapted)


@pytest.fixture(scope="module")
def d4_runtime_episodes():
    frozen = load_v8_frozen_request(D4_REQUEST_PATH, D4_REGISTRY_PATH)
    episodes = {}
    for target_class in (
        V8TransferClass.SAFE_FORWARD,
        V8TransferClass.SAFE_REVERSE,
        V8TransferClass.HARD_NO_TRANSFER,
    ):
        recipe = next(
            item
            for item in frozen.schedule
            if item.requested_target_class == target_class
        )
        config = ScenarioConfig(
            scenario_name="nominal",
            scenario_version="nominal-v1",
            target_count=16,
            resource_count=16,
            recon_count=2,
            region_count=recipe.region_count,
            duration_s=3.0,
            seed=recipe.seed,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
            metadata={
                "learning_source_recipe": {
                    "module": "D4",
                    **recipe.to_registry_dict(),
                }
            },
        )
        stack = _stack()
        result = run_episode(config, module_stack=stack)
        episode = build_d4_v8_runtime_episode(
            recipe=recipe,
            episode_id=f"d4-v8-adapter-smoke-{recipe.seed}",
            region_frames=stack.learning_artifacts().d4_region_frames,
        )
        episodes[target_class] = (recipe, episode, result)
    return episodes


def test_actual_d4_runtime_builds_forward_reverse_and_hard_negative(
    d4_runtime_episodes,
) -> None:
    forward = d4_runtime_episodes[V8TransferClass.SAFE_FORWARD][1]
    reverse = d4_runtime_episodes[V8TransferClass.SAFE_REVERSE][1]
    negative = d4_runtime_episodes[V8TransferClass.HARD_NO_TRANSFER][1]

    assert all(item[2].summary["online_truth_use_count"] == 0 for item in d4_runtime_episodes.values())
    assert all(frame.projected_transfers for frame in forward.frames)
    assert all(frame.projected_transfers for frame in reverse.frames)
    assert all(not frame.projected_transfers for frame in negative.frames)
    assert all(label.hard_negative_reasons for label in negative.labels)


@pytest.fixture(scope="module")
def d5_runtime_episodes():
    main_recipes = load_d5_a3_v3_episode_recipes(D5_SCHEDULE_PATH)
    module_recipes = load_frozen_a3_v3_episode_recipes(
        source_schedule_path=D5_SCHEDULE_PATH
    )
    episodes = []
    for entry_index in range(5):
        seed = 31_100 + entry_index
        main_recipe = main_recipes[entry_index]
        recipe_payload = module_recipes[entry_index].to_dict()
        recipe_payload.update(
            {
                "seed": seed,
                "episode_id": f"d5-a3-v3-adapter-smoke-{seed}",
                "scale": 5,
                "target_count": 5,
                "resource_count": 5,
                "recon_count": 2,
            }
        )
        adapter_recipe = A3V3EpisodeRecipeV1.from_dict(recipe_payload)
        base = ScenarioConfig(
            target_count=5,
            resource_count=5,
            recon_count=2,
            region_count=1,
            duration_s=6.0,
            seed=seed,
            visual_period_s=0.05,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
        )
        config = main_recipe.build_config(base)
        metadata = dict(config.metadata)
        metadata["learning_source_recipe"] = {
            **dict(metadata["learning_source_recipe"]),
            "seed": seed,
            "episode_id": adapter_recipe.episode_id,
        }
        config = replace(
            config,
            seed=seed,
            target_count=5,
            resource_count=5,
            recon_count=2,
            visual_period_s=0.05,
            metadata=metadata,
        )
        stack = _stack(d5_collection=True)
        result = run_episode(config, module_stack=stack)
        frames = stack.learning_artifacts().d5_active_vision_frames
        online, offline = build_d5_a3_runtime_episode(
            recipe=adapter_recipe,
            active_vision_frames=frames,
        )
        episodes.append(
            {
                "entry_index": entry_index,
                "frames": frames,
                "online": online,
                "offline": offline,
                "result": result,
            }
        )
    return tuple(episodes)


def test_actual_d5_runtime_covers_all_boundaries_and_window_quotas(
    d5_runtime_episodes,
) -> None:
    families = set()
    for episode in d5_runtime_episodes:
        assert episode["result"].summary["online_truth_use_count"] == 0
        counts = Counter(item.window_id for item in episode["online"].samples)
        assert all(counts[item.window_id] >= 24 for item in episode["online"].recipe.intent_windows)
        families.update(item.family for item in episode["offline"].boundary_pairs)

    assert families == {
        "observe_vs_reacquire_projection_boundary",
        "search_vs_reacquire_cue_loss_boundary",
        "hold_vs_observe_gimbal_busy_boundary",
        "role_matched_interceptor_recon_geometry",
        "multiple_legal_targets_near_tie",
    }
    near_tie_pairs = [
        pair
        for episode in d5_runtime_episodes
        for pair in episode["offline"].boundary_pairs
        if pair.family == "multiple_legal_targets_near_tie"
    ]
    assert near_tie_pairs
    assert all(
        pair.left_state.legal_target_count >= 2
        and pair.right_state.legal_target_count >= 2
        and pair.left_state.projection_quality_gap <= 0.05
        and pair.right_state.projection_quality_gap <= 0.05
        for pair in near_tie_pairs
    )


def _d3_smoke_evidence(frame_index: int) -> A1V3AdapterFrameEvidence:
    measurement = 0.1 * frame_index
    teacher_resources = (0, 1, 0, 1, 1, 1, 1, 1, 1)
    hard_frames = {0, 4}
    teacher_resource = teacher_resources[frame_index]
    candidate_resource = (
        1 - teacher_resource if frame_index in hard_frames else teacher_resource
    )
    return A1V3AdapterFrameEvidence(
        frame_index=frame_index,
        measurement_timestamp_s=measurement,
        arrival_timestamp_s=measurement + 0.01,
        observed_target_count=1,
        observed_resource_count=2,
        candidate_mask_shape=(1, 2),
        candidate_mask_true_edges=((0, 0), (0, 1)),
        rule_cost_matrix=((1.0, 1.001),),
        teacher_edges=((0, teacher_resource),),
        candidate_selected_edges=((0, candidate_resource),),
        effective_selected_edges=((0, teacher_resource),),
        residual_ranking=(
            A1V3EdgeResidualRank(edge=(0, 0), residual=0.0, rank=1),
            A1V3EdgeResidualRank(edge=(0, 1), residual=0.001, rank=2),
        ),
        target_demand_slots=(1,),
        pre_projection_reason_codes=("rule_candidate_available",),
        post_projection_reason_codes=("effective_plan_projected",),
    )


def test_strict_writers_stage_one_synthetic_episode_without_finalizing_inventory(
    tmp_path: Path,
    d4_runtime_episodes,
    d5_runtime_episodes,
) -> None:
    d3_contract = load_a1_v3_writer_contract()
    d3_episode = d3_contract.schedule.episodes[0]
    d3_evidence = [_d3_smoke_evidence(index) for index in range(9)]
    d3_writer = A1V3DatasetWriter(
        tmp_path / "d3",
        dataset_id="main-adapter-smoke-d3",
        contract=d3_contract,
    )
    d3_summary = d3_writer.stage_episode(
        d3_episode,
        d3_evidence,
    )
    assert d3_summary.frame_count == 9
    assert d3_writer.staged_episode_count == 1

    d4_recipe, d4_episode, _ = d4_runtime_episodes[
        V8TransferClass.SAFE_FORWARD
    ]
    d4_metadata = V8CleanSourceMetadata(
        source_scenario_id="main-adapter-smoke",
        source_scenario_version="main-adapter-smoke-v1",
        source_git_commit="a" * 40,
        source_git_dirty=False,
        source_config_sha256="b" * 64,
    )
    d4_writer = V8TrainDatasetWriter.from_contract_files(
        dataset_root=tmp_path / "d4" / "dataset",
        main_schedule_path=tmp_path / "d4" / "schedule.json",
        request_path=D4_REQUEST_PATH,
        registry_path=D4_REGISTRY_PATH,
        expected_source_metadata=d4_metadata,
        schedule_id="main-adapter-smoke-d4-schedule",
        dataset_id="main-adapter-smoke-d4-dataset",
    )
    d4_staged = d4_writer.stage_episode(
        schedule_index=0,
        episode_id=d4_episode.episode_id,
        frames=d4_episode.frames,
        labels=d4_episode.labels,
        source_metadata=d4_metadata,
    )
    assert d4_staged.seed == d4_recipe.seed
    d4_writer.abort()
    assert not (tmp_path / "d4" / "dataset").exists()

    frozen_d5_recipe = load_frozen_a3_v3_episode_recipes(
        source_schedule_path=D5_SCHEDULE_PATH
    )[0]
    d5_online, d5_offline = build_d5_a3_runtime_episode(
        recipe=frozen_d5_recipe,
        active_vision_frames=d5_runtime_episodes[0]["frames"],
    )
    descriptor = stage_a3_v3_episode_evidence(
        development_dir=tmp_path / "d5" / "development",
        future_held_out_dir=tmp_path / "d5" / "future",
        online=d5_online,
        offline=d5_offline,
    )
    root = tmp_path / "d5" / "development"
    decoded_online = A3V3OnlineEpisodeEvidenceV1.from_dict(
        json.loads((root / descriptor["online_file"]).read_text(encoding="utf-8"))
    )
    decoded_offline = A3V3OfflineEpisodeAuditV1.from_dict(
        json.loads((root / descriptor["offline_file"]).read_text(encoding="utf-8"))
    )
    assert decoded_online.to_dict() == d5_online.to_dict()
    assert decoded_offline.to_dict() == d5_offline.to_dict()
    assert not (root / "manifest.json").exists()


def test_actual_d3_adapter_reason_codes_are_writer_canonical() -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(capture_learning_artifacts=True)
    )
    result = run_episode(
        ScenarioConfig(
            target_count=5,
            resource_count=5,
            recon_count=1,
            duration_s=2.0,
            seed=31_901,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
        ),
        module_stack=stack,
    )
    assert result.summary["online_truth_use_count"] == 0
    adapted = adapt_d3_a1_runtime_frame(
        stack.learning_artifacts().d3_a1_source_frames[0]
    )
    contract = load_a1_v3_writer_contract()
    frame = build_a1_v3_online_frame(contract.schedule.episodes[0], adapted)

    assert tuple(frame.pre_projection_reason_codes) == tuple(
        sorted(frame.pre_projection_reason_codes)
    )
    assert tuple(frame.post_projection_reason_codes) == tuple(
        sorted(frame.post_projection_reason_codes)
    )
