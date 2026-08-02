from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
    A1V3DatasetWriter,
    build_a1_v3_online_frame,
    load_a1_v3_writer_contract,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_sidecar_classification import (
    derive_a1_v3_frame_classifications,
)
from research_modules.scalable_3d_simulation.learning_source_adapters import (
    adapt_d3_a1_runtime_frame,
)
from research_modules.scalable_3d_simulation.learning_source_recipes import (
    load_d3_a1_v3_episode_recipes,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEDULE_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_generation_schedule_v1.json"
)
BASE_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/nominal_200v200.json"
)
EXPECTED_COUNTS = {
    "a1-v3-cell-00-train-00": (10, 3, 7, 3),
    "a1-v3-cell-01-train-00": (10, 3, 7, 6),
    "a1-v3-cell-02-train-00": (10, 7, 3, 3),
    "a1-v3-cell-03-train-00": (10, 4, 6, 6),
    "a1-v3-cell-04-train-00": (10, 6, 4, 4),
    "a1-v3-cell-05-train-00": (9, 3, 6, 6),
    "a1-v3-cell-06-train-00": (10, 3, 7, 5),
    "a1-v3-cell-07-train-00": (10, 3, 7, 5),
    "a1-v3-cell-08-train-00": (10, 3, 7, 7),
    "a1-v3-cell-09-train-00": (10, 5, 5, 5),
    "a1-v3-cell-10-train-00": (10, 5, 5, 5),
    "a1-v3-cell-11-train-00": (10, 3, 7, 6),
    "a1-v3-cell-12-train-00": (10, 3, 7, 3),
    "a1-v3-cell-13-train-00": (10, 7, 3, 3),
    "a1-v3-cell-14-train-00": (10, 3, 7, 7),
}


@pytest.fixture(scope="module")
def frozen_runtime_stage_summaries(tmp_path_factory: pytest.TempPathFactory):
    base = ScenarioConfig.from_dict(
        json.loads(BASE_CONFIG_PATH.read_text(encoding="ascii"))
    )
    recipes = {
        item.episode_id: item
        for item in load_d3_a1_v3_episode_recipes(SCHEDULE_PATH)
        if item.episode_id in EXPECTED_COUNTS
    }
    contract = load_a1_v3_writer_contract()
    scheduled = {item.episode_id: item for item in contract.schedule.episodes}
    output_root = tmp_path_factory.mktemp("d3-a1-v3-runtime-to-writer")
    summaries = {}

    for episode_id in EXPECTED_COUNTS:
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(
            recipes[episode_id].build_config(base), module_stack=stack
        )
        adapted = tuple(
            adapt_d3_a1_runtime_frame(frame)
            for frame in stack.learning_artifacts().d3_a1_source_frames
        )
        online = tuple(
            build_a1_v3_online_frame(scheduled[episode_id], frame)
            for frame in adapted
        )
        classified = derive_a1_v3_frame_classifications(
            scheduled[episode_id],
            online,
            request=contract.request,
            policy=contract.sidecar_classification_policy,
        )
        class_counts = Counter(item.frame_class for item in classified)
        counts = (
            class_counts["positive"],
            class_counts["negative"],
            sum(item.hard_negative for item in classified),
        )
        assert result.summary["online_truth_use_count"] == 0
        assert all(
            frame.to_dict()["online_truth_use_count"] == 0
            and not any(frame.to_dict()["permissions"].values())
            for frame in online
        )
        writer = A1V3DatasetWriter(
            output_root / episode_id,
            dataset_id=f"d3-runtime-regression-{episode_id}",
            contract=contract,
        )
        summary = writer.stage_episode(scheduled[episode_id], adapted)
        assert counts == (
            summary.positive_frame_count,
            summary.negative_frame_count,
            summary.hard_negative_frame_count,
        )
        stage_paths = tuple(
            (output_root / episode_id / ".a1_v3_staging/episodes").glob(
                "*.json"
            )
        )
        assert len(stage_paths) == 1
        staged = json.loads(stage_paths[0].read_text(encoding="ascii"))
        assert all(
            frame["online_truth_use_count"] == 0
            and not any(frame["permissions"].values())
            for frame in staged["online_frames"]
        )
        summaries[episode_id] = (len(classified), *counts)
    return summaries


@pytest.mark.parametrize("episode_id", tuple(EXPECTED_COUNTS))
def test_real_frozen_recipe_matches_strict_natural_sidecar_quota_audit(
    frozen_runtime_stage_summaries,
    episode_id: str,
) -> None:
    frame_count, positive, negative, hard_negative = (
        frozen_runtime_stage_summaries[episode_id]
    )
    assert (frame_count, positive, negative, hard_negative) == EXPECTED_COUNTS[
        episode_id
    ]
    assert positive >= 3 and negative >= 3 and hard_negative >= 2
